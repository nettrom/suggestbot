#!/usr/bin/env python
# -*- coding: utf-8  -*-
'''
Wikipedia page object with properties reflecting an article's
current assessment rating, it's predicted assessment rating,
and the average number of views over the past 14 days.  The
assessment rating is calculated per Warncke-Wang et al. (CSCW
2015) from the article's talk page assessments.  Predicted rating
is calculated by the Objective Revision Evaluation Service.  Page
views are grabbed from the Wikimedia Pageview API.

Copyright (C) 2005-2016 SuggestBot Dev Group

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

## Purpose of this module:
## Extend the Pywikibot page object with information on:
## 1: the page's assessment rating
## 2: predicted assessment rating by ORES
## 3: page views for the past 14 days as well as average views/day
##    over the same time period
## 4: specific suggestions for article improvement

import logging

import requests

import mwparserfromhell as mwp

import pywikibot
from pywikibot.pagegenerators import PreloadingGenerator
from pywikibot.tools import itergroup
from pywikibot.data import api

from math import log
from time import sleep
from datetime import date, timedelta
from urllib.parse import quote

from collections import namedtuple
from mwtypes import Timestamp
from wikiclass.extractors import enwiki

from scipy import stats

from suggestbot import config
import suggestbot.utilities.qualmetrics as qm

class InvalidRating(Exception):
    '''The given rating is not one we support.'''
    pass

class Page(pywikibot.Page):
    def __init__(self, site, title, *args, **kwargs):
        super(Page, self).__init__(site, title, *args, **kwargs)

        self._avg_views = None # avg views per last 14 days
        self._rating = None # current assessment rating
        self._prediction = None # predicted rating by ORES

        self._wp10_scale = {r: i for i, r
                            in enumerate(config.wp_ratings[site.lang])}
        self._qualdata = {}
        self._qualtasks = {}

        self._headers =  {
            'User-Agent': config.http_user_agent,
            'From': config.http_from
        }

    def set_views(self, views):
        '''
        Set the number of average views.

        :param views: Number of average views.
        :type views: float
        '''
        self._avg_views = views

    def _get_views_from_api(self, http_session=None):
        '''
        Make a request to the Wikipedia pageview API to retrieve page views
        for the past 14 days and calculate and set `_avg_views` accordingly.

        :param http_session: Session to use for HTTP requests
        :type http_session: requests.session
        '''
        # make a URL request to config.pageview_url with the following
        # information appendend:
        # languageCode + '.wikipedia/all-access/all-agents/' + uriEncodedArticle + '/daily/' +
        # startDate.format(config.timestampFormat) + '/' + endDate.format(config.timestampFormat)
        # Note that we're currently not filtering out spider and bot access,
        # we might consider doing that.

        # Note: Per the below URL, daily pageviews might be late, therefore
        # we operate on a 2-week basis starting a couple of days back. We have
        # no guarantee that the API has two weeks of data, though.
        # https://wikitech.wikimedia.org/wiki/Analytics/PageviewAPI#Updates_and_backfilling

        if not http_session:
            http_session = requests.Session()
        
        today = date.today()
        start_date = today - timedelta(days=15)
        end_date = today - timedelta(days=2)

        # test url for Barack Obama
        # 'https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/Barack%20Obama/daily/20160318/20160331'
        
        url = '{api_url}{lang}.wikipedia/all-access/all-agents/{title}/daily/{startdate}/{enddate}'.format(api_url=config.pageview_url, lang=self.site.lang, title=quote(self.title(), safe=''), startdate=start_date.strftime('%Y%m%d'), enddate=end_date.strftime('%Y%m%d'))

        view_list = []
        num_attempts = 0
        while not view_list and num_attempts < config.max_url_attempts:
            r = http_session.get(url, headers=self._headers)
            num_attempts += 1
            if r.status_code == 200:
                try:
                    response = r.json()
                    view_list = response['items']
                except ValueError:
                    logging.warning('Unable to decode pageview API as JSON')
                    continue # try again
                except KeyError:
                    logging.warning("Key 'items' not found in pageview API response")
            else:
                logging.warning('Pageview API did not return HTTP status 200')

        if view_list:
            # The views should be in chronological order starting with
            # the oldest date requested. Iterate and sum.
            total_views = 0
            days = 0
            for item in view_list:
                try:
                    total_views += item['views']
                    days += 1
                except KeyError:
                    # no views for this day?
                    pass
            self._avg_views = total_views/days
                
        return()
        
    def get_views(self, http_session=None):
        '''
        Retrieve the average number of views for the past 14 days
        for this specific page.

        :param http_session: Session to use for HTTP requests
        :type http_session: requests.Session

        :returns: This page's number of average views
        '''
        if self._avg_views is None:
            self._get_views_from_api(http_session=http_session)

        return(self._avg_views)

    def set_rating(self, new_rating):
        '''
        Set this article's current assessment rating.

        :param new_rating: The new assessment rating
        '''
        self._rating = new_rating

    def get_assessment(self, wikitext):
        '''
        Parse the given wikitext and extract any assessment rating.

        If multiple ratings are present, the highest rating is used.
        The same approach is used in the research paper below, where a low
        amount of disagreement was found between using a majority vote
        and the highest rating.

        Warncke-Wang, M., Ayukaev, V. R., Hecht, B., and Terveen, L.
        "The Success and Failure of Quality Improvement Projects in
        Peer Production Communities", in CSCW 2015.

        :param wikitext: wikitext of a talk page
        :returns: assessment rating
        '''

        rating = 'na'
        ratings = [] # numeric ratings

        # Helper objects, the wikiclass extractor wants `mwxml.Page' objects
        Revision = namedtuple("Revisions", ['id', 'timestamp', 'sha1', 'text'])
        class MWXMLPage:
            def __init__(self, title, namespace, revisions):
                self.title = title
                self.namespace = namespace
                self.revisions = revisions
                
            def __iter__(self):
                return iter(self.revisions)
        
        # NOTE: The assessments are at the top of the page,
        # and the templates are rather small,
        # so if the page is > 8k, truncate.
        if len(wikitext) > 8*1024:
            wikitext = wikitext[:8*1024]

        # Extract rating observations from a dummy `mwxml.Page` object
        # where the only revision is our wikitext
        observations = enwiki.extract(MWXMLPage(self.title(),
                                                1,
                                                [Revision(1, Timestamp(1),
                                                          "aaa", wikitext)]))
        for observation in observations:
            try:
                ratings.append(self._wp10_scale[observation['wp10']])
            except KeyError:
                pass # invalid rating

        if ratings:
            # set rating to the highest rating, but the str, not ints
            rating = {v: k for k, v in self._wp10_scale.items()}[max(ratings)]
        return(rating)
        
    def get_rating(self):
        '''
        Retrieve the current article assessment rating as found on the
        article's talk page.

        :returns: The article's assessment rating, 'na' if it is not assessed.
        '''

        if not self._rating:
            try:
                tp = self.toggleTalkPage()
                self._rating = self.get_assessment(tp.get())
            except pywikibot.NoPage:
                self._rating = 'na'
            except pywikibot.IsRedirectPage:
                self._rating = 'na'
            
        return(self._rating)

    def set_prediction(self, prediction):
        '''
        Set the article's predicted quality rating.

        :param prediction: Predicted quality rating.
        :type prediction: str
        '''
        if not prediction in self._wp10_scale:
            raise InvalidRating

        self._prediction = prediction
    
    def _get_ores_pred(self):
        '''
        Make a request to ORES to get the predicted article rating.
        '''
        # make a URL request to config.ORES_url with the following
        # information appended:
        # lang + "wiki/wp10/" + revid

        if not hasattr(self, '_revid'):
            self.site.loadrevisions(self)

        langcode = '{lang}wiki'.format(lang=self.site.lang)
            
        url = '{ores_url}{langcode}/wp10/{revid}'.format(
            ores_url=config.ORES_url,
            langcode=langcode,
            revid=self._revid)

        rating = None
        num_attempts = 0
        while not rating and num_attempts < config.max_url_attempts:
            r = requests.get(url, headers=self._headers)
            num_attempts += 1
            if r.status_code == 200:
                try:
                    response = r.json()
                    rating = response['scores'][langcode]['wp10']['scores'][str(self._revid)]['prediction'].lower()
                    break # ok, done
                except ValueError:
                    logging.warning('Unable to decode ORES response as JSON')
                except KeyError:
                    logging.warning("ORES response keys not as expected")

            # something didn't go right, let's wait and try again
            sleep(500)
        return(rating)
                    
    def get_prediction(self):
        '''
        Retrieve the predicted assessment rating from ORES using the
        current revision of the article.
        '''
        if not self._prediction:
            self._prediction = self._get_ores_pred()
            
        return(self._prediction)

    def _get_qualmetrics(self):
        '''
        Populate quality metrics used for task suggestions.
        '''

        try:
            qualfeatures = qm.get_qualfeatures(self.get())
        except pywikibot.NoPage:
            return()
        except pywikibot.IsRedirectPage:
            return()

        # 1: length
        self._qualdata['length'] = log(qualfeatures.length, 2)
        # 2: lengthToRefs
        self._qualdata['lengthToRefs'] = qualfeatures.length \
                                     /(1 + qualfeatures.num_references)

        # 3: completeness
        self._qualdata['completeness'] = 0.4 * qualfeatures.num_pagelinks
        
        # 4: numImages
        self._qualdata['numImages'] = qualfeatures.num_imagelinks
        # 5: headings
        self._qualdata['headings'] = qualfeatures.num_headings_lvl2 \
                                     + 0.5 * qualfeatures.num_headings_lvl3

        return()
    
    def get_suggestions(self):
        '''
        Decide whether this article is in need of specific improvements,
        and if so, suggest those.
        '''

        # I need page data for:
        if not self._qualdata:
            self._get_qualmetrics()

        for (key, keyDistr) in config.task_dist.items():
            if not key in self._qualdata:
                logging.warning("Warning: suggestion key {0} not found in page data for {1}".format(key, self.title()))
                continue

            if key == u"lengthToRefs":
                pVal = 1 - keyDistr.cdf(self._qualdata[key])
            else:
                # calculate P-value from CDF
                pVal = keyDistr.cdf(self._qualdata[key])

            logging.debug("pVal for {task} is {p:.5f}".format(task=key,
                                                              p=pVal))
            verdict = 'no'
            if pVal < config.task_p_yes:
                verdict = 'yes'
            elif pVal < config.task_p_maybe:
                verdict = 'maybe'
            self._qualtasks[key] = verdict

        return(self._qualtasks)

def TalkPageGenerator(pages):
    '''
    Generate talk pages from a list of pages.
    '''
    for page in pages:
        yield page.toggleTalkPage()
    
def RatingGenerator(pages, step=50):
    '''
    Generate pages with assessment ratings.
    '''

    # Preload talk page contents in bulk to speed up processing
    # Note: since pywikibot's PreloadingGenerator doesn't guarantee
    #       order, we'll have to exhaust it and map title to talkpage.
    tp_map = {}
    for talkpage in PreloadingGenerator(
            TalkPageGenerator(pages), step=step):
        tp_map[talkpage.title(withNamespace=False)] = talkpage

    # iterate and set the rating
    for page in pages:
        try:
            talkpage = tp_map[page.title()]
            page._rating = page.get_assessment(talkpage.get())
        except KeyError:
            page._rating = 'na'
        except pywikibot.NoPage:
            page._rating = 'na'
        except pywikibot.IsRedirectPage:
            page._rating = 'na'
        yield page

def PageRevIdGenerator(site, pagelist, step=50):
    """
    Generate page objects with their most recent revision ID.
    
    This generator is a modified version of `preloadpages` in pywikibot.site.

    :param site: site we're requesting page IDs from
    :param pagelist: an iterable that returns Page objects
    :param step: how many Pages to query at a time
    :type step: int
    """
    for sublist in itergroup(pagelist, step):
        pageids = [str(p._pageid) for p in sublist
                   if hasattr(p, "_pageid") and p._pageid > 0]
        cache = dict((p.title(withSection=False), p) for p in sublist)
        props = "revisions|info|categoryinfo"
        rvgen = api.PropertyGenerator(props, site=site)
        rvgen.set_maximum_items(-1)  # suppress use of "rvlimit" parameter
        if len(pageids) == len(sublist):
            # only use pageids if all pages have them
            rvgen.request["pageids"] = "|".join(pageids)
        else:
            rvgen.request["titles"] = "|".join(list(cache.keys()))
        rvgen.request[u"rvprop"] = u"ids|flags|timestamp|user|comment"
        
        logging.debug(u"Retrieving {n} pages from {s}.".format(n=len(cache),
                                                              s=site))
        for pagedata in rvgen:
            logging.debug(u"Preloading {0}".format(pagedata))
            try:
                if pagedata['title'] not in cache:
#                   API always returns a "normalized" title which is
#                   usually the same as the canonical form returned by
#                   page.title(), but sometimes not (e.g.,
#                   gender-specific localizations of "User" namespace).
#                   This checks to see if there is a normalized title in
#                   the response that corresponds to the canonical form
#                   used in the query.
                    for key in cache:
                        if site.sametitle(key, pagedata['title']):
                            cache[pagedata['title']] = cache[key]
                            break
                    else:
                        logging.warning(
                            u"preloadpages: Query returned unexpected title"
                            u"'%s'" % pagedata['title'])
                        continue
            except KeyError:
                logging.debug(u"No 'title' in %s" % pagedata)
                logging.debug(u"pageids=%s" % pageids)
                logging.debug(u"titles=%s" % list(cache.keys()))
                continue
            page = cache[pagedata['title']]
            api.update_page(page, pagedata)

        # Since we're not loading content and the pages are already in
        # memory, let's yield the pages in the same order as they were
        # received in case that's important.
        for page in sublist:
            yield page
        
def PredictionGenerator(site, pages, step=50):
    '''
    Generate pages with quality predictions.

    :param site: site of the pages we are predicting for
    :type pages: pywikibot.Site

    :param pages: List of pages we are predicting.
    :type pages: list of pywikibot.Page

    :param step: Number of pages to get predictions for at a time,
                 maximum is 50.
    :type step: int
    '''

    # looks like the best way to do this is to first make one
    # API request to update the pages with the current revision ID,
    # then make one ORES request to get the predictions.

    if step > 50:
        step = 50

    langcode = '{lang}wiki'.format(lang=site.lang)
        
    # example ORES URL predicting ratings for multiple revisions:
    # https://ores.wmflabs.org/v2/scores/enwiki/wp10/?revids=703654757%7C714153013%7C713916222%7C691301429%7C704638887%7C619467163
    # sub "%7C" with "|"

    # pywikibot.tools.itergroup splits up the list of pages
    for page_group in itergroup(pages, step):
        revid_page_map = {} # rev id (str) -> page object
        # we use the generator to efficiently load most recent rev id
        for page in PageRevIdGenerator(site, page_group):
            revid_page_map[str(page.latestRevision())] = page

        # make a request to score the revisions
        url = '{ores_url}{langcode}/wp10/?revids={revids}'.format(
            ores_url=config.ORES_url,
            langcode=langcode,
            revids='|'.join([str(page.latestRevision()) for page in page_group]))

        logging.debug('Requesting predictions for {n} pages from ORES'.format(
            n=len(revid_page_map)))

        num_attempts = 0
        while num_attempts < config.max_url_attempts:
            r = requests.get(url,
                             headers={'User-Agent': config.http_user_agent,
                                      'From': config.http_from})
            num_attempts += 1
            if r.status_code == 200:
                try:
                    response = r.json()
                    revid_pred_map = response['scores'][langcode]['wp10']['scores']
                    # iterate over returned predictions and update
                    for revid, score_data in revid_pred_map.items():
                        revid_page_map[revid].set_prediction(score_data['prediction'].lower())
                    break
                except ValueError:
                    logging.warning("Unable to decode ORES response as JSON")
                except KeyErrror:
                    logging.warning("ORES response keys not as expected")

            # something didn't go right, let's wait and try again
            sleep(500)

        for page in page_group:
            yield page
