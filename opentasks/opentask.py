#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Program to update a list of open tasks for a Wikipedia.
Copyright (C) 2012-2014 SuggestBot dev group

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

import os
import sys
import re
import random
import logging
import oursql

from datetime import datetime

import pywikibot

class OpenTaskUpdater:
	def __init__(self, lang=None, mysqlConf=None,
		     taskPage=None, taskDef=None, pagesPerCategory=5,
		     editComment=None, testRun=False, maxDBQueryAttempts=3):
		"""
		Instantiate an object intended to update the list of open tasks.
		
		@param lang: Language code of the Wikipedia we're working on.
		@type lang: str

		@param mysqlConf: Path to MySQL's configuration file
                                  used for authentication
		@type mysqlConf: str

		@param taskPage: Title of the page containing open tasks
		@type taskPage: unicode

		@param taskDef: Dictionary mapping task IDs
                                to categories containing tasks
		@type taskDef: dict

		@param pagesPerCategory: No. of desired pages per task category
		@type pagesPerCategory: int
		
		@param editComment: Edit comment used on successful update
		@type editComment: unicode

		@param testRun: Do a test run? Prints the resulting wikitext
                                to stdout instead of saving the page.
		@type testRun: bool

		@param maxDBQueryAttempts: max number of database query
                                           attempts before aborting.
		@type maxDBQueryAttempts: int
		"""
		
		self.lang = 'en'
		if lang:
			self.lang = lang

		self.mysqlConf = "~/replica.my.cnf"
		if mysqlConf:
			self.mysqlConf = mysqlConf

		self.numPages = pagesPerCategory

		self.editComment = u"Updating list of open tasks..."
		if editComment:
			self.editComment = editComment

		self.taskPage = u"Wikipedia:Community portal/Open tasks"
		if taskPage:
			self.taskPage = taskPage

		if taskDef:
			self.taskDef = taskDef
		else:
			# Wikify is deleted, the following templates and
			# associated categories take over for it:
			# {{dead end}}, {{underlinked}}, and {{overlinked}}

			# "leadcleanup" refers to
			# "Category:Wikipedia introduction cleanup"
			# where amongst others, {{inadequate lead}},
			# {{lead too short}}, and {{lead too long}} end up

			# Task def is a dictionary where keys are IDs of
			# the span elements to which the list of pages will go.
			# Values are one of:
			# 1: unicode string, name of category to grab pages from
			# 2: list of unicode strings, names of categories,
			#    pages will be grabbed randomly from
			#    all categories combined
			#
			# The name of a category can also be a tuple of the form
			# ("use-subs", u"[category name]") which will indicate
			# that we need to grab all sub-categories from
			# the given category. Pages will then be grabbed
			# randomly from all the sub-categories.

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
				}

		self.testRun = testRun

		self.dbConn = None
		self.dbCursor = None
		self.maxDBQueryAttempts = maxDBQueryAttempts
		
		# Dictionary of results, a list of pages for each task
		self.foundTasks = dict((taskId, []) for taskId in self.taskDef.keys())

		# Query to fetch a number of random pages from a given category.
		self.randomPageQuery = r"""SELECT /* LIMIT:120 */
                                           page_id, page_title
                                           FROM page JOIN categorylinks
                                           ON page_id=cl_from
                                           WHERE cl_to=?
                                           AND page_namespace=?
                                           AND page_random >= RAND()
                                           ORDER BY page_random LIMIT ?"""

		# Query to fetch all pages in a given namespace
		# from a given category
		self.getAllPagesQuery = u"""SELECT page_id, page_title
                                            FROM page JOIN categorylinks
                                            ON page_id=cl_from
                                            WHERE cl_to=?
                                            AND page_namespace=?"""

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
			hostName = u"{lang}wiki.labsdb".format(lang=self.lang)
			dbName = u"{lang}wiki_p".format(lang=self.lang)

		if self.dbConn:
			self.disconnectDatabase()

		try:
			self.dbConn = oursql.connect(db=dbName,
						     host=hostName,
						     read_default_file=os.path.expanduser(self.mysqlConf),
						     use_unicode=False,
						     charset=None)
			self.dbCursor = self.dbConn.cursor()
		except oursql.Error, e:
			logging.error("unable to connect to database {0} on server {1}".format(dbName, hostname))
			logging.error("oursqul error {0}: {1}".format(e.args[0], e.args[1]))
			return False
		
		# Ok, done
		return True

	def disconnectDatabase(self):
		if not self.dbConn or not self.dbCursor:
			logging.warning(u"can't disconnect connections that are None")
			return False
		try:
			self.dbCursor.close()
			self.dbConn.close()
		except oursql.Error, e:
			logging.error("unable to disconnect from database")
			logging.error("oursql error {0}: {1}".format(e.args[0], e.args[1]))
			return False
		# Ok, done
		return True

	def stopme(self):
		pywikibot.stopme()

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
			logging.error(u"cannot find relisted AfDs without the definition of how to find them")
			return []

		# Query to get pages from the relisted AfD category,
		# matching a given pattern, enabling exclusion based
		# on certain titles (e.g. log-pages) and limiting
		# to a given namespace
		afdPageQuery = r"""SELECT /* LIMIT:120 */
                                   page_id, page_title
                                   FROM page JOIN categorylinks
                                   ON page_id=cl_from
                                   WHERE cl_to=?
                                   AND page_title LIKE ?
                                   AND page_title NOT LIKE ?
                                   AND page_namespace=?
                                   AND page_random >= RAND()
                                   ORDER BY page_random
                                   LIMIT ?"""

		logging.info("trying to find {n} relisted articles for deletion...".format(n=nPages))

		foundPages = []
		attempts = 0
		while attempts < self.maxDBQueryAttempts:
			try:
				dbCursor = self.dbConn.cursor()
				dbCursor.execute(afdPageQuery,
						 (re.sub(" ", "_",
							 afdDef['catname']),
						  afdDef['pattern'],
						  afdDef['exclude'],
						  afdDef['namespace'],
						  nPages));
				for (pageId, pageTitle) in dbCursor:
					foundPages.append(unicode(re.sub('_', ' ', pageTitle),
								  'utf-8', errors='strict'))
			except oursql.Error, e:
				attempts += 1
				logging.error("unable to execute query to get relisted AfDs, possibly retrying")
				logging.error("oursql error {0}: {1}".format(e.args[0], e.args[1]))
				if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
					    or e.errno == oursql.errnos['CR_SERVER_LOST']:
					# lost connection, reconnect
					self.connectDatabase()
			else:
				break

		if attempts >= self.maxDBQueryAttempts:
			logging.error("exhausted number of query attempts, aborting")
			return foundPages

		logging.info(u"found {n} relisted AfDs".format(n=len(foundPages)))

		# OK, done
		return foundPages

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
			logging.error(u"unable to find stubs without a seed category")
			return []

		logging.info("trying to find {n} stub tasks...".format(n=nPages))

		foundPages = []
		
		dbCursor = self.dbConn.cursor()
		exitLoop = False
		while len(foundPages) < nPages and not exitLoop:
			randStubCategory = None
			attempts = 0
			while attempts < self.maxDBQueryAttempts:
				try:
					# pick one random stub category (ns = 14)
					dbCursor.execute(self.randomPageQuery,
							 (re.sub(" ", "_", category).encode('utf-8'),
							  14, 1))
					for (pageId, pageTitle) in dbCursor:
						randStubCategory = unicode(pageTitle, 'utf-8', errors='strict')
				except oursql.Error, e:
					attempts += 1
					logging.error("unable to execute query to get a random stub category, possibly retrying");
					logging.error("oursql error {0}: {1}".format(e.args[0], e.args[1]))
					if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
						    or e.errno == oursql.errnos['CR_SERVER_LOST']:
						# lost connection, reconnect
						self.connectDatabase()
				else: 
					break

			if not randStubCategory:
				# something went wrong
				logging.error("unable to find random stub category, aborting");
				exitLoop = True
				continue

			foundPages.extend(self.findPages(category=randStubCategory,
							 nPages=nPages))

		# truncate to self.numPages
		if len(foundPages) > nPages:
			foundPages = foundPages[:nPages]

		logging.info("found {n} stub tasks".format(n=len(foundPages)))

		return foundPages

	def findAllPages(self, category=None):
		"""
		Use the database to fetch all main namespace pages from
		a given category.  Expects a working database connection
		to exist as self.dbConn

		@param category: Name of the category to grab pages from
		@type category: unicode
		"""

		if not category:
			logging.error(u"unable to find pages from a given category without a category name")
			return None

		logging.info(u"finding all pages in category {cat}".format(cat=category).encode('utf-8'))

		attempts = 0
		while attempts < self.maxDBQueryAttempts:
			try:
				foundPages = []
				dbCursor = self.dbConn.cursor()
				dbCursor.execute(self.getAllPagesQuery,
						 (re.sub(' ', '_', category).encode('utf-8'), # catname
						  0) # ns
						 )
				for (pageId, pageTitle) in dbCursor:
					foundPages.append(unicode(re.sub('_', ' ', pageTitle),
								  'utf-8', errors='strict'))
			except oursql.Error, e:
				attempts += 1
				logging.error("unable to execute query to get pages from this category, possibly retrying")
				logging.error("oursql error {0}: {1}".format(e.args[0], e.args[1]))
				if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
					    or e.errno == oursql.errnos['CR_SERVER_LOST']:
					# lost connection, reconnect
					self.connectDatabase()
			else:
				break
		if attempts >= self.maxDBQueryAttempts:
			logging.error(u"exhausted number of query attempts")

		logging.info(u"found {n} pages in this category".format(n=len(foundPages)))
		return foundPages

	def findSubcategoryPages(self, category=None):
		"""
		Use the database to retrieve all direct descendant
		sub-categories of the given category.  Then find all pages
		in all the sub-categories and return the union of all of them.

		@param category: Name of the category from which we'll
		                 grab sub-categories.
		@type category: unicode
		"""

		if not category:
			logging.error(u"unable to find sub-categories in a given category without a category name")
			return None

		logging.info(u"finding all pages from direct descendants of category {cat}".format(cat=category).encode('utf-8'))

		subCategories = []
		attempts = 0
		while attempts < self.maxDBQueryAttempts:
			try:
				dbCursor = self.dbConn.cursor()
				dbCursor.execute(self.getAllPagesQuery,
						 (re.sub(' ', '_', category).encode('utf-8'), # catname
						  14) # ns (14=Category)
						 )
				for (pageId, pageTitle) in dbCursor:
					subCategories.append(unicode(re.sub('_', ' ', pageTitle),
								     'utf-8', errors='strict'))
			except oursql.Error, e:
				attempts += 1;
				logging.error("unable to execute query to get sub-categories from this category, possibly retrying")
				logging.error("oursql error {0}: {1}".format(e.args[0], e.args[1]))
				if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
					    or e.errno == oursql.errnos['CR_SERVER_LOST']:
					# lost connection, reconnect
					self.connectDatabase()
			else:
				break
		if attempts >= self.maxDBQueryAttempts:
			logging.error(u"exhausted number of query attempts")
			return []

		logging.info(u"found {n} sub-categories in this category".format(n=len(subCategories)))
		
		foundPages = set()
		for categoryName in subCategories:
			subCatPages = self.findAllPages(category=categoryName)
			if subCatPages:
				foundPages = foundPages.union(subCatPages)

		return foundPages

	def findRandomPages(self, category=None, nPages=5):
		"""
		Use the database to pick a number of pages from
		a given category. Expects a working database connection
		to exist as self.dbConn

		@param category: Name of the category to grab pages from
		@type category: unicode

		@param nPages: number of pages to fetch
		@type nPages: int
		"""

		if not category:
			logging.error(u"unable to find pages without a category to pick from")
			return []

		logging.info(u"finding {n} tasks from category {cat}".format(n=nPages, cat=category).encode('utf-8'))

		foundPages = []
		attempts = 0
		while attempts < self.maxDBQueryAttempts:
			try:
				dbCursor = self.dbConn.cursor()
				dbCursor.execute(self.randomPageQuery,
						 (re.sub(' ', '_', category).encode('utf-8'), # catname
						  0, # ns
						  nPages) # n pages
						 )
				for (pageId, pageTitle) in dbCursor:
					foundPages.append(unicode(re.sub('_', ' ', pageTitle),
								  'utf-8', errors='strict'))
			except oursql.Error, e:
				attempts += 1;
				logging.error("unable to execute query to get pages from this category, possibly retrying")
				logging.error("oursql error {0}: {1}".format(e.args[0], e.args[1]))
				if e.errno == oursql.errnos['CR_SERVER_GONE_ERROR'] \
					    or e.errno == oursql.errnos['CR_SERVER_LOST']:
					# lost connection, reconnect
					self.connectDatabase()
			else:
				break
		if attempts >= self.maxDBQueryAttempts:
			logging.error(u"exhausted number of query attempts")

		logging.info(u"found {n} tasks from this category".format(n=len(foundPages)).encode('utf-8'))

		return foundPages


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
			logging.error(u"unable to find pages without a category defition to pick from")
			return []

		if isinstance(category, unicode):
			return self.findRandomPages(category=category,
						    nPages=nPages)
		else:
			# Create a set of all pages we find,
			# from which we'll randomly sample.
			foundPages = set()
			if isinstance(category, list):
				for catName in category:
					if isinstance(catName, unicode):
						foundPages = foundPages.union(self.findAllPages(category=catName))
					elif isinstance(catName, tuple):
						# Category name is the second element
						foundPages = foundPages.union(self.findSubcategoryPages(category=catName[1]))
			elif isinstance(category, tuple):
				# Category name is the second element
				foundPages = self.findSubcategoryPages(category=category[1])
				
		try:
			# OK, return a random sample of size nPages:
			return random.sample(foundPages, nPages)
		except ValueError:
			# Might happen if we have too few pages to sample,
			# return the whole set.
			return foundPages;

	def update(self):
		"""
		Update the list of open tasks.
		"""

		# connect to the wiki and log in
		logging.info("connecting to {lang}wiki".format(lang=self.lang))

		wikiSite = pywikibot.getSite(self.lang)
		# wikiSite.login()

		# Did we log in?
		if wikiSite.username() is None:
			logging.error("failed to log in correctly, aborting")
			return False

		# connect to the database
		logging.info("connecting to database")

		if not self.connectDatabase():
			logging.error("failed to connect to database, aborting")
			return False

		# Lets deal with stubs first, where we'll pick random stub
		# categories until we have enough
		# (self.numPages) pages from those
		logging.info("finding stub tasks...")
		self.foundTasks['stub'] = self.findStubs(category=self.taskDef['stub'],
							 nPages=self.numPages)

		logging.info("done finding stub tasks");

		# Handle relisted AfDs, they use a slightly different query
		if "afdrelist" in self.taskDef:
			logging.info("fetching relisted articles for deletion...");
			self.foundTasks['afdrelist'] = self.findAfDs(afdDef=self.taskDef['afdrelist'],
								     nPages=self.numPages)
			logging.info(u"done fetching relisted AfDs")

		# Now, for all the other categories...
		for (taskId, taskCategory) in self.taskDef.iteritems():
			if taskId == 'stub' \
				    or taskId == 'afdrelist':
				# already done...
				continue

			logging.info(u"finding tasks for id {id} from category {cat}".format(id=taskId, cat=taskCategory).encode('utf-8'))

			self.foundTasks[taskId] = self.findPages(category=taskCategory,
								 nPages=self.numPages)
			logging.info("find complete, found {n} pages in this category".format(n=len(self.foundTasks[taskId])))

		# Go through the found tasks and turn the list of page titles
		# into a unicode string, we write an unordered list (*)
		# where each list item is a link to a given page
		for (taskId, pageList) in self.foundTasks.iteritems():
			if not pageList:
				self.foundTasks[taskId] = u"None"
			else:
				if taskId == "afdrelist":
					# Switch SQL LIKE-pattern into a regex
					# we can use to strip that from
					# the page title
					stripPattern = u""
					pattern = self.taskDef['afdrelist']['pattern']
					if pattern: # more than ""?
						stripPattern = re.sub('%', "", pattern)
						stripPattern = re.sub("_", " ", stripPattern)
					# Build all the links manually
					self.foundTasks[taskId] = u"\n".join([u"* [[{prefix}{fulltitle}|{linktitle}]]".format(prefix=self.taskDef['afdrelist']['prefix'], fulltitle=page, linktitle=re.sub(stripPattern, u"", page)) for page in pageList])

				else:
					self.foundTasks[taskId] = u"\n".join([u"* {title}".format(title=pywikibot.Page(wikiSite, page).title(asLink=True)) for page in pageList])

		logging.info(u"turned page titles into page links, getting wikitext of page {taskpage}".format(taskpage=self.taskPage).encode('utf-8'))

		tasktext = None;
		try:
			taskpage = pywikibot.Page(wikiSite, self.taskPage)
			tasktext = taskpage.get()
		except pywikibot.exceptions.NoPage:
			logging.warning(u"task page {title} does not exist, aborting".format(title=self.taskPage).encode('utf-8'))
		except pywikibot.exceptions.IsRedirectPage:
			logging.warning(u"task page {title} is a redirect, aborting".format(title=self.taskPage).encode('utf-8'))
		except pywikibot.data.api.TimeoutError:
			logging.error(u"API request to {lang}-WP timed out, unable to get wikitext of {title}, cannot continue".format(lang=self.lang, title=self.taskPage))

		if tasktext is None:
			return False

		logging.info(u"got wikitext, substituting page lists...");

		for (taskId, pageList) in self.foundTasks.iteritems():
			# note: using re.DOTALL because we need .*? to match \n
			#       since our content is a list
			tasktext = re.sub(ur'<div id="{taskid}">(.*?)</div>'.format(taskid=taskId),
					  ur'<div id="{taskid}">\n{pagelist}</div>'.format(taskid=taskId, pagelist=pageList),
					  tasktext, flags=re.DOTALL)

		if self.testRun:
			logging.info(u"running a test, printing out new wikitext:\n")
			print(tasktext.encode('utf-8'))
		else:
			logging.info(u"saving page with new text")
			taskpage.text = tasktext
			try:
				taskpage.save(comment=self.editComment)
			except pywikibot.exceptions.EditConflict:
				logging.error(u"saving page {title} failed, edit conflict".format(title=self.taskPage).encode('utf-8'))
				return False;
			except pywikibot.exceptions.PageNotSaved as e:
				logging.error(u"saving page {title} failed")
				logging.error(u"pywikibot error: {etext}".format(title=self.taskPage, etext=e).encode('utf-8'))
				return False
			except pywikibot.data.api.TimeoutError:
				logging.error(u"saving page {title} failed, API request timeout fatal".format(title=self.taskPage).encode('utf-8'))
				return False

		logging.info("list of open tasks successfully updated")

		if not self.disconnectDatabase():
			logging.warning(u"unable to cleanly disconnect from the database")

		return True

def main():
	import argparse

	cli_parser = argparse.ArgumentParser(
		description="Program to update list of open tasks for a given Wikipedia.")

	# Option to control the edit comment
	cli_parser.add_argument('-c', '--comment', default=None,
				help="edit comment to use when saving the new page")

	# Option to control the list of tasks
	cli_parser.add_argument('-d', '--taskdef', default=None,
				help="repr of dictionary mapping task IDs to task categories")

	# Option to control language
	cli_parser.add_argument('-l', '--lang', default=u'en',
				help="language code of the Wikipedia we're working on (default: en)")

	# Option to control the MySQL configuration file
	cli_parser.add_argument('-m', '--mysqlconf', default=None,
				help="path to MySQL configuration file")

	# Option to control number of pages per category of tasks
	cli_parser.add_argument('-n', '--numpages', default=5,
				help="number of pages displayed in each task category (default: 5)")

	# Option to control where the list of open tasks are
	cli_parser.add_argument('-p', '--page', default=None,
				help="title of the page with the open tasks")

	# Test option
	cli_parser.add_argument('-t', '--test', action='store_true',
				help='if set the program does not save the page, writes final wikitext to stdout instead')
	
	# Verbosity option
	cli_parser.add_argument('-v', '--verbose', action='store_true',
				help='if set informational output is written to stderr')

	args = cli_parser.parse_args()

	if args.verbose:
		logging.basicConfig(level=logging.DEBUG)

	if args.taskdef:
		args.taskdef = eval(args.taskdef)

	taskUpdater = OpenTaskUpdater(lang=args.lang,
				      mysqlConf=args.mysqlconf,
				      taskPage=args.page,
				      taskDef=args.taskdef,
				      pagesPerCategory=args.numpages,
				      editComment=args.comment,
				      testRun=args.test)
	try:
		taskUpdater.update()
	finally:
		taskUpdater.stopme()

if __name__ == "__main__":
	main()
