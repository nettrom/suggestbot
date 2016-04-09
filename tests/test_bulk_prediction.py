# Test get_views() method using the pageview API

import logging
logging.basicConfig(level=logging.INFO)

import pywikibot
import suggestbot.utilities.page as sup

site = pywikibot.Site('en')

pagelist = [sup.Page(site, 'Barack Obama'),
            sup.Page(site, 'Ara Parseghian'),
            sup.Page(site, 'Clarence Darrow'),
            sup.Page(site, 'Andre Dawson'),
            sup.Page(site, '2004 Chicago Bears season'),
            sup.Page(site, "Jack O'Callahan"),
            sup.Page(site, "Switchcraft")]

for page in sup.PredictionGenerator(site, pagelist):
    print("{0} has a page ID of {1}, last revision of {2}, and prediction of {3}".format(page.title(), page._pageid, page.latestRevision(), page.get_prediction()))
    
