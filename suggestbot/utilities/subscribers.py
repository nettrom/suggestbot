#!/usr/env/python
# -*- coding: utf-8 -*-
"""
Library for updating the list of subscribers stored in SuggestBot's
local database.

Relies on sql/regular_users.sql for the format of the database
and config.py for definition of natural language phrases
for parameter values, and which pages to ignore when looking for links.

Copyright (C) 2005-2017 SuggestBot Dev Group

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Library General Public
License as published by the Free Software Foundation; either
version 2 of the License, or (at your option) any later version.

This library is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
Library General Public License for more details.

You should have received a copy of the GNU Library General Public
License along with this library; if not, write to the
Free Software Foundation, Inc., 51 Franklin St, Fifth Floor,
Boston, MA  02110-1301, USA.
"""

__version__ = "$Id$"

import re
import time
import codecs
import logging

from random import shuffle

from datetime import datetime, timedelta

import pywikibot
from pywikibot.pagegenerators import PreloadingGenerator

import mwparserfromhell as mwp

from suggestbot import suggestbot
from suggestbot import config
from suggestbot import db

import MySQLdb

class Subscriber(pywikibot.User):
    '''
    Object for a subcriber of SuggestBot.  Reflects the values
    found in the regular users table in the suggestbot database.
    '''
    def __init__(self, lang, username, site=None):
        '''
        Instantiate a subscriber on the given Wikipedia with the given
        username.

        :param lang: Language code of the Wikipedia the user belongs to
        :type lang: str

        :param username: Name of the user
        :type username: str

        :param site: Site the user belongs to
        :type site: pywikibot.Site
        '''
        super(Subscriber, self).__init__(site, username)

        ## NOTE: We could have used self._lang = site.lang, but that breaks
        ## because in some editions the language code (e.g. "nb") differs
        ## from the site's URL (e.g. "no.wikipedia.org").
        self._lang = lang
        self._username = username
        
        if site is None:
            self._site = pywikibot.Site(lang)
        else:
            self._site = site
            

        # Default status is that we're not processing this user, and
        # they haven't gotten any suggestions
        self._status = 'idle'
        self._last_rec = None
        
        # Default values define the bot to not post to a specific sub-page,
        # once a month, that replacement of existing suggestions is not done,
        # and that recommendations are posted with a level 2 heading (== ==)
        self._page_title = None
        self._weekday = None
        self._time = None
        self._period = 0
        self._replace = 0
        self._headlevel = 2

        # Default is also that this user is seen, is still requesting
        # suggestions, and is an active contributor to Wikipedia.
        self._seen = 1
        self._active = 1
        self._retired = 0

        # Default is that this user gets the 'full' design, whatever that is
        self._design = 'full'

        # Default is that the user has not withdrawn from any given study
        self._withdrawn = 0

    def __str__(self):
        return("""{}:User:{}
Last rec: {}
Replace: {}
Subpage: {}
Period: {}
Active: {}
Retired: {}""".format(self._lang, self._username, self._last_rec,
                       self._replace, self._page_title, self._period,
                       self._active, self._retired))
        
    def useParam(self, key, value):
        '''
        Method to store values in the user object based on mapping
        to global template parameters.
        '''
        # These are the global parameters we currently grok:

        # desired frequency of receiving suggestions:
        if key == 'frequency':
            # Expect to get a value that's an int
            self._period = self._freq2int(value)
        elif key == 'replace':
            # Expect to get an int back (yes=1, no=0)
            self._replace = self.parseYesNo(value)
        elif key == 'headlevel':
            # Expect value to be an int
            self._headlevel = 2
            try:
                self._headlevel = int(value)
            except ValueError:
                pass

        # Ok, done
        return
        
    def _freq2int(self, frequency):
        '''
        Translate a given frequency string to a numerical value.

        :param frequency: The frequency requested, must match one of
                          the config's regular expressions
                          'once_monthly', 'twice_monthly', or 'weekly'.
        :type frequency: str
        '''

        # Default value is once a month.
        if not frequency:
            return 0

        if re.match(config.once_monthly[self._lang],
                    frequency, re.IGNORECASE):
            return 0
        if re.match(config.twice_monthly[self._lang],
                    frequency, re.IGNORECASE):
            # Twice a month
            return 14
        if re.match(config.weekly[self._lang],
                    frequency, re.IGNORECASE):
            # Weekly
            return 7

        logging.warning("user {0} used a non-matching frequency {1}".format(self._username, frequency))
        # Return the default (once a month)
        return 0

    def parseYesNo(self, value):
        '''
        Translate a yes/no value in a given language to yes=1, no=0

        :param value: The text string of the value for this parameter
        :type value: str
        '''
        if not value\
           or re.match(config.re_yes[self._lang], value, re.IGNORECASE):
            return 1

        if re.match(config.re_no[self._lang], value, re.IGNORECASE):
            return 0

        # Default is to return "no"
        return 0

    def _sbot_edited(self, page):
        '''
        Did SuggestBot edit this page? If not return None, otherwise
        return the edit timestamp as a string.

        :param page: The page we're checking
        :type page: pywikibot.Page
        '''

        history = page.getVersionHistory()
        hist_length = len(history)
        edited = None
        i = 0
        logging.debug("potentially checking {n} edits to {title}".format(
            n=hist_length, title=page.title()))
        while i < hist_length and not edited:
            (revid, edittime, username, summary) = history[i]
            # I can just check what username I'm logged in
            # as and then use that... duh!
            if username == self.site.user():
                logging.debug("found SBot contribution at time {timestamp}".format(timestamp=edittime.strftime("%Y%m%d%H%M%S")))
                edited = edittime
                
            i += 1

        return(edited)
                
    def _insert(self, sbdb=None):
        '''
        Insert a new row into the database with this user's information.

        :param sbdb: Connection to the database.
        :type sbdb: suggestbot.db.SuggestBotDatabase
        '''

        if not sbdb:
            sbdb = db.SuggestBotDatabase()
            if not sbdb.connect():
                logging.error("Unable to connect to the SuggestBot database")
                return(False)
            
        (dbconn, dbcursor) = sbdb.getConnection()

        # NOTE: default values of the 'active', 'retired', 'design',
        # and 'withdrawn' columns makes it unnecessary to specify
        # the values of those colums.
        insert_query = '''INSERT INTO {}
                          (lang, username, last_rec, page_title, period,
                           replace_recs, headlevel)
                          VALUES (%(lang)s, %(username)s, %(last_rec)s,
                          %(page)s, %(period)s, %(replace)s,
                          %(headlevel)s)'''.format(config.regulars_table)
   
        # go look for posts by SuggestBot on:
        # 1: a userspace sub-page, if they've got the template there
        # 2: their user talk page
        subpage_edit = None
        usertalkpage_edit = None

        # Note: the subpage will always have a history because otherwise
        # the user couldn't have put the SuggestBot template there.
        if self._page_title is not None:
            subpage_edit = self._sbot_edited(pywikibot.Page(self._site,
                                                            self._page_title))
            
        usertalkpage = self.getUserTalkPage()
        if usertalkpage.exists():
            usertalkpage_edit = self._sbot_edited(usertalkpage)

        # If one is None, but not the other, use the one that's not None.
        if usertalkpage_edit is not None and subpage_edit is None:
            logging.debug("using edit to user talk page as last rec timestamp.")
            self.last_rec = usertalkpage_edit.strftime("%Y%m%d%H%M%S")
        elif subpage_edit is not None:
            logging.debug("using edit to {} as last rec timestamp".format(
                self._page_title))
            self.last_rec = subpage_edit.strftime("%Y%m%d%H%M%S")
        elif subpage_edit is not None and usertalkpage_edit is not None:
            # If both are not None, then use the more recent one:
            logging.debug("using the more recent edit to either user talk page or sub page as last rec timestamp.")
            if usertalkpage_edit >= subpage_edit:
                self.last_rec = usertalkpage_edit.strftime("%Y%m%d%H%M%S")
            else:
                self.last_rec = subpage_edit.strftime("%Y%m%d%H%M%S")

        # No need for anything else, we'll then store NULL, and it will
        # be populated when the regular user update runs.

        max_retries = 3
        num_retries = 0
        done = False
        while num_retries < max_retries and not done:
            num_retries += 1
            try:
                # Store user info.
                dbcursor.execute(insert_query,
                                 {'lang': self._lang,
                                  'username': self._username,
                                  'last_rec': self._last_rec,
                                  'page': self._page_title,
                                  'period': self._period,
                                  'replace': self._replace,
                                  'headlevel': self._headlevel})
                if dbcursor.rowcount != 1:
                    logging.warning("insert of User:{username} resulted in {n} updated rows".format(
                        username=self._username,
                        n=dbcursor.rowcount))
                    dbconn.rollback()
                else:
                    dbconn.commit()
                    done = True
            except MySQLdb.Error as e:
                logging.error("unable to store User:{username}' in database".format(username=self._username).encode('utf-8'))
                logging.error("MySQL Error {}: {}".format(e.args[0], e.args[1]))
                ## If "CR_SERVER_GONE_ERROR" or "CR_SERVER_LOST",
                ## reconnect and retry if possible
                if e.args[0] == 2006 or e.args[0] == 2013:
                    sbdb.connect()
                    (dbconn, dbcursor) = sbdb.getConnection()

        logging.info("inserted the following new user:\n{}".format(self))
                    
        # ok, done
        return(True)

    def update(self, sbdb=None):
        '''
        Update the values for this user in the table for regular users in
        the suggestbot database.

        :param sbdb: Existing connection to the database.
        :type sbdb: suggestbot.db.SuggestBotDatabase
        '''

        # Does the user exist?
        user_exists_query = '''SELECT lang, username FROM {}
                               WHERE lang=%(lang)s
                               AND username=%(username)s'''.format(
                                   config.regulars_table)

        # NOTE: this also sets them as active if they've been inactive
        update_query = '''UPDATE {}
                          SET seen=1, active=1, page_title=%(page)s,
                          period=%(period)s, replace_recs=%(replace)s,
                          retired=%(retired)s, headlevel=%(headlevel)s
                          WHERE lang=%(lang)s
                          AND username=%(username)s'''.format(
                              config.regulars_table)

        if not sbdb:
            sbdb = db.SuggestBotDatabase()
            if not sbdb.connect():
                logging.error("Unable to connect to the SuggestBot database")
                return(False)

        (dbconn, dbcursor) = sbdb.getConnection()


        logging.info('checking if {}:User:{} is new'.format(self._lang,
                                                            self._username))
        try:
            dbcursor.execute(user_exists_query,
                             {'lang': self._lang,
                              'username': self._username})
            if dbcursor.fetchone() is None:
                # a new user, yay!
                logging.info('user is new')
                return(self._insert(sbdb))
        except MySQLdb.Error as e:
            logging.error("Unable to query database")
            logging.error("MySQL Error {}: {}".format(e.args[0], e.args[1]))
            return(False)
        
        max_retries = 3
        num_retries = 0
        done = False
        while num_retries < max_retries and not done:
            num_retries += 1
            try:
                # Update userinfo.
                dbcursor.execute(update_query,
                                 {'page': self._page_title,
                                  'period': self._period,
                                  'replace': self._replace,
                                  'headlevel': self._headlevel,
                                  'retired': self._retired,
                                  'lang': self._lang,
                                  'username': self._username})
                # ok, done
                dbconn.commit()
                done = True
                logging.info('committed on attempt {}'.format(num_retries))
                logging.info("Committed the following user data:\n{}".format(self))
            except MySQLdb.Error as e:
                dbconn.rollback()
                logging.error(
                    "Unable to update User:{username} in database.".format(
                        username=self._username))
                logging.error("MySQL Error %d: %s\n" % (e.args[0], e.args[1]))
                ## If "CR_SERVER_GONE_ERROR" or "CR_SERVER_LOST", try reconnect
                if e.args[0] == 2006 or e.args[0] == 2013:
                    sbdb.connect()
                    (dbconn, dbcursor) = sbdb.getConnection()

        # did something go wrong?
        if num_retries == max_retries:
            return(False)

        # ok, everything went well
        return(True)

class Subscribers:
    def __init__(self, lang):
        '''
        Initialise the subscriber updater object.
        
        :param lang: What language are we working with?
        :type lang: str
        '''

        # What Wikipedia language edition are we working with?
        self._lang = lang
        self._site = pywikibot.Site(self._lang)
        self._site.login()

    def _translate_key(self, key):
        '''
        Look up `key' in `config.template_parameters` for current language
        and return the global parameter name.
        '''

        params = config.template_parameters[self._lang]
        if not key in params:
            logging.warning('got key {} which does not translate to anything.'.format(key))
            return(None)

        # Return the global name
        return(params[key])

    def update_subscribers(self):
        '''
        Update the list of subscribers based on the current configuration

        '''
        # reset all seen-values of users of the current wiki,
        # and who are currently active 
        reset_query = r"""UPDATE {}
                          SET seen=0
                          WHERE lang=%(lang)s
                          AND active=1""".format(config.regulars_table)

        # query to set all unseen users as inactive, because it means
        # they no longer use the template
        inactive_query = r"""UPDATE {}
                             SET active=0
                             WHERE lang=%(lang)s
                             AND seen=0""".format(config.regulars_table)

        ## Connect to the database
        sbdb = db.SuggestBotDatabase()
        if not sbdb.connect():
            logging.error("Unable to connect to the suggestbot database")
            return(False)

        (dbconn, dbcursor) = sbdb.getConnection()

        ## Reset the `seen` bit for all active uers
        dbcursor.execute(reset_query,
                         {'lang': self._lang})
        dbconn.commit()
        logging.info('number of rows with updated seen-values: {}'.format(dbcursor.rowcount))

        # Build the set of pages that we'll ignore when we find links to
        # our templates.
        ignorePages = set()
        for page_title in config.template_stoplist[self._lang]:
            ignorePages.add(pywikibot.Page(self._site, page_title))

        # Grab the config templates for this language Wikipedia
        configTemplates = config.config_templates[self._lang]
        configPages = set()

        # Regular expression for splitting into username + subpage-name.
        subpageSplitRe = re.compile(r'(?P<username>[^/]+)(?P<subname>/.*)')

        # Loop over them, userbox first as any settings in the config template
        # is to take priority.
        for temp_nick in ['userbox', 'config']:
            configPage = pywikibot.Page(self._site,
                                        configTemplates[temp_nick])
            configPages.add(configPage.title().strip().lower())

            # Grab all links to the config template that are redirects
            warningsList = list(configPage.getReferences(
                onlyTemplateInclusion=True,
                redirectsOnly=True))

            # Output all of them to a file so we know which users might
            # have changed usernames.
            if len(warningsList) > 0:
                logging.info('writing {n} pages that are redirects to warnings file.'.format(n=len(warningsList)))

                with codecs.open(config.userlist_warnings, 'a',
                                 'utf-8') as warningsFile:
                    warningsFile.write("The following pages are redirects:\n")
                    for page in warningsList:
                        warningsFile.write(page.title())
                        warningsFile.write("\n")
                                
            # warningsList is now used as a list of pages that contain errors
            # that need fixing.  Values are tuples where the first item is the
            # pywikibot.Page object, and the second is a short description of
            # the problem.
            warningsList = []
        
            # For each page, that we're preloading 10 of at a time to
            # speed things up:
            for page in PreloadingGenerator(
                    configPage.getReferences(
                        onlyTemplateInclusion=True,
                        redirectsOnly=False),
                    step=10):
                # Is this one of our own pages?
                if page in ignorePages:
                    continue

                logging.info('now processing {}'.format(page.title()))

                #   figure out what user this page belongs to
                #   1: check that the page namespace is user or user talk
                if page.namespace() not in [2, 3]:
                    warningsList.append((page,
                                         "namespace not user or user talk"))
                    continue

                #   2: fetch the title without namespace
                page_title = page.title(withNamespace=False,
                                        withSection=False)

                # split the page title on first "/" in case it's a subpage.
                subpageTitle = None
                username = ''
                matchObj = subpageSplitRe.match(page_title)
                if matchObj:
                    # we have a subpage
                    # store subpage title in user object
                    subpageTitle = page.title()
                    username = matchObj.group('username')
                    logging.info('found subpage {subtitle} of user {username}'.format(
                        subtitle=matchObj.group('subname'), username=username))
                else:
                    username = page_title

                subscriber = Subscriber(self._lang, username, site=self._site)

                # check the timestamp of the user's last contribution,
                # set the retired bit if the user's no longer active.
                lastEditTuple = None
                try:
                    lastEditTuple = next(subscriber.contributions(total=5))
                except StopIteration:
                    # User apparently has made no edits, so there's no tuple
                    pass
                except KeyError:
                    # pywikibot had a bug that made it fail with a KeyError
                    # if a revision's comment was deleted.  That's fixed now,
                    # but we'll capture the exception just in case something
                    # else goes wrong and triggers it.
                    pass

                if lastEditTuple is not None:
                    lastEditTime = lastEditTuple[2]
                    logging.info('user last edited at {}'.format(lastEditTime))
                    timeSinceLastEdit = datetime.utcnow() - lastEditTime
                    if timeSinceLastEdit.days >= config.retired_days:
                        subscriber._retired = 1

                # NOTE: Don't add "if not subscriber.retired:" to skip
                # the template checking if the user is retired.  Don't do that.
                # It'll lead to us storing default values for our users in
                # the database, and since we've already fetched the page text,
                # this is cheap processing.

                parsed_page = mwp.parse(page.get(), skip_style_tags=True)
                #   call page.templatesWithParams()
                for template in parsed_page.filter_templates(recursive=True):
                    ## logging.info('checking template {}'.format(template.name))
                    template_name = template.name.strip().lower()
                    if not template_name in configPages:
                        continue

                    ## logging.info('checking parameters to known template {}'.format(template_name))

                    # This accounts for the case where a user has a subpage for
                    # their userboxes.  We'll post to their user talk page.
                    if subpageTitle is not None and template_name \
                       == configTemplates['userbox'].strip().lower():
                        subpageTitle = None

                    # for each parameter...
                    for param in template.params:
                        ## True if this is a key/value pair
                        if param.showkey:
                            # translate the key (e.g. Norwegian -> English)
                            translatedKey = self._translate_key(
                                param.name.strip().lower())
                        else:
                             translatedKey = self._translate_key(
                                 param.value.strip().lower())

                        if translatedKey is None:
                            warningsList.append((page, "unaccepted parameter"))
                            continue

                        ## logging.info("using parameter {} with value {}".format(translatedKey, param.value))

                        if param.showkey:
                            # parameter is OK, use it:
                            subscriber.useParam(translatedKey, param.value.strip().lower())
                        else:
                            ## Note: This works because the methods behave
                            ## sensibly if the value evaluates to False
                            subscriber.useParam(translatedKey, "")
                        
                # Always updating this ensures that we capture users who return
                # and do not specify where they want it posted.
                subscriber._page_title = subpageTitle

                ## FIXME: if we've gone through all the templates on a page
                ## and not found SuggestBot's template, we have a parsing error.
                ## In that case, we shouldn't update the database?
                
                logging.info('updating database for this user')
                
                # update or store values for this user
                subscriber.update(sbdb)

            if len(warningsList) > 0:
                logging.info("writing {n} users that have errors to warnings file".format(n=len(warningsList)))

                warningFilename = "{base}.{lang}".format(
                    base=config.userlist_warnings,
                    lang=self._lang)
                with codecs.open(warningFilename, 'a', 'utf-8') as \
                        warningsFile:
                    warningsFile.write("The following users had errors in their configuration:\n")
                    for (page, reason) in warningsList:
                        warningsFile.write(page.title())
                        warningsFile.write(" - %s" % (reason,))
                        warningsFile.write("\n")

        dbcursor.execute(inactive_query,
                         {'lang': self._lang})
        dbconn.commit()
        logging.info("number of users set as inactive: {}".format(dbcursor.rowcount))
        sbdb.disconnect()
        return()

    def post_suggestions(self):
        """
        Find all the subscribers in the SuggestBot database for
        the current language version of Wikipedia, check if any of them
        are due up for receiving suggestions, and then post suggestions
        to their user talk page (or userspace subpage if that is set).
        """

        # today is?
        # Note: We use UTC as the basis for our calculations, because
        # the Wikipedia API also returns timestamps as UTC, thus allowing
        # us to correctly post suggestions to new subscribers who saw
        # SuggestBot post to their user talk page earlier.
        now = datetime.utcnow()

        # Query to get all regular users of the current language versions
        getRegularsQuery = r"""SELECT *
                                FROM {}
                                WHERE lang=%(lang)s
                                AND active=1
                                AND retired=0""".format(config.regulars_table)

        # Query to update a specific user's status (to processing|idle|ready)
        setStatusQuery = r"""UPDATE {} SET status=%(status)s
                              WHERE lang=%(lang)s
                              AND username=%(username)s""".format(config.regulars_table)

        # Query to update a specific user's last recommendation time
        setLastrecQuery = r"""UPDATE {}
                               SET last_rec=%(rectime)s
                               WHERE lang=%(lang)s
                               AND username=%(username)s""".format(config.regulars_table)

        # Query to get the time of the last suggestion posted
        getLastRecQuery = r"""SELECT MAX(last_rec) AS last_rec
                               FROM {}
                               WHERE lang=%(lang)s
                               AND active=1""".format(config.regulars_table)

        # query to increment the number of recommendations count
        incRecCountQuery = r'''UPDATE {}
                                SET n_recs=n_recs+1
                                WHERE lang=%(lang)s
                                AND username=%(user)s'''.format(config.regulars_table)

        
        # Query to set (or reset) the busy bit in the status info table
        updateStatusTableQuery = r"""UPDATE {status}
                                      SET daily_running=%(status)s
                                      WHERE lang=%(lang)s""".format(status=config.status_table)

        # Query to check the busy bit in the status info table, so that
        # multiple updates don't run at the same time (otherwise we'll get
        # double-posts (how do we know that?  we tested it!))
        checkStatusTableQuery = r"""SELECT daily_running FROM {status}
                                     WHERE lang=%(lang)s""".format(status=config.status_table)

        # instantiate the database object, and connect
        myDb = db.SuggestBotDatabase()
        # if connection fails, fail too.
        if not myDb.connect():
            logging.error('unable to connect to the SuggestBot database')
            return(False)

        (dbconn, dbcursor) = myDb.getConnection()

        # Check if a job is already running
        dbcursor.execute(checkStatusTableQuery, {'lang': self._lang})
        row = dbcursor.fetchone()
        dbcursor.fetchall() # flush cursor

        if ord(row['daily_running']):
            logging.warning("SuggestBot is already posting to users on {0}wiki, exiting!".format(self._lang))
            return(True)

        ## Instantiating bot so we can get suggestions
        sbot = suggestbot.SuggestBot(lang=self._lang)
        
        # Update the status of busyness to pretty busy...
        dbcursor.execute(updateStatusTableQuery, {'status': 1,
                                                  'lang': self._lang})
        dbconn.commit()

        # Figure out how long since we last ran.
        dbcursor.execute(getLastRecQuery, {'lang': self._lang})
        row = dbcursor.fetchone()
        dbcursor.fetchall() # flush cursor
        # Check that we got a row and that it's something...
        if row and row['last_rec']:
            timeSinceLastRun = now - row['last_rec']
            # If tSLR.days < 0, something's not right:
            if timeSinceLastRun.days < 0:
                logging.error("Time since last set of recs posted is negative, aborting!")
                return(False)
        else:
            # We might see this branch the first time we're running...
            timeSinceLastRun = timedelta(0)

        # If it's more than one day since we last ran, we don't look
        # into the future, instead we'll just catch up.  Otherwise,
        # we look half the distance into the future.
        # FIXME: this will bump people if one run runs a little long,
        # and the user is at the end of the next run.  We should instead
        # store the start and end-time of the last run somewhere, perhaps
        # actually have a log, and then use the last start-time from the log.
        lookaheadTime = 0
        if timeSinceLastRun.days == 0:
            lookaheadTime = timeSinceLastRun.seconds / 2

        logging.info("looking {0} seconds ahead for due recs.".format(lookaheadTime))

        # Store users who should get recs in this list:
        userQueue = list()

        dbcursor.execute(getRegularsQuery, {'lang': self._lang})
        done = False
        while not done:
            row = dbcursor.fetchone()
            if not row:
                done = True
                continue

            # The values of the row we currently use:
            lastRec = row['last_rec']
            period = row['period']
            username = row['username']
            pagetitle = row['page_title']
            design = row['design']

            recTemplate = config.templates[self._lang]['regulars']
            # If the user has chosen to use a different design from the default,
            # check if we have a template and possibly use that.
            if design:
                try:
                    recTemplate = config.templates[self._lang][design]
                except KeyError:
                    pass

            # If the user wants recs replaced, do so.
            replace = False
            if ord(row['replace_recs']):
                replace = True

            # FIXME: better to use the Subscriber object now, since it is
            # here and has slots for all the variables. Makes more sense.

            # if lastRec is None (NULL), they didn't receive any recs earlier,
            # which means it's definitely time to post.
            if not lastRec:
                print('lastRec is None/False, adding user')
                userQueue.append({'username': username,
                                  'page': pagetitle,
                                  'replace': replace,
                                  'template': recTemplate,
                                  })
                continue

            # Use last rec and period to check if it's time to post or not
            if period == 0:
                # Add 28 days to last rec.  This is stricly not always
                # "once a month", but it's a lot easier than trying to
                # handle overflow when the last recommendation occurred near
                # the end of the previous month (e.g. Jan to Feb).  It also
                # has the added feature that recommendations usually happen on
                # the same day of the week.
                modLastRec = lastRec + timedelta(days=28)
            else:
                # add 'period' days to last rec
                modLastRec = lastRec + timedelta(days=period)

            # subtract the modified last rec from today
            timelapse = now - modLastRec

            # It's time to post recommendations if we're past this user's due
            # date, or if it's less than lookaheadTime seconds ahead.
            # This makes sure that we don't always bump users to the
            # next day's recommendations, which would otherwise mean
            # we'd consistently post a day late.
            if timelapse.days >= 0 \
                    or (timelapse.days == -1 and (86400 - timelapse.seconds) < lookaheadTime):
                # add {'username':username, 'page':page_title} to list
                userQueue.append({'username': username,
                                  'page': pagetitle,
                                  'replace': replace,
                                  'template': recTemplate,
                                  })
        logging.info("Checked subscribers, found {n} users to post to.".format(
            n=len(userQueue)))

        # (We shuffle the user list so it doesn't necessarily get processed in
        # alphabetical order, IIRC the results of this SELECT is in sorted
        # order because we use a primary key)
        if len(userQueue) > 0:
            shuffle(userQueue)

        # for each user on said list...
        for user in userQueue:
            # update database to processing
            dbcursor.execute(setStatusQuery, {'status': 'processing',
                                              'lang': self._lang,
                                              'username': user['username']})
            dbconn.commit()

            logging.info("now getting recs for User:{username}".format(
                username=user['username']))

            # Get recommendations and post...
            # Design and template is passed along based on what we looked
            # up earlier.
            success = sbot.recommend(username=user['username'],
                                     userGroup='suggest',
                                     filterMinor=True,
                                     filterReverts=True,
                                     page=user['page'],
                                     recTemplate=user['template'],
                                     replace=user['replace'])
            if success:
                # update database to idle, and update last_rec
                dbcursor.execute(setStatusQuery, {'status': 'idle',
                                                  'lang': self._lang,
                                                  'username': user['username']})

                # we don't update the rec time on a test run...
                if not config.testrun:
                    # Note: we call utcnow() to store the closest last recommendation
                    # time in the database.  If some slack is needed with regards to
                    # posting time, we can instead alter the scheduling.
                    dbcursor.execute(setLastrecQuery, {'rectime': datetime.utcnow(),
                                                       'lang': self._lang,
                                                       'username': user['username']})
                    # update count of number of recommendations for this user
                    dbcursor.execute(incRecCountQuery, {'lang': self._lang,
                                                        'user': user['username']})
                    
                dbconn.commit()
                logging.info("Posted recs to User:{username}".format(
                    username=user['username']))

        # Update the status of busyness to pretty unbusy...
        dbcursor.execute(updateStatusTableQuery, {'status': 0,
                                                  'lang': self._lang})
        dbconn.commit()

        # disconnect from database
        myDb.disconnect()

        # ok, done
        return
