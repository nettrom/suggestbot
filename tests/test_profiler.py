#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Test the XML-RPC-based edit profiler.
'''

import logging

from suggestbot import config
import xmlrpc.client

def main():
    test_lang = 'en'
    test_user = 'Nettrom'
    
    sp = xmlrpc.client.ServerProxy("http://{hostname}:{port}".format(hostname=config.edit_server_hostname, port=config.edit_server_hostport))
    try:
        edits = sp.get_edits(test_user,
                             test_lang,
                             config.nedits)
        print("Got {} edits back".format(len(edits)))
    except xmlrpc.client.Error as e:
        logging.error('Getting edits for {0}:User:{1} failed'.format(
            lang, user))
        logging.error(e)
    return()

if __name__ == "__main__":
    main()
    
                
