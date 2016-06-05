#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Test the XML-RPC-based co-edit recommender.
'''

import logging

from suggestbot import config
from suggestbot.profilers import EditProfiler

import xmlrpc.client

def main():
    test_lang = 'en'
    test_user = 'Nettrom'
    test_n = 500

    # Get my edits
    profiler = EditProfiler()
    my_edits = profiler.get_edits(test_user, test_lang, test_n)

    # Collapse into a dict, then a list
    my_edits = {item['title'] : 1 for item in my_edits}
    my_edits = list(my_edits.keys())

    print("Got {} edits back".format(len(my_edits)))

    sp = xmlrpc.client.ServerProxy("http://{hostname}:{port}".format(hostname=config.coedit_hostname, port=config.coedit_hostport))
    try:
        recs = sp.recommend(test_user,
                            test_lang,
                            my_edits)
        print("Got {} recommendations back".format(len(recs)))
    except xmlrpc.client.Error as e:
        logging.error('Getting edits for {0}:User:{1} failed'.format(
            test_lang, test_user))
        logging.error(e)
    return()

if __name__ == "__main__":
    main()
    
                
