def main():
    pass

#!/usr/bin/perl -I../config -I../utils -I../algos

# Rewritten co-edit server that handles multiple languages
# and communicates through XML-RPC, using the database for
# data storage instead of reading the coedits-file into (lots of) memory.

# FIXME: Make table's username and title varchar(255) binary,
#        and consider making it rank by recency as well as co-edits.
#        Consider alternative approaches to measuring similarity, e.g. Cosine,
#        and alternative ways of choosing articles (e.g. equivalence classes)

# The 'use lib' statement is necessary to be able to find the XML-RPC library.

import config
import db
import logging

default_lang = "en"

# Default parameters, can be overridden per-request.
default_params = {
    'nrecs' : 100,
    'lang' : default_lang,
    'threshold' : 3,
    'backoff' : 0,
    'min_threshold' : 1,
    'association-threshold' : 0.0001,
    'filter-threshold' : 18, # number of edits where we filter out minors & reverts
}

# Easier to have these SQL queries as global variables, rather than pass
# them around.  Does make for possible errors if they're not prepared
# properly before execution, though.
get_articles_by_user_query =""
get_articles_by_expert_user_query = ""
get_editcount_query = ""

def recommend(in_contribs, in_username, in_lang, in_nrecs = 100, in_threshold = 3, in_backoff = 0):

    # Second param is the list of articles the user has edited
    # Third is the username
    # Fourth is a string with the language code (optional, default is config)
    # Fifth  is the number of recommendations we want (default: 100)
    # Sixth is the co-edit threshold (default: 3)
    # Seventh is the backoff (default: 0)
    contribs = in_contribs
    username = in_username
    lang = in_lang
    nrecs = in_nrecs
    threshold = in_threshold
    backoff = in_backoff

    params = default_params

    # FIXME: return fault if username is not defined

    params['username'] = username
    params['lang'] = lang
    params['nrecs'] = nrecs
    params['threshold'] = threshold
    params['backoff'] = backoff

    logging.info("Got request for user {0}:{1} to recommend based on {2} edits!".format(params['lang'], username.encode('utf-8'), len(contribs)))

    N = params['nrecs']
    coedit_threshold = params['threshold']
    backoff = params['backoff']
    min_thresh = params['min_threshold']

    # Get some recs.
    recs = get_recs_at_coedit_threshold(contribs, params)

    # If we're allowed to back off on the coedit threshold and don't have enough
    # recs, ease off on the threshold and try again.

    needed = N
    if recs in locals():
        needed = N - len(recs)

    while backoff and --coedit_threshold >= min_thresh and needed:
        params['threshold'] = coedit_threshold
        recs = get_recs_at_coedit_threshold(contribs, params)
        needed = N - len(recs)

    # This shouldn't happen, but...
    if recs in locals():
        "Completed getting recs.\n"
        return recs[:N]
    else:
        return [] # return an empty array


def get_recs_at_coedit_threshold(in_contribs, in_param_map_ref):
    contribs = in_contribs
    param_map_ref = in_param_map_ref
    # coedit-threshold is now param_map_ref['threshold']

    # We're working with this language version of Wikipedia
    lang = param_map_ref['lang']

    # Return this many recs
    N = param_map_ref['nrecs']

    # Exclude items edited by this user.
    user_for_query = param_map_ref-['username']

    # Must have this template in the page
    template_filter = param_map_ref['template-filter']

    # Neighbours must have at least this much association.
    association_threshold = param_map_ref['association-threshold']

    # Connect to the database, prepare SQL statements
    row = 0 # result row variable
    db = db.SuggestBotDatabase()
    if not db.connect():
        sys.stderror.write("Failed to connect to db")
        return []

    (conn, cursor) = db.getConnection()

    # NOTE: because rev_user and rev_title currently are VARCHAR(255) and UTF-8,
    # they're assumed to consume ~765 bytes in memory, and therefore MySQL chooses
    # to use a temp file table rather than a temp memory table.  Because the queries
    # to get users by article are each only run once per article a user edited,
    # we can live with the temp file being created to move less data.

    # First query gets users who made non-minor, non-reverting edits
    # to this article.  These are _always_ potential neighbours.
    get_users_by_article_query = """SELECT DISTINCT rev_user
                                    FROM {coedit_table}
                                    WHERE rev_title = %(title)s
                                    AND rev_is_minor = 0
                                    AND rev_comment_is_revert = 0""".format(coedit_table=config.coedit_table[lang])


    # Second query gets the other users (either minor or reverting),
    # these are only interesting if they're below the threshold for total
    # number of edits, as they otherwise know what they were doing.
    get_minor_users_by_article_query = """SELECT DISTINCT rev_user
                                          FROM {coedit_table}
                                          WHERE rev_title = %(title)s
                                          AND (rev_is_minor = 1
                                          OR rev_comment_is_revert = 1)""".format(coedit_table=config.coedit_table[lang])

    # Query to get edited articles for a given user if the user is
    # below the edit threshold.
    get_articles_by_user_query = """SELECT rev_title
                                    FROM {coedit_table}
                                    WHERE rev_user = %(username)s""".format(coedit_table=config.coedit_table[lang])

    # Query to get edited articles for a user who is above the threshold,
    # we then disregard minor edits and reverts.
    get_articles_by_expert_user_query = """SELECT rev_title
FROM {coedit_table}
WHERE rev_user = %(username)s
AND rev_is_minor = 0
AND rev_comment_is_revert = 0""".format(coedit_table=config.coedit_table[lang])

    # Query to get the number of edits a user has made (in our dataset)
    get_editcount_query = """SELECT count(*) AS numedits
                             FROM {coedit_table}
                             WHERE rev_user = %(username)s""".format(coedit_table=config.coedit_table[lang])

    rec_map = {}

    # How many different users have coedited a given item with something
    # in the basket
    coedit_count = {}

    # Find users who rated the given items
    coeditor_map = {}
    user_assoc = {}
    user_shared = {}

    logging.info("user {0}:".format(user_for_query))

    user = ""
    num_edits = 0
    page_title = ""

    for item in contribs:
    	# For each article the user has edited, find other editors.
        other_editors = []

    	# First we get major stakeholders in the article (non-minor/non-reverting edits)
        try:
            cursor.execute(get_users_by_article_query,
                           {'title': item})
        except MySQLdb.Error:
            logging.error("unable to execute query to get users by article")
            return []

        for row in cursor:
            user = row['rev_user']
            if user in coeditor_map:
                continue

            if user == user_for_query:
                continue

            other_editors[user] = 1

    	# Then we check minor edits and reverts, and keep those users who are
    	# not in the top 10% of users (see param filter-threshold defined earlier).

    	# Users we've seen (so we don't re-run SQL queries all the time)...
        seen_minors = {}

        try:
            cursor.execute(get_minor_users_by_article_query,
                           {'title': item})
        except MySQLdb.Error:
            logging.error("unable to execute query to get users by article")
            return []

        for row in cursor:
            if user in coeditor_map:
                continue
            if user in other_editors:
                continue
            if user in seen_minors:
                continue
            seen_minors[user] = 1

        for username in seen_minors.keys():
            try:
                cursor.execute(get_editcount_query,
                                {'username': username})
            except MySQLdb.Error:
                logging.error("unable to execute query to get editcount for user")

            if row['numedits'] >= param_map_ref['filter-threshold']:
                other_editors[username] = 1

	# Now we have all relevant stakeholders in the article, and can
	# compute the appropriate association.
    for user in other_editors:
	    # Add user to coeditor-map so we'll skip this user later
        coeditor_map[user] = 1

        (assoc, shared) = user_association(user, contribs,
            param_map_ref['filter-threshold'], cursor)

        if assoc < association_threshold:
            continue

        user_assoc[user] = assoc
        user_shared[user] = shared

    logging.info("Found {0} pre-neighbours".format(len(user_assoc)))

    # Find nhood of top k users
    k = 250  # Larger nhood for more recs, hopefully
    nhood = sorted(user_assoc.items(), key=operator.itemgetter(1), reversed=True)[:k]

    db.disconnect()

    # Rank 'em and spit out N of them
    recs = []
    for rec_ct in range(0, N):
	# Note: again we need to make sure we send proper UTF-8 here.
	# (but we didn't we have to do that with the MySQL stuff?)

        map = {}
        map['user'] = other_editors[rec_ct]
        map['assoc'] = user_assoc
        map['shared'] = user_shared
        recs.append(map)

    return recs

def user_association(in_user, in_basket_ref, in_exp_threshold, dbcursor):
    # First argument is the user we're looking at.
    # Second is the contributions of the user we're recommending to.
    # Third is the threshold (int) for determining expert users.
    user = in_user
    basket_ref = in_basket_ref
    exp_threshold = in_exp_threshold

    assoc = 0
    shared = 0
    row = ""
    user_edits_ref = {}

    # Find common articles.  We first find the user's editcount, to check if this user
    # is in the top 10% of users or not.  If they are (as defined by filter-threshold)
    # we'll only use non-minor, non-reverting article edits for comparison.
    # Otherwise, we use all articles the user edited.
    user_editcount = 0
    page_title = ""
    dbcursor.execute(get_editcount_query,
                     {'username': user})

    for row in cursor:
        user_editcount = row['numedits']

    if user_editcount >= xp_threshold:
        dbcursor.execute(get_articles_by_expert_user_query,
                         {'username': user})
        for row in dbcursor:
            user_edits_ref[row['rev_title']] = 1
    else:
        dbcursor.execute(get_articles_by_user_query,
                         {'username': user})
        for row in dbcursor:
            user_edits_ref[row['rev_title']] = 1

    for item in basket_ref:
        if item in user_edits_ref:
            ++shared

    assoc = shared / (len(basket_ref) + len(user_edits_ref) - shared)

    return (assoc, shared)