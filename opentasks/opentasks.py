#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
Program to update a list of open tasks for a Wikipedia.
Copyright (C) 2012-2020 SuggestBot dev group

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
import re
import yaml
import random
import logging

from collections import defaultdict

import pymysql

import pywikibot

class OpenTaskUpdater:
    def __init__(self, config_file):
        """
        Instantiate the Opentask updater.
        
        :param config_file: path to the YAML configuration file for
                             this particular instance.
        :type config_file: str
        """

        with open(config_file) as f:
            self.config = yaml.load(f, Loader=yaml.FullLoader)

        self.db_conn = None
        self.mysql_conf = '~/replica.my.cnf'

        # Query to fetch a number of random pages from a given category.
        self.random_page_query = '''SELECT /* LIMIT:120 */
                                    page_id, page_title
                                    FROM page JOIN categorylinks
                                    ON page_id = cl_from
                                    WHERE cl_to = %(cat_name)s
                                    AND page_namespace = %(ns)s
                                    AND page_random >= RAND()
                                    ORDER BY page_random LIMIT %(n_pages)s'''

        # Query to fetch all pages in a given namespace
        # from a given category
        self.all_pages_query = '''SELECT page_id, page_title
                                  FROM page JOIN categorylinks
                                  ON page_id = cl_from
                                  WHERE cl_to = %(cat_name)s
                                  AND page_namespace = %(ns)s'''

    def db_connect(self):
        '''
        Connect to the database defined by this instance's configuration.
        '''

        host_name = '{}.web.db.svc.eqiad.wmflabs'.format(self.config['db_host'])
        
        if self.db_conn:
            self.db_disconnect()

        try:
            self.db_conn = pymysql.connect(
                db=self.config['db_name'],
                host=host_name,
                read_default_file=os.path.expanduser(self.mysql_conf),
                use_unicode=False,
                charset=None)
        except pymysql.Error as e:
            logging.error("DB connection to {} on server {} failed".format(
                self.config['db_name'], host_name))
            logging.error("error {}: {}".format(e.args[0], e.args[1]))
            return(False)
        
        # Ok, done
        return(True)

    def db_disconnect(self):
        if self.db_conn is None:
            return(True) # already disconnected

        try:
            self.db_conn.close()
        except pymysql.Error as e:
            logging.error("unable to disconnect from database")
            logging.error("error {}: {}".format(e.args[0], e.args[1]))
            return(False)

        # Ok, done
        return(True)

    def find_stubs(self, category, n):
        '''
        Use the database to pick a random stub category,
        then pick a sufficient number of pages from that category.
        Expects a working database connection to exist as `self.db_conn`

        :param category: the parent stub category.
        :type category: str

        :param n: number of pages to find
        :type n: int
        '''

        logging.info("trying to find {} stub tasks...".format(n))

        stub_articles = list()
        
        exit_loop = False
        while len(stub_articles) < n and not exit_loop:
            stub_category = None
            attempts = 0
            while attempts < self.config['max_query_attempts']:
                try:
                    with self.db_conn.cursor() as db_cursor:
                        # pick one random stub category (ns = 14)
                        db_cursor.execute(
                            self.random_page_query,
                            {'cat_name': category.replace(
                                ' ', '_').encode('utf-8'),
                             'ns': 14,
                             'n_pages': 1})
                        
                        for (page_id, page_title) in db_cursor:
                            stub_category = page_title.decode(
                                'utf-8').replace('_', ' ')
                except pymysql.Error as e:
                    attempts += 1
                    logging.error("query error {}: {}".format(
                        e.args[0], e.args[1]))
                    if e.errno == pymysql.errnos['CR_SERVER_GONE_ERROR'] \
                       or e.errno == pymysql.errnos['CR_SERVER_LOST']:
                        # lost connection, reconnect
                        self.db_connect()
                else: 
                    break # out of attempt-loop

            if not stub_category:
                logging.error("unable to find random stub category")
                exit_loop = True
            else:
                stub_articles.extend(self.find_pages(stub_category, n))
                
        # truncate to the right number of pages per task category
        stub_articles = stub_articles[:n]

        logging.info("found {} stub pages".format(len(stub_articles)))

        return(stub_articles)

    def find_all_pages(self, category_name):
        """
        Use the database to fetch all Main & Talk namespace pages from
        a given category.  Expects a working database connection
        to exist as `self.db_conn`

        :param category_name: name of the category to grab pages from
        :type category_name: str
        """

        logging.info("finding all pages in category {}".format(
            category_name))

        found_pages = list()
        attempts = 0
        while attempts <  self.config['max_query_attempts']:
            try:
                with self.db_conn.cursor() as db_cursor:
                    db_cursor.execute(
                        self.all_pages_query,
                        {'cat_name': category_name.replace(
                            ' ', '_').encode('utf-8'),
                         'ns': 0})

                    for (page_id, page_title) in db_cursor:
                        found_pages.append(
                            page_title.decode('utf-8').replace('_', ' '))

            except pymysql.Error as e:
                attempts += 1
                logging.error("query error {}: {}".format(e.args[0], e.args[1]))
                if e.errno == pymysql.errnos['CR_SERVER_GONE_ERROR'] \
                        or e.errno == pymysql.errnos['CR_SERVER_LOST']:
                    # lost connection, reconnect
                    self.db_connect()
            else:
                break # break out of query attempt loop
            
        if attempts >= self.config['max_query_attempts']:
            logging.error("exhausted number of query attempts")

        logging.info("found {} pages in this category".format(
            len(found_pages)))

        return(found_pages)

    def find_subcategory_pages(self, category_name):
        """
        Use the database to retrieve all direct descendant
        sub-categories of the given category.  Then find all pages
        in all the sub-categories and return the union of all of them.

        :param category_name: name of the starting category, which we'll
                              grab all sub-categories from.
        :type category_name: str
        """

        logging.info("finding sub-category pages of category {}".format(
            category_name))

        sub_categories = list()
        attempts = 0
        while attempts < self.config['max_query_attempts']:
            try:
                with self.db_conn.cursor() as db_cursor:
                    db_cursor.execute(
                        self.all_pages_query,
                        {'cat_name': category_name.replace(
                            ' ', '_').encode('utf-8'),
                         'ns': 14} # namespace 14 is the Category namespace
                         )

                    for (page_id, page_title) in db_cursor:
                        sub_categories.append(
                            page_title.decode('utf-8').replace('_', ' '))

            except pymysql.Error as e:
                attempts += 1;
                logging.error("query error {}: {}".format(e.args[0], e.args[1]))
                if e.errno == pymysql.errnos['CR_SERVER_GONE_ERROR'] \
                   or e.errno == pymysql.errnos['CR_SERVER_LOST']:
                    # lost connection, reconnect
                    self.db_connect()
            else:
                break # break out of query attempt loop
            
        if attempts >= self.config['max_query_attempts']:
            logging.error("exhausted number of query attempts finding sub-categories")
            return(list())

        logging.info("found {} sub-categories".format(len(sub_categories)))
        
        found_pages = set()
        for category_name in sub_categories:
            subcat_pages = self.find_all_pages(category_name)
            found_pages = found_pages.union(subcat_pages)

        return(found_pages)

    def find_subsubcategory_pages(self, category_name):
        """
        Get all subcategories of the given category, then iteratively
        call `self.find_subcategory_pages` for each of them to get
        all pages two levels down.

        :param category_name: name of the starting category
        :type category_name: str
        """

        logging.info("finding all pages from sub-sub-categories of {}".format(
            category_name))

        sub_categories = list()
        attempts = 0
        while attempts <  self.config['max_query_attempts']:
            try:
                with self.db_conn.cursor() as db_cursor:
                    db_cursor.execute(
                        self.all_pages_query,
                        {'cat_name': category_name.replace(
                            ' ', '_').encode('utf-8'),
                         'ns': 14} # namespace 14 is the Category namespace
                        )

                for (page_i, page_title) in db_cursor:
                    sub_categories.append(
                        page_title.decode('utf-8').replace('_', ' '))

            except pymysql.Error as e:
                attempts += 1;
                logging.error("query error {}: {}".format(e.args[0], e.args[1]))
                if e.errno == pymysql.errnos['CR_SERVER_GONE_ERROR'] \
                   or e.errno == pymysql.errnos['CR_SERVER_LOST']:
                    # lost connection, reconnect
                    self.db_connect()
            else:
                break # break out of query attempt loop
            
        if attempts >= self.config['max_query_attempts']:
            logging.error("exhausted number of query attempts")
            return(list())

        logging.info("found {} sub-categories".format(len(sub_categories)))
        
        found_pages = set()
        for category_name in sub_categories:
            subcat_pages = self.find_subcategory_pages(category_name)
            found_pages = found_pages.union(subcat_pages)

        return(found_pages)

    def find_random_pages(self, category_name, n):
        """
        Use the database to pick a number of pages from
        a given category. Expects a working database connection
        to exist as `self.db_conn`

        :param category_name: the category we're picking pages from
        :type category_name: str

        :param n: number of pages to return
        :type n: int
        """

        logging.info("finding {n} tasks from category {cat}".format(
            n=n, cat=category_name))

        found_pages = list()
        attempts = 0
        while attempts < self.config['max_query_attempts']:
            try:
                with self.db_conn.cursor() as db_cursor:
                    db_cursor.execute(
                        self.random_page_query,
                        {'cat_name': category_name.replace(
                            ' ', '_').encode('utf-8'),
                         'ns': 0,
                         'n_pages' : n})

                    for (page_id, page_title) in db_cursor:
                        found_pages.append(
                            page_title.decode('utf-8').replace('_', ' '))
            except pymysql.Error as e:
                attempts += 1;
                logging.error("query error {}: {}".format(e.args[0], e.args[1]))
                if e.errno == pymysql.errnos['CR_SERVER_GONE_ERROR'] \
                   or e.errno == pymysql.errnos['CR_SERVER_LOST']:
                    # lost connection, reconnect
                    self.db_connect()
            else:
                break # exit query attempt loop
            
        if attempts >= self.config['max_query_attempts']:
            logging.error("exhausted number of query attempts")

        logging.info("found {} tasks".format(len(found_pages)))

        return(found_pages)

    def find_pages(self, cat_def, n):
        """
        Pick a number of pages using a given category definition through
        sub-methods that access the database. The category definition can
        be one of:

        1: A string, the name of a category to randomly pick articles from
        2: A list of strings, names of categories to randomly pick articles from.
        3: A list where the first element is "use-subs". The second element in
           the list is a category, and we'll randomly pick articles from that
           category's sub-categories.
        4: A list where the first element is "use-subsubs". The second element in
           the list is a category, and we'll randomly pick articles from that
           cateogry's sub-sub-categories.

        For items 2, 3, and 4 above, articles in the categories are combined into
        a set before articles are randomly picked.

        :param cat_def: Category-definition of where to grab pages from
        :type cat_def: str or list

        :param n: number of pages to fetch
        :type n: int
        """

        if isinstance(cat_def, str):
            return(self.find_random_pages(cat_def, n))
        else:
            # Create a set of all pages we find,
            # from which we'll randomly sample.
            found_pages = set()
            if isinstance(cat_def, list) \
               and cat_def[0] == 'use-subs':
                found_pages = self.find_subcategory_pages(cat_def[1])
            elif isinstance(cat_def, list) \
                 and cat_def[0] == 'use-subsubs':
                found_pages = self.find_subsubcategory_pages(cat_def[1])
            elif isinstance(cat_def, list):
                for cat_name in cat_def:
                    found_pages = found_pages.union(
                        self.find_all_pages(cat_name))
            elif isinstance(cat_def, tuple):
                # Category name is the second element
                found_pages = self.find_subcategory_pages(cat_def[1])

        if not found_pages:
            # Something went wrong, bummer
            return(found_pages)
        elif len(found_pages) < n:
            # not enough to sample, return everything
            return(found_pages)
        else:
            return(random.sample(found_pages, n))

    def update(self):
        '''
        Update the list of open tasks.
        '''

        # log in to the given wiki
        logging.info("logging in to {}-wiki".format(self.config['lang_code']))

        site = pywikibot.getSite(self.config['lang_code'])
        site.login()

        # Did we log in?
        if site.username() is None:
            logging.error("failed to log in correctly, aborting")
            return()

        # connect to the database
        logging.info("connecting to the database")

        if not self.db_connect():
            # shouldn't need to log anything, db_connect() does it for us
            return(False)

        # Tasks defined in the configuration:
        task_list = self.config['tasks']

        # Found articles maps task ID to a list of articles:
        found_tasks = defaultdict(list)

        if 'stub' in task_list:
            logging.info("finding stub tasks...")

            found_tasks['stub'] = self.find_stubs(
                task_list['stub'],
                self.config['pages_per_category'])

            logging.info("done finding stub tasks")

        # Now, for all the other categories...
        for (task_id, task_def) in task_list.items():
            if task_id == 'stub':
                # we handled that already...
                continue

            logging.info("finding tasks for id {} with definition {}".format(
                task_id, task_def))

            found_tasks[task_id] = self.find_pages(
                task_def, self.config['pages_per_category'])

            logging.info("find complete, found {} pages in this category".format(
                len(found_tasks[task_id])))

        # Go through the found tasks and turn the list of page titles
        # into wikitext, an unordered list (*) where each list item
        ## is a link to a given page
        
        for (task_id, pages) in found_tasks.items():
            if not pages:
                found_tasks[task_id] = "None"
            else:
                link_list = list()
                for page in pages:
                    page_obj = pywikibot.Page(site, page)
                    link_list.append('* {}'.format(
                        page_obj.title(asLink=True, insite=site)))

                found_tasks[task_id] = '\n'.join(link_list)
                    
        logging.info("turned page titles into page links")
        logging.info("getting wikitext of task page {}".format(
            self.config['opentask_page']))

        tasktext = None
        try:
            taskpage = pywikibot.Page(site, self.config['opentask_page'])
            tasktext = taskpage.get()
        except pywikibot.exceptions.NoPage:
            logging.warning("task page {} does not exist".format(
                self.config['opentask_page']))
        except pywikibot.exceptions.IsRedirectPage:
            logging.warning("task page {} is a redirect".format(
                self.config['opentask_page']))
        except pywikibot.data.api.TimeoutError:
            logging.error("TimeOutError, unable to continue")

        if tasktext is None:
            return()

        logging.info("got wikitext, substituting page lists...")

        for (task_id, page_list) in found_tasks.items():
            # note: using re.DOTALL because we need .*? to match \n
            #       since our content is a list
            tasktext = re.sub(
                r'<div\s+id="{task}"\s*>(.*?)</div>'.format(task=task_id),
                r'<div id="{task}">\n{pagelist}</div>'.format(
                    task=task_id, pagelist=page_list),
                tasktext, flags=re.DOTALL)

        if self.config['test_run']:
            logging.info("running a test, printing out new wikitext:\n")
            print(tasktext)
        else:
            logging.info("saving page with new text")
            taskpage.text = tasktext
            try:
                taskpage.save(comment=self.config['edit_comment'])
            except pywikibot.exceptions.EditConflict:
                logging.error("edit conflict saving {}, not retrying".format(
                    self.config['opentask_page']))
                return()
            except pywikibot.exceptions.PageNotSaved as e:
                logging.error("saving {} failed, unable to continue".format(
                    self.config['opentask_page']))
                logging.error("pywikibot error: {}".format(e))
                return()
            except pywikibot.data.api.TimeoutError:
                logging.error("time out error saving {}".format(
                    self.config['opentask_page']))
                return()

        logging.info("list of open tasks successfully updated")

        self.db_disconnect()
        return()

def main():
    import argparse

    cli_parser = argparse.ArgumentParser(
        description="Program to update list of open tasks for a given Wikipedia.")

    # Verbosity option
    cli_parser.add_argument('-v', '--verbose', action='store_true',
                help='if set informational output is written to stderr')

    # Configuration file has to be provided
    cli_parser.add_argument('config_file', default=None,
                help="path to YAML configuration file")
        
    args = cli_parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    task_updater = OpenTaskUpdater(args.config_file)
    task_updater.update()

if __name__ == "__main__":
    main()
