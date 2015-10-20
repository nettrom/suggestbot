#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Library for handling suggestion requests for WikiProjects
using the WikiProject X page and task template layout.

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

import re

import logging
import requests

from datetime import datetime, timezone

import pywikibot
import mwparserfromhell as mwp

import request
from reqhandler import RequestTemplateHandler

from suggestbot import config
from suggestbot import db

class WikiProjectRequest:
    def __init__(self, projname, projpage,
                 projcat=None):
        '''
        :param projname: Name of the WikiProject we're suggesting to
        :type projname: str

        :param projpage: Page we're posting suggestions to
        :type projpage: str
        '''
        self.name = projname
        self.page = projpage
        self.category = projcat

class WikiProjectHandler(RequestTemplateHandler):
    def __init__(self, bot, lang=u'en',
                 name_pattern='^WikiProject',
                 module_name='User:SuggestBot/WikiProjects',
                 method_name='suggestions'):
        """
        Initialise an object that will handle WikiProject requests
        added to WikiProject pages.

        :param bot: The SuggestBot instance we will use to get and prepare suggestions
        :type bot: suggestbot.SuggestBot

        :param lang: What language Wikipedia we are working on
        :type lang: unicode

        :param name_pattern: Regular expression pattern to match names of pages,
                             if a page does not match this pattern it is not processed.
        :type name_pattern: unicode

        :param module_name: Name of the module 
        """
        
        super(self.__class__, self).__init__(lang=lang,
                                             templates={},
                                             ignoreList=config.wikiproject_ignores)
        self.invoke_pattern = re.compile('#invoke', re.I)
        self.name_pattern = re.compile(name_pattern, re.I)
        self.wikiproject_template = config.wikiproject_template.lower()

        self.module_name = module_name
        self.method_name = method_name

        self.bot = bot
        self.db = db.SuggestBotDatabase()
        
        # Regular expression for splitting a project page into project name
        # and sub page parts.
        self.subpage_re = re.compile('(?P<projname>[^/]+)(?P<subname>/.*)')

    def edit_invoke(self, page_source, new_invoke):
        '''
        Parse the given page source wikitext. If an existing SuggestBot
        module invoke is present, replace it, otherwise add it to the
        end of the page.

        :param page_source: The source wikitext we're editing
        :type page_source: str

        :param new_invoke: The new invoke text to edit/insert
        :type new_invoke: str
        '''
        parsed_text = mwp.parse(page_source)

        i = 0
        edited = False
        while i < len(parsed_text.nodes):
            node = parsed_text.nodes[i]
            if isinstance(node, mwp.nodes.template.Template) \
               and re.match(self.invoke_pattern, str(node.name)) \
               and re.search(self.module_name, str(node.name)):
                # It's a template that's an invoke call,
                # and it's matching our module, edit it
                parsed_text.nodes[i] = new_invoke
                edited = True
                break
            else:
                i += 1

        if not edited:
            parsed_text.nodes.append(new_invoke)

        return str(parsed_text)

    def get_wikiproject_pages(self, project_name):
        '''
        Fetch articles from this project's categories for articles
        organised by quality class. Only gets up to `wikiproject_articles`
        number of articles, if the project has more than that.      

        :param project_name: Name of the project, to be used in category names
        :type project_name: str
        '''

        ## Can use a list instead of a set, because it's unlikely that
        ## a project has the same article in two assessment classes.
        proj_articles = []
        i = 0
        while len(proj_articles) < config.wikiproject_articles \
              and i < len(config.wikiproject_qual_prefixes):
            ## Note: strips out 'WikiProject ' because category names do not
            ## contain that.
            cat = pywikibot.Category(
                self.site,
                '{prefix} {proj} {suffix}'.format(
                    prefix=config.wikiproject_qual_prefixes[i],
                    proj=project_name.replace('WikiProject ', ''),
                    suffix=config.wikiproject_suffix[self.lang]))
            for page in cat.articles(namespaces=[0,1],
                                     sortby='timestamp',
                                     reverse=True):
                if page.namespace() == 0:
                    proj_articles.append(page)
                else:
                    proj_articles.append(page.toggleTalkPage())

            i += 1

        ## If we have more than we should, trim the list...
        if len(proj_articles) > config.wikiproject_articles:
            proj_articles = proj_articles[config.wikiproject_articles:]

        return(proj_articles)
    
    def process_requests(self):
        '''
        Find and process all WikiProject requests for suggestions.  Requests
        are discovered through transclusions of the SuggestBot template for
        WikiProject requests (`suggestbot.config.wikiproject_template`), and
        by polling the WikiProject X config URL
        (`suggestbot.config.wikiproject_config_url`).
        '''

        if not self.db.connect():
            logging.error('unable to connect to SuggestBot database, exiting')
            return False
        
        wproj_reqs = {} # maps project name to project request object
        wproj_queue = [] # project's we'll post suggestions to

        # Find transclusions of the WikiProject template in the
        # Wikipedia and Wikipedia talk namespaces.
        template_page = pywikibot.Page(self.site, config.wikiproject_template)
        for tr_page in template_page.embeddedin(filter_redirects=False,
                                                namespaces=[4,5],
                                                content=True):
            if tr_page.title() in self.ignoreList:
                continue

            if not tr_page.canBeEdited():
                logging.warning('SuggestBot cannot edit {0} (page locked?), skipping'.format(tr_page.title()))
                continue

            logging.info('now processing request on {0}'.format(tr_page.title()))

            parsed_text = mwp.parse(tr_page.get())
            for template in parsed_text.filter_templates(recursive=True):
                template_name = template.name().strip().lower()
                if template_name == self.wikiproject_template:
                    # page title (without namespace) must match project name pattern
                    if not self.name_pattern.match(tr_page.title(withNamespace=False)):
                        continue
                    
                    # strip off subpage to get project name
                    match_obj = self.subpage_re.match(
                        tr_page.title(withNamespace=False))
                    if not match_obj:
                        # this is not supposed to happen
                        logging.warning('Template found, but not a project sub-page, ignoring this page')
                        continue
                    
                    project_name = match_obj.group('projname')
                    ## Store this request
                    wproj_reqs[project_name] = WikiProjectRequest(
                        project_name, tr_page)

        # Poll the WikiProject X config url
        req = requests.get(config.wikiproject_config_url)
        wpx_config = req.json()
        for project in wpx_config['projects']:
            ## If there's a suggestbot config variable and it's true...
            if 'suggestbot' in project and project['suggestbot']:
                project_page = pywikibot.Page(self.site, project['name'])
                project_name = project_page.title(withNamespace=False)
                project_post_page = pywikibot.Page(
                    self.site, '{project}/{subpage}'.format(
                        project=project_page.title(),
                        subpage=config.wikiproject_subpage))
                project_category = pywikibot.Category(
                    self.site, project['source'])

                ## Store the request
                wproj_reqs[project_name] = WikiProjectRequest(
                    project_name, project_post_page,
                    project_category)

        ## Go through all requests and add all projects where it's time
        ## to post again to the project queue.
        wproj_queue = []
        now = datetime.now(timezone.utc)
        for project in wproj_reqs.values():
            ## Default is to process this project
            wproj_queue.append(project)

            ## Check the edit history, assuming that if we've edited,
            ## we've done so in the past 50 edits...
            try:
                for (revid, revtime, revuser, revcomment) \
                    in project.page.getVersionHistory(total=50):
                    # revtime is UTC, but Python doesn't know, so add tz
                    time_since = now - revtime.replace(tzinfo=timezone.utc)
                    if revuser == self.site.user():
                        # is it too soon?
                        if time_since.days < (config.wikiproject_delay -1):
                            wproj_queue.pop()
                            break
                        elif time_since.days == (config.wikiproject_delay -1) \
                             and time_since.seconds < 86400/2:
                            ## We check if we're less than half a day away,
                            ## otherwise the delay in generating suggestions
                            ## makes us always update it too late.
                            wproj_queue.pop()
                            break
                        
            except pywikibot.exceptions.NoPage:
                ## Project page doesn't exist, process project and create it...
                pass

        # Go through all requests that are to be processed, fetch articles
        # from project categories
        for project in wproj_queue:
            if not project.category:
                ## Figure out the WikiProject's category name
                project.category = pywikibot.Category(
                    self.site,
                    "{project}{suffix}".format(
                        project=project.name,
                        suffix=config.wikiproject_suffix))

            project.pages = self.get_category_pages(project.category)

            ## If we didn't find any articles in that category, go see
            ## if the project has categories for articles by assessment rating.
            if not project.pages:
                logging.info('Did not find any articles for {0} in the main project category, checking assessment categories'.format(project.name))
                project.pages = self.get_wikiproject_pages(project.name)

        ## For each project in the queue, create the Request object,
        ## update the database, get suggestions, complete the request
        for project in wproj_queue[:1]:
            logging.info('Suggesting articles to {0}'.format(project.name))
            rec_req = request.Request(lang=self.lang,
                                      username=project.name,
                                      page=project.page,
                                      revid=0,
                                      timestamp=datetime.now(timezone.utc),
                                      templates=[config.wikiproject_template],
                                      seeds=[page.title() for page in project.pages],
                                      sbDb=self.db)
            try:
                rec_req.updateDatabase()
            except request.RequestUpdateError:
                logging.error(u"adding request info to database failed, unable to continue")
                return(False)

            userRecs = self.bot.getRecs(username=project.name,
                                        isRequest=True,
                                        requestId=rec_req.getId(),
                                        interestPages=[page.title() for page in \
                                                       project.pages])
            if not 'recs' in userRecs \
               or not userRecs['recs']:
                logging.warning("got no recommendations for {0}".format(project.name))
                try:
                    rec_req.setEndtime(newEndtime=datetime.now(timezone.utc))
                    rec_req.setStatus(u'completed')
                    rec_req.updateDatabase()
                except request.RequestUpdateError:
                    logging.error("failed to update data for request {reqid}".format(reqid=recRequest.getId()))
                    return(False)
                else:
                    continue

            ## Turn recommendations into a Lua-module template invoke-call.
            rec_msg = self.bot.create_invoke(userRecs['recs'],
                                             self.module_name,
                                             self.method_name,
                                             add_include_clause=True);
            
            try:
                page_source = project.page.get()
            except pywikibot.exceptions.NoPage:
                page_source = ''

            project.page.text = self.edit_invoke(page_source, rec_msg)
            
            try:
                project.page.save(summary=config.edit_comment[self.lang],
                                  minor=False)
            except pywikibot.exceptions.EditConflig:
                logging.error('Posting recommendations to {page} failed, edit conflict, will try again later'.format(page=project.page.title()))
                return False
            except pywikibot.execptions.PageNotSaved as e:
                logging.error('Failed posting recommendations to {page}, reason: {e_code} {e_text}'.format(page=project.page.title(), e_code=e.args[0], e_text=e.args[1]))
                return False
                
            # OK, we've posted suggestions, add the recs to the request object,
            # update its status, and commit to the database
            try:
                rec_req.setRecs(recs=userRecs['recs'])
                rec_req.setEndtime(newEndtime=datetime.now(timezone.utc))
                rec_req.setStatus(u'completed')
                rec_req.updateDatabase()
            except request.RequestUpdateError:
                logging.error("failed to update data for request {reqid}".format(reqid=recRequest.getId()))
                return(False)

        self.db.disconnect()
        logging.info(u"all done!\n")
        # ok, everything went well, done
        return True

def main():
    """
    Run some tests.
    """

    from suggestbot import SuggestBot

    mybot = SuggestBot()
    myhandler = WikiProjectHandler(mybot)

    logging.info(u"instantiated WikiProjectHandler and SuggestBot objects, testing request handling...")

    try:
        myhandler.process_requests()
    finally:
        pywikibot.stopme()
        
    # OK, done...
    return

if __name__ == "__main__":
    main()
