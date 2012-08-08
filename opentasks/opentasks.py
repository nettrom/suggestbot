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
import oursql;

from datetime import datetime;

import pywikibot;

class OpenTaskUpdater:
	def __init__(self, verbose=False, lang=None, mysqlConf=None,
		     taskPage=None, taskDef=None, pagesPerCategory=5,
		     editComment=None, testRun=False, updateInterval=60):
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
			self.taskDef = {
				"wikify": u"All articles that need to be wikified",
				"orphan": u"All orphaned articles",
				"copyedit": u"All articles needing copy edit",
				"update": u"All Wikipedia articles in need of updating",
				"style" : u"All articles needing style editing",
				"translate": u"Wikipedia articles needing cleanup after translation",
				"cleanup": u"All pages needing cleanup",
				"verify": u"All pages needing factual verification",
				"npov": u"All NPOV disputes",
				"or" : u"All articles that may contain original research",
				"merge": u"All articles to be merged",
				"split": u"All articles to be split",
				"expand" : u"All articles to be expanded",
				"stub" : u"Stub categories",
				"afdrelist" : {
					"catname": u"Relisted AfD debates",
					"pattern": u"Articles_for_deletion/%", # filter
					"exclude": u"%/Log/%", # remove these
					"namespace": 4, # namespace of pages we're looking for
					"prefix": u"Wikipedia:", # namespace prefix
					},
				};

		self.testRun = testRun;

		self.verbose = verbose;
		self.dbConn = None;
		self.dbCursor = None;

		# Dictionary of results, a list of pages for each task
		self.foundTasks = dict([(taskId, []) for taskId in self.taskDef.keys()]);

	def connectDatabase(self):
		'''
		Connect to the database associated with our Wikipedia.
		'''
		dbName = u"{lang}wiki_p".format(lang=self.lang);
		hostName = u"{lang}wiki-p.rrdb.toolserver.org".format(lang=self.lang);

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

	def update(self):
		"""
		Update the list of open tasks.
		"""

		# Query to fetch a list of random pages, used to find a stub category
		# to select stubs from, and random pages from any categories
		randomPageQuery = r"""SELECT page_id, page_title
                                      FROM page JOIN categorylinks ON page_id=cl_from
                                      WHERE cl_to=?
                                      AND page_namespace=?
                                      AND page_random >= RAND()
                                      ORDER BY page_random LIMIT ?""";

		# Query to get pages from the relisted AfD category, matching a given
		# pattern, enabling exclusion based on certain titles (e.g. log-pages)
		# and limiting to a given namespace
		afdPageQuery = r"""SELECT page_id, page_title
                                   FROM page JOIN categorylinks ON page_id=cl_from
                                   WHERE cl_to=?
                                   AND page_title LIKE ?
                                   AND page_title NOT LIKE ?
                                   AND page_namespace=?
                                   AND page_random >= RAND()
                                   ORDER BY page_random
                                   LIMIT ?""";

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

		# Lets deal with stubs first, where we'll pick random stub categories
		# until we have enough (self.numPages) pages from those
		if self.verbose:
			sys.stderr.write("Info: Finding stub tasks...\n");

		foundPages = [];
		while len(foundPages) < self.numPages:
			randStubCategory = None;
			try:
				# pick one random stub category (ns = 14)
				self.dbCursor.execute(randomPageQuery,
						      (re.sub(" ", "_", self.taskDef['stub']).encode('utf-8'),
						      14, 1));
				for (pageId, pageTitle) in self.dbCursor:
					randStubCategory = unicode(pageTitle, 'utf-8', errors='strict');
			except oursql.Error, e:
				sys.stderr.write("Error: Unable to execute query to get a random stub category, aborting!\n");
				sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
				return False;

			if not randStubCategory:
				# something went wrong
				sys.stderr.write("Error: Unable to find random stub category, aborting!\n");
				return False;

			try:
				# pick random pages from the given category (ns = 0)
				self.dbCursor.execute(randomPageQuery,
						      (randStubCategory.encode('utf-8'), 0, 5));
				for (pageId, pageTitle) in self.dbCursor:
					foundPages.append(unicode(re.sub('_', ' ', pageTitle),
								  'utf-8', errors='strict'));
			except oursql.Error, e:
				sys.stderr.write(u"Error: Unable to execute query to get random pages from category {cat}, aborting!\n".format(cat=randStubCategory).encode('utf-8'));
				sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
				return False;

		# truncate to self.numPages
		if len(foundPages) > self.numPages:
			foundPages = foundPages[:self.numPages];

		self.foundTasks['stub'] = foundPages;

		if self.verbose:
			sys.stderr.write("Info: Done finding stub tasks\n");

		# Handle relisted AfDs, they use a slightly different query
		if "afdrelist" in self.taskDef:
			if self.verbose:
				sys.stderr.write("Info: fetching relisted articles for deletion...\n");
			try:
				foundPages = [];
				self.dbCursor.execute(afdPageQuery,
						      (re.sub(" ", "_",
							      self.taskDef['afdrelist']['catname']),
						       self.taskDef['afdrelist']['pattern'],
						       self.taskDef['afdrelist']['exclude'],
						       self.taskDef['afdrelist']['namespace'],
						       self.numPages));
				for (pageId, pageTitle) in self.dbCursor:
					foundPages.append(unicode(re.sub('_', ' ', pageTitle),
								  'utf-8', errors='strict'));
				sys.stderr.write("Debug: found {n} relisted AfDs\n".format(n=len(foundPages)));
				self.foundTasks['afdrelist'] = foundPages;
			except oursql.Error, e:
				sys.stderr.write("Error: Unable to execute query to get relisted AfDs, aborting!\n");
				sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
				return False;

			if self.verbose:
				sys.stderr.write(u"Info: done fetching relisted AfDs\n");

		# Now, for all the other categories...
		for (taskId, taskCategory) in self.taskDef.iteritems():
			if taskId == 'stub' \
				    or taskId == 'afdrelist':
				# already done...
				continue;

			if self.verbose:
				sys.stderr.write(u"Info: finding {id} tasks from category {cat}\n".format(id=taskId, cat=taskCategory).encode('utf-8'));

			foundPages = [];

			try:
				self.dbCursor.execute(randomPageQuery,
						      (re.sub(' ', '_', self.taskDef[taskId]).encode('utf-8'),
						       0, self.numPages));
				for (pageId, pageTitle) in self.dbCursor:
					foundPages.append(unicode(re.sub('_', ' ', pageTitle),
								  'utf-8', errors='strict'));
			except oursql.Error, e:
				sys.stderr.write("Error: Unable to execute query to get pages from this category, skipping!\n");
				sys.stderr.write("Error {0}: {1}\n".format(e.args[0], e.args[1]));
				continue;

			self.foundTasks[taskId] = foundPages;

			if self.verbose:
				sys.stderr.write("Info: Find complete, found {n} pages in this category\n".format(n=len(foundPages)));

		# Go through the found tasks and turn the list of page titles
		# into a unicode string with a list of links...
		for (taskId, pageList) in self.foundTasks.iteritems():
			if not pageList:
				self.foundTasks[taskId] = u"None, ";
			else:
				if taskId == "afdrelist":
					# Switch SQL LIKE-pattern into a regex we can use
					# to strip that from the page title
					stripPattern = u"";
					pattern = self.taskDef['afdrelist']['pattern'];
					if pattern: # more than ""?
						stripPattern = re.sub('%', "", pattern);
						stripPattern = re.sub("_", " ", stripPattern);

					# Build all the links manually
					self.foundTasks[taskId] = u", ".join([u"[[{prefix}{fulltitle}|{linktitle}]]".format(prefix=self.taskDef['afdrelist']['prefix'], fulltitle=page, linktitle=re.sub(stripPattern, u"", page)) for page in pageList]);

				else:
					self.foundTasks[taskId] = u", ".join([pywikibot.Page(wikiSite, page).title(asLink=True) for page in pageList]);

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
			tasktext = re.sub(ur'<span id="{taskid}">(.*?)</span>'.format(taskid=taskId),
					  ur'<span id="{taskid}">{pagelist}</span>'.format(taskid=taskId, pagelist=pageList),
					  tasktext);

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

		# OK, done
		if self.verbose:
			sys.stderr.write("Info: List of open tasks successfully updated!\n");

		if not self.disconnectDatabase():
			sys.stderr.write(u"Warning: Unable to cleanly disconnect from the database!\n");

		return True;

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

	# Option to control language
	cli_parser.add_argument('-l', '--lang', default=u'en',
				help="language code of the Wikipedia we're working on (default: en)");

	# Option to control the MySQL configuration file
	cli_parser.add_argument('-m', '--mysqlconf', default=None,
				help="path to MySQL configuration file");

	# Option to control number of pages per category of tasks
	cli_parser.add_argument('-n', '--numpages', default=5,
				help="number of pages displayed in each task category (default: 5)");

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
				      editComment=args.comment, testRun=args.test);
	try:
		taskUpdater.update();
	finally:
		taskUpdater.stopme();

if __name__ == "__main__":
	main();
