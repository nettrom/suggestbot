#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Tool Labs database connection library
'''

import os

import MySQLdb
from MySQLdb import cursors

def connect(dbhost='enwiki.labsdb',
            dbname='enwiki_p',
            dbconf='~/replica.my.cnf'):
    '''
    Open the database connection.
    '''
    try:
        dbconn = MySQLdb.connect(host=dbhost,
                                 db=dbname,
                                 charset='utf8',
                                 read_default_file=os.path.expanduser(dbconf))
        # Create an SSDictCursor, standard fare.
        dbcursor = dbconn.cursor(cursors.SSDictCursor)
        return (dbconn, dbcursor)
    except MySQLdb.Error as e:
        logging.error("Unable to connect to database: {code} {explain}".format(code=e.args[0], explain=e.args[1]))

    return (None, None)
    
def disconnect(dbconn, dbcursor):
    '''
    Close the given database connection, closing the cursor
    first if possible.
    '''
    try:
        dbcursor.close()
    except MySQLdb.Error as e:
        pass

    try:
        dbconn.close()
    except MySQLdb.Error as e:
        logging.error("Unable to disconnect from database: {code} {explain}".format(code=e.args[0], explain=e.args[1]))
        
    return
