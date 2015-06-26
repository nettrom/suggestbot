#import sys
#sys.path.append('export/scratch/evan/pyenvs/sb/suggestbot/suggestbot/recommenders/collaborator.py')
from suggestbot.recommenders.collaborator import CollabRecommender
import pywikibot

def __main__():
	print("Beginning collaborator recommendation test")

	name = "Aldaron"
	site = pywikibot.Site('en') 
	user = pywikibot.User(site, name)

	contribs = []

	for (page, revid, time, comment) in user.contributions(128):
		contribs.append(page.title)	

	rec = CollabRecommender()	

	matches = rec.recommend(contribs, name, 'en', 10)

	for result in matches:
		print("%s", result)

	print("Matching complete")
	
__main__()
