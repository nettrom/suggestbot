#!/usr/env/python
# -*- coding: utf-8  -*-
'''
Program to handle posting of suggestions to users.

Copyright (C) 2016 SuggestBot Dev Group

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

__version__ = "$Id$";

import sys
import codecs
import re
import logging

from suggestbot import SuggestBot, config

def main():
    # Parse CLI options
    import argparse
    cli_parser = argparse.ArgumentParser(
        description="Program to post suggestions to users."
        )

    # Language (if set, overrides setting in configuration)
    cli_parser.add_argument("lang",
                            help="post to this specific language version of Wikipedia")

    # Also possible to specify users directly:
    cli_parser.add_argument("users",
                            help="comma-separated list of usernames wanting recommendations")
    
    # Option to specify the address of the template used for substitution.
    cli_parser.add_argument("-a", "--template",
                            default=None,
                            help="name of template subst'ed for recommendations")
    cli_parser.add_argument("-b", "--bypasspage",
                            default=None,
                            help="skip posting to a user's talk page, post to this page instead (WARNING: only use when recommending to a single user, and post to a page in the given user's userspace)")

    # Delay between subsequent recommendation posts
    cli_parser.add_argument("-d", "--delay", dest="delay",
                            type=int, default=10,
                            help="delay in seconds between subsequent rec posts")

    # Replace an existing recommendation with the new, or simply append?
    cli_parser.add_argument("-r", "--replace",
                            action="store_true",
                            help="Replace rec message instead of appending (if present)")

    # Option to force posting of recommendations even though a user has {{nobots}}
    # or a similar template to prevent posting to their user talk page.
    cli_parser.add_argument("-f", "--force",
                            action="store_true",
                            help="Force posting (ignores {{bots}} and {{nobots}} templates), use with caution (e.g. only for handling requests).")

    # Option to control which user group the user belongs to
    cli_parser.add_argument("-g", "--group",
                            type=str, default=None,
                            help='name of the (experiment) group the user is in')


    # Maximum number of retries before abandoning posting a recommendation
    cli_parser.add_argument("-m", "--retries",
                            type=int, default=3,
                            help="number of retries before abandoning posting a rec")

    # Number of recommendations to use in rec template
    cli_parser.add_argument("-n", "--nrecs",
                            type=int, default=3,
                            help="number of recommendations to use")

    # Recommendation server port number
    cli_parser.add_argument("-p", "--port",
                            type=int, default=10010,
                            help="what port to connect to the recommendation server")

    # Test runs will not actually post to user pages, but instead print to STDOUT
    cli_parser.add_argument("-t", "--test",
                            action="store_true",
                            help="test runs don't post changes to Wikis, prints to stdout instead.")


    # Be verbose?
    cli_parser.add_argument("-v", "--verbose",
                            action="store_true",
                            help="I can has kittehtalkzalot?")

    args = cli_parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    try:
        myBot = SuggestBot(recPort=args.port, nRecs=args.nrecs,
                           postDelay=args.delay, maxRetries=args.retries,
                           testRun=args.test,
                           lang=args.lang)
        myBot.login()
        if not myBot.isLoggedIn():
            logging.error("Failed to log in, exiting.")
            return()

        usernames = args.users.split(",")
        groupname = u'sugg';
        if args.group:
            groupname = args.group

        # For each user supplied, try to do some recommendations
        for user in usernames:
            # recommend to this user
            status = myBot.recommend(user,
                                     userGroup=groupname,
                                     recTemplate=args.template,
                                     force=args.force,
                                     page=args.bypasspage,
                                     replace=args.replace)
            if status:
                print("Successfully posted recommendations to %s" % (user['username'],))
    finally:
        myBot.stopme()

if __name__ == "__main__":
    main()
