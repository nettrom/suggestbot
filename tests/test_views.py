import logging
logging.basicConfig(level=logging.DEBUG)

# Test get_views() method using the pageview API
import pywikibot
from suggestbot.utilities.page import Page

site = pywikibot.Site('en')
page = Page(site, 'Barack Obama')
print("{0} had {1} views".format(page.title(), page.get_views()))
