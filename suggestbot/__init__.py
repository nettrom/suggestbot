#!/usr/bin/env python
# -*- coding: utf-8  -*-
'''
Library with SuggestBot functionality

Copyright (C) 2013 Morten Wang

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

# Requires:
#   pywikibot (core)
#   Our SuggestBotConfig library

from __future__ import with_statement

__version__ = "$Id$"

import sys
import codecs
import re
import time
import xmlrpclib

import pywikibot
import mwparserfromhell as mwp

from datetime import datetime, timedelta
from random import shuffle

from Config import SuggestBotConfig
from .db import SuggestBotDatabase

# FIXME: use RegularUser object from RegularUserUpdater
# since that has all the parameters

class NotLoggedInError(pywikibot.Error):
    '''Bot is not correctly logged in'''
    pass

class SuggestBot:
    def __init__(self, configFile=None, recPort=None, nRecs=3,
                 postDelay=30, maxRetries=3, verbose=False, testRun=False,
                 lang=None):

	# pywikibot.verbose = True;

        # Get our configuration
        self.config = SuggestBotConfig(configFile)

        self.config.setConfig('REC_SERVER', "localhost")
        if recPort is not None:
            self.config.setConfig('MAIN_SERVER_PORT', recPort)
        self.config.setConfig('NRECS', nRecs)
        self.config.setConfig('POST_DELAY', postDelay)
        self.config.setConfig('POST_RETRIES', maxRetries)

        # Using getConfig() to test verbosity is too verbose.
        self.verbose = verbose
        self.config.setConfig('VERBOSE', verbose)

        self.config.setConfig('TESTRUN', testRun)
        self.config.setConfig('CONNECT_TIMEOUT', 5.0) # 5 second timeout
        self.config.setConfig('CONNECT_RETRIES', 20) # num retries for rec server connections

        if lang:
            self.config.setConfig('WP_LANGCODE', lang)

        # config our site, note that this also logs us in
        self.site = pywikibot.getSite(self.config.getConfig('WP_LANGCODE'))

    def login(self):
        # instantiating a site object logs us in...
        self.site = pywikibot.getSite(self.config.getConfig('WP_LANGCODE'))
        self.site.login()
        # then we can simply check if we're logged in
        return self.isLoggedIn()

    def durrdurr(self):
        '''http://drmcninja.com/archives/comic/14p28'''
        return self.login()

    def pthooey(self):
        return self.logout()
    
    def logout(self):
        '''Logs the bot out, if we're logged in.'''
        if self.site.user():
            self.loginMgr.logout()

    def isLoggedIn(self):
        '''Returns username if we're logged in, None otherwise.'''
        return self.site.user()

    def setConfig(self, key=None, value=None):
        '''Set a configuration variable for the bot.'''
        if not key:
            logging.warning("setConfig called without a key.")
            return False

        self.config.setConfig(key=key, value=value)
        return True

    def getConfig(self, key=None):
        '''Get a configuration variable.'''
        if not key:
            logging.warning("getConfig called without a key.")

        return self.config.getConfig(key)

    def getRecs(self, username="", userGroup="suggest", itemEnd=True,
                filterMinor=False, filterReverts=False, useUserlinks=False,
                isRequest=False, requestId=-1, interestPages=None):
        '''Connect to the main recommendation server and get recommendations
           for the given user.  If successful, a list of recommendations are
           returned.

           @param username: The name of the user we are recommending articles to
           @type username: unicode

           @param userGroup: Which group the user belongs to
           @type userGroup: unicode

           @param itemEnd: recommend based on the user's oldest (False)
                           or most recent (True) 500 contributions in Main namespace
           @type itemEnd: bool

           @param filterMinor: filter out minor edits from the item basket?
           @type filterMinor: bool

           @param filterReverts: do we remove reverts from the item basket?
           @type filterReverts: bool

           @param useUserLinks: do we look for a user's more important contributions
                                by fetching links from their user page? (unsupported)

           @type useUserLinks: bool

           @param isRequest: Is this a one-time request (True), or a users who has signed
                             up to receive recommendations regularly (False)?
           @type isRequest: bool

           @param requestId: ID of this request in the SuggestBot database
           @type requestId: int

           @param interestPages: List of pages the user has expressed interest in,
                                 used for handling requests.
           @type interestPages: pywikibot.Page iterator
           '''

        recServer = xmlrpclib.ServerProxy("http://{hostname}:{port}".format(hostname=self.config.getConfig('REC_SERVER'),
                                                                            port=self.config.getConfig('MAIN_SERVER_PORT')),
                                          allow_none=True)

        # Server expects language, username, and request type as three parameters,
        # and then the rest as a dictionary.  Prepare said dictionary.
        item_end = u"first"
        if itemEnd:
            item_end = u"last"
        recParameters = {'articles': [],
                         'item-end': item_end,
                         'filter-minor': filterMinor,
                         'filter-unimportant': filterReverts,
                         'use-userpage': useUserlinks,
                         'nrecs': self.config.getConfig('NRECS'),
                         'request-id': requestId,
                         }

        # Is this a one-time request, or a regular user?
        request_type = 'regular'
        if isRequest:
            request_type = 'single-request'

        # If this is a request and the user has a list of pages they've expressed interest in...
        if isRequest and interestPages \
           and (len(interestPages) > 0):
            recParameters['articles'] = interestPages

        recs = {}
        try :
            recs= recServer.recommend(self.config.getConfig('WP_LANGCODE'),
                                      username,
                                      request_type,
                                      recParameters)
        except xmlrpclib.Fault, e:
            logging.error("something went wrong when trying to get suggestions:")
            logging.error(u"{error}".format(error=e))

        return recs

    def createRecsPage(self, recs, recTemplate=None, userGroup=None):
        """
        @param recs Recommendations for this user in the right order needed
                    for substitution into our template.
        @type recs list of dicts
        @param recTemplate Relative address on Wikipedia to the template we use for
                           substitution when posting recommendations.  If 'None',
                           the request template found in Config.py for the language
                           defined in config.pm is used (except when lang is defined).
        @type recTemplate str or None

        @param userGroup: name of the (experiment) group the user is in
        @type userGroup: unicode
        """

        # FIXME: Should we send the user a message if we couldn't do anything?
        if not recs:
            return None

        # Create the parameter string of "|CAT?=ITEM" where ? is the order.
        paramString = u""
        for (recTitle, recData) in recs.iteritems():
            paramString = u"{params}|{category}{order}={title}".format(params=paramString,
                                                                       category=recData['cat'],
                                                                       order=recData['rank'],
                                                                       title=recTitle)

        # On English Wikipedia we currently run an experiment with popularity,
        # quality, and task suggestions.  RequestTemplateHandler doesn't supply
        # a user group, so if it is set, we know we're processing regular users.
        if self.config.getConfig('WP_LANGCODE') == u'en' \
                and userGroup:
            for (recTitle, recData) in recs.iteritems():
                # Was popcount calculated?  If not, set it to an empty string,
                # {{formatnum:}} appears to handle that nicely.
                if not 'popcount' in recData \
                        or recData['popcount'] < 0:
                    recData['popcount'] = u""

                # Add quality data
                qual = recData['pred'].lower()
                qualSort = 1.0
                if qual == u'high':
                    qualSort = 3.0
                elif qual == u'medium':
                    qualSort = 2.0
                if recData['pred']: # did we get a prediction?
                    assessedClass = "Unassessed"
                    if recData['qual'] != "NOCLASS":
                        # Set, and capitalise, unless "FA" or "GA"
                        assessedClass = recData['qual']
                        if assessedClass not in ["FA", "GA"]:
                            assessedClass = assessedClass.capitalize()
                    # Turn into quality file link w/assessment and prediction,
                    # using quality map in configuration.
                    predClass = recData['predclass']
                    qual = self.config.getConfig('QUALITY_MAP')[qual].format(rectitle=recTitle, assessedclass=assessedClass, predclass=predClass)

                # Add both popularity and quality parameters to paramString
                paramString = u"{params}|POP{category}{order}={popcount}|QUAL{category}{order}={qualcode}|QUALSORT{category}{order}={qualsort}".format(params=paramString, category=recData['cat'], order=recData['rank'], popcount=recData['popcount'], qualcode=qual, qualsort=qualSort)

                # NOTE: for merge tasks, link to the merge discussion directly?
                #       No, we link to the talk page, where the merge discussion
                #       is likely found, or easy to find.

                # Note: consider also flagging them if "length" is "maybe"?
                # only flag "headings" and "links" if not flagging length
                # Set to True and uncomment if-block if you want that.
                skipLinksAndHeadings = False
                # if 'length:no' in recData['work']:
                #     skipLinksAndHeadings = False;
                
                if not 'work' in recData \
                        or recData['work'] is None:
                    recData['work'] = []

                # For each of the tasks...
                for task in recData['work']:
                    # print "task=", task;
                    # split into task and yes/no/maybe
                    (task, verdict) = task.split(u':')
                    # NOTE: Based on beta testing, we skip marking maybe-tasks
                    #       with a ?
                    if verdict == u'maybe':
                        verdict = u'no'
                    # map into human-readable form
                    task = self.config.getConfig('HUMANTASKS')[task]
                    # should we skip headings and links?
                    if task in [u"headings", u"links"] \
                            and skipLinksAndHeadings:
                        verdict = "no"
                    # make key into configuration's TASK_MAP
                    mapKey = u'{task}-{verdict}'.format(task=task, verdict=verdict)
                    # put it all together...
                    paramString = u"{params}|{task}{category}{order}={mapping}".format(params=paramString, task=task.upper(), category=recData['cat'], order=recData['rank'], mapping=self.config.getConfig('TASK_MAP')[mapKey].format(rectitle=recTitle))

        # Now create the subst template which refers to
        # our self-defined message template, with the created string of parameters
        if not recTemplate:
            lang = self.config.getConfig('WP_LANGCODE')
            recTemplate = self.config.getConfig('TEMPLATES')[lang]['request']

        # Add in the template and parameters (note escaping of '{' with '{{')
        recString = u"{{{{subst:{template}{params}}}}} -- ~~~~".format(template=recTemplate,
                                                                   params=paramString)
        return recString

    # FIXME: get a unit test case of the recommendation post thingamajig
    # replacing content and stuff.

    def addReplaceRecMessage(self, pageSource=u"", recMsg=u"",
                             replace=False):
        """
        Adds or replaces a message with article recommendations to the given
        page source.

        @param pageSource: source wikitext of the page
        @type pageSource: unicode

        @param recMsg: wikitext of the article recommendations
        @type recMsg: unicode

        @param replace: are we replacing (True) or appending (False)?
        @type replace: bool
        """

        # FIXME: if we're going to do heading level control, we will need to...
        # 1: move the heading out of all the templates
        # 2: have a better way of identifying where the header is located
        #    on the page we're working on
        # 3: figure out a way to start with a level 1 heading and then pad
        #    with '=' on both sides until we've reached the right level.

        # (We can't make a call to expand templates since the page might contain
        #  other templates which we don't control)

        if not replace:
            newPageSource = u"{current}\n\n{recs}".format(current=pageSource,
                                                          recs=recMsg)
        else:
            # We're replacing, do some magic to find the last rec and
            # replace from there up until the next non-rec header (or EOF)

            # What language are we posting to?
            lang = self.config.getConfig('WP_LANGCODE')

            # Compile rec message header regex, and all sub-section regexes.
            recHeaderRe = re.compile(self.config.getConfig('REC_HEADER_RE')[lang], re.U)
            subHeaderRegs = []
            for regEx in self.config.getConfig('SUB_HEADER_RE')[lang]:
                subHeaderRegs.append(re.compile(regEx, re.U))

            # Parse the page contents
            parsedCode = mwp.parse(pageSource)

            # Indexes of where the rec message begins and ends
            recMsgStartIdx = 0
            recMsgEndIdx = 0

            # loop through i=0:length(nodes), search for the first occurrence of
            # a heading (isinstance heading) matching REC_HEADER_RE.
            # Store it as recMsgStartIdx if found.
            i = 0
            while i < len(parsedCode.nodes):
                node = parsedCode.nodes[i]
                if isinstance(node, mwp.nodes.heading.Heading) \
                   and recHeaderRe.search(node.strip()):
                    recMsgStartIdx = i
                    break

                # Move along...
                i += 1

            # If none was found, ignore and append
            if i == len(parsedCode.nodes):
                newPageSource = u"{current}\n\n{recs}".format(current=pageSource,
                                                              recs=recMsg)
            else:
                # examine the remaining list of nodes, if encountering a section
                # header that does not match REC_HEADER_RE or the subheader regex,
                # stop and store that index.
                i = recMsgStartIdx+1
                while i < len(parsedCode.nodes):
                    node = parsedCode.nodes[i]
                    if isinstance(node, mwp.nodes.heading.Heading):
                        isMatch = recHeaderRe.search(node.strip()) is not None
                        for regEx in subHeaderRegs:
                            if regEx.search(node.strip()):
                                isMatch = isMatch or True
                        if not isMatch:
                            recMsgEndIdx = i
                            break

                    # Move along...
                    i += 1

                # If we exhausted our search, set end index beyond end of nodes,
                # so we delete up until the end.
                if i == len(parsedCode.nodes):
                    recMsgEndIdx = i

            # Now the new page source is the content of parsedtext.nodes[:firstindex]
            # + new content + the content of parsedtext.nodes[lastindex:]
            newPageSource = u"{beforeMsg}{recMsg}\n\n{afterMsg}".format(beforeMsg=u"".join([unicode(node) for node in parsedCode.nodes[:recMsgStartIdx]]),
                                                                    recMsg=recMsg,
                                                                    afterMsg=u"".join([unicode(node) for node in parsedCode.nodes[recMsgEndIdx:]]))

        return newPageSource

    def postRecommendations(self, username=u"", recMsg=None,
                            page=None, force=False, replace=False,
                            headLevel=2):
        '''
        Posts the given recommendation message for 'username' to either their
        user page or a specified user sub-page, forcing the post if set.

        @param username: Username of the user to post to
        @type username: str
        
        @param recMsg: The recommendation message
        @type recMsg: str

        @param page: Page title of a specific user sub-page to post to.
        @type page: str

        @param force: Ignore {{nobots}} and {{bots}} templates and post anyway.
        @type force: bool

        @param replace: Replace the most recent recommendation post, instead of
                        simply appending the post to the page.
        @type replace: bool

        @param headLevel: Which level of heading to use for the recommendation post
        @type headLevel: int
        '''
        if not username or not recMsg:
            logging.error("Unable to post recs, username or recommendation not supplied.")
            return False

        # make a user object
        recUser = pywikibot.User(self.site, username)

        # check if the user is blocked
        if recUser.isBlocked():
            logging.warnng(u"user {username} is blocked, posting aborted.".format(username=username).encode('utf-8'))
            return False

        # get the user's talk page, or a preferred page to post recs to if defined
        if page:
            destPage = pywikibot.Page(self.site, page)
        else:
            destPage = recUser.getUserTalkPage()

        try:
            pageSource = destPage.get()
        except pywikibot.exceptions.NoPage:
            logging.warning(u"Destination page {title} doesn't exist, will be created.".format(title=destPage.title()))
            pageSource = ""
        except pywikibot.exceptions.IsRedirectPage:
            logging.warning(u"Destination page {title} is a redirect, posting cancelled.".format(title=destPage.title()))
            return False

        # We're currently struggling to post to large pages.  If the destination
        # page is >250kB, skip posting, anticipating that it'll be shorter next time.
        if len(pageSource.encode('utf-8')) > 250*1024:
            logging.warning(u"Destination page {title} is too large for saving, {n:,} bytes, posting cancelled!".format(title=destPage.title(), n=len(pageSource.encode('utf-8'))))
            return False

        # What language are we posting to?
        lang = self.config.getConfig('WP_LANGCODE')

        # Create new page source by adding or replacing suggestions
        newPageSource = self.addReplaceRecMessage(pageSource=pageSource,
                                                  recMsg=recMsg,
                                                  replace=replace)

        # if testing, print the proposed userpage
        if self.config.getConfig('TESTRUN'):
            print "SuggestBot is doing a test run. Here's the new page:"
            print newPageSource.encode('utf-8')
        # else: update it, and ask to watch it too
        else:
            try:
                destPage.text = newPageSource
                destPage.save(comment=self.config.getConfig('EDIT_COMMENT')[lang],
                              watch=True, minor=False, force=force)
            except pywikibot.exceptions.EditConflict:
                logging.error(u"Posting recommendations to {title} failed, edit conflict.".format(title=destPage.title()))
                return False
            except pywikibot.exceptions.PageNotSaved as e:
                logging.error(u"Failed posting recommendations to {title} :".format(title=destPage.title()))
                logging.errog(u"{emsg}".format(emsg=e))
                return False
        # done
        return True
        
    def recommend(self, username="", userGroup="suggest", itemEnd=True,
                  filterMinor=False, filterReverts=False, useUserlinks=False,
                  recTemplate=None, force=False, page=None, replace=False,
                  isRequest=False):
        '''Get and post recommendations to the specific user based on the set
           of options given (see getRecs() for specifics).

           @param username: What user are we recommending articles to?
           @type username: unicode

           @param userGroup: Which user group does this user belong to?
           @type userGroup: str
           
           @param itemEnd: Are we looking at their latest contributions or not?
           @type itemEnd: bool

           @param filterMinor: Filter out minor edits?
           @type filterMinor: bool

           @param filterReverts: Filter out reverts?
           @type filterReverts: bool

           @param useUserlinks: Mine the user page for links to important articles?
           @type useUserlinks: bool

           @param recTemplate: Title of the template to use as the recommendation post.
           @type recTemplate: str

           @param force: Ignore {{bots}} and {{nobots}} templates?
                         (default of False is to adhere to those)
           @type force: bool

           @param page: Title of the page we will post recommendations to.
                        If None, we post to the user's talk page.
           @type page: str

           @param replace: Controls whether we replace recs, or simply append them.
           @type replace: bool

           @param isRequest: Is this a one-time request (True), or a users who has signed
                             up to receive recommendations regularly (False)?
           @type isRequest: bool

           '''
        if not username:
            logging.error("must supply username to do recommendations.")
            return None

        # create user object
        # FIXME: instead of passing usernames around, we can pass this user object
        # around...
        recUser = pywikibot.User(self.site, username)

        # Check if the user is blocked.  Since that will aport posting, there's
        # no need to spend time generating recommendations.
        if recUser.isBlocked():
            logging.warning(u"User:{username} is blocked, posting aborted.".format(username=recUser.username))
            return False

        # Test if the destination page is too large, as we otherwise struggle
        # with posting, getting timeouts.
        try:
            if page:
                destPage = pywikibot.Page(self.site, page)
            else:
                destPage = recUser.getUserTalkPage()
            pageSource = destPage.get()
            if len(pageSource.encode('utf-8')) > 250*1024:
                logging.warning(u"Destination page {title} is too large for saving, {n:,} bytes, posting cancelled!".format(title=destPage.title(), n=len(pageSource.encode('utf-8'))))
                return False
        except pywikibot.exceptions.IsRedirectPage:
            logging.warning(u"Destination page {title} is a redirect, posting cancelled.".format(title=destPage.title()).encode('utf-8'))
            return False
        except pywikibot.exceptions.NoPage
            pass

        # get recommendations
        userRecs = self.getRecs(username=username, userGroup=userGroup,
                                itemEnd=itemEnd, filterMinor=filterMinor,
                                filterReverts=filterReverts, useUserlinks=useUserlinks,
                                isRequest=isRequest)
        # if none, post?
        if not "recs" in userRecs \
                or not userRecs["recs"]:
            logging.warning(u"Got no recommendations for User:{username}".format(username=recUser.username))
            return False
        # else, create recs message
        recMsg = self.createRecsPage(userRecs["recs"], recTemplate=recTemplate,
                                     userGroup=userGroup)
        # update userpage (test for now)
        if self.postRecommendations(username=username, recMsg=recMsg,
                                        page=page, force=force, replace=replace):
            # do some logging here
            pass

        return

    def stopme(self):
        pywikibot.stopme()

    def getPageLinks(self, pageTitles=None, namespaces=None):
        '''Get all links from the given pages restricted to the given namespaces'''
        if not pageTitles:
            logging.warning("getPageLinks called with no page titles.")
            return None

        # This method is based on pywikipedia's getReferences() method
        # (see wikipedia.py line 1196 onwards)

        params = {
            'action': 'query',
            'prop' : 'links',
            'list': [],
            'pllimit' : 5000, # high limit only allowed for bots
            'plnamespace' : namespaces,
            }

        slice_size = 100

        # Check if we have bot-flag, if not we can only ask for 500 result at a time,
        # and we send only 10 titles at a time to keep result size down.
        if not self.site.isAllowed('apihighlimits'):
            slice_size = 10
            params['pllimit'] = 500
        
        # iterate over keys() in a meaningful way...
        # e.g. if we're not a bot, send 10 pages at a time, with max 500 results
        # otherwise, send 50, with max 5000 results

        # We return a dictionary where the keys are titles,
        # and the values are lists of pages they link to.
        linkedPages = dict()
        i = 0
        max_ind = len(pageTitles)
        while i < max_ind:
            # get a slice of titles
            j = i+slice_size
            titles = pageTitles[i:j]

            params['titles'] = titles

            logging.info("Getting links for {n} titles through the API".format(n=len(title)))

            allDone = False
            while not allDone:
                pywikibot.get_throttle()
                # FIXME: rewrite to use pywikibot.api instead
                # json_data = query.GetData(params, self.site);
                
                # json_data is mostly a dict in this case.
                # 'query' : the result of the query
                # 'query-continue' : a dict with information on how to continue
                #     in our case one key 'links', with an additional key
                #     'plcontinue' which is the param we should send,
                #          and the value holds the value we need to continue.
                # Under query:
                # 'pages' : dict with info regarding each page we looked up
                #      key is page-id
                #      value is a dict with
                #        'ns' : namespace of the page we looked up
                #        'pageid' : page-id (again)
                #        'links'  : what pages it links to (list)
                #        'title'  : page title
                # 

                # iterate over all pages we got back
                if not json_data:
                    # didn't get any data back, we quit
                    allDone = True
                    continue

                all_pages = json_data['query']['pages']
                for (page, page_data) in all_pages.iteritems():
                    page_title = page_data['title']
                    if not page_title in linkedPages:
                        # create a new list for the links
                        linkedPages[page_title] = list()

                    if not 'links' in page_data:
                        continue

                    # Iterate over the list of links, each entry
                    # is a dict() where 'title' holds the article title.
                    for page_link in page_data['links']:
                        linkedPages[page_title].append(page_link['title'])

                if 'query-continue' in json_data:
                    # We have more data to pull down
                    cont = json_data['query-continue']['links']
                    cont_param = cont.keys()[0]
                    cont_value = cont[cont_param]
                    params[cont_param] = cont_value
                    logging.info("API continue at {cont}".format(cont=cont_value))
                else:
                    allDone = True

            i += slice_size

        return linkedPages

    def getBackLinks(self, pageTitles=None, namespaces=None):
        '''Get all backlinks from the given pages restricted to the given namespaces'''
        if not pageTitles:
            logging.warning("getBackLinks called with no page titles.")
            return None

        # The API only allows for requesting backlinks for _one_ page at a time,
        # so we'll simply push the request on to pywikipedia.

        # We return a dict with the title of each page we got info for,
        # where the value is a list of titles to the pages they link to.
        linkedPages = dict()
        
        for title in pageTitles:
            page_obj = pywikibot.Page(self.site, title)
            linkedPages[title] = []
            # iterate over the lis of references for each title,
            # but don't follow redirects.
            for linkedpage in page_obj.getReferences(follow_redirects=False):
                if linkedpage.namespace in namespaces
                    linkedPages[title].append(linkedpage.title)

        return linkedPages

    def processRegulars(self):
        """
        Find all the regular users defined in the SuggestBot database for
        the current language version of Wikipedia, check if any of them
        are due up for recommendations, and then process and post to those.

        Requires: SuggestBotDatabase library.
        """

        # today is?
        # Note: We use UTC as the basis for our calculations, because
        # the Wikipedia API also returns timestamps as UTC, thus allowing
        # us to correctly post suggestions to new regulars who saw SuggestBot
        # post to their user talk page earlier.
        now = datetime.utcnow()

        statusTable = self.config.getConfig('STATUS_TABLE')
        regularsTable = self.config.getConfig('REGULARS_TABLE')

        # Query to get all regular users of the current language versions
        getRegularsQuery = ur"""SELECT *
                                FROM {regtable}
                                WHERE lang=%(lang)s
                                AND active=1
                                AND retired=0""".format(regtable=regularsTable)

        # Query to update a specific user's status (to processing|idle|ready)
        setStatusQuery = ur"""UPDATE {regtable} SET status=%(status)s
                              WHERE lang=%(lang)s
                              AND username=%(username)s""".format(regtable=regularsTable)

        # Query to update a specific user's last recommendation time
        setLastrecQuery = ur"""UPDATE {regtable}
                               SET last_rec=%(rectime)s
                               WHERE lang=%(lang)s
                               AND username=%(username)s""".format(regtable=regularsTable)

        # Query to set (or reset) the busy bit in the status info table
        updateStatusTableQuery = ur"""UPDATE {status}
                                      SET daily_running=%(status)s
                                      WHERE lang=%(lang)s""".format(status=statusTable)

        # Query to check the busy bit in the status info table, so that
        # multiple updates don't run at the same time (otherwise we'll get
        # double-posts (how do we know that?  we tested it!))
        checkStatusTableQuery = ur"""SELECT daily_running FROM {status}
                                     WHERE lang=%(lang)s""".format(status=statusTable,)

        # Query to get the time of the last suggestion posted
        getLastRecQuery = ur"""SELECT MAX(last_rec) AS last_rec
                               FROM {regtable}
                               WHERE lang=%(lang)s
                               AND active=1""".format(regtable=regularsTable)

        # query to increment the number of recommendations count
        incRecCountQuery = ur'''UPDATE {regtable}
                                SET n_recs=n_recs+1
                                WHERE lang=%(lang)s
                                AND username=%(user)s'''.format(regtable=regularsTable)

        # instantiate the database object, and connect
        myDb = SuggestBotDatabase(config=self.config)
        # if connection fails, fail too.
        if not myDb.connect():
            return False

        # if not, get data for all users of the current language version
        (dbconn, dbcursor) = myDb.getConnection()

        # What language are we running?
        lang = self.config.getConfig('WP_LANGCODE')

        # Check if a job is already running
        dbcursor.execute(checkStatusTableQuery, {'lang': lang})
        row = dbcursor.fetchone()
        dbcursor.fetchall() # flush cursor

        if ord(row['daily_running']):
            logging.warning(u"SuggestBot is already posting to users on {0}-WP, exiting!".format(lang))
            return True

        # Update the status of busyness to pretty busy...
        dbcursor.execute(updateStatusTableQuery, {'status': 1,
                                                  'lang': lang})
        dbconn.commit()

        # Figure out how long since we last ran.
        dbcursor.execute(getLastRecQuery, {'lang': lang})
        row = dbcursor.fetchone()
        dbcursor.fetchall() # flush cursor
        # Check that we got a row and that it's something...
        if row and row['last_rec']:
            timeSinceLastRun = now - row['last_rec']
            # If tSLR.days < 0, something's not right:
            if timeSinceLastRun.days < 0:
                logging.error("Time since last set of recs posted is negative, aborting!")
                return False
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

        dbcursor.execute(getRegularsQuery, {'lang': lang})
        done = False
        while not done:
            row = dbcursor.fetchone()
            if not row:
                done = True
                continue

            # The values of the row we currently use:
            lastRec = row['last_rec']
            period = row['period']
            # Note: we'll have to unicode based on UTF-8, even though our
            # database is UTF-8 and everything, IIRC it's because we do
            # utf8_bin collation, which is the equivalent of "VARCHAR() BINARY"
            # that's used on the Wikimedia servers.
            username = unicode(row['username'], 'utf-8', errors='strict')
            pagetitle = row['page_title']
            design = row['design']

            recTemplate = self.config.getConfig('TEMPLATES')[lang]['regulars']
            # If the user has chosen to use a different design from the default,
            # UTF-8ify it and check if we have a template, then use that.
            if design:
                design = unicode(design, 'utf-8', errors='strict')
                try:
                    recTemplate = self.config.getConfig('TEMPLATES')[lang][design]
                except KeyError:
                    pass
                logging.info(u"found design {0} with template {1}".format(design, recTemplate))

            # If user supplied a sub-page to post to, UTF-8ify it.
            if pagetitle:
                pagetitle = unicode(pagetitle, 'utf-8', errors='strict')

            # If the user wants recs replaced, do so.
            replace = False
            if ord(row['replace_recs']):
                replace = True

            # if lastRec is None (NULL), they didn't receive any recs earlier,
            # which means it's definitely time to post.
            if not lastRec:
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
        logging.info("Checked regulars, found {n} users to post to.".format(n=len(userQueue)))

        # (We shuffle the user list so it doesn't necessarily get processed in
        # alphabetical order, IIRC the results of this SELECT is in sorted
        # order because we use a primary key)
        if len(userQueue) > 0:
            shuffle(userQueue)

        # for each user on said list...
        for user in userQueue:
            # update database to processing
            dbcursor.execute(setStatusQuery, {'status': 'processing',
                                              'lang': lang,
                                              'username': user['username']})
            dbconn.commit()

            logging.info(u"now getting recs for User:{username}".format(username=user['username']))

            # Get recommendations and post...
            # Design and template is passed along based on what we looked
            # up earlier.
            success = self.recommend(username=user['username'],
                                     userGroup='suggest',
                                     filterMinor=True,
                                     filterReverts=True,
                                     page=user['page'],
                                     recTemplate=user['template'],
                                     replace=user['replace'])
            if success:
                # update database to idle, and update last_rec
                dbcursor.execute(setStatusQuery, {'status': 'idle',
                                                  'lang': lang,
                                                  'username': user['username']})

                # we don't update the rec time on a test run...
                if not self.config.getConfig('TESTRUN'):
                    # Note: we call utcnow() to store the closest last recommendation
                    # time in the database.  If some slack is needed with regards to
                    # posting time, we can instead alter the scheduling.
                    dbcursor.execute(setLastrecQuery, {'rectime': datetime.utcnow(),
                                                       'lang': lang,
                                                       'username': user['username']})
                    # update count of number of recommendations for this user
                    dbcursor.execute(incRecCountQuery, {'lang': lang,
                                                        'user': user['username']})
                    
                dbconn.commit()
                # post to stdout saying yay!
                logging.info(u"Posted recs to User:{username}".format(username=user['username']))

        # Update the status of busyness to pretty unbusy...
        dbcursor.execute(updateStatusTableQuery, {'status': 0,
                                                  'lang': lang})
        dbconn.commit()

        # disconnect from database
        myDb.disconnect()

        # ok, done
        return
