#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Library for recommending collaborators.

Copyright (C) 2015 SuggestBot Dev Group

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
'''

import operator
import logging
import math
import re

from datetime import datetime

## Import our Tool Labs DB connector
import db

## Catching MySQL errors
import MySQLdb

## Import from MediaWiki to check for reverts
from mw.lib import reverts

## defaultdict used to track edit counts
from collections import defaultdict

class RecUser:
    def __init__(self, username, assoc, shared, cosine):
        '''
        Instantiate a user object.
    
        :param username: Name of the user
        :type username: str

        :param assoc: Association between this user and the user we're
                      recommending for.
        :type assoc: float

        :param shared: Number of shared articles edited
        :type shared: int

        :param cosine: Cosine similarity between this user and the user
                      we're recomending for.
        :type cosine: float
        '''

        self.username = username
        self.assoc = assoc
        self.shared = shared
        self.cosine = cosine

class CollabRecommender:
    def __init__(self, lang='en', revtable='revision_userindex',
                 nrecs=100, threshold=3, backoff=0,
                 min_threshold=1, assoc_threshold=0.0001, exp_threshold=18):
        '''
        Instantiate an object for recommending collaborators.

        :param lang: default language we are recommeding for
        :type lang: str

        :param revtable: name of the table which holds revision data.
                         Because we query using usernames, the default
                         should be "revision_userindex" to use indexes properly.
        :type revtable: str

        :param nrecs: default number of recommended users
        :type nrecs: int

        :param threshold: starting threshold for finding neighbours
        :type threshold: int

        :param backoff: do we back off the neighbour threshold?
        :type backoff: int

        :param min_threshold: minimum threshold for labelling as neighbour
        :type min_threshold: int

        :param assoc_threshold: threshold for user similarity
        :type assoc_threshold: float

        :param filter_threshold: threshold for labelling user as experienced
        :type filter_threshold: int
        '''
        
        self.lang = lang
        self.revtable= revtable
        self.nrecs = nrecs
        self.backoff = backoff
        self.thresh = threshold
        self.min_thresh = min_threshold
        self.assoc_thresh = assoc_threshold
        self.exp_thresh = exp_threshold

        # Database connection and cursor
        self.dbconn = None
        self.dbcursor = None

#---------------------------------------------------------------------------------------------------------------------
        
    def recommend(self, contribs, username, lang, cutoff,
                  nrecs=100, threshold=3, backoff=0, test = 'jaccard'):

        '''
        Find `nrecs` number of neighbours for a given user based on
        the overlap between their contributions.

        :param contribs: The user's contributions
        :type contribs: list

        :param username: Username of the user we're recommending for
        :type username: str

        :param lang: Language code of the Wikipedia we're working on
        :type lang: str

        :param cutoff: Date and time from when to start looking for revisions
        :type cutoff: datetime.datetime

        :param nrecs: Number of recommendations we seek
        :type nrecs: int

        :param threshold: Number of articles in common to be determined a neighbour
        :type threshold: int

        :param backoff: Do we apply a backoff strategy on the threshold?
        :type backoff: int

        :param test: Name of correlation test to return results from
        :type param: str
        '''

        # Override default variables with supplied parameters
        self.cutoff = cutoff
        self.lang = lang
        self.nrecs = nrecs
        self.thresh  = threshold
        self.backoff = backoff
        self.test = test

        # SQL queries are defined here so as to not perform the string
        # formatting multiple times.
        self.get_articles_by_user_query = """SELECT DISTINCT page_title
             FROM {revision_table} r
             JOIN page p
             ON r.rev_page=p.page_id
             WHERE rev_user_text = %(username)s
             AND rev_timestamp >= %(timestamp)s""".format(revision_table=self.revtable)

        # Query to get edited articles for a user who is above the threshold,
        # we then disregard minor edits and reverts.
        # self.get_articles_by_expert_user_query = """SELECT p.page_title,
        #      p.page_id, r.rev_id, r.rev_sha1, r.rev_timestamp
        #      FROM {revision_table} r
        #      JOIN page p
        #      ON r.rev_page=p.page_id
        #      WHERE rev_user_text = %(username)s
        #      AND rev_timestamp >= %(timestamp)s
        #      AND rev_minor_edit=0""".format(revision_table=self.revtable)
        self.get_articles_by_expert_user_query = """SELECT DISTINCT p.page_title
             FROM {revision_table} r
             JOIN page p
             ON r.rev_page=p.page_id
             WHERE rev_user_text = %(username)s
             AND rev_timestamp >= %(timestamp)s
             AND rev_minor_edit=0""".format(revision_table=self.revtable)

        # Query to get the number of edits a user has made (in our dataset)
        # might want to limit this to namespace 0 (articles)
        self.get_edit_count_query = """SELECT count(r.rev_id) AS numedits
             FROM {revision_table} r
             JOIN page p
             ON r.rev_page=p.page_id
             WHERE r.rev_user_text = %(username)s
             AND r.rev_timestamp >= %(timestamp)s
             AND p.page_namespace=0""".format(revision_table=self.revtable)

        logging.info(
            "Got request for user {0}:{1} to recommend based on {2} edits!".format(
                lang, username, len(contribs)))

        # Recommendations we'll be returning
        recs = []

        # Mapping usernames to number of edits to not repeat those SQL queries
        self.nedit_map = {}

        (self.dbconn, self.dbcursor) = db.connect(dbhost='c3.labsdb')
        if not self.dbconn:
            logging.error("Failed to connect to database")
            return(recs)

        # Turn contributions into a set, as we'll only use it that way
        contribs = set(contribs)

        # Get some recs.
        recs = self.get_recs_at_coedit_threshold(username, contribs, self.test)

        db.disconnect(self.dbconn, self.dbcursor)
        # Return truncated to nrecs, switched from list of objects to list of dicts
        return([{'item': rec.username, 'value': rec.assoc} for rec in recs[:nrecs]])

    def get_recs_at_coedit_threshold(self, username, contribs, test):
        '''
        Get recommendations of other users based on a set of contributions.

        :param username: User we are recommending for
        :type username: str
        
        :param contribs: Contributions we're recommending based on
        :type contribs: set

        :param test: Name of the test to return results from
        :type test: str
        '''
        
        # This query gets users who made edits to the article. Reverts, IPs, bot names, and minor edits for experienced users
        # will be filtered out of the resulting set.
        get_users_by_article_query = """SELECT r.rev_user, r.rev_user_text,
            r.rev_timestamp, r.rev_minor_edit, r.rev_id, r.rev_sha1,
            IFNULL(ug.ug_group, 'no') AS is_bot
        FROM page p
        JOIN revision_userindex r
        ON p.page_id=r.rev_page
        LEFT JOIN (SELECT * FROM user_groups WHERE ug_group='bot') ug
        ON r.rev_user=ug.ug_user
        WHERE p.page_namespace=0
        AND p.page_title=%(title)s
        AND r.rev_timestamp >= %(timestamp)s
        ORDER BY r.rev_timestamp ASC"""

        # This query fetches the hashes and IDs of the fifteen edits prior
        # to the examined tate range to identify reverts..
        get_revision_history_query = """SELECT r.rev_sha1,
            r.rev_id, r.rev_timestamp, r.rev_user_text
        FROM revision r
        JOIN page p
        ON r.rev_page=p.page_id
        WHERE p.page_namespace=0
        AND p.page_title=%(title)s
        AND r.rev_timestamp < %(timestamp)s
        ORDER BY r.rev_timestamp DESC
        LIMIT %(k)s"""

        # Found co-editors, and recommendations we'll return
        coeditor_objs = {}
        recs = []

        logging.info("recommending for user '{0}'".format(username))

        user = ""
        num_edits = 0
        page_title = ""
        
        user_acc_ct = 0
        
        for item in contribs:
            # For each article the user has edited, find other editors.
            #logging.info('checking article: {0}'.format(item))
            
            # Translate " " to "_"
            item = item.replace(" ", "_")

            # Load up the revert detector with the 15 edits prior to
            # the first one we'll process.
            detector = reverts.Detector()
            try:
                self.dbcursor.execute(get_revision_history_query,
                                      {'title': item,
                                       'timestamp': self.cutoff.strftime('%Y%m%d%H%M%S'),
                                       'k': 15})
            except MySQLdb.Error as e:
                logging.error("unable to execute query to get users by article")
                logging.error("Error {0}: {1}".format(e.args[0], e.args[1]))
                return(recs)

            for row in self.dbcursor.fetchall():
                try:
                    sha1 = row['rev_sha1'].decode()
                    rev_user = row['rev_user_text'].decode()
                    rev_time = datetime.strptime(row['rev_timestamp'].decode(),
                                                 '%Y%m%d%H%M%S')
                    detector.process(sha1,
                                     {'rev_id': row['rev_id'],
                                      'rev_user': rev_user,
                                      'rev_timestamp': rev_time})
                except AttributeError:
                    continue
            
            # Get all contributors to item; Remove bots and reverts

            # editors maps usernames to a list containing a contribution count
            # and a boolean indicating whether the user should be included
            # in final results
            editors = defaultdict(lambda: {'numedits': 0, 'is_major': False})
            edits = {}
            try:
                self.dbcursor.execute(get_users_by_article_query,
                                      {'title': item,
                                       'timestamp': self.cutoff.strftime('%Y%m%d%H%M%S')})
            except MySQLdb.Error as e:
                logging.error("unable to execute query to get users by article")
                logging.error("Error {0}: {1}".format(e.args[0], e.args[1]))
                return(recs)

            for row in self.dbcursor.fetchall():
                try:
                    rev_username = row['rev_user_text'].decode()
                    rev_time = datetime.strptime(row['rev_timestamp'].decode(),
                                                 '%Y%m%d%H%M%S')
                    rev_sha1 = row['rev_sha1'].decode()
                    rev_is_bot = row['is_bot'].decode()
                except AttributeError:
                    # Not a valid revision (e.g. deleted), ignore it...
                    continue

                # Increment defaultdict contribution count if the editor
                # is registered, not a bot, and not the user we're suggesting to
                if self.valid_editor(rev_username, row['rev_user'],
                                     rev_is_bot, username):
                    editors[rev_username]['numedits'] += 1

                    # This flag in the defaultdict is set to True if the user makes
                    # a non-minor edit now, or later if their edit count is below
                    # the threshold
                    if not row['rev_minor_edit']:
                        editors[rev_username]['is_major'] = True

                # This is checked even if the user failed the validity checks above,
                # ensuring that reverts by bots are caught as well
                revert = detector.process(rev_sha1,
                                          {'rev_id': row['rev_id'],
                                           'rev_user': rev_username,
                                           'rev_timestamp': rev_time})
                if not revert:
                    continue

                # If the revert was done by a bot, or it was done in less
                # than 5 minutes, decrement all intermediate editors.
                timediff = revert.reverting['rev_timestamp'] \
                           - revert.reverteds[0]['rev_timestamp']
                if (rev_is_bot == 'bot' or re.search("bot(\b|$)", rev_username, re.I) is not None) or timediff.seconds <= 300:
                    for intermediate in revert.reverteds:
                        editors[intermediate['rev_user']]['numedits'] -= 1
                    if rev_is_bot == 'no' and re.search("bot(\b|$)", rev_username, re.I) is None:
                        editors[rev_username]['numedits'] -= 1

            #print('found {0} candidate users'.format(len(editors)))

            for candidate_user, candata in editors.items():
                # Already processed this user?
                if candidate_user in coeditor_objs:
                    continue

                # No edits means they were reverted
                if candata['numedits'] <= 0:
                    continue

                # Check total number of edits if the user's edits on this
                # article have all been minor
                if not candata['is_major']:
                    if self.get_editcount(candidate_user) < self.exp_thresh:
                        # Set flag to True if user is below edit count threshold,
                       candata['is_major'] = True

                if not candata['is_major']:
                    logging.info("{0} made only minor edits, but is above the edit threshold".format(candidate_user))
                    continue

                #print('Calculating association for User:{0}'.format(candidate_user))

                user_obj = RecUser(candidate_user, 0, 0, 0)
                
                # Add user to coeditor_objs so we'll skip this user later
                coeditor_objs[candidate_user] = user_obj

                (assoc, shared, cosine) = self.user_association(candidate_user,
                                                                contribs)
                user_acc_ct += 1
                logging.info('user={0}, assoc={1}, shared={2}, cosine={3}'.format(
                    candidate_user, assoc, shared, cosine))
                if assoc < self.assoc_thresh:
                    continue

                user_obj.assoc = assoc
                user_obj.shared = shared
                user_obj.cosine = cosine

        #logging.info("Found {0} pre-neighbours".format(len(coeditor_objs)))
        print("Number of applicable users found: {0}; Number of user acc calls: {1}".format(len(coeditor_objs), user_acc_ct))

        # Find nhood of top k users
        k = 250  # Larger nhood for more recs, hopefully

        # Return results sorted according to "test" parameter
        if test == 'jaccard':
            recs = sorted(coeditor_objs.values(),
                          key=operator.attrgetter('assoc'),
                          reverse=True)[:k]
        elif test == 'cosine':
            recs = sorted(coeditor_objs.values(),
                          key=operator.attrgetter('cosine'),
                          reverse=True)[:k]
        elif test == 'coedit':
            recs = sorted(coeditor_objs.values(),
                          key=operator.attrgetter('shared'),
                          reverse=True)[:k]
        return recs

    def valid_editor(self, cand_name, cand_id, is_bot, username):
        '''
        Test if a candidate user is a valid editor to process.

        :param cand_name: Username of the candidate editor
        :type cand_name: str

        :param cand_id: User ID of the candidate editor
        :type cand_id: int

        :param cand_bot: User group set to 'bot' if the user is in the bot group
        :type cand_bot: str

        :param username: Username of the editor we are suggesting to
        :type username: str
        '''
        try:
            if cand_name == username:
                #logging.info('user cannot be their own neighbour, skipping')
                return(False)
            if not cand_id:
                # Unregistered editor, or a deleted revision w/no user ID
                return(False)
            if is_bot == 'bot':
                #print("{0} is a bot by flag".format(cand_name))
                return(False)
            if re.search("bot(\b|$)", cand_name, re.I) is not None:
                print("{0} is a bot by name".format(cand_name))
                return(False)
        except AttributeError:
            return(False)
            
        return(True)

    def get_editcount(self, username, **kwargs):
        '''
        Get the edit count of the given user
        
        :param username: Name of the user
        :type username: str
        
        :param default: Value to return if user has no edits
        :type default: mixed
        '''
        nedits = kwargs.get('default', self.exp_thresh)

        try:
            return(self.nedit_map[username])
        except KeyError:
            try:
                self.dbcursor.execute(self.get_edit_count_query,
                                      {'username': username,
                                       'timestamp': self.cutoff.strftime('%Y%m%d%H%M%S')})
                for row in self.dbcursor.fetchall():
                    nedits = row['numedits']
                    self.nedit_map[username] = nedits
            except MySQLdb.Error as e:
                logging.error("unable to execute query to get editcount for user")
                logging.error("Error {0}: {1}".format(e.args[0], e.args[1]))
        
        return nedits

    def is_revert(self, page_id, sha1, timestamp, radius=15):
        '''
        Check if within `radius` number of revisions to the given page id
        prior to the given timestamp, any revision has the same checksum.

        :param page_id: page we're checking
        :type page_id: long

        :param sha1: SHA1 checksum of the revision we're checking
        :type sha1: str

        :param timestamp: timestamp of the revision we're checking
        :type timestamp: str
        '''
        get_checksums_query = """SELECT rev_sha1
        FROM revision
        WHERE rev_page=%(pageid)s
        AND rev_timestamp < %(timestamp)s
        ORDER BY rev_timestamp DESC
        LIMIT %(k)s"""

        checksums = set()
        try:
            self.dbcursor.execute(get_checksums_query,
                                  {'pageid': page_id,
                                   'timestamp': timestamp,
                                   'k': radius})
            for row in self.dbcursor.fetchall():
                checksums.add(row['rev_sha1'].decode())
        except MySQLdb.Error as e:
            logging.warning('Unable to execute query to get revision checksums')
            return(False)

        return(sha1 in checksums)

    def user_association(self, user, basket):
        '''
        Calculate the association between a given user and a basket
        of edits.  A user has to have at least self.exp_thresh edits
        to be labelled experienced, thus discarding minor edits.

        :param user: The user we are looking up contributions for.
        :type user: str

        :param basket: The basket of contributions we are comparing user to.
        :type basket: set
        '''

        assoc = 0
        shared = 0
        user_edits = set()

        # Find common articles.  We first find the user's editcount, to check if this
        # user is in the top 10% of users or not.  If they are (as defined by
        # self.exp_thresh) we'll only use non-minor, non-reverting article edits
        # for comparison.  Otherwise, we use all articles the user edited.
        if self.get_editcount(user) < self.exp_thresh: 
            self.dbcursor.execute(self.get_articles_by_user_query,
                                  {'username': user,
                                   'timestamp': self.cutoff.strftime('%Y%m%d%H%M%S')})
        else:
            # Note: Removing reverts would be neat, but requires a lot of
            # processing time, unless we can find a shortcut.
            self.dbcursor.execute(self.get_articles_by_expert_user_query,
                                  {'username': user,
                                   'timestamp': self.cutoff.strftime('%Y%m%d%H%M%S')})
        for row in self.dbcursor.fetchall():
            user_edits.add(row['page_title'].decode())

        #print('Total edits by {0}: {1}'.format(user, len(user_edits)))
        #print('Size of target basket: {0}'.format(len(basket)))
        # Calculate association using the Jaccard Coefficient and Cosine Similarity test
        if len(user_edits) > 0:
            shared = len(user_edits & basket)
            union = len(user_edits | basket)
            assoc = float(shared) / union
            cosine = float(shared) / (math.sqrt(len(user_edits)) * math.sqrt(len(basket)))
            return(assoc, shared, cosine)
        return(0, 0, 0)
