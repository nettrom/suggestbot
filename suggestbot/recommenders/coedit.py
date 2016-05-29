#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Library for recommending articles based on co-editing the same articles.

Copyright (C) 2016 SuggestBot Dev Group

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

import sys
import logging

from suggestbot import config
from suggestbot import db

from operator import itemgetter

class Recommender:
    def __init__(self):
        # Easier to have these SQL queries as global variables,
        # rather than pass them around.  Does make for possible
        # errors if they're not prepared properly before execution, though.
        self.get_articles_by_user_query = ''
        self.get_articles_by_expert_user_query = ''
        self.get_editcount_query = ''

        self.dbconn = None
        self.dbcursor = None
        
    def recommend(self, username, lang, user_edits,
                  nrecs=None, threshold=None,
                  backoff=None, min_threshold=None):
        '''
        Try to recommend `nrecs` articles to `username` in `lang`
        Wikipedia, using the given `threshold` and `backoff` if
        the threshold isn't met.

        :param username: Name of the user we're recommending to
        :param lang: Language code of the Wikipedia we're on
        :param user_edit: Dictionary of the user's edited articles
                          mapping page titles to interest scores
        :param nrecs: Number of recommendations to return
        :type nrecs: int
        :param threshold: Threshold for considering a user as a neighbour
        :type threshold: int
        :param backoff: Are we allowed to reduce the co-edit threshold?
        :type backoff: bool
        :param min_threshold: Minimum association required to be a candidate
        :type min_threshold: float
        '''

        params = {
            'backoff': config.coedit_backoff,
            'nrecs' : config.nrecs_per_server,
            'threshold' : config.coedit_threshold,
            'min-threshold' : config.coedit_min_threshold,
            'association-threshold': config.coedit_assoc_threshold,
            'filter-threshold' : config.coedit_filter_threshold,
        }

        if backoff is not None and backoff != params['backoff']:
            params['backoff'] = backoff

        if nrecs:
            params['nrecs'] = nrecs

        if threshold:
            params['threshold'] = threshold

        if min_threshold:
            param['min-threshold'] = min_threshold

        sys.stderr.write("Got request to recommend {} articles to {}:User:{} based on {} edited articles\n".format(
            params['nrecs'], lang, username, len(user_edits)))

        # Get some recs.
        recs = self.get_recs_at_coedit_threshold(lang, username,
                                                 user_edits, params)

        # sys.stderr.write("Got {} recs back\n".format(len(recs)))
        
        # If we're allowed to back off on the coedit threshold and don't
        # have enough recs, ease off on the threshold and try again.
        while params['backoff'] \
              and (params['threshold'] > params['min-threshold']) \
              and (len(recs) < params['nrecs']):
            # sys.stderr.write("Backing off threshold...\n")
            params['threshold'] -= 1
            recs = self.get_recs_at_coedit_threshold(lang, username,
                                                     user_edits, params)

        sys.stderr.write("Done recommeding for {}:User:{}, returning {} recommendations\n".format(lang, username, len(recs)))

        # OK, done
        return(recs[:params['nrecs']])

    def get_recs_at_coedit_threshold(self, lang, username, contribs, params):
        # NOTE: because rev_user and rev_title currently are VARCHAR(255) and
        # UTF-8, they're assumed to consume ~765 bytes in memory, and
        # therefore MySQL chooses to use a temp file table rather than
        # a temp memory table.  Because the queries to get users by article
        # are each only run once per article a user edited, we can live with
        # the temp file being created to move less data.

        # First query gets users who made non-minor, non-reverting edits
        # to this article.  These are _always_ potential neighbours.
        get_users_by_article_query = """
            SELECT DISTINCT rev_user 
            FROM {}
            WHERE rev_title=%(title)s
            AND rev_is_minor=0
            AND rev_comment_is_revert=0""".format(
                config.revision_table[lang])

        # Second query gets the other users (either minor or reverting),
        # these are only interesting if they're below the threshold for total
        # number of edits, as they otherwise know what they were doing.
        get_minor_users_by_article_query = """
            SELECT DISTINCT rev_user
            FROM {}
            WHERE rev_title=%(title)s
	    AND (rev_is_minor=1
                 OR rev_comment_is_revert=1)""".format(
                     config.revision_table[lang])

        # Query to get edited articles for a given user if the user is
        # below the edit threshold.
        self.get_articles_by_user_query = """
            SELECT rev_title
	    FROM {}
	    WHERE rev_user=%(username)s""".format(
                config.revision_table[lang])
    
        # Query to get edited articles for a user who is above the threshold,
        # we then disregard minor edits and reverts.
        self.get_articles_by_expert_user_query = """
            SELECT rev_title
	    FROM {}
            WHERE rev_user=%(username)s
	    AND rev_is_minor=0
	    AND rev_comment_is_revert=0""".format(
                config.revision_table[lang])
    
        # Query to get the number of edits a user has made (in our dataset)
        self.get_editcount_query = """
            SELECT count(*) AS num_edits
	    FROM {}
	    WHERE rev_user=%(username)s""".format(
                config.revision_table[lang])

        # Return this many recs
        N = params['nrecs']

        # Exclude items edited by this user.
        user_for_query = username

        # Neighbours must have at least this much association.
        association_threshold = params['association-threshold']

        # Recommendations we found
        recs = []
        
        sbdb = db.SuggestBotDatabase()
        if not sbdb.connect():
            logging.error("Unable to connect to the SuggestBot database")
            return(recs)

        (self.dbconn, self.dbcursor) = sbdb.getConnection()
        
        rec_map = {}

        # How many different users have coedited a given item with something
        # in the basket
        coedit_count = {}

        # Find users who rated the given items
        coeditor_map = {}
        user_assoc = {}
        user_shared = {}

        for item in contribs:
	    # For each article the user has edited, find other editors.
            other_editors = {}
            # sys.stderr.write("Looking for contributors to {}\n".format(item))

	    # First we get major stakeholders in the article
            # (non-minor/non-reverting edits)
            self.dbcursor.execute(get_users_by_article_query,
                             {'title': item})
            for row in self.dbcursor:
                # Only compute each thing once
                user = row['rev_user']
                if user in coeditor_map:
                    continue
                
                # User can't be their own neighbour
                if user == user_for_query:
                    continue
                
                # OK, add user to hash
                other_editors[user] = 1
                
	    # Then we check minor edits and reverts, and keep those users
            # who are not in the top 10% of users (see param filter-threshold
            # defined earlier).

	    # Users we've seen (so we don't re-run SQL queries all the time)...
            seen_minors = {}
            self.dbcursor.execute(get_minor_users_by_article_query,
                             {'title' : item})

            # Note: using fetchall() to allow us to execute further queries
            for row in self.dbcursor.fetchall():
                user = row['rev_user']
                
	        # If user has already been seen, move along...
                if user in coeditor_map:
                    continue

                # If user is a major stakeholder, move along...
                if user in other_editors:
                    continue

                # If we tested this user already...
                if user in seen_minors:
                    continue

                # User can't be their own neighbour
                if user == user_for_query:
                    continue

                # Passed tests, add as a minor user
                seen_minors[user] = 1

	        # Is user above threshold?  If so, skip...
                self.dbcursor.execute(self.get_editcount_query,
                                      {'username': user})
                nedit_row = self.dbcursor.fetchone()
                self.dbcursor.fetchall() # flush cursor
                if nedit_row['num_edits'] >= params['filter-threshold']:
                    continue

                # Passed all criteria, adding the user
                other_editors[user] = 1;
            
	    # Now we have all relevant stakeholders in the article, and can
	    # compute the appropriate association.
            for user in other_editors.keys():
	        # Add user to coeditor-map so we'll skip this user later
                coeditor_map[user] = 1

                (assoc, shared) = self.user_association(
                    user, contribs, params['filter-threshold'])
                if assoc < association_threshold:
                    continue

                user_assoc[user] = assoc
                user_shared[user] = shared

        sys.stderr.write("Found {} pre-neighbours\n".format(
            len(user_assoc)))

        # Find nhood of top k users
        k = 250  # Larger nhood for more recs, hopefully
        nhood = sorted(user_assoc,
                       key=itemgetter(1),
                       reverse=True)[:k]

        # Gather up preds
        for user in nhood: 
            # sys.stderr.write("user {} assoc {} shared {}\n".format(user, user_assoc[user], user_shared[user]))

            # Find other items they've rated
            self.dbcursor.execute(self.get_articles_by_user_query,
                                  {'username' : user})
            for row in self.dbcursor:
                new_item = row['rev_title']
                rec_map[new_item] = rec_map.get(new_item, 0) + \
                                    user_assoc[user]
                coedit_count[new_item] = coedit_count.get(new_item, 0) + 1

        # sys.stderr.write("Gathered predictions from neighbourhood, now have {} recs\n".format(len(rec_map)))
                
        # Take out items already given 
        for item in contribs:
            if item in rec_map:
                del(rec_map[item])

        # sys.stderr.write("Took out existing contribs, now {} recs\n".format(len(rec_map)))
                
        # Take out items from user
        self.dbcursor.execute(self.get_articles_by_user_query,
                              {'username': user_for_query})
        for row in self.dbcursor:
            page_title = row['rev_title']
            if page_title in rec_map:
                del(rec_map[page_title])

        # sys.stderr.write("Took out all known articles by user, now {} recs\n".format(len(rec_map)))
        
        # Filter by coedit thresh
        rec_map = {k:v for k,v in rec_map.items()
                   if coedit_count[k] >= params['threshold']}

        # sys.stderr.write("Filtered by coedit threshold, now {} recs\n".format(len(rec_map)))
        
        # Done with the database, disconnect
        self.dbconn = None
        self.dbcursor = None
        sbdb.disconnect()
        
        # Rank 'em and spit out 'nrecs' of them
        for (item, value) in sorted(rec_map.items(),
                                    key=itemgetter(1),
                                    reverse=True)[:params['nrecs']]:
            recs.append({'item': item,
                         'value': value})
        return(recs)

    def user_association(self, user, basket_ref, exp_threshold):
        '''
        Calculate the association between the given user and a list of edits.
        
        :param user: The user we're examining.
        :param contribs: A list of edits we're comparing `user` to.
        :param exp_threshold: Threshold for being an "expert" user.
        '''
        shared = 0
        user_edits_ref = {}

        # Find common articles.  We first find the user's editcount,
        # to check if this user is in the top 10% of users or not.
        # If they are (as defined by filter-threshold) we'll only use
        # non-minor, non-reverting article edits for comparison.
        # Otherwise, we use all articles the user edited.
        self.dbcursor.execute(self.get_editcount_query,
                              {'username': user})
        row = self.dbcursor.fetchone()
        self.dbcursor.fetchall() # flush cursor
        user_editcount = row['num_edits']

        user_query = self.get_articles_by_user_query # default is non-expert
        if user_editcount >= exp_threshold:
            # sys.stderr.write("User {} is expert.\n".format(user))
            user_query = self.get_articles_by_expert_user_query
        else:
            # sys.stderr.write("User {} is not expert.\n".format(user))
            pass
            
        self.dbcursor.execute(user_query, {'username': user})
        for row in self.dbcursor:
            user_edits_ref[row['rev_title']] = 1

        for item in basket_ref:
            if item in user_edits_ref:
                shared += 1
                
        assoc = shared / (len(basket_ref) + len(user_edits_ref) - shared)
        return(assoc, shared)
