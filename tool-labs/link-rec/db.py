#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Library to connect to a given shared replicated Wikipedia database server.

Copyright (c) 2017 Morten Wang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import os
import logging
import subprocess

import pymysql
import pymysql.cursors

ctypes = {'dict': pymysql.cursors.DictCursor,
          'ss': pymysql.cursors.SSCursor,
          'ssdict': pymysql.cursors.SSDictCursor,
          'default': pymysql.cursors.Cursor
          }

def connect(server, database, config_file):
    '''
    Connect to a database server.

    :param server: the hostname of the server
    :type server: str

    :param database: the name of the database to use
    :type database: str

    :param config_file: path to the MySQL configuration file to use
                       (os.path.expanduser() is called on this path)
    :type config_file: str
    '''
    db_conn = None
    try:
        db_conn = pymysql.connect(db=database,
                                  host=server,
                                  read_default_file=os.path.expanduser(
                                      config_file),
                                  charset='utf8mb4')
    except pymysql.Error as e:
        logging.error('unable to connect to database')
        logging.error('{} : {}'.format(e[0], e[1]))

    return(db_conn)

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

def disconnect(connection):
    '''Close our database connections.'''
    try:
        connection.close()
    except:
        pass
    return()

def execute_sql(sql_file, host, database, config_file, output_file=None):
    '''
    Fork out a shell to execute the given file with SQL statements
    after connecting to the given host and database, using the
    configuration file for authentication, with optional output
    to a given file.

    :param sql_file: path to the SQL file to execute
    :type sql_file: str

    :param host: hostname of the database server
    :type host: str

    :param database: name of the database we connect to
    :type database: str

    :param config_file: configuration file to use for authentication and options
    :type config_file: str

    :param output_file: path to an output file
    :type output_file: str
    '''

    command = 'mysql --defaults-file={} -h {} -D {} < {}'.format(
        config_file, host, database, sql_file)
    if output_file:
        command = '{} > {}'.format(command, output_file)
    
    logging.info('`executing {}`'.format(command))
    retcode = None
    try:
        retcode = subprocess.call(command, shell=True)
        if retcode < 0:
            logging.error("child was terminated by signal {}".format(-retcode))
        else:
            logging.info("child returned {}".format(retcode))
    except OSError as e:
        logging.error("SQL file execution failed: {}".format(e))
    return(retcode)
