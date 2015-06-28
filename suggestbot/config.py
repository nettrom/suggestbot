#!/soft/python-2.6/bin/python
# -*- coding: utf-8 -*-
'''
SuggestBot configuration library.

If you add specific variables to this file, make sure you also
add an explanation of what they're for.

Copyright (C) 2005-2015 SuggestBot Dev Group

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

# $Id$

from __future__ import with_statement

# Dictionary to translate a language code to a descriptive language name
lang_codes={
    'en': 'english',
    'no': 'norwegian',
    'sv': 'swedish',
    'pt': 'portuguese',
    'fa': 'persian',
    'h': 'hungarian',
    'r': 'russian',
}

# Edit comments used when posting recommendations
edit_comment = {
    'en': "SuggestBot recommends these articles...",
    'no': "AnbefalingsBot anbefaler disse artiklene...",
    'sv': "FörslagsBot rekommenderar dessa artiklar...",
    'pt': "SuggestBot recomenda estes artigos",
    'fa': 'SuggestBot recommends these articles...',
    'h': 'SuggestBot recommends these articles...',
    'r': 'SuggestBot предлагает следующие статьи...',
}

# Edit comments used when removing the request template
# from a user page
replace_comment = {
    'en': "Removed SuggestBot request template to prevent multiple suggestions posts",
    'no': "Fjernet mal for engangsanbefalinger så anbefalinger ikke sendes flere ganger",
    'sv': "Tar bort FörslagsBots mall så förslag inte skickas fler gånger",
    'pt': "Modelo de pedido de SuggestBot removido para evitar postagens múltiplas",
    'fa': 'Removed SuggestBot request template to prevent multiple suggestions posts',
    'h': 'Removed SuggestBot request template to prevent multiple suggestions posts',
    'r': 'Удаление шаблона запроса к SuggestBot для предотвращения дублирования сообщений'
}

# Table names for database tables containing task categories
# and articles found in those categories
task_table = {
    'en': 'enwiki_work_category_data',
    'no': 'nowiki_work_category_data',
    'sv': 'svwiki_work_category_data',
    'pt': 'ptwiki_work_category_data',
    'fa': 'fawiki_work_category_data',
    'h': 'huwiki_work_category_data',
    'r': 'ruwiki_work_category_data'
}

# Configuration of categories containing articles that need work.
# update-data.py iterates over the keys in the dictionary and uses
# the various values to gather article titles.  We are doing a mapping
# from our work category names (e.g. "STUB"), to a set of categories
# that we will gather articles from, either by grabbing them directly,
# or by traversing the category tree.

# The format of the task dictionary is as follows:
# Keys: Our over-arching work category name (e.g. STUB)
# Values: A dictionary containing configuration for each work category,
#         the dictionary contains four key-value pairs as follows:
#     'categories': List of categories that we will directly
#                   gather article titles from.
#     'recurseCategories': Dictionary where the keys are category
#                          names, and the values are integers.
#                          We will traverse down sub-categories
#                          to the level defined by the integer.
#                          Thus a value of 1 will only look down one sub-level.
#     'inclusion': A string containing a regular expression we will use
#                  for inclusion.  Category names that do _not_ match
#                  this regex are ignored.
#     'exclusion': A string containing a regular expression we will use
#                  for exclusion.  Category names that _match_ this regex
#                  are ignored.

# Regular expressions used to match category names of stub categories
# so we disregard non-stub categories when traversing the category graph.
stub_re = {
    "en": r"\b[Ss]tub", # English
    "no": r"[Ss]tubb", # Norwegian
    "sv": r"[Ss]tubb", # Swedish
    "pt": r"!Esboços (sobre|por|maiores que)", # Portuguese
    'fa': r'مقاله‌های خرد',
    'h': None,
    'r': r"Незавершённые статьи",
}

tasks = {
    'en': {
        'MERGE': {
            'categories': ['All articles to be merged',
                           'Articles to be merged'],
            'recurseCategories': {'Merge by month': 1},
            'inclusion': None,
            'exclusion': stub_re['en'] },
        'WIKIFY': {
            'categories': ['All articles covered by WikiProject Wikify'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None},
        'CLEANUP': {
            'categories': ['All pages needing cleanup',
                           'Articles with excessive see also sections',
                           'Wikipedia introduction cleanup'
                           "All articles needing copy edit"],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'SOURCE': {
            'categories': ['All articles lacking reliable references',
                           'All articles needing additional references',
                           'All articles lacking sources',
                           'All articles with topics of unclear notability',
                       ],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'EXPAND': {
            'categories': ['All articles to be expanded',
                           "All Wikipedia articles in need of updating"],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'STUB': {
            'categories': [],
            'recurseCategories': {'Stub_categories': 5},
            'inclusion': stub_re['en'],
            'exclusion': None, },
        'ORPHAN': {
            'categories': ['All orphaned articles'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'UNENC': { # unencyclopædic articles
            'categories': ['All NPOV disputes',
                           'All articles that may contain original research'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
    },
    'pt': {
        'STUB': {
            'categories': ["!Artigos mínimos", ],
            'recurseCategories': {"!Esboços": 5},
            'inclusion': stub_re['pt'],
            'exclusion': None,
        },
        'TRANSLATE': {
            'categories': [],
            'recurseCategories': {"!Artigos em tradução": 5},
            'inclusion': None,
            'exclusion': stub_re['pt'],
        },
        'SOURCE': {
            'categories': ["!Artigos com referências não fiáveis",
                           "!Artigos com citações quebradas"],
            'recurseCategories': {"!Artigos que carecem de fontes": 5,
                                  "!Artigos que carecem de fontes secundárias": 5,
                                  "!Artigos que necessitam de verificação factual": 5},
            'inclusion': None,
            'exclusion': stub_re['pt'],
        },
        'MERGE': {
            'categories': [],
            'recurseCategories': {"!Artigos a sofrerem fusão": 5},
            'inclusion': r"(!Artigos a sofrerem)|(!Artigos de .* a sofrerem)",
            'exclusion': stub_re['pt'],
        },
        'CLEANUP': {
            'categories': [],
            'recurseCategories': {"!Páginas a reciclar": 3,
                                  "!Artigos que necessitam de esclarecimento": 2},
            'inclusion': None,
            'exclusion': stub_re['pt'],
        },
        'UPDATE': {
            'categories': [],
            'recurseCategories': {"!Artigos com dados desatualizados": 3,
                                  "!Artigos contendo afirmações potencialmente datadas": 3,
                                  "!Artigos a expandir": 3,
                                  "!Artigos parciais": 3},
            'inclusion': None,
            'exclusion': stub_re['pt'],
        },
        'IMAGES': {
            'categories': [],
            'recurseCategories': {"!Artigos sem imagens": 5},
            'inclusion': None,
            'exclusion': stub_re['pt'],
        },
    },
    'no': {
        'KILDER': {
            # Note: As of 2013-11-11, there's only four source-related
            # categories on Norwegian Wikipedia.  We choose to recurse
            # rather than list them in case they change their category
            # structure in the future.
            'categories': [],
            'recurseCategories': {'Artikler som trenger referanser': 3},
            'inclusion': None,
            'exclusion': stub_re['no'],
        },
        'FLETT': {
            "categories": ['Artikler_som_bør_flettes'],
            "recurseCategories": {},
            "inclusion": None,
            "exclusion": stub_re['no'],
        },
        'OPPRYDNING': {
            "categories": [],
            "recurseCategories": {'Opprydning': 1},
            "inclusion": None,
            "exclusion": stub_re['no'],
        },
        'OBJEKTIV': {
            "categories": ['Objektivitet', 'Nøyaktighet',
                           'Uencyklopediske_artikler'],
            "recurseCategories": {},
            "inclusion": None,
            "exclusion": stub_re['no'],
        },
        'UFULLSTENDIG': {
            "categories": ['Ufullstendige_lister'],
            "recurseCategories": {},
            "inclusion": None,
            "exclusion": stub_re['no'],
        },
        'UTVID': {
            "categories": ['Snevre_artikler', 'Sider som må utvides'],
            "recurseCategories": {},
            "inclusion": None,
            "exclusion": stub_re['no'],
        },
    'STUBBER': {
        "categories": [],
        "recurseCategories": {
            'Stubber etter størrelse': 2,
        'Stubber': 5},
        "inclusion": stub_re['no'],
        "exclusion": None,
    },
        'VSTUBB': {
            "categories": ['Viktige stubber'],
            "recurseCategories": {},
            "inclusion": None,
        "exclusion": None,
        },
    },
    'sv': {
        'INFOGA': {
            'categories': ['Samtliga artiklar föreslagna för sammanslagningar och delningar',],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
    },
        'WIKIFIERA': {
            'categories': ['Artiklar som behöver wikifieras-samtliga'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
    'UOPPDATERAD': {
        'categories': ['Ej uppdaterad-samtliga',
                       'Samtliga utgångna bäst före'],
        'recurseCategories': {},
        'inclusion': None,
        'exclusion': None,
    },
        'GLOBALT': {
        'categories': ['Wikipedia:Globalt perspektiv-samtliga', ],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'SPRÅK': {
            'categories': [],
            'recurseCategories': {'Artiklar som behöver språkvård': 2},
            'inclusion': None,
            'exclusion': stub_re['sv'],
        },
    'KÄLLOR': {
        'categories': ['Alla artiklar som behöver källor', ],
        'recurseCategories': {},
        'inclusion': None,
        'exclusion': None,
    },
        'STÄDA': {
            'categories': [],
            'recurseCategories': {'Städa': 2},
            'inclusion': None,
            'exclusion': stub_re['sv'],
        },
        'STUBBAR': {
            'categories': [],
            'recurseCategories': {'Stubbar': 5},
            'inclusion': stub_re['sv'],
            'exclusion': r'(Ofullständiga listor)|mallar',
        },
    },
    'r': {
        'STUB': {
            'categories': [],
            'recurseCategories': {'Незавершённые статьи по темам':5},
            'inclusion': stub_re['r'],
            'exclusion': None,
        },
        'WIKIFY': {
            'categories': ['Википедия:Статьи к викификации'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'SOURCE': {
            'categories': ['Википедия:Статьи с утверждениями без источников'],
            'recurseCategories': {'Википедия:Статьи с утверждениями без источников':1,
                                  'Википедия:Статьи без ссылок на источники': 1},
            'inclusion': None,
            'exclusion': r'Википедия:Статьи с сомнительной значимостью',
        },
        'EXPAND': {
            'categories': ['Википедия:Статьи с незавершёнными разделами'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'ORPHAN': {
            'categories': [],
            'recurseCategories': {'Википедия:Изолированные статьи': 1},
            'inclusion': None,
            'exclusion': stub_re['r'],
        },
        'OBJECTIVITY': {
            'categories': ['Википедия:Статьи, нейтральность которых поставлена под сомнение'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'IMAGES': {
            'categories': ['Википедия:Статьи без иллюстраций'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'CLEANUP': {
            'categories': ['Википедия:Статьи к переработке'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'UPDATE': {
            'categories': ['Википедия:Статьи для обновления'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'TRANSLATE': {
            'categories': [],
            'recurseCategories': {'Википедия:Запросы на перевод': 1},
            'inclusion': None,
            'exclusion': None,
        },
        'RELIABILITY': {
            'categories': ['Википедия:Статьи, достоверность которых требует проверки'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'NOTABILITY': {
            'categories': ['Википедия:Статьи с сомнительной значимостью'],
            'recurseCategories': {'Википедия:Статьи с сомнительной значимостью по давности': 1},
            'inclusion': None,
            'exclusion': None,
        },
    },
    'fa': {
        'STYLE': {
            'categories': ['همه مقاله‌های نیازمند ویرایش سبک'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'EXPAND': {
            'categories': ['مقاله‌های نیازمند گسترش'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'MERGE': {
            'categories': ['صفحه‌های نامزد ادغام'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'OBJECTIVITY': {
            'categories': ['همه اختلاف‌ها در بی‌طرفی'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'ORPHAN': {
            'categories': ['مقاله‌های یتیم'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'STUB': {
            'categories': [],
            'recurseCategories': {'رده‌های خرد':
                                  1},
            'inclusion': stub_re['fa'],
            'exclusion': None,
        },
        'SOURCE': {
            'categories': ['مقاله‌های با منبع ناکافی',
                           'همه مقاله‌های دارای عبارت‌های بدون منبع'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'IMAGES' : {
            'categories': [],
            'recurseCategories' : {'مقاله‌های نیازمند تصویر':
                                   1},
            'inclusion': None,
            'exclusion': None,
        },
        'TRANSLATE': {
            'categories': ['مقاله‌های نیازمند اصلاح ترجمه'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'UPDATE': {
            'categories': ['رده:مقاله‌های نیازمند به روز شدن'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
        'WIKIFY': {
            'categories': ['مقاله‌های نیازمند به ویکی‌سازی'],
            'recurseCategories': {},
            'inclusion': None,
            'exclusion': None,
        },
    }
}


# URL to the Tool Labs webservice used to get quality metadata
# (num. images, num. wikilinks, num. broken wikilinks) for articles
qualws_url = r'http://tools.wmflabs.org/suggestbot/quality_metadata'

# Variables that control how we handle regulars, and store them
# in the suggestbot database.

# Name of the table that holds the list of regulars in the suggestbot database
regulars_table = "regular_users"

# Name of the table that stores logs of recommendations
reclog_table = "recommendation_log"

# Template for the name of the table that stores text index terms
term_table = "{lang}wiki_terms"

# Name of the table that stores articles in need of parsing
parse_queue = "parse_queue"

# The number of days after which we regard a user as retired,
# meaning we stop sending them suggestions.
# FIXME: make this into a relative measure, e.g. after k number of posts,
# depending on how often they get them?
retired_days = 60

# The number of seconds between checks for new suggestion requests
suggest_req_poll = 300

# Tables for storing information about requests
req_logtable = "request_log"
req_seedstable = "request_seeds"
req_recstable = "request_recs"

# The number of seconds we wait between retrieving recent changes
rc_delay = 3600

# Template filename for the recent changes daemon's pickle files
rc_pickle = "../data/recentchanges-updatetitles-{0}.dat"

# Number of days we keep revisions for, for each language
rc_keep = {
    'en': 90,
    'r': 274,
    'sv': 925,
    'pt': 720,
    'no': 1461,
    'fa': 1461,
    'h': 1461
}

# Configuration of text tables used to store data
text_table = {
    'en': 'enwiki_solr_text',
    'sv': 'svwiki_solr_text',
    'no': 'nowiki_solr_text',
    'pt': 'ptwiki_solr_text',
    'fa': 'fawiki_solr_text',
    'h': 'huwiki_solr_text',
    'r': 'ruwiki_solr_text',
}

# Configuration of database tables used to store revision data
# (used by the co-edit recommender)
# NOTE: this duplicates $COEDIT_TABLES in config.pm
revision_table = {
    'en': 'enwiki_revisions',
    'no': 'nowiki_revisions',
    'sv': 'svwiki_revisions',
    'pt': 'ptwiki_revisions',
    'fa': 'fawiki_revisions',
    'r': 'ruwiki_revisions',
    'h': 'huwiki_revisions'
}

# Configuration of URLs to query each language's Solr backend,
# Page ID is substituted in at runtime.
# NOTE: we currently have separate URLs for each language to allow
# tweaking of parameters like minimum term frequency in the source document (mintf),
# minimum document frequency (mindf), and minimum word length (minwl)
solr_baseurl = {
    'en': "http://localhost:8080/solr/English/mlt?q=id:{pageid}&mlt.fl=text&mlt.mindf=2&mlt.mintf=2&fl=id,titleText,score&mlt.match.include=false&rows=1000&mlt.minwl=5&wt=json",
    'no': "http://localhost:8080/solr/Norwegian/mlt?q=id:{pageid}&mlt.fl=text&mlt.mindf=2&mlt.mintf=2&fl=id,titleText,score&mlt.match.include=false&rows=1000&mlt.minwl=5&wt=json",
    'sv': "http://localhost:8080/solr/Swedish/mlt?q=id:{pageid}&mlt.fl=text&mlt.mindf=2&mlt.mintf=2&fl=id,titleText,score&mlt.match.include=false&rows=1000&mlt.minwl=5&wt=json",
    'pt': "http://localhost:8080/solr/Portuguese/mlt?q=id:{pageid}&mlt.fl=text&mlt.mindf=2&mlt.mintf=2&fl=id,titleText,score&mlt.match.include=false&rows=1000&mlt.minwl=5&wt=json",
    'fa': "http://localhost:8080/solr/Persian/mlt?q=id:{pageid}&mlt.fl=text&mlt.mindf=2&mlt.mintf=2&fl=id,titleText,score&mlt.match.include=false&rows=1000&mlt.minwl=5&wt=json",
    'h': "http://localhost:8080/solr/Hungarian/mlt?q=id:{pageid}&mlt.fl=text&mlt.mindf=2&mlt.mintf=2&fl=id,titleText,score&mlt.match.include=false&rows=1000&mlt.minwl=5&wt=json",
    'r': "http://localhost:8080/solr/Russian/mlt?q=id:{pageid}&mlt.fl=text&mlt.mindf=2&mlt.mintf=2&fl=id,titleText,score&mlt.match.include=false&rows=1000&mlt.minwl=5&wt=json",
}

# Mapping language codes to URLs used to delete pages from Solr's
# search index
solr_delurl = {
    'en': 'http://localhost:8080/solr/English/update/json',
    'no': 'http://localhost:8080/solr/Norwegian/update/json',
    'sv': 'http://localhost:8080/solr/Swedish/update/json',
    'pt': 'http://localhost:8080/solr/Portuguese/update/json',
    'fa': 'http://localhost:8080/solr/Persian/update/json',
    'h': 'http://localhost:8080/solr/Hungarian/update/json',
    'r': 'http://localhost:8080/solr/Russian/update/json',
}

# Configuration of what templates to use.  Complete title
# to the Wikipedia userspace article that contains the template.
# Each key is a language code, which then contains a dictionary
# where one key is 'request', that points to the template for
# one-time requests, and the other is 'regulars', which points
# to the template to use for our regular users.

# For the popularity and quality study in Aug-Sept 2011, we have added
# templates for each of the four experimental groups. (the control group
# uses 'regulars')
templates = {
    'en': {
        'request': 'User:SuggestBot/Templates/RequestsPlain',
        'plain': 'User:SuggestBot/Templates/RegularsPlain',
        'regulars': 'User:SuggestBot/Templates/RegularsFull',
        # 'regulars': 'User:SuggestBot/Templates/Regulars',
        'popqual': 'User:SuggestBot/Templates/studytemplate-1',
        'pop': 'User:SuggestBot/Templates/studytemplate-2',
        'qual': 'User:SuggestBot/Templates/studytemplate-3',
        'combined': 'User:SuggestBot/Templates/studytemplate-4',
    },
    'no': {
        'request': 'Bruker:AnbefalingsBot/Maler/Anbefaling',
        'regulars': 'Bruker:AnbefalingsBot/Maler/Anbefaling',
    },
    'sv': {
        'request': 'Användare:FörslagsBot/Mallar/Enstaka',
        'regulars': 'Användare:FörslagsBot/Mallar/Regelbundna',
    },
    'pt': {
        'request': 'Usuário(a):SuggestBot/Templates/Requests',
        'regulars': 'Usuário(a):SuggestBot/Templates/Regulars',
    },
    'r': {
        'request': 'Участник:SuggestBot/Шаблоны/Запросы',
        'regulars': 'Участник:SuggestBot/Шаблоны/Регулярные',
    },
    'fa': {
        'request': 'کاربر:SuggestBot/Templates/Requests',
        'regulars': 'کاربر:SuggestBot/Templates/Regulars',
    }
}

# Templates added by our regular users.
config_templare = {
    'en': { 'config': 'User:SuggestBot/config',
             'userbox': 'User:SuggestBot/userbox', },
    'no': { 'config': 'Bruker:AnbefalingsBot/konfigurasjon',
             'userbox': 'Bruker:AnbefalingsBot/brukerboks', },
    'sv': { 'config': 'Användare:FörslagsBot/konfiguration',
             'userbox': 'Användare:FörslagsBot/användarruta', },
    'pt': { 'config': 'Usuário(a):SuggestBot/config',
             'userbox': 'Usuário(a):SuggestBot/userbox', },
    'r': { 'config': 'Участник:SuggestBot/Настройка',
             'userbox': 'Участник:SuggestBot/userbox',
         },
    'fa': {
        'config': 'کاربر:SuggestBot/config',
        'userbox': 'کاربر:SuggestBot/userbox',
    }
}

# Which references we'll ignore when looking for backlinks
# when processing the regular user templates.
templater_stoplist = {
    'en': ['User:SuggestBot/config',
           'User:SuggestBot/Getting Recommendations Regularly', ],
    'no': ['Bruker:AnbefalingsBot/konfigurasjon',
           'Bruker:AnbefalingsBot/Jevnlige Anbefalinger', ],
    'sv': ['Användare:FörslagsBot/konfiguration',
           'Användare:FörslagsBot/Få rekommendationer regelbundet'],
    'pt': [ 'Usuário(a):SuggestBot/config',
            'Usuário(a):SuggestBot/Getting suggestions regularly',
            'Usuário(a):SuggestBot/Obtendo sugestões regularmente'],
    'r': [ 'Участник:SuggestBot/Настройка',
            'Участник:SuggestBot/Регулярные рекомендации' ],
    'fa': [ 'کاربر:SuggestBot/config',
            'کاربر:SuggestBot/Getting suggestions regularly', ]
}

# Request templates used in the WP:Teahouse experiment
teahouse_templates = {
    'en': ['User:SuggestBot/th-suggest'],
    'sv': ['Användare:FörslagsBot/fr-förslag'],
    'no': [],
    'pt': [],
    'fa': [],
    'r': [],
    'h': []
}

# Templates used for one-time requests.
# Outermost dictionary maps language codes to template configurations
# for that language.  Inner dictionary maps a template name to
# its known synonyms (synonyms are redirects to the template)
request_template = {
    'en': {"User:SuggestBot/suggest":
            ["User:SuggestBot/th-suggest",
             "User:SuggestBot/wp-suggest"],
        },
    'no': {'Bruker:AnbefalingsBot/anbefaling':
            [],
        },
    'sv': {'Användare:FörslagsBot/förslag':
            ['Användare:FörslagsBot/fr-förslag'],
        },
    'pt': {'Usuário(a):SuggestBot/suggest':
            [],
            'User:SuggestBot/suggest': [],
        },
    'r': { 'Участник:SuggestBot/suggest': [],
             'User:SuggestBot/suggest': [],
         },
    'fa': { 'کاربر:SuggestBot/suggest':
             ['ربات پیشنهاددهنده'],
             'User:SuggestBot/suggest':
             ['ربات پیشنهاددهنده'],
         }
}

# Regular expressions used to match the section heading of requests
# associated with the WP:Teahouse experiment (maybe also elsewhere).
# Section headings matching this regular expression are deleted as
# SuggestBot posts the recommendations.
request_head_re = {
    'en': ["[=]{1,3}\s*.* your editing suggestions are on the way.*\s*[=]{1,3}"],
    'no': [],
    'sv': ["[=]{1,3}\s*.*, dina förslag är på väg.*\s*[=]{1,3}"],
    'pt': [],
    'fa': [],
    'r': [],
    'h': []
}

# Name of the category parameter used in Teahouse suggestions,
# users copy & paste WikiProject names into these
th_category = {
    'en': 'category',
    'no': '',
    'sv': 'kategori',
    'pt': '',
    'fa': '',
    'r': '',
    'h': ''
}

# Suffix used in category names to match WikiProject category names,
# e.g. on enwiki we must add ' articles' to match it correctly.
wikiproject_suffix = {
    'en': ' articles',
    'no': '',
    'sv': '',
    'pt': '',
    'fa': '',
    'r': '',
    'h': ''
}

## WikiProject suggestion request parameters

## Page name of the template used for WikiProject requests
wikiproject_template = 'User:SuggestBot/wp-request'

## URL for WikiProject X configuration data
wikiproject_config_url = 'https://tools.wmflabs.org/projanalysis/config.php'

## Subpage-name to post to for projects discovered through the WPX URL
wikiproject_subpage = '/Edit articles'

## List of pages to ignore requests from
wikiproject_ignores = []

## Number of days between updates of WikiProject suggestions
wikiproject_delay = 7

# Placeholder text added when a page would otherwise be empty,
# used to make sure our edits actually get saved
empty_placeholder = {
    'en': '<!-- Empty placeholder left by SuggestBot, feel free to delete when necessary -->',
    'no': '<!-- Fyllkommentar lagt igjen av AnbefalingsBot, kan fjernes ved behov -->',
    'sv': '<!-- Fyllkommentar från FörslagsBot, kan tas bort vid behov -->',
    'pt': '<!-- Empty placeholder left by SuggestBot, feel free to delete -->',
    'fa': '<!-- Empty placeholder left by SuggestBot, feel free to delete -->',
    'r': '<!-- Empty placeholder left by SuggestBot, feel free to delete -->',
    'h': ''
}

# Base-filename of file to store names of users where the configuration
# didn't parse correctly.
userlist_warnings = '../data/userlists/regulars/warnings.txt'

# Dictionary of accepted parameters for our configuration templates.
# Keys are language codes, which then map to a dictionary where each
# key is the parameter name used for the template in said language,
# and the value is the global parameter name.
template_parameters = {
    'en': {
        'frequency': 'frequency',
        'replace': 'replace',
        'headlevel': 'headlevel',
    },
    'no': {
        'frekvens': 'frequency',
        'erstatt': 'replace',
        'nivå': 'headlevel',
    },
    'sv': {
        'frekvens': 'frequency',
        'ersätt': 'replace',
        'nivå': 'headlevel',
    },
    'pt': {
        'frequência': 'frequency',
        'substituir': 'replace',
        'nível': 'headlevel',
    },
    'r': {
        'частота': 'frequency',
        'заменять': 'replace',
        'уровень': 'headlevel',
    },
    'fa': {
        'frequency': 'frequency',
        'replace': 'replace',
        'level': 'headlevel',
    }
}

# Regular expressions for matching desired frequency of recommendations.
# Keys are language codes, values are the regular expression used for
# matching in that language.
once_monthly = {
    'en': r"monthly|once a month",
    'no': r"en gang i måneden",
    'sv': r"en gång i månaden",
    'pt': r"mensalmente|uma vez por mês",
    'r': r"ежемесячно|раз в месяц",
    'fa': r'monthly|once a month',
}
twice_monthly = {
    'en': r"twice a month|(every|once (a|every)) (fortnight|two weeks)",
    'no': r"to ganger i måneden|annenhver uke",
    'sv': r"två gånger i månaden",
    'pt': r"quinzenalmente|duas vezes por mês",
    'r': r"дважды в месяц",
    'fa': r'twice a month|every two weeks',
}
weekly = {
    # NOTE: we're allowing users to specify getting them daily, but serve them weekly
    'en': r"(once a|twice a|every) (week|day)|weekly|daily",
    'no': r"en gang i uken",
    'sv': r"en gång i veckan",
    'pt': r"uma vez por semana|semanalmente",
    'r': r"еженедельно|раз в неделю",
    'fa': r'(once a|every) week|weekly',
}

# Dictionary holding the text of the header of the SuggestBot
# post in each language we understand.  When replacing recommendations,
# we search for this text in the document we're working on.
rec_headers = {
    'en': '== Articles you might like to edit, from SuggestBot ==',
    'no': '== Artikler du med glede kan redigere, fra AnbefalingsBot ==',
    'sv': '== Artiklar du kanske vill redigera, från FörslagsBot ==',
    'pt': '== Artigos que você gostaria de editar, de SuggestBot ==',
    'r': '== Статьи, которые Вам возможно захочется исправить, от SuggestBot ==',
    'fa': '== مقاله‌های پیشنهادی توسط ربات پیشنهاددهنده ==',
}

rec_header_re = {
    'en': 'Articles you might like to edit, from SuggestBot',
    'no': 'Artikler du med glede kan redigere, fra AnbefalingsBot',
    'sv': 'Artiklar du kanske vill redigera, från FörslagsBot',
    'pt': 'Artigos que você gostaria de editar, de SuggestBot',
    'r': 'Статьи, которые Вам возможно захочется исправить, от SuggestBot',
    'fa': 'مقاله‌های پیشنهادی توسط ربات پیشنهاددهنده',
}

# Dictionarly holding lists of titles of subsections of SuggestBot's
# post.  We will also delete the contents of these sub-headers if
# the user has invoked the "replace" option.
sub_header_re = {
    'en': ["Changes to SuggestBot's suggestions"],
    'no': [],
    'sv': [],
    'pt': [],
    'fa': [],
    'r': [],
    'h': []
}

# Regular expressions to match a Yes/No parameter value in
# all languages we speak.  Matching is done case-insensitively.
re_yes = {
    'en': r'\s*yes\s*',
    'no': r'\s*ja\s*',
    'sv': r'\s*ja\s*',
    'pt': r'\s*sim\s*',
    'r': r'\s*да\s*',
    'fa': r'\s*yes\s*',
}
re_no = {
    'en': r'\s*no\s*',
    'no': r'\s*nei\s*',
    'sv': r'\s*nej\s*',
    'pt': r'\s*não\s*',
    'r': r'\s*нет\s*',
    'fa': r'\s*no\s*',
}

## Regular expressions to match list-articles in the given language
## (should be in sync with the same in toolserver/links-server-*.py)
list_re = {
    'en': r'[Ll]ist[ _]of[ _]',
    'no': r'[Ll]iste[ _]over[ _]',
    'sv': r'[Ll]ista[ _]över[ _]',
    'pt': r'[Ll]ista[ _]de[ _]',
    'h': r'[ _]listája$',
    'fa': r'^فهرست',
    'r': r'(^Список|(:Алфавитный[ _]|Хронологический[ _])список)|—[ _]список'
}

# P-value cutoffs for determining if an article-specific task suggestion
# is a "yes" or a "maybe"
task_p_yes = 0.1
tesk_p_maybe = 0.15

# Maps our five dimensions to human-comprehensible task names
humantasks = {
    'length': 'content',
    'lengthToRefs': 'sources',
    'headings': 'headings',
    'numImages': 'images',
    'completeness': 'links'
}

# Mapping of yes/maybe/no for each task category to table-sort template
# and if necessary files with matching alt-texts
task_map = {
    'content-yes': '{{{{Hs|0.0}}}} [[File:Redx2.svg|18px|alt=Please add more content|link={rectitle}|Please add more content]]',
    'content-maybe': '{{{{Hs|1.0}}}} [[File:Question mark basic.svg|20px|alt=Please check the article, it might need more content|link={rectitle}|Please check the article, it might need more content]]',
    'content-no': '{{{{Hs|2.0}}}}',

    'headings-yes': '{{{{Hs|0.0}}}} [[File:Redx2.svg|18px|alt=Please create proper section headings|link={rectitle}|Please create proper section headings]]',
    'headings-maybe': '{{{{Hs|1.0}}}} [[File:Question mark basic.svg|20px|alt=Please check the article, it might not have all the necessary section headings|link={rectitle}|Please check the article, it might not have all the necessary section headings]]',
    'headings-no': '{{{{Hs|2.0}}}}',

    'images-yes': '{{{{Hs|0.0}}}} [[File:Redx2.svg|18px|alt=Please add more images|link={rectitle}|Please add more images]]',
    'images-maybe': '{{{{Hs|1.0}}}} [[File:Question mark basic.svg|20px|alt=Please check the article, it might need more images|link={rectitle}|Please check the article, it might need more images]]',
    'images-no': '{{{{Hs|2.0}}}}',

    'links-yes': '{{{{Hs|0.0}}}} [[File:Redx2.svg|18px|alt=Please add more wikilinks|link={rectitle}|Please add more wikilinks]]',
    'links-maybe': '{{{{Hs|1.0}}}} [[File:Question mark basic.svg|20px|alt=Please check the article, it might need more wikilinks|link={rectitle}|Please check the article, it might need more wikilinks]]',
    'links-no': '{{{{Hs|2.0}}}}',

    'sources-yes': '{{{{Hs|0.0}}}} [[File:Redx2.svg|18px|alt=Please add more sources|link={rectitle}|Please add more sources]]',
    'sources-maybe': '{{{{Hs|1.0}}}} [[File:Question mark basic.svg|20px|alt=Please check the article, it might need more sources|link={rectitle}|Please check the article, it might need more sources]]',
    'sources-no': '{{{{Hs|2.0}}}}',
}

## Dictionary mapping low/medium/high quality
## to appropriate strings with format-parameters for inserting
## assessment class and predicted class
quality_map = {
    'low': '[[File:Stars310.svg|60 px|alt=Quality: Low, Assessed class: {assessedclass}, Predicted class: {predclass}|link={rectitle}|Quality: Low, Assessed class: {assessedclass}, Predicted class: {predclass}]]',
    'medium': '[[File:Stars320.svg|60 px|alt=Quality: Medium, Assessed class: {assessedclass}, Predicted class: {predclass}|link={rectitle}|Quality: Medium, Assessed class: {assessedclass}, Predicted class: {predclass}]]',
    'high': '[[File:Stars330.svg|60 px|alt=Quality: High, Assessed class: {assessedclass}, Predicted class: {predclass}|link={rectitle}|Quality: High, Assessed class: {assessedclass}, Predicted class: {predclass}]]',
}

# Table name of the status information table in the database
# (it holds one row for each defined language)
status_table = 'status_info'

# List of names of the different study groups used in the fall 2011
# experiment on adding information.
# self.config['STUDYGROUPS'] = {
#     'en': ['pop', 'qual', 'popqual', 'combined', 'control'],
#     'no': [],
#     'sv': [],
#     'pt': [],
#     }

# Dictionary mapping high/medium/low popularity,
# high/medium/low quality, and high/medium/low needslove
# to wikicode to include them in our templates.
# self.config['POPULARITY_MAP'] = {
#     'low': '[[File:Gnome-stock person.svg|22 px|alt=Readership: Low|Readership: Low]]',
#     'medium': '[[File:Gnome-system-users.svg|28 px|alt=Readership: Medium|Readership: Medium]]',
#     'high': '[[File:Icon of three people in different shades of grey.svg|30 px|alt=Readership: High|Readership: High]]',
#     }
# self.config['QUALITY_MAP'] = {
#     'low': '[[File:Stars310.svg|60 px|alt=Quality: Low|Quality: Low]]',
#     'medium': '[[File:Stars320.svg|60 px|alt=Quality: Medium|Quality: Medium]]',
#     'high': '[[File:Stars330.svg|60 px|alt=Quality: High|Quality: High]]',
#     }
# self.config['COMBINED_MAP'] = {
#     'low': '[[File:Green cross.svg|15 px|alt=Opportunity: Low|Opportunity: Low]]',
#     'medium': '[[File:Green cross.svg|15 px|alt=Opportunity: Medium|Opportunity: Medium]] [[File:Green cross.svg|15 px|alt=|Opportunity: Medium]]',
#     'high': '[[File:Green cross.svg|15 px|alt=Opportunity: High|Opportunity: High]] [[File:Green cross.svg|15 px|alt=|Opportunity: High]] [[File:Green cross.svg|15 px|alt=|Opportunity: High]]',
#     }

## What language Wikipedia are we working on? Usually set by individual scripts
## as necessary.
wp_langcode = "en"

# Server configurations
# The recommendation server will always listen on "localhost:$MAIN_SERVER_PORT'
main_server_port = 10010
coedit_hostname = "localhost"
coedit_hostport = 10001
textmatch_hostname = "localhost"
textmatch_hostport = 10003
edit_server_hostname = "localhost"
edit_server_hostport = 10007
filter_server_hostname = "localhost"
filter_server_hostport = 10009
popularity_and_quality_hostname= "localhost"
popularity_and_quality_hostport= 10008

textdaemon_hostname = "localhost"
textdaemon_hostport = 10128

classifier_hostname = "localhost"
classifier_hostport = 10129

# These are kept for backwards compatibility, as the links server is now on
# the Toolserver.  The port number is used for picking recommendations.
links_hostname = "localhost"
links_hostport = 10006

# How many contributions do we maximally grab through the API
# to base our recommendations on?
# FIXME: this should be called NEDITS instead!
nrecs = 500
