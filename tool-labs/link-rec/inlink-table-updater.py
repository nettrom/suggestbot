#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
Script to update the local table with inlink counts which is used
for penalising popular pages in the link recommender.

Copyright (C) 2012-2013 Morten Wang

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

# FIXME: import signal, and add a handler that will set an object variable
# if SIGUSR1 is received.  That way we can send a cautionary signal before
# the script is terminated, and clean up nicely and exit.  We'll add a check
# to the variable to the "while i < numPages" loop.

# FIXME: we might lose the connection to the database server during execution,
# so test if that happens, reconnect and re-execute.
# _mysql_exceptions.OperationalError: (2013, 'Lost connection to MySQL server during query')

from __future__ import with_statement;

import MySQLdb;
from MySQLdb import cursors;

import time;
import sys;
import os;
import re;

from datetime import datetime;

class UpdateRunningError(Exception):
    """
    Raised if the status table declares that this wiki is already being updated.
    """
    pass;

class UpdateTableError(Exception):
    """
    Raised if updating the status table does not result in one updated row.
    """
    pass;

class InlinkTableUpdater:
    def __init__(self, lang='en', verbose=False, sliceSize=100, commitSize=1000):
        '''
        Instantiate object.

        @param lang: Which language to update the table for.
        @type lang: str

        @param verbose: Write information output while running.
        @type verbose: bool

        @param sliceSize: Number of pages we'll grab inlink counts for at a time.
        @type sliceSize: int
        '''

        # Initialise options...
        self.lang = lang;
        self.verbose = verbose;
        self.sliceSize = sliceSize;
        self.commitSize = commitSize;

        # Database variables...
        self.dbConn = None;
        self.dbCursor = None;
        self.dbConfigFile = "~/replica.my.cnf";

        # Table name of the update table w/last update timestamp
        self.ilcUpdateTableName = "p50380g50553__ilc.inlinkcount_updates";

        # Table names of the inlink count tables, database names,
        # and host names, for the languages that we support.
        self.ilcTableNames = {'en': 'p50380g50553__ilc.enwiki_inlinkcounts',
                              'no': 'p50380g50553__ilc.nowiki_inlinkcounts',
                              'sv': 'p50380g50553__ilc.svwiki_inlinkcounts',
                              'pt': 'p50380g50553__ilc.ptwiki_inlinkcounts'};
        self.wikidbNames = {'en': 'enwiki_p',
                            'no': 'nowiki_p',
                            'sv': 'svwiki_p',
                            'pt': 'ptwiki_p'};
        self.hostnames = {'en': 'enwiki.labsdb',
                          'no': 'nowiki.labsdb',
                          'sv': 'svwiki.labsdb',
                          'pt': 'ptwiki.labsdb'};

    def dbConnect(self):
        '''
        Connect to the user database for our defined language.
        '''
        # Connect to user-db for the given language.
        # NOTE: We select the language's database, and then use
        #       databasename.tablename for the user table.
        try:
            self.dbConn = MySQLdb.connect(db=self.wikidbNames[self.lang],
                                          host=self.hostnames[self.lang],
                                          use_unicode=True,
                                          read_default_file=os.path.expanduser(self.dbConfigFile));
            # Create an SSDictCursor, standard fare.
            self.dbCursor = self.dbConn.cursor(cursors.SSDictCursor);
        except:
            self.dbConn = None;
            self.dbCursor = None;
            
        if self.dbConn:
            return True;
        else:
            return False;

    def dbDisconnect(self):
        '''
        Close the database connection.
        '''
        try:
            self.dbCursor.close();
            self.dbConn.close();
        except:
            pass;

        return;

    def setUpdateStatus(self):
        """
        Check the ilcu_update_running column, if set, raise error,
        else set it, commit, and return
        """
        checkRunningQuery = u"""SELECT ilcu_update_running
                                FROM {ilcUpdateTable}
                                WHERE ilcu_lang=%(lang)s""".format(ilcUpdateTable=self.ilcUpdateTableName);
        setRunningQuery = u"""UPDATE {ilcUpdateTable}
                              SET ilcu_update_running=1
                              WHERE ilcu_lang=%(lang)s""".format(ilcUpdateTable=self.ilcUpdateTableName);
        self.dbCursor.execute(checkRunningQuery, {'lang': self.lang});
        row = self.dbCursor.fetchone();
        self.dbCursor.fetchall(); # flush cursor

        if ord(row['ilcu_update_running']):
            raise UpdateRunningError;

        self.dbCursor.execute(setRunningQuery, {'lang': self.lang});
        if self.dbCursor.rowcount != 1:
            raise UpdateTableError;
        self.dbConn.commit();

        # OK, done.
        return;

    def clearUpdateStatus(self):
        """
        We're done updating, clear the bit in the update table.
        """
        setRunningQuery = u"""UPDATE {ilcUpdateTable}
                              SET ilcu_update_running=0
                              WHERE ilcu_lang=%(lang)s""".format(ilcUpdateTable=self.ilcUpdateTableName);
        self.dbCursor.execute(setRunningQuery, {'lang': self.lang});
        if self.dbCursor.rowcount != 1:
            raise UpdateTableError;
        self.dbConn.commit();

        # OK, done.
        return;

    def updateInlinkTable(self):
        '''
        Update the inlink count table for the given language.
        '''

        # Query to find articles that need to be deleted, the left join
        # means p.page_id is null for those pages.  This can take a little
        # while for large wikis.
        findDeletedPagesQuery = ur'''SELECT
              ilc_page_id FROM
              {ilcTableName} ilc LEFT JOIN page p
              ON ilc.ilc_page_id=p.page_id
              WHERE p.page_id IS NULL'''.format(ilcTableName=self.ilcTableNames[self.lang]);
        
        # Query to find new articles that need to be inserted, similar as the
        # previous query, except the roles are reversed.  We only care about
        # pages in main that are not redirects, though.
        findNewPagesQuery = ur'''SELECT
              page_id FROM
              page p LEFT JOIN {ilcTableName} ilc
              ON p.page_id=ilc.ilc_page_id
              WHERE p.page_namespace=0
              AND p.page_is_redirect=0
              AND ilc.ilc_page_id IS NULL'''.format(ilcTableName=self.ilcTableNames[self.lang]);

        # Query to find linked articles (namespace 0) from a given page ID
        getLinksQuery = ur'''SELECT p.page_id AS pageid
                             FROM pagelinks pl JOIN page p
                             ON (pl.pl_namespace=p.page_namespace
                             AND pl.pl_title=p.page_title)
                             WHERE pl.pl_namespace=0
                             AND pl.pl_from=%(pageid)s''';

        # Query to find the inlink count for a specific set of pages.
        getLinkCountQuery = ur'''SELECT
              p.page_id, COUNT(*) AS numlinks
              FROM page p JOIN pagelinks pl ON
              (p.page_namespace=pl.pl_namespace AND p.page_title=pl.pl_title)
              JOIN page p2 ON pl.pl_from=p2.page_id
              WHERE p.page_id IN ({idlist})
              AND p2.page_namespace=0
              GROUP BY p.page_id''';

        # Query to delete a page from the inlink count table
        deletePageQuery = ur'''DELETE FROM {ilcTableName}
              WHERE ilc_page_id=%s'''.format(ilcTableName=self.ilcTableNames[self.lang]);

        # Query to insert a new page into the inlink count table,
        # this uses a MySQL/MariaDB extension to SQL to update if the page exists
        insertPageQuery = ur'''INSERT INTO {ilcTableName}
              VALUES (%(pageid)s, %(numlinks)s)
              ON DUPLICATE KEY
              UPDATE ilc_numlinks=%(numlinks)s'''.format(ilcTableName=self.ilcTableNames[self.lang]);

        # Query to get the last update timestamp from the database
        getLastupdateQuery = ur'''SELECT ilcu_timestamp
                                  FROM {ilcUpdateTable}
                                  WHERE ilcu_lang=%(lang)s'''.format(ilcUpdateTable=self.ilcUpdateTableName);

        # Query to set the last update timestamp from the database
        setLastupdateQuery = ur'''UPDATE {ilcUpdateTable}
                                  SET ilcu_timestamp=%(timestamp)s
                                  WHERE ilcu_lang=%(lang)s'''.format(ilcUpdateTable=self.ilcUpdateTableName);

        # Query to get IDs and most recent edit timestamp
        # of non-redirecting articles (namespace 0)
        # updated after a given timestamp, from the recentchanges table
        getRecentChangesQuery = ur'''SELECT p.page_id AS pageid,
                                     MAX(rc.rc_timestamp) AS timestamp
                                     FROM recentchanges rc
                                     JOIN page p
                                     ON p.page_id=rc.rc_cur_id
                                     WHERE rc.rc_namespace=0
                                     AND p.page_is_redirect=0
                                     AND rc.rc_timestamp >= %(timestamp)s
                                     GROUP BY pageid''';

        # Query to get the newest timestamp of a main namespace
        # non-redirecting edit from recent changes
        getMostRecentchangeQuery = ur'''SELECT rc.rc_timestamp
                                        FROM recentchanges rc
                                        JOIN page p
                                        ON p.page_id=rc.rc_cur_id
                                        WHERE rc.rc_namespace=0
                                        AND p.page_is_redirect=0
                                        ORDER BY rc.rc_timestamp DESC
                                        LIMIT 1''';

        if self.verbose:
            sys.stderr.write("Info: {timestamp} finding pages to delete\n".format(timestamp=datetime.utcnow()));

        # 1: find pages that need to be deleted, and delete them
        self.dbCursor.execute(findDeletedPagesQuery);

        # There shouldn't be too many pages that need to be deleted every time,
        # so we can just do a list comprehension to make a list of tuples we
        # can feed to executemany().
        changedPages = [(row['ilc_page_id'],) for row in self.dbCursor.fetchall()];

        if self.verbose:
            sys.stderr.write("Info: found %d pages to delete.\n" % (len(changedPages),));

        if len(changedPages) > 0:
            self.dbCursor.executemany(deletePageQuery, changedPages);
            if self.verbose:
                sys.stderr.write("Info: deleted %d rows.\n" % (self.dbCursor.rowcount,));
            self.dbConn.commit(); # commit changes

        if self.verbose:
            sys.stderr.write("Info: {timestamp} completed page deletion, finding new pages...\n".format(timestamp=datetime.utcnow()));

        # 2: Find pages that need to be created, add those to our set of pages that
        #    need updating.
        self.dbCursor.execute(findNewPagesQuery);

        pagesToUpdate = set();
        done = False;
        while not done:
            row = self.dbCursor.fetchone();
            if not row:
                done = True;
                continue;

            pagesToUpdate.add(row['page_id']);
        
        if self.verbose:
            sys.stderr.write("Info: {timestamp} found {n} new pages, added to update list.\n".format(timestamp=datetime.utcnow(), n=len(pagesToUpdate)));

        # 3: Find pages that have been updated since our last update

        # Get timestamp of last update
        self.dbCursor.execute(getLastupdateQuery,
                              {'lang': self.lang});
        row = self.dbCursor.fetchone();
        self.dbCursor.fetchall(); # flush cursor
        lastUpdatetime = row['ilcu_timestamp'];

        # Timestamp of the last edit we checked from recentchanges,
        # to later be set as the new update time.
        newUpdateTime = datetime(1970, 1, 1, 0, 0, 0);

        # List of recently changed pages
        changedPages = [];

        if lastUpdatetime is None:
            # Grab the latest main namespace update from recentchanges.
            # Keep changedPages an empty list, since pagesToUpdate should
            # be all articles we need to update anyway.
            self.dbCursor.execute(getMostRecentchangeQuery);
            row = self.dbCursor.fetchone();
            self.dbCursor.fetchall(); # flush cursor
            newUpdateTime = datetime.strptime(row['rc_timestamp'], "%Y%m%d%H%M%S");
        else:
            # Get recent pages that have changed since then
            self.dbCursor.execute(getRecentChangesQuery,
                                  {'timestamp': lastUpdatetime.strftime("%Y%m%d%H%M%S")});
        
            done = False;
            while not done:
                row = self.dbCursor.fetchone();
                if not row:
                    done = True;
                    continue;

                changedPages.append(row['pageid']);
                rcTime = datetime.strptime(row['timestamp'], '%Y%m%d%H%M%S');
                if rcTime > newUpdateTime:
                    newUpdateTime = rcTime;

            if self.verbose:
                sys.stderr.write("Info: {timestamp} found {n} changed pages, grabbing links from them.\n".format(timestamp=datetime.utcnow(), n=len(changedPages)));

        # For each of the recently changed pages, grab the page IDs of the pages
        # they link to and add that to our pages in need of updating.
        # (Our basic assumption is that this takes less time than grabbing text
        #  and diffing to find the exact link added/removed)
        for pageID in changedPages:
            self.dbCursor.execute(getLinksQuery,
                                  {'pageid': pageID});
            # There's a reasonable limit to the number of articles and amount of
            # data retrieved, so fetchall() can be used.
            for row in self.dbCursor.fetchall():
                pagesToUpdate.add(row['pageid']);

        # This can now be cleaned up
        changedPages = None;

        if self.verbose:
            sys.stderr.write("Info: {timestamp} found {n} articles, starting inserting/updating\n".format(timestamp=datetime.utcnow(), n=len(pagesToUpdate)));

        # 4: Iterate over all changed pages and insert/update their inlink counts
        inlinkCount = 0;
        dataToInsert = [];
        pagesToUpdate = list(pagesToUpdate);
        i = 0;
        while i < len(pagesToUpdate):
            # create a list of strings of size self.sliceSize
            idList = [str(pageId) for pageId in pagesToUpdate[i:i+self.sliceSize]];
            self.dbCursor.execute(getLinkCountQuery.format(idlist=",".join(idList)));
            for row in self.dbCursor.fetchall():
                # Add to pages
                dataToInsert.append({'pageid': row['page_id'],
                                     'numlinks': row['numlinks']});

            # If we've grabbed links for a large enough number of articles,
            # insert/update and commit
            self.dbCursor.executemany(insertPageQuery,
                                          dataToInsert);
            dataToInsert = [];
            i += self.sliceSize;

            if i % self.commitSize == 0:
                self.dbConn.commit();
                if self.verbose:
                    sys.stderr.write("Info: {timestamp} committed {n} articles...\n".format(timestamp=datetime.utcnow(), n=self.commitSize));


        # Insert/update remaining articles and update the update timestamp
        #self.dbCursor.executemany(insertPageQuery,
        #                          dataToInsert);
        self.dbCursor.execute(setLastupdateQuery,
                              {'timestamp': newUpdateTime,
                               'lang': self.lang});
        self.dbConn.commit();

        if self.verbose:
            sys.stderr.write("Info: {timestamp} completed updating all pages\n".format(timestamp=datetime.utcnow()));

        # OK, we're done here
        return;
        
def main():
    '''
    Process command line arguments and run update.
    '''
    import argparse;

    cli_parser = argparse.ArgumentParser(
        description="Script to update user tables with inlink counts for all articles (pages in namespace 0)"
        );

    # Alternate configuration file...
    cli_parser.add_argument("-l", "--lang", type=str, default=u'en',
                            help="what language to update the inlink count table for (default: en)");

    # Alter the number of pages we grab inlink counts for at a time
    cli_parser.add_argument("-s", "--slice", type=int, default=100,
                            help='how many pages to update/commit a time (default: 100)');

    # Be verbose?
    cli_parser.add_argument("-v", "--verbose", action="store_true",
                          help="I can has kittehtalkzalot?");

    args = cli_parser.parse_args();
    
    # Create the updater object for the language
    myUpdater = InlinkTableUpdater(lang=args.lang, verbose=args.verbose,
                                   sliceSize=args.slice);

    if not myUpdater.dbConnect():
        sys.stderr.write("ERROR: Unable to connect to user database, exiting!\n");
        return;

    try:
        # Try to set status of this language as running.
        myUpdater.setUpdateStatus();

        # Helpful to output the beginning and end of a run, so we know what's been
        # going on.
        print "Update of inlink count for lang {lang} started at {timestamp}".format(lang=args.lang, timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"));
        myUpdater.updateInlinkTable();
        print "Update of inlink count for lang {lang} ended at {timestamp}".format(lang=args.lang, timestamp=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"));

        myUpdater.clearUpdateStatus();
        myUpdater.dbDisconnect();
    except UpdateRunningError:
        sys.stderr.write("ERROR: An update is already running for this wiki, exiting\n");
    except UpdateTableError:
        sys.stderr.write("ERROR: Failed to update the status table, exiting\n");

    # OK, done
    return;

if __name__ == "__main__":
    main();
