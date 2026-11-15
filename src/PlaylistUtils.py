# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# Reading and editing a playlist (.m3u). Pure Python, no enigma2: it is tested on the PC (test/test_playlist.py).
#
# A playlist is kept as a list of entries, each with the comment lines in front of it (#EXTINF...), so that editing it leaves
# those lines with their entry. The entries are written as they were read (a relative path stays relative); a path that is added
# is relative when the file is below the folder of the playlist, absolute otherwise.

import os
from urllib.parse import unquote


def entryPath(line, directory):
    """The path an entry line stands for: absolute and normalised. file:// is decoded; a stream address is kept as it is."""
    line = line.strip()
    if line.startswith("file://"):
        line = unquote(line[len("file://"):])
    elif "://" in line:
        return line
    if not line.startswith("/"):
        line = os.path.join(directory, line)
    return os.path.normpath(line)


class Playlist():

    def __init__(self, text="", directory=""):
        self.directory = directory
        self.head = []          # "#EXTM3U"
        self.entries = []       # [comment lines, entry line]
        self.tail = []          # comment lines after the last entry
        pending = []
        for raw in text.lstrip("﻿").splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                if line.upper().startswith("#EXTM3U") and not self.head and not self.entries and not pending:
                    self.head.append(line)
                else:
                    pending.append(line)
                continue
            self.entries.append([pending, line])
            pending = []
        self.tail = pending

    def paths(self):
        """The path of every entry, in order (a path that is listed twice appears twice)."""
        return [entryPath(line, self.directory) for _comments, line in self.entries]

    def index(self, path):
        """Index of the first entry with this path, -1 if there is none."""
        paths = self.paths()
        return paths.index(path) if path in paths else -1

    def remove(self, path):
        """Remove every entry with this path (the playlist shows a path once, however often it is listed). Returns how many."""
        keep = [entry for entry in self.entries if entryPath(entry[1], self.directory) != path]
        removed = len(self.entries) - len(keep)
        self.entries = keep
        return removed

    def add(self, path):
        """Add a path at the end. False if it is in the playlist already."""
        if self.index(path) >= 0:
            return False
        if "://" not in path and self.directory:
            relative = os.path.relpath(path, self.directory)
            line = relative if not relative.startswith("..") else path
        else:
            line = path
        self.entries.append([[], line])
        return True

    def move(self, path, step):
        """Move the entry one place backward (-1) or forward (+1). A path that is listed more than once is listed once from then
        on, because the places of the others would be invisible. False if it cannot be moved (not there, or at the end)."""
        index = self.index(path)
        if index < 0:
            return False
        seen = set()
        unique = []
        for entry in self.entries:
            entry_path = entryPath(entry[1], self.directory)
            if entry_path not in seen:
                seen.add(entry_path)
                unique.append(entry)
        index = [entryPath(entry[1], self.directory) for entry in unique].index(path)
        target = index + step
        if not 0 <= target < len(unique):
            return False
        unique[index], unique[target] = unique[target], unique[index]
        self.entries = unique
        return True

    def text(self):
        lines = list(self.head)
        for comments, line in self.entries:
            lines += comments
            lines.append(line)
        lines += self.tail
        return "".join(line + "\n" for line in lines)


def readPlaylist(path):
    """The playlist of a file; an empty one if it cannot be read."""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            return Playlist(f.read(), os.path.dirname(path))
    except OSError:
        return Playlist("", os.path.dirname(path))


def writePlaylist(path, playlist):
    """Write the file next to the old one and rename it over it: an interrupted write leaves the old playlist as it was.
    Raises OSError if the folder cannot be written."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(playlist.text())
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def newPlaylistPath(directory, name):
    """The path of a new playlist called name in directory, or None if the name is empty or unusable. The file is not made."""
    name = name.strip().replace("/", "").replace("\\", "").strip(".")
    if not name:
        return None
    if not name.lower().endswith(".m3u"):
        name += ".m3u"
    return os.path.join(directory, name)


def createPlaylist(path):
    """Make an empty playlist. Raises FileExistsError if there is one with this name, OSError if it cannot be written."""
    with open(path, "x", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
