#!/usr/bin/python
# -*- coding: utf-8  -*-
'''
Webservice script to recommend articles based on links between them.

Copyright (C) 2011-2017 SuggestBot Dev Group

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

__version__ = "$Id$";

import os
import re
import json
import math
import logging
import operator

import db
import pymysql

from flipflop import WSGIServer
import cgi

from collections import defaultdict
from more_itertools import chunked

class DatabaseConnectionError(Exception):
    """
    Raised if we're unable to connect to a given database.
    """
    pass

# Based this off of Aaron Halfaker's API.py
class JSON():
    def __init__(self):
        self.returnVariable = None
        
    def setReturnVariable(self, retVar):
        self.returnVariable = retVar
        
    def getError(self, code, message):
        error = {}
        error['code'] = code
        error['message'] = message
        if self.returnVariable != None:
            return "%s=%s" % (self.returnVariable, json.dumps({"error": error}))
        else:
            return json.dumps({"error": error})
        
    def getSuccess(self, data, code=None, message=None):
        dump = {"success": data}
        if code != None and message != None:
            dump['warning'] = {
                "code": code,
                "message": message
                }
            
        if self.returnVariable != None:
            return "%s=%s" % (self.returnVariable, json.dumps(dump))
        else:
            return json.dumps(dump)
                
    def process(self, request):
        self.sendSuccess(request)

class LinkRecommender():
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

        self.db_config = "~/replica.my.cnf"

        ## Hostname, database and table name pattern for the Tool database
        self.tool_host = 'tools.db.svc.eqiad.wmflabs'
        self.tool_db = 's51172__ilc_p'
        self.tool_status_table = 'inlinkcount_updates'
        self.tool_ilc_table = '{}wiki_inlinkcounts'.format(lang)
        self.tool_temp_table = 'temp_inlinkcounts'

        ## Hostname and database name pattern for the replicated Wikipedia DBs
        self.wiki_db_name = '{}wiki_p'.format(lang)
        self.wiki_host = '{}wiki.web.db.svc.eqiad.wmflabs'.format(lang)

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
        with db.cursor(self.wiki_db_conn, 'dict') as db_cursor:
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

                except pymysql.Error as e:
                    logging.warning("Failed to get page links")
                    logging.warning("MySQL error {0}: {1}".format(e.args[0], e.args[1]))

                logging.info("rec_map now contains {0} items".format(len(self.rec_map)))

        # OK, done
        return()

    def get_recs(self, item_map=None, param_map=None):
        '''
        Get recommendations based on the given dictionary of items
        (keys are article page IDs, values are integers) and dictionary
        of parameters.

        @param item_map: items (article IDs) to recommend from
        @type item_map: dict

        @param param_map: parameters for the recommendations
        @type param_map: dict
        '''

        if not item_map or not param_map:
            return(None)

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

        # We create our dictionary of recommendations by fetching page IDs
        # for all items we've received that are not to be excluded,
        # resolving single redirects in the process and ignoring double redirects.
        # We also swap the keys in item_map from page titles to IDs
        # so we can use them for removal of edited articles later.
        self.rec_map = defaultdict(int)
        newItemMap = {}
        with db.cursor(self.wiki_db_conn, 'dict') as db_cursor:
            for item, val in item_map.items():
                try:
                    db_cursor.execute(
                        getPageIdQuery,
                        {'title': re.sub(b' ', b'_', item.encode('utf-8'))})
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
                        newItemMap[page_id] = val
                        if not self.exclude_item(item):
                            self.rec_map[page_id] = 0
                except pymysql.Error as e:
                    logging.warning("Failed to get page ID for {title}".format(title=item))
                    logging.warning("MySQL error {0}: {1}".format(e.args[0], e.args[1]))

        item_map = newItemMap
        newItemMap = None

        depth = 0
        max_depth = self.max_depth
        n_items = len(item_map)

        while (len(self.rec_map) - n_items) < self.nrecs \
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
        with db.cursor(self.tool_db_conn, 'dict') as db_cursor:
            for subset in chunked(self.rec_map.keys(), self.sliceSize):
                db_cursor.execute(get_inlinkcount_query.format(
                    ilc_table=self.tool_ilc_table,
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

        # Sort the recs in descending order by score,
        # limit size to self.nrecs if larger than that,
        # then recreate as a dict for mapping page IDs to values.
        self.rec_map = dict(sorted(self.rec_map.items(),
                                   key=operator.itemgetter(1),
                                   reverse=True)[:self.nrecs])

        logging.info("Sorted and attempted truncation to {nrecs}, rec set now contains {n} articles".format(nrecs=self.nrecs, n=len(self.rec_map)))

        recs = {}
        with db.cursor(self.wiki_db_conn, 'dict') as db_cursor:
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

        # Sort (again) and translate from tuples to dicts with item and value keys
        recs = sorted(recs.items(),
                      key=operator.itemgetter(1),
                      reverse=True)
        recs = [{'item': pageTitle, 'value': recVal} for (pageTitle, recVal) in recs]

        return(recs)

    def connect(self):
        '''Connect to the appropriate Wikipedia and user databases.'''
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

    def close(self):
        '''Close our database connections.'''
        try:
            self.wiki_db_conn.close()
            self.tool_db_conn.close()
        except:
            raise DatabaseConnectionError

        ## all ok
        return()

def app(envir, start_response):
    json_helper = JSON()
    
    # read items and params from request.
    formdata = cgi.FieldStorage(fp = envir['wsgi.input'], environ = envir)
    
    start_response('200 OK',
                   [('Content-type', 'application/json; charset=UTF-8')])
    
    if 'items' not in formdata or 'params' not in formdata:
        return(json_helper.getError(
            400, 'Bad Request: Items or parameters not supplied'))

    try:
        req_items = json.loads(formdata['items'].value)
        req_params = json.loads(formdata['params'].value)
    except:
        return(json_helper.getError(
            500, 'Unable to decode items or parameters as JSON.'))

    try:
        nrecs_param = int(req_params['nrecs'])
    except:
        nrecs_param = 10

    recommender = LinkRecommender(lang=req_params['lang'], nrecs=nrecs_param)

    if not recommender.checkLang():
        return(json_helper.getError(501, 'Error: Language not supported.'))

    if not recommender.checkNrecs():
        return(json_helper.getError(
            413, 'Error: Requested too many recommendations.'))

    try:
        recommender.connect()
    except DatabaseConnectionError:
        return(json_helper.getError(
            500, 'Error: Unable to connect to database servers.'))

    # Check that both item_map and param_map are dictionaries
    if (not isinstance(req_items, dict)) or (not isinstance(req_params, dict)):
        return(json_helper.getError(
            400, 'Error: Items and params not dictionaries.'))

    recs = recommender.get_recs(item_map=req_items, param_map=req_params)
    recommender.close()
    del(recommender) # done, can be GC'ed if possible
    return(json_helper.getSuccess(recs))

# Test code, uncomment and run from command line to verify functionality
#if __name__ == "__main__":
    # testItems = {
    #     u"Suhr Guitars": 1,
    #     u"Santa Cruz Guitar Company": 1,
    #     u"Bogner Amplification": 1,
    #     u"Bogner": 1,
    #     u"Collings Guitars": 1,
    #     u"Vibrato systems for guitar": 1,
    #     u"3rd bridge": 1,
    #     u"Tailed bridge guitar": 1,
    #     u"Floyd Rose": 1,
    #     u"Rosewood": 1,
    #     u"Fender Stratocaster": 1,
    #     u"Buzz Feiten": 1,
    #     u"Sadowsky": 1,
    #     u"List of guitar manufacturers": 1,
    #     u"James Tyler Guitars" :1,
    #     u"Tom Anderson Guitarworks": 1,
    #     u"Z.Vex Effects": 1,
    #     u"Roscoe Beck": 1,
    #     u"Tremstopper": 1,
    #     u"Fender Coronado": 1,
    #     u"Fender Swinger": 1,
    #     u"Humbucker": 1,
    #     u"Reb Beach": 1,
    #     u"Wayne Krantz": 1,
    #     u"Doug Aldrich": 1,
    #     u"Superstrat": 1,
    #     u"Guthrie Govan": 1,
    #     u"Blackstratblues": 1,
    #     u"Strat Plus": 1,
    #     u"Fender stratocaster ultra": 1,
    #     u"Fender Stratocaster Ultra": 1,
    #     u"Strat Ultra": 1,
    #     };
    # testLang = u"en";

    # testItems = {
    #     u"Luis Hernández": 1,
    #     u"Mexikói labdarúgó-válogatott": 1,
    #     u"Labdarúgó": 1,
    #     u"CA Boca Juniors": 1,
    #     u"CF Monterrey": 1
    #     }
    # testLang = u"hu";

    # testItems = {
    #     u"باشگاه فوتبال بوکا جونیورز": 1,
    #     u"فوتبال": 1,
    #     u"زبان اسپانیایی": 1,
    #     u"آرژانتین": 1};
    # testLang = u"fa";

# if __name__ == '__main__':
#     testItems = {"Findus":1,"Findus":1,"Åhléns":1,"Folkets Hus och Parker":1,"Mustang (spårvagn)":1,"Bräckelinjen":1,"Lundby landskommun":1,"Lundby landskommun":1,"Lundby socken, Västergötland":1,"Hisingsbron":1,"Klippan, Göteborg":1,"Hisingsbron":1,"Ryttarens torvströfabrik":1,"Rydals museum":1,"Samuel Owen":1,"Per Murén":1,"William Lindberg":1,"Robert Almström":1,"David Otto Francke":1,"William Chalmers":1,"Alexander Keiller":1,"Sven Erikson":1,"Rydahls Manufaktur":1,"Rydals Manufaktur":1,"Rydals museum":1,"Rydals museum":1,"Rydals museum":1,"Freedom Flotilla":1,"Generalmönsterrulla":1,"Generalmönstring":1,"Julia Cæsar":1,"Buskteater":1,"Buskis":1,"Persontåg":1,"Mustang (spårvagn)":1,"Mustang (spårvagn)":1,"Mustang (spårvagn)":1,"Mustang (spårvagn)":1,"Mustang (spårvagn)":1,"Lia Schubert-van der Bergen":1,"Johanna von Lantingshausen":1,"Gustav Gustavsson av Wasa":1,"Fredrika av Baden":1,"Ulrika Eleonora von Berchner":1,"Ulla von Höpken":1,"Stig T. Karlsson":1,"Tony Adams":1,"Zofia Potocka":1,"Lena Möller":1,"Lena Möller":1,"Novak Đoković":1,"Historiska kartor över Stockholm":1,"Afrikanska barbetter":1,"Aldosteron":1,"Cyklooxygenas":1,"Isoenzym":1,"Proenzym":1,"Strix (släkte)":1,"Simsnäppor":1,"Salskrake":1,"Jim Dine":1,"Fostervatten":1,"Svensk arkitektur":1,"Kuba":1,"Rune Gustafsson":1,"Föreningen för Stockholms fasta försvar":1,"Carl Johan Billmark":1,"Carl Johan Billmark":1,"Alfred Rudolf Lundgren":1,"Alfred Bentzer":1,"Svenska Brukarföreningen":1,"Karl August Nicander":1,}
#     testLang = u'sv'

#     logging.basicConfig(level=logging.DEBUG)

#     recommender = LinkRecommender(lang=testLang, nrecs=2500, verbose=True)
#     recommender.connect()
#     recs = recommender.get_recs(item_map=testItems, \
#                                     param_map=dict({u'nrecs': 2500,u'lang': testLang}))
#     recommender.close()
#     # print("Received {} recommendations.".format(len(recs)))
#     print(recs)
    
# Also, comment out these if you run from command line
WSGIServer(app).run()
