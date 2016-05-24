#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Library for running the central server that recommends articles
to edit to Wikipedia contributors.

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

import re
import sys
import logging

from suggestbot import config, db
import suggestbot.utilities.reverts as sur

import json
import requests

import xmlrpc.server
import xmlrpc.client

class RecommendationServer:
    def __init__(self):
        # Set up the database
        self.db = db.SuggestBotDatabase()
        self.dbconn = None
        self.dbcursor = None

    def is_unimportant_by_comment(self, comment_text, lang):
        '''
        Determine if an edit's comment suggests it is not an important
        indicator of interest in the given article.  We filter out
        common anti-vandalism edits as well as AutoWikiBrowser and HotCat.

        :param comment_text: The text of the edit comment
        :param lang: Language code of the Wikipedia we're checking on
        '''
        
        if not comment_text:
            return(False)

        if lang in sur.REVERT_RE \
           and re.search(sur.REVERT_RE[lang], comment_text, re.I | re.X):
            return(True)

        for regex in [sur.VLOOSE_RE, sur.VSTRICT_RE, sur.AWB, sur.HotCat,
                      sur.Twinkle, sur.curation, sur.misc]:
            if re.search(regex, comment_text, re.I | re.X):
                return(True)

        # nope, no matches
        return(False)
    
    def get_edited_items(self, lang, user):
        '''
        Get edited items for a user in a given language.
        '''

        all_edits = {}
        edits = []
        not_minor_edits = []
        reverts = {}
        sp = xmlrpc.client.ServerProxy("http://{hostname}:{port}".format(hostname=config.edit_server_hostname, port=config.edit_server_hostport))
        try:
            raw_edits = sp.get_edits(user,
                                     lang,
                                     config.nedits)
        except xmlrpc.client.Error as e:
            logging.error('Getting edits for {0}:User:{1} failed'.format(
                lang, user))
            logging.error(e)
            return((all_edits, edits))

        for edit in raw_edits:
            edits.append(edit['title'])
            all_edits[edit['title']] = 1
            
            if not edit['minor']:
                not_minor_edits.append(edit['title'])

            if config.filter_unimportant:
                if not edit['title'] in reverts:
                    reverts[edit['title']] = 'revert'
                if not self.is_unimportant_by_comment(edit['comment'], lang):
                    reverts[edit['title']] = 'keep'

        # Replace all edits, items with non-minor ones if asked to filter
        # and if there were some not-minor edits
        if config.filter_minor and not_minor_edits:
            edits = not_minor_edits

        # Remove unimportant edits if needed and able
        if config.filter_unimportant:
            goodedits = [edit for edit in edits if reverts[edit] == 'keep']
            if goodedits:
                edits = goodedits

        useful_edits = []
        items = set()
        for edit in edits:
            if not edit in items:
                useful_edits.append(edit)
                items.add(edit)

            if len(useful_edits) == config.nedits:
                break

        # Return a tuple of all edits and the useful ones
        return(all_edits, useful_edits)
        
    def get_coedit_recs(self, lang, user, user_edits):
        '''
        Connect to the coedit recommender and get recommendations for
        a specific user and language.

        :param lang: Language code of the Wikipedia we're recommending for
        :param user: Username of the user who requested recommendations
        :param user_edits: Dict of edits this user made (title -> num_edits)
        '''

        recommendations = []
        sp = xmlrpc.client.ServerProxy("http://{hostname}:{port}".format(
            hostname=config.coedit_hostname,
            port=config.coedit_hostport))
        try:
            recommendations = sp.recommend(user,
                                           lang,
                                           user_edits,
                                           config.nrecs_per_server,
                                           config.coedit_threshold,
                                           config.coedit_backoff)
        except xmlrpc.client.Error as e:
            logging.error('Failed to get coedit recommendations for {0}:User:{1}'.format(
                lang, user))
            logging.error(e)

        return(recommendations)

    def get_textmatch_recs(self,lang, user, user_edits):
        '''
        Connect to the text recommender and get recommendations for
        a specific user and language.

        :param lang: Language code of the Wikipedia we're recommending for
        :param user: Username of the user who requested recommendations
        :param user_edits: Dict of edits this user made (title -> num_edits)
        '''

        recommendations = []
        sp = xmlrpc.client.ServerProxy("http://{hostname}:{port}".format(
            hostname=config.textmatch_hostname,
            port=config.textmatch_hostport))
        try:
            rec_params = {
                'nrecs': config.nrecs_per_server
                }
            recommendations = sp.recommend(user,
                                           lang,
                                           user_edits,
                                           rec_params)
        except xmlrpc.client.Error as e:
            logging.error('Failed to get text-based recommendations for {0}:User:{1}'.format(
                lang, user))
            logging.error(e)

        return(recommendations)

    def get_link_recs(self, lang, user, user_edits):
        '''
        Connect to the link recommender and get recommendations for
        a specific user and language.

        :param lang: Language code of the Wikipedia we're recommending for
        :param user: Username of the user who requested recommendations
        :param user_edits: Dict of edits this user made (title -> num_edits)
        '''

        # The link recommender expects a dictionary mapping page titles
        # to scores, so we make that dictionary
        user_edit_dict = {title : 1 for title in user_edits}
        
        recommendations = []

        req_headers = {
            'User-Agent': config.http_user_agent,
            'From': config.http_from
        }
        req_params = {'lang': lang,
                      'nrecs': config.nrecs_per_server}
        
        attempts = 0
        while attempts < config.max_url_attempts \
              and len(recommendations) == 0:
            attempts += 1
            r = requests.post(config.linkrec_url,
                              data={'items': json.dumps(user_edit_dict),
                                    'params': json.dumps(req_params)},
                              headers=req_headers)
            if r.status_code != 200:
                logging.warning("Tool Labs web server did not return 200 OK")
            else:
                try:
                    response = r.json()
                    recommendations = response['success']
                except ValueError:
                    logging.error("Unable to decode response as JSON")
                except KeyError:
                    logging.error("Did not find key 'success' in reponse, error?")
        if attempts == config.max_url_attempts:
            logging.warning('Reached max attempts to contact Tool Labs HTTP server without success')
        return(recommendations)
    
    def recommend(self, lang, username, rec_params):
        '''
        Collect a set of articles to recommend for the given user in the
        specified language, with the supplied recommendation parameters.

        :param lang: Language code of the Wikipedia we're recommending for
        :param username: Name of the user we're recommending to.
        :param params: Recommendation paramaters
        :type params: dict
        '''

        # SQL query to add an entry to the seeds table
        addseed_query = r"""INSERT INTO {}
                            (id, title)
                            VALUES (%s, %s)""".format(config.req_seedstable)

        # Default result of a recommendation
        rec_result = {'code': 200,
                      'message': 'OK',
                      'recs': {}}

        sys.stderr.write("Requested to recommend articles for {0}:User:{1}\n".format(
            lang, username))
        
        if 'debug-headers' in rec_params and rec_params['debug-headers']:
            print("For debugging purposes, the recommendation paramaters:")
            for param, value in rec_params.items():
                if param == 'articles':
                    print('Got {n} articles to use as an interest profile:'.format(n=len(rec_params['articles'])))
                    for article in value:
                        print('* {0}'.format(article))
                else:
                    print('{0} = {1}'.format(param, value))
            return(rec_result)
        
        # We need to keep track of all items, even if some are filtered
        all_articles = {}
        user_articles = []

        if 'articles' in rec_params and len(rec_params['articles']) > 0:
            # We were given a set of articles to use as a basis
            all_articles = {k: 1 for k in rec_params['articles']}
            user_articles = list(all_articles.keys())
            if len(user_articles) > config.nedits:
                user_articles = user_articles[:config.nedits]
        else:
            (all_articles, user_articles) = self.get_edited_items(
                lang, username)

        if not user_articles:
            logging.warning('Found no articles to use as a basis for {0}:{1}'.format(lang, username))
            return(rec_result)

        # If this is a request and no seeds were supplied with the request,
        # add the articles to the request's seed list.
        if rec_params['request-type'] == 'single-request' \
           and ('articles' not in rec_params \
                or not rec_params['articles']):
            logging.info('Adding {n} single-request articles to the seed list'.format(n=len(user_articles)))
            if not self.db.connect():
                logging.warning('Unable to connect to SuggestBot database')
            else:
                (self.dbconn, self.dbcursor) = self.db.getConnection()
                try:
                    self.dbcursor.executemany(
                        addseed_query,
                        [(rec_params['request-id'], title)
                         for article in user_articles])
                except MySQLdb.Error as e:
                    logging.error('Failed to insert seeds into the database')
                    logging.error('{0} : {1}'.format(e[0], e[1]))
                     
                self.db.disconnect()
                self.dbcursor = None
                self.dbconn = None

        # Recommendations form each of our rec servers
        rec_lists = {}

        logging.info('Getting recommendations from the co-edit recommender')
        rec_lists['coedits'] = self.get_coedit_recs(lang, username,
                                                    user_articles)
        if rec_lists['coedits']:
            logging.info('Successfully retrieved co-edit recommendations')

        logging.info('Getting recommendations from the link recommender')
        rec_lists['links'] = self.get_link_recs(lang, username,
                                                  user_articles)
        if rec_lists['links']:
            logging.info('Successfully retrieved link-based recommendations')
        
        logging.info('Getting recommendations from the text recommender')
        rec_lists['textmatch'] = self.get_textmatch_recs(lang, username,
                                                         user_articles)
        if rec_lists['textmatch']:
            logging.info('Successfully retrieved text-based recommendations')

        # The recommenders returns an ordered list of dicts, where
        # each list item is a dict with a key "item" mapping to the
        # page title, and "value" to the score returned.  At the
        # moment we only care about rank, so we collapse these to
        # lists of page titles
        for recommender in rec_lists.keys():
            rec_lists[recommender] = [rec['item'] \
                                      for rec in rec_lists[recommender]]
            
        # Add categories if not present
        if not 'categories' in rec_params:
            rec_params['categories'] = config.task_categories[lang]
            
        # Prepare the parameters for the filter server
        filter_server_params = {
            'categories' : rec_params['categories'],
            'nrecs-per-server' : config.nrecs_per_server,
            'request-type' : rec_params['request-type'],
            'nrecs' : rec_params['nrecs'],
            'log' : True,
            }

        filtered_recs = []
        sp = xmlrpc.client.ServerProxy("http://{hostname}:{port}".format(
            hostname=config.filter_server_hostname,
            port=config.filter_server_hostport))
        try:
            logging.info('Filtering recommendations')
            filtered_recs = sp.getrecs(username,
                                       lang,
                                       rec_lists,
                                       all_articles,
                                       filter_server_params)
            logging.info('Successfully filtered recommendations')
        except xmlrpc.client.Error as e:
            logging.error("Failed to filter recommendations for {0}:User:{1}".format(lang, username))
            logging.error(e)
            return(rec_result)

        rec_result['recs'] = filtered_recs

        print("Completed recommendations for {0}:User:{1}".format(lang, username))
        logging.info("Returning {} recommendations".format(len(rec_result['recs'])))
        return(rec_result)

