# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# What MENU > Delete does with the tile under the cursor: which kind it is, and the rename of a folder. No enigma2 imports: the decision can be tested without a box.

import os

FILE = "file"               # a file: a picture, a movie, a song, a playlist ...
FOLDER = "folder"           # a folder, with everything in it
PROTECTED = "protected"     # a bookmark, a mount point or the root of the file system: never deleted, the screen says so
DELETED_SUFFIX = ".del"        # what is added to the name of a folder that was deleted


def deleteKind(is_folder, is_placeholder, path, bookmarks, ismount=os.path.ismount):
    """FILE, FOLDER, PROTECTED, or None when the tile is no real file or folder (the tile of the parent folder, an entry of a playlist
    that cannot be found): nothing happens.

    A folder that is a bookmark is what the list of the bookmarks shows, and removing it would take a whole disk or share with it;
    a mount point is the same. They are compared as normalized paths (a trailing slash does not matter)."""
    if is_placeholder or not path or ".." in path.split("/"):
        return None         # a path with .. is the tile of the parent folder: normpath would turn it into the folder that is shown
    if not is_folder:
        return FILE
    folder = os.path.normpath(path)
    if folder == os.path.dirname(folder) or ismount(folder) or any(os.path.normpath(bookmark) == folder for bookmark in bookmarks):
        return PROTECTED
    return FOLDER


def deleteFolder(path):
    """A folder is not removed but renamed to name.del (name.2.del, name.3.del ... when that exists already): everything stays on the disk
    and renaming it back brings it back, while the cache does not load it (CacheLoadMDC.checkDir). Returns the new path, None if the folder
    could not be renamed (nothing is changed then)."""
    if not path or ".." in path.split("/"):
        return None
    folder = os.path.normpath(path)
    target = folder + DELETED_SUFFIX
    number = 1
    while os.path.lexists(target):
        number += 1
        target = f"{folder}.{number}{DELETED_SUFFIX}"
    try:
        os.rename(folder, target)
    except OSError:
        return None
    return target
