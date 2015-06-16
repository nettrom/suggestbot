#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Library for handling suggestion requests for WikiProjects
using the WikiProject X page and task template layout.

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

import logging

from reqhandler import RequestTemplateHandler

## Need a "WikiProjectRequest" object, or something similar,
## to hold information about the project request
## Also need some configuration variables: how many days between each update

class WikiProjectHandler(RequestTemplateHandler):
    def __init__(self, lang=u'en',
                 templates={u"User:SuggestBot/suggest": []},
                 ignore_list=[],
                 name_pattern=ur'^WikiProject'):
        """
        Initialise an object that will handle WikiProject requests
        added to WikiProject pages.

        
        @param lang: What language Wikipedia we are working on
        @type lang: unicode

        @param templates: Dictionary where each key is the title of a main template
                          that we'll look for, and its corresponding value is a list
                          of synonyms (through redirects).
        @type templates: dict (unicode to list of unicode)

        @param ignore_list: List of page titles we'll ignore when looking for references
        @type ignore_list: list (of unicode strings)

        @param name_pattern: Regular expression pattern to match names of pages,
                             if a page does not match this pattern it is not processed.
        @type name_pattern: unicode
        """
        
        super(self.__class__, self).__init__(lang, templates, ignore_list)

    def process_requests(self):
        ## 1: find all open requests
        ##    Two sources for requests:
        ##    1.1: transclusions of a specific template (I propose we create
        ##         User:SuggestBot/wp-suggest as a redirect, similar to th-suggest)
        ##    1.2: https://tools.wmflabs.org/projanalysis/config.php
        ##         projects that want suggestions have suggestbot: true, need to have
        ##         a config variable with the subpage name for those projects
        ## 2: process and update them

def main():
    """
    Run some tests.
    """

    import suggestbot

    myBot = suggestbot.SuggestBot()
    myHandler = WikiProjectHandler(templates=templates);


    logging.info(u"instantiated RequestTemplateHandler and SuggestBot objects, testing request handling...");

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
