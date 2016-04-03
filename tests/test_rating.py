# Test get_views() method using the pageview API
import pywikibot
from suggestbot.utilities.page import Page

site = pywikibot.Site('en')
page = Page(site, 'Barack Obama')
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, 'Ara Parseghian')
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, 'Clarence Darrow')
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, 'Andre Dawson')
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, '2004 Chicago Bears season')
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "Jack O'Callahan")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "Switchcraft")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))
