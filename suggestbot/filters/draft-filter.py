#!/usr/bin/env python
# -*- coding: utf-8  -*-
'''
Server for filtering sets of recommendations.

'''

import re
import logging

from random import shuffle
from datetime import datetime

from suggestbot import config
from suggestbot.db import SuggestBotDatabase
import suggestbot.utilities.popqual as sup

class RecFilter:
    def __init__(self, randomID=u'random', tooManyEdits=1):
        '''
        Instantiate an object of this class.

        :param randomID: ID to use for randomly selected recommendations
        :type randomID: str

        :param tooManyEdits: how many edits are regarded to be many?
                             used for not selecting very popular articles
        :type tooManyEdits: int
        '''

        # Set up the database
        self.db = SuggestBotDatabase()
        self.dbConn = None
        self.dbCursor = None
        
        self.randomID = randomID

        # Variables for edit counts
        self.editCounts = {}
        self.tooManyEdits = tooManyEdits
        
        # Variable for storing catMembershipQuery so that we won't have to
        # add the language code to it all the time
        self.catMembershipQuery = ""

        # Variable for storing a specific language's regex for matching
        # list articles.
        self.listRegex = None

    def getRecs(self, user=u'', lang=u'en', recLists={}, edits={}, params={}):
        '''
        Find articles needing work from the given lists of recommendations,
        not recommending anything found in the list of edits.

        :param user: username of the user we are recommending articles to
        :type user: str

        :param lang: language code of the Wikipedia we're recommending for
        :type lang: str

        :param recLists: list of recommendations for each recommender server
        :type recLists: dict (of list of str)

        :param edits: dictionary of titles of the articles the user has recently edited,
                      keys are article titles, values are redundant
        :type edits: dict

        :param params: parameters for the filtering
        :type params: dict
        '''

        # SQL query to test if an article is in a category
        # Note that we store it in the object to do language code
        # interpolation once.
        self.catMembershipQuery = """SELECT *
                                     FROM {lang}wiki_work_category_data
                                     WHERE category=%(category)s
                                     AND title=%(title)s""".format(lang=lang)

        # SQL query to get all work tags applied to a given article
        getArticleCatsQuery = """SELECT category
                                 FROM {lang}wiki_work_category_data
                                 WHERE title=%(title)s""".format(lang=lang)

        # SQL query to get old recommendations from the log table
        getOldRecsQuery = """SELECT title
                             FROM (SELECT recsetid
                                   FROM {user_recs}
                                   WHERE lang=%(lang)s
                                   AND username=%(username)s
                                   ORDER BY rectime DESC
                                   LIMIT %(nrecsets)s) AS userecs
                             JOIN {logtable}
                             USING (recsetid)""".format(
                                 user_recs=config.reclog_table,
                                 logtable=self.config.getConfig('recommendation_log_new'))

        # Set up the list regex for this language
        self.listRegex = re.compile(self.config.getConfig('LIST_RE')[lang])

        # Turn username into str if not
        if not isinstance(user, str):
            logging.error('User is not a str, aborting!')
            return {}

        print("Got request to filter recommendations for user {0}:{1}".format(lang, user))

        logging.info("User has {0} edits we'll make sure we don't recommend.".format(len(edits)))
        logging.info("Info: Getting recs in categories {0}\n".format(params['categories']))

        categories = params['categories'].split(",")

        # The set of recommendations we'll return
        recs = {}

        # A dictionary mapping recommender ID to the rank of the last rec we chose
        recRanks = {}

        # Maximum number of recommendations in each list of recommendations
        maxListLength = params['nrecs-per-server']

        # Connect to database, prepare all SQL statements
        if not self.db.connect():
            logging.error("Unable to connect to the SuggestBot database, can't filter squat!")
            return recs
        
        (self.dbConn, self.dbCursor) = self.db.getConnection()

        logging.info("Got database connection, now fetching user's previous recs...")

        # Get the previous recommendations from the database and add them to the
        # full list of the user's edits, to prevent them from being recommended.
        self.dbCursor.execute(getOldRecsQuery, {'lang': lang,
                                                'username': user,
                                                'nrecsets': self.config.getConfig('RECSET_EXCLUDE_K')})
        for row in self.dbCursor.fetchall():
            pageTitle = row['title']
            edits[pageTitle] = 1

        logging.info("known list of edits now {0} items\n".format(len(edits)))

        # Now build our combined recommendations.

        # For each category, we track the rank of the last recommendation
        # from each of the recommendation lists.
        for cat in categories:
            recRanks[cat] = {}
            for recID in recLists.keys():
                recRanks[cat][recID] = 0

        logging.info("Info: done writing ranks, now filtering...")

        # Each category wants N recs, so, let's iterate through positions
        # 1..n and get the best recommendation that one of the recommenders
        # can offer for that category.
            
        # Randomise the order of the categories to even out the odds
        # that a given category will get a highly similar article.
        shuffle(categories)

        for i in range(1, params['nrecs']+1):
            for cat in categories:
                # For each recommendation, give each recommender an equal shot at
                # being 1st, 2nd, 3rd to provide it.  We tried a random recommender
                # and it was just terrible, so it's been removed.
                thisOrder = recLists.keys()
                shuffle(thisOrder)

                # Try recommenders in order until one can supply a recommendation.
                found = False
                while not found and len(thisOrder) > 0:
                    nextRecommender = thisOrder.pop()
                    if nextRecommender == self.randomID:
                        found = self.getOneRandomRec(cat=cat, rank=i, recs=recs,
                                                     edits=edits, maxLength=maxListLength,
                                                     lang=lang)
                    else:
                        logging.info("getting one rec from {0}\n".format(nextRecommender))
                        found = self.getOneRec(recList=recLists[nextRecommender],
                                               recId=nextRecommender,
                                               cat=cat, rank=i, recs=recs,
                                               edits=edits, lang=lang,
                                               recRanks=recRanks)
                        if found:
                            logging.info("Found rec using {recid} recommender.".format(recid=nextRecommender))

                # If none could, or it's random's turn, pick one randomly.
                if not found:
                    found = self.getOneRandomRec(cat=cat, rank=i, recs=recs,
                                                 edits=edits, maxLength=maxListLength,
                                                 lang=lang)
                    if found:
                        logging.info("got random rec.")

                # If we can't even find one randomly, that's really bad.
                if not found:
                    logging.warning("Whoa, couldn't even randomly pick a rec for {cat}!\n".format(cat=cat))
                    return {}

        # For each recommended article, look up and store
        # _all_ the work categories it is in.
        for recTitle in recs.keys():
            recs[recTitle]['allcats'] = []
            self.dbCursor.execute(getArticleCatsQuery,
                                  {'title': recTitle})
            for row in self.dbCursor.fetchall():
                recs[recTitle]['allcats'].append(row['category'])

        # Now go fetch popularity and quality info for the recommended articles
        # (if the user is on en-WP, that is, for now...)

        # Default values are empty strings and lists and such...
        for rec in recs.keys():
            recs[rec]['pop'] = ''
            recs[rec]['popcount'] = -1
            recs[rec]['qual'] = ''
            recs[rec]['pred'] = ''
            recs[rec]['predclass'] = ''
            recs[rec]['work'] = []

        # Currently we only do popularity/quality/tasks for English Wikipedia
        if lang == 'en':
            logging.info('Getting popularity & quality data...')
            popquals = sup.get_popquals(lang, recs.keys(), do_tasks=True)
            for pq_info in popquals:
                # Copy over the pop/qual info, keys should match
                recs[pq_info['title']].update(pg_info)
                    
        logging.info("OK, done!")

        self.db.disconnect()
        print("Completed filtering recommendations for user {0}:{1}".format(lang, user))

        # Send back the recommendations.
        return recs

    def getOneRandomRec(self, cat=None, rank=0, recs=None, edits=None,
                        maxLength=0, lang=None):
        '''
        Get a random rec from the given category.

        @param cat: The category we are getting random recommendations for
        @tpye cat: str

        @param rank: The rank of the recommendation we are getting (e.g. STUB1)
        @type rank: int

        @param recs: The current set of recommendations
        @type recs: dict

        @param edits: The user's edits
        @type edits: dict

        @param maxLength: the maximum length of a recommendation set
        @type maxLength: int

        @param lang: The language code of the Wiki we're working on
        @type lang: str
        '''

        # Build a little faux rec set for the get_one_rec_method.
        # Little is better because otherwise we have to sort long lists
        # for each rec down there.

        # SQL query to get a random set of recommendations in a given category
        randomRecQuery = """SELECT * 
                            FROM
                                (SELECT * FROM
                                 {lang}wiki_work_category_data
	                         WHERE category=%(category)s
                                 LIMIT %(sublimit)s)
                            AS work_cat
                            ORDER BY RAND()
	                    LIMIT %(limit)s""".format(lang=lang)
        # our faux rec-set
        recList = []

        strippedCat = re.sub(r'\d*', '', cat) # remove numbers for multiply-listed categories
        maxItems = max(10000, 4*maxLength)

        self.dbCursor.execute(randomRecQuery, {'category': strippedCat,
                                               'sublimit': maxItems,
                                               'limit': maxLength})
        for row in self.dbCursor.fetchall():
            recList.append(row['title'])

        logging.info("got {num} hits for category {cat}".format(num=len(recList), cat=strippedCat))

        # We always force random IDs to start looking for items at slot 0, of course.
        randomRanks = { cat : { self.randomID : 0 }}
        return self.getOneRec(recList=recList, recId=self.randomID,
                              cat=cat, rank=rank, recs=recs,
                              edits=edits, lang=lang, recRanks=randomRanks)

    def tooManyEdits(self, item=None):
        if not item:
            return False
        try:
            if editCounts[item] >= self.tooManyEdits:
                return True
        except KeyError:
            # item not in editCounts, pass and return False
            pass
        return False

    def getOneRec(self, recList=None, recId=None, cat=None, rank=0, recs=None,
                  edits=None, lang=None, recRanks=None):
        '''
        Try to get the next recommendation from a given recommendation list
        that is in a given category and hasn't already been recommended.

        @param recList: the list of recommendations to look for articles in
        @type recList: list

        @param recId: the ID of the recommender who created the list
        @type recId: str

        @param cat: the category we are recommending in
        @type cat: str

        @param rank: the rank of the recommendation we're getting (e.g. STUB1)
        @type rank: int

        @param recs: The current set of recommendations
        @type recs: dict

        @param edits: The user's edits
        @type edits: dict

        @param lang: Language code of the Wiki we're working on
        @type lang: str

        @param recRanks: ranking of the last issued recommendation, keys are
                         categories, values are dicts where keys are recommender IDs
                         and values are ints (the ranking).
        @type recRanks: dict
        '''

        logging.info("Got request for one rec from {0}, looking at {1} candidates in a {2}".format(recId, len(recList), type(recList)))

        # Go through the list of recommendations in order, starting from the
        # first one that hasn't been found recommendable.
        for j in range(recRanks[cat][recId], len(recList)):
            rec = recList[j]
            if not isinstance(rec, str):
                rec = str(rec)

            logging.info("candidate #{0} is {1}".format(j+1, rec))

            # Make sure it's not already recommended nor edited by user,
            # that it's not a list article, and that it's in the right category.
            if rec in recs \
                    or rec in edits \
                    or self.listRegex.match(rec) \
                    or not self.inCategory(cat=cat, rec=rec):
                continue

            # Book it.
            logging.info("Booking the recommendation {0}, rec rank: {1}\n".format(rec, j))

            recs[rec]  = {'cat': cat,
                          'rank': rank,
                          'source': recId,
                          'rec_rank': j}

            # Set $rec_ranks_href to the rank of the next item we want to visit,
            # which is the one right after the one we just booked.
            recRanks[cat][recId] = j+1
            return True
    
        # We must have failed.
        return False

    def inCategory(self, cat, rec):
        """
        Decide if a recommendation is in the given category.

        @param cat: The category we're checking
        @type cat: str

        @param rec: Title of the article we're attempting to recommend
        @type rec: str
        """

        # This is just asking the SQL database if category "foo" contains "bar"
        # which we have indexes to make sure goes fast.
        strippedCat = re.sub(r'\d*', '', cat) # remove numbers for multiply-listed categories
        self.dbCursor.execute(self.catMembershipQuery, {'category': strippedCat,
                                                        'title': rec})
        rows = self.dbCursor.fetchall()
        if rows:
            return True
        return False
