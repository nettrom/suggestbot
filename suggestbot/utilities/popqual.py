#!/usr/bin/env python
# -*- coding: utf-8  -*-
'''
Wrapper around our customized Page object to retrieve
popularity and quality information for a list of articles.

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

import logging

import requests

import pywikibot
from pywikibot.pagegenerators \
    import PagesFromTitlesGenerator, PreloadingGenerator

from suggestbot import config
import suggestbot.utilities.page as sup

def get_popquals(lang, titles, do_tasks=False):
    '''
    Get popularity and quality data for the given list of article titles.
    If do_tasks is set, also get task recommendations.

    :param titles: Article titles to retrieve data for
    :type titles: list (of str)

    :param do_tasks: Should we get recommendations for specific tasks?
    :type do_tasks: bool
    '''

    site = pywikibot.Site(lang)

    # Make our titles into Page objects
    pages = [sup.Page(site, title) for title in titles]

    # List of dictionaries with popularity and quality data
    result = []

    # Create HTTP session to pool pageview HTTP requests
    http_session = requests.Session()
    
    for page in PreloadingGenerator(
            sup.PredictionGenerator(site,
                                sup.RatingGenerator(pages))):
        
        # 2: populate task suggestions
        task_suggestions = page.get_suggestions()

        # Page data we'll return, with some defaults
        pdata = {
            'title': page.title(),
            'pop': 'High',
            'popcount': round(page.get_views(http_session=http_session)),
            'qual': page.get_rating(),
            'pred': 'NA',
            'predclass': page.get_prediction(),
            'work': ['{0}:{1}'.format(k, v) \
                     for k, v in task_suggestions.items()],
            'pred-numeric': -1
            }

        # Properly capitalize or uppercase predicted class:
        if pdata['predclass'] in ['start', 'stub']:
            pdata['predclass'] = pdata['predclass'].capitalize()
        else:
            pdata['predclass'] = pdata['predclass'].upper()

        if pdata['qual'] in ['start', 'stub']:
            pdata['qual'] = pdata['qual'].capitalize()
        else:
            pdata['qual'] = pdata['qual'].upper()
            
        # Set medium/low popularity if below thresholds
        if pdata['popcount'] <= config.pop_thresh_low:
            pdata['pop'] = 'Low'
        elif pdata['popcount'] <= config.pop_thresh_med:
            pdata['pop'] = 'Medium'

        # Set high/medium/low quality based on assessment rating
        if pdata['qual'] in ['FA', 'A', 'GA'] \
           or pdata['predclass'] in ['FA', 'GA']:
            pdata['pred'] = 'High'
            pdata['pred-numeric'] = 3
        elif pdata['predclass'] in ['B', 'C']:
            pdata['pred'] = 'Medium'
            pdata['pred-numeric'] = 2
        else:
            pdata['pred'] = 'Low'
            pdata['pred-numeric'] = 1

        result.append(pdata)

    return(result)
