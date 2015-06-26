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

import logging
import requests

import pywikibot
import mwparserfromhell as mwp

from reqhandler import RequestTemplateHandler

from suggestbot import config

## Need a "WikiProjectRequest" object, or something similar,
## to hold information about the project request
## Also need some configuration variables: how many days between each update

class WikiProjectRequest:
    def __init__(self, projname, projpage):
        '''
        :param projname: Name of the WikiProject we're suggesting to
        :type projname: str

        :param projpage: Page we're posting suggestions to
        :type projpage: str
        '''
        self.name = projname
        self.page = projpage

class WikiProjectHandler(RequestTemplateHandler):
    def __init__(self, lang=u'en',
                 name_pattern=ur'^WikiProject'):
        """
        Initialise an object that will handle WikiProject requests
        added to WikiProject pages.

        :param lang: What language Wikipedia we are working on
        :type lang: unicode

        :param name_pattern: Regular expression pattern to match names of pages,
                             if a page does not match this pattern it is not processed.
        :type name_pattern: unicode
        """
        
        super(self.__class__, self).__init__(lang, {}, [])

        self.template_pages = [config.wikiproj_template]
        self.name_pattern = name_pattern

    def process_requests(self):
        ## 1: find all open requests
        ##    Two sources for requests:
        ##    1.1: transclusions of a specific template (I propose we create
        ##         User:SuggestBot/wp-suggest as a redirect, similar to th-suggest)
        ##    1.2: https://tools.wmflabs.org/projanalysis/config.php
        ##         projects that want suggestions have suggestbot: true, need to have
        ##         a config variable with the subpage name for those projects
        ## FIXME: add the URL to the configuration
        ## 2: process and update them

        # 1: Find all open requests
        wproj_reqs = {} # maps project name to project request object

        template_page = pywikibot.Page(self.site, self.templates.keys()[0])
        for tr_page in template_page.embeddedin(filter_redirects=False,
                                                namespaces=[4],
                                                content=True):
            if tr_page.title() in self.ignoreList:
                continue

            if not tr_page.canBeEdited():
                logging.warning('SuggestBot cannot edit {0} (page locked?), skipping'.format(tr_page.title()))
                continue

            logging.info('now processing request on {0}'.format(tr_page.title()))

            parsed_text = mwp.parse(tr_page.get())
            for template in parsed_text.filter_templates(recursive=True):
                
        


def main():
    """
    Run some tests.
    """

    from suggestbot import SuggestBot

    myBot = SuggestBot()
    myHandler = WikiProjectHandler(templates=templates);
    logging.info(u"instantiated WikiProjectHandler and SuggestBot objects, testing request handling...");

    try:
        recRequests = myHandler.getRequests();
        for (page, pageData) in recRequests.iteritems():
            logging.info(u"Found the following templates on page {page}:".format(page=page.title()).encode('utf-8'))

            for template in pageData['templates']:
                logging.info(u"- {template}".format(template=template.title()).encode('utf-8'))

            logging.info("\nIn the templates were listed the following articles:")

            for intPage in pageData['articles']:
                logging.info(u"- {page}".format(page=intPage.title()).encode('utf-8'))
            logging.info("")

        # Uncomment when doing live testing...
        if not myHandler.db.connect():
            logging.error("unable to connect to database");
        else:
            for (page, pageData) in recRequests.iteritems():
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
