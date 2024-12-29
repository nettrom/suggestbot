#!/usr/env/python
# -*- coding: utf-8  -*-
'''
Test the links-based recommender.
'''

import logging

from suggestbot import config

import xmlrpc.client

def main():
    test_lang = 'en'
    test_user = 'Nettrom'
    test_nrecs = 500

    test_edits = {
        'Association football': 1,
        'The Seems': 1,
        'Ghost Whisperer (season 4)': 1,
        'List of cats in the Tribe of Rushing Water': 1,
        'Sunrise (Warriors)': 1,
        'Indian cuisine': 1,
        'Thalia Grace': 1,
        'Victoria Holmes': 1,
        'Harry Potter and the Deathly Hallows': 1,
        'Dav Pilkey': 1,
        'The Lightning Thief': 1,
        'Starlight (Warriors)': 1,
        'List of ShadowClan cats': 1,
        'Long Shadows (Warriors)': 1,
        'List of Percy Jackson and the Olympians terms': 1,
        'Skender Vakuf City': 1,
        'Moonrise (Warriors)': 1,
        'Discovery Channel': 1,
        'Violin': 1,
        'Rachel Elizabeth Dare': 1,
        'Percy Jackson': 1,
        'List of Ghost Whisperer episodes': 1,
        "Firestar's Quest": 1,
        'Flora of A Series of Unfortunate Events': 1,
        'Eyeshield 21': 1,
        "Bluestar's Prophecy": 1,
        'Kate Cary': 1,
        'Forest of Secrets': 1,
        'Grover Underwood': 1,
        'Eragon': 1,
        'The Shining (novel)': 1,
        'Sunset (Warriors)': 1,
        'Rising Storm (Warriors)': 1,
        'Nico di Angelo': 1,
        'The Sight (Warriors)': 1,
        'Erin Hunter': 1,
        "Ranger's Apprentice": 1,
        'Neo (The Matrix)': 1,
        'List of WindClan cats': 1,
        'Luke Castellan': 1,
        'The Battle of the Labyrinth': 1,
        '2012 in fiction': 1,
        'The Maze of Bones': 1,
        'Outcast (Warriors)': 1,
        'The Fourth Apprentice (Warriors)': 1,
        'Cherith Baldry': 1,
        'List of Percy Jackson and the Olympians characters': 1,
        'The Demigod Files': 1,
        'The Illuminatus! Trilogy': 1,
        'List of Warriors characters outside Clans': 1,
        'Fading Echoes (Warriors)': 1,
        'Poreotics': 1,
        'List of ThunderClan cats': 1,
        'Annabeth Chase (Percy Jackson)': 1,
        'Warriors (novel series)': 1,
        'Dawn (Warriors)': 1,
        'Bath City F.C.': 1,
        'The Last Olympian': 1,
        'List of SkyClan cats': 1
    }

    # items_json = {"The Seems":1,"Ghost Whisperer (season 4)":1,"Indian cuisine":1,"Sunrise (Warriors)":1,"List of cats in the Tribe of Rushing Water":1,"Thalia Grace":1,"Victoria Holmes":1,"Dav Pilkey":1,"The Lightning Thief":1,"Starlight (Warriors)":1,"Long Shadows (Warriors)":1,"List of Percy Jackson and the Olympians terms":1,"Skender Vakuf City":1,"Moonrise (Warriors)":1,"Violin":1,"Firestar's Quest":1,"Bluestar's Prophecy":1,"The Shining (novel)":1,"Sunset (Warriors)":1,"Nico di Angelo":1,"The Sight (Warriors)":1,"Ranger's Apprentice":1,"Luke Castellan":1,"Outcast (Warriors)":1,"2012 in fiction":1,"The Fourth Apprentice (Warriors)":1,"The Demigod Files":1,"List of Warriors characters outside Clans":1,"Fading Echoes (Warriors)":1,"Poreotics":1,"List of ThunderClan cats":1,"Warriors (novel series)":1,"Dawn (Warriors)":1,"Bath City F.C.":1,"List of SkyClan cats":1,"The Last Olympian":1}
    #testLang = u'en'

    # Some Norwegian articles
    test_edits = {"Henrik Ibsen":1, "Oslo":1, "Afrika":1}
    test_lang = 'no'

    # Some Swedish articles
    test_edits = {
        "Kingsburg, Kalifornien":1,
        "Fidias":1,
        "Micke Dubois":1,
        "HMS Grundsund (15)":1
    }
    test_lang = 'sv'

    # items_json = {
    #     u"باشگاه فوتبال بوکا جونیورز": 1,
    #     u"فوتبال": 1,
    #     u"زبان اسپانیایی": 1,
    #     u"آرژانتین": 1};
    # testLang = u"fa";

    # items_json = {
    #     u"Luis Hernández": 1,
    #     u"Mexikói labdarúgó-válogatott": 1,
    #     u"Labdarúgó": 1,
    #     u"CA Boca Juniors": 1,
    #     u"CF Monterrey": 1
    #     }
    # testLang = u"hu";

    # test_edits = {
    #     'Гонконг': 1,
    #     'Китайская Народная Республика': 1,
    #     'Ли, Брюс': 1,
    #     'Международный коммерческий центр': 1,
    #     'Международный финансовый центр': 1
    # }
    # test_lang = 'ru'

    print("Making request...")
    
    sp = xmlrpc.client.ServerProxy("http://{hostname}:{port}".format(
        hostname=config.links_hostname, port=config.links_hostport))
    try:
        recs = sp.recommend(test_user,
                            test_lang,
                            test_edits,
                            2500)
        print("Got {} recommendations back".format(len(recs)))
        for i in range(50):
            print(recs[i])
    except xmlrpc.client.Error as e:
        logging.error('Getting edits for {0}:User:{1} failed'.format(
            test_lang, test_user))
        logging.error(e)
    return()

if __name__ == "__main__":
    main()
