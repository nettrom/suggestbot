#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Library for handling one-time requests for suggestions from users by
fetching transcluded templates.

Copyright (C) 2005-2015 SuggestBot Dev Group

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

__version__ = "$Id$";

import os
import re
import sys
import time
import signal
import logging

from datetime import datetime

from difflib import Differ

import pywikibot
from pywikibot.pagegenerators import PagesFromTitlesGenerator

import mwparserfromhell as mwp

# FIXME: wouldn't it be better to be able to say:
# from SuggestBot import Config (as SBConfig)?
# from SuggestBot import Database as SBDatabase
# from SuggestBot import SuggestBot
# or something like that, so there's one config module, one database module,
# and one bot module?
# Or maybe say 'import SuggestBot; dbConn = SuggestBot.getDatabaseConnection();"?
# We'll have a suggestbot package, which has a database and a config
# sub-package, and some class methods and stuff...

import request
from suggestbot import config
from suggestbot import db
from suggestbot import SuggestBot, PageNotSavedError

# FIXME: figure out a way to store pages with issues, e.g. {{nobots}}?
# and then ignore further requests from those...?

class DBConnectionError(Exception):
    """Failed to connect/disconnect to/from the SuggestBot database."""
    pass;

class RequestTemplateHandler:
    def __init__(self, lang='en',
                 templates={"User:SuggestBot/suggest": []},
                 ignoreList=[], verbose=False):
        """
        Initialise an object that will handle one-time requests that are added to
        a user-page.

        @param lang: What language Wikipedia we are working on
        @type lang: unicode

        @param templates: Dictionary where each key is the title of a main template
                          that we'll look for, and its corresponding value is a list
                          of synonyms (through redirects).
        @type templates: dict (unicode to list of unicode)

        @param ignoreList: List of page titles we'll ignore when looking for references
        @type ignorelist: list (of unicode strings)

        @param verbose: Write informational output?
        @type verbose: bool
        """

        self.lang = lang
        self.templates = templates
        self.db = db.SuggestBotDatabase()
        self.site = pywikibot.Site(self.lang)

        # For each defined template, create a set of templates unicode strings
        # we'll be looking for.
        self.template_pages = {}
        for (template, synonyms) in self.templates.items():
            self.template_pages[template] = set([template.lower()] + [s.lower() for s in synonyms])

        self.ignoreList = ignoreList
        self.verbose = verbose

        # Compile the regular expressions used to match section headings
        # in the language this script handles.
        self.reqHeaderReList = [re.compile(regex) for regex in config.request_head_re[self.lang]]

        self.shutdown = False # time to shut down?

    def handleSignal(self, signum, stack):
        '''
        Handle incoming signals, specifically SIGUSR1, which we'll use
        to quit gracefully.
        '''
        self.shutdown = True;
        return;

    def stopme(self):
        '''
        Simply a call to pywikibot.stopme(), and usually
        used in the finally section of a try/finally clause.
        '''
        pywikibot.stopme();

    def daemonLoop(self, bot=None):
        """
        Loop forever, handling requests as they come in, otherwise sleeping.
        """
        # Set up a signal handler for SIGUSR1
        signal.signal(signal.SIGUSR1, self.handleSignal);

        logging.info("OK, ready to run for as long as possible... running".encode('utf-8'));
        
        while not self.shutdown:
            startTime = datetime.utcnow()
            # print('It is {timestamp}, checking {lang}-wiki'.format(timestamp=startTime.strftime('%Y-%m-%d %H:%M:%S'), lang=self.lang))

            try:
                if not self.db.connect():
                    raise DBConnectionError
                # Trying to fix issue with tokens by not keeping the site
                # object around for too long
                self.site = pywikibot.Site(self.lang)
                recRequests = self.getRequests()
                for (page, pageData) in recRequests.items():
                    self.processSingleRequest(userPage=page,
                                              interestPages=pageData['articles'],
                                              knownTemplates=pageData['templates'],
                                              bot=bot)
                if not self.db.disconnect():
                    raise DBConnectionError
            except pywikibot.data.api.TimeoutError:
                logging.warning("API TimeoutError occurred, will try again after sleeping")
                startTime = datetime.utcnow() # reset the clock so we'll sleep for a while
            except request.RequestUpdateError:
                logging.warning("Error when updating data for a request in the database")
                startTime = datetime.utcnow() # reset the clock so we'll sleep for a while
            except DBConnectionError:
                logging.error("failed to (dis)connect the database")
                startTime = datetime.utcnow() # reset the clock so we'll sleep for a while

            timeDiff = datetime.utcnow() - startTime
            delay = config.suggest_req_poll - timeDiff.seconds
            if delay > 0:
                # logging.info("sleeping for {0} seconds".format(delay));
                time.sleep(delay)

            # ok, loop ends...

        # OK,done
        return

    def process_parameter(self, parameter):
        '''
        Process the given template parameter supplied to the request template
        and return a set of articles referred to by the parameter.

        @param parameter: the parameter
        @type parameter: unicode
        '''

        # Regular expression to match parameters on the form "category1= ..."
        # and so on, localised to the language we're talking
        catparam_regex = re.compile(r"\s*{catparam}\d*=".format(
            catparam=config.th_category[self.lang]), re.I)

        # Suffix to use when using categories to fetch pages of interest
        catname_suffix = config.wikiproject_suffix[self.lang]

        # Titles as a set to automatically ignore duplicates
        listed_titles = set()

        # All articles we've found (stored as pywikibot.Page objects)
        found_articles = set()

        # Support "category=" parameter by removing the
        # keyword and adding the category namespace name
        # to the title.
        if catparam_regex.match(parameter):
            parameter = self.site.category_namespace() \
                + ":" + cataparam_regex.sub("", parameter)
            listed_titles.add(parameter)
            
            # Support category suffixes by adding that as well
            if catname_suffix:
                listed_titles.add('{param}{suffix}'.format(
                        param=parameter, 
                        suffix=catname_suffix))
        else:
            # Just this one title
            listed_titles.add(parameter)

        try:
            # Turn title set into a list and process articles/categories
            seed_pages = PagesFromTitlesGenerator(list(listed_titles),
                                                  site=self.site)
            for seedpage in seed_pages:
                if not seedpage.exists():
                    logging.warning("listed {page} does not exist".format(page=seedpage.title()))
                    continue

                if not seedpage.isCategory():
                    if seedpage.namespace() != 0:
                        logging.warning("listed page {page} not in ns 0".format(page=seedpage.title()))
                    elif seedpage.isRedirectPage():
                        try:
                            found_articles.add(seedpage.getRedirectTarget())
                        except pywikibot.exceptions.NoPage:
                            logging.warning("listed {page} redirects to a non-existent page".format(page=seedpage.title()))
                    else:
                        # Everything looks OK, add the page
                        found_articles.add(seedpage);
                else:
                    # We use the site's categorymembers() method
                    # to get articles and talk pages, ordered by
                    # when they were added to the category.
                    # For large categories we should thereby get
                    # the oldest and hopefully most developed
                    # articles in our seed set of articles.
                    if seedpage.isCategoryRedirect():
                        try:
                            seedpage = seedpage.getCategoryRedirectTarget()
                        except pywikibot.exceptions.NoPage:
                            logging.warning("listed {title} redirects to a non-existent category".format(title=seedpage.title()))
                            continue # skip this category

                    cat_articles = set();
                    for catmember in self.site.categorymembers(seedpage,
                                                               namespaces=[0,1],
                                                               sortby="timestamp",
                                                               reverse=True):
                        if catmember.namespace() == 0:
                            cat_articles.add(catmember)
                        else:
                            cat_articles.add(catmember.toggleTalkPage())
                        if len(cat_articles) >= 256:
                            break

                    # Add the category's articles to our result
                    found_articles = found_articles.union(cat_articles)
        except pywikibot.Error:
            logging.warning("Failed to instantiate and iterate over list generator, or something else went wrong")

        # okay, done
        return found_articles

    def get_category_pages(self, cat_page):
        '''
        Grab up to 128 articles from the given category and return them as a set.
        If the category contains talk pages, the corresponding articles are added
        instead.  The category will be traversed in reverse chronological order
        by setting the `cmsort` parameter to `timestamp`, ref
        https://www.mediawiki.org/wiki/API:Categorymembers
        '''

        cat_articles = set()
        if cat_page.isCategoryRedirect():
            try:
                cat_page = cat_page.getCategoryRedirectTarget()
            except pywikibot.exceptions.NoPage:
                logging.warning("listed {title} redirects to a non-existent category".format(title=seedpage.title()))
                return cat_articles

        ## Grab category members from Main and Talk, reverse sort by
        ## timestamp, a max of 128 pages.
        for catmember in self.site.categorymembers(cat_page,
                                                   namespaces=[0,1],
                                                   sortby="timestamp",
                                                   reverse=True,
                                                   total=128):
            if catmember.namespace() == 0:
                cat_articles.add(catmember)
            else:
                cat_articles.add(catmember.toggleTalkPage())

        # ok, done
        return(cat_articles)

    def getRequests(self):
        """
        Returns a dictionary with referencing pages (as pywikbot.Page) as keys,
        where values are a set of pywikibot.Page objects found by expecting
        template parameters to either be a page title, a category title,
        or key-value pairs "category[1,2,3]="
        {{User:Suggestbot/request|Category:Title|Title1|Title2}}
        """
        requests={}

        # Regular expression to match parameters on the form "category1= ..."
        # and so on, localised to the language we're talking
        catParamRegex = re.compile(r"\s*{catparam}\d*=".format(
            catparam=config.th_category[self.lang]), re.I)

        # Suffix to use when using categories to fetch pages of interest
        catname_suffix = config.wikiproject_suffix[self.lang]

        # for each template we know about...
        for (temp_title, alltitles_set) in self.template_pages.items():
            # iterate through all pages that transclude the template
            # (limited to User and User talk namespaces)
            template = pywikibot.Page(self.site, temp_title)
            for page in template.embeddedin(filter_redirects=False,
                                            namespaces=[2,3], content=True):
                if page.title() in self.ignoreList:
                    continue; # ignore this page

                # If the page is locked, SuggestBot can't edit, so skip it
                if not page.canBeEdited():
                    logging.info('cannot edit {0} (page locked?), skipping'.format(page.title()))
                    continue

                logging.info("now processing request on page {page} ...".format(page=page.title()).encode('utf-8'));

                # Articles the user has listed, and templates we know about
                listedArticles = set();
                knownTemplates = set();

                parsed_text = mwp.parse(page.get())
                for template in parsed_text.filter_templates(recursive=True):
                    template_name = unicode(template.name).strip().lower()
                    if template_name not in alltitles_set:
                        continue
                    
                    knownTemplates.add(template_name)
                    for parameter in template.params:
                        if not unicode(parameter).strip():
                            continue

                        listedArticles |= self.process_parameter(unicode(parameter.value))

                # Done processing this page, add found templates and
                # articles to the set of known things.
                if not page in requests:
                    requests[page] = {'articles': set(),
                                      'templates': set()}

                requests[page]['articles'] |= listedArticles
                requests[page]['templates'] |= knownTemplates

        return requests;
                
    def removeTemplateFromSource(self, sourceText="",
                                 knownTemplates=[]):
        """
        Return a version of the source wikitext, with the known
        templates and potentially other content removed.

        @param sourceText: wikitext from which we'll remove templates/content
        @type sourceText: unicode

        @param knownTemplates: names of known templates to be removed
        @type knownTemplates: list (of unicode strings)
        """
        # 1: parse the text, look for templates
        parsedCode = mwp.parse(sourceText);
        templates = parsedCode.filter_templates(recursive=True);

        for template in templates:
            # Note: mwparserfromhell supplies template name w/newlines, thus strip()
            if template.name.strip().lower() in knownTemplates:
                parsedCode.remove(template);

        # Test if any of the seen templates are in the Teahouse experiment,
        # and if not, return early.
        teahouseTemplates = set(temp.lower() for temp in config.teahouse_templates[self.lang]);
        intersect = set(knownTemplates).intersection(teahouseTemplates);

        if not intersect:
            return unicode(parsedCode);

        # 2: look for section headings that we need to remove
        # if we find a match, delete everything from that point on
        # onto we either find a new heading, or the end of the page...
        doDelete = False;
        i = 0;
        while i < len(parsedCode.nodes):
            node = parsedCode.nodes[i];
            # print "node=", node;
            # is heading?
            if isinstance(node, mwp.nodes.heading.Heading):
                # Stop deleting
                if doDelete:
                    doDelete = False;

                for regex in self.reqHeaderReList:
                    # if it matches, start deleting
                    if regex.match(node.strip()):
                        doDelete = True;

            if doDelete:
                # print "deleting...";
                del(parsedCode.nodes[i]);
            else:
                i += 1;

        return unicode(parsedCode);

    def processSingleRequest(self, userPage=None, interestPages=None,
                             knownTemplates=None, bot=None):
        """
        Process this user's request for suggestions.  Will ask for recommendations
        based on pages of interest if they were listed, otherwise SuggestBot will
        use the user's edit history as usual.  The recommendations are saved to
        a given userpage (or user talk page) and the request template deleted
        in the same operation.

        @param userPage: User page, or user talk page, or sub-page in userspace,
                         for the user we will be sending suggestions to
        @type userPage: pywikibot.Page

        @param interestPages: All pages the user has expressed interest in
        @type interestPages: pywikibot.Page iterator

        @param knownTemplates: The templates we know about that were
                               transcluded on the given userPage
        @type knownTemplates: list (of unicode)

        @param bot: The SuggestBot that will get and post the recommendations
        @type bot: SuggestBot.SuggestBot
        """
        # 1: determine the username, and figure out where we're sending recs
        # (code is similar to the one handling regular users in SuggestBot.py)
        logging.info("processing request from page {page}".format(page=userPage.title()).encode('utf-8'));

        # Regular expression for splitting into username + subpage-name.
        subPageSplitRe = re.compile(r'(?P<username>[^/]+)(?P<subname>/.*)');

        pageTitle = userPage.title(withNamespace=False, withSection=False);
        # split the pageTitle on first "/" in case it's a subpage.
        subPageTitle = None;
        username = '';
        matchObj = subPageSplitRe.match(pageTitle);
        if matchObj:
            # we have a subpage
            subPageTitle = userPage.title();
            username = matchObj.group('username');

            logging.info("found subpage {title} of user {username}".format(title=matchObj.group('subname'), username=username).encode('utf-8'));
        else:
            username = pageTitle;

        # Create a user object, and check if this user is blocked
        recUser = pywikibot.User(self.site, username);

        # FIXME: delete the template from the user page if the user is blocked?
        # We'll see how much of a problem blocked users and users adding them not being
        # themselves, and then consider simply deleting it.
        if recUser.isBlocked():
            logging.warning("User:{username} is blocked, posting aborted".format(username=recUser.username).encode('utf-8'));
            return False;

        # check the page history to find the first revision with the template,
        # and check who added it.  If it's not the same user, ignore the request.
        # NOTE: this stores the username and text of the "previous" revision because
        # we move backwards in history (since we're then likely to diff fewer revisions).
        pageDiffer = Differ();

        maxRevs = 25;
        numSeenRevs = 0; # number of revisions we inspected
        prevRevisionText = ""; # default previous revision is empty
        prevRevisionUser = ""; # name of the user who potentially added the template
        
        # Switch to lowercase for case-insensitive matching
        knownTemplateTitles = set([temp.lower() \
                                   for temp in knownTemplates]);

        # did this user add the template?  None means "unknown", False means "no",
        # while True means "yes"
        selfAddedTemplate = None;

        # for each request, we also store the revision ID of the page,
        # potentially later added to the Request object for logging.
        templateAddedRevision = None;

        for (revId, revTime, revUser, revComment) in userPage.getVersionHistory(total=maxRevs):
            # Keep track of this right away to avoid off-by-1 errors
            numSeenRevs += 1;

            try:
                revText = userPage.getOldVersion(revId);
            except:
                logging.warning("unable to fetch revision ID {0}".format(revId));
                continue;

            logging.info('got text of revision {0}'.format(revId))

            # If we do not have data already, populate and continue
            if not prevRevisionText:
                prevRevisionText = revText;
                prevRevisionUser = revUser;
                continue;

            revDiff = pageDiffer.compare(revText.splitlines(),
                                         prevRevisionText.splitlines());

            # Build a string of lines from the diff
            diffString = "";
            for line in revDiff:
                if re.match(r'[+]\s+', line):
                    diffString = "{diff}{line}\n".format(diff=diffString,
                                                         line=re.sub(r'[+]\s+', "", line));

            # Parse the diff string and filter templates
            parsedCode = mwp.parse(diffString);
            templates = parsedCode.filter_templates(recursive=True);

            templateAdded = False;
            if templates:
                for template in templates:
                    # Template.name is mwp.wikicode.Wikicode,
                    # need unicode for comparison Pywikibot.page titles.
                    # Strip whitespace & lowercase for case-insensitive
                    # matching.
                    if template.name.strip().lower() \
                            in knownTemplateTitles:
                        templateAdded = True;

            if templateAdded:
                logging.info('template was added in revision {0}'.format(revId))
                if prevRevisionUser == recUser.username:
                    # we've got a valid addition
                    selfAddedTemplate = True;
                    templateAddedRevision = revId;
                    logging.info("user {username} added the template themselves".format(username=recUser.username).encode('utf-8'));
                else:
                    selfAddedTemplate = False;
                    logging.info("user {username} did not add the template themselves, instead added by {revUser}".format(username=recUser.username, revUser=prevRevisionUser).encode('utf-8'));
                
                # either way, we found the most recent addition of the template,
                # our job is done...
                break;

            # no match, move forward and compare
            prevRevisionText = revText;
            prevRevisionUser = revUser;

        if selfAddedTemplate is None \
                and numSeenRevs <= maxRevs:
            # We've exhausted our search but not found a diff _adding_ the template,
            # check if it was added in the first edit to the page, and if the user
            # who edited was the same users as the one owning the page.
            (revId, revTime, revUser, revComment) = userPage.getVersionHistory(reverseOrder=True, total=1)[0];
            try:
                revText = userPage.getOldVersion(revId);
                # Parse the diff string and filter templates
                parsedCode = mwp.parse(revText);
                templates = parsedCode.filter_templates(recursive=True);
                templateAdded = False;
                if templates:
                    for template in templates:
                        # Similar name check as earlier...
                        if template.name.strip().lower() \
                                in knownTemplateTitles:
                            templateAdded = True;

                if templateAdded:
                    if revUser == recUser.username:
                        selfAddedTemplate = True;
                        templateAddedRevision = revId;
                        logging.info("inspected first revision, user {username} added the template themselves".format(username=recUser.username).encode('utf-8'));
                    else:
                        logging.info("inspected first revision, user {username} did not add the template themselves, instead added by {revUser}".format(username=recUser.username, revUser=prevRevisionUser).encode('utf-8'));
            except pywikibot.Error as e:
                logging.warning("unable to fetch revision ID {0}".format(revId));
                logging.warning("Error: {0}\n".format(e.args[0]));

        # This should now reflect whether we could determine if the template was added...
        if not selfAddedTemplate:
            return False;

        # create Request object, setting seeds to page titles,
        # and update database...
        recRequest = request.Request(lang=self.lang,
                                     username=recUser.username,
                                     page=userPage.title(),
                                     revid=templateAddedRevision,
                                     timestamp=datetime.utcnow(),
                                     templates=knownTemplateTitles,
                                     seeds=[page.title() for page in interestPages],
                                     sbDb=self.db.conn, # SBot DB connection
                                     verbose=self.verbose)
        try:
            recRequest.updateDatabase();
        except request.RequestUpdateError:
            logging.error("could not add the request info to the database, unable to continue");
            return False;

        # Instantiate the page object.  This also solves the problem of a user putting
        # the template on their User page, as we'll then post on their User talk page.
        if subPageTitle:
            destPage = pywikibot.Page(self.site, subPageTitle);
        else:
            destPage = recUser.getUserTalkPage();

        # Recommendations for this user
        userRecs = None;

        # Ask for recommendations for this user, turn interestPages into
        # a list of titles for transport to SuggestBot
        userRecs = bot.getRecs(username=recUser.username,
                               isRequest=True,
                               requestId=recRequest.getId(),
                               interestPages=[page.title() for page in interestPages]);

        # FIXME: if the user is in the Teahouse experiment and did not supply any
        # seeds, we should post a message asking them to use a different approach.

        if not 'recs' in userRecs \
                or not userRecs['recs']:
            logging.warning("got no recommendations for {username}".format(username=username).encode('utf-8'));
            return False;
        # 3.1: if we get recommendations back... create full template substitution text...
        recMsg = bot.createRecsPage(userRecs['recs']);
        # check again if the user is blocked...
        if recUser.isBlocked():
            logging.warning("User:{username} is blocked, posting aborted".format(recUser.username()).encode('utf-8'));
            return False;

        # Source text of the page we post suggestions to.
        destPageSource = None;

        try:
            destPageSource = destPage.get();
        except pywikibot.exceptions.NoPage:
            logging.warning("destination page {title} doesn't exist, will be created".format(title=destPage.title()).encode('utf-8'));
            destPageSource = "";
        except pywikibot.exceptions.IsRedirectPage:
            logging.warning("destination page {title} is a redirect, posting cancelled".format(title=destPage.title()).encode('utf-8'));
            return False;

        # Attempt to remove the template from the source, if it's not found
        # the existing source is returned unchanged.
        destPageSource = self.removeTemplateFromSource(destPageSource,
                                                       knownTemplates=knownTemplateTitles);
        #   3.3: add the recommendations to the end of the page,
        #        but strip any remaining leading/trailing whitespace.
        destPageSource = "{source}\n\n{recs}".format(source=destPageSource, recs=recMsg).strip();

        #   3.4: save the new page
        try:
            # NOTE: we're forcing the bot to post, ignoring {{nobots}}
            # and the like, because we expect the user to be conscious
            # about their choices...
            bot.save_page(destPage, destPageSource,
                          config.edit_comment[self.lang],
                          force=True)
        except PageNotSavedError:
            return False

        # OK, posting the suggestions went well...
        # If the template is found on a different page, basically the user page,
        # we'll have to remove it.
        if userPage != destPage:
            userPageSource = None;
            try:
                userPageSource = userPage.get();
            except pywikibot.exceptions.NoPage:
                logging.warning("user page {title} has stopped existing, aborting".format(title=destPage.title()).encode('utf-8'));
                return False;
            except pywikibot.exceptions.IsRedirectPage:
                logging.warning("user page {title} is a redirect, aborting".format(title=destPage.title()).encode('utf-8'));
                return False;

            # FIXME: test this part, it seems to malfunction!
                
            # Attempt to remove the template from the source, if it's not found
            # the existing source is returned unchanged.
            newUserPageSource = self.removeTemplateFromSource(userPageSource,
                                                              knownTemplates=knownTemplateTitles);
            if newUserPageSource != userPageSource:
                # We actually removed something...
                if not newUserPageSource:
                    # Insert placeholder to prevent a non-save
                    # and subsequent non-removal of the template
                    newUserPagesource = config.empty_placeholder[self.lang]

                try:
                    # NOTE: we're forcing the bot to post, ignoring {{nobots}}
                    # and the like, because we expect the user to be conscious
                    # about their choices...
                    userPage.text = newUserPageSource;
                    userPage.save(comment=config.replace_comment[self.lang],
                                  watch=False, minor=True, force=True);
                    # sys.stderr.write("Info: New user page source: {0}".format(newUserPageSource).encode('utf-8'));
                    # sys.stderr.write("Info: user page with removed template would have been saved at this point\n");
                except pywikibot.exceptions.EditConflict:
                    # FIXME: if this happens, fetch the page source again and make the edit,
                    # since that should resolve the edit conflict.
                    logging.error("removing template from {title} failed, edit conflict".format(title=destPage.title()).encode('utf-8'));
                    return False;
                except pywikibot.exceptions.PageNotSaved as e:
                    logging.error("removing template from {title} failed.\nError: {etext}".format(title=destPage.title(), etext=e).encode('utf-8'));
                    return False;

        # OK, we've posted suggestions, add the recs to the request object,
        # update its status, and commit to the database
        try:
            recRequest.setRecs(recs=userRecs['recs']);
            recRequest.setEndtime(newEndtime=datetime.utcnow());
            recRequest.setStatus('completed');
            recRequest.updateDatabase();
        except request.RequestUpdateError:
            logging.error("failed to update data for request {reqid}".format(reqid=recRequest.getId()));
            return False;

        logging.info("all done!\n");
        # ok, everything went well, done
        return True;

def main():
    """
    Run some tests.
    """
    # dict mapping a template to its synonyms
    templates = {"User:SuggestBot/suggest":
                 ["User:SuggestBot/th-suggest",
                  "User:Jtmorgan/sandbox/2"]};

    myHandler = RequestTemplateHandler(verbose=True,
                                       templates=templates);
    myBot = SuggestBot(lang=myHandler.lang);

    logging.info("instantiated RequestTemplateHandler and SuggestBot objects, testing request handling...");

    try:
        recRequests = myHandler.getRequests();
        for (page, pageData) in recRequests.items():
            logging.info("Found the following templates on page {page}:".format(page=page.title()).encode('utf-8'))

            for template in pageData['templates']:
                logging.info("- {template}".format(template=template.title()).encode('utf-8'))

            logging.info("\nIn the templates were listed the following articles:")

            for intPage in pageData['articles']:
                logging.info("- {page}".format(page=intPage.title()).encode('utf-8'))
            logging.info("")

        # Uncomment when doing live testing...
        if not myHandler.db.connect():
            logging.error("unable to connect to database");
        else:
            for (page, pageData) in recRequests.items():
                myHandler.processSingleRequest(userPage=page,
                                               interestPages=pageData['articles'],
                                               knownTemplates=pageData['templates'],
                                               bot=myBot);
            myHandler.db.disconnect();
    finally:
        myHandler.stopme();

    # OK, done...
    return;

if __name__ == "__main__":
    main();
