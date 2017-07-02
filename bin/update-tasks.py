#!/usr/bin/env python
# -*- coding: utf-8  -*-
"""
Script to update the database with articles in specific task categories.

Copyright (C) 2005-2017 SuggestBot Dev Group

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
"""

import argparse
import logging

from suggestbot.utilities.tasks import TaskUpdater

def main():
    # Parse CLI options
    cli_parser = argparse.ArgumentParser(
        description="Script to update the task database for a given language"
        )

    # Add verbosity option
    cli_parser.add_argument('-v', '--verbose', action='store_true',
                            help='be verbose')
    
    # Add required language parameter
    cli_parser.add_argument('lang',
                            help='language code of the Wikipedia we are processing')

    args = cli_parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    updater = TaskUpdater(args.lang)
    updater.update_database()
    return()

if __name__ == "__main__":
    main()
