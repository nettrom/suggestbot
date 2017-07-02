#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Library for connecting to the SuggestBot database.

Copyright (C) 2005-2016 SuggestBot Dev Group

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Library General Public
License as published by the Free Software Foundation; either
version 2 of the License, or (at your option) any later version.

This library is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
Library General Public License for more details.

You should have received a copy of the GNU Library General Public
License along with this library; if not, write to the
Free Software Foundation, Inc., 51 Franklin St, Fifth Floor,
Boston, MA  02110-1301, USA.
'''

__version__ = "$Id$"

import os
import logging

import MySQLdb
import MySQLdb.cursors

ctypes = {'dict': MySQLdb.cursors.DictCursor,
          'ss': MySQLdb.cursors.SSCursor,
          'ssdict': MySQLdb.cursors.SSDictCursor,
          'default': MySQLdb.cursors.Cursor
          }

def cursor(connection, cursor_type=None):
    '''
    Get a cursor connected to the given database connection.

    :param connection: an open database connection
    :type MySQLdb.Connection

    :param cursor_type: type of cursor we want back, one of either:
                        'dict': MySQLdb.cursor.DictCursor
                        'ss': MySQLdb.cursor.SSCursor
                        'ssdict': MySQLdb.cursor.SSDictCursor
                        if no type is specified, the default
                        (MySQLdb.cursors.Cursor) is returned
    :type cursor_type: str
    '''

    if cursor_type is None:
        cursor_type = 'default'
    return(connection.cursor(ctypes[cursor_type]))

class SuggestBotDatabase:
    def __init__(self, default_file='my.cnf'):
        """
        Instantiate an object of this class.

        :param default_file: path to the MySQL configuration file,
                             relative to the SuggestBot installation directory
        :type default_file: str
        """

        self.default_file = os.path.join(os.environ['SUGGESTBOT_DIR'], default_file)
        self.conn = None;
        self.cursor = None;

    def connect(self):
        '''
        Connect to the database that is defined in config.
        '''
        try:
            self.conn = MySQLdb.connect(read_default_file=self.default_file,
                                        charset='utf8')
            self.cursor = self.conn.cursor(MySQLdb.cursors.DictCursor)
            return True
        except MySQLdb.Error as e:
            logging.error("Unable to connect to database.")
            logging.error("Error {0}: {1}".format(e.args[0], e.args[1]))
            return False

    def disconnect(self):
        '''
        Disconnect from the database.
        '''
        try:
            if self.cursor:
                self.cursor.close()
                self.cursor = None
            if self.conn:
                self.conn.close()
                self.conn = None
            return True;
        except MySQLdb.Error as e:
            logging.error("Unable to disconnect from database.")
            logging.error("Error {0}: {1}".format(e.args[0], e.args[1]))
            return False

    def getConnection(self):
        """
        Get a database connection from this object.

        Returns a tuple of (connection, cursor) for this connection,
        where 'connection' is a MySQLdb.Connection object,
        and 'cursor' is a MySQLdb.cursors.Dictcursor object,
        unless we are disconnected, in that case both are None.
        """
        return (self.conn, self.cursor)
