#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Library for recommeding collaborators.

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

import MySQLdb

from suggestbot import config
from suggestbot import db

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
    def __init__(self, lang='en', nrecs=100, threshold=3, backoff=0,
                 min_threshold=1, assoc_threshold=0, exp_threshold=18):
        '''
        Instantiate an object for recommending collaborators.

        :param lang: default language we are recommeding for
        :type lang: str

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
        self.nrecs = nrecs
        self.backoff = backoff
        self.thresh = threshold
        self.min_thresh = min_threshold
        self.assoc_thresh = assoc_threshold
        self.exp_thresh = exp_threshold

        # Database connection and cursor
        self.dbconn = None
        self.dbcursor = None
        
    def recommend(self, contribs, username, lang, nrecs = 100, threshold = 3, backoff = 0, test = 'jaccard'):

        '''
        Find `nrecs` number of neighbours for a given user based on
        the overlap between their contributions.

        :param contribs: The user's contributions
        :type contribs: list

        :param username: Username of the user we're recommending for
        :type username: str

        :param lang: Language code of the Wikipedia we're working on
        :type lang: str

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
        self.lang = lang
        self.nrecs = nrecs
        self.thresh  = threshold
        self.backoff = backoff
        self.test = test

        # SQL queries are defined here so as to not perform the string
        # formatting multiple times.
        self.get_articles_by_user_query = """SELECT rev_title
             FROM {revision_table}
             WHERE rev_user = %(username)s""".format(revision_table=config.revision_table[lang])

        # Query to get edited articles for a user who is above the threshold,
        # we then disregard minor edits and reverts.
        self.get_articles_by_expert_user_query = """SELECT rev_title
             FROM {revision_table}
             WHERE rev_user = %(username)s
             AND rev_is_minor = 0
             AND rev_comment_is_revert = 0""".format(revision_table=config.revision_table[lang])

        # Query to get the number of edits a user has made (in our dataset)
        self.get_edit_count_query = """SELECT count(*) AS numedits
             FROM {revision_table}
             WHERE rev_user = %(username)s""".format(revision_table=config.revision_table[lang])

        logging.info("Got request for user {0}:{1} to recommend based on {2} edits!".format(lang, username, len(contribs)))

        # Recommendations we'll be returning
        recs = []

        database = db.SuggestBotDatabase()
        if not database.connect():
            logging.error("Failed to connect to SuggestBot database")
            return(recs)

        (self.dbconn, self.dbcursor) = database.getConnection()

        # Turn contributions into a set, as we'll only use it that way
        contribs = set(contribs)

        # Get some recs.
        recs = self.get_recs_at_coedit_threshold(username, contribs, self.test)

        # If we're allowed to back off on the coedit threshold and don't have enough
        # recs, ease off on the threshold and try again.
        needed = nrecs - len(recs) > 0
        while backoff and self.thresh >= self.min_thresh and needed:
            self.thresh -= 1
            logging.info('Co-edit threshold is now {0}'.format(self.thresh))
            recs = self.get_recs_at_coedit_threshold(username, contribs, self.test)
            needed = nrecs - len(recs)

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
        
        # NOTE: because rev_user and rev_title currently are VARCHAR(255) and UTF-8,
        # they're assumed to consume ~765 bytes in memory, and therefore MySQL chooses
        # to use a temp file table rather than a temp memory table.  Because the queries
        # to get users by article are each only run once per article a user edited,
        # we can live with the temp file being created to move less data.
        
        # First query gets users who made non-minor, non-reverting edits
        # to this article.  These are _always_ potential neighbours.
        get_users_by_article_query = """SELECT DISTINCT rev_user
        FROM {revision_table}
        WHERE rev_title = %(title)s
        AND rev_is_minor = 0
        AND rev_comment_is_revert = 0""".format(revision_table=config.revision_table[self.lang])

        # Second query gets the other users (either minor or reverting),
        # these are only interesting if they're below the threshold for total
        # number of edits, as they otherwise know what they were doing.
        get_minor_users_by_article_query = """SELECT DISTINCT rev_user
        FROM {revision_table}
        WHERE rev_title = %(title)s
        AND (rev_is_minor = 1
        OR rev_comment_is_revert = 1)""".format(revision_table=config.revision_table[self.lang])
        
        # How many different users have coedited a given item with something
        # in the basket
        coedit_count = {}

        # Found co-editors, and recommendations we'll return
        coeditors = {}
        recs = []

        logging.info("recommending for user '{0}'".format(username))

        user = ""
        num_edits = 0
        page_title = ""
        
        for item in contribs:
            # For each article the user has edited, find other editors.
            logging.info('checking article: {0}'.format(item))
            
            other_editors = {}
            
            # First we get major stakeholders in the article (non-minor/non-reverting edits)
            try:
                self.dbcursor.execute(get_users_by_article_query,
                               {'title': item})
            except MySQLdb.Error as e:
                logging.error("unable to execute query to get users by article")
                logging.error("Error {0}: {1}".format(e.args[0], e.args[1]))
                return(recs)

            for row in self.dbcursor:
                user = row['rev_user']
                if user == username: # user can't be their own neighbour
                    continue
                if user in coeditors:
                    continue

                other_editors[user] = 1

            logging.info('found {0} major stakeholders'.format(len(other_editors)))
                
            # Then we check minor edits and reverts, and keep those users who are
            # not in the top 10% of users (see `self.exp_thresh`).

            # Users we've seen (so we don't re-run SQL queries all the time)...
            seen_minors = {}
            try:
                self.dbcursor.execute(get_minor_users_by_article_query,
                               {'title': item})
            except MySQLdb.Error as e:
                logging.error("unable to execute query to get users by article")
                logging.error("Error {0}: {1}".format(e.args[0], e.args[1]))
                return(recs)

            for row in self.dbcursor:
                user = row['rev_user']
                if user == username:
                    logging.info('user cannot be their own neighbour, skipping')
                    continue
                if user in coeditors:
                    logging.info('already seen this user')
                if user in other_editors:
                    logging.info('user already major stakeholder')
                    continue

                seen_minors[user] = 1

            logging.info('found {0} minor editors, checking edit counts'.format(
                len(seen_minors)))
                
            for user in seen_minors.keys():
                try:
                    self.dbcursor.execute(self.get_edit_count_query,
                                   {'username': user})
                except MySQLdb.Error as e:
                    logging.error("unable to execute query to get editcount for user")
                    logging.error("Error {0}: {1}".format(e.args[0], e.args[1]))
                    continue

                for row in self.dbcursor:
                    if row['numedits'] < self.exp_thresh:
                        other_editors[user] = 1

            logging.info('found {0} other editors in total'.format(len(other_editors)))

            # Now we have all relevant stakeholders in the article, and can
            # compute the appropriate association.
            for user in other_editors:
                user_obj = RecUser(user, 0, 0, 0)
                
                # Add user to coeditors so we'll skip this user later
                coeditors[user] = user_obj

                (assoc, shared, cosine) = self.user_association(user, contribs)
                logging.info('user={0}, assoc={1}, shared={2}, cosine={3}'.format(
                    user, assoc, shared, cosine))
                if assoc < self.assoc_thresh:
                    continue

                user_obj.assoc = assoc
                user_obj.shared = shared
                user_obj.cosine = cosine

        logging.info("Found {0} pre-neighbours".format(len(coeditors)))

        # Find nhood of top k users
        k = 250  # Larger nhood for more recs, hopefully

        # Return results sorted according to "test" parameter
        if test == 'jaccard':
                recs = sorted(coeditors.values(),
                      key=operator.attrgetter('assoc'),
                      reverse=True)[:k]
        elif test == 'cosine':
                recs = sorted(coeditors.values(),
                      key=operator.attrgetter('cosine'),
                      reverse=True)[:k]
        elif test == 'coedit':
                recs = sorted(coeditors.values(),
                      key=operator.attrgetter('shared'),
                      reverse=True)[:k]
        return recs

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

        # Find common articles.  We first find the user's editcount, to check if this user
        # is in the top 10% of users or not.  If they are (as defined by self.exp_thresh)
        # we'll only use non-minor, non-reverting article edits for comparison.
        # Otherwise, we use all articles the user edited.
        user_editcount = 0
        self.dbcursor.execute(self.get_edit_count_query,
                              {'username': user})
        for row in self.dbcursor:
            user_editcount = row['numedits']

        # Grab the users edits...
        if user_editcount >= self.exp_thresh:
            self.dbcursor.execute(self.get_articles_by_expert_user_query,
                                  {'username': user})
        else:
            self.dbcursor.execute(self.get_articles_by_user_query,
                                  {'username': user})
        for row in self.dbcursor:
            user_edits.add(row['rev_title'])

        # Calculate association using the Jaccard Coefficient and Cosine Similarity test
        shared = len(user_edits & basket)
        union = len(user_edits | basket)
        assoc = float(shared) / union
        cosine = float(shared) / (math.sqrt(len(user_edits)) * math.sqrt(len(basket)))
        return(assoc, shared, cosine)
