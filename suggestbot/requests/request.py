#!/usr/env/python
# -*- coding: utf-8 -*-
"""
Class for suggestion requests.
"""

import os;
import sys;
import re;

import MySQLdb;

class RequestLoadDataError(Exception):
    pass;

class RequestIdError(Exception):
    pass;

class RequestUpdateError(Exception):
    pass;

class Request:
    def __init__(self, lang=u"en", id=None, username=None, page=None, revid=None,
                 timestamp=None, templates=[], seeds=[], sbDb=None, config=None,
                 verbose=False):
        """
        Instatiate a new Request object.

        @param lang: language code of the Wikipedia this request came from
        @type lang: unicode

        @param id: this request's ID
        @type id: int

        @param username: username of the user making the request
        @type username: unicode

        @param page: title of the page where the request was made
        @type page: unicode

        @param revid: revision ID of the revision containing the request template
        @type revid: int

        @param timestamp: time when the request was identified
        @type timestamp: datetime.datetime

        @param templates: templates used in the request
        @type templates: list of unicode

        @param seeds: list of articles submitted with the request
        @type seeds: list of unicode

        @param sbDb: database connection used for creation/updating
        @type sbDb: SuggestBotDatabase

        @param config: SuggestBot configuration to use
        @type config: Config.SuggestBotConfig

        @param verbose: write informational output?
        @type verbose: bool
        """
        self.verbose = verbose;
        self.id = id;
        self.lang = lang;
        self.username = username;
        self.page = page;
        self.revId = revid;
        self.startTime = timestamp;
        self.endTime = None; # request not fully processed yet
        self.status = 'processing';

        self.templates = templates;

        self.seeds = seeds;
        self.seedSource = "contributions";
        if seeds:
            self.seedSource = 'template';

        # Recommendations issued with this request
        # (dict where keys are titles, values are dicts with data)
        self.recs = {};

        # SuggestBot configuration
        self.config = config;

        self.dbConn = sbDb;
        # if we were given a request ID, fetch data from the database
        # (note: test for None since id 0 is a valid id)
        if self.id is not None:
            self.populateFromDatabase();

    def populateFromDatabase(self):
        """
        Populate this object with data from the database.
        """
        
        # Query to get basic Request data
        getDataQuery = ur"""SELECT * FROM {reqtable}
                            WHERE id=%(id)s""".format(reqtable=self.config.getConfig("REQ_LOGTABLE"));
        
        # Query to get the seeds
        getSeedsQuery = ur"""SELECT * FROM {reqseedstable}
                             WHERE id=%(id)s""".format(reqseedstable=self.config.getConfig("REQ_SEEDSTABLE"));

        # Query to get recs
        getRecsQuery = ur"""SELECT * FROM {reqrecstable}
                            WHERE id=%(id)s""".format(reqrecstable=self.config.getConfig("REQ_RECSTABLE"));

        dbCursor = self.dbConn.cursor();
        try:
            dbCursor.execute(getDataQuery, {'id': self.id});
            row = dbCursor.fetchone();
            dbCursor.fetchall(); # flush cursor
            if not row:
                sys.stderr.write(u"SBot Error: failed to find request with id {id} in the database\n".format(id=self.id));
                raise RequestIdError;

            self.lang = row['lang'];
            self.username = unicode(row['username'], 'utf-8', errors='strict');
            self.page = unicode(row['page'], 'utf-8', errors='strict');
            self.revId = row['revid'];
            self.seedSource = row['seed_source'];
            self.startTime = row['start_time'];
            self.endTime = row['end_time'];
            self.status = row['status'];

            templates = unicode(row['templates'], 'utf-8', errors='strict');
            self.templates = templates.split(u",");
        except MySQLdb.Error, e:
            sys.stderr.write("SBot Error: Unable to update w/request data from database!\n");
            sys.stderr.write("Error {d}: {s}\n".format(d=e.args[0], s=e.args[1]));
            raise RequestLoadDataError;

        # We got request data, look for seeds...
        try:
            dbCursor.execute(getSeedsQuery, {'id': self.id});
            for row in dbCursor.fetchall():
                seedTitle = unicode(row['title'], 'utf-8', errors='strict');
                self.seeds.append(seedTitle);
        except MySQLdb.Error, e:
            sys.stderr.write("SBot Error: Unable to update w/seed data from database!\n");
            sys.stderr.write("Error {d}: {s}\n".format(d=e.args[0], s=e.args[1]));
            raise RequestLoadDataError;

        # ...and look for recs
        try:
            dbCursor.execute(getRecsQuery, {'id': self.id});
            for row in dbCursor.fetchall():
                recTitle = unicode(row['title'], 'utf-8', errors='strict');
                self.recs[recTitle] = {'title': recTitle,
                                       'cat': row['category'],
                                       'rank': row['rank'],
                                       'source': row['rec_source'],
                                       'rec_rank': row['rec_rank'],
                                       'popcount': row['popcount'],
                                       'popularity': row['popularity'],
                                       'quality': row['quality'],
                                       'assessedclass': row['assessed_class'],
                                       'predictedclass': row['predicted_class']};
        except MySQLdb.Error, e:
            sys.stderr.write("SBot Error: Unable to update w/rec data from database!\n");
            sys.stderr.write("Error {d}: {s}\n".format(d=e.args[0], s=e.args[1]));
            raise RequestLoadDataError;

        # OK, done
        return;

    def updateDatabase(self):
        """
        Update the database with the current state of this object.
        """

        reqTable = self.config.getConfig("REQ_LOGTABLE");
        reqSeedsTable = self.config.getConfig("REQ_SEEDSTABLE");
        reqRecsTable = self.config.getConfig("REQ_RECSTABLE");

        existsQuery = ur"""SELECT * FROM {reqtable}
                           WHERE id=%(id)s""".format(reqtable=reqTable);
        insertQuery = ur"""INSERT INTO {reqtable}
                          (lang, username, page, revid, templates,
                           seed_source, start_time, status)
                           VALUES (%(lang)s, %(username)s,
                           %(page)s, %(revid)s, %(templates)s,
                           %(seedsource)s, %(starttime)s, %(status)s)""".format(reqtable=reqTable);

        updateQuery = ur"""UPDATE {reqtable}
                           SET lang=%(lang)s, username=%(username)s,
                           page=%(page)s, revid=%(revid)s,
                           templates=%(templates)s, seed_source=%(seedsource)s,
                           start_time=%(starttime)s, end_time=%(endtime)s,
                           status=%(status)s
                           WHERE id=%(id)s""".format(reqtable=reqTable);

        deleteSeedsQuery = ur"""DELETE FROM {reqseedstable}
                                WHERE id=%(id)s""".format(reqseedstable=reqSeedsTable);
        insertSeedQuery = ur"""INSERT INTO {reqseedstable}
                               (id, title)
                               VALUES (%(id)s, %(title)s)""".format(reqseedstable=reqSeedsTable);

        deleteRecsQuery = ur"""DELETE FROM {reqrecstable}
                               WHERE id=%(id)s""".format(reqrecstable=reqRecsTable);
        insertRecQuery = ur"""INSERT INTO {reqrecstable}
                              (id, title, category, rank, rec_source,
                               rec_rank, popcount, popularity, quality,
                               assessed_class, predicted_class)
                              VALUES (%(id)s, %(title)s, %(category)s, %(rank)s,
                              %(rec_source)s, %(rec_rank)s, %(popcount)s,
                              %(popularity)s, %(quality)s, %(assessed_class)s,
                              %(predicted_class)s)""".format(reqrecstable=reqRecsTable);

        # build update dictionary
        reqData = {"id": self.id,
                   "lang": self.lang,
                   "username": self.username.encode('utf-8'),
                   "page": self.page.encode('utf-8'),
                   "revid": self.revId,
                   "templates": u",".join(self.templates).encode('utf-8'),
                   "seedsource": self.seedSource,
                   "starttime": self.startTime,
                   "endtime": self.endTime,
                   "status": self.status};

        dbCursor = self.dbConn.cursor();
        try:
            # check if this request exists
            dbCursor.execute(existsQuery, reqData);
            row = dbCursor.fetchone();
            dbCursor.fetchall(); # flush cursor
            if row:
                # if it does, update
                dbCursor.execute(updateQuery, reqData);
            else:
                # if it doesn't, insert
                dbCursor.execute(insertQuery, reqData);
                # update ourself with the ID we got
                self.id = self.dbConn.insert_id();
            self.dbConn.commit();
        except MySQLdb.Error, e:
            sys.stderr.write("SBot Error: Unable to update request data in the database!\n");
            sys.stderr.write("Error {d}: {s}\n".format(d=e.args[0], s=e.args[1]));
            raise RequestUpdateError;

        # if the rec server is not responsible for handling our seeds,
        # delete existing seeds and insert the ones we have...
        if self.seedSource == u"template":
            try:
                dbCursor.execute(deleteSeedsQuery, {'id': self.id});
                if self.verbose:
                    sys.stderr.write(u"SBot Info: deleted {n} seeds from the database\n".format(n=self.dbConn.affected_rows()));
                seedsToInsert = [];
                for seed in self.seeds:
                    seedsToInsert.append({'id': self.id,
                                          'title': seed.encode('utf-8')});
                if seedsToInsert:
                    dbCursor.executemany(insertSeedQuery, seedsToInsert);
                    if self.verbose:
                        sys.stderr.write(u"SBot Info: inserted {n} seeds into the database\n".format(n=self.dbConn.affected_rows()));
                    self.dbConn.commit();
            except MySQLdb.Error, e:
                sys.stderr.write("SBot Error: Unable to delete and insert seeds in the database!\n");
                sys.stderr.write("Error {d}: {s}\n".format(d=e.args[0], s=e.args[1]));
                raise RequestUpdateError;

        # delete existing recs and insert the ones we have
        try:
            dbCursor.execute(deleteRecsQuery, {'id': self.id});
            if self.verbose:
                sys.stderr.write(u"SBot Info: deleted {n} recs from the database\n".format(n=self.dbConn.affected_rows()));
                sys.stderr.write(u"SBot Info: adding {n} recs to the list to insert\n".format(n=len(self.recs)));
            recsToInsert = [];
            for (recTitle, recData) in self.recs.iteritems():
                recsToInsert.append({'id': self.id,
                                     'title': recTitle.encode('utf-8'),
                                     'category': recData['cat'],
                                     'rank': recData['rank'],
                                     'rec_source': recData['source'],
                                     'rec_rank': recData['rec_rank'],
                                     'popcount': recData['popcount'],
                                     'popularity': recData['popularity'],
                                     'quality': recData['quality'],
                                     'assessed_class': recData['assessedclass'],
                                     'predicted_class': recData['predictedclass']});
            if recsToInsert:
                dbCursor.executemany(insertRecQuery, recsToInsert);
                if self.verbose:
                    sys.stderr.write(u"SBot Info: inserted {n} recs into the database\n".format(n=self.dbConn.affected_rows()));
            self.dbConn.commit();
        except MySQLdb.Error, e:
            sys.stderr.write("SBot Error: Unable to delete and insert recs in the database!\n");
            sys.stderr.write("Error {d}: {s}\n".format(d=e.args[0], s=e.args[1]));
            raise RequestUpdateError;

        # OK, done
        return;

    def getId(self):
        return self.id;
    def setId(self, newId=None):
        if newId is not None:
            self.id = newId;

    def getRecs(self):
        return self.recs;
    def setRecs(self, recs=[]):
        """
        Sets this request's list of recommendations.  Adds some keys to each
        recommendation's dictionary because the original naming conventions
        were poorly chosen.

        @param recs: Recommendations to set.  A dictionary where the keys are
                     titles of the recommended articles and values are dictionaries
                     with data for each article (rank, category, etc...)
        @type recs: dict
        """
        if isinstance(recs, dict):
            if self.verbose:
                sys.stderr.write(u"Info: got {n} recs to add to myself\n".format(n=len(recs)));
            self.recs = recs;
            for (title, recData) in self.recs.iteritems():
                recData['popularity'] = recData['pop'];
                recData['assessedclass'] = recData['qual'];
                recData['quality'] = recData['pred'];
                recData['predictedclass'] = recData['predclass'];

        return;

    def getStatus(self): return self.status;
    def setStatus(self, newStatus=u""):
        if not isinstance(newStatus, unicode):
            newStatus = unicode(newStatus, 'utf-8', errors='strict');
        self.status = newStatus;
        return;

    def setEndtime(self, newEndtime=None):
        self.endTime = newEndtime;
    def getEndtime(self):
        return self.endTime;
