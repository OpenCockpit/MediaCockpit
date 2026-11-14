# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# The manual order of the files of a folder. It is kept in the folder itself, in a hidden text file with one file name per line,
# so that it survives a rebuild of the cache, and moves with the folder. CacheCockpit reads it while it loads a folder (the
# position of a file is stored in the cache), MediaCockpit writes it when a file is moved.
#
# Files that are not listed come after the listed ones, in the order the sort mode gives; names of files that do not exist any
# more are ignored (and dropped the next time the order is written).

import os


ORDER_FILE = ".mediacockpit_order"


def orderPath(adir):
    return os.path.join(adir, ORDER_FILE)


def readOrder(adir):
    """The file names of the order file of a folder, in order. [] if there is no (readable) order file."""
    try:
        with open(orderPath(adir), encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    return list(dict.fromkeys(line for line in lines if line))


def writeOrder(adir, names):
    """Write the order file. It is written next to the old one and renamed over it: an interrupted write (a USB stick pulled out,
    a full disk) leaves the old order as it was. Raises OSError if the folder cannot be written."""
    path = orderPath(adir)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("".join(name + "\n" for name in names))
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def positionsOf(names):
    """{name: position}, positions count from 1 (0 means: not in the order)."""
    return {name: position for position, name in enumerate(names, 1)}


def moved(names, name, step):
    """names with name moved by step places (-1 backward, 1 forward), None if it cannot be moved (not there, or already at the end)."""
    if name not in names:
        return None
    index = names.index(name)
    target = index + step
    if not 0 <= target < len(names):
        return None
    result = list(names)
    result[index], result[target] = result[target], result[index]
    return result
