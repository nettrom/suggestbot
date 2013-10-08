#!/usr/bin/python
# -*- coding: utf-8  -*-
'''
Webservice script to recommend articles based on links between them.

Copyright (C) 2011-2013 Morten Wang

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

from __future__ import with_statement;

__version__ = "$Id$";

import os;
import re;
import math;
import operator;

import logging;

import simplejson as json;

import MySQLdb;
from MySQLdb import cursors;

from flup.server.fcgi import WSGIServer;
import cgi;

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
        self.lang = lang;
        self.nrecs = nrecs;
        self.max_depth = max_depth;
        self.verbose = verbose;
        self.sliceSize = sliceSize;
        self.n_docs = n_docs;

        self.dbNames = {'en': 'enwiki_p',
                        'no': 'nowiki_p',
                        'sv': 'svwiki_p',
                        'pt': 'ptwiki_p',
                        'hu': 'huwiki_p',
                        'fa': 'fawiki_p',};
        self.hostnames = {'en': 'enwiki.labsdb',
                          'no': 'nowiki.labsdb',
                          'sv': 'svwiki.labsdb',
                          'pt': 'ptwiki.labsdb',
                          'hu': 'huwiki.labsdb',
                          'fa': 'fawiki.labsdb'};
        # Table name of the inlink count table in our user database.
        self.tableNames = {'en': 'p50380g50553__ilc.enwiki_inlinkcounts',
                           'no': 'p50380g50553__ilc.nowiki_inlinkcounts',
                           'sv': 'p50380g50553__ilc.svwiki_inlinkcounts',
                           'pt': 'p50380g50553__ilc.ptwiki_inlinkcounts',
                           'hu': 'p50380g50553__ilc.huwiki_inlinkcounts',
                           'fa': 'p50380g50553__ilc.fawiki_inlinkcounts'};

        self.dbConn = None;
        self.dbCursor = None;
        self.dbConfigFile = "~/replica.my.cnf";

        # Regular expressions for things that we exclude.
        # Note that we use match() to anchor these at the beginning
        # of the string, instead of using "^" and search(), and that we use
        # non-capturing groups since we're not using the results.
        # Also note that Swedish and Norwegian Wikipedia specify dates as "xx. Januar" rather
        # than "January 1" as they do in English.
        self.months = {
            u'en': ur'January|February|March|April|May|June|July|August|September|October|November|December',
            u'no': ur'\d+\.[ _]+(:[Jj]anuar|[Ff]ebruar|[Mm]ars|[Aa]pril|[Mm]ai|[Jj]uni|[Jj]uli|[Aa]ugust|[Ss]eptember|[Oo]ktober|[Nn]ovember|[Dd]esember)',
            u'sv': ur'\d+\.[ _]+(:[Jj]anuari|[Ff]ebruari|[Mm]ars|[Aa]pril|[Mm]aj|[Jj]uni|[Jj]uli|[Aa]ugusti|[Ss]eptember|[Oo]ktober|[Nn]ovember|[Dd]ecember)',
            u'pt': ur'\d+[ _]+de[ _]+(:[Jj]aneiro|[Ff]evereiro|[Mm]arço|[Aa]bril|[Mm]aio|[Jj]unho|[Jj]ulho|[Aa]gosto|[Ss]etembro|[Oo]utubro|[Nn]ovembro|[Dd]ezembro)',
            u'hu': ur'Január|Február|Március|Április|Május|Június|Július|Augusztus|Szeptember|Október|November|December',
            u'fa': 'دسامب|نوامب|اکتب|سپتامب|اوت|ژوئی|ژوئن|مه|آوریل|مارس|فوریه|ژانویه'
            };

        # Note: compatible with both ' '  and '_' as spaces
        self.lists = {
            u'en': ur'^List[ _]of[ _]',
            u'no': ur'^Liste[ _]over[ _]',
            u'sv': ur'^Lista[ _]över[ _]',
            u'pt': ur'^Lista[ _]de[ _]',
            u'hu': ur'[ _]listája$',
            u'fa': ur'^فهرست'
            };

        # Compile the regular expressions
        self.months_re = dict();
        self.lists_re = dict();
        for lang in self.months.keys():
            self.months_re[lang] = re.compile(self.months[lang], re.U|re.I);
            self.lists_re[lang] = re.compile(self.lists[lang], re.U|re.I);

        self.rec_map = dict();

    def checkLang(self):
        if not self.lang in self.dbNames:
	    return False;
        return True;

    def checkNrecs(self):
        if self.nrecs > 5000:
            return False;
        return True;

    def setLang(self, lang=None):
        if lang:
            self.lang = lang;

    def getLang(self):
        return self.lang;

    def exclude_item(self, item=None):
        if not item:
            return False;

        # date
        if re.search(r'\d{4}', item):
            return True;

        # is a list
        if self.lists_re[self.lang].search(item):
            return True;
        
        # starting with a month name
        if self.months_re[self.lang].match(item):
            return True;

        return False;

    def get_links(self):
        '''Get all links from the articles in self.rec_map'''
        if not self.rec_map:
            return None;

        # SQL query to get linked articles from an input set of page IDs.
        # Single redirects are resolved, double redirects are marked
        # as such so they can be ignored.  Inlink counts for both links
        # and redirects (if present) are also listed.
        getLinkedPagesQuery = ur'''SELECT link.page_id AS lpage,
                                          link.page_title AS lpage_title,
                                          linkilc.ilc_numlinks AS lpage_numlinks,
                                          redir.page_id AS rpage,
                                          redir.page_title AS rpage_title,
                                          redirilc.ilc_numlinks AS rpage_numlinks,
                                          redir.page_is_redirect AS is_double_redirect
                                   FROM pagelinks AS pl
                                   JOIN page AS link
                                   ON (pl.pl_namespace=link.page_namespace
                                       AND pl.pl_title=link.page_title)
                                   LEFT JOIN redirect AS rd
                                   ON link.page_id=rd.rd_from
                                   LEFT JOIN {ilcTable} AS linkilc
                                   ON link.page_id=linkilc.ilc_page_id
                                   LEFT JOIN page AS redir
                                   ON (rd.rd_namespace=redir.page_namespace
                                       AND rd.rd_title=redir.page_title)
                                   LEFT JOIN {ilcTable} AS redirilc
                                   ON redir.page_id=redirilc.ilc_page_id
                                   WHERE pl.pl_namespace=0
                                   AND pl.pl_from IN ({pageidlist})'''

        logging.info("Ready to find recs based on {n} articles.".format(n=len(self.rec_map)))

        # Get a snapshot of the current set of recommendations,
        # and extend recommendations based on it.
        current_recs = self.rec_map.keys()
        i = 0
        while i < len(current_recs):
            logging.info("Fetching links for slice {i}:{j}".format(i=i, j=i+self.sliceSize))

            # Build a comma-separated string out of a subset of the page IDs
            pageIdSubset = u",".join(str(pageid) for pageid in current_recs[i:i+self.sliceSize])

            # Get linked pages
            try:
                self.dbCursor.execute(getLinkedPagesQuery.format(ilcTable=self.tableNames[self.lang],
                                                                 pageidlist=pageIdSubset))
                done = False
                while not done:
                    row = self.dbCursor.fetchone()
                    if not row:
                        done = True
                        continue

                    # If the link is a double redirect, we skip it
                    if row['is_double_redirect']:
                        continue

                    pageId = None
                    pageTitle = None
                    numLinks = None

                    # Is the page a redirect to a page that we exclude?
                    if row['rpage']:
                        pageId = row['rpage']
                        pageTitle = unicode(row['rpage_title'], 'utf-8', errors='strict');
                        numLinks = row['rpage_numlinks']
                    else:
                        pageId = row['lpage']
                        pageTitle = unicode(row['lpage_title'], 'utf-8', errors='strict');
                        numLinks = row['lpage_numlinks']
                        
                    # Does the link go to a page that we exclude? (e.g. lists, dates)
                    if self.exclude_item(pageTitle):
                        continue;

                    if not numLinks:
                        numLinks = 0

                    # Classic idf = log(N/df).  We'd like to not give singly-linked
                    # items quite so much clout, and so we put the highest weight
                    # on things that have a few links.  How to estimate?  The
                    # "right" way is to make it a parameter and test against people.

                    # calculate penalty for popular links using a classic idf = log(N/df)
                    idf = math.log(self.n_docs/math.fabs(math.exp(3)-numLinks))

                    try:
                        self.rec_map[pageId] += idf;
                    except KeyError:
                        self.rec_map[pageId] = idf;

            except MySQLdb.Error, e:
                logging.warning("Failed to get page links");
                logging.warning("MySQL error {0}: {1}".format(e.args[0], e.args[1]));

            # OK, done with this batch, move along...
            i += self.sliceSize;

            logging.info("rec_map now contains {0} items".format(len(self.rec_map)));

        # OK, done
        return;

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
            return None

        # Query to get the page ID of a given page and if it's
        # a redirect also get the page ID of the page it redirects to
        getPageIdQuery = ur'''SELECT p.page_id, p.page_is_redirect,
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
        getPageTitlesQuery = ur'''SELECT page_id, page_title
                                  FROM page
                                  WHERE page_id IN ({pageidlist})'''

        # We create our dictionary of recommendations by fetching page IDs
        # for all items we've received that are not to be excluded,
        # resolving single redirects in the process and ignoring double redirects.
        # We also swap the keys in item_map from page titles to IDs
        # so we can use them for removal of edited articles later.
        self.rec_map = {}
        newItemMap = {}
        for item, val in item_map.iteritems():
            try:
                self.dbCursor.execute(getPageIdQuery,
                                      {'title': re.sub(' ', '_', item.encode('utf-8'))})
                row = self.dbCursor.fetchone()
                self.dbCursor.fetchall() # flush cursor
                pageId = None
                if row:
                    # Article exists, set pageId accordingly
                    if not row['page_is_redirect']:
                        pageId = row['page_id']
                    elif not row ['double_redirect']:
                        pageId = row['redir_page_id']

                if pageId:
                    # Switch item map to pageId->val, add to rec seed
                    # if not an item to exclude.
                    newItemMap[pageId] = val
                    if not self.exclude_item(item):
                        self.rec_map[pageId] = val
            except MySQLdb.Error, e:
                logging.warning(u"Failed to get page ID for {title}".format(title=item))
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

        # Sort the recs in descending order by score,
        # limit size to self.nrecs if larger than that,
        # then recreate as a dict for mapping page IDs to values.
        self.rec_map = dict(sorted(self.rec_map.iteritems(),
                                   key=operator.itemgetter(1),
                                   reverse=True)[:self.nrecs])

        logging.info("Sorted and attempted truncation to {nrecs}, rec set now contains {n} articles".format(nrecs=self.nrecs, n=len(self.rec_map)))

        recs = {}
        i = 0
        recIds = self.rec_map.keys()
        while i < len(recIds):
            recSubset = recIds[i:i+self.sliceSize]
            recSubset = u",".join(str(pageid) for pageid in recSubset)
            try:
                self.dbCursor.execute(getPageTitlesQuery.format(pageidlist=recSubset))
                for row in self.dbCursor.fetchall():
                    pageId = row['page_id']
                    pageTitle = unicode(row['page_title'], 'utf-8', errors='strict')
                    pageTitle = re.sub('_', ' ', pageTitle)
                    recs[pageTitle] = self.rec_map[pageId]

            except MySQLdb.Error, e:
                logging.warning("Failed to get page titles")
                logging.warning("MySQL error {0}: {1}".format(e.args[0], e.args[1]))

            # ok, advance
            i += self.sliceSize

        # Sort (again) and translate from tuples to dicts with item and value keys
        recs = sorted(recs.iteritems(),
                      key=operator.itemgetter(1),
                      reverse=True)
        recs = [{'item': pageTitle, 'value': recVal} for (pageTitle, recVal) in recs]

        return recs;

    def connect(self):
        '''Connect to the appropriate Wikipedia and user databases.'''
        try:
            self.dbConn = MySQLdb.connect(db=self.dbNames[self.lang],
                                          host=self.hostnames[self.lang],
                                          use_unicode=True,
                                          read_default_file=os.path.expanduser(self.dbConfigFile));
            self.dbCursor = self.dbConn.cursor(cursors.SSDictCursor);
        except:
            self.dbConn = None;
            self.dbCursor = None;

        if self.dbConn:
            return True;
        else:
            return False;

    def close(self):
        '''Close our database connections.'''
        try:
            self.dbCursor.close();
            self.dbConn.close();
        except:
            pass;

        return;

def app(envir, start_response):
    json_helper = JSON();
    
    # read items and params from request.
    formdata = cgi.FieldStorage(fp = envir['wsgi.input'], environ = envir);
    
    start_response('200 OK', [('Content-type', 'application/json; charset=UTF-8')]);
    
    if 'items' not in formdata or 'params' not in formdata:
        yield json_helper.getError(400, 'Bad Request: Items or parameters not supplied');
        return;

    try:
        req_items = unicode(formdata['items'].value, 'utf-8', errors='strict');
        req_params = unicode(formdata['params'].value, 'utf-8', errors='strict');
    except UnicodeDecodeError, e:
	yield json_helper.getError(500, 'Unable to decode items or params.');


    try:
        req_items = json.loads(req_items);
        req_params = json.loads(req_params);
    except:
        yield json_helper.getError(500, 'Unable to decode message as JSON.');

    try:
        nrecs_param = int(req_params['nrecs']);
    except:
        nrecs_param = 10;

    recommender = LinkRecommender(lang=req_params['lang'], \
	                              nrecs=nrecs_param);

    if not recommender.checkLang():
	yield json_helper.getError(501, 'Error: Language not supported.');

    if not recommender.checkNrecs():
        yield json_helper.getError(413, 'Error: Requested too many recommendations.');

    if not recommender.connect():
        yield json_helper.getError(500, 'Error: Unable to connect to database servers.');

    # Check that both item_map and param_map are dictionaries
    if (not isinstance(req_items, dict)) or (not isinstance(req_params, dict)):
        yield json_helper.getError(400, 'Error: Items and params not dictionaries.');

    recs = recommender.get_recs(item_map=req_items, param_map=req_params);
    recommender.close();
    yield json_helper.getSuccess(recs);

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
   
    # logging.basicConfig(level=logging.DEBUG)

    # recommender = LinkRecommender(lang=testLang, nrecs=2500, verbose=True);
    # recommender.connect();
    # recs = recommender.get_recs(item_map=testItems, \
    #                                 param_map=dict({u'nrecs': 2500,u'lang': testLang}));
    # recommender.close();
    # print "Received %d recommendations." % (len(recs),);

# Also, comment out these if you run from command line
wsgi = WSGIServer(app);
wsgi.run();
