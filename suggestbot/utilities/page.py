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

from suggestbot import config

class Page(pywikibot.Page):
    def __init__(self, site, title, *args, **kwargs):
        super(Page, self).__init__(site, title, *args, **kwargs)

        self._avg_views = None # avg views per last 14 days
        self._rating = None # current assessment rating
        self._prediction = None # predicted rating by ORES
        
    def get_views(self):
        '''
        Retrieve the average number of views for the past 14 days
        for this specific page.
        '''

        # make a URL request to config.pageview_url with the following
        # information appendend:
        # languageCode + '.wikipedia/all-access/all-agents/' + uriEncodedArticle + '/daily/' +
        # startDate.format(config.timestampFormat) + '/' + endDate.format(config.timestampFormat)
        pass

    def get_rating(self):
        '''
        Retrieve the current article assessment rating as found on the
        article's talk page. Returns `None` if article is unrated.
        '''
        pass

    def get_prediction(self):
        '''
        Retrieve the predicted assessment rating from ORES using the
        current revision of the article.
        '''
        # make a URL request to config.ORES_url with the following
        # information appended:
        # "enwiki/?models=wp10&revids=" + current revision ID

        pass
    
