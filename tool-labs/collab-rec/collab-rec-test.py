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

from datetime import datetime, timedelta

import db
import MySQLdb

from collaborator import CollabRecommender
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

    cli_parser.add_argument('output_file', type=str,
                            help='path to output file (for appending, must exist!)')
    
    cli_parser.add_argument('nrecs', type=int,
                            help='number of recommendations per user')
    
    cli_parser.add_argument('test', type=str,
                            help='type of similary test to base recommendations on (jaccard, cosine, or coedit)')

    cli_parser.add_argument('cutoff', type=int,
                            help='the number of 30-day months to use when fetching revisions')

    cli_parser.add_argument('namespaces', type=str,
                            help='comma-separated list of namespaces to base the similarity on')
    
    args = cli_parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)

    # Regular expression to match a member username in our membership file
    member_re = re.compile('User talk[:](?P<username>[^\}]+)')

    all_members = set()
    
    with open(args.member_file, 'r', encoding='utf-8') as infile:
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

    # members = ['XavierItzm']

    # Store namespaces as a list of str
    namespaces_list = args.namespaces.split(',')
    
    get_contribs_query = '''SELECT rev_id, page_id
    FROM page JOIN revision_userindex
    ON page_id=rev_page
    WHERE page_namespace IN ({namespaces})
    AND rev_minor_edit=0
    AND rev_deleted=0
    AND rev_user_text=%(username)s
    ORDER BY rev_id DESC
    LIMIT %(k)s
    '''.format(namespaces=",".join(namespaces_list))

    ## Set number of recommendations to 50 for now,
    ## which allows us to calculate overlap for 10,20,30,40, and 50 recs
    nrecs = 50

    ## Measuring total number of recommendations and overlap per size of
    ## recommendations requested.
    total_recs = {10: 0, 20: 0, 30: 0, 40: 0, 50: 0}
    total_overlap = {10: 0, 20: 0, 30: 0, 40: 0, 50: 0}
    
    for member in members:
    
        contribs = set()

        try:
            ## Note: connecting and disconnecting to prevent the DB
            ## from disconnecting us due to inactivity
            (dbconn, dbcursor) = db.connect(dbhost='c3.labsdb')

            ## Asking for 500 contributions per namespace, just in case.
            dbcursor.execute(get_contribs_query,
                             {'username': member,
                              'k': 500*len(namespaces_list)})
            for row in dbcursor.fetchall():
                try:
                    contribs.add(row['page_id'])
                    if len(contribs) == 128:
                        break
                except AttributeError:
                    continue
            db.disconnect(dbconn, dbcursor)
        except MySQLdb.Error as e:
            logging.error("unable to execute query to get users by article")
            logging.error("Error {0}: {1}".format(e.args[0], e.args[1]))
            return(False)

        # Calculate the cutoff date
        cutoff = datetime.now() - timedelta(days=args.cutoff*30)
        matches = recommender.recommend(contribs, member, 'en', cutoff,
                                        namespaces=namespaces_list,
                                        nrecs=nrecs, backoff=1, test=args.test)
        for k in range(10, 60, 10):
            match_set = set([rec['item'] for rec in matches[:k]])
            overlap = match_set & all_members
        
            total_recs[k] += len(match_set)
            total_overlap[k] += len(overlap)

            print('Requested {k}, got {n} recommendations for User:{user}'.format(
                k=k, n=len(match_set), user=member))
            print('Overlap with all members: {0}'.format(len(overlap)))
       
        #for i in range(0, len(match_set)):
        #    print(match_set.pop())

    # Print stats to stdout, and append stats to output file
    for k in range(10, 60, 10):
        print('''Total statistics:
        Number of requested recs per user: {k}
        Number of recommendations: {n}
        Overlap with all members: {o}
        % overlap: {p:.2}'''.format(k=k, n=total_recs[k], o=total_overlap[k],
                                    p=100*float(total_overlap[k])/float(total_recs[k])))

        with open(args.output_file, 'a') as outfile:
            outfile.write('{n}\t{t}\t{nrecs}\t{ns}\t{int_n}\t{int_p:.2}\n'.format(
                n=k, t=args.cutoff, nrecs=total_recs[k], int_n=total_overlap[k],
                ns=",".join(namespaces_list),
                int_p=100*float(total_overlap[k])/float(total_recs[k])))

    print('Recommendation test complete')
    
if __name__ == "__main__":
    main()
