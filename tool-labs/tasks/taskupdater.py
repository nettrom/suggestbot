#!/usr/env/python
# -*- coding: utf-8 -*-
"""
Library for updating the database with a list of articles in different
work categories (stubs, needing sources, etc).

Configuration of how a task category corresponds to a set of Wikipedia
categories is defined in a JSON file. Said file will also define
a regular expression to match (or exclude) stub categories when traversing.
"""

# $Id$

import sys
import re
import os
import time
import json

import logging
import MySQLdb

class TaskUpdater:
    def __init__(self, config):
        '''
        Initialise a new TaskUpdater object.

        :param config: Configuration built from importing the associated
                       JSON configuration file for the Wikipedia edition
                       that we will be gathering articles from.
        :type config: dict
        '''
        
        self.config = config

    def db_connect(self):
        '''
        Connect to the database. Returns True if successful.
        '''
        self.db_conn = None
        self.db_cursor = None
        try:
            self.db_conn = MySQLdb.connect(db=self.config['task_db'],
                                           host=self.config['db_server'],
                                           read_default_file=os.path.expanduser(self.config['db_config']))
            self.db_cursor = self.db_conn.cursor(MySQLdb.cursors.SSDictCursor)
        except:
            pass

        if self.db_conn:
            return(True)

        return(False)

    def db_disconnect(self):
        '''Close our database connections.'''
        try:
            self.db_cursor.close()
            self.db_conn.close()
        except:
            pass

        return()
        
    def update_database(self):
        '''
        Update the task database per the configuration set when initialising
        this updater.

        For each task category, there are five parameters:
        
        * The internally used task category name (e.g. "STUB")
        * A list of categories from which to grab articles.
        * A dictionary where the keys are categories and the values are
          integers defining how many sub-levels down we can recurse.
        * A regular expression that has to be matched for a category to
          be _included_ when recursing into subcategories.
        * A regular expression that has to be matched for a category to
          be _excluded_ when recursing into subcategories.

        The internal task category name is a key in the dictionary of tasks,
        and its associated value is another dictionary where each of the
        other four parameters have an associated key ("categories",
        "recurseCategories", "inclusion", and "exclusion", respectively).
        '''

        update_seen_query = """UPDATE {task_table}
                               SET seen=0
                               WHERE lang=%(lang)s
                               AND category=%(category)s""".format(task_table=self.config['task_table'])

        delete_query = """DELETE FROM {task_table}
                          WHERE lang=%(lang)s
                          AND category=%(category)s
                          AND seen=0""".format(task_table=self.config['task_table'])

        insert_query = """INSERT INTO {task_table}
                          (lang, page_id, category)
                          VALUES (%(lang)s, %(page_id)s, %(category)s)
                          ON DUPLICATE KEY UPDATE seen=1""".format(task_table=self.config['task_table'])
        
        if not self.db_connect():
            logging.error('Unable to connect to task database server {}'.format(self.config['db_server']))
            return()

        for (task_name, task_conf) in self.config['tasks'].items():
            self.db_cursor.execute(update_seen_query,
                                   {'lang': self.config['lang'],
                                    'category': task_name})
            self.db_conn.commit()
            logging.info('number of rows with updated "seen" values: {}'.format(self.db_cursor.rowcount))

            ##    for each category
            ##       grab articles
            ##    for each category to recurse
            ##       grab articles and recurse

            self.db_cursor.execute(delete_query,
                                   {'lang': self.config['lang'],
                                    'category': task_name})
            self.db_conn.commit()
            logging.info('deleted {} articles that are no longer in task category {}'.format(self.db_cursor.rowcount, task_name))

        self.db_disconnect()
        return()
        
class WorkUpdater:
    def __init__(self, lang=None, configFile=None, config=None,
                 taskCatDef=None, verbose=False):
        '''
        Initialize a new WorkUpdater object.

        @param lang: language code of the Wikipedia we're updating data for
        @type lang: unicode
        
        @param configFile: Filename of alternate configfile to use.
        @type configFile: str

        @param config: Existing SuggestBotConfig that we'd like to re-use
        @type config: SuggetBotConfig object

        @param taskCatDef: dictionary of tasks and their associated Wikipedia
                           categories to fetch articles from and traverse,
                           and regular expressions for inclusion and exclusion.
        @type taskCatDef: dict

        @param verbose: Are we going to print config messages?
        @type verbose: bool
        '''
        if config:
            self.config = config;
        else:
            self.config = SuggestBotConfig(configFile=configFile);

        self.lang = self.config.getConfig('WP_LANGCODE');
        if lang:
            self.lang = lang;

        # What site are we working on again?
        self.site = pywikibot.Site(self.lang);
        self.site.login();

        self.seen_categories = set();
        self.seen_titles = set();

        self.taskCatDef = taskCatDef;
        if not taskCatDef:
            self.taskCatDef = self.config.getConfig('TASKS')[self.lang];

        self.verbose = verbose;

        # RegEx used for proper quoting of single quotes in SQL queries,
        # and escaping '\' (because there _is_ an article named 'Control-\');
	self.quote_re = re.compile(r"[']");
        self.backslash_re = re.compile(r"\\");

        self.db = SuggestBotDatabase(config=self.config);
        self.dbConn = None;
        self.dbCursor = None;

    def updateCategoryDatabase(self):
        """
        Update the whole database per our configuration.
        """

        if not self.db.connect():
            sys.stderr.write(u"Error: cannot connect to SuggestBot database, exiting!\n");
            return False;

        (self.dbConn, self.dbCursor) = self.db.getConnection();

        # Update the categories
        for category in self.taskCatDef.keys():
            self.updateCategory(categoryName=category,
                                cats=self.taskCatDef[category]['categories'],
                                recurseCats=self.taskCatDef[category]['recurseCategories'],
                                inclusionRegex=self.taskCatDef[category]['inclusion'],
                                exclusionRegex=self.taskCatDef[category]['exclusion']);

        # OK, done, disconnect and return...
        self.db.disconnect();
        return True;

    def updateCategory(self, categoryName="", cats=[], recurseCats={},
                       inclusionRegex="", exclusionRegex=""):
        '''
        Update the articles in the database for a specific category.

        @param categoryName: Our internal category name, e.g. "STUB"
        @type categoryName: str

        @param cats: List of Wikipedia categories that we'll only grab articles from.
        @type cats: list (of unicode)

        @param recurseCats: Wikipedia categories that we'll grab any articles from
                            and also recursively look through subcategories for
                            additional articles.  Keys in the dict are the category
                            names, values are the number of sub-levels to inspect.
        @type recurseCats: dict (unicode:int)

        @param inclusionRegex: Regular expression used to test for inclusion.
                               Categories that _do not_ match this regex are
                               ignored.
        @type inclusionRegex: str

        @param exclusionRegex: Regular expression used to test for exclusion.
                               Categories that _match_ this regex are ignored.
        @type exclusionRegex: str

        Note that the 'cats' and 'recurseCats' parameters can be interchanged,
        defining a category in 'recurseCats' with level set to 0 is equivalent
        to having the category listed in 'cats'.  Do observe though, that if
        the category is found earlier in the search it will be ignored upon
        any later occurrences.

        Upon entry into this method, the 'seen' column of all existing articles
        in 'categoryName' is set to 0.  After having completed inserting and
        updating article titles, all remaining articles in 'categoryName' that
        have the 'seen' column set to 0 are deleted.
        '''

        if not categoryName:
            return;
        if not cats and not recurseCats:
            return;

        self.categoryName = categoryName;
        self.catTableName = self.config.getConfig('TASK_TABLE')[self.lang];

        # Query to reset the seen column for all articles in 'categoryname'
        resetQuery = ur"""UPDATE {tablename}
                          SET seen=0
                          WHERE category=%(catname)s""".format(tablename=self.catTableName);

        # Query to delete all rows in 'categoryname' that have seen=0,
        # to be run after a successful update to clean out articles that are
        # no longer members of our category.
        deleteQuery = ur"""DELETE FROM {tablename}
                           WHERE category=%(catname)s
                           AND seen=0""".format(tablename=self.catTableName);

        # Query to check if an article already exists in the database
        self.pageExistsQuery = ur"""SELECT title
                                    FROM {tablename}
                                    WHERE category=%(catname)s AND title=%(title)s""".format(tablename=self.catTableName);

        # Query to insert a new article
        self.insertQuery = ur"""INSERT INTO {tablename}
                                (title, category)
                                VALUES (%(title)s, %(catname)s)""".format(tablename=self.catTableName);

        # Query to update the seen-bit for a given article
        self.updateQuery = ur"""UPDATE {tablename}
                                SET seen=1
                                WHERE title=%(title)s AND category=%(catname)s""".format(tablename=self.catTableName);

        # reset all seen-values for articles in 'categoryname'
        self.dbCursor.execute(resetQuery, {'catname': self.categoryName.encode('utf-8')});
        self.dbConn.commit();
        if self.verbose:
            print "INFO: number of rows with updated seen-values: %d" % (self.dbCursor.rowcount,);

        self.storageQueue = set();

        # traverse the categories and store data
        self.traverseCategories(titleCategories=cats, recurseCategories=recurseCats,
                                inclusionRegex=inclusionRegex,
                                exclusionRegex=exclusionRegex);

        # flush any remaining articles from the queue
        self.flushQueue();

        # Delete all articles in 'categoryname' with seen=0
        # Note: this doesn't delete any newly added articles because they're inserted
        #       with the 'seen' column unspecified, and it defaults to 1.
        self.dbCursor.execute(deleteQuery, {'catname': self.categoryName.encode('utf-8')});
        self.dbConn.commit();
        if self.verbose:
            print u"INFO: deleted {n} articles that are no longer in category {catname}".format(n=self.dbCursor.rowcount, catname=self.categoryName).encode('utf-8');

        return True;

    def store(self, article):
        '''
        Add this article to the pending storage queue.  If the queue is
        full, commit to the database.

        @param article: The article to store
        @type article: pywikibot.Page
        '''

        self.storageQueue.add(article.title());

        if len(self.storageQueue) == 250:
            if self.verbose:
                print "INFO: Storage queue is full, flushing...";
            self.flushQueue();

    def flushQueue(self):
        '''
        Update/insert any articles found in self.storageQueue in the database.
        Articles are assumed to belong to the internal category self.categoryName.

        Note that any article that is inserted has the 'seen' column set to 1,
        as that is the default value.  Articles that are updated get the 'seen'
        column value set to 1.

        Expects the necessary SQL queries to already exist as self.pageExistsQuery,
        self.insertQuery, and self.updateQuery.
        '''

        try:
            knownArticles = set();
            articlesToUpdate = list();

            for title in self.storageQueue:
                self.dbCursor.execute(self.pageExistsQuery, {'title': title,
                                                             'catname': self.categoryName});
                for row in self.dbCursor.fetchall():
                    title = row['title']
                    if not isinstance(title, unicode):
                        title = unicode(title, 'utf-8')
                    knownArticles.add(title);
                    articlesToUpdate.append({'title' : title,
                                             'catname': self.categoryName});

            # update the seen attribute for those
            if len(articlesToUpdate) > 0:
                if self.verbose:
                    print "INFO: Updating the seen attribute for %d existing articles." % (len(articlesToUpdate),);

                self.dbCursor.executemany(self.updateQuery, articlesToUpdate);

            # Add the titles for those not already known.
            # Notice that we use a set minus operation to get these.
            articlesToInsert = list();
            for articleTitle in self.storageQueue.difference(knownArticles):
                articlesToInsert.append({'title': articleTitle,
                                         'catname': self.categoryName});

            if len(articlesToInsert) > 0:
                if self.verbose:
                    print "INFO: Inserting %d articles into the database." % (len(articlesToInsert),);

                self.dbCursor.executemany(self.insertQuery, articlesToInsert);

            # commit the transaction
            self.dbConn.commit();
            # clear the queue
            self.storageQueue.clear();
            return True;
        except MySQLdb.Error, e:
            sys.stderr.write("SBot Error: Unable to store/update articles in database.\n");
            sys.stderr.write("Error %d: %s\n" % (e.args[0], e.args[1]));
            sys.exit(1);
            
        return False;

    def login(self):
        '''
        Log our bot in on the Wikipedia specified in config/config.pm
        '''
        self.site = pywikibot.Site(self.config.getConfig('WP_LANGCODE'));
        self.site.login();
        return self.isLoggedIn();

    def logout(self):
        '''Logs the bot out, if we're logged in. Currently unimplemented.'''
        # if self.site.user():
        return True;

    def isLoggedIn(self):
        '''Returns our username if we're logged in, None otherwise.'''
        return self.site.user();

    # NOTE: we _can_ replace this with a toolserver system, because the current
    # traversal strategy uses the API.  Except that on the Toolserver, we'll have
    # to traverse the category tree to figure out which categories to search through
    # when we attempt to decide if a recommendation is in category X.
    def catTraverser(self, category=None, limit=1,
                     inclusion_re=None, exclusion_re=None):
        '''
        Traverse the Wikipedia category tree.  Usually not called directly,
        see 'traverseCategories()' or 'updateCategoryDatabase()' instead.

        @param category: What category to start traversal on.  Any articles found
                         in this category that are not already known, will be stored,
                         and any subcategories will be descended if 'limit' is > 0.
        @type category: pywikibot.Category

        @param limit: How many sub-levels to descend.
        @type limit: int

        @param inclusion_re: Regular expression to use for testing category names
                             for inclusion.  Categories _not_ matching this regex
                             get skipped.
        @type inclusion_re: RegEx

        @param exclusion_re: Regular expression to use for testing category names
                             for exclusion.  Categories _matching_ this regex
                             get skipped.
        @type exclusion_re: RegEx

        '''
        
        try:
            if self.verbose:
                print "INFO: Storing article titles in category '%s'." % (category.title().encode('utf-8'));
            for article in category.articles(namespaces=[0]):
                # We define redirects as seen articles, but do not store them as
                # articles that need work.  NOTE: consider following the redirect...
                if article.title() not in self.seen_titles \
                        and not article.isRedirectPage():
                    self.store(article);
                    self.seen_titles.add(article.title());
        except pywikibot.exceptions.Error:
            # Due to problems with Wiki families not being defined and such,
            # pywikibot might throw an error.  We then simply pass on this category
            # and continue.

            if self.verbose:
                print "INFO: Caught pywikibot exception, passing over.";
            pass;

        try:
            if limit > 0:
                for subcat in category.subcategories():
                    # skip already seen categories...
                    if subcat.title() in self.seen_categories:
                        continue;

                    if inclusion_re and not inclusion_re.search(subcat.title()):
                        if self.verbose:
                            print "INFO: category '%s' failed inclusion check." % (subcat.title().encode('utf-8'),);
                        continue;

                    if exclusion_re and exclusion_re.search(subcat.title()):
                        if self.verbose:
                            print "INFO: category '%s' matched exclusion check." % (subcat.title().encode('utf-8'),);
                        continue;

                    if self.verbose:
                        print "INFO: now traversing category '%s' to level %d." % (subcat.title().encode('utf-8'), limit-1,);

                    self.seen_categories.add(subcat.title());
                    self.catTraverser(category=subcat, limit=limit-1,
                                      inclusion_re=inclusion_re,
                                      exclusion_re=exclusion_re);
        except pywikibot.exceptions.Error:
            # Again we catch the error...
            if self.verbose:
                print "INFO: caught pywikibot error, passing over.";
            pass;

        return;

    def traverseCategories(self, titleCategories=[],
                           recurseCategories={},
                           inclusionRegex="", exclusionRegex=""):
        '''
        Update articles on disk for a specific category.

        @param titleCategories: Name of categories for which to only gather
                                article titles
        @type titleCategories: list

        @param recurseCategories: Categories for which to traverse subcategories
                                  and store titles.  Keys in the dictionary are
                                  the names of the categories, values are the number
                                  of sublevels to descend.
        @type recurseCategories: dict (str:int)

        @param inclusionRegex: Regular expression to be used for a re.search() call
                               on category titles during subcategory traversal.
                               Only categories matching this regex will be included.
        @type inclusionRegex: string

        @param exclusionRegex: Regular expression to be used for a re.search() call
                               on category titles during subcategory traversal.
                               Categories matching this regex will be excluded from
                               traversal (and gathering of article titles).
        @type exclusionRegex: string
        '''

        include_re = None;
        exclude_re = None;
        if inclusionRegex:
            include_re = re.compile(inclusionRegex);
        if exclusionRegex:
            exclude_re = re.compile(exclusionRegex);

        self.seen_categories = set();
        self.seen_titles = set();

        # check if any recurseCategories are defined with level = 0,
        # if so, remove it and add it to titleCategories instead
        for catname in recurseCategories.keys():
            if recurseCategories[catname] == 0:
                del(recurseCategories[catname]);
                titleCategories.append(catname);

        # store the article titles for these categories
        for catname in titleCategories:
            cat = pywikibot.Category(self.site,
                                     self.site.category_namespace() + ":" + catname);
            self.seen_categories.add(cat.title());
                
            if self.verbose:
                print u"INFO: storing titles in {catname}".format(catname=cat.title()).encode('utf-8');
            try:
                for article in cat.articles(namespaces=[0]):
                    # We define redirects as seen articles, but do not store them as
                    # articles that need work.  NOTE: consider following the redirect...
                    if article.title() not in self.seen_titles \
                            and not article.isRedirectPage():
                        self.store(article);
                        self.seen_titles.add(article.title());
            except pywikibot.exceptions.Error:
                # Due to problems with Wiki families not being defined and such,
                # pywikibot might throw an error.  We then simply continue.
                pass;

        # traverse these categories...
        for catname in recurseCategories.keys():
            # if catname is already seen (because it could be found
            # through links form other categories), simply skip to next.
            # NOTE: possible problem is that this category contains sub-categories
            # that we might not have traversed due to the level limitation.
            # Discuss whether that's worth worrying about...
            cat = pywikibot.Category(self.site,
                                     self.site.category_namespace() + ":" + catname);
            if cat.title() in self.seen_categories:
                continue;

            self.seen_categories.add(cat.title());
            self.catTraverser(category=cat, limit=recurseCategories[catname],
                              inclusion_re=include_re,
                              exclusion_re=exclude_re);

        return;

    def downloadCategory(self, filename, titles, recurse_titles = []):
        '''
        This method is deprecated: Use self.traverseCategories() instead.

        Grabs articles and categories from the Wikipedia instance defined in
        self.site.  Article titles and category names are intermittently stored
        in local variables so that article titles are only stored once, and no
        categories are traversed more than once.

        @param filename: Name of the file to store article titles in
        @type filename: str

        @param titles: Wikipedia categories to only grab article titles from
        @type titles: list

        @param recurse_titles: Wikipedia categories to recursively traverse.
                               Any article titles found are stored, and sub-categories
                               down to five sub-levels are checked.
        @type recurse_titles: list 
        '''

        with codecs.open(filename, 'w', 'utf-8') as outfile:
            # Smarter to use set()s than dictionaries for this.
            wanted_categories = set(); # Goal: prevent infinite loops
            full_list = set(); # Goal: eliminate duplicates
            # I think this tracking caused running out of memory
            # on large tasks such as stub downloading... we may have
            # to just eat it, write duplicates, and post-process

            # Manually skip broken categories
            wanted_categories.add('African academic biography stubs');
    
            for catname in titles:
                if catname in wanted_categories:
                    continue;

                wanted_categories.add(catname);
                cat = pywikibot.Category(self.site,
                                         self.site.category_namespace() + ":" + catname);
                for page in cat.articles(namespaces=[0]):
                    # NOTE: we only store article titles in Main namespace.
                    try:
                        if page.title() not in full_list:
                            outfile.write("%s\n" % (page.title(),));
                            full_list.add(page.title());
                    except pywikibot.exceptions.Error:
                        # The namespace() call might error out due to
                        # links to other Wikipedias and stuff.  We catch
                        # the error and simply skip the link.
                        continue;
        
            for catname in recurse_titles:
                if catname in wanted_categories:
                    continue;

                wanted_categories.add(catname);
                cat = pywikibot.Category(self.site,
                                         self.site.category_namespace() + ":" + catname);

                try:
                    for page in cat.articles(namespaces=[0]):
                        if page.title() not in full_list:
                            outfile.write("%s\n" % (page.title(),));
                            full_list.add(page.title());
                except pywikibot.exceptions.Error:
                    # If there's an error in the article list, we simply
                    # catch that error and go on.
                    pass;

                for subcat in cat.subcategories(recurse=4):
                    if subcat.title() in wanted_categories:
                        continue;

                    wanted_categories.add(subcat.title());

                    try:
                        for page in subcat.articles(namespaces=[0]):
                            if page.title() not in full_list:
                                outfile.write("%s\n" % (page.title(),));
                                full_list.add(page.title());
                    except pywikibot.exceptions.Error:
                        # Same as before...
                        pass;

    def downloadTasks(self, taskList=None):
        '''
        This method is deprecated.  Use self.traverseCategories() instead.

        Download article titles and traverse sub-categories as defined by the
        specificed taskList argument.

        @param taskList: A list where the first entry is a string with the
                         internal category name we use (e.g. "STUB"), the second
                         entry is a list of categories to look for articles in,
                         and the third entry is a list of categories to both
                         store articles from and traverse down to 5 sub-levels.
        @type taskList: list
        '''
        if not taskList:
            sys.stderr.write("SBot Error: Cannot download tasks without a task list.\n");
            return False;

        for task in taskList:
            self.downloadCategory(self.config.getConfig('DOWNLOAD_DIR') + "/" + task[0],
                                  task[1], task[2]);
        return True;

    def testTraverser(self, filename="", cats=[], recurseCats={},
                      inclusionRegex="", exclusionRegex=""):
        '''
        Test method for the file storage based category traverser.  Arguments
        are much the same as for 'self.traverseCategories()', the only exception
        is that we pre-pend $DOWNLOAD_DIR to the filename to get a suitable
        filename for storage (usualy data/work-needed/newest).

        '''
        if not filename:
            return;
        if not cats and not recurseCats:
            return;

        self.traverseCategories(os.path.join(self.config.getConfig('DOWNLOAD_DIR'),
                                             filename),
                                titleCategories=cats,
                                recurseCategories=recurseCats,
                                inclusionRegex=inclusionRegex,
                                exclusionRegex=exclusionRegex);
        
    def stopme(self):
        '''
        Stop the bot.  Simply a call to pywikibot.stopme(), and usually
        used in the finally section of a try/finally clause.
        '''
        pywikibot.stopme();

def main():
    import argparse

    cli_parser = argparse.ArgumentParser(
        description="Program to update SuggestBot's task database"
    )

    # Verbosity option
    cli_parser.add_argument('-v', '--verbose', action='store_true',
                            help='write informational output')

    cli_parser.add_argument("config_file",
                            help="path to the JSON configuration file")
    
    args = cli_parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    
                try:
                        with codecs.open(args.taskfile, 'r', 'utf-8') as infile:
                                args.taskdef = json.load(infile)
                except IOError:
                        logging.error('Unable to open task definition file {0}, cannot continue'.format(args.taskfile))
                        return()
                except:
                        logging.error('Unable to parse task definition file {0} as JSON, cannot continue'.format(args.taskfile))
                        return()
        
    ## parse the config file
    ## instantiate the updater
    ## update the database
    ## ok, done!
    return()

if __name__ == "__main__":
    main()
    
