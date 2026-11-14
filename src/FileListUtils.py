# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
import json
from urllib.parse import unquote
from Components.config import config
from Plugins.SystemPlugins.CacheCockpit.FileManager import FileManager
from .Debug import logger
from .FileManagerUtils import MDC_TYPE_DIR, MDC_TYPE_FILE, MDC_TYPE_LINK
from .FileManagerUtils import MDC_IDX_TYPE, MDC_IDX_PATH, MDC_IDX_MEDIA, MDC_IDX_META, MDC_IDX_DATE
from .FileManagerUtils import MDC_MEDIA_TYPE_FILE, MDC_MEDIA_TYPE_PICTURE, MDC_MEDIA_TYPE_MOVIE, MDC_MEDIA_TYPE_MUSIC, MDC_MEDIA_TYPE_DIR, MDC_MEDIA_TYPE_UP, MDC_MEDIA_TYPE_UNAVAILABLE
from .ConfigInit import sort_modes
from .Version import ID
from .FileUtils import readFile


def nextIndex(file_index, file_list_length):
    index = -1
    if file_list_length > 0:
        index = (file_index + 1) % file_list_length
    return index


def previousIndex(file_index, file_list_length):
    index = -1
    if file_list_length > 0:
        index = file_index - 1 if file_index else file_list_length - 1
    return index


def getIndex(file_list, path):
    file_index = 0 if file_list else -1
    for i, afile in enumerate(file_list):
        if afile[MDC_IDX_PATH] == path:
            file_index = i
            break
    return file_index


def getPath(file_list, index):
    current_path = ""
    if file_list:
        afile = file_list[index]
        current_path = afile[MDC_IDX_PATH]
    logger.debug("current_path: %s", current_path)
    return current_path


def getDir(file_list, index):
    current_dir = ""
    if file_list:
        afile = file_list[index]
        logger.debug("afile: %s", afile)
        path = afile[MDC_IDX_PATH]
        # a link is a folder too (the cache stores a symlinked folder as a link, and lists it with the folders)
        if afile[MDC_IDX_TYPE] in {MDC_TYPE_DIR, MDC_TYPE_LINK} and not path.endswith(".."):
            current_dir = path
        else:
            current_dir = os.path.dirname(path)
    logger.debug("current_dir: %s", current_dir)
    return current_dir


def getFile(file_list, value):
    afile = []
    if file_list:
        if isinstance(value, int):
            afile = file_list[value]
        elif isinstance(value, str):
            afile = file_list[getIndex(file_list, value)]
    return afile


def findMediaIndex(file_list, start=0):
    """Index of the first picture or movie at or after start (wrapping around), -1 if the list has none."""
    length = len(file_list)
    for i in range(length):
        index = (max(start, 0) + i) % length
        if file_list[index][MDC_IDX_MEDIA] in (MDC_MEDIA_TYPE_PICTURE, MDC_MEDIA_TYPE_MOVIE):
            return index
    return -1


def splitMediaSongList(file_list):
    song_list = []
    media_list = []
    for afile in file_list:
        logger.debug("afile: %s", afile)
        if afile[MDC_IDX_MEDIA] in MDC_MEDIA_TYPE_FILE:
            if afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MUSIC:
                song_list.append(afile)
            else:
                media_list.append(afile)
    return media_list, song_list


def sortList(file_list):
    file_list_sort = config.plugins.mediacockpit.sort.value
    sort_across_dirs = config.plugins.mediacockpit.sort_across_dirs.value
    mode, order = sort_modes[file_list_sort][0]
    logger.debug("sort_mode: %s, sort_order: %s", mode, order)

    if mode == "alpha":
        if sort_across_dirs:
            if order:
                file_list.sort(key=lambda afile: (min(afile[MDC_IDX_MEDIA], MDC_MEDIA_TYPE_PICTURE), os.path.basename(
                    afile[MDC_IDX_PATH]).lower()), reverse=True)
            else:
                file_list.sort(key=lambda afile: (min(
                    afile[MDC_IDX_MEDIA], MDC_MEDIA_TYPE_PICTURE), os.path.basename(afile[MDC_IDX_PATH]).lower()))
        elif order:
            file_list.sort(key=lambda afile: (min(
                afile[MDC_IDX_MEDIA], MDC_MEDIA_TYPE_PICTURE), afile[MDC_IDX_PATH].lower()), reverse=True)
        else:
            file_list.sort(key=lambda afile: (
                min(afile[MDC_IDX_MEDIA], MDC_MEDIA_TYPE_PICTURE), afile[MDC_IDX_PATH].lower()))
    elif mode == "date":
        if order:
            file_list.sort(key=lambda afile: (min(
                afile[MDC_IDX_MEDIA], MDC_MEDIA_TYPE_PICTURE), afile[MDC_IDX_DATE]), reverse=True)
        else:
            file_list.sort(key=lambda afile: (
                min(afile[MDC_IDX_MEDIA], MDC_MEDIA_TYPE_PICTURE), afile[MDC_IDX_DATE]))
    return file_list


def scanPlaylistFiles(path):
    """The entries of a .m3u as paths, in order. Entries whose file does not exist, and streams, are returned as well: the
    caller shows them as unavailable instead of dropping them without a word."""
    logger.debug("path: %s", path)
    file_list = []
    playlist_dir = os.path.dirname(path)
    lines = readFile(path).lstrip("\ufeff").splitlines()  # a UTF-8 BOM would corrupt the first path
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        logger.debug("line: %s", line)
        if line.startswith("file://"):
            line = unquote(line[len("file://"):])
        elif "://" in line:
            logger.debug("stream: %s", line)
            file_list.append(line)
            continue
        if not line.startswith("/"):
            line = os.path.join(playlist_dir, line)
        file_list.append(os.path.normpath(line))
    return file_list


def createBookmarkEntries(bookmarks):
    logger.debug("bookmarks: %s", bookmarks)
    alist = []
    meta = {}
    for bookmark in bookmarks:
        afile = list(FileManager.getInstance(
            ID).newDirData(bookmark, MDC_TYPE_DIR))
        logger.debug("afile: %s", afile)
        afile[MDC_IDX_MEDIA] = MDC_MEDIA_TYPE_DIR
        afile[MDC_IDX_META] = json.dumps(meta)
        alist.append(afile)
    return alist


def createUnavailableEntry(path):
    """The list entry of a playlist file that cannot be found (or is not in the cache)."""
    logger.debug("path: %s", path)
    afile = list(FileManager.getInstance(ID).newDirData(path, MDC_TYPE_FILE))
    afile[MDC_IDX_MEDIA] = MDC_MEDIA_TYPE_UNAVAILABLE
    afile[MDC_IDX_META] = json.dumps({})
    return afile


def createParentDirEntry(path):
    logger.debug("path: %s", path)
    meta = {}
    if os.path.splitext(path)[1] != ".m3u":
        path = os.path.join(path, "..")
    afile = list(FileManager.getInstance(ID).newDirData(path, MDC_TYPE_DIR))
    afile[MDC_IDX_MEDIA] = MDC_MEDIA_TYPE_UP
    afile[MDC_IDX_META] = json.dumps(meta)
    logger.debug("afile: %s", afile)
    return afile
