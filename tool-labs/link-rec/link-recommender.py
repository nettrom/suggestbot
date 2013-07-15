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
import sys;
import re;
import math;
import operator;

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
                        'pt': 'ptwiki_p'};
        self.hostnames = {'en': 'enwiki.labsdb',
                          'no': 'nowiki.labsdb',
                          'sv': 'svwiki.labsdb',
                          'pt': 'ptwiki.labsdb'};
        # Table name of the inlink count table in our user database.
        self.tableNames = {'en': 'p50380g50553__ilc.enwiki_inlinkcounts',
                           'no': 'p50380g50553__ilc.nowiki_inlinkcounts',
                           'sv': 'p50380g50553__ilc.svwiki_inlinkcounts',
                           'pt': 'p50380g50553__ilc.ptwiki_inlinkcounts'};

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
            u'pt': ur'\d+[ _]+de[ _]+(:[Jj]aneiro|[Ff]evereiro|[Mm]arço|[Aa]bril|[Mm]aio|[Jj]unho|[Jj]ulho|[Aa]gosto|[Ss]etembro|[Oo]utubro|[Nn]ovembro|[Dd]ezembro)'
            };

        # Note: compatible with both ' '  and '_' as spaces
        self.lists = {
            u'en': ur'[Ll]ist[ _]of[ _]',
            u'no': ur'[Ll]iste[ _]over[ _]',
            u'sv': ur'[Ll]ista[ _]över[ _]',
            u'pt': ur'[Ll]ista[ _]de[ _]'
            };

        # Compile the regular expressions
        self.months_re = dict();
        self.lists_re = dict();
        for lang in self.months.keys():
            self.months_re[lang] = re.compile(self.months[lang]);
            self.lists_re[lang] = re.compile(self.lists[lang]);

        self.rec_map = dict();
        self.titleIdMap = {}; # map page_title to page_id

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
        if self.lists_re[self.lang].match(item):
            return True;
        
        # starting with a month name
        if self.months_re[self.lang].match(item):
            return True;

        return False;

    def get_links(self):
        '''Get all links from the articles in self.rec_map'''
        if not self.rec_map:
            return None;

        # SQL query to get linked page titles and inlink counts from
        # a given page, where the pages linked to are in main,
        # and are not redirects.  Note that we substitute the table name
        # for our inlink count table directly.
        # This query should be fairly fast because we're using page IDs as
        # the identifier and only look up a single article at a time
        
        getLinkedPagesQuery = ur"""SELECT
             page_title, ilc_numlinks
             FROM page p JOIN pagelinks pl
             ON (p.page_title=pl.pl_title AND p.page_namespace=pl.pl_namespace)
             LEFT JOIN {ilcTable} ilc ON p.page_id=ilc.ilc_page_id
             WHERE pl.pl_namespace=0
             AND p.page_is_redirect=0
             AND pl.pl_from IN ({{idList}})""".format(ilcTable=self.tableNames[self.lang]);

        getPageidQuery = ur"""SELECT
                              page_id, page_is_redirect, rd_namespace, rd_title
                              FROM page
                              LEFT JOIN redirect
                              ON page_id=rd_from
                              WHERE page_namespace=0
                              AND page_title=%(title)s""";

        # remove all items that match our limitation expressions
        for rec in self.rec_map.keys():
            if self.exclude_item(rec):
                del(self.rec_map[rec]);

        if self.verbose:
            sys.stderr.write("Info: Ready to find recs based on %d articles.\n" % (len(self.rec_map.keys()),));

        # Get a snapshot of the current set of recommendations,
        # and extend recommendations based on it.
        current_recs = self.rec_map.keys();
        pageIdList = [];
        for pageTitle in current_recs:
            try:
                pageId = self.titleIdMap[pageTitle];
            except KeyError:
                # Get page ID
                pageId = None;
                try:
                    self.dbCursor.execute(getPageidQuery, {'title': pageTitle.encode('utf-8')});
                    row = self.dbCursor.fetchone();
                    self.dbCursor.fetchall(); # flush cursor
                    if not row['page_is_redirect']:
                        pageIdList.append(row['page_id']);
                        self.titleIdMap[pageTitle] = row['page_id'];
                    # elif row['rd_namespace'] == 0:
                    #     self.dbCursor.execute(getPageidQuery, {'title': row['rd_title']});
                    #     row = self.dbCursor.fetchone();
                    #     self.dbCursor.fetchall(); # flush cursor
                    #     if not row['page_is_redirect']:
                    #         pageIdList.append(row['page_id']);
                    #         self.titleIdMap[pageTitle] = row['page_id'];
                            
                except MySQLdb.Error, e:
                    sys.stderr.write("SBot Warning: Failed to get page ID for \n");
                    sys.stderr.write("SBot Warning: MySQL error {0}: {1}".format(e.args[0], e.args[1]));

        i = 0;
        while i < len(pageIdList):
            # Build a comma-separated string out of a subset of the page IDs
            pageIdSubset = ",".join([str(pageid) for pageid in pageIdList[i:i+self.sliceSize]]);

            # Get linked pages
            try:
                self.dbCursor.execute(getLinkedPagesQuery.format(idList=pageIdSubset));
                done = False;
                while not done:
                    row = self.dbCursor.fetchone();
                    if not row:
                        done = True;
                        continue;

                    # We check if the article matches our exclusion regex, and skip it
                    # if so...
                    page_title = unicode(row['page_title'], 'utf-8', errors='strict');
                    if self.exclude_item(page_title):
                        continue;

                    num_links = row['ilc_numlinks'];
                    if num_links is None:
                        num_links = 0;

                    # Classic idf = log(N/df).  We'd like to not give singly-linked
                    # items quite so much clout, and so we put the highest weight
                    # on things that have a few links.  How to estimate?  The
                    # "right" way is to make it a parameter and test against people.

                    # calculate penalty for popular links using a classic idf = log(N/df)
                    idf = math.log(self.n_docs/math.fabs(math.exp(3)-num_links));

                    try:
                        self.rec_map[page_title] += idf;
                    except KeyError:
                        self.rec_map[page_title] = idf;

                    if self.verbose:
                        sys.stderr.write("Info: rec_map now contains {0} items\n".format(len(self.rec_map)));
            except MySQLdb.Error, e:
                sys.stderr.write("SBot Warning: Failed to get links for \n");
                sys.stderr.write("SBot Warning: MySQL error {0}: {1}".format(e.args[0], e.args[1]));

            # OK, done with this batch, move along...
            i += self.sliceSize;

        # OK, done
        return;

    def get_recs(self, item_map=None, param_map=None):
        if not item_map or not param_map:
            return None;

        # We create our dictionary of recommendations, and copy over any
        # items we've received that are not to be excluded,
        # while translating " " in titles to "_".
        self.rec_map = dict();
        for item in item_map.keys():
            if not self.exclude_item(item):
                title = re.sub(' ', '_', item);
                self.rec_map[title] = 1;

        depth = 0;
        max_depth = self.max_depth;
        n_items = len(item_map);

        while (len(self.rec_map) - n_items) < self.nrecs \
                and depth < max_depth:
            if self.verbose:
                sys.stderr.write("Calling get_links(), with %d recs in the map.\n" % (len(self.rec_map,)));
            self.get_links();
            depth += 1;

        # We remove any item that the user has edited.
        # Because we might have removed items, not all
        # will be present.
        for item in item_map:
            title = re.sub(' ', '_', item);
            if title in self.rec_map:
                del(self.rec_map[title]);

        num = 0;
        recs = [];
        # sort them in reverse order by score
        # and push onto the recs list.
        for item in sorted(self.rec_map.iteritems(),
                           key=operator.itemgetter(1),
                           reverse=True):
            num += 1;
            if num > self.nrecs:
                break;

            (title, value) = item; # item is a tuple now
            # we translate "_" back to regular spaces...
            title = re.sub('_', ' ', title);
            recs.append(dict({'item': title,
                              'value': value}));

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
# if __name__ == "__main__":
#     testItems = {
#         u"Suhr Guitars": 1,
#         u"Santa Cruz Guitar Company": 1,
#         u"Bogner Amplification": 1,
#         u"Bogner": 1,
#         u"Collings Guitars": 1,
#         u"Vibrato systems for guitar": 1,
#         u"3rd bridge": 1,
#         u"Tailed bridge guitar": 1,
#         u"Floyd Rose": 1,
#         u"Rosewood": 1,
#         u"Fender Stratocaster": 1,
#         u"Buzz Feiten": 1,
#         u"Sadowsky": 1,
#         u"List of guitar manufacturers": 1,
#         u"James Tyler Guitars" :1,
#         u"Tom Anderson Guitarworks": 1,
#         u"Z.Vex Effects": 1,
#         u"Roscoe Beck": 1,
#         u"Tremstopper": 1,
#         u"Fender Coronado": 1,
#         u"Fender Swinger": 1,
#         u"Humbucker": 1,
#         u"Reb Beach": 1,
#         u"Wayne Krantz": 1,
#         u"Doug Aldrich": 1,
#         u"Superstrat": 1,
#         u"Guthrie Govan": 1,
#         u"Blackstratblues": 1,
#         u"Strat Plus": 1,
#         u"Fender stratocaster ultra": 1,
#         u"Fender Stratocaster Ultra": 1,
#         u"Strat Ultra": 1,
#         };
#     recommender = LinkRecommender(lang='en', nrecs=2500, verbose=True);
#     recommender.connect();
#     recs = recommender.get_recs(item_map=testItems, \
# 		param_map=dict({u'nrecs': 2500,u'lang': u'en'}));
#     recommender.close();
#     print "Received %d recommendations." % (len(recs),);

# Also, comment out these if you run from command line
wsgi = WSGIServer(app);
wsgi.run();
