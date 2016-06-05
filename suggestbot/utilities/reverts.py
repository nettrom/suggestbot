#!/usr/env/python
# -*- coding: utf-8 -*-
"""
Library code to identify reverts in various languages.
"""

VLOOSE_RE = r'''
          (^revert\ to.+using)
        | (^reverted\ edits\ by.+using)
        | (^reverted\ edits\ by.+to\ last\ version\ by)
        | (^bot\ -\ rv.+to\ last\ version\ by)
        | (-assisted\ reversion)
        | (^(revert(ed)?|rv).+to\ last)
        | (^undo\ revision.+by)
        '''

VSTRICT_RE = r'''
          (\brvv)
        | (\brv[/ ]v)
        | (vandal(?!proof|bot))
        | (\b(rv|rev(ert)?|rm)\b.*(blank|spam|nonsense|porn|mass\sdelet|vand))
        '''

HU_VANDAL_RE = r"""vandál"""

REVERT_RE = {
    'en': r'''[Uu]ndid.*\ revision\ [0-9]+\ by''',
    'no': r'''(^tilbakestilt)|(^fjerner\s+revisjon\s+\d+)''',
    'sv': r'''(Rullade\s+till?baka.*redigeringar\s+av)
              |(^Gjorde\s+redigering\s+\d+\s+av.*ogjord)
              |(Återställ(er|(d\s+till\s+(tidigare|senaste)\s+(version|redigering)\s+av)))''',
    'de': r'''(^(re)?revert)
              |(Die\ (\d+\ )?letzten?\ Änderung(en)?\ von\ .+\ wurden?\ verworfen\ und\ die\ Version\ \d+\ von\ .+\ wiederhergestellt)
              |(Änderung(en)?.+rückgängig\ gemacht)''',
    'zh': r'''(\[\[Wikipedia:UNDO[^\]]+\]\])
              |(取消\s*\[\[[^\]]+\]\]\s*\(对话\)\s*的编辑；更改回\s*\[\[[^\]]+\]\]的最后一个版本)''',
    'pt': r'''[Rr]evertidas.*edições\ de.*para\ a\ edição\ \d+\ de
              |[Rr]evertidas.*edições\ por\ .*\ para\ a\ última\ versão\ por
              |[Rr]emovendo vandalismos
              |[Rr]eversão\ de\ uma\ ou\ mais\ edições\ de.*para\ a\ versão\ \d+\ de''',
    'fa': r"""خنثی‌سازی ویرایش \d+ توسط \[\[.+?\]\] \(\[\[.+?\|بحث\]\]\)
              |ویرایش \[\[(.+?)\]\] \(\[\[.+?\|بحث\]\]\) به آخرین تغییری که .+? انجام داده بود واگردانده شد
              |به نسخهٔ \d+? ویرایش .+? واگردانده شد: .+?""",
    'hu': r"""Visszaállítottam\ a\ lap\ korábbi\ változatát:\ \[\[.*?\]\].*?szerkesztéséről.*?szerkesztésére
              |Visszavontam\ az\ utolsó\ (\d+\ )?változtatást\ \(\[\[.*?\]\]\),\ visszaállítva.*?szerkesztésére
              |Visszavontam\ \[\[.*?\]\]\ \(\[\[.*?\]\]\)\ szerkesztését\ \(oldid:\ \d+\)""",
    'ru': r"""[Оо]тмена[\s]*(\]\])*[\s]*[Пп]равки
              |[Оо]ткат[\s]*(\]\])*[\s]*[Пп]равок
              |[Оо]ткатчены[\s]*(\]\])*[\s]*к[\s]*[Вв]ерсии""",
    'fr': r'''[Rr]évocation\ des\ modifications\ de.*retour\ à\ la\ dernière\ version\ de
              |[Aa]nnulation\ des\ modifications\ \d+\ de'''
    }

AWB = r"""(using|utilizando)\s+\[\[[^|]+[|]AWB\]\]"""

# Rewrote this to be case insensitive and support Swedish use of HotCat
HotCat = r"(using|med|usando)\s+\[\[[^|]+[|]HotCat\]\]"

# Twinkle
Twinkle = r"\[\[[^|]+[|]TW\]\]"

# Page curation
curation = "using\s+\[\[[^|]+[|]Page\s+Curation\]\]"

# Always something miscellaneous at the end...
misc = r"^\s*rv|wikify|cleanup|protect|disamb|Undid.+revision\s+\d+\s+"
