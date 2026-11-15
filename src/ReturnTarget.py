# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# Where the tile screen goes back to when it is shown again (after a slideshow, the music player, the video player, a restart of the
# list, ...): a folder with the cursor on one of its entries, the list of the bookmarks, or a playlist with the cursor on one of
# its entries. The entries of a playlist live in any folder, so the folder of the entry under the cursor is not the place to return
# to: the playlist is.

import os

PLAYLIST = "PLAYLIST"   # dir of a target that is a playlist


class ReturnTarget:
    def __init__(self):
        self.dir = ""       # the folder to show, "" for the bookmarks, PLAYLIST for the entries of a playlist
        self.path = ""      # the entry that has the cursor in a folder; the .m3u when dir is PLAYLIST
        self.entry = ""     # the entry that has the cursor in a playlist

    def __repr__(self):
        return f"ReturnTarget(dir={self.dir!r}, path={self.path!r}, entry={self.entry!r})"

    def bookmarks(self):
        self.dir = self.path = self.entry = ""

    def folder(self, adir, path=""):
        self.dir, self.path, self.entry = adir, path, ""

    def remember(self, playlist_path, selected_dir, selected_path):
        """The screen is hidden: come back to what it shows now. selected_dir, selected_path: folder and path of the entry
        under the cursor."""
        if playlist_path:
            self.dir, self.path, self.entry = PLAYLIST, playlist_path, selected_path
        else:
            self.dir, self.path, self.entry = selected_dir, selected_path, ""

    def cursor_on(self, path, in_playlist):
        """Another entry has the cursor when the screen comes back (e.g. the song that played last)."""
        if not path:
            return
        if in_playlist:
            self.entry = path
        else:
            self.path = path

    def take_entry(self):
        """The entry for the cursor of a playlist, once."""
        entry, self.entry = self.entry, ""
        return entry


def parentTarget(current_dir, bookmarks):
    """Where "up" leads from the folder that is shown: (the folder to show, the entry that gets the cursor), or None when the
    list of the bookmarks is shown already. From a bookmark (the top of a tree) up is the list of the bookmarks, with the cursor
    on that bookmark; elsewhere it is the parent folder, with the cursor on the folder that was left.
    A bookmark can lie inside another one: whether a folder is a bookmark depends on the folder that is shown, not on the entry
    under the cursor (a bookmark inside the folder is only an entry of it)."""
    if not current_dir:
        return None
    folder = os.path.normpath(current_dir)
    for bookmark in bookmarks:
        if os.path.normpath(bookmark) == folder:
            return "", bookmark
    parent = os.path.dirname(folder)
    if parent == folder:        # the root of the file system is not a bookmark: the list of the bookmarks is the only way up
        return "", ""
    return parent, folder


def forgetDeleted(file_list, closed_path, deleted, path_index):
    """The tile list after pictures were deleted in the viewer: (the list without them, the path that gets the cursor). The cursor stays
    where it was: on the entry the viewer was left on, or, when that one was deleted too, on the entry that took its place (the last
    one when it was the last). path_index: where the path is in an entry."""
    gone = set(deleted)
    if not gone:
        return file_list, closed_path
    old_index = next((i for i, afile in enumerate(file_list) if afile[path_index] == closed_path), 0)
    before = sum(1 for afile in file_list[:old_index] if afile[path_index] in gone)
    remaining = [afile for afile in file_list if afile[path_index] not in gone]
    if closed_path in gone:
        closed_path = remaining[min(max(old_index - before, 0), len(remaining) - 1)][path_index] if remaining else ""
    return remaining, closed_path
