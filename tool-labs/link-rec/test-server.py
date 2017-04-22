#!/usr/bin/python
# -*- coding: utf-8  -*-

import json;
import urllib2, urllib, httplib;
import sys;

url = "http://tools.wmflabs.org/suggestbot/link-recommender.py"

items_json = {u'Association football': 1,
              u'The Seems': 1,
              u'Ghost Whisperer (season 4)': 1,
              u'List of cats in the Tribe of Rushing Water': 1,
              u'Sunrise (Warriors)': 1,
              u'Indian cuisine': 1,
              u'Thalia Grace': 1,
              u'Victoria Holmes': 1,
              u'Harry Potter and the Deathly Hallows': 1,
              u'Dav Pilkey': 1,
              u'The Lightning Thief': 1,
              u'Starlight (Warriors)': 1,
              u'List of ShadowClan cats': 1,
              u'Long Shadows (Warriors)': 1,
              u'List of Percy Jackson and the Olympians terms': 1,
              u'Skender Vakuf City': 1,
              u'Moonrise (Warriors)': 1,
              u'Discovery Channel': 1,
              u'Violin': 1,
              u'Rachel Elizabeth Dare': 1,
              u'Percy Jackson': 1,
              u'List of Ghost Whisperer episodes': 1,
              u"Firestar's Quest": 1,
              u'Flora of A Series of Unfortunate Events': 1,
              u'Eyeshield 21': 1,
              u"Bluestar's Prophecy": 1,
              u'Kate Cary': 1,
              u'Forest of Secrets': 1,
              u'Grover Underwood': 1,
              u'Eragon': 1,
              u'The Shining (novel)': 1,
              u'Sunset (Warriors)': 1,
              u'Rising Storm (Warriors)': 1,
              u'Nico di Angelo': 1,
              u'The Sight (Warriors)': 1,
              u'Erin Hunter': 1,
              u"Ranger's Apprentice": 1,
              u'Neo (The Matrix)': 1,
              u'List of WindClan cats': 1,
              u'Luke Castellan': 1,
              u'The Battle of the Labyrinth': 1,
              u'2012 in fiction': 1,
              u'The Maze of Bones': 1,
              u'Outcast (Warriors)': 1,
              u'The Fourth Apprentice (Warriors)': 1,
              u'Cherith Baldry': 1,
              u'List of Percy Jackson and the Olympians characters': 1,
              u'The Demigod Files': 1,
              u'The Illuminatus! Trilogy': 1,
              u'List of Warriors characters outside Clans': 1,
              u'Fading Echoes (Warriors)': 1,
              u'Poreotics': 1,
              u'List of ThunderClan cats': 1,
              u'Annabeth Chase (Percy Jackson)': 1,
              u'Warriors (novel series)': 1,
              u'Dawn (Warriors)': 1,
              u'Bath City F.C.': 1,
              u'The Last Olympian': 1,
              u'List of SkyClan cats': 1};

# items_json = {"The Seems":1,"Ghost Whisperer (season 4)":1,"Indian cuisine":1,"Sunrise (Warriors)":1,"List of cats in the Tribe of Rushing Water":1,"Thalia Grace":1,"Victoria Holmes":1,"Dav Pilkey":1,"The Lightning Thief":1,"Starlight (Warriors)":1,"Long Shadows (Warriors)":1,"List of Percy Jackson and the Olympians terms":1,"Skender Vakuf City":1,"Moonrise (Warriors)":1,"Violin":1,"Firestar's Quest":1,"Bluestar's Prophecy":1,"The Shining (novel)":1,"Sunset (Warriors)":1,"Nico di Angelo":1,"The Sight (Warriors)":1,"Ranger's Apprentice":1,"Luke Castellan":1,"Outcast (Warriors)":1,"2012 in fiction":1,"The Fourth Apprentice (Warriors)":1,"The Demigod Files":1,"List of Warriors characters outside Clans":1,"Fading Echoes (Warriors)":1,"Poreotics":1,"List of ThunderClan cats":1,"Warriors (novel series)":1,"Dawn (Warriors)":1,"Bath City F.C.":1,"List of SkyClan cats":1,"The Last Olympian":1}
testLang = u'en'

# Some Norwegian articles
# items_json = {u"Henrik Ibsen":1, u"Oslo":1, u"Afrika":1};
# testLang = u'no'

# Some Swedish articles
# items_json = {u"Kingsburg, Kalifornien":1, u"Fidias":1,
#               u"Micke Dubois":1, u"HMS Grundsund (15)":1};
# testLang = u'sv'

# items_json = {u"Findus":1,u"Findus":1,u"Åhléns":1,u"Folkets Hus och Parker":1,u"Mustang (spårvagn)":1,u"Bräckelinjen":1,u"Lundby landskommun":1,u"Lundby landskommun":1,u"Lundby socken, Västergötland":1,u"Hisingsbron":1,u"Klippan, Göteborg":1,u"Hisingsbron":1,u"Ryttarens torvströfabrik":1,u"Rydals museum":1,u"Samuel Owen":1,u"Per Murén":1,u"William Lindberg":1,u"Robert Almström":1,u"David Otto Francke":1,u"William Chalmers":1,u"Alexander Keiller":1,u"Sven Erikson":1,u"Rydahls Manufaktur":1,u"Rydals Manufaktur":1,u"Rydals museum":1,u"Rydals museum":1,u"Rydals museum":1,u"Freedom Flotilla":1,u"Generalmönsterrulla":1,u"Generalmönstring":1,u"Julia Cæsar":1,u"Buskteater":1,u"Buskis":1,u"Persontåg":1,u"Mustang (spårvagn)":1,u"Mustang (spårvagn)":1,u"Mustang (spårvagn)":1,u"Mustang (spårvagn)":1,u"Mustang (spårvagn)":1,u"Lia Schubert-van der Bergen":1,u"Johanna von Lantingshausen":1,u"Gustav Gustavsson av Wasa":1,u"Fredrika av Baden":1,u"Ulrika Eleonora von Berchner":1,u"Ulla von Höpken":1,u"Stig T. Karlsson":1,u"Tony Adams":1,u"Zofia Potocka":1,u"Lena Möller":1,u"Lena Möller":1,u"Novak Đoković":1,u"Historiska kartor över Stockholm":1,u"Afrikanska barbetter":1,u"Aldosteron":1,u"Cyklooxygenas":1,u"Isoenzym":1,u"Proenzym":1,u"Strix (släkte)":1,u"Simsnäppor":1,u"Salskrake":1,u"Jim Dine":1,u"Fostervatten":1,u"Svensk arkitektur":1,u"Kuba":1,u"Rune Gustafsson":1,u"Föreningen för Stockholms fasta försvar":1,u"Carl Johan Billmark":1,u"Carl Johan Billmark":1,u"Alfred Rudolf Lundgren":1,u"Alfred Bentzer":1,u"Svenska Brukarföreningen":1,u"Karl August Nicander":1,};
# testLang = u'sv'

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

#items_json = {
#    u'Гонконг': 1,
#    u'Китайская Народная Республика': 1,
#    u'Ли, Брюс': 1,
#    u'Международный коммерческий центр': 1,
#    u'Международный финансовый центр': 1
#}
#testLang = u'ru'

params = {'lang': testLang,
          'nrecs': 2500};

querydata = {'items': json.dumps(items_json),
             'params': json.dumps(params)};

encoded_data = urllib.urlencode(querydata);

try:
    print "Making request...";
    response = urllib2.urlopen(url, encoded_data);
except httplib.HTTPException as e:
    print 'HTTPException occurred', e;
    sys.exit();

print "Decoding data...";
jsondata = u"";
for line in response.readlines():
    line = unicode(line, 'utf-8', errors='strict');
    jsondata = u"{data}{newline}".format(data=jsondata, newline=line);

# print "DEBUG: jsondata = ", jsondata;
try:
    decoded_data = json.loads(jsondata);
except:
    print "ERROR: failed to load JSON data:";
    print jsondata;
    exit;

itemlist = decoded_data['success'];

print "%d items returned" % (len(itemlist),);
for pageData in itemlist[:10]:
    print pageData['item'].encode('utf-8');
