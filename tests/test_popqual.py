# Test get_popquals method of suggestbot.utilities.popqual

import logging
logging.basicConfig(level=logging.INFO)

import suggestbot.utilities.popqual as sup

pagelist = ['Barack Obama', 'Ara Parseghian', 'Clarence Darrow', 'Andre Dawson',
            '2004 Chicago Bears season', "Jack O'Callahan", "Switchcraft"]

for pq_info in sup.get_popquals('en', pagelist):
    print(pq_info)
    
