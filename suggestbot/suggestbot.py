#!/usr/bin/env python
# -*- coding: utf-8  -*-
'''
Library with SuggestBot functionality

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
'''

# Requires:
#   pywikibot (core)

from __future__ import with_statement

__version__ = "$Id$"

import sys
import codecs
import re
import time
import xmlrpc.client
import logging

import pywikibot
import mwparserfromhell as mwp

from datetime import datetime, timedelta
from random import shuffle

from suggestbot import config
from suggestbot import db

# FIXME: use RegularUser object from RegularUserUpdater
# since that has all the parameters

class PageNotSavedError(Exception):
    '''Posting suggestions failed.'''
    pass

class NotLoggedInError(Exception):
    '''Bot is not correctly logged in'''
    pass

class SuggestBot:
    def __init__(self, recPort=None, nRecs=3,
                 postDelay=30, maxRetries=3, testRun=False,
                 lang=None):

        config.rec_server = "localhost"
        if recPort is not None:
            config.main_server_port = recPort
        config.nrecs = nRecs
        config.post_delay = postDelay
        config.post_retries = maxRetries

        config.testrun = testRun
        config.connect_timeout = 5.0 # 5 second timeout
        config.connect_retries = 20 # num retries for rec server connections

        if lang:
            config.wp_langcode = lang

        # config our site, note that this also logs us in
        self.site = pywikibot.Site(config.wp_langcode)

    def login(self):
        # instantiating a site object logs us in...
        self.site = pywikibot.Site(config.wp_langcode)
        self.site.login()
        # then we can simply check if we're logged in
        return(self.isLoggedIn())

    def durrdurr(self):
        '''http://drmcninja.com/archives/comic/14p28'''
        return(self.login())

    def pthooey(self):
        return(self.logout())
    
    def logout(self):
        '''Logs the bot out, if we're logged in.'''
        if self.site.user():
            self.loginMgr.logout()

    def isLoggedIn(self):
        '''Returns username if we're logged in, None otherwise.'''
        return(self.site.user())

    def getRecs(self, username="", userGroup="suggest", itemEnd=True,
                filterMinor=False, filterReverts=False, useUserlinks=False,
                isRequest=False, requestId=-1, interestPages=None):
        '''Connect to the main recommendation server and get recommendations
           for the given user.  If successful, a list of recommendations are
           returned.

           @param username: The name of the user we are recommending articles to
           @type username: str

           @param userGroup: Which group the user belongs to
           @type userGroup: str

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

        recServer = xmlrpc.client.ServerProxy("http://{hostname}:{port}".format(hostname=config.main_server_hostname,
                                                                            port=config.main_server_hostport),
                                          allow_none=True)

        # Server expects language, username, and request type as three parameters,
        # and then the rest as a dictionary.  Prepare said dictionary.
        item_end = "first"
        if itemEnd:
            item_end = "last"
        recParameters = {'articles': [],
                         'item-end': item_end,
                         'filter-minor': filterMinor,
                         'filter-unimportant': filterReverts,
                         'use-userpage': useUserlinks,
                         'nrecs': config.nrecs,
                         'request-id': requestId,
                         'request-type': 'regular'
                         }

        # Is this a one-time request, or a regular user?
        if isRequest:
            recParameters['request-type'] = 'single-request'

            # If this is a request and the user has a list of pages they've expressed interest in...
            if interestPages \
               and (len(interestPages) > 0):
                recParameters['articles'] = interestPages

        recs = {}
        try :
            recs= recServer.recommend(config.wp_langcode,
                                      username,
                                      recParameters)
        except xmlrpc.client.Fault as e:
            logging.error("something went wrong when trying to get suggestions:")
            logging.error("{}".format(e))

        return(recs)

    def create_invoke(self, recs, module_name, method_name,
                      cat_order=[], add_include_clause=False):
        '''
        Construct the appropriate Lua-module invoke call, invoking the
        given module & method, passing in the given set of recommendations.

        :param recs: The recommendations to pass in as parameters
        :type recs: dict

        :param module_name: Name of the module to invoke
        :type module_name: str

        :param method_name: Name of the publicly exposed method to invoke
        :type method_name: str

        :param cat_order: List of category names in the order they should
                          be passed in as parameters.  The articles will
                          be sorted in order of categories first, if this
                          list is something else than empty.  Note: this
                          list _must_ contain all categories used in the
                          accompanying recommendations.

        :param add_include_clause: Should an "includeonly" clause that
                                   passes an "is_included" parameter to
                                   the invoke call be used? Allows the module
                                   to know whether it is displayed on a page
                                   that is transcluded.
        :type add_include_clause: bool
        '''

        for rec_title, rec_data in recs.items():
            ## Lowercase category and strip away numbers
            rec_data['cat'] = rec_data['cat'].lower()
            rec_data['cat'] = re.sub(r'(\w+)\d+', r'\1', rec_data['cat'])
            ## Capitalise assessment rating, use 'NA' if no rating
            if rec_data['qual'] in ['NOCLASS', 'NA']:
                rec_data['qual'] = 'NA'
            else:
                rec_data['qual'] = rec_data['qual'].capitalize()
        
        ## Note: format needs quadruple brackets
        invoke_text = '{{{{#invoke:{module}|{method}'.format(module=module_name,
                                                             method=method_name)
        if add_include_clause:
            invoke_text += '<includeonly>|is_included=yes</includeonly>\n'
        
        if cat_order:
            ## Sort the recommendations based on categories
            try:
                recs = sorted(recs,
                              lambda rec: cat_order.index(rec[1]['cat']))
            except ValueError:
                ## We're probably here because 'cat' wasn't in cat_order...
                pass

        if not isinstance(recs, list):
            recs = recs.items()

        for rec_title, rec_data in recs:
            ## Example line of invoke parameters for a recommendation
            ## '|source|Fender Showmaster|30|Stub|Stub|content,headings,links,sources'
            
            ## Was popcount calculated? IF not, set it to an empty string,
            ## {{formatnum:}} seems to handle that nicely.
            if not 'popcount' in rec_data \
               or rec_data['popcount'] < 0:
                rec_data['popcount'] = ''

            invoke_text += '|{cat}|{title}|{views}|{rating}|{prediction}|{tasks}\n'.format(
                cat=rec_data['cat'],
                title=rec_title,
                views=rec_data['popcount'],
                rating=rec_data['qual'],
                prediction=rec_data['predclass'],
                ## Loop through tasks and split them, keeping the ones where
                ## task is set to 'yes', but translate them into the new
                ## keywords, then join as a comma-separated list.
                tasks=','.join([config.human_tasks[task] for (task, verdict) in \
                          (w.split(':') for w in rec_data['work']) \
                          if verdict == 'yes'])
            )
            
        ## Finish off with some closing brackets
        invoke_text += '}}'
        return(invoke_text)
            
    def createRecsPage(self, recs, recTemplate=None, userGroup=None):
        """
        :param recs Recommendations for this user in the right order needed
                    for substitution into our template.
        :type recs list of dicts
        :param recTemplate Relative address on Wikipedia to the template we use for
                           substitution when posting recommendations.  If 'None',
                           the request template found in Config.py for the language
                           defined in config.pm is used (except when lang is defined).
        :type recTemplate str or None

        :param userGroup: name of the (experiment) group the user is in
        :type userGroup: str
        """

        # FIXME: Should we send the user a message if we couldn't do anything?
        if not recs:
            return(None)

        # Create the parameter string of "|CAT?=ITEM" where ? is the order.
        paramString = ""
        for (recTitle, recData) in recs.items():
            paramString = "{params}|{category}{order}={title}".format(params=paramString,
                                                                       category=recData['cat'],
                                                                       order=recData['rank'],
                                                                       title=recTitle)

        # On English Wikipedia, we have popularity & quality information available,
        # so add that.
        if config.wp_langcode == 'en':
            for (recTitle, recData) in recs.items():
                # Was popcount calculated?  If not, set it to an empty string,
                # {{formatnum:}} appears to handle that nicely.
                if not 'popcount' in recData \
                        or recData['popcount'] < 0:
                    recData['popcount'] = ""

                # Add quality data
                qual = recData['pred'].lower()
                qualSort = 1.0
                if qual == u'high':
                    qualSort = 3.0
                elif qual == 'medium':
                    qualSort = 2.0
                if recData['pred']: # did we get a prediction?
                    assessedClass = "Unassessed"
                    if recData['qual'] != "NOCLASS":
                        # Set, and capitalise, unless "FA" or "GA"
                        assessedClass = recData['qual']
                        if assessedClass not in ["FA", "GA", "NA"]:
                            assessedClass = assessedClass.capitalize()
                    # Turn into quality file link w/assessment and prediction,
                    # using quality map in configuration.
                    predClass = recData['predclass']
                    qual = config.quality_map[qual].format(rectitle=recTitle, assessedclass=assessedClass, predclass=predClass)

                # Add both popularity and quality parameters to paramString
                paramString = "{params}|POP{category}{order}={popcount}|QUAL{category}{order}={qualcode}|QUALSORT{category}{order}={qualsort}".format(params=paramString, category=recData['cat'], order=recData['rank'], popcount=recData['popcount'], qualcode=qual, qualsort=qualSort)

                # NOTE: for merge tasks, link to the merge discussion directly?
                #       No, we link to the talk page, where the merge discussion
                #       is likely found, or easy to find.

                # Note: consider also flagging them if "length" is "maybe"?
                # only flag "headings" and "links" if not flagging length
                # Set to True and uncomment if-block if you want that.
                skipLinksAndHeadings = False
                # if 'length:no' in recData['work']:
                #     skipLinksAndHeadings = False
                
                if not 'work' in recData \
                        or recData['work'] is None:
                    recData['work'] = []

                # Make set of all tasks
                all_tasks = set(config.human_tasks.values())

                # For each of the tasks...
                for task in recData['work']:
                    # print "task=", task
                    # split into task and yes/no/maybe
                    (task, verdict) = task.split(':')
                    # NOTE: Based on beta testing, we skip marking maybe-tasks
                    #       with a ?
                    if verdict == 'maybe':
                        verdict = 'no'
                    # map into human-readable form
                    task = config.human_tasks[task]
                    # should we skip headings and links?
                    if task in ["headings", "links"] \
                            and skipLinksAndHeadings:
                        verdict = "no"
                    # make key into configuration's TASK_MAP
                    mapKey = '{task}-{verdict}'.format(task=task, verdict=verdict)
                    # put it all together...
                    paramString = "{params}|{task}{category}{order}={mapping}".format(params=paramString, task=task.upper(), category=recData['cat'], order=recData['rank'], mapping=config.task_map[mapKey].format(rectitle=recTitle))
                    # remove this task from the set of all tasks
                    all_tasks.remove(task)

                # Go through all remaining tasks and add them as parameters,
                # building a key into config's TASK_MAP as before
                for task in all_tasks:
                    task_key = '{task}-no'.format(task=task)
                    # Add the parameter to not show any task needed
                    paramString = "{params}|{task}{category}{order}={mapping}".format(
                        params=paramString, task=task.upper(), category=recData['cat'],
                        order=recData['rank'], mapping=config.task_map[task_key])

        # Now create the subst template which refers to
        # our self-defined message template, with the created string of parameters
        if not recTemplate:
            lang = config.wp_langcode
            recTemplate = config.templates[lang]['request']

        # Add in the template and parameters (note escaping of '{' with '{{')
        recString = "{{{{subst:{template}{params}}}}} -- ~~~~".format(
            template=recTemplate,
            params=paramString)
        return(recString)

    # FIXME: get a unit test case of the recommendation post thingamajig
    # replacing content and stuff.

    def addReplaceRecMessage(self, pageSource="", recMsg="",
                             replace=False):
        """
        Adds or replaces a message with article recommendations to the given
        page source.

        @param pageSource: source wikitext of the page
        @type pageSource: str

        @param recMsg: wikitext of the article recommendations
        @type recMsg: str

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

        # Due to performance issues with Template:Ntsh, replace any occurrences
        # with Template:Hs (this only applies to enwiki).  Based on what I can find,
        # on a page that we're likely to post to (User and User talk namespaces), we're
        # the only one using it.
        lang = config.wp_langcode
        if lang == 'en':
            parsedCode = mwp.parse(pageSource, skip_style_tags=True)
            templates = parsedCode.filter_templates(recursive=True)
            for template in templates:
                if template.name.matches('Ntsh'):
                    template.name = 'Hs'
                    
            # Replace current wikitext with new code that uses Template:Hs
            pageSource = str(parsedCode)

        # Normal replacement or not replacement of suggestion post
        if not replace:
            newPageSource = "{current}\n\n{recs}".format(current=pageSource,
                                                          recs=recMsg)
        else:
            # We're replacing, do some magic to find the last rec and
            # replace from there up until the next non-rec header (or EOF)

            # Compile rec message header regex, and all sub-section regexes.
            recHeaderRe = re.compile(config.rec_header_re[lang], re.U)
            subHeaderRegs = []
            for regEx in config.sub_header_re[lang]:
                subHeaderRegs.append(re.compile(regEx, re.U))

            # Parse the page contents
            parsedCode = mwp.parse(pageSource, skip_style_tags=True)

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
                newPageSource = "{current}\n\n{recs}".format(current=pageSource,
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
                newPageSource = "{beforeMsg}{recMsg}\n\n{afterMsg}".format(beforeMsg="".join([str(node) for node in parsedCode.nodes[:recMsgStartIdx]]),
                                                                           recMsg=recMsg,
                                                                           afterMsg="".join([str(node) for node in parsedCode.nodes[recMsgEndIdx:]]))

        return(newPageSource)

    def save_page(self, page, content, edit_comment,
                  watch=True, minor=False, force=False):
        '''
        Save the given page with new content using the given
        edit comment.  Due to issues with large pages the save
        is only attempted once, if it fails with a timeout error
        we check the page's contribution history.

        @param page: Page to save to
        @type page: pywikibot.Page

        @param content: New content for the page
        @type content: str

        @param edit_comment: Edit comment to use when saving
        @type edit_comment: str

        @param watch: Add the page to our watchlist?
        @type watch: bool

        @param minor: Flag the edit as a minor edit?
        @type minor: bool

        @param force: Force the edit, ignoring {{nobots}} and such?
        @type force: bool
        '''
        try:
            # Store old config setting, set it to 0 so we only get one
            # save-attempt, save, then reset max_retries
            max_retries = pywikibot.config.max_retries
            pywikibot.config.max_retries = 0
            page.text = content
            page.save(comment=edit_comment,
                      watch=watch, minor=minor, force=force)
            pywikibot.config.max_retries = max_retries
        except pywikibot.exceptions.EditConflict:
            logging.error("Posting recommendations to {title} failed, edit conflict.".format(title=page.title()))
            raise PageNotSavedError

        except pywikibot.exceptions.PageNotSaved as e:
            # Wait a bit, then test if the edit actually got saved
            logging.warning("Failed to post recommendations to {title} on first try, waiting 60 seconds to check edit history.".format(title=page.title()))
            time.sleep(60)
            # Check article's edit history, did SuggestBot recently save?
            # ver. hist. is list of tuples: (revid, timestamp, user, comment)
            last_edits = page.getVersionHistory(step=10, total=10)
            sbot_username = self.site.user()
            sbot_edited = False # did we edit?
            for edit_info in last_edits:
                if edit_info[2] != sbot_username:
                    continue

                timediff = datetime.utcnow() - edit_info[1]
                if timediff.seconds < 300: # last 5 minutes
                    sbot_edited = sbot_edited or True
                
            if not sbot_edited:
                logging.error("Failed posting recommendations to {title}.\nError: {emsg}\n".format(title=page.title(), emsg=e))
                raise PageNotSavedError

        # ok, all done
        return

    def post_warning(self, page_source, is_talk=True):
        '''
        We want to post to the given page, but it is too large. Post either
        a talk page suggestion or SuggestBot-specific suggestion about
        archiving the page.

        :param page: The page we're posting to
        :type page: pywikibot.Page

        :param is_talk: Is it a talk page?
        :type is_talk: bool
        '''

        message = config.page_warning
        if is_talk:
            message = config.talkpage_warning

        return("{old_source}\n\n{{{{subst:{message}}}}}".format(
            old_source=page_source, message=message))

    def postRecommendations(self, username="", recMsg=None,
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
            return(False)

        # make a user object
        recUser = pywikibot.User(self.site, username)

        # check if the user is blocked
        if recUser.isBlocked():
            logging.warnng("user {username} is blocked, posting aborted.".format(username=username).encode('utf-8'))
            return(False)

        # get the user's talk page, or a preferred page if defined
        if page:
            destPage = pywikibot.Page(self.site, page)
        else:
            destPage = recUser.getUserTalkPage()

        try:
            pageSource = destPage.get()
        except pywikibot.exceptions.NoPage:
            logging.warning("Destination page {title} doesn't exist, will be created.".format(title=destPage.title()))
            pageSource = ""
        except pywikibot.exceptions.IsRedirectPage:
            logging.warning("Destination page {title} is a redirect, posting cancelled.".format(title=destPage.title()))
            return(False)

        # What language are we posting to?
        lang = config.wp_langcode

        ## Posting to large pages can be problematic, and at least enwiki has
        ## a guideline against large talk pages.
        page_length = len(pageSource.encode('utf-8'))
        if (page and config.page_limit[lang] and \
            page_length > 1024*config.page_limit[lang]) \
            or (config.talkpage_limit[lang] and \
                page_length > 1024*config.talkpage_limit[lang]):
            logging.warning("destination page {title} is too large for saving, {n:,} bytes, posting cancelled!".format(title=destPage.title(), n=page_length))
            return(False)

        # Create new page source by adding or replacing suggestions
        newPageSource = self.addReplaceRecMessage(pageSource=pageSource,
                                                  recMsg=recMsg,
                                                  replace=replace)

        # if testing, print the proposed userpage
        if config.testrun:
            print("SuggestBot is doing a test run. Here's the new page:")
            print(newPageSource)
        else:
            # Make an edit to save the new page contents...
            try:
                self.save_page(destPage, newPageSource,
                               config.edit_comment[lang],
                               force=force)
            except PageNotSavedError:
                return(False)

        # OK, done
        return(True)
        
    def recommend(self, username, userGroup="suggest", itemEnd=True,
                  filterMinor=True, filterReverts=True, useUserlinks=False,
                  recTemplate=None, force=False, page=None, replace=False,
                  isRequest=False):
        '''Get and post recommendations to the specific user based on the set
           of options given (see getRecs() for specifics).

           @param username: What user are we recommending articles to?
           @type username: str

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
            logging.error("must supply username to do recommendations")
            return(False)

        # create user object
        # FIXME: instead of passing usernames around, we can pass this user object
        # around...
        recUser = pywikibot.User(self.site, username)

        # Check if the user is blocked.  Since that will aport posting, there's
        # no need to spend time generating recommendations.
        if recUser.isBlocked():
            sys.stderr.write("SBot Warning: User:{username} is blocked, posting aborted.\n".format(username=recUser.username).encode('utf-8'))
            return(False)

        # What language are we posting to?
        lang = config.wp_langcode

        # Test if the destination page is too large, as we otherwise struggle
        # with posting, getting timeouts.
        if page:
            destPage = pywikibot.Page(self.site, page)
        else:
            destPage = recUser.getUserTalkPage()

        try:
            pageSource = destPage.get()
            page_length = len(pageSource.encode('utf-8'))
            if (page and config.page_limit[lang] and \
                page_length > 1024*config.page_limit[lang]) \
                or (config.talkpage_limit[lang] and \
                    page_length > 1024*config.talkpage_limit[lang]):
                logging.warning("destination page {title} is too large for saving, {n:,} bytes, posting cancelled!".format(title=destPage.title(), n=page_length))
                return(False)

            # Create new page source by adding or replacing suggestions
            newPageSource = self.addReplaceRecMessage(pageSource=pageSource,
                                                      recMsg=recMsg,
                                                      replace=replace)
        except pywikibot.exceptions.IsRedirectPage:
            logging.warning("destination page {title} is a redirect, posting cancelled".format(title=destPage.title()))
            return(False)
        except pywikibot.exceptions.NoPage:
            pass

        # if testing, print the proposed userpage
        if config.testrun:
            print("SuggestBot is doing a test run. Here's the new page:")
            print(newPageSource)
        else:
            # Make an edit to save the new page contents...
            try:
                self.save_page(destPage, newPageSource,
                               config.edit_comment[lang],
                               force=force)
            except PageNotSavedError:
                return(False)

        # OK, done
        return(True)
        
    def recommend(self, username, userGroup="suggest", itemEnd=True,
                  filterMinor=True, filterReverts=True, useUserlinks=False,
                  recTemplate=None, force=False, page=None, replace=False,
                  isRequest=False):
        '''Get and post recommendations to the specific user based on the set
           of options given (see getRecs() for specifics).

           @param username: What user are we recommending articles to?
           @type username: str

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
            logging.error("must supply username to do recommendations")
            return(False)

        # create user object
        # FIXME: instead of passing usernames around, we can pass this user object
        # around...
        recUser = pywikibot.User(self.site, username)

        # Check if the user is blocked.  Since that will aport posting, there's
        # no need to spend time generating recommendations.
        if recUser.isBlocked():
            logging.warning("User:{username} is blocked, posting aborted".format(username=recUser.username))
            return(False)

        # What language are we posting to?
        lang = config.wp_langcode

        # Test if the destination page is too large, as we otherwise struggle
        # with posting, getting timeouts.
        if page:
            destPage = pywikibot.Page(self.site, page)
        else:
            destPage = recUser.getUserTalkPage()

        try:
            pageSource = destPage.get()
            page_length = len(pageSource.encode('utf-8'))
            if (page and config.page_limit[lang] and \
                page_length > 1024*config.page_limit[lang]) \
                or (config.talkpage_limit[lang] and \
                    page_length > 1024*config.talkpage_limit[lang]):
                logging.warning("destination page {title} is too large for saving, {n:,} bytes, posting cancelled!".format(title=destPage.title(), n=page_length))
                return(False)
        except pywikibot.exceptions.IsRedirectPage:
            logging.warning("destination page {title} is a redirect, posting cancelled".format(title=destPage.title()))
            return(False)
        except pywikibot.exceptions.NoPage:
            pass

        # get recommendations
        userRecs = self.getRecs(username=username, userGroup=userGroup,
                                itemEnd=itemEnd, filterMinor=filterMinor,
                                filterReverts=filterReverts, useUserlinks=useUserlinks,
                                isRequest=isRequest)
        # if none, post?
        if not "recs" in userRecs \
                or not userRecs["recs"]:
            logging.error("SBot Warning: Got no recommendations for User:{username}\n".format(username=recUser.username))
            return(False)
        # else, create recs message
        recMsg = self.createRecsPage(userRecs["recs"], recTemplate=recTemplate,
                                     userGroup=userGroup)
        # update userpage (test for now)
        return(self.postRecommendations(username=username, recMsg=recMsg,
                                        page=page, force=force, replace=replace))

    def stopme(self):
        pywikibot.stopme()

    def getPageLinks(self, pageTitles=None, namespaces=None):
        '''Get all links from the given pages restricted to the given namespaces'''
        if not pageTitles:
            logging.warning("getPageLinks called with no page titles.")
            return(None)

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
                # json_data = query.GetData(params, self.site)
                
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
                for (page, page_data) in all_pages.items():
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

        return(linkedPages)

    def getBackLinks(self, pageTitles=None, namespaces=None):
        '''Get all backlinks from the given pages restricted to the given namespaces'''
        if not pageTitles:
            logging.warning("getBackLinks called with no page titles.")
            return(None)

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
                if linkedpage.namespace in namespaces:
                    linkedPages[title].append(linkedpage.title)

        return(linkedPages)
