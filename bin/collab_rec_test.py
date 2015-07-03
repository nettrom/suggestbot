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

import re
import random
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

        cli_parser.add_argument('member_file', type=str,
                                help='path to member file')

        # cli_parser.add_argument('k', type=int,
        #                     help='size of random sample to draw')

        cli_parser.add_argument('nrecs', type=int,
                                help='number of recommendations per user')

        cli_parser.add_argument('test', type=str,
                                help='type of test to return recommendations from')
        
        args = cli_parser.parse_args()
        
        if args.verbose:
                logging.basicConfig(level=logging.DEBUG)

        # Regular expression to match a member username in our membership file
        member_re = re.compile('User talk[:](?P<username>[^\}]+)')

        all_members = set()

        with open(args.member_file, 'r') as infile:
                for line in infile:
                        match_obj = member_re.search(line.strip())
                        if match_obj is None:
                                print("None object")
                        else:
                               all_members.add(match_obj.group('username'))

        # members = random.sample(all_members, args.k)
        if args.test == 'coedit':
                recommender = CollabRecommender(assoc_threshold=0)
        else:
                recommender = CollabRecommender()
                
        site = pywikibot.Site('en') 
               
        print("Beginning collaborator recommendation test")

        total_recs = 0
        total_overlap = 0

        members = ['Slatersteven', 'WerWil', 'Fnlayson', 'Drrcs15', 'Turbothy',
                   '21stCenturyGreenstuff', 'RGFI', 'Loesorion', 'Grahamdubya', 'Sioraf',
                   'Skittles the hog', 'Smoth 007', 'Superfly94', 'Ewulp', 'Dank', 'Magus732',
                   'Redmarkviolinist', 'The27thMaine', 'Kcdlp', 'Foxsch', 'Tdrss', 'URTh',
                   'Waase', 'L clausewitz', 'Judgedtwice', 'Choy4311', 'Codrinb', 'Smmurphy',
                   'Kliu1', 'Gowallabies', 'Secutor7', 'Moneywagon', 'Nostalgia of Iran',
                   'Linmhall', 'Karanacs', 'Dana boomer', 'Robotam', 'Fdsdh1', 'DanieB52',
                   'Rosiestep', 'Scholarus', 'Laurinavicius', 'Dapi89', 'UrbanTerrorist',
                   'AGK', 'Samuel Peoples', 'Sapphire', 'Catlemur', 'Martocticvs', 'Gparkes',
                   'Pratyya Ghosh', 'Eurocopter', 'Pahari Sahib', 'Seitzd', 'The Bushranger',
                   'Natobxl', 'MasterOfHisOwnDomain', 'Takashi kurita', 'TeunSpaans',
                   'Kierzek', 'WDGraham', 'Miborovsky', 'The lost library',
                   'Antidiskriminator', 'The ed17', 'Cliftonian', 'AshLin',
                   'GeneralizationsAreBad', 'MechaChrist', 'Joep01', 'Chris.w.braun',
                   'TBrandley', 'Marky48', 'Cplakidas', 'John', 'Nyth83', 'Elonka',
                   'Alexandru.demian', 'Martinp23', 'GermanJoe', 'P.Marlow', 'ryan.opel',
                   'Asarelah', 'Ian Rose', 'Pectory', 'KizzyB', 'MrDolomite', 'Leifern',
                   'Timeweaver', 'Ashashyou', 'Sumsum2010', 'Looper5920', 'Geira', 'Ackpriss',
                   'Binksternet', 'Lothar von Richthofen', 'Molestash', 'Srnec',
                   'Sasuke Sarutobi', '.marc.']

        # members = ['Kieran4', 'Brendandh', 'Gog the Mild', 'Seitzd', 'Robotam',
        #            'Keith-264', 'Nyth83', 'Mmuroya', 'Navy2004', 'Secutor7',
        #            'Ranger Steve', 'MisterBee1966']


        for member in members:
                user = pywikibot.User(site, member)
                contribs = []
                for (page, revid, time, comment) in user.contributions(128,
                                                                       namespaces = [0]):
                        contribs.append(page.title())	

                matches = recommender.recommend(contribs, member, 'en',
                                                nrecs=args.nrecs, backoff=1, test=args.test)

                match_set = set([rec['item'] for rec in matches])
                overlap = match_set & all_members

                total_recs += len(match_set)
                total_overlap += len(overlap)

                print('Got {n} recommendations for User:{user}'.format(n=len(match_set),
                                                                       user=member))
                print('Overlap with all members: {0}'.format(len(overlap)))

        print('''Total statistics:
    Number of recommendations: {n}
    Overlap with all members: {o}
    % overlap: {p:.2}'''.format(n=total_recs, o=total_overlap,
                                p=100*float(total_overlap)/float(total_recs)))
        print('Recommendation test complete')
	
if __name__ == "__main__":
        main()
