#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Program to update a list of open tasks for a Wikipedia.
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
import random;

import oursql;

from datetime import datetime;

import pywikibot;

import PopQual;

class DummyConfig:
	"""
	Dummy configuration class that exposes C{getConfig} and C{setConfig} methods that
	allows retrieval of what would've been SuggestBot's configuration values, used
	in the PopQual library.
	"""
	def __init__(self):
		self.config = {
			'WP_LANGCODE': u"en",
			'CLASSIFIER_HOSTNAME': 'localhost',
			'CLASSIFIER_HOSTPORT': 10129,
			'QUALWS_URL': u'http://toolserver.org/~nettrom/suggestbot/quality-metadata.fcgi',
			};

	def getConfig(self, key=None):
		if not key:
			return None;
		try:
			return self.config[key];
		except KeyError:
			return None;

	def setConfig(self, key=None, value=None):
		if not key:
			return None;
		self.config[key] = value;
		return True;

class OpenTaskUpdater:
	def __init__(self, verbose=False, lang=None, mysqlConf=None,
		     taskPage=None, taskDef=None, pagesPerCategory=5,
		     editComment=None, testRun=False, samplingFactor=20,
		     classifierFile=None, logDBHost=None, logDBName=None,
		     logTableName=None, maxDBQueryAttempts=3):
		"""
		Instantiate an object intended to update the list of open tasks.
		
		@param verbose: Write informational output?
		@type verbose: bool

		@param lang: Language code of the Wikipedia we're working on.
		@type lang: str

		@param mysqlConf: Path to the .my.cnf used for MySQL authentication
		@type mysqlConf: str

		@param taskPage: Title of the page which contains the open tasks
		@type taskPage: unicode

		@param taskDef: Dictionary mapping task IDs to categories containing tasks
		@type taskDef: dict

		@param pagesPerCategory: Number of pages we want per task category
		@type pagesPerCategory: int
		
		@param editComment: Edit comment used on successful update
		@type editComment: unicode

		@param testRun: Do a test run? Prints the resulting wikitext to stdout
		@type testRun: bool

		@param samplingFactor: Multiplier to use for oversampling and selection
		                       based on popularity/quality. (0 = no oversampling)
		@type samplingFactor: int

		@param classifierFile: name of file containing hostname & port where
		                       the quality classification server is listening.
		@type classifierFile: str

		@param logDBHost: hostname of the database server used for logging
		@type logDBHost: str

		@param logDBName: name of the database used for logging
		@type logDBName: str

		@param logTableName: name of the table used for logging
		@type logTableName: str

		@param maxDBQueryAttempts: max number of database queries attempts
		                           we will make before aborting.
		@type maxDBQueryAttempts: int
		"""
		
		self.lang = 'en';
		if lang:
			self.lang = lang;

		self.mysqlConf = "~/.my.cnf";
		if mysqlConf:
			self.mysqlConf = mysqlConf;

		self.numPages = pagesPerCategory;

		self.editComment = u"Updating list of open tasks...";
		if editComment:
			self.editComment = editComment;

		self.taskPage = u"Wikipedia:Community portal/Opentask";
		if taskPage:
			self.taskPage = taskPage;

		if taskDef:
			self.taskDef = taskDef;
		else:
			# Wikify is deleted, the following templates and associated
			# categories take over for it:
			# {{dead end}}, {{underlinked}}, and {{overlinked}}

			# "leadcleanup" refers to "Category:Wikipedia introduction cleanup"
			# where amongst others, {{inadequate lead}}, {{lead too short}},
			# and {{lead too long}} end up

			# Task def is a dictionary where keys are IDs of the span elements
			# to which the list of pages will go.  Values are one of:
			# 1: unicode string, name of category to grab pages from
			# 2: list of unicode strings, names of categories,
			#    pages will be grabbed randomly from all categories combined
			#
			# The name of a category can also be a tuple of the form
			# ("use-subs", u"[category name]") which will indicate that
			# we need to grab all sub-categories from the given category.
			# Pages will then be grabbed randomly from all the sub-categories.

			self.taskDef = {
				"wikify": [u"All dead-end pages",
					   u"All articles with too few wikilinks",
					   u"All articles with too many wikilinks"],
				"leadcleanup": ("use-subs", "Wikipedia introduction cleanup"),

				"copyedit": u"All articles needing copy edit",
				"update": u"All Wikipedia articles in need of updating",
				"translate": u"Wikipedia articles needing cleanup after translation",
				"verify": u"All pages needing factual verification",
				"or" : u"All articles that may contain original research",
				"stub" : u"Stub categories",
				# "merge": u"All articles to be merged",
				# "split": u"All articles to be split",
				# "expand" : u"All articles to be expanded",
				# "npov": u"All NPOV disputes",
				# "cleanup": u"All pages needing cleanup",
				# "style" : u"All articles needing style editing",
				# "orphan": u"All orphaned articles",
				# "afdrelist" : {
				#	"catname": u"Relisted AfD debates",
				#	"pattern": u"Articles_for_deletion/%", # filter
				#	"exclude": u"%/Log/%", # remove these
				#	"namespace": 4, # namespace of pages we're looking for
				#	"prefix": u"Wikipedia:", # namespace prefix
				#	},
				};

		self.testRun = testRun;

		self.samplingFactor = samplingFactor;

		self.verbose = verbose;
		self.dbConn = None;
		self.dbCursor = None;
		self.maxDBQueryAttempts = maxDBQueryAttempts;
		
		self.logDBHost = 'sql-user-n';
		self.logDBName = 'u_nettrom';
		self.logTableName = 'u_nettrom_opentask_log';
		if logDBHost:
			self.logDBHost = logDBHost;
		if logDBName:
			self.logDBName = logDBName;
		if logTableName:
			self.logTableName = logTableName;

		self.popQualServer = None;
		if self.samplingFactor > 1:
			# Read classifier configuration from file,
			# and instantiate Popularity/Quality server
			classifierFilename = "~/SuggestBot/classifier/hostname.txt";
			if classifierFile:
				classifierFilename = classifierFile;

			pqServerConfig = DummyConfig();
			with(open(os.path.expanduser(classifierFilename))) as inputFile:
				hostname = inputFile.readline().strip();
				port = int(inputFile.readline().strip());
			pqServerConfig.setConfig(key="CLASSIFIER_HOSTNAME",
						 value=hostname);
			pqServerConfig.setConfig(key="CLASSIFIER_HOSTPORT",
						 value=port);

			self.popQualServer = PopQual.PopularityQualityServer(config=pqServerConfig);

		# Dictionary of results, a list of pages for each task
		self.foundTasks = dict([(taskId, []) for taskId in self.taskDef.keys()]);

		# Query to fetch a number of random pages from a given category.
		self.randomPageQuery = r"""SELECT /* LIMIT:120 */
                                           page_id, page_title
                                           FROM page JOIN categorylinks ON page_id=cl_from
                                           WHERE cl_to=?
                                           AND page_namespace=?
                                           AND page_random >= RAND()
                                           ORDER BY page_random LIMIT ?""";

		# Query to fetch all pages in a given namespace from a given category
		self.getAllPagesQuery = u"""SELECT page_id, page_title
                                            FROM page JOIN categorylinks ON page_id=cl_from
                                            WHERE cl_to=?
                                            AND page_namespace=?""";

	def connectDatabase(self, hostName=None, dbName=None):
		'''
		Connect to the database associated with our Wikipedia,
		or a given server and database if host/database names
		are supplied.

		@param hostName: hostname of the server we're connecting to
		@type hostName: str

		@param dbName: name of the database we will be using
		@type dbName: str
		'''
		if not hostName:
			hostName = u"{lang}wiki-p.rrdb.toolserver.org".format(lang=self.lang);
			dbName = u"{lang}wiki_p".format(lang=self.lang);

		if self.dbConn:
			self.disconnectDatabase();

		try:
			self.dbConn = oursql.connect(db=dbName,
						     host=hostName,
						     read_default_file=os.path.expanduser(self.mysqlConf),
						     use_unicode=False,
						     charset=None);
			self.dbCursor = self.dbConn.cursor();
		except oursql.Error, e:
			sys.stderr.write("Error: Unable to connect to database {0} on server {1}.\n".format(dbName, hostname));
			sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
			return False;
		
		# Ok, done
		return True;

	def disconnectDatabase(self):
		if not self.dbConn or not self.dbCursor:
			sys.stderr.write(u"Warning: can't disconnect connections that are None!\n".encode('utf-8'));
			return False;
		try:
			self.dbCursor.close();
			self.dbConn.close();
		except oursql.Error, e:
			sys.stderr.write("Error: Unable to disconnect from database!\n");
			sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
			return False;
		# Ok, done
		return True;

	def stopme(self):
		pywikibot.stopme();

	def findAfDs(self, afdDef=None, nPages=5):
		"""
		Find relisted Articles for Deletion (AfDs).
		Excepts a working database connection to exist as self.dbConn

		@param afdDef: Dictionary defining how to find the relisted AfDs
		               keys and their mapping:
                               catname: category where they are listed
                               pattern: SQL "LIKE" pattern for inclusion
                               exclude: SQL "LIKE" pattern of exclusion
                               namespace: ns of the pages we're looking for
                               prefix: namespace prefix
		@type afdDef: dict

		@param nPages: number of pages to find
		@type nPages: int
		"""
		if not afdDef:
			sys.stderr.write(u"Error: cannot find relisted AfDs without the definition of how to find them\n");
			return [];

		# Query to get pages from the relisted AfD category, matching a given
		# pattern, enabling exclusion based on certain titles (e.g. log-pages)
		# and limiting to a given namespace
		afdPageQuery = r"""SELECT /* LIMIT:120 */
                                   page_id, page_title
                                   FROM page JOIN categorylinks ON page_id=cl_from
                                   WHERE cl_to=?
                                   AND page_title LIKE ?
                                   AND page_title NOT LIKE ?
                                   AND page_namespace=?
                                   AND page_random >= RAND()
                                   ORDER BY page_random
                                   LIMIT ?""";
		if self.verbose:
			sys.stderr.write("Info: trying to find {n} relisted articles for deletion...\n".format(n=nPages));

		foundPages = [];
		attempts = 0;
		while attempts < self.maxDBQueryAttempts:
			try:
				dbCursor = self.dbConn.cursor();
				dbCursor.execute(afdPageQuery,
						 (re.sub(" ", "_",
							 afdDef['catname']),
						  afdDef['pattern'],
						  afdDef['exclude'],
						  afdDef['namespace'],
						  nPages));
				for (pageId, pageTitle) in dbCursor:
					foundPages.append(unicode(re.sub('_', ' ', pageTitle),
								  'utf-8', errors='strict'));
			except oursql.Error, e:
				attempts += 1;
				sys.stderr.write("Error: Unable to execute query to get relisted AfDs, possibly retrying!\n");
				sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
				if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
					    or e.errno == oursql.errnos['CR_SERVER_LOST']:
					# lost connection, reconnect
					self.connectDatabase();
			else:
				break;

		if attempts >= self.maxDBQueryAttempts:
			sys.stderr.write("Error: Exhausted number of query attempts, aborting!\n");
			return foundPages;

		if self.verbose:
			sys.stderr.write(u"Info: found {n} relisted AfDs\n".format(n=len(foundPages)));

		# OK, done
		return foundPages;

	def findStubs(self, category=None, nPages=5):
		"""
		Use the database to pick a random stub category,
		then pick a sufficient number of pages from that category.
		Expects a working database connection to exist as self.dbConn

		@param category: The overarching stub category to find a random
                                 category from.
		@type category: unicode

		@param nPages: number of pages to find
		@type nPages: int
		"""
		if not category:
			sys.stderr.write(u"Error: unable to find stubs without a seed category\n");
			return [];

		if self.verbose:
			sys.stderr.write("Info: Trying to find {n} stub tasks...\n".format(n=nPages));

		foundPages = [];

		dbCursor = self.dbConn.cursor();
		exitLoop = False;
		while len(foundPages) < nPages and not exitLoop:
			randStubCategory = None;
			attempts = 0;
			while attempts < self.maxDBQueryAttempts:
				try:
					# pick one random stub category (ns = 14)
					dbCursor.execute(self.randomPageQuery,
							 (re.sub(" ", "_", category).encode('utf-8'),
							  14, 1));
					for (pageId, pageTitle) in dbCursor:
						randStubCategory = unicode(pageTitle, 'utf-8', errors='strict');
				except oursql.Error, e:
					attempts += 1;
					sys.stderr.write("Error: Unable to execute query to get a random stub category, possibly retrying!\n");
					sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
					if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
						    or e.errno == oursql.errnos['CR_SERVER_LOST']:
						# lost connection, reconnect
						self.connectDatabase();
				else: 
					break;

			if not randStubCategory:
				# something went wrong
				sys.stderr.write("Error: Unable to find random stub category, aborting!\n");
				exitLoop = True;
				continue;

			foundPages.extend(self.findPages(category=randStubCategory,
							 nPages=nPages));

		# truncate to self.numPages
		if len(foundPages) > nPages:
			foundPages = foundPages[:nPages];

		if self.verbose:
			sys.stderr.write("Info: Found {n} stub tasks\n".format(n=len(foundPages)));

		return foundPages;

	def findAllPages(self, category=None):
		"""
		Use the database to fetch all main namespace pages from a given category.
		Expects a working database connection to exist as self.dbConn

		@param category: Name of the category to grab pages from
		@type category: unicode
		"""

		if not category:
			sys.stderr.write(u"Error: unable to find pages from a given category without a category name!\n");
			return None;

		if self.verbose:
			sys.stderr.write(u"Info: finding all pages in category {cat}\n".format(cat=category).encode('utf-8'));

		attempts = 0;
		while attempts < self.maxDBQueryAttempts:
			try:
				foundPages = [];
				dbCursor = self.dbConn.cursor();
				dbCursor.execute(self.getAllPagesQuery,
						 (re.sub(' ', '_', category).encode('utf-8'), # catname
						  0) # ns
						 );
				for (pageId, pageTitle) in dbCursor:
					foundPages.append(unicode(re.sub('_', ' ', pageTitle),
								  'utf-8', errors='strict'));
			except oursql.Error, e:
				attempts += 1;
				sys.stderr.write("Error: Unable to execute query to get pages from this category, possibly retrying!\n");
				sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
				if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
					    or e.errno == oursql.errnos['CR_SERVER_LOST']:
					# lost connection, reconnect
					self.connectDatabase();
			else:
				break;
		if attempts >= self.maxDBQueryAttempts:
			sys.stderr.write(u"Error: Exhausted number of query attempts!\n");
		elif self.verbose:
			sys.stderr.write(u"Info: found {n} pages in this category.\n".format(n=len(foundPages)).encode('utf-8'));

		return foundPages;

	def findSubcategoryPages(self, category=None):
		"""
		Use the database to retrieve all direct descendant sub-categories
		of the given category.  Then find all pages in all the sub-categories
		and return the union of all of them

		@param category: Name of the category to grab sub-category pages from
		@type category: unicode
		"""

		if not category:
			sys.stderr.write(u"Error: unable to find sub-categories in a given category without a category name!\n");
			return None;

		if self.verbose:
			sys.stderr.write(u"Info: finding all pages from direct descendants of category {cat}\n".format(cat=category).encode('utf-8'));

		subCategories = [];
		attempts = 0;
		while attempts < self.maxDBQueryAttempts:
			try:
				dbCursor = self.dbConn.cursor();
				dbCursor.execute(self.getAllPagesQuery,
						 (re.sub(' ', '_', category).encode('utf-8'), # catname
						  14) # ns (14=Category)
						 );
				for (pageId, pageTitle) in dbCursor:
					subCategories.append(unicode(re.sub('_', ' ', pageTitle),
								     'utf-8', errors='strict'));
			except oursql.Error, e:
				attempts += 1;
				sys.stderr.write("Error: Unable to execute query to get sub-categories from this category, possibly retrying!\n");
				sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
				if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
					    or e.errno == oursql.errnos['CR_SERVER_LOST']:
					# lost connection, reconnect
					self.connectDatabase();
			else:
				break;
		if attempts >= self.maxDBQueryAttempts:
			sys.stderr.write(u"Error: Exhausted number of query attempts!\n");
			return [];
		elif self.verbose:
			sys.stderr.write(u"Info: found {n} sub-categories in this category.\n".format(n=len(subCategories)).encode('utf-8'));
		
		foundPages = set();
		for categoryName in subCategories:
			subCatPages = self.findAllPages(category=categoryName);
			if subCatPages:
				foundPages = foundPages.union(subCatPages);

		return foundPages;

	def findRandomPages(self, category=None, nPages=5):
		"""
		Use the database to pick a number of pages from a given category.
		Expects a working database connection to exist as self.dbConn

		@param category: Name of the category to grab pages from
		@type category: unicode

		@param nPages: number of pages to fetch
		@type nPages: int
		"""

		if not category:
			sys.stderr.write(u"Error: unable to find pages without a category to pick from\n");
			return [];

		if self.verbose:
			sys.stderr.write(u"Info: finding {n} tasks from category {cat}\n".format(n=nPages, cat=category).encode('utf-8'));

		foundPages = [];
		attempts = 0;
		while attempts < self.maxDBQueryAttempts:
			try:
				dbCursor = self.dbConn.cursor();
				dbCursor.execute(self.randomPageQuery,
						 (re.sub(' ', '_', category).encode('utf-8'), # catname
						  0, # ns
						  nPages) # n pages
						 );
				for (pageId, pageTitle) in dbCursor:
					foundPages.append(unicode(re.sub('_', ' ', pageTitle),
								  'utf-8', errors='strict'));
			except oursql.Error, e:
				attempts += 1;
				sys.stderr.write("Error: Unable to execute query to get pages from this category, possibly retrying!\n");
				sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
				if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
					    or e.errno == oursql.errnos['CR_SERVER_LOST']:
					# lost connection, reconnect
					self.connectDatabase();
			else:
				break;
		if attempts >= self.maxDBQueryAttempts:
			sys.stderr.write(u"Error: Exhausted number of query attempts!\n");
		elif self.verbose:
			sys.stderr.write(u"Info: found {n} tasks from this category.\n".format(n=len(foundPages)).encode('utf-8'));

		return foundPages;


	def findPages(self, category=None, nPages=5):
		"""
		Pick a number of pages from a given category definition through
		sub-methods that access the database.

		@param category: Category-definition of where to grab pages from
		@type category: unicode

		@param nPages: number of pages to fetch
		@type nPages: int
		"""

		if not category:
			sys.stderr.write(u"Error: unable to find pages without a category defition to pick from\n");
			return [];

		if isinstance(category, unicode):
			return self.findRandomPages(category=category,
						    nPages=nPages);
		else:
			# Create a set of all pages we find,
			# from which we'll randomly sample.
			foundPages = set();
			if isinstance(category, list):
				for catName in category:
					if isinstance(catName, unicode):
						foundPages = foundPages.union(self.findAllPages(category=catName));
					elif isinstance(catName, tuple):
						# Category name is the second element
						foundPages = foundPages.union(self.findSubcategoryPages(category=catName[1]));
			elif isinstance(category, tuple):
				# Category name is the second element
				foundPages = self.findSubcategoryPages(category=category[1]);
				
		try:
			# OK, return a random sample of size nPages:
			return random.sample(foundPages, nPages);
		except ValueError:
			# Might happen if we have too few pages to sample,
			# return the whole set.
			foundPages;

	def update(self):
		"""
		Update the list of open tasks.
		"""

		# Query used to log data in the database upon successful update
		# of the opentask page
		logEntryQuery = u"""INSERT INTO {tablename}
                                    (page_selected, page_title, page_len, task_category,
                                     assessed_class, predicted_class, quality,
                                     popcount, popularity, strategy)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""".format(tablename=self.logTableName);


		# connect to the wiki and log in
		if self.verbose:
			sys.stderr.write("Info: connecting to {lang}wiki\n".format(lang=self.lang));

		wikiSite = pywikibot.getSite(self.lang);
		wikiSite.login();

		# Did we log in?
		if wikiSite.username() is None:
			sys.stderr.write("Error: failed to log in correctly, aborting!\n");
			return False;

		# connect to the database
		if self.verbose:
			sys.stderr.write("Info: Connecting to database\n");

		if not self.connectDatabase():
			sys.stderr.write("Error: failed to connect to database, aborting!\n");
			return False;

		# Are we oversampling?
		numPages = self.numPages;
		if self.samplingFactor > 1:
			numPages *= self.samplingFactor;

		# Lets deal with stubs first, where we'll pick random stub categories
		# until we have enough (self.numPages) pages from those
		if self.verbose:
			sys.stderr.write("Info: Finding stub tasks...\n");

		self.foundTasks['stub'] = self.findStubs(category=self.taskDef['stub'],
							 nPages=numPages);

		if self.verbose:
			sys.stderr.write("Info: Done finding stub tasks\n");

		# Handle relisted AfDs, they use a slightly different query
		if "afdrelist" in self.taskDef:
			if self.verbose:
				sys.stderr.write("Info: fetching relisted articles for deletion...\n");
			self.foundTasks['afdrelist'] = self.findAfDs(afdDef=self.taskDef['afdrelist'],
								     nPages=numPages);
			if self.verbose:
				sys.stderr.write(u"Info: done fetching relisted AfDs\n");

		# Now, for all the other categories...
		for (taskId, taskCategory) in self.taskDef.iteritems():
			if taskId == 'stub' \
				    or taskId == 'afdrelist':
				# already done...
				continue;

			if self.verbose:
				sys.stderr.write(u"Info: finding tasks for id {id} from category {cat}\n".format(id=taskId, cat=taskCategory).encode('utf-8'));

			self.foundTasks[taskId] = self.findPages(category=taskCategory,
								 nPages=numPages);
			if self.verbose:
				sys.stderr.write("Info: Find complete, found {n} pages in this category\n".format(n=len(self.foundTasks[taskId])));

		# The data that we want to log about the selected pages,
		# populated as we go through the,
		logEntries = [];

		# Go through the found tasks and turn the list of page titles
		# into a unicode string, we write an unordered list (*)
		# where each list item is a link to a given page
		for (taskId, pageList) in self.foundTasks.iteritems():
			if not pageList:
				self.foundTasks[taskId] = u"None";
				# Add one log entry for this category with no pages.
				logEntries.append({'taskcategory': taskId,
						   'title': None,
						   'length': None,
						   'strategy': None,
						   'popcount': None,
						   'popularity:': None,
						   'quality': None,
						   'predclass': None});
			else:
				if taskId == "afdrelist":
					# Switch SQL LIKE-pattern into a regex we can use
					# to strip that from the page title
					stripPattern = u"";
					pattern = self.taskDef['afdrelist']['pattern'];
					if pattern: # more than ""?
						stripPattern = re.sub('%', "", pattern);
						stripPattern = re.sub("_", " ", stripPattern);

					# If we oversampled, reduce through pop/qual
					if self.samplingFactor > 1:
						pageData = self.selectSubset(pageList=pageList,
									     nPages=self.numPages,
									     replacePattern=stripPattern);
						for (title, metadata) in pageData.iteritems():
							logData = {'taskcategory': taskId,
								   'title': title,
								   'length': metadata['pagedata']['length'],
								   'strategy': metadata['strategy'],
								   'popcount': metadata['pagedata']['popcount'],
								   'popularity': metadata['pagedata']['popularity'],
								   'assessedclass': metadata['pagedata']['quality'],
								   'quality': metadata['pagedata']['prediction'],
								   'predclass': metadata['pagedata']['predclass']};
							logEntries.append(logData);

						# Recreate the page list
						pageList = pageData.keys();
					else:
						# Add log entries with the right title
						# and None-values for the metadata
						for pageTitle in pageList:
							logEntries.append({'taskcategory': taskId,
									   'title': pageTitle,
									   'length': None,
									   'strategy': None,
									   'popcount': None,
									   'popularity:': None,
									   'assessedclass': None,
									   'quality': None,
									   'predclass': None});

					# Build all the links manually
					self.foundTasks[taskId] = u"\n".join([u"* [[{prefix}{fulltitle}|{linktitle}]]".format(prefix=self.taskDef['afdrelist']['prefix'], fulltitle=page, linktitle=re.sub(stripPattern, u"", page)) for page in pageList]);

				else:
					# If we oversampled, reduce through pop/qual
					if self.samplingFactor > 1:
						pageData = self.selectSubset(pageList=pageList,
									     nPages=self.numPages);
						for (title, metadata) in pageData.iteritems():
							logData = {'taskcategory': taskId,
								   'title': title,
								   'length': metadata['pagedata']['length'],
								   'strategy': metadata['strategy'],
								   'popcount': metadata['pagedata']['popcount'],
								   'popularity': metadata['pagedata']['popularity'],
								   'assessedclass': metadata['pagedata']['quality'],
								   'quality': metadata['pagedata']['prediction'],
								   'predclass': metadata['pagedata']['predclass']};
							logEntries.append(logData);

						# Recreate the page list
						pageList = pageData.keys();
					else:
						# Add log entries with the right title
						# and None-values for the metadata
						for pageTitle in pageList:
							logEntries.append({'taskcategory': taskId,
									   'title': pageTitle,
									   'length': None,
									   'strategy': None,
									   'popcount': None,
									   'popularity:': None,
									   'assessedclass': None,
									   'quality': None,
									   'predclass': None});

					self.foundTasks[taskId] = u"\n".join([u"* {title}".format(title=pywikibot.Page(wikiSite, page).title(asLink=True)) for page in pageList]);

		if self.verbose:
			sys.stderr.write(u"Info: Turned page titles into page links, getting wikitext of page {taskpage}\n".format(taskpage=self.taskPage).encode('utf-8'));

		tasktext = None;
		try:
			taskpage = pywikibot.Page(wikiSite, self.taskPage);
			tasktext = taskpage.get();
		except pywikibot.exceptions.NoPage:
			sys.stderr.write(u"Warning: Task page {title} does not exist, aborting!\n".format(title=self.taskPage).encode('utf-8'));
		except pywikibot.exceptions.IsRedirectPage:
			sys.stderr.write(u"Warning: Task page {title} is a redirect, aborting!\n".format(title=self.taskPage).encode('utf-8'));
		except pywikibot.data.api.TimeoutError:
			sys.stderr.write(u"Error: API request to {lang}-WP timed out, unable to get wikitext of {title}, cannot continue!\n".format(lang=self.lang, title=self.taskPage));

		if tasktext is None:
			return False;

		if self.verbose:
			sys.stderr.write(u"Info: got wikitext, substituting page lists...\n");

		for (taskId, pageList) in self.foundTasks.iteritems():
			# note: using re.DOTALL because we need .*? to match \n
			#       since our content is a list
			tasktext = re.sub(ur'<span id="{taskid}">(.*?)</span>'.format(taskid=taskId),
					  ur'<span id="{taskid}">\n{pagelist}</span>'.format(taskid=taskId, pagelist=pageList),
					  tasktext, flags=re.DOTALL);

		if self.testRun:
			sys.stderr.write(u"Info: Running a test, printing out new wikitext:\n\n");
			print tasktext.encode('utf-8');
		else:
			if self.verbose:
				sys.stderr.write(u"Info: Saving page with new text\n");
			taskpage.text = tasktext;
			try:
				taskpage.save(comment=self.editComment);
			except pywikibot.exceptions.EditConflict:
				sys.stderr.write(u"Error: Saving page {title} failed, edit conflict.\n".format(title=self.taskPage).encode('utf-8'));
				return False;
			except pywikibot.exceptions.PageNotSaved as e:
				sys.stderr.write(u"Error: Saving page {title} failed.\nError: {etext}\n".format(title=self.taskPage, etext=e).encode('utf-8'));
				return False;
			except pywikibot.data.api.TimeoutError:
				sys.stderr.write(u"Error: Saving page {title} failed, API request timeout fatal\n".format(title=self.taskPage).encode('utf-8'));
				return False
			else:
				# Everything went OK, switch connection to the SQL server
				# used for logging.
				if not self.connectDatabase(hostName=self.logDBHost,
							    dbName=self.logDBName):
					sys.stderr.write(u"Error: Unable to connect to DB server {server} using DB {database} for logging\n".format(server=self.logDBHost, database=self.logDBName));
				else:
					timestamp = pywikibot.Timestamp.fromISOformat(taskpage.editTime());
					with self.dbConn.cursor() as dbCursor:
						for logData in logEntries:
							try:
								if logData['title']:
									logData['title'] = logData['title'].encode('utf-8');
								dbCursor.execute(logEntryQuery,
										 (timestamp,
										  logData['title'],
										  logData['length'],
										  logData['taskcategory'],
										  logData['assessedclass'],
										  logData['predclass'],
										  logData['quality'],
										  logData['popcount'],
										  logData['popularity'],
										  logData['strategy']));
							# NOTE: Consider catching something else than oursql.Error,
							# that also catches warnings.
 							except oursql.Error, e:
								sys.stderr.write("Error: Unable to insert log entry!\n");
								sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));

		# OK, all done
		if self.verbose:
			sys.stderr.write("Info: List of open tasks successfully updated!\n");

		if not self.disconnectDatabase():
			sys.stderr.write(u"Warning: Unable to cleanly disconnect from the database!\n");

		return True;

	def selectSubset(self, pageList=[], nPages=5, replacePattern=None):
		"""
		Expects a list of pages of length greater than self.numPages, from
		which we will pick self.numPages pages based on some criteria.

		@param pageList: page titles we'll want to select a subset from
		@type pageList: list

		@param nPages: number of pages we want to end up with
		@type nPages: int

		@param replacePattern: regular expression pattern for replacement,
                                       used to strip page titles so we correctly
				       inspect an associated page (e.g. for AfDs)
		@type replacePattern: unicode
		"""

		pageMapping = {};
		popQualData = [];

		# number of picks from each non-random selection
		nNonRandom = nPages/5;
		sortedPages = {};

		# The Pop/Qual server takes care of gathering popularity and quality
		# data as efficiently as possible for our list of pages.
		if replacePattern:
			# Map replaced page titles to original titles.
			for pageTitle in pageList:
				replacedTitle = re.sub(replacePattern, u"", pageTitle);
				pageMapping[replacedTitle] = pageTitle;
			popQualData = self.popQualServer.getPopQualList(pageMapping.keys());
		else:
			popQualData = self.popQualServer.getPopQualList(pageList);

		# Now, how to actually select the pages?
		# 0: keep pages for which we have data
		popQualData = [pageData for pageData in popQualData \
				       if pageData['status'] == 200 \
				       and pageData['pred-numeric'] > 0];

		# 1: sort by popularity, high to low
		sortedPages['highpop'] = sorted(popQualData,
						key=lambda pageData: pageData['popcount'],
						reverse=True);

		# 2: sort by quality, high to low
		sortedPages['highqual'] = sorted(popQualData,
						 key=lambda pageData: pageData['pred-numeric'],
						 reverse=True);

		# 3: sort by quality, low to high
		#   (most likely correlated with popularity, so we don't need both)
		sortedPages['lowqual'] = sorted(popQualData,
						key=lambda pageData: pageData['pred-numeric']);
		# 4: sort by discrepancy between popularity and quality
		#   (since we already sorted by high popularity, we just sort it again by quality (low to high))
		sortedPages['maxlove'] = sorted(sortedPages['highpop'],
						key=lambda pageData: pageData['pred-numeric']);
		# randomise the strategies
		strategies = sortedPages.keys();
		random.shuffle(strategies);

		selectedPages = {};

		# Pick pages from the non-random strategies
		for strategy in strategies:
			i = 0;
			nSelected = 0;
			while nSelected < nNonRandom and i < len(sortedPages[strategy]):
				pageTitle = sortedPages[strategy][i]['title'];
				try:
					x = selectedPages[pageTitle];
				except KeyError:
					selectedPages[pageTitle] = {'strategy': strategy,
								    'pagedata': sortedPages[strategy][i]};
					nSelected += 1;
				i += 1;

		# Fill up the rest with randomly picked pages
		while len(selectedPages) < nPages:
			randPage = random.choice(popQualData);
			try:
				x = selectedPages[randPage['title']];
			except KeyError:
				selectedPages[randPage['title']] = {'strategy': 'random',
								    'pagedata': randPage};

		# if we replaced titles, reverse that after selection
		if replacePattern:
			replacedTitles = {};
			for (pageTitle, pageData) in selectedPages.iteritems():
				mappedTitle = pageMapping[pageTitle];
				replacedTitles[mappedTitle] = pageData;
			selectedPages = replacedTitles;

		return selectedPages;

def main():
	import argparse;

	cli_parser = argparse.ArgumentParser(
		description="Program to update list of open tasks for a given Wikipedia."
		);

	# Option to control the edit comment
	cli_parser.add_argument('-c', '--comment', default=None,
				help="edit comment to use when saving the new page");

	# Option to control the list of tasks
	cli_parser.add_argument('-d', '--taskdef', default=None,
				help="repr of dictionary mapping task IDs to task categories");

	# Option to control where the classifier configuration file is located
	cli_parser.add_argument('-f', '--classifier', default=None, metavar="<classifier-path>",
				help="path to file with hostname and port of the quality classifier");
	# Option to control language
	cli_parser.add_argument('-l', '--lang', default=u'en',
				help="language code of the Wikipedia we're working on (default: en)");

	# Option to control the MySQL configuration file
	cli_parser.add_argument('-m', '--mysqlconf', default=None,
				help="path to MySQL configuration file");

	# Option to control number of pages per category of tasks
	cli_parser.add_argument('-n', '--numpages', default=5,
				help="number of pages displayed in each task category (default: 5)");

	# Option to control the number of oversampled pages
	# when selecting based on popularity and quality
	cli_parser.add_argument('-o', '--oversample', default=20, type=int,
				help="multiplication factor used for oversampling and selection by popularity and quality. (a value of '1' turns it off)");

	# Option to control where the list of open tasks are
	cli_parser.add_argument('-p', '--page', default=None,
				help="title of the page with the open tasks");

	# Test option
	cli_parser.add_argument('-t', '--test', action='store_true',
				help='if set the program does not save the page, writes final wikitext to stdout instead');
	
	# Verbosity option
	cli_parser.add_argument('-v', '--verbose', action='store_true',
				help='if set informational output is written to stderr');

	args = cli_parser.parse_args();

	if args.taskdef:
		args.taskdef = eval(args.taskdef);

	taskUpdater = OpenTaskUpdater(verbose=args.verbose, lang=args.lang,
				      mysqlConf=args.mysqlconf, taskPage=args.page,
				      taskDef=args.taskdef, pagesPerCategory=args.numpages,
				      editComment=args.comment, testRun=args.test,
				      samplingFactor=args.oversample,
				      classifierFile=args.classifier);
	try:
		taskUpdater.update();
	finally:
		taskUpdater.stopme();

if __name__ == "__main__":
	main();
