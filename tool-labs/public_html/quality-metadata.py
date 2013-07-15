#!/usr/bin/python
# -*- coding: utf-8  -*-
'''
Webservice script to get metadata about articles,
used for calculating article quality.

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
import sys;
import MySQLdb;
from MySQLdb import cursors;

from flup.server.fcgi import WSGIServer;
import cgi;

import simplejson as json;

# FIXME: add error handling and logging

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

class MetadataGetter():
    def __init__(self, lang='en', verbose=False):
        '''
        Initialize the getter.

        @param lang: Language code of the language we're getting data for
        @type lang: str

        @param verbose: Write informational output?
        @type verbose: bool
        '''
        self.lang = lang;
        self.verbose = verbose;

        self.dbConf = "/data/project/suggestbot/replica.my.cnf";
        self.dbNames = {'en': 'enwiki_p',
                        'no': 'nowiki_p',
                        'sv': 'svwiki_p',
                        'pt': 'ptwiki_p'};
        self.hostnames = {'en': 'enwiki.labsdb',
                          'no': 'nowiki.labsdb',
                          'sv': 'svwiki.labsdb',
                          'pt': 'ptwiki.labsdb'};
        self.dbConn = None;
        self.dbCursor = None;

    def checkLang(self):
        if not self.lang in self.dbNames:
	    return False;
        return True;

    def setLang(self, lang=None):
        if lang:
            self.lang = lang;

    def getLang(self):
        return self.lang;

    def getMetadata(self, title=u''):
        '''
        Retrieve metadata for a given article.  Expects a valid database connection
        to be up and running.

        @param title: Title of the article to get metadata for
        @type title: str
        '''
        if not title:
            return None;

        # SQL query to get the page ID of a given article.
        getIDQuery = ur'''SELECT page_id FROM page
                          WHERE page_title=%(title)s
                          AND page_namespace=%(ns)s''';

        # SQL query to get a count of images in a given article.
        getImageCount = ur"""SELECT count(*) AS numimages
                             FROM imagelinks WHERE il_from=%(pageid)s""";

        # SQL query to get a count of all unbroken pagelinks from a given article
        # (unbroken links have a matching NS and title pair in the page table)
        getUnbrokenPageLinkCount = ur"""SELECT count(*) AS numlinks
                                        FROM pagelinks pl JOIN page p
                                        ON (pl.pl_namespace=p.page_namespace
                                        AND pl.pl_title=p.page_title)
                                        WHERE pl.pl_from=%(pageid)s""";

        # SQL query to get a count of all pagelinks from a given article
        getPagelinkCount = ur"""SELECT count(*) AS numlinks
                                FROM pagelinks WHERE pl_from=%(pageid)s""";

        if self.verbose:
            sys.stderr.write("Info: Ready to find metadata for %s:%s\n" % (self.lang, title.encode('utf-8'),));

        # Sensible defaults
        numImages = 0;
        numLinks = 0;
        numBrokenLinks = 0;

        # replace any space with "_"
        title = re.sub(' ', '_', title);

        row = None;
        try:
            # get page id
            self.dbCursor.execute(getIDQuery, {'title': title.encode('utf-8'),
                                               'ns': 0});
            row = self.dbCursor.fetchone();
            self.dbCursor.fetchall(); # flush cursor
        except MySQLdb.Error, e:
            pass;

        if not row:
            sys.stderr.write(u"Error: Failed to get page ID for {0}:{1}\n".format(self.lang, title).encode('utf-8'),);
            return None;

        pageId = row['page_id'];

        row = None;
        try:
            # get image count
            self.dbCursor.execute(getImageCount, {'pageid': pageId});

            row = self.dbCursor.fetchone();
            self.dbCursor.fetchall(); # flush cursor
        except MySQLdb.Error, e:
            sys.stderr.write(u"Error: Failed to get image count for {0}:{1}\n".format(self.lang, title).encode('utf-8'));
            return None;

        if row:
            numImages = row['numimages'];

        try:
            # get number of links
            self.dbCursor.execute(getUnbrokenPageLinkCount, {'pageid': pageId});
        
            row = self.dbCursor.fetchone();
            self.dbCursor.fetchall(); # flush cursor
        except MySQLdb.Error, e:
            sys.stderr.write(u"Error: Failed to get unbroken page link count for {0}:{1}\n".format(self.lang, title).encode('utf-8'));
            return None;

        if row:
            numLinks = row['numlinks'];

        row = None;
        try:
            # get number of links in total
            self.dbCursor.execute(getPagelinkCount, {'pageid': pageId});
            row = self.dbCursor.fetchone();
            self.dbCursor.fetchall(); # flush cursor
        except MySQLdb.Error, e:
            sys.stderr.write(u"Error: Failed to get total page link count for {0}:{1}\n".format(self.lang, title).encode('utf-8'));
            return None;

        if row:
            # Number of broken links is the difference between this number
            # and the previous number of functional links.
            numBrokenLinks = row['numlinks'] - numLinks;

        # Ok, we're done, return data
        return {'numImages': numImages,
                'numLinks': numLinks,
                'numBrokenLinks': numBrokenLinks};

    def getListData(self, titles=[]):
        '''
        Go through a list of article titles and retrieve metadata for all of them.
        Return a list of corresponding metadata.

        @params titles: The titles to find metadata for.
        @type titles: list
        '''
        metadata = [];

        for title in titles:
            metadata.append(self.getMetadata(title=title));

        return metadata;

    def connect(self):
        '''Connect to the appropriate Wikipedia and user databases.'''
        try:
            self.dbConn = MySQLdb.connect(db=self.dbNames[self.lang],
                                          host=self.hostnames[self.lang],
                                          use_unicode=True,
                                          read_default_file=os.path.expanduser(self.dbConf));
            self.dbCursor = self.dbConn.cursor(cursors.SSDictCursor);
        except MySQLdb.Error, e:
            sys.stderr.write(u"Error: unable to connect to host {0}, db {1}\n".format(self.hostnames[self.lang], self.dbNames[self.lang]).encode('utf-8'));
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
        except MySQLdb.Error, e:
            pass;

        return;

def app(envir, start_response):
    json_helper = JSON();

    # read items and params from request.
    formdata = cgi.FieldStorage(fp = envir['wsgi.input'], environ = envir);

    start_response('200 OK', [('Content-type', 'application/json; charset=UTF-8')]);

    if 'titles' not in formdata or 'params' not in formdata:
        yield json_helper.getError(400, 'Bad Request: Titles or parameters not supplied');
        return;

    try:
        req_titles = unicode(formdata['titles'].value, 'utf-8', errors='strict');
        req_params = unicode(formdata['params'].value, 'utf-8', errors='strict');
    except UnicodeDecodeError, e:
	yield json_helper.getError(500, 'Unable to decode titles or params.');

#    req_titles = formdata['titles'].value;
#    req_params = formdata['params'].value;

    try:
        req_titles = json.loads(req_titles);
        req_params = json.loads(req_params);
    except:
        yield json_helper.getError(500, 'Unable to decode message as JSON.');

    myGetter = MetadataGetter(lang=req_params['lang']);

    if not myGetter.checkLang():
	yield json_helper.getError(501, 'Error: Language not supported.');

    if not myGetter.connect():
        yield json_helper.getError(500, 'Error: Unable to connect to database servers.');

    # Check that the given list of titles is actually a list.
    if not isinstance(req_titles, list):
        yield json_helper.getError(400, 'Error: Titles not given in a list.');

    metadata = myGetter.getListData(titles=req_titles);
    myGetter.close();
    yield json_helper.getSuccess(metadata);

# Test code, uncomment and run from command line to verify functionality
#if __name__ == "__main__":
#    myGetter = MetadataGetter(lang='en', verbose=True);
#    myGetter.connect();
#    metadata = myGetter.getListData(titles=[u'Günter Kunert']);
#    myGetter.close();
#    print metadata;

# Also, comment out these if you run from command line
wsgi = WSGIServer(app);
wsgi.run();
