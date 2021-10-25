#!/usr/env/python
# -*- coding: utf-8 -*-
"""
Library for updating our list of articles in different work categories
(stubs, needing sources, etc).  Configuration of the task categories
are found in suggestbot/config.py

Copyright (C) 2017 SuggestBot Dev Group

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

import re
import os
import logging

from suggestbot import config
import suggestbot.db as db

import pywikibot
import MySQLdb

class TaskUpdater:
    def __init__(self, lang, task_def=None):
        '''
        Initialize an extractor.

        :param lang: Language code of the Wikipedia we're updating data for
        :type lang: str

        :param task_def: Dictionary of tasks and their associated categories
                         to fetch articles from and traverse, as well as
                         regular expressions for inclusion and exclusion.
        :type task_def: dict
        '''

        self.lang = config.wp_langcode
        if lang:
            self.lang = lang

        self.seen_categories = set()
        self.seen_titles = set()

        if not task_def:
            self.task_def = config.tasks[self.lang]
        else:
            self.task_def = task_def

        self.site = pywikibot.Site(self.lang)
            
        # RegEx used for proper quoting of single quotes in SQL queries,
        # and escaping '\' (because there _is_ an article named 'Control-\');
        self.quote_re = re.compile(r"[']")
        self.backslash_re = re.compile(r"\\")

        self.db = db.SuggestBotDatabase()
        self.db_conn = None
        self.db_cursor = None

        self.queue_size = 1000

    def update_database(self):
        """
        Update the whole task database for a given language per the
        configuration for that language.
        """

        if not self.db.connect():
            logging.error("cannot connect to SuggestBot database, exiting")
            return(False)

        (self.db_conn, self.db_cursor) = self.db.getConnection()

        # Update the categories
        for (task_cat, task_config) in self.task_def.items():
            self.update_category(task_cat,
                                 task_config['categories'],
                                 task_config['recurseCategories'],
                                 task_config['inclusion'],
                                 task_config['exclusion'])

        # OK, done, disconnect and return...
        self.db.disconnect()
        return(True)

    def update_category(self, task_name, cats, recurse_cats,
                        inc_regex, excl_regex):
        '''
        Update the articles in the database for a specific category.

        :param task_name: Our internal category name, e.g. "STUB"
        :type task_name: str

        :param cats: names of categories that we'll only grab articles from.
        :type cats: list

        :param recurse_cats: name of categories that we'll grab any articles
                             from and also recursively look through
                             subcategories for additional articles.  Keys in
                             the dict are the category names, values are
                             the number of levels down we can recurse
        :type recurse_cats: dict

        :param inc_regex: Regular expression used to test for inclusion.
                          Categories that _do not_ match this regex are ignored.
        :type inc_regex: str

        :param excl_regex: Regular expression used to test for exclusion.
                           Categories that _match_ this regex are ignored.
        :type excl_regex: str

        Note that the 'cats' and 'recurse_cats' parameters can be interchanged,
        defining a category in 'recurse_cats' with level set to 0 is equivalent
        to having the category listed in 'cats'.  Do observe though, that if
        the category is found earlier in the search it will be ignored upon
        any later occurrences.

        Upon entry into this method, the 'seen' column of all existing articles
        in `task_cat` is set to 0.  After having completed inserting and
        updating article titles, all remaining articles in `task_cat` that
        have the 'seen' column set to 0 are deleted.
        '''

        self.task_name = task_name
        self.task_table = config.task_table[self.lang]

        ## Query to reset the seen column for all articles in a specific
        ## task category in the task table
        reset_query = """UPDATE {table}
                         SET seen=0
                         WHERE category=%(catname)s""".format(
                             table=self.task_table)

        # Query to delete all rows in a task category that have seen=0,
        # to be run after a successful update to clean out articles that are
        # no longer members of our category.
        delete_query = r"""DELETE FROM {table}
                           WHERE category=%(catname)s
                           AND seen=0""".format(table=self.task_table)

        ## Query to insert/update a new article. This uses the MySQL/MariaDB
        ## "ON DUPLICATE KEY" to update seen if the article exists.
        self.insert_query = """INSERT INTO {table}
                               (title, category)
                               VALUES (%(title)s, %(catname)s)
                               ON DUPLICATE KEY UPDATE seen=1""".format(
                                   table=self.task_table)
        
        # reset all seen-values for articles in the task category
        with db.cursor(self.db_conn) as db_cursor:
            db_cursor.execute(reset_query,
                              {'catname': task_name.encode('utf-8')})
            logging.info("num rows w/updated seen-values: {}".format(
                db_cursor.rowcount))
            self.db_conn.commit()

        self.art_queue = set()

        # traverse the categories and store data
        self.grab_articles(cats, recurse_cats, inc_regex, excl_regex)

        # flush any remaining articles from the queue
        self.flush()

        # Delete all articles in 'categoryname' with seen=0
        # Note: this doesn't delete any newly added articles because they're
        # inserted with the 'seen' column unspecified, and it defaults to 1.
        with db.cursor(self.db_conn) as db_cursor:
            db_cursor.execute(delete_query,
                              {'catname': task_name.encode('utf-8')})
            logging.info("deleted {n} articles no longer in {catname}".format(
                n=db_cursor.rowcount, catname=task_name))
            self.db_conn.commit()

        return()

    def store(self, article):
        '''
        Add this article to the queue.  If the queue is full, flush it.

        :param article: The article to store.
        :type article: `pywikibot.Page`
        '''

        self.art_queue.add(article.title())

        if len(self.art_queue) == self.queue_size:
            logging.info("storage queue is full, flushing...")
            self.flush()

        return()

    def flush(self):
        '''
        Update/insert any articles found in `self.art_queue` in the database.
        Articles are assumed to belong to the task category `self.task_name`.

        Note that any article that is inserted has the 'seen' column set to 1,
        as that is the default value.  Articles that are updated get the 'seen'
        column value set to 1.

        Assumes that the SQL query to insert/update articles is found in the
        `insert_queue` property.
        '''

        try:
            with db.cursor(self.db_conn) as db_cursor:
                articles = [{'title': t.encode('utf-8'),
                             'catname': self.task_name.encode('utf-8')}
                            for t in self.art_queue]
                
                db_cursor.executemany(self.insert_query, articles)
                self.db_conn.commit()
                # clear the queue
                self.art_queue.clear()
        except MySQLdb.Error as e:
            logging.error("unable to insert/update articles in task database")
            logging.error("MySQL error {}: {}".format(e.args[0], e.args[1]))
            
        return()

    def traverse_cat(self, category, inclusion_re, exclusion_re, limit=1):
        '''
        Traverse the Wikipedia category tree starting from the given category,
        descending max `limit` levels. If `inclusion_re` or 'exclusion_re` are
        not none, they define regular expression for inclusion or exclusion of
        categories based on title.

        :param category: What category to start traversal on.  Any articles found
                         in this category that are not already known, will be
                         stored, and any subcategories will be descended if
                         `limit` is greater than 0.
        :type category: `pywikibot.Category`

        :param inclusion_re: Regular expression to use for testing category names
                             for inclusion.  Categories _not_ matching this regex
                             get skipped. If `None`, no check is performed.
        :type inclusion_re: str

        :param exclusion_re: Regular expression to use for testing category names
                             for exclusion.  Categories _matching_ this regex
                             get skipped. If `None`, no check is performed.
        :type exclusion_re: str

        :param limit: How many sub-levels to descend.
        :type limit: int
        '''
        
        try:
            logging.info("storing articles from {}".format(category.title()))
            for article in category.articles(namespaces=[0]):
                # We define redirects as seen articles, but do not store them as
                # articles that need work. NOTE: consider following the redirect.
                if article.title() not in self.seen_titles \
                        and not article.isRedirectPage():
                    self.store(article)
                    self.seen_titles.add(article.title())
        except pywikibot.exceptions.Error:
            # Due to problems with Wiki families not being defined and such,
            # pywikibot might throw an error. We then label this category as
            # seen and continue
            self.seen_categories.add(category.title())
            logging.info("caught pywikibot exception, adding to seen and ignoring")

        try:
            if limit > 0:
                for subcat in category.subcategories():
                    # skip already seen categories...
                    if subcat.title() in self.seen_categories:
                        continue

                    if inclusion_re and \
                       not re.search(inclusion_re, subcat.title()):
                        logging.info("category {} failed inclusion check".format(subcat.title()))
                        continue

                    if exclusion_re and \
                       re.search(exclusion_re, subcat.title()):
                        logging.info("category {} matched exclusion check",format(subcat.title()))
                        continue

                    logging.info("now traversing category {} to level {}".format(subcat.title(), limit-1))

                    self.seen_categories.add(subcat.title())
                    self.traverse_cat(subcat, inclusion_re, exclusion_re,
                                      limit=limit-1)
        except pywikibot.exceptions.Error:
            # Again we catch the error...
            self.seen_categories.add(category.title())
            logging.info("caught pywikibot exception, adding to seen and ignoring")

        return()

    def grab_articles(self, cats, recurse_cats, inc_regex, excl_regex):
        '''
        Update articles on disk for a specific category.

        :param cats: Name of categories for which to only gather article titles
        :type cats: list

        :param recurse_cats: Categories for which to traverse subcategories
                             and store titles.  Keys in the dictionary are
                             the names of the categories, values are the number
                             of sublevels to descend.
        :type recurse_cats: dict

        :param inc_regex: Regular expression to be used for a re.search() call
                          on category titles during subcategory traversal.
                          Only categories matching this regex will be included.
        :type inc_regex: str

        :param excl_regex: Regular expression to be used for a re.search() call
                           on category titles during subcategory traversal.
                           Categories matching this regex will be excluded from
                           traversal (and gathering of article titles).
        :type excl_regex: str
        '''

        self.seen_categories = set()
        self.seen_titles = set()

        # check if any categories in `recurse_cats` are defined with level 0,
        # if so, remove them and add them to titleCategories instead
        for catname in recurse_cats.keys():
            if recurse_cats[catname] == 0:
                del(recurse_cats[catname])
                cats.append(catname)

        # store the article titles for these categories
        for cat_name in cats:
            cat = pywikibot.Category(
                self.site,
                '{}:{}'.format(
                    self.site.namespaces.CATEGORY.custom_name, cat_name))
            self.seen_categories.add(cat.title())
                
            logging.info("storing titles in {}".format(cat_name))

            try:
                for article in cat.articles(namespaces=[0]):
                    # We define redirects as seen articles, but do not store
                    # them as articles that need work.
                    # NOTE: consider following the redirect...
                    if article.title() not in self.seen_titles \
                            and not article.isRedirectPage():
                        self.store(article)
                        self.seen_titles.add(article.title())
            except pywikibot.exceptions.Error:
                # Due to problems with Wiki families not being defined and such,
                # pywikibot might throw an error.  We then simply continue.
                pass

        # traverse these categories...
        for (cat_name, limit) in recurse_cats.items():
            # if catname is already seen (because it could be found
            # through links from other categories), simply skip to next.
            # NOTE: possible problem is that this category contains
            # sub-categories that we might not have traversed due to the level
            # limitation.
            cat = pywikibot.Category(
                self.site,
                '{}:{}'.format(
                    self.site.namespaces.CATEGORY.custom_name, cat_name))
            if cat.title() in self.seen_categories:
                continue

            self.seen_categories.add(cat.title())
            self.traverse_cat(cat, inc_regex, excl_regex, limit=limit)

        return()
