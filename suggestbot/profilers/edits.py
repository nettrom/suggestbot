#!/usr/bin/env python
# -*- coding: utf-8  -*-
'''
Library for retrieving a user's edits to use as their interest profile.

Copyright (C) 2005-2013 SuggestBot Dev Group

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

from __future__ import with_statement

__version__ = "$Id$"

import re
import os
import sys
import logging

from datetime import datetime, timedelta

import pywikibot

## FIXME: PEP8 style changes
## FIXME: configuration variables
## FIXME: configuration library
# from Config import SuggestBotConfig

## FIXME: library fix, add reverts library
import ..utils.reverts

class EditGetter:
    def __init__(self, config=None):

        self.config = config
        # if not config:
        #     self.config = SuggestBotConfig()

    def getUserEdits(self, lang, wikiSite, username, startDate, endDate,
                     filterMinor, filterReverts, edit_dict, recent_set):
        n_contribs = 500
        if wikiSite.has_right('apihighlimits'):
            n_contribs = 5000

        query = pywikibot.data.api.Request(site=wikiSite, action="query")
        query['list'] = u"usercontribs"
        query['ucnamespace'] = 0
        query['uclimit'] = n_contribs
        query['ucstart'] = startDate.strftime('%Y%m%d%H%M%S')
        query['ucend'] = endDate.strftime('%Y%m%d%H%M%S')
        query['ucuser'] = username
        if filterMinor:
            query['ucshow'] = '!minor'

        attempts = 0
        max_attempts = 3
        done = False
        while attempts < max_attempts and not done:
            try:
                response = query.submit()
                if 'query-continue' in response:
                    query['ucstart'] = response['query-continue']['usercontribs']['ucstart']
                else:
                    done = True
            except:
                attempts += 1

        if not 'query' in response \
                        or not 'usercontribs' in response['query']:
                logging.warning(u"Possible query response error for {lang}:{username}, unable to continue".format(lang=lang, username=username))
                return

        edits = response['query']['usercontribs']

        if filterReverts == True:
            edits[:] = [edit for edit in edits \
                            if re.match(Reverts.REVERT_RE[lang],
                                        edit[u'comment']) == None]
            #Checks for english specific revert tags
            if lang == u'en':
                edits[:] = [edit for edit in edits \
                                if re.match(Reverts.VLOOSE_RE,
                                            edit[u'comment']) == None \
                                and re.match(Reverts.VSTRICT_RE,
                                             edit[u'comment']) == None]

        # adds to edit dictionary, based on number of edits made on an article,
        # and adds title to recent article set
        for edit in edits:
            title = edit[u'title']
            recent_set.add(title)
            edit_dict[title] = edit_dict.get(title,
                                             {u'numEdits': 0,
                                              u'firstedit': edit[u'timestamp']})
            edit_dict[title][u'numEdits'] += 1
    
    def getEdits(self, freq=7, lang=None,  username=None,
                 history_multiplier = 4, num_retries = 4,
                 min_articles=64, min_avg_edits = 1.05,
                 filterMinor=True, filterReverts=True):
        """
        Build an interest profile for the given user, return nItems.

        @param lang: Language code of the Wikipedia this user belongs to
        @type lang: unicode

        @param username: Username of the user we're fetching edits for
        @type username: unicode

        @param nItems: number of items to return
        @type nItems: int

        @param date: Date from which to start iterating edits, format YYYYMMDDHHMMSS.
                     Default is to fetch edits from the current time.
        @type date: str

        @param filterMinor: filter out minor edits?
        @type filterMinor: bool

        @param filterReverts: filter out reverts?
        @type filterReverts: bool
        """
        edits = []

        if not lang \
                or not username:
            logging.error("getEdits called without lang code or username, unable to continue")
            return edits

        logging.info(u"Getting edits for {lang}:{username}".format(lang=lang, username=username))

        wikiSite = pywikibot.getSite(lang)
        wikiSite.login()

        # sets initial time conditions for first article retrieval
        now = datetime.utcnow()
        startTime = now
        endTime = now - timedelta(days = freq * history_multiplier)

        edit_dict = {}
        all_recent_edits = set()
        avg_edits = 0
        profile = {}
        
        self.getUserEdits(lang, wikiSite, username, startTime, endTime, filterMinor, filterReverts, edit_dict, all_recent_edits)
        if not edit_dict:
             logging.warning(u"{username} had no recent edits for {lang}".format(lang = lang, username=username))
             profile['edit profile'], profile['all recent edits'] = self.getOldEdits(lang, username, 128, filterMinor, filterReverts)
             return profile   
        for title in edit_dict:
                avg_edits += edit_dict[title][u'numEdits']
                avg_edits = avg_edits / len(edit_dict)
           
        retries = 0
        #keeps adding articles to profile until ideal conditions met or retry limit is met
        while len(edit_dict) < min_articles and avg_edits < min_avg_edits:   
                startTime = endTime
                endTime = startTime \
                    - timedelta(days = freq * history_multiplier / 2)
                prev_num_articles = len(edit_dict)    
                self.getUserEdits(lang, wikiSite, username, startTime, endTime, filterMinor, filterReverts, edit_dict, all_recent_edits)
                retries +=1

                prev_avg_edits = avg_edits                
                avg_edits = 0
                for title in edit_dict:
                        avg_edits += edit_dict[title][u'numEdits']
                avg_edits = avg_edits / len(edit_dict)
                
                if avg_edits <= prev_avg_edits and len(edit_dict) == prev_num_articles:
                        break
                
                if retries >= num_retries:
                        break
        
        sorted_list = sorted(edit_dict.items(), key=lambda x: x[1][u'firstedit'], reverse = True)
        edits = [(title, val[u'numEdits']) for (title, val) in sorted_list]

        #adds the rest of the edits to all_recent_edits, without worrying about adding them to the edit profile itself
        startTime = endTime
        endTime = now - timedelta(days = freq*history_multiplier * 12)
        self.getUserEdits(lang, wikiSite, username, startTime, endTime, filterMinor, filterReverts, edit_dict, all_recent_edits)        

        #stores data into dictionary to return
        profile['edit profile'] = edits
        profile['all recent edits'] = all_recent_edits                 

        # Returns user profile
        return profile

    def stopme(self):
        pywikibot.stopme()

    def getOldEdits(self, lang=None, username=None, nItems=128, 
                 filterMinor=True, filterReverts=True):
        """
        Build an interest profile for the given user, return nItems.

        @param lang: Language code of the Wikipedia this user belongs to
        @type lang: unicode

        @param username: Username of the user we're fetching edits for
        @type username: unicode

        @param nItems: number of items to return
        @type nItems: int

        @param date: Date from which to start iterating edits, format YYYYMMDDHHMMSS.
                     Default is to fetch edits from the current time.
        @type date: str

        @param filterMinor: filter out minor edits?
        @type filterMinor: bool

        @param filterReverts: filter out reverts?
        @type filterReverts: bool
        """
        edits = []

        if not lang \
                or not username:
            logging.error("getEdits called without lang code or username, unable to continue")
            return edits

        logging.info(u"Getting edits for {lang}:{username}".format(lang=lang, username=username))

        wikiSite = pywikibot.getSite(lang)
        wikiSite.login()

        n_contribs = 500

        query = pywikibot.data.api.Request(site=wikiSite, action="query")
        query['list'] = u"usercontribs"
        query['ucnamespace'] = 0
        query['uclimit'] = n_contribs
        query['ucuser'] = username

        response = query.submit()

        if not 'query' in response \
                or not 'usercontribs' in response['query']:
            logging.warning(u"Possible query response error for {lang}:{username}, unable to continue".format(lang=lang, username=username))
            return edits

        edits = response['query']['usercontribs']

        if filterMinor == True:
            edits[:] = [edit for edit in edits if 'minor' in edit]

        if filterReverts == True:
            edits[:] = [edit for edit in edits if re.match(Reverts.REVERT_RE[lang],edit[u'comment'])==None]
            #Checks for english specific revert tags
            if lang == u'en':
                edits[:] = [edit for edit in edits if re.match(Reverts.VLOOSE_RE, edit[u'comment'])== None and re.match(Reverts.VSTRICT_RE, edit[u'comment'])==None]

        #creates edit dictionary, based on number of edits made on an article
        edit_dict = {}
        all_edits_set = set()
        for edit in edits:
            title = edit[u'title']
            all_edits_set.add(title)
            if len(edit_dict) < nItems:
                edit_dict[title] = edit_dict.get(title, {u'numEdits': 0, u'firstedit': edit[u'timestamp']})
                edit_dict[title][u'numEdits'] += 1

        sorted_list = sorted(edit_dict.items(), key=lambda x: x[1][u'firstedit'], reverse = True)
        edits = [(title, val[u'numEdits']) for (title, val) in sorted_list]                   

        # Return contribs list
        return edits[:nItems], all_edits_set

def main():
    testLang = u'en'
    testUser = u'Nettrom'
    myGetter = EditGetter()
    profile = myGetter.getEdits(lang=testLang, username = testUser)
    print u'Got interest profile with {n} items for user {username}'.format(n=len(profile['edit profile']),username=testUser).encode('utf-8')
    print profile['edit profile']
    print profile['all recent edits']
    print len(profile['edit profile'])
    print len(profile['all recent edits'])

if __name__ == '__main__':
	main()
