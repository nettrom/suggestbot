#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Program to update a template with three
types of tasks: copy edit, clarification,
and too feww wikilinks.
Copyright (C) 2012 Morten Wang

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
"""

import os;
import sys;
import re;
import random;

from datetime import datetime;

import oursql;
import pywikibot;

from opentasks import OpenTaskUpdater;

class OpentaskShort:
    def __init__(self, verbose=False, testRun=False,
                 taskPage=None, nPages=6, sizeLimit=10240,
                 classifierFile=None):
        """
        Instantiate an object of this class, which in turn will update the task list.

        @param verbose: write informational output?
        @type verbose: bool

        @param testRun: just testing? (won't save pages)
        @type testRun: bool

        @param taskPage: page containing the template we're writing to
        @type taskPage: unicode
        
        @param nPages: number of pages to be listed
        @type nPages: int

        @param sizeLimit: max page length of the articles we'll consider
        @type sizeLimit: int

        @param classifierFile: path to the file with info about the classifier
                               used for quality classification
        @type classifierFile: str
        """
        self.taskPage = taskPage;
        self.taskDef = {"copyedit": u"All articles needing copy edit",
                        "clarify": u"All Wikipedia articles needing clarification",
                        "wikilinks": u"All articles with too few wikilinks"};
        
        self.nPages = nPages;
        self.sizeLimit = sizeLimit;

        self.verbose = verbose;
        self.testRun = testRun;

        self.lang = u"en";
        self.editComment = u"Updating tasklist...";

        self.dbHost = "{lang}wiki-p.rrdb.toolserver.org".format(lang=self.lang);
        self.dbName = "{lang}wiki_p".format(lang=self.lang);
        self.dbConn = None;

        self.maxDBQueryAttempts = 3; # num retries for DB queries

        self.taskUpdater = OpenTaskUpdater(verbose=self.verbose,
                                           lang=self.lang,
                                           classifierFile=classifierFile,
                                           taskDef=self.taskDef);

    def stopme(self):
        pywikibot.stopme();


    def findRandomPages(self, category=None, nPages=5):
        """
        Use the database to pick a number of pages from a given category
        that are not longer than self.sizeLimit and which are not protected.
        Expects a working database connection to exist as self.dbConn
        
        @param category: Name of the category to grab pages from
        @type category: unicode

        @param nPages: number of pages to pick
        @type nPages: int
        """

        # Query to fetch a number of random pages from a given category
        # not longer than a given size limit and not protected.
        randomPageQuery = r"""SELECT /* LIMIT:180 */
                              page_id, page_title
                              FROM page p JOIN categorylinks cl
                              ON p.page_id=cl.cl_from
                              LEFT JOIN page_restrictions pr
                              ON p.page_id=pr.pr_page
                              WHERE cl_to=?
                              AND page_namespace=?
                              AND page_len <= ?
                              AND page_random >= RAND()
                              AND pr.pr_page IS NULL
                              ORDER BY page_random LIMIT ?""";

        if not category:
            sys.stderr.write(u"Error: unable to find pages without a category to pick from\n");
            return [];

        if self.verbose:
            sys.stderr.write(u"Info: finding {n} tasks from category {cat}\n".format(n=nPages, cat=category).encode('utf-8'));

        foundPages = [];
        attempts = 0;
        while attempts < self.maxDBQueryAttempts:
            try:
                dbCursor = self.dbConn.cursor();
                dbCursor.execute(randomPageQuery,
                                 (re.sub(' ', '_', category).encode('utf-8'), # catname
                                  0, # ns
                                  self.sizeLimit, # length limit
                                  nPages) # n pages
                                 );
                for (pageId, pageTitle) in dbCursor:
                    foundPages.append(unicode(re.sub('_', ' ', pageTitle),
                                              'utf-8', errors='strict'));
            except oursql.Error, e:
                attempts += 1;
                sys.stderr.write("Error: Unable to execute query to get pages from this category, possibly retrying!\n");
                sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
                if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
                        or e.errno == oursql.errnos['CR_SERVER_LOST']:
                    # lost connection, reconnect
                    self.connectDatabase();
            else:
                break;
        if attempts >= self.maxDBQueryAttempts:
            sys.stderr.write(u"Error: Exhausted number of query attempts!\n");
        elif self.verbose:
            sys.stderr.write(u"Info: found {n} tasks from this category.\n".format(n=len(foundPages)).encode('utf-8'));

        return foundPages;
        
    def update(self):
        """
        Update the task page.
        """

        # Query to check if a page is deleted
        # (necessary to make sure we're skipping pages that appear to exist but don't)
        isDeletedQuery = ur"""SELECT log_id, log_type, log_action
                              FROM logging_ts_alternative
                              WHERE log_namespace=0
                              AND log_title=?""";

        # connect to the wiki and log in
        if self.verbose:
            sys.stderr.write("Info: connecting to {lang}wiki\n".format(lang=self.lang));

        wikiSite = pywikibot.getSite(self.lang);
        wikiSite.login();

        # Did we log in?
        if wikiSite.username() is None:
            sys.stderr.write("Error: failed to log in correctly, aborting!\n");
            return False;

        # connect to database
        if not self.taskUpdater.connectDatabase(hostName=self.dbHost,
                                                dbName=self.dbName):
            sys.stderr.write(u"Error: Unable to connect to database, aborting!\n");
            return False;

        # We'll be using this database connection quite a bit, so give me a reference
        self.dbConn = self.taskUpdater.dbConn;

        taskLists = {};
        # 1: Oversample pages by x25
        for (taskId, taskCat) in self.taskDef.iteritems():
            taskLists[taskId] = self.findRandomPages(category=taskCat,
                                                     nPages=self.nPages*25);

        # until we have picked self.nPages,
        # check each of the pages in the list
        pickedPages = {};
        for (taskId, taskList) in taskLists.iteritems():
            pickedPages[taskId] = [];
            i = 0;
            with self.dbConn.cursor() as dbCursor:
                while len(pickedPages[taskId]) < self.nPages and i < len(taskList):
                    # choose a candidate
                    pageTitle = re.sub(" ", "_", taskList[i]);

                    isDeleted = False;
                    dbCursor.execute(isDeletedQuery, (pageTitle.encode('utf-8'),));
                    for (logId, logType, logAction) in dbCursor:
                        if logType == "delete" and logAction == "delete":
                            isDeleted = True;

                    if not isDeleted:
                        pickedPages[taskId].append(pageTitle);

                    # OK, move to next candidate
                    i += 1;
        
        # get current page text
        tasktext = None;
        try:
            taskpage = pywikibot.Page(wikiSite, self.taskPage);
            tasktext = taskpage.get();
        except pywikibot.exceptions.NoPage:
            sys.stderr.write(u"Warning: Task page {title} does not exist, aborting!\n".format(title=self.taskPage).encode('utf-8'));
        except pywikibot.exceptions.IsRedirectPage:
            sys.stderr.write(u"Warning: Task page {title} is a redirect, aborting!\n".format(title=self.taskPage).encode('utf-8'));
        except pywikibot.data.api.TimeoutError:
            sys.stderr.write(u"Error: API request to {lang}-WP timed out, unable to get wikitext of {title}, cannot continue!\n".format(lang=self.lang, title=self.taskPage));

        if tasktext is None:
            return False;

        if self.verbose:
            sys.stderr.write(u"Info: got wikitext, updating...\n");

        # Matches beginning unordered list, grabs the ID as
        # a matching group
        ulStartRegex = re.compile('\s*<ul id="([^"]+)"');

        taskLines = tasktext.split("\n");
        for i in range(len(taskLines)):
            lineMatch = ulStartRegex.match(taskLines[i]);
            if lineMatch:
                taskId = lineMatch.group(1);
                # do we know this task ID?
                if not taskId in pickedPages:
                    continue;

                # OK, replace
                pageList = pickedPages[taskId];
                for j in range(len(pageList)):
                    taskLines[(i+1)+j] = u"      <li>{title}</li>".format(title=pywikibot.Page(wikiSite, pageList[j]).title(asLink=True));

        # Re-assemble
        tasktext = "\n".join(taskLines);
            
        if self.testRun:
            sys.stderr.write(u"Info: Running a test, printing out new wikitext:\n\n");
            print tasktext.encode('utf-8');
        else:
            if self.verbose:
                sys.stderr.write(u"Info: Saving page with new text\n");
            taskpage.text = tasktext;
            try:
                taskpage.save(comment=self.editComment);
            except pywikibot.exceptions.EditConflict:
                sys.stderr.write(u"Error: Saving page {title} failed, edit conflict.\n".format(title=self.taskPage).encode('utf-8'));
                return False;
            except pywikibot.exceptions.PageNotSaved as e:
                sys.stderr.write(u"Error: Saving page {title} failed.\nError: {etext}\n".format(title=self.taskPage, etext=e).encode('utf-8'));
                return False;
            except pywikibot.data.api.TimeoutError:
                sys.stderr.write(u"Error: Saving page {title} failed, API request timeout fatal\n".format(title=self.taskPage).encode('utf-8'));
                return False
            
        # OK, all done
        if self.verbose:
            sys.stderr.write("Info: List of open tasks successfully updated!\n");
                
        return True;

def main():
    # parse cli options
    import argparse;
    
    cli_parser = argparse.ArgumentParser(
        description="Program to update Template:Opentask-short on English Wikipedia."
        );

    # Option to control where the classifier configuration file is located
    cli_parser.add_argument('-f', '--classifier', default=None, metavar="<classifier-path>",
                            help="path to file with hostname and port of the quality classifier");

    # Option to control the number of pages per column
    cli_parser.add_argument('-n', '--numpages', type=int, default=6,
                            help="number of pages in the list (default: 6)");

    
    # Option to control where the list of open tasks are
    cli_parser.add_argument('-p', '--page', default=None,
                            help="title of the page with the open tasks");

    # Option to control the size limit
    cli_parser.add_argument('-s', '--sizelimit', type=int, default=10240,
                            help="max size in bytes a page can be to be a candidate (default: 10240, 10kB)");

    # Test option
    cli_parser.add_argument('-t', '--test', action='store_true',
                            help='if set the program does not save the page, writes final wikitext to stdout instead');

    # Verbosity option
    cli_parser.add_argument('-v', '--verbose', action='store_true',
                            help='if set informational output is written to stderr');
    
    args = cli_parser.parse_args();

    # instantiate object
    taskUpdater = OpentaskShort(verbose=args.verbose,
                                testRun=args.test,
                                taskPage=args.page,
                                nPages=args.numpages,
                                sizeLimit=args.sizelimit,
                                classifierFile=args.classifier);
    try:
        # update
        taskUpdater.update();
    finally:
        taskUpdater.stopme();
        
    return;

if __name__ == "__main__":
    main();
