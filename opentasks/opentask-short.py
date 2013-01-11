#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Program to update a template with only
copyedit tasks, using certain exclusion
criteria in the selection process.
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
        self.taskDef = {"copyedit": u"All articles needing copy edit"};
        
        self.nPages = nPages;
        self.sizeLimit = sizeLimit;

        self.verbose = verbose;
        self.testRun = testRun;

        self.lang = u"en";
        self.editComment = u"Updating tasklist...";

        self.dbHost = "enwiki-p.userdb.toolserver.org";
        self.dbName = "enwiki_p";
        self.cacheTable = "u_nettrom.opentask_short";

        # Regular expression to match optional pre-text and post-text
        # noinclude sections
        self.noincludeRegex = re.compile(ur"""<noinclude>.*?</noinclude>""", re.DOTALL);

        self.taskUpdater = OpenTaskUpdater(verbose=self.verbose,
                                           lang=self.lang,
                                           classifierFile=classifierFile,
                                           taskDef=self.taskDef);

    def stopme(self):
        pywikibot.stopme();

    def findPages(self):
        """
        Use the database to grab all the pages in our copy edit category.
        Expects a working database connection to exist as self.taskUpdater.dbConn
        """
        pageQuery = ur"""SELECT /* LIMIT: 120 */
                         page_id, page_title
                         FROM page JOIN categorylinks
                         ON page_id=cl_from
                         WHERE cl_to=?
                         AND page_namespace=?
                         AND page_len <= ?
                         LIMIT 50""";

        if self.verbose:
            sys.stderr.write(u"Info: finding pages from category {cat}\n".format(cat=self.taskDef['copyedit']).encode('utf-8'));

        foundPages = [];
        attempts = 0;
        maxDBQueryAttempts = 3;
        while attempts < maxDBQueryAttempts:
            try:
                dbCursor = self.taskUpdater.dbConn.cursor();
                dbCursor.execute(pageQuery,
                                 (self.taskDef['copyedit'].replace(" ", "_").encode('utf-8'), # catname
                                  0, # ns
                                  self.sizeLimit) # <= sizeLimit
                                 );
                for (pageId, pageTitle) in dbCursor:
                    foundPages.append(unicode(pageTitle.replace("_", " "),
                                              'utf-8', errors='strict'));
            except oursql.Error, e:
                attempts += 1;
                sys.stderr.write("Error: Unable to execute query to get pages from this category, possibly retrying!\n");
                sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
                if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
                        or e.errno == oursql.errnos['CR_SERVER_LOST']:
                    # lost connection, reconnect
                    self.taskUpdater.connectDatabase();
            else:
                break;
        if attempts >= maxDBQueryAttempts:
            sys.stderr.write(u"Error: Exhausted number of query attempts!\n");
        elif self.verbose:
            sys.stderr.write(u"Info: found {n} tasks from this category.\n".format(n=len(foundPages)).encode('utf-8'));
            
        return foundPages;
        
    def update(self):
        """
        Update the task page.
        """
        # NOTE: arguably this can be done a lot faster if we cache
        # every page's edit time and text and quality
        # Then we compare against the database.

        # We cache views and quality.  We only check views if the date has changed
        # and it's after 06:00 (so stats.grok.se is updated)
        # We only check quality if the article's been edited (store the SHA1 checksum
        # and only fetch if it has changed)
        # I need a SQL table on enwiki-p.userdb with:
        # page_id, checksum, update time, views, quality
        # we need page_id and checksum for checking if quality needs updating
        # we need page_id and update time to check if views needs updating

        # Query to compare our cached list with current data
        # to find pages which should be deleted.
        deletedPagesQuery = ur"""SELECT op.page_id
                                 FROM {cachetable} op
                                 LEFT JOIN
                                    (SELECT page_id
                                     FROM page p JOIN categorylinks cl
                                     ON p.page_id=cl.cl_from
                                     WHERE cl_to=?
                                     AND p.page_namespace=?
                                     AND p.page_len <= ?) AS cp
                                 ON op.page_id=cp.page_id
                                 WHERE cp.page_id IS NULL""".format(cachetable=self.cacheTable);

        deletePageQuery = ur"""DELETE FROM {cachetable}
                               WHERE page_id=?""".format(cachetable=self.cacheTable);

        # Query to compare our cached list with current data
        # to find pages which should be added.
        addedPagesQuery = ur"""SELECT /* LIMIT:120 */
                               p.page_id
                               FROM page p JOIN categorylinks cl
                               ON p.page_id=cl.cl_from
                               LEFT JOIN {cachetable} op
                               ON p.page_id=op.page_id
                               WHERE cl.cl_to=?
                               AND p.page_namespace=?
                               AND p.page_len <= ?
                               AND op.page_id IS NULL""".format(cachetable=self.cacheTable);

        addPageQuery = ur"""INSERT INTO {cachetable}
                            (page_id)
                            VALUES (?)""".format(cachetable=self.cacheTable);

        # Query to get the earliest update of popularity from the cache,
        # used to figure out if we need to do our daily update or not
        getFirstPoptimeQuery = ur"""SELECT pop_timestamp AS mintime
                                    FROM {cachetable}
                                    WHERE pop_timestamp IS NOT NULL
                                    ORDER BY pop_timestamp ASC
                                    LIMIT 1""".format(cachetable=self.cacheTable);

        # Query to get a list of all pages so we can compare the time
        # when it was last update to the current time and if necessary update popularity.
        getPoptimeQuery = ur"""SELECT p.page_id, p.page_title, op.pop_timestamp
                               FROM page p JOIN {cachetable} op
                               ON p.page_id=op.page_id""".format(cachetable=self.cacheTable);

        # Query to update popularity data
        updatePopQuery = ur"""UPDATE {cachetable}
                              SET pop_timestamp=?, popcount=?, popularity=?
                              WHERE page_id=?""".format(cachetable=self.cacheTable);
        
        # Query to get a list of all pages which need to get new quality data
        # because the page has changed since we cached it.
        # (cached rev ID of 0 means we haven't stored quality data yet)
        getChangedQuery = ur"""SELECT p.page_id, p.page_title
                               FROM page p JOIN {cachetable} op
                               ON p.page_id=op.page_id
                               JOIN revision r1
                               ON p.page_latest=r1.rev_id
                               JOIN revision r2
                               ON op.rev_id=r2.rev_id
                               WHERE r2.rev_id=0
                               OR (r1.rev_timestamp > r2.rev_timestamp
                               AND r1.rev_sha1 <> r2.rev_sha1)""".format(cachetable=self.cacheTable);

        # Query to update quality data
        updateQualQuery = ur"""UPDATE {cachetable}
                               SET assessed_class=?, predicted_class=?, quality=?, rev_id=?
                               WHERE page_id=?""".format(cachetable=self.cacheTable);

        # Query to get data for all pages
        # which are not protected (this is a quick shortcut to find non-protected pages,
        # might find some false positives), and which have a minimum amount of views.
        getAllPagesQuery = ur"""SELECT p.page_id, p.page_title, op.popcount, op.quality
                                FROM page p JOIN {cachetable} op
                                ON p.page_id=op.page_id
                                LEFT JOIN page_restrictions pr
                                ON p.page_id=pr.pr_page
                                WHERE pr.pr_page IS NULL
                                AND op.popcount > 2""".format(cachetable=self.cacheTable);

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
        dbHost = u"{lang}wiki-p.userdb.toolserver.org".format(lang=self.lang);
        dbName = re.sub("-", "_", u"{lang}wiki_p".format(lang=self.lang));
        if not self.taskUpdater.connectDatabase(hostName=dbHost,
                                                dbName=dbName):
            sys.stderr.write(u"Error: Unable to connect to database, aborting!\n");
            return False;

        # We'll be using this database connection quite a bit, so give me a reference
        dbConn = self.taskUpdater.dbConn;

        # 1: delete pages that are no longer valid
        with dbConn.cursor() as dbCursor:
            dbCursor.execute(deletedPagesQuery,
                             (re.sub(" ", "_", self.taskDef['copyedit']), # category
                              0, # namespace
                              self.sizeLimit)); # size limit
            deletedPages = [];
            for (pageId,) in dbCursor:
                deletedPages.append((pageId,));
            if self.verbose:
                sys.stderr.write(u"Info: found {n} pages to be deleted from the cache\n".format(n=len(deletedPages)));

            dbCursor.executemany(deletePageQuery, deletedPages);
            dbConn.commit();
            if self.verbose:
                sys.stderr.write(u"Info: deleted {n} pages from the cache\n".format(n=dbCursor.rowcount));
        
        # 2: add new pages
        with dbConn.cursor() as dbCursor:
            dbCursor.execute(addedPagesQuery,
                             (re.sub(" ", "_", self.taskDef['copyedit']), # category
                              0, # namespace
                              self.sizeLimit)); # size limit
            addedPages = [];
            for (pageId,) in dbCursor:
                addedPages.append((pageId,));

            if self.verbose:
                sys.stderr.write(u"Info: found {n} pages to be added to the cache\n".format(n=len(addedPages)));

            dbCursor.executemany(addPageQuery, addedPages);
            dbConn.commit();
            if self.verbose:
                sys.stderr.write(u"Info: added {n} pages to the cache\n".format(n=dbCursor.rowcount));
        
        # get a list of pages in need of pop updating
        with dbConn.cursor() as dbCursor:
            dbCursor.execute(getPoptimeQuery);
            changedPages = {}; # map page title to page ID
            for (pageId, pageTitle, popTime) in dbCursor:
                pageTitle = unicode(pageTitle, 'utf-8', errors='strict');
                pageTitle = re.sub("_", " ", pageTitle);

                # add it doesn't have pop data
                if not popTime:
                    changedPages[pageTitle] = pageId;

            if self.verbose:
                sys.stderr.write(u"Info: found {n} to update popularity data for\n".format(n=len(changedPages)));

            # get popdata for these pages
            popData = self.taskUpdater.popQualServer.getPopList(pages=changedPages.keys());

            # list of data to be executed with executemany()
            updatedPopPages = [];

            for (pageTitle, pageData) in popData.iteritems():
                # append tuple w/timestamp, avg views (popcount), low/med/high pop,
                # and get page ID by mapping from title
                updatedPopPages.append((pageData.popTimestamp.strftime("%Y%m%d%H%M%S"),
                                        pageData.popCount,
                                        pageData.popularity,
                                        changedPages[pageData.title]));
            if self.verbose:
                sys.stderr.write(u"Info: got updated pop data for {n} pages\n".format(n=len(updatedPopPages)));

            # update database
            dbCursor.executemany(updatePopQuery,
                                 updatedPopPages);
            dbConn.commit();
            if self.verbose:
                sys.stderr.write(u"Info: updated {n} rows in the cache\n".format(n=dbCursor.rowcount));


        # Skipping quality assessment due to correlation with length,
        # as we're limiting by that anyway.
        # 4: get all pages which need new quality data
        # 4.1: update quality data for those pages
        # we'll need to know the rev IDs of the revision we based our quality
        # assessment on, so we can store that (and its rev_timestamp) in our database.
        # make a method in PopQual for this, it'll _only_ get quality for these pages.
        # with dbConn.cursor() as dbCursor:
        #     dbCursor.execute(getChangedQuery);
            
        #     changedPages = {}; # map page title to page ID
        #     for (pageId, pageTitle) in dbCursor:
        #         pageTitle = unicode(pageTitle, 'utf-8', errors='strict');
        #         changedPages[pageTitle] = pageId;

        #     qualData = self.taskUpdater.popQualServer.getQualList(titles=changedPages.keys());
            
        #     # list of data to be executed with executemany();
        #     updatedQualPages = [];

        #     for pageData in qualData:
        #         # append tuple with assessed class, predicted class, low/med/high quality,
        #         # and revision ID we based our assessment on
        #         updatedQualPages = ((pageData.assessedClass,
        #                              pageData.predictedClass,
        #                              pageData.quality,
        #                              pageData.qualRevisionId));

        #     if self.verbose:
        #         sys.stderr.write(u"Info: got updated qual data for {n} pages\n".format(n=len(updatedQualPages)));

        #     # update database
        #     dbCursor.executemany(updateQualQuery,
        #                          updatedQualPages);
        #     dbConn.commit();
        #     if self.verbose:
        #         sys.stderr.write(u"Info: updated {n} rows in the cache\n".format(n=dbCursor.rowcount));

        # 5: get all pages (that are not protected)
        # 5.1: sort by quality, low/medium/high
        # 5.2: sort by popularity, descending
        # 5.3: select pages, and update
        popQualData = [];

        with dbConn.cursor() as dbCursor:
            dbCursor.execute(getAllPagesQuery);

            for (pageId, pageTitle, popCount, quality) in dbCursor:
                pageTitle = unicode(pageTitle, 'utf-8', errors='strict');
                popQualData.append({'id': pageId,
                                    'title': pageTitle,
                                    'popcount': popCount});

        if self.verbose:
            sys.stderr.write(u"Info: got {n} pages from the cache, sorting and updating...\n".format(n=len(popQualData)));

        # sort by popularity (views/day), descending
        # sortedPages = sorted(popQualData,
        #                      key=lambda pageData: pageData['popcount'],
        #                      reverse=True);

        # sort by pseudo-random
        sortedPages = popQualData;
        random.shuffle(sortedPages);

        # until we have picked self.nPages,
        # check each of the pages in the list
        pickedPages = [];
        i = 0;
        with dbConn.cursor() as dbCursor:
            while len(pickedPages) < self.nPages and i < len(sortedPages):
                # choose a candidate
                pageData = sortedPages[i];
                pageTitle = re.sub(" ", "_", pageData['title']);

                isDeleted = False;
                dbCursor.execute(isDeletedQuery, (pageTitle.encode('utf-8'),));
                for (logId, logType, logAction) in dbCursor:
                    if logType == "delete" and logAction == "delete":
                        isDeleted = True;

                if not isDeleted:
                    pickedPages.append(pageData);

                # OK, move to next candidate
                i += 1;
        
        # turn into wikitext, one unicode string of list items
        wikitext = u"\n".join([u"* {title}".format(title=pywikibot.Page(wikiSite, page['title']).title(asLink=True)) for page in pickedPages]);

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

        noincludeFind = self.noincludeRegex.findall(tasktext);
        if not noincludeFind:
            sys.stderr.write(u"Info: no noinclude sections in the template source, someone messed with the wikitext?\n");
            return False;
        elif len(noincludeFind) != 2:
            sys.stderr.write(u"Info: did not find two noinclude sections, someone messed with the wikitext?\n");
            sys.stderr.write(u"Warning: aborting edit!\n");
            return False;
        else:
            tasktext = u"{pre}{tasklist}{post}".format(pre=noincludeFind[0],
                                                       tasklist=wikitext,
                                                       post=noincludeFind[1]);
            
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
    cli_parser.add_argument('-n', '--numpages', default=6,
                            help="number of pages in the list (default: 6)");

    
    # Option to control where the list of open tasks are
    cli_parser.add_argument('-p', '--page', default=None,
                            help="title of the page with the open tasks");

    # Option to control the size limit
    cli_parser.add_argument('-s', '--sizelimit', default=10240, type=int,
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
