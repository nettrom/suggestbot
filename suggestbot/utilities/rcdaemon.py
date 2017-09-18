#!/usr/bin/env python
# -*- coding: utf-8  -*-
'''
Daemon that polls recentchanges for our configured Wikipedias at regular
intervals and updates the edit database with info.
'''

import re
import os
import time
import signal
import codecs
import logging
import datetime

import pywikibot
import MySQLdb

from time import sleep

from suggestbot import config
from suggestbot import db
import suggestbot.utilities.reverts as sur

class RecentChangesDaemon:
    def __init__(self):
        '''
        Instantiate a RecentChangesDaemon
        '''

        self.db = db.SuggestBotDatabase()

        # Flag set by our signal handler if we receive SIGUSR1,
        # daemon will then shutdown cleanly upon next iteration
        # of its infinite loop.
        self.shutdown = False

        # Flag defining if we're running while SuggestBot is processing
        # subscribers (in any language)
        self.dailyRunning = False

    def handleSignal(self, signum, stack):
        '''
        Handle incoming signals, specifically SIGUSR1, which we'll use
        to quit gracefully.
        '''
        self.shutdown = True
        return()

    def run(self):
        '''
        Run as a daemon for as long as possible.
        '''

        # Query to get the most recent edit in a given revision table...
        most_recent_query = """SELECT
                               MAX(rev_timestamp) AS mostrecent
                               FROM {}"""

        logging.info("registering signal handler for SIGUSR1")

        # Set up a signal handler for SIGUSR1
        signal.signal(signal.SIGUSR1, self.handleSignal)

        logging.info("running infinite loop")

        # Loop for as long as we need to...
        while not self.shutdown:
            # connect to the database
            if not self.db.connect():
                logging.error("unable to connect to the database")
                return()

            (db_conn, db_cursor) = self.db.getConnection()

            # for each of the Wikipedias we know something about...
            for lang in config.lang_codes.keys():
                logging.info("checking {}wiki".format(lang))

                db_cursor.execute(most_recent_query.format(
                    config.revision_table[lang]))
                row = db_cursor.fetchone()
                db_cursor.fetchall() # flush cursor...
                if not row:
                    logging.error("unable to get most recent edit for {}wiki".format(lang))
                    continue
                
                logging.info("most recent edit was {}".format(
                    row['mostrecent']))
                
                # check if enough time has passed
                timelapse = datetime.datetime.utcnow() - row['mostrecent']
                logging.info("time lapsed since most recent edit: {} days, {} seconds".format(timelapse.days, timelapse.seconds))

                if (timelapse.days > 0) \
                   or (timelapse.seconds >= config.rc_delay):
                    # Convert 'then' to a pywikibot.Timestamp object...
                    then = pywikibot.Timestamp.fromtimestampformat(
                        then.strftime("%Y%m%d%H%M%S"))
                    self.get_revisions(lang, fromTime=then)

            self.db.disconnect()
            # Ok, now sleep for a while...
            logging.info("sleeping for 300 seconds...")
            sleep(300)
            
        return()

    def update(self, lang):
        '''
        Fetch recent changes for a single language.

        :param lang: language code of the Wikipedia to fetch data from
        :type lang: str
        '''

        # Query to get the most recent edit in a given revision table...
        most_recent_query = """SELECT
                               MAX(rev_timestamp) AS mostrecent
                               FROM {}"""
        
        # connect to the database
        if not self.db.connect():
            logging.error("unable to connect to the database")
            return()

        (db_conn, db_cursor) = self.db.getConnection()

        logging.info("checking {0}wiki".format(lang))

        db_cursor.execute(most_recent_query.format(config.revision_table[lang]))
        row = db_cursor.fetchone()
        db_cursor.fetchall() # flush cursor...
        if not row:
            logging.warning("unable to get most recent edit for {}wiki".format(
                lang))
            return()

        logging.info("most recent edit was {0}".format(row['mostrecent']))

        # check if enough time has passed
        # since the most recent edit was made...
        now = datetime.datetime.utcnow()
        then = row['mostrecent']
        if then is None:
            logging.info('no revisions in table, fetching everything from recentchanges')
            self.get_revisions(lang)
        else:
            timelapse = now - then
            logging.info(u"time lapsed since most recent edit: {0} days, {1} seconds".format(timelapse.days, timelapse.seconds))
            if timelapse.days > 0 \
                   or timelapse.seconds >= config.rc_delay:
                # Convert 'then' to a pywikibot.Timestamp object...
                then = pywikibot.Timestamp.fromtimestampformat(then.strftime("%Y%m%d%H%M%S"))
                self.get_revisions(lang, fromTime=then)

        self.db.disconnect()
        
        # ok, done
        return()

    def get_revisions(self, lang, fromTime=None, toTime=None):
        '''
        Make a request to the API on the given language Wikipedia to get
        recent changes from one timestamp to another timestamp, or from
        a timestamp to whatever is last available.

        :param lang: language code of the Wikipedia we're fetching data from
        :type lang: str

        :param fromTime: timestamp to start fetching recentchanges from
        :type fromTime: pywikibot.Timestamp

        :param toTime: timestamp to end fetching recentchanges
        :type toTime: pywikibot.Timestamp
        '''

        logging.info("fetching recent changes for {}wiki".format(lang))

        # get site
        site = pywikibot.Site(lang)

        # check if we have apihighlimits and set step as necessary
        step_limit = 500
        if site.has_right('apihighlimits'):
            step_limit = 5000

        # Create our recent changes generator that only grabs edits
        # and creation of new pages from the Main namespace, and filters
        # out anonymous edits, bots, and redirects.
        # NOTE: we discard redirects because they're not articles we're
        #       interested in recommending to anyone (instead we'd like to
        #       recommend the article it redirects to, but that's currently
        #       too much work to keep track of)
        # NOTE: as you can see we also discard anonymous users.
        rc_gen = site.recentchanges(start=fromTime,
                                    end=toTime,
                                    step=step_limit,
                                    reverse=True,
                                    namespaces=[0],
                                    showAnon=False,
                                    showBot=False,
                                    showRedirects=False,
                                    changetype="edit|new")
        self.update_database(lang, rc_gen)
        return()

    def update_database(self, lang, generator):
        '''
        Update the database for the given language with the recent changes info
        returned by the given generator.

        :param lang: Wikipedia language edition we're updating
        :type lang: str
        
        :param generator: Recent changes generator with data we want to store
        :type generator: pywikibot.api.ListGenerator
        '''

        if not lang in config.lang_codes.keys():
            logging.error("parameter 'lang' set to '{}', which is not found in the configuration".format(lang))
            return()

        if not lang in sur.REVERT_RE.keys():
            logging.error("language '{}' not configured in the reverts library".format(lang))
            return()

        # NOTE: this uses the MySQL extension to SQL that adds
        # "ON DUPLICATE KEY UPDATE ..." to update the values if
        # the revision ID is already in the table.
        insert_query = """INSERT INTO {}
                          (rev_id, rev_title, rev_user, rev_timestamp,
                           rev_length, rev_delta_length, rev_is_identical,
                           rev_comment_is_revert, rev_is_minor)
                          VALUES (%(revid)s, %(title)s, %(username)s,
                                  %(timestamp)s, %(length)s, %(delta)s,
                                  %(identical)s, %(revert)s, %(minor)s)
                          ON DUPLICATE KEY UPDATE
                          rev_title=%(title)s, rev_user=%(username)s,
                          rev_timestamp=%(timestamp)s, rev_length=%(length)s,
                          rev_delta_length=%(delta)s,
                          rev_is_identical=%(identical)s,
                          rev_comment_is_revert=%(revert)s,
                          rev_is_minor=%(minor)s""".format(
                              config.revision_table[lang])

        # Query to delete revisions that are older than a given timestamp
        delete_query = """DELETE FROM {}
                          WHERE rev_timestamp < %(timestamp)s""".format(
                              config.revision_table[lang])

        # We should already be connected to the database...
        (db_conn, db_cursor) = self.db.getConnection()

        # An example revision from Swedish Wikipedia:
        # {u'comment': u"Skapade sidan med '{{Filmfakta |filmtitel=Tidsmaskinen |originaltitel=The Time Machine |genre=[[Science Fiction]] |land={{flaggbild2|USA}} |spr\xe5k=[[Engelska]] |\xe5r=1960 |regi=[[George Pal]] |fo...'",
        #  u'rcid': 15184824,
        #  u'pageid': 1505532,
        #  u'title': u'Tidsmaskinen (film)',
        #  u'timestamp': u'2011-10-07T20:15:26Z',
        #  u'revid': 15053319,
        #  u'old_revid': 0,
        #  u'user': u'Okvadsomhelst',
        #  u'new': u'',
        #  u'ns': 0,
        #  u'type': u'new'}

        # The key u'minor' exists if it's a minor edit.

        # Regular expression used to identify reverts
        revert_re  = sur.REVERT_RE[lang]

        # list of revisions, pushed to executemany()
        revisions = []

        ## counter to trigger commits
        num_inserted_revisions = 0
        
        for revdata in generator:
            is_revert = 0
            is_minor = 1
            delta_length = 0
            length = 0
            is_identical = 1

            # Check if we have a user, a revision ID, and an edit comment,
            # otherwise we'll skip this revision. (This info might be deleted
            # from revisions, e.g. due to abuse)
            if revdata['revid'] is None \
               or 'user' not in revdata \
               or not revdata['user']:
                logging.info(u"no rev ID or user info in revision {}".format(
                    revdata['rcid']))
                continue

            ## Comments might also be deleted
            if 'comment' not in revdata:
                logging.info("no comment info in revision {}".format(
                    revdata['rcid']))
                revdata['comment'] = u''
               
            # Parse the timestamp
            try:
                timestamp = pywikibot.Timestamp.fromISOformat(
                    revdata['timestamp'])
            except ValueError:
                logging.warning('unable to parse timestamp {}'.format(
                    revdata['timestamp']))
                timestamp = None

            # check if it's a revert
            if re.search(revert_re, revdata['comment'], re.VERBOSE):
                is_revert = 1

            # if English we'll also check VLOOSE and VSTRICT
            if lang == u'en' and \
               (re.search(sur.VSTRICT_RE, revdata['comment'], re.VERBOSE) \
                or re.search(sur.VLOOSE_RE, revdata['comment'], re.VERBOSE)):
                is_revert = 1

            # check if it's a minor edit
            if 'minor' in revdata:
                is_minor = 1

            # push revision data for later updating.
            try:
                db_cursor.execute(insert_query,
                                  {'revid': revdata['revid'],
                                   'title': revdata['title'].encode('utf-8'),
                                   'username': revdata['user'].encode('utf-8'),
                                   'timestamp': timestamp,
                                   'length': length,
                                   'delta': delta_length,
                                   'identical': is_identical,
                                   'revert': is_revert,
                                   'minor': is_minor})
                num_inserted_revisions += 1
            except MySQLdb.Error as e:
                logging.error('failed to insert revision data')
                logging.error('MySQL Error: {} : {}'.format(e.args[0],
                                                            e.args[1]))
            if num_inserted_revisions == 500:
                logging.info('inserted 500 revisions, committing')
                db_conn.commit()
                num_inserted_revisions = 0

        # Commit any outstanding data
        logging.info("done inserting revisions, deleting old revisions")

        # Delete old revisions, a simple now - RC_KEEP days calculation...
        cutoff = datetime.datetime.utcnow() \
                 - datetime.timedelta(days=config.rc_keep[lang])
        try:
            db_cursor.execute(delete_query, {'timestamp': cutoff})
            db_conn.commit()
        except MySQLdb.Error as e:
            logging.error("unable to delete revisions from database")
            logging.error("MySQL Error {}: {}" % (e.args[0], e.args[1]))

        logging.info("info: done deleting old revisions")

        # ok, done
        return()
