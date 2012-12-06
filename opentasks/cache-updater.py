#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Program to update the popularity data
stored in the cache.  Usually run once
a day since stats.grok.se has per-day
summary data.
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

from datetime import datetime;

import oursql;

from opentasks import OpenTaskUpdater;

class CacheUpdater:
    def __init__(self, lang=u"en", cacheTable=None,
                 verbose=False):
        """
        Instantiate an object of this class, which will in turn update
        the cache database table.

        @param verbose: write informational output?
        @type verbose: bool
        """
        self.verbose = verbose;

        self.lang = lang;
        self.dbHost = u"{lang}wiki-p.userdb.toolserver.org".format(lang=self.lang);
        self.dbName = re.sub("-", "_", u"{lang}wiki_p".format(lang=self.lang));

        self.cacheTable = cacheTable;
        if not self.cacheTable:
            self.cacheTable = "u_nettrom.opentask_short"

        self.taskUpdater = OpenTaskUpdater(verbose=self.verbose,
                                           lang=self.lang)

    def update(self):
        """
        Update the cache database table.
        """

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

        # connect to database
        if not self.taskUpdater.connectDatabase(hostName=self.dbHost,
                                                dbName=self.dbName):
            sys.stderr.write(u"Error: Unable to connect to database, aborting!\n");
            return False;

        # We'll be using this database connection quite a bit, so give me a reference
        dbConn = self.taskUpdater.dbConn;

        # if time > 01:00, check if we need to update pop for everything
        updateAllPop = False;
        now = datetime.utcnow();
        if now.hour >= 1:
            with dbConn.cursor() as dbCursor:
                dbCursor.execute(getFirstPoptimeQuery);
                for (minTime,) in dbCursor:
                    # turn string into datetime object
                    minTime = datetime.strptime(minTime, "%Y%m%d%H%M%S");

                    if self.verbose:
                        sys.stderr.write(u"Info: testing min pop time {time} against {now}\n".format(time=minTime.strftime("%Y-%m-%d %H:%M:%S"), now=now.strftime("%Y-%m-%d %H:%M:%S")));
                    
                    # if it's not today we need to update
                    if minTime.day != now.day:
                        updateAllPop = True;

        if not updateAllPop:
            return False;
        
        # get a list of pages in need of pop updating
        with dbConn.cursor() as dbCursor:
            dbCursor.execute(getPoptimeQuery);
            changedPages = {}; # map page title to page ID
            for (pageId, pageTitle, popTime) in dbCursor:
                pageTitle = unicode(pageTitle, 'utf-8', errors='strict');
                pageTitle = re.sub("_", " ", pageTitle);

                # add if it doesn't have a pop update timestamp...
                if not popTime:
                    changedPages[pageTitle] = pageId;
                    continue;

                # or if the timestamp isn't from today
                popTime = datetime.strptime(popTime, "%Y%m%d%H%M%S");
                if popTime.day != now.day:
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

        # OK, all done
        return True;

def main():
    # parse cli options
    import argparse;
    
    cli_parser = argparse.ArgumentParser(
        description="Program to update Template:Opentask-short on English Wikipedia."
        );

    # Option to control language
    cli_parser.add_argument('-l', '--lang', default=u"en",
                            help="language code of the Wikipedia we're updating data for");

    # Test option
    cli_parser.add_argument('-t', '--tablename', default=None,
                            help='name of the cache database table');

    # Verbosity option
    cli_parser.add_argument('-v', '--verbose', action='store_true',
                            help='if set, informational output is written to stderr');
    
    args = cli_parser.parse_args();

    # instantiate object
    cacheUpdater = CacheUpdater(lang=args.lang,
                                cacheTable=args.tablename,
                                verbose=args.verbose);
    cacheUpdater.update();
        
    return;

if __name__ == "__main__":
    main();
