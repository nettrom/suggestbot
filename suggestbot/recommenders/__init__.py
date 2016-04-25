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
        self.db = SuggestBotDatabase()
        self.dbConn = None
        self.dbCursor = None

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
           and re.search(regex, sur.REVERT_RE[lang], re.I | re.X):
            return(True)

        for regex in [sur.VLOOSE_RE, sur.VSTRICT_RE, sur.AWB, sur.HotCat,
                      sur.Twinkle, sur.curation, sur.misc]:
            if re.search(regex, edit_comment, re.I | re.X):
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
        with xmlrpc.client.ServerProxy("http://{hostname}:{port}".format(
                hostname=config.edit_server_hostname,
                port=config.edit_server_hostport)) as sp:
            try:
                edits = sp.getedits(user,
                                    lang,
                                    config.nedits)
            except xmlrpc.client.Error as e:
                logging.error('Getting edits for {0}:User:{1} failed'.format(
                    lang, user))
                logging.error(e)
                return((all_edits, edits))

        for edit in edits:
            edits.append(edit['title'])
            all_edits[edit['title']] = 1
            
            if edit['minor']:
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
        return((all_edits, useful_edits))
        
    def get_coedit_recs(self, lang, user, user_edits):
        '''
        Connect to the coedit recommender and get recommendations for
        a specific user and language.

        :param lang: Language code of the Wikipedia we're recommending for
        :param user: Username of the user who requested recommendations
        :param user_edits: Dict of edits this user made (title -> num_edits)
        '''

        recommendations = []
        with xmlrpc.client.ServerProxy("http://{hostname}:{port}".format(
                hostname=config.coedit_hostname,
                port=config.coedit_hostport)) as sp:
            try:
                recommendations = sp.getedits(user,
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
        with xmlrpc.client.ServerProxy("http://{hostname}:{port}".format(
                hostname=config.textmatch_hostname,
                port=config.textmatch_hostport)) as sp:
            try:
                recommendations = sp.getedits(user,
                                              lang,
                                              user_edits,
                                              config.nrecs_per_server)
            except xmlrpc.client.Error as e:
                logging.error('Failed to get coedit recommendations for {0}:User:{1}'.format(
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

        recommendations = []

        req_headers = {
            'User-Agent': config.http_user_agent,
            'From': config.http_from
        }
        req_params = {'lang': lang,
                      'nrecs': config.nrecs_per_server}
        
        attempts = 0
        while attemps < config.max_url_attempts:
            attempts += 1
            r = requests.post(config.linkrec_url,
                              data={'items': json.dumps(user_edits),
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
    
