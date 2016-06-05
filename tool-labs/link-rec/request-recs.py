#!/usr/bin/python
# -*- coding: utf-8  -*-

import json
import logging
import requests


linkrec_url = "http://tools.wmflabs.org/suggestbot/link_recommender"

params = {
    'lang': 'en',
    'nrecs' : 2500,
}

seed_articles = {
    u'Elizabeth F. Churchill' : 1,
    u'Paul Dourish' : 1,
    u'Don Norman' : 1,
    u'Ben Shneiderman' : 1,
    u'Robert E. Kraut' : 1
}

print("Sending request for {n} recommendations based on {m} seed articles".format(n=params['nrecs'], m=len(seed_articles)))

r = requests.post(linkrec_url,
                  data={'items': json.dumps(seed_articles),
                        'params': json.dumps(params)})
if r.status_code != 200:
    logging.error("Web server did not return 200 OK, unable to continue")
else:
    try:
        response = r.json()
        recs = response['success']
        print("Got {n} recommendations back".format(n=len(recs)))
    except ValueError:
        logging.error("Unable to decode response as JSON")
    except KeyError:
        logging.error("Did not find key 'success' in reponse, error?")
