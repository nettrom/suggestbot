#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Class for suggestion requests.

Copyright (C) 2005-2015 SuggestBot Dev Group

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
import sys
import re
import logging
import MySQLdb

from suggestbot import config

class RequestLoadDataError(Exception):
    pass

class RequestIdError(Exception):
    pass

class RequestUpdateError(Exception):
    pass

class Request:
    def __init__(self, lang='en', id=None, username=None, page=None, revid=None,
                 timestamp=None, templates=[], seeds=[], sbDb=None,
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
        self.verbose = verbose
        self.id = id
        self.lang = lang
        self.username = username
        self.page = page
        self.revId = revid
        self.startTime = timestamp
        self.endTime = None # request not fully processed yet
        self.status = 'processing'

        self.templates = templates

        self.seeds = seeds
        self.seedSource = "contributions"
        if seeds:
            self.seedSource = 'template'

        # Recommendations issued with this request
        # (dict where keys are titles, values are dicts with data)
        self.recs = {}

        self.dbConn = sbDb.conn
        # if we were given a request ID, fetch data from the database
        # (note: test for None since id 0 is a valid id)
        if self.id is not None:
            self.populateFromDatabase()

    def populateFromDatabase(self):
        """
        Populate this object with data from the database.
        """
        
        # Query to get basic Request data
        getDataQuery = """SELECT * FROM {reqtable}
                          WHERE id=%(id)s""".format(reqtable=config.req_logtable)
        
        # Query to get the seeds
        getSeedsQuery = """SELECT * FROM {reqseedstable}
                           WHERE id=%(id)s""".format(reqseedstable=config.req_seedstable)

        # Query to get recs
        getRecsQuery = """SELECT * FROM {reqrecstable}
                          WHERE id=%(id)s""".format(reqrecstable=config.req_recstable)

        dbCursor = self.dbConn.cursor()
        try:
            dbCursor.execute(getDataQuery, {'id': self.id})
            row = dbCursor.fetchone()
            dbCursor.fetchall() # flush cursor
            if not row:
                sys.stderr.write("SBot Error: failed to find request with id {id} in the database\n".format(id=self.id))
                raise RequestIdError

            self.lang = row['lang']
            self.username = unicode(row['username'], 'utf-8', errors='strict')
            self.page = unicode(row['page'], 'utf-8', errors='strict')
            self.revId = row['revid']
            self.seedSource = row['seed_source']
            self.startTime = row['start_time']
            self.endTime = row['end_time']
            self.status = row['status']

            templates = unicode(row['templates'], 'utf-8', errors='strict')
            self.templates = templates.split(",")
        except MySQLdb.Error as e:
            logging.error("unable to update with request data from database")
            logging.erorr("MySQL error {d}: {s}".format(d=e.args[0], s=e.args[1]))
            raise RequestLoadDataError

        # We got request data, look for seeds...
        try:
            dbCursor.execute(getSeedsQuery, {'id': self.id})
            for row in dbCursor.fetchall():
                seedTitle = unicode(row['title'], 'utf-8', errors='strict')
                self.seeds.append(seedTitle)
        except MySQLdb.Error as e:
            logging.error("unable to update with seed data from database")
            logging.error("MySQL error {d}: {s}\n".format(d=e.args[0], s=e.args[1]))
            raise RequestLoadDataError

        # ...and look for recs
        try:
            dbCursor.execute(getRecsQuery, {'id': self.id})
            for row in dbCursor.fetchall():
                recTitle = unicode(row['title'], 'utf-8', errors='strict')
                self.recs[recTitle] = {'title': recTitle,
                                       'cat': row['category'],
                                       'rank': row['rank'],
                                       'source': row['rec_source'],
                                       'rec_rank': row['rec_rank'],
                                       'popcount': row['popcount'],
                                       'popularity': row['popularity'],
                                       'quality': row['quality'],
                                       'assessedclass': row['assessed_class'],
                                       'predictedclass': row['predicted_class']}
        except MySQLdb.Error as e:
            logging.error("unable to update with rec data from database")
            logging.error("MySQL error {d}: {s}".format(d=e.args[0], s=e.args[1]))
            raise RequestLoadDataError

        # OK, done
        return

    def updateDatabase(self):
        """
        Update the database with the current state of this object.
        """

        reqTable = config.req_logtable
        reqSeedsTable = config.req_seedstable
        reqRecsTable = config.req_recstable

        existsQuery = """SELECT * FROM {reqtable}
                         WHERE id=%(id)s""".format(reqtable=reqTable)
        insertQuery = """INSERT INTO {reqtable}
                        (lang, username, page, revid, templates,
                         seed_source, start_time, status)
                         VALUES (%(lang)s, %(username)s,
                         %(page)s, %(revid)s, %(templates)s,
                         %(seedsource)s, %(starttime)s, %(status)s)""".format(reqtable=reqTable)

        updateQuery = """UPDATE {reqtable}
                         SET lang=%(lang)s, username=%(username)s,
                         page=%(page)s, revid=%(revid)s,
                         templates=%(templates)s, seed_source=%(seedsource)s,
                         start_time=%(starttime)s, end_time=%(endtime)s,
                         status=%(status)s
                         WHERE id=%(id)s""".format(reqtable=reqTable)

        deleteSeedsQuery = """DELETE FROM {reqseedstable}
                              WHERE id=%(id)s""".format(reqseedstable=reqSeedsTable)
        insertSeedQuery = """INSERT INTO {reqseedstable}
                            (id, title)
                             VALUES (%(id)s, %(title)s)""".format(reqseedstable=reqSeedsTable)
        deleteRecsQuery = """DELETE FROM {reqrecstable}
                             WHERE id=%(id)s""".format(reqrecstable=reqRecsTable)
        insertRecQuery = """INSERT INTO {reqrecstable}
                            (id, title, category, rank, rec_source,
                             rec_rank, popcount, popularity, quality,
                             assessed_class, predicted_class)
                            VALUES (%(id)s, %(title)s, %(category)s, %(rank)s,
                            %(rec_source)s, %(rec_rank)s, %(popcount)s,
                            %(popularity)s, %(quality)s, %(assessed_class)s,
                            %(predicted_class)s)""".format(reqrecstable=reqRecsTable)

        # build update dictionary
        reqData = {"id": self.id,
                   "lang": self.lang,
                   "username": self.username,
                   "page": self.page,
                   "revid": self.revId,
                   "templates": ",".join(self.templates),
                   "seedsource": self.seedSource,
                   "starttime": self.startTime,
                   "endtime": self.endTime,
                   "status": self.status}

        dbCursor = self.dbConn.cursor()
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
        except MySQLdb.Error as e:
            logging.error("unable to update request data in the database")
            logging.error("MySQL error {d}: {s}".format(d=e.args[0], s=e.args[1]))
            raise RequestUpdateError

        # if the rec server is not responsible for handling our seeds,
        # delete existing seeds and insert the ones we have...
        if self.seedSource == "template":
            try:
                dbCursor.execute(deleteSeedsQuery, {'id': self.id});
                logging.info("deleted {n} seeds from the database".format(n=self.dbConn.affected_rows()))
                seedsToInsert = []
                for seed in self.seeds:
                    seedsToInsert.append({'id': self.id,
                                          'title': seed})
                if seedsToInsert:
                    dbCursor.executemany(insertSeedQuery, seedsToInsert)
                    logging.info("inserted {n} seeds into the database".format(n=self.dbConn.affected_rows()))
                    self.dbConn.commit()
            except MySQLdb.Error as e:
                logging.error("unable to delete and insert seeds in the database")
                logging.error("MySQL error {d}: {s}".format(d=e.args[0], s=e.args[1]))
                raise RequestUpdateError

        # delete existing recs and insert the ones we have
        try:
            dbCursor.execute(deleteRecsQuery, {'id': self.id})
            logging.info("deleted {n} recs from the database".format(
                n=self.dbConn.affected_rows()))
            logging.info("adding {n} recs to the list to insert".format(
                n=len(self.recs)))
            recsToInsert = []
            for (recTitle, recData) in self.recs.items():
                recsToInsert.append({'id': self.id,
                                     'title': recTitle,
                                     'category': recData['cat'],
                                     'rank': recData['rank'],
                                     'rec_source': recData['source'],
                                     'rec_rank': recData['rec_rank'],
                                     'popcount': recData['popcount'],
                                     'popularity': recData['popularity'],
                                     'quality': recData['quality'],
                                     'assessed_class': recData['assessedclass'],
                                     'predicted_class': recData['predictedclass']})
            if recsToInsert:
                dbCursor.executemany(insertRecQuery, recsToInsert)
                logging.info("inserted {n} recs into the database".format(
                    n=self.dbConn.affected_rows()))
            self.dbConn.commit()
        except MySQLdb.Error as e:
            logging.error("unable to delete and insert recs in the database")
            logging.error("MySQL error {d}: {s}".format(d=e.args[0], s=e.args[1]))
            raise RequestUpdateError

        # OK, done
        return

    def getId(self):
        return self.id
    def setId(self, newId=None):
        if newId is not None:
            self.id = newId

    def getRecs(self):
        return self.recs
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
            logging.info("got {n} recs to add to myself".format(n=len(recs)))
            self.recs = recs
            for (title, recData) in self.recs.items():
                recData['popularity'] = recData['pop']
                recData['assessedclass'] = recData['qual']
                recData['quality'] = recData['pred']
                recData['predictedclass'] = recData['predclass']

        return

    def getStatus(self): return self.status
    def setStatus(self, newStatus=""):
        self.status = newStatus
        return

    def setEndtime(self, newEndtime=None):
        self.endTime = newEndtime
    def getEndtime(self):
        return self.endTime
