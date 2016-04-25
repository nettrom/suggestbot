# Test get_views() method using the pageview API
import pywikibot
from suggestbot.utilities.page import Page

site = pywikibot.Site('en')

# page = Page(site, 'Barack Obama')
# print("{0} has a rating of {1}".format(page.title(), page.get_rating()))
# page = Page(site, 'Ara Parseghian')
# print("{0} has a rating of {1}".format(page.title(), page.get_rating()))
# page = Page(site, 'Clarence Darrow')
# print("{0} has a rating of {1}".format(page.title(), page.get_rating()))
# page = Page(site, 'Andre Dawson')
# print("{0} has a rating of {1}".format(page.title(), page.get_rating()))
# page = Page(site, '2004 Chicago Bears season')
# print("{0} has a rating of {1}".format(page.title(), page.get_rating()))
# page = Page(site, "Jack O'Callahan")
# print("{0} has a rating of {1}".format(page.title(), page.get_rating()))
# page = Page(site, "Switchcraft")
# print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

# These were all assessed as NA, bug?
page = Page(site, "Fender American Deluxe Series")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "Axel F")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "Song structure")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "Seven-string guitar")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "Slow parenting")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "Hex key")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "Abbassa Malik")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "Don't Tell Me You Love Me")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "Northern Light Orchestra")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "Keep On Moving (The Butterfield Blues Band album)")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))

page = Page(site, "(You Can Still) Rock in America")
print("{0} has a rating of {1}".format(page.title(), page.get_rating()))
