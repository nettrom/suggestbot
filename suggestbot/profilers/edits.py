#!/usr/bin/env python
# -*- coding: utf-8  -*-
'''
Library for retrieving a user's edits to use as their interest profile.

Copyright (C) 2005-2016 SuggestBot Dev Group

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

__version__ = "$Id$"

import re
import logging

from datetime import datetime, timedelta

import pywikibot

from suggestbot import config
import suggestbot.utilities.reverts as sur

class EditProfiler:
    def get_last_n(self, site, username, n=500):
        '''
        Grab the user's `n` most recent edits, build a set of the titles,
        and return that as a list.

        :param site: Wikipedia site the user belongs to
        :type site: pywikibot.Site

        :param username: Username of the user we're fetching edits for
        :param n: The number of edits to build the set from
        '''

        query = pywikibot.data.api.Request(site=site, action="query")
        query['list'] = "usercontribs"
        query['ucnamespace'] = 0
        query['uclimit'] = n
        query['ucuser'] = username
        query['continue'] = ''

        try:
            response = query.submit()
        except pywikibot.Error as e:
            # Something reasonably serious happened, so return.
            logging.warning('User contributions query failed')
            logging.warning('{} : {}'.format(e[0], e[1]))
            return([])

        # Valid response? If not, return an empty list
        if not 'query' in response \
           or not 'usercontribs' in response['query']:
            logging.warning("Possible query response error for {}:{}, unable to continue".format(lang, username))
            return([])
          
        edits = response['query']['usercontribs']
        if not edits:
            logging.info('{}:{} has no edits'.format(lang, username))
            return([])

        edited_titles = set()
        for edit in edits:
            try:
                edited_titles.add(edit['title'])
            except KeyError:
                # edit info redacted
                continue

        return(list(edited_titles))
    
    def make_profile(self, lang, username, multiplier=0.98,
                     min_articles=64,
                     filter_minor=True, filter_reverts=True):
        """
        Build an interest profile for the given user, try to return a
        minimum of `min_articles`.

        :param lang: Language code of the Wikipedia this user belongs to
        :type lang: str

        :param username: Username of the user we're fetching edits for
        :type username: str

        :param min_articles: The minimum number of articles we seek to return
        :type min_articles: int
        
        :param filter_minor: filter out minor edits?
        :type filter_minor: bool

        :param filter_reverts: filter out reverts?
        :type filter_reverts: bool
        """
        # Proposed new algorithm:
        # Incrementally walk backwards in the user's edit history
        # until we have data on k articles, counting up the edits.
        # An edit is scored as 0.98^n where n is the number of days
        # back since the most recent user edit (this prevents a user's
        # profile from being altered just by time passing).  We choose
        # 0.98 because it means an edit 35 days out counts 0.5.  At the
        # same time, we set a lower bound of 0.025, meaning any edit
        # older than ~1/2 year is scored the same. This is done to prevent
        # adding and ranking very low scores.
        # We gather edits until we have k articles, or exhausted our
        # search.

        # Note: The old algorithm would iterate through the user's
        # last 500 edits and store _everything_, but only use a random
        # sample of those articles for recommendations The rest would
        # be stored, however, so we'll have to return two things:
        # 1: the interest profile.
        # 2: a list of all relevant articles to be used for filtering.
        
        # We return a dictionary mapping titles to interest scores.

        logging.info("Building profile {lang}:{username}".format(lang=lang, username=username))
        
        site = pywikibot.Site(lang)

        # Default profile
        profile = {'interests' : {},
                   'all_edits' : self.get_last_n(site, username)}
       
        # Start building the query
        query = pywikibot.data.api.Request(site=site, action="query")
        query['list'] = "usercontribs"
        query['ucnamespace'] = 0
        query['ucuser'] = username
        query['continue'] = ''

        # By default we'll get 500 edits a time, for a max of 10 times
        query['uclimit'] = 500
        n_tries = 10
        
        if site.has_right('apihighlimits'):
            # I'm a bot, so I'll get 5,000 in one go and be done with it
            query['uclimit'] = 5000
            n_tries = 1

        if filter_minor:
            query['ucshow'] = '!minor'

        done = False
        attempts = 0
        first_date = None
        last_title = ''
        while not done and attempts < n_tries:
            # Submit the query to the API. If the query continues,
            # update the query parameters, otherwise we're done.
            logging.info('Making attempt {}'.format(attempts))
            try:
                response = query.submit()
                if 'continue' in response:
                    query['continue'] = response['continue']['continue']
                    query['uccontinue'] = response['continue']['uccontinue']
                else:
                    done = True
            except pywikibot.Error as e:
                # Something reasonably serious happened, so return.
                logging.warning('User contributions query failed')
                logging.warning('{} : {}'.format(e[0], e[1]))
                return(profile)

            # Valid response? If not, return whatever we have.
            if not 'query' in response \
               or not 'usercontribs' in response['query']:
                logging.warning("Possible query response error for {}:{}, unable to continue".format(lang, username))
                return(profile)
          
            edits = response['query']['usercontribs']
            if not edits:
                logging.info('{}:{} has no edits'.format(lang, username))
                return(profile)

            logging.info('Processing {} edits'.format(len(edits)))
            
            # OK, we have some data, call this a valid attempt...
            attempts += 1

            for edit in edits:
                try:
                    title = edit['title']
                    timestamp = datetime.strptime(edit['timestamp'],
                                                  '%Y-%m-%dT%H:%M:%SZ')
                    comment = edit['comment']
                except KeyError:
                    # edit info redacted
                    continue
                
                # skip if a revert
                if filter_reverts and self.is_revert(lang, comment):
                    logging.info('"{}" identified as revert'.format(comment))
                    continue
                                 
                if not first_date:
                    first_date = timestamp
                    profile[title] = 1
                else:
                    # Note: first_date is the most recent edit, so we
                    # subtract the edit's older timestamp to get the diff.
                    # We use max() to prevent small-number math.
                    diff = first_date - timestamp
                    profile['interests'][title] = profile.get(title, 0) + \
                                                  max(0.025,
                                                      multiplier**diff.days)

                logging.info('Profile now contains {} articles'.format(len(profile['interests'])))
                                 
                if not last_title:
                    last_title = title
                elif len(profile['interests']) == min_articles \
                     and last_title != title:
                    done = True

        # Returns user profile
        return profile

    def is_revert(self, lang, edit_comment):
        '''
        Determine if the edit comment is a revert based on the given language.
        
        :param lang: Language we're checking
        :param edit_comment: The (unparsed) edit comment
        '''

        # Note: we use search, not match, and require anchoring
        # in the regex as necessary.

        if re.search(sur.REVERT_RE[lang], edit_comment):
            return(True)

        if lang == 'en' and \
           (re.search(sur.VLOOSE_RE, edit_comment) or \
            re.search(sur.VSTRICT_RE, edit_comment)):
            return(True)
        
        return(False)

    def get_edits(self, username, lang, n):
        '''
        Get a user's last `n` edits.  Kept for backwards compatibility
        as it feeds the recserver's edit-based profiler.

        :param username: Username of the user we're getting edits for
        :param lang: Language code of the Wikipedia we're accessing
        :paran n: Number of edits to grab
        '''

        # List of edits (as dicts) we'll return
        user_edits = []

        site = pywikibot.Site(lang)
        query = pywikibot.data.api.Request(site=site, action="query")
        query['list'] = "usercontribs"
        query['ucnamespace'] = 0
        query['uclimit'] = n
        query['ucuser'] = username
        query['continue'] = ''

        try:
            response = query.submit()
        except pywikibot.Error as e:
            # Something reasonably serious happened, so return.
            logging.warning('User contributions query failed')
            logging.warning('{} : {}'.format(e[0], e[1]))
            return([])

        # Valid response? If not, return an empty list
        if not 'query' in response \
           or not 'usercontribs' in response['query']:
            logging.warning("Possible query response error for {}:{}, unable to continue".format(lang, username))
            return(user_edits)
          
        edits = response['query']['usercontribs']
        if not edits:
            logging.info('{}:{} has no edits'.format(lang, username))
            return(user_edits)

        for edit in edits:
            if 'minor' in edit:
                edit['minor'] = True
            else:
                edit['minor'] = False
            user_edits.append(edit)
                            
        return(user_edits)
 
def main():
    logging.basicConfig(level=logging.INFO)
    
    lang = u'en'
    user = u'Nettrom'
    profiler = EditProfiler()

    profile = profiler.make_profile(lang, user)
    print('Got interest profile with {n} items for user {username}'.format(n=len(profile['interests']),username=user))
    print(profile['interests'])
    print(profile['all_edits'])
    print("No. of items in profile: {}, no. of most recent edited articles: {}".format(len(profile['interests']), len(profile['all_edits'])))
    print("")

    print("Testing backwards compatibility...")
    edits = profiler.get_edits(user, lang, 500)
    print("Asked for 500 edits, got {} edits back".format(len(edits)))
    print("Printing first 5:")
    for edit in edits[:5]:
        print(edit)
    
if __name__ == '__main__':
    main()
