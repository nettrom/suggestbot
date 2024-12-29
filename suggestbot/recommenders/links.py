#!/usr/bin/python
# -*- coding: utf-8  -*-
'''
Library to recommend articles based on links between them.

Copyright (C) 2011-2023 SuggestBot Dev Group

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

import os
import re
import json
import math
import logging
import operator

import MySQLdb
import MySQLdb.cursors

from collections import defaultdict
from more_itertools import chunked

class DatabaseConnectionError(Exception):
    """
    Raised if we're unable to connect to a given database.
    """
    pass

class Recommender():
    def __init__(self, lang='en', nrecs=10, max_depth=2, verbose=False,
                 sliceSize=25, n_docs=1000):
        '''
        Initialize the link recommender object.

        @param lang: Language code of the language we're recommending for
        @type lang: str

        @param nrecs: Number of recommendations we need to return
        @type nrecs: int

        @param max_depth: Maximum search depth.
        @type max_depth: int

        @param verbose: Write informational output?
        @type verbose: bool

        @param sliceSize: How many articles we find links for at a time.
        @type sliceSize: int

        @param n_docs: The number of links used as a basis to regard an article
                       as popular.
        @type n_docs: int
        '''
        self.lang = lang
        self.nrecs = nrecs
        self.max_depth = max_depth
        self.verbose = verbose
        self.sliceSize = sliceSize
        self.n_docs = n_docs

        ## Database connection to the replicated Wikipedia database,
        ## and the tool database with our inlink count tables.
        self.wiki_db_conn = None
        self.tool_db_conn = None

        self.db_config = os.path.expandvars('$HOME/replica.my.cnf')

        ## Hostname, database and table name pattern for the Tool database
        self.tool_host = 'tools.db.svc.eqiad.wmflabs'
        self.tool_db = 's51172__ilc_p'
        self.tool_status_table = 'inlinkcount_updates'
        self.tool_ilc_table = '{lang_code}wiki_inlinkcounts'
        self.tool_temp_table = 'temp_inlinkcounts'

        ## Hostname and database name pattern for the replicated Wikipedia DBs
        self.wiki_db_name = '{lang_code}wiki_p'
        self.wiki_host = '{lang_code}wiki.analytics.db.svc.eqiad.wmflabs'

        # Regular expressions for things that we exclude.
        # Note that we use match() to anchor these at the beginning
        # of the string, instead of using "^" and search(), and that we use
        # non-capturing groups since we're not using the results.
        # Also note that Swedish and Norwegian Wikipedia specify dates as
        # "xx. Januar" rather than "January 1" as they do in English.
        self.months = {
            'en': r'(January|February|March|April|May|June|July|August|September|October|November|December)[ _]\d+',
            'no': r'\d+\.[ _]+(:[Jj]anuar|[Ff]ebruar|[Mm]ars|[Aa]pril|[Mm]ai|[Jj]uni|[Jj]uli|[Aa]ugust|[Ss]eptember|[Oo]ktober|[Nn]ovember|[Dd]esember)',
            'sv': r'\d+\.[ _]+(:[Jj]anuari|[Ff]ebruari|[Mm]ars|[Aa]pril|[Mm]aj|[Jj]uni|[Jj]uli|[Aa]ugusti|[Ss]eptember|[Oo]ktober|[Nn]ovember|[Dd]ecember)',
            'pt': r'\d+[ _]+de[ _]+(:[Jj]aneiro|[Ff]evereiro|[Mm]arço|[Aa]bril|[Mm]aio|[Jj]unho|[Jj]ulho|[Aa]gosto|[Ss]etembro|[Oo]utubro|[Nn]ovembro|[Dd]ezembro)',
            'hu': r'Január|Február|Március|Április|Május|Június|Július|Augusztus|Szeptember|Október|November|December',
            'fa': 'دسامب|نوامب|اکتب|سپتامب|اوت|ژوئی|ژوئن|مه|آوریل|مارس|فوریه|ژانویه',
            'ru': r'(:Январь|Февраль|Март|Апрель|Май|Июнь|Июль|Август|Сентябрь|Октябрь|Ноябрь|Декабрь)|(:\d+[ _]+(:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря))',
            ## Note the negative lookahead (?! ...) to allow us to match
            ## the actual months, but not dates.
            'fr': r'(\d+[ _](?!.*[ _]\d+$))?([Jj]anvier|[Ff]évrier|[Mm]ars|[Aa]vril|[Mm]ai|[Jj]uin|[Jj]uillet|[Aa]oût|[Ss]eptembre|[Oo]ctobre|[Nn]ovembre|[Dd]écembre)(\d+)?',
            }

        # Note: compatible with both ' '  and '_' as spaces
        self.lists = {
            'en': r'^List[ _]of[ _]',
            'no': r'^Liste[ _]over[ _]',
            'sv': r'^Lista[ _]över[ _]',
            'pt': r'^Lista[ _]de[ _]',
            'hu': r'[ _]listája$',
            'fa': r'^فهرست',
            'ru': r'(^Список|(:Алфавитный[ _]|Хронологический[ _])список)|—[ _]список',
            'fr': r"[Ll]iste[ _]d[e']",
            }

        # Compile the regular expressions
        self.months_re = dict()
        self.lists_re = dict()
        for lang in self.months.keys():
            self.months_re[lang] = re.compile(self.months[lang], re.U|re.I)
            self.lists_re[lang] = re.compile(self.lists[lang], re.U|re.I)

        self.rec_map = defaultdict(int)

    def checkLang(self):
        '''
        Were we instantiated with a language we support?
        '''
        return(self.lang in self.lists)

    def checkNrecs(self):
        if self.nrecs > 5000:
            return(False)
        return(True)

    def setLang(self, lang=None):
        if lang:
            self.lang = lang

    def getLang(self):
        return(self.lang)

    def exclude_item(self, item=None):
        if not item:
            return(False)

        # date
        ## FIXME: what's the false positive rate on this one?
        if re.search(r'\d{4}', item):
            return(True)

        # is a list
        if self.lists_re[self.lang].search(item):
            return(True)
        
        # starting with a month name
        if self.months_re[self.lang].match(item):
            return(True)

        return(False)

    def get_links(self):
        '''Get all links from the articles in self.rec_map'''
        if not self.rec_map:
            return(None)

        # SQL query to get linked articles from an input set of page IDs.
        # Single redirects are resolved, double redirects are marked
        # as such so they can be ignored.  Inlink counts for both links
        # and redirects (if present) are also listed.
        getLinkedPagesQuery = r'''SELECT link.page_id AS lpage,
                                         link.page_title AS lpage_title,
                                         redir.page_id AS rpage,
                                         redir.page_title AS rpage_title,
                                         redir.page_is_redirect AS is_double_redirect
                                  FROM pagelinks AS pl
                                  JOIN page AS link
                                  ON (pl.pl_namespace=link.page_namespace
                                      AND pl.pl_title=link.page_title)
                                  LEFT JOIN redirect AS rd
                                  ON link.page_id=rd.rd_from
                                  LEFT JOIN page AS redir
                                  ON (rd.rd_namespace=redir.page_namespace
                                      AND rd.rd_title=redir.page_title)
                                  WHERE pl.pl_namespace=0
                                  AND pl.pl_from IN ({idlist})'''

        logging.info("Ready to find recs based on {n} articles.".format(n=len(self.rec_map)))

        # Get a snapshot of the current set of recommendations,
        # and extend recommendations based on it.
        current_recs = list(self.rec_map.keys())
        i = 0
        with self.wiki_db_conn.cursor(MySQLdb.cursors.DictCursor) as db_cursor:
            for subset in chunked(current_recs, self.sliceSize):
                logging.info("fetching links for slice {}".format(i))

                # Get linked pages
                try:
                    db_cursor.execute(
                        getLinkedPagesQuery.format(
                            idlist=','.join([str(p) for p in subset])))
                    for row in db_cursor:
                        # If the link is a double redirect, we skip it
                        if row['is_double_redirect']:
                            continue
                        
                        pageId = None
                        pageTitle = None
                        numLinks = None

                        ## If the page is a redirect, use the rediected page
                        if row['rpage']:
                            pageId = row['rpage']
                            pageTitle = row['rpage_title'].decode('utf-8')
                        else:
                            pageId = row['lpage']
                            pageTitle = row['lpage_title'].decode('utf-8')
                        
                        # Does the link go to a page that we exclude?
                        # (e.g. lists, dates)
                        if self.exclude_item(pageTitle):
                            continue

                        self.rec_map[pageId] += 1

                except MySQLdb.Error as e:
                    logging.warning("Failed to get page links")
                    logging.warning("MySQL error {0}: {1}".format(e.args[0], e.args[1]))

                logging.info("rec_map now contains {0} items".format(len(self.rec_map)))
                i += 1
                
        # OK, done
        return()

    def recommend(self, user, lang, user_edits, n_recs):
        '''
        Get recommendations based on the given dictionary of items
        (keys are article page IDs, values are integers) and dictionary
        of parameters.

        @param user: user name of the user we're recommending for
        @type user: str

        @param lang: language code of the wiki we're recommending for
        @type lang: str

        @param user_edits: titles of the articles the user has edited
        @type user_edits: list

        @param n_recs: number of recommendations we are to return
        @type n_recs: int
        '''

        # Query to get the page ID of a given page and if it's
        # a redirect also get the page ID of the page it redirects to
        getPageIdQuery = '''SELECT p.page_id, p.page_is_redirect,
                                   redir.page_id AS redir_page_id,
                                   redir.page_is_redirect AS double_redirect
                            FROM page p LEFT JOIN redirect rd
                            ON p.page_id=rd.rd_from
                            LEFT JOIN page redir
                            ON (rd.rd_namespace=redir.page_namespace
                                AND rd.rd_title=redir.page_title)
                            WHERE p.page_namespace=0
                            AND p.page_title=%(title)s'''

        # Query to get the page titles for a list of page IDs
        getPageTitlesQuery = '''SELECT page_id, page_title
                                FROM page
                                WHERE page_id IN ({idlist})'''

        # Query to get inlink counts for found pages
        get_inlinkcount_query = '''SELECT ilc_page_id, ilc_numlinks
                                   FROM {ilc_table}
                                   WHERE ilc_page_id IN ({idlist})'''

        # Connect to the database servers using the correct language
        self.connect(lang)
        
        # We create our dictionary of recommendations by fetching page IDs
        # for all items we've received that are not to be excluded,
        # resolving single redirects in the process and ignoring double redirects.
        # We also swap the keys in item_map from page titles to IDs
        # so we can use them for removal of edited articles later.
        self.rec_map = defaultdict(int)
        newItemMap = {}
        with self.wiki_db_conn.cursor(MySQLdb.cursors.DictCursor) as db_cursor:
            for page_title in user_edits:
                try:
                    db_cursor.execute(
                        getPageIdQuery,
                        {'title':
                         re.sub(b' ', b'_', page_title.encode('utf-8'))
                         }
                    )
                    row = db_cursor.fetchone()
                    db_cursor.fetchall() # flush cursor
                    page_id = None
                    if row:
                        # Article exists, set pageId accordingly
                        if not row['page_is_redirect']:
                            page_id = row['page_id']
                        elif not row ['double_redirect']:
                            page_id = row['redir_page_id']

                    if page_id:
                        # Store `val` in new item map, add page ID to rec seed
                        # if not an item to exclude
                        newItemMap[page_id] = 1
                        if not self.exclude_item(page_title):
                            self.rec_map[page_id] = 0
                except MySQLdb.Error as e:
                    logging.warning("Failed to get page ID for {title}".format(title=page_title))
                    logging.warning("MySQL error {0}: {1}".format(e.args[0], e.args[1]))

        item_map = newItemMap
        newItemMap = None

        depth = 0
        max_depth = self.max_depth
        n_items = len(item_map)

        while (len(self.rec_map) - n_items) < n_recs \
                and depth < max_depth:
            logging.info("Calling get_links(), with {n} recs in the map.".format(n=len(self.rec_map)))
            self.get_links()
            depth += 1

        # Delete any articles that the user already edited
        for pageId in item_map.keys():
            if pageId in self.rec_map:
                del(self.rec_map[pageId])

        logging.info("Deleted edited pages, rec set now contains {n} articles".format(n=len(self.rec_map)))

        ## Grab inlink counts and use that to calculate new scores
        with self.tool_db_conn.cursor(MySQLdb.cursors.DictCursor) as db_cursor:
            for subset in chunked(self.rec_map.keys(), self.sliceSize):
                db_cursor.execute(get_inlinkcount_query.format(
                    ilc_table=self.tool_ilc_table.format(lang_code = lang),
                    idlist=','.join([str(p) for p in subset])))

                for row in db_cursor:
                    # Classic idf = log(N/df).  We'd like to not give
                    # singly-linked items quite so much clout, and so
                    # we put the highest weight on things that have
                    # a few links.  How to estimate?  The "right" way
                    # is to make it a parameter and test against people.
            
                    # calculate penalty for popular links using
                    # a classic idf = log(N/df)
                    
                    idf = math.log(
                        self.n_docs/math.fabs(math.exp(3)-row['ilc_numlinks']))
            
                    self.rec_map[row['ilc_page_id']] *= idf

        logging.info('Applied TF/IDF scores to all pages, rec set now contains {} articles'.format(len(self.rec_map)))
                    
        # Sort the recs in descending order by score,
        # limit size to self.nrecs if larger than that,
        # then recreate as a dict for mapping page IDs to values.
        self.rec_map = dict(sorted(self.rec_map.items(),
                                   key=operator.itemgetter(1),
                                   reverse=True)[:n_recs])

        logging.info("Sorted and attempted truncation to {nrecs}, rec set now contains {n} articles".format(nrecs = n_recs, n=len(self.rec_map)))

        recs = {}
        with self.wiki_db_conn.cursor(MySQLdb.cursors.DictCursor) as db_cursor:
            for subset in chunked(self.rec_map.keys(), self.sliceSize):
                try:
                    db_cursor.execute(getPageTitlesQuery.format(
                        idlist=','.join([str(p) for p in subset])))
                    for row in db_cursor:
                        pageId = row['page_id']
                        pageTitle = row['page_title'].decode('utf-8')
                        pageTitle = re.sub('_', ' ', pageTitle)
                        recs[pageTitle] = self.rec_map[pageId]

                except pymysql.Error as e:
                    logging.warning("Failed to get page titles")
                    logging.warning("MySQL error {0}: {1}".format(e.args[0], e.args[1]))

        # Disconnect from the database servers
        self.close()
                    
        # Sort (again) and translate from tuples to dicts with item and value keys
        recs = sorted(recs.items(),
                      key=operator.itemgetter(1),
                      reverse=True)
        recs = [{'item': pageTitle, 'value': recVal} for (pageTitle, recVal) in recs]

        return(recs)

    def connect(self, lang):
        '''
        Connect to the appropriate Wikipedia and user databases.
        
        @param lang: language code of the wiki we're working with
        @type lang: str
        '''
        try:
            self.wiki_db_conn = MySQLdb.connect(
                host = self.wiki_host.format(lang_code = lang),
                database = self.wiki_db_name.format(lang_code = lang),
                read_default_file = self.db_config,
                charset = 'utf8'
        )
        except:
            raise DatabaseConnectionError

        try:
            self.tool_db_conn = MySQLdb.connect(
                host = self.tool_host,
                database = self.tool_db.format(lang_code = lang),
                read_default_file = self.db_config,
                charset = 'utf8'
            )
        except:
            raise DatabaseConnectionError

        ## all ok
        return()

    def close(self):
        '''Close our database connections.'''
        try:
            self.wiki_db_conn.close()
            self.tool_db_conn.close()
        except:
            raise DatabaseConnectionError

        ## all ok
        return()
