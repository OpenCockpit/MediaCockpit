# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# The order of the entries of a folder. Pure Python, no enigma2: it is tested on the PC (test/test_sort.py).

import re
import unicodedata


NOT_IN_ORDER = 1 << 30      # position of a file that is not in the manual order of its folder: after all that are

MODE_NAME, MODE_DATE, MODE_MANUAL = "name", "date", "manual"


def naturalKey(name):
    """Sort key of a file name: upper and lower case and accents are ignored, and numbers count by their value, so that
    img2.jpg comes before img10.jpg and Äpfel next to Apfel."""
    text = unicodedata.normalize("NFKD", name).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    # the parts alternate: text, number, text, number, ... (the first text may be empty): two keys never compare a number with text
    return [int(part) if index % 2 else part for index, part in enumerate(re.split(r"(\d+)", text))]


def nameKey(name):
    """naturalKey() with the name itself as the last tie-breaker: names that only differ in case or accents have a fixed order."""
    return naturalKey(name), name


def sortEntries(entries, mode, reverse, name, date, position, group):
    """Sort entries in place and return them. name, date, position and group give the sort values of an entry.

    The sort is done in several passes, the last one being the most important: stable sorts keep the order of the earlier passes
    for entries that are equal in the later ones. So a date has the name as its tie-breaker (videos and songs of one day), and
    reverse only turns the names or the dates, never the groups: folders and playlists stay in front of the files."""
    if mode == MODE_NAME:
        entries.sort(key=lambda entry: nameKey(name(entry)), reverse=reverse)
    elif mode == MODE_DATE:
        entries.sort(key=lambda entry: nameKey(name(entry)))
        entries.sort(key=date, reverse=reverse)
    else:   # manual: the files of the order file of the folder first, in its order; the others after them by date and name
        entries.sort(key=lambda entry: nameKey(name(entry)))
        entries.sort(key=date)
        entries.sort(key=lambda entry: position(entry) or NOT_IN_ORDER)
    entries.sort(key=group)
    return entries
