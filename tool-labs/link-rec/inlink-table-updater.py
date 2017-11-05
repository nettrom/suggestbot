#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
Script to update the local table with inlink counts which is used
for penalising popular pages in the link recommender.

Copyright (C) 2012-2017 SuggestBot Dev Group

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

import os
import re
import sys
import logging

from datetime import datetime
from more_itertools import chunked

import db

class DatabaseConnectionError(Exception):
    """
    Raised if we're unable to connect to a given database.
    """
    pass

class UpdateRunningError(Exception):
    """
    Raised if the status table declares that this wiki is already being updated.
    """
    pass

class UpdateTableError(Exception):
    """
    Raised if updating the status table does not result in one updated row.
    """
    pass

class InlinkTableUpdater:
    def __init__(self, lang,
                 slice_size=100, commit_size=1000):
        '''
        Instantiate object.

        :param lang: Which language to update the table for.
        :type lang: str

        :param slice_size: Number of pages we get inlink counts for at a time.
        :type slice_size: int

        :param commit_size: Number of updated pages between each DB commit
        :type commit_size: int
        '''

        # Initialise options...
        self.lang = lang
        self.slice_size = slice_size
        self.commit_size = commit_size

        ## Maximum number of days before a page's number of inlinks is updated
        self.max_age = 7

        ## Database connection to the replicated Wikipedia database,
        ## and the tool database with our inlink table.
        self.wiki_db_conn = None
        self.tool_db_conn = None

        self.db_config = "~/replica.my.cnf"

        ## Hostname, database and table name pattern for the Tool database
        self.tool_host = 'tools.db.svc.eqiad.wmflabs'
        self.tool_db = 's51172__ilc_p'
        self.tool_status_table = 'inlinkcount_updates'
        self.tool_ilc_table = '{}wiki_inlinkcounts'.format(lang)
        self.tool_temp_table = 'temp_inlinkcounts'

        ## Hostname and database name pattern for the replicated Wikipedia DBs
        self.wiki_db_name = '{}wiki_p'.format(lang)
        self.wiki_host = '{}wiki.analytics.db.svc.eqiad.wmflabs'.format(lang)

    def setUpdateStatus(self):
        """
        Check the ilcu_update_running column, if set, raise error,
        else set it, commit, and return
        """
        checkRunningQuery = u"""SELECT ilcu_update_running
                                FROM {status_table}
                                WHERE ilcu_lang=%(lang)s""".format(
                                    status_table=self.tool_status_table)
        setRunningQuery = u"""UPDATE {status_table}
                              SET ilcu_update_running=1
                              WHERE ilcu_lang=%(lang)s""".format(
                                  status_table=self.tool_status_table)

        with db.cursor(self.tool_db_conn, 'dict') as db_cursor:
            db_cursor.execute(checkRunningQuery, {'lang': self.lang})
            row = db_cursor.fetchone()
            db_cursor.fetchall() # flush cursor

            if row['ilcu_update_running']:
                raise UpdateRunningError

            db_cursor.execute(setRunningQuery, {'lang': self.lang})
            if db_cursor.rowcount != 1:
                raise UpdateTableError
            self.tool_db_conn.commit()

        # OK, done.
        return()

    def clearUpdateStatus(self):
        """
        We're done updating, clear the bit in the update table.
        """
        setRunningQuery = """UPDATE {status_table}
                             SET ilcu_update_running=0
                             WHERE ilcu_lang=%(lang)s""".format(
                                 status_table=self.tool_status_table)

        with db.cursor(self.tool_db_conn, 'dict') as db_cursor:
            db_cursor.execute(setRunningQuery, {'lang': self.lang})
            if db_cursor.rowcount != 1:
                raise UpdateTableError
            self.tool_db_conn.commit()

        # OK, done.
        return()

    def db_connect(self):
        '''
        Connect to the Tool database and the replicated Wikipedia database.
        '''
        try:
            self.wiki_db_conn = db.connect(self.wiki_host,
                                           self.wiki_db_name,
                                           self.db_config)
        except:
            raise DatabaseConnectionError

        try:
            self.tool_db_conn = db.connect(self.tool_host,
                                           self.tool_db,
                                           self.db_config)
        except:
            raise DatabaseConnectionError

        ## all ok
        return()

    def db_disconnect(self):
        '''
        Disconnect the database connections
        '''
        db.disconnect(self.wiki_db_conn)
        db.disconnect(self.tool_db_conn)
    
    def updateInlinkTable(self):
        '''
        Update the inlink count table for the given language.
        '''

        # Query to update the ILC table
        update_query = '''UPDATE {ilc_table}
                          SET ilc_numlinks=%(num_links)s,
                              ilc_age=0
                          WHERE ilc_page_id=%(page_id)s'''.format(
                              ilc_table=self.tool_ilc_table)
        
        ## Query to get page IDs of all pages in the Wikipedia we're processing
        wiki_pages_query = '''SELECT page_id
                              FROM page p
                              WHERE page_namespace=0
                              AND page_is_redirect=0'''

        ## Query to get page IDs of all pages of the Wikipedia we're processing
        ## that we have inlink counts for
        ilc_pages_query = '''SELECT ilc_page_id
                             FROM {ilc_table}'''.format(
                                 ilc_table=self.tool_ilc_table)
        
        # Query to find linked articles (namespace 0) from a set of pages
        getLinksQuery = '''SELECT p.page_id, p.page_is_redirect
                           FROM pagelinks pl JOIN page p
                           ON (pl.pl_namespace=p.page_namespace
                           AND pl.pl_title=p.page_title)
                           WHERE pl.pl_namespace=0
                           AND pl.pl_from IN ({pageidlist})
                           GROUP BY p.page_id'''

        # Query to resolve redirects (we discard double-redirects)
        resolveRedirectQuery = '''SELECT p.page_id, p.page_is_redirect
                                  FROM redirect r JOIN page p
                                  ON (r.rd_namespace=p.page_namespace
                                  AND r.rd_title=p.page_title)
                                  WHERE p.page_namespace=0
                                  AND rd_from IN ({pageidlist})'''

        # Query to insert a set of articles with no inlink count
        # and no age into an ILC table
        insert_query = '''INSERT INTO {ilc_table}
                          (ilc_page_id) VALUES (%s)'''.format(
                              ilc_table=self.tool_ilc_table)
        
        # Query to get a set of articles with their inlink count
        # so we can update their inlink counts
        get_inlinkcount_query = '''
            SELECT page_id AS ilc_page_id,
                   links.numlinks + IFNULL(redirlinks.numlinks, 0)
                   - IFNULL(redirs.numredirs, 0) AS ilc_numlinks
            FROM
            (SELECT p.page_id AS page_id,
                    count(*) AS numlinks
             FROM page p
             JOIN pagelinks pl
             ON (p.page_namespace=pl.pl_namespace
                 AND p.page_title=pl.pl_title)
             WHERE p.page_id IN ({idlist})
             AND pl.pl_from_namespace=0
             GROUP BY p.page_id
            ) AS links
            LEFT JOIN
            (SELECT p1.page_id,
                    count(*) AS numredirs
             FROM page p1
             JOIN redirect 
             ON (p1.page_namespace=rd_namespace
                 AND page_title=rd_title)
             JOIN page p2
             ON rd_from=p2.page_id
             WHERE p2.page_namespace=0
             AND p1.page_id IN ({idlist})
             GROUP BY page_id
            ) AS redirs
            USING (page_id)
            LEFT JOIN
            (SELECT p1.page_id,
                    count(*) AS numlinks
             FROM page p1
             JOIN redirect 
             ON (p1.page_namespace=rd_namespace
                 AND page_title=rd_title)
             JOIN page p2
             ON rd_from=p2.page_id
             JOIN pagelinks pl
             ON (p2.page_namespace=pl.pl_namespace
                 AND p2.page_title=pl.pl_title)
             WHERE p2.page_namespace=0
             AND pl.pl_from_namespace=0
             AND p1.page_id IN ({idlist})
             GROUP BY page_id
            ) AS redirlinks
            USING (page_id)'''

        # Query to delete a page from the inlink count table
        deletePageQuery = '''DELETE FROM {ilc_table}
                             WHERE ilc_page_id IN ({idlist})'''

        # Query to update the age of all pages
        update_age_query = '''UPDATE {ilc_table}
                              SET ilc_age = ilc_age + 1'''.format(
                                  ilc_table=self.tool_ilc_table)

        # Query to find all pages that have reached a given age
        get_aged_query = '''SELECT ilc_page_id
                            FROM {ilc_table}
                            WHERE ilc_age >= %(age)s'''.format(
                                ilc_table=self.tool_ilc_table)

        ## After an update, all articles that still have age >= self.max_age
        ## do not have any inlinks. So, we reset those.
        reset_aged_query = '''UPDATE {ilc_table}
                              SET ilc_numlinks=0, ilc_age=0
                              WHERE ilc_age >= %(age)s'''.format(
                                  ilc_table=self.tool_ilc_table)
        
        # Query to get the last update timestamp from the database
        getLastupdateQuery = '''SELECT ilcu_timestamp
                                FROM {status_table}
                                WHERE ilcu_lang=%(lang)s'''.format(
                                    status_table=self.tool_status_table)

        # Query to set the last update timestamp from the database
        setLastupdateQuery = '''UPDATE {status_table}
                                SET ilcu_timestamp=%(timestamp)s
                                WHERE ilcu_lang=%(lang)s'''.format(
                                    status_table=self.tool_status_table)

        # Query to get IDs and most recent edit timestamp
        # of non-redirecting articles (namespace 0)
        # updated after a given timestamp, from the recentchanges table
        getRecentChangesQuery = '''SELECT p.page_id AS pageid,
                                   MAX(rc.rc_timestamp) AS timestamp
                                   FROM recentchanges rc
                                   JOIN page p
                                   ON p.page_id=rc.rc_cur_id
                                   WHERE rc.rc_namespace=0
                                   AND p.page_is_redirect=0
                                   AND rc.rc_timestamp >= %(timestamp)s
                                   GROUP BY pageid'''

        # Query to get the newest timestamp of a main namespace
        # non-redirecting edit from recent changes
        getMostRecentchangeQuery = '''SELECT rc.rc_timestamp
                                      FROM recentchanges rc
                                      JOIN page p
                                      ON p.page_id=rc.rc_cur_id
                                      WHERE rc.rc_namespace=0
                                      AND p.page_is_redirect=0
                                      ORDER BY rc.rc_timestamp DESC
                                      LIMIT 1'''

        logging.info("finding pages to delete")

        ## 1: get a set of all page IDs of all Wikipedia pages
        all_wiki_pages = set()
        with db.cursor(self.wiki_db_conn, 'dict') as db_cursor:
            db_cursor.execute(wiki_pages_query)
            for row in db_cursor:
                all_wiki_pages.add(row['page_id'])
        
        ## 2: get a set of all page IDs in our corresponding inlink table
        all_ilc_pages = set()
        with db.cursor(self.tool_db_conn, 'dict') as db_cursor:
            db_cursor.execute(ilc_pages_query)
            for row in db_cursor:
                all_ilc_pages.add(row['ilc_page_id'])
        
        # 1: find pages that need to be deleted, and delete them
        deleted_pages = [str(p) for p in (all_ilc_pages - all_wiki_pages)]
        
        logging.info("found {} pages to delete.".format(len(deleted_pages)))

        i = 0
        with db.cursor(self.tool_db_conn) as db_cursor:
            for subset in chunked(deleted_pages, self.slice_size):
                db_cursor.execute(deletePageQuery.format(
                    ilc_table=self.tool_ilc_table,
                    idlist=",".join([str(p) for p in subset])))
            logging.info("deleted {} rows.".format(db_cursor.rowcount))

        self.tool_db_conn.commit() # commit changes
        deleted_pages = None ## This can be cleaned up now

        logging.info("completed page deletion, finding and inserting new articles...")

        # 2: Find pages that need to be created, add those to our set of pages
        #    that need updating.
        ## Note: named "pages_to_update" because we later add to this to get
        ## the whole set of pages we'll update inlink counts for.
        pages_to_update = all_wiki_pages - all_ilc_pages
        
        # 2.1 iterate over slices and insert the pages into the ILC table.
        logging.info("Inserting {} articles to the ILC table".format(len(pages_to_update)))

        i = 0
        with db.cursor(self.tool_db_conn) as db_cursor:
            for subset in chunked(pages_to_update, self.slice_size):
                db_cursor.executemany(insert_query,
                                      [(p) for p in subset])

            i += self.slice_size
            if i % self.commit_size == 0:
                logging.info("commiting {} article inserts".format(self.commit_size))
                self.tool_db_conn.commit()

        # Commit any non-commited inserts
        self.tool_db_conn.commit()

        logging.info("done inserting pages, looking for other articles to update")

        # 3: Find articles that have been updated since our last update

        # Get timestamp of last update
        with db.cursor(self.tool_db_conn, 'dict') as db_cursor:
            db_cursor.execute(getLastupdateQuery,
                              {'lang': self.lang})
            row = db_cursor.fetchone()
            db_cursor.fetchall() # flush cursor
            lastUpdatetime = row['ilcu_timestamp']
            
        # Timestamp of the last edit we checked from recentchanges,
        # to later be set as the new update time.
        newUpdateTime = datetime(1970, 1, 1, 0, 0, 0)

        ## Set of recently changed pages
        changedPages = set()

        if lastUpdatetime is None:
            with db.cursor(self.wiki_db_conn, 'dict') as db_cursor:
                # Grab the latest main namespace update from recentchanges.
                # Keep changedPages an empty list, no pages to update.
                db_cursor.execute(getMostRecentchangeQuery)
                row = db_cursor.fetchone()
                db_cursor.fetchall() # flush cursor
                newUpdateTime = datetime.strptime(
                    row['rc_timestamp'].decode('utf-8'), "%Y%m%d%H%M%S")
        else:
            with db.cursor(self.wiki_db_conn, 'dict') as db_cursor:
                # Get recent pages that have changed since then
                db_cursor.execute(
                    getRecentChangesQuery,
                    {'timestamp': lastUpdatetime.strftime("%Y%m%d%H%M%S")})
                for row in db_cursor:
                    changedPages.add(row['pageid'])
                    rcTime = datetime.strptime(
                        row['timestamp'].decode('utf-8'), '%Y%m%d%H%M%S')
                    if rcTime > newUpdateTime:
                        newUpdateTime = rcTime

        logging.info("found {} changed articles, grabbing links from them".format(len(changedPages)))

        # For each of the recently changed pages, grab the page IDs of the pages
        # they link to and add that to our pages in need of updating.
        # (Our basic assumption is that this takes less time than grabbing text
        #  and diffing to find the exact link added/removed)
        redirectsToResolve = set()
        with db.cursor(self.wiki_db_conn, 'dict') as db_cursor:
            for subset in chunked(changedPages, self.slice_size):
                db_cursor.execute(getLinksQuery.format(
                    pageidlist=",".join([str(p) for p in subset])))

                for row in db_cursor:
                    if row['page_is_redirect']:
                        redirectsToResolve.add(row['page_id'])
                    else:
                        pages_to_update.add(row['page_id'])

        # This can now be cleaned up
        changedPages = None

        logging.info("attempting to resolve {} redirects...".format(len(redirectsToResolve)))

        # Resolve single redirects, first listify it...
        redirectsToResolve = [str(pageid) for pageid in redirectsToResolve]
        with db.cursor(self.wiki_db_conn, 'dict') as db_cursor:
            for subset in chunked(redirectsToResolve, self.slice_size):
                db_cursor.execute(resolveRedirectQuery.format(
                    pageidlist=",".join([str(p) for p in subset])))
                for row in db_cursor:
                    if not row['page_is_redirect']:
                        pages_to_update.add(row['page_id'])

        logging.info("resolved redirects, found {} articles in need of an update.".format(len(pages_to_update)))

        # Also add any page that has not been updated in self.max_age days
        with db.cursor(self.tool_db_conn, 'dict') as db_cursor:
            db_cursor.execute(update_age_query)
            db_cursor.fetchall() # flush cursor
            self.tool_db_conn.commit()

            db_cursor.execute(get_aged_query,
                              {'age': self.max_age})
            for row in db_cursor:
                pages_to_update.add(row['ilc_page_id'])

        logging.info('added pages that have reached max age, now have {} articles in need of an update'.format(len(pages_to_update)))
            
        # 4: Iterate over all changed pages and update their inlink counts
        wiki_cursor = db.cursor(self.wiki_db_conn, 'dict')
        tool_cursor = db.cursor(self.tool_db_conn, 'dict')

        i = 0
        for subset in chunked(pages_to_update, self.slice_size):
            page_ids = [str(p) for p in subset]

            wiki_cursor.execute(get_inlinkcount_query.format(
                idlist=','.join(page_ids)))
            for row in wiki_cursor:
                tool_cursor.execute(update_query,
                                    {'num_links': row['ilc_numlinks'],
                                     'page_id': row['ilc_page_id']})
            i += self.slice_size
            if i % self.commit_size == 0:
                logging.info("updated {} articles in the ILC table.".format(i))
                self.tool_db_conn.commit()

        ## Commit any outstanding updates
        self.tool_db_conn.commit()

        ## Done fetching data from the Wiki, close that cursor
        wiki_cursor.close()

        ## Update age of all pages
        tool_cursor.execute(reset_aged_query,
                            {'age': self.max_age})
        logging.info("reset inlink count for {} aged rows in the ILC table, committing all changes".format(tool_cursor.rowcount))
        
        # Update the last updated timestamp
        tool_cursor.execute(setLastupdateQuery,
                            {'timestamp': newUpdateTime,
                             'lang': self.lang})
        self.tool_db_conn.commit()
        tool_cursor.close()

        logging.info("completed updating all articles")

        # OK, we're done here
        return()
        
def main():
    '''
    Process command line arguments and run update.
    '''
    import argparse

    cli_parser = argparse.ArgumentParser(
        description="Script to update user tables with inlink counts for all articles (pages in namespace 0)"
        )

    # The number of pages we grab inlink counts for at a time
    cli_parser.add_argument("-s", "--slice", type=int, default=100,
                            help='how many pages to update/commit a time (default: 100)')

    # Be verbose?
    cli_parser.add_argument("-v", "--verbose", action="store_true",
                          help="I can has kittehtalkzalot?")

    # Language we're updating
    cli_parser.add_argument("lang", type=str,
                            help="what language to update the inlink count table for")
    
    args = cli_parser.parse_args()

    # Set logging parameters for this script
    logLevel = logging.WARNING
    if args.verbose:
        logLevel = logging.INFO
    logging.basicConfig(format='%(asctime)s %(levelname)s:%(message)s',
                        level=logLevel)
    
    # Create the updater object for the language
    myUpdater = InlinkTableUpdater(args.lang,
                                   slice_size=args.slice)

    try:
        myUpdater.db_connect()
    except DatabaseConnectionError:
        logging.error("unable to connect to databases, exiting")
        return()

    try:
        # Try to set status of this language as running.
        myUpdater.setUpdateStatus()
        

        # Helpful to output the beginning and end of a run,
        # so we know what's been going on.
        print("Update of inlink count for lang {} started at {}".format(
            args.lang, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
        myUpdater.updateInlinkTable()
        print("Update of inlink count for lang {} ended at {}".format(
            args.lang, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
        myUpdater.clearUpdateStatus()
        myUpdater.db_disconnect()
    except UpdateRunningError:
        logging.error("update already running for {}wiki, exiting.".format(
            args.lang))
    except UpdateTableError:
        logging.error("failed to update the status table, exiting.")

    # OK, done
    return()

if __name__ == "__main__":
    main()
