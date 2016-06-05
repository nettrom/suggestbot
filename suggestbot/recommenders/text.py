#!/usr/bin/env python
# -*- coding: utf-8  -*-
'''
Text-based recommender that uses CirrusSearch/ElasticSearch
and Borda count rank aggregation to recommend articles.

Copyright (C) 2015-2016 SuggestBot Dev Group

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

import logging
import operator
import itertools
import collections

from suggestbot import config

import pywikibot

class Recommender:
    def recommend(self, user, lang, articles, params):
        """
        Find articles matching a given set of articles for a given user.

        :param user: username of the user we are recommending articles to
        :param lang: language code of the Wikipedia we're recommending for
        :param articles: the articles the user has recently edited
        :type articles: list
        :param params: parameters for the recommendation
                       key:'nrecs', value:int => number of recs returned
        :type params: dict
        """
       
        # number of recommendations we'll return
        nrecs = 500; # default
        if 'nrecs' in params:
            nrecs = params['nrecs']

        # temporary result set
        recs = {}

        # statistics on timing
        numArticles = len(articles)

        # print got request info
        logging.info("got request for {lang}:User:{username} to find {nrecs} recommend articles based on {num} articles".format(lang=lang, username=user, nrecs=nrecs, num=numArticles))

        # initialize Pywikibot site
        site = pywikibot.Site(lang)
        site.login()

        # Can we get more results back? (Note: we don't necessarily need
        # too many, as we're looking for _similar_ articles)
        srlimit = 50
        if site.has_right('apihighlimits'):
            srlimit = 100
        
        # dict of resulting recommendations mapping titles to Borda scores
        # (as ints, defaults are 0)
        recs = collections.defaultdict(int)

        # query parameters:
        # action=query
        # list=search
        # srsearch=morelike:{title}
        # srnamespace=0 (is the default)
        # srlimit=50 (tested by trial & error, bots can get <= 500)
        # format=json

        # FIXME: start timing

        for page_title in articles:
            q = pywikibot.data.api.Request(site=site,
                                           action='query')
            q['list'] = 'search'
            # q['srbackend'] = u'CirrusSearch'
            q['srnamespace'] = 0
            # FIXME: add quotes around title and escape quotes in title?
            q['srsearch'] = 'morelike:{title}'.format(title=page_title)
            q['srlimit'] = srlimit
            reqdata = q.submit()

            if not 'query' in reqdata \
               or not 'search' in reqdata['query']:
                logging.warning('no results for query on {title}'.format(title=page_title))
            else:
                results = reqdata['query']['search']
                # calculate a Borda score for each article (len(list) - rank)
                # and throw it into the result set.
                n = len(results)
                score = itertools.count(n, step=-1)
                for article in results:
                    s = next(score)
                    recs[article['title']] += s
                
                logging.info('completed fetching recommendations for {title}'.format(title=page_title))
                logging.info('number of recommendations currently {0}'.format(len(recs)))

        # FIXME: end timing, write out if verbose

        # take out edits from results
        for page_title in articles:
            try:
                del(recs[page_title])
            except KeyError:
                pass

        # sort the results and iterate through to create
        # a list of dictionaries, which we'll then return
        result = []
        for (page_title, score) in sorted(recs.items(),
                                          key=operator.itemgetter(1),
                                          reverse=True)[:nrecs]:
            result.append({'item': page_title,
                           'value': score});

        logging.info("returning {n} recommendations.".format(n=len(result)))
        logging.info("completed getting recs")

        # OK, done, return
        return(result)
