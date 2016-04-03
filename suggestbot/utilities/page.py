#!/usr/bin/env python
# -*- coding: utf-8  -*-
'''
SuggestBot Recommender Libraries

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

## Purpose of this module:
## Extend the Pywikibot page object with information on:
## 1: the page's assessment rating
## 2: predicted assessment rating by ORES
## 3: page views for the past 14 days as well as average views/day
##    over the same time period
## 4: specific suggestions for article improvement

import logging
import pywikibot
import requests

import mwparserfromhell as mwp

from time import sleep
from datetime import date, timedelta
from urllib.parse import quote

from suggestbot import config

class InvalidRating(Exception):
    '''The given rating is not one we support.'''
    pass

class Page(pywikibot.Page):
    def __init__(self, site, title, *args, **kwargs):
        super(Page, self).__init__(site, title, *args, **kwargs)

        self._avg_views = None # avg views per last 14 days
        self._rating = None # current assessment rating
        self._prediction = None # predicted rating by ORES

        self._wp10_scale = {'stub': 0,
                            'start': 1,
                            'c': 2,
                            'b': 3,
                            'ga': 4,
                            'a': 5,
                            'fa': 6}

    def set_views(self, views):
        '''
        Set the number of average views.

        :param views: Number of average views.
        :type views: float
        '''
        self._avg_views = views

    def _get_views_from_api(self):
        '''
        Make a request to the Wikipedia pageview API to retrieve page views
        for the past 14 days and calculate and set `_avg_views` accordingly.
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

        today = date.today()
        start_date = today - timedelta(days=16)
        end_date = today - timedelta(days=2)

        # test url for Barack Obama
        # 'https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/Barack%20Obama/daily/20160318/20160331'
        
        url = '{api_url}{lang}.wikipedia/all-access/all-agents/{title}/daily/{startdate}/{enddate}'.format(api_url=config.pageview_url, lang=self.site.lang, title=quote(self.title(), safe=''), startdate=start_date.strftime('%Y%m%d'), enddate=end_date.strftime('%Y%m%d'))

        view_list = []
        num_attempts = 0
        while not view_list and num_attempts < config.max_url_attempts:
            r = requests.get(url)
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
        
    def get_views(self):
        '''
        Retrieve the average number of views for the past 14 days
        for this specific page.

        :returns: This page's number of average views
        '''
        if self._avg_views is None:
            self._get_views_from_api()

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

        # NOTE: The assessments are at the top of the page,
        # and the templates are rather small,
        # so if the page is > 8k, truncate.
        if len(wikitext) > 8*1024:
            wikitext = wikitext[:8*1024]
        
        parsed_text = mwp.parse(wikitext)
        templates = parsed_text.filter_templates()
        for template in templates:
            try:
                label = str(template.get('class').value.strip().lower())
                ratings.append(self._wp10_scale[label])
            except ValueError:
                pass # no class rating in the template
            except KeyError:
                pass # rating invalid

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
            r = requests.get(url)
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
