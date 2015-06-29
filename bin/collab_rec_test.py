#!/usr/env/python
# -*- coding: utf-8 -*-
'''
Script to test the collaborator recommender.

Copyright (C) 2015 SuggestBot Dev Group

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

import logging

from suggestbot.recommenders.collaborator import CollabRecommender
import pywikibot

def main():
        # Parse CLI options
        import argparse
        
        cli_parser = argparse.ArgumentParser(
                description="Code for testing the collaborator recommender"
        )
        
        # Add verbosity option
        cli_parser.add_argument('-v', '--verbose', action='store_true',
                                help='I can has kittehtalkzalot?')
        
        args = cli_parser.parse_args()
        
        if args.verbose:
                logging.basicConfig(level=logging.DEBUG)

        recommender = CollabRecommender()
                
        print("Beginning collaborator recommendation test")

        members = ['Kieran4', 'Brendandh', 'Gog the Mild', 'Seitzd', 'Robotam',
                   'Keith-264', 'Nyth83', 'Mmuroya', 'Navy2004', 'Secutor7',
                   'Ranger Steve', 'MisterBee1966']
        site = pywikibot.Site('en') 

        for member in members:
                user = pywikibot.User(site, member)
                contribs = []
                for (page, revid, time, comment) in user.contributions(128,
                                                                       namespaces = [0]):
                        contribs.append(page.title())	

                matches = recommender.recommend(contribs, member, 'en',
                                                nrecs=10, backoff = 1)

                print("Recommendations for User:{0}".format(member))
                for rec in matches:
                        print("User:{0} score={1:.3}".format(rec['item'],
                                                             rec['value']))
        print('Recommendation test complete')
	
if __name__ == "__main__":
        main()
