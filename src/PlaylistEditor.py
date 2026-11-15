# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# Editing playlists from the tile screen: remove or move an entry of the playlist that is shown, add the selected file to a
# playlist (an existing one, or a new one). Part of the MediaCockpit screen (a mixin like Menu); the editing itself is in
# PlaylistUtils.

import os
from Screens.ChoiceBox import ChoiceBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Components.config import config
from Plugins.SystemPlugins.CacheCockpit.FileManager import FileManager
from .__init__ import _
from .Debug import logger
from .Version import ID
from .FileManagerUtils import MDC_IDX_PATH, MDC_IDX_MEDIA
from .FileManagerUtils import MDC_MEDIA_TYPE_FILE, MDC_MEDIA_TYPE_UP, MDC_MEDIA_TYPE_PLAYLIST
from .FileListUtils import getFile
from .PlaylistUtils import readPlaylist, writePlaylist, newPlaylistPath, createPlaylist

NEW_PLAYLIST = ""       # the answer "New playlist" of the list of playlists (the others are paths)


class PlaylistEditor():

    def selectedPlaylistEntry(self):
        """The selected entry of the playlist that is shown, None for the parent tile or an empty list."""
        afile = getFile(self.file_list, self.file_index)
        return afile if afile and afile[MDC_IDX_MEDIA] != MDC_MEDIA_TYPE_UP else None

    def selectedFile(self):
        """The selected entry if it is a picture, video or song that exists."""
        afile = getFile(self.file_list, self.file_index)
        return afile if afile and afile[MDC_IDX_MEDIA] in MDC_MEDIA_TYPE_FILE else None

    def playlistMenuEntries(self):
        """The entries of the menu that are about playlists, for what is selected."""
        entries = []
        if self.playlist_path and self.selectedPlaylistEntry():
            entries.append((_("Remove from playlist"), "playlist_remove"))
        if self.selectedFile():
            entries.append((_("Add to playlist"), "playlist_add"))
        return entries

    def savePlaylist(self, path, playlist):
        try:
            writePlaylist(path, playlist)
        except OSError as e:
            logger.error("cannot write %s: %s", path, e)
            self.toast.show(_("The playlist cannot be written: %s") % (e.strerror or e))
            return False
        return True

    # the playlist that is shown

    def playlistMove(self, step):
        """Move the selected entry of the playlist one place backward (-1) or forward (+1). The playlist file is the order."""
        entry = self.selectedPlaylistEntry()
        if not entry:
            return
        path = entry[MDC_IDX_PATH]
        playlist = readPlaylist(self.playlist_path)
        if not playlist.move(path, step):
            self.toast.show(_("This is the first file.") if step < 0 else _("This is the last file."))
            return
        if self.savePlaylist(self.playlist_path, playlist):
            self.readFileList("PLAYLIST", self.playlist_path, path)

    def playlistRemove(self):
        """Remove the selected entry from the playlist (the file itself is not touched)."""
        entry = self.selectedPlaylistEntry()
        if not entry or not self.playlist_path:
            return
        path = entry[MDC_IDX_PATH]
        playlist = readPlaylist(self.playlist_path)
        if not playlist.remove(path):
            self.toast.show(_("The entry is not in the playlist."))
            return
        # the cursor goes to the entry behind the removed one, or in front of it at the end
        cursor = ""
        for index in (self.file_index + 1, self.file_index - 1):
            if 0 <= index < len(self.file_list) and self.file_list[index][MDC_IDX_MEDIA] != MDC_MEDIA_TYPE_UP:
                cursor = self.file_list[index][MDC_IDX_PATH]
                break
        if self.savePlaylist(self.playlist_path, playlist):
            self.readFileList("PLAYLIST", self.playlist_path, cursor)
            self.toast.show(_("Removed from the playlist."))

    # add the selected file to a playlist

    def playlistAdd(self):
        entry = self.selectedFile()
        if not entry:
            return
        path = entry[MDC_IDX_PATH]
        try:
            playlists = FileManager.getInstance(ID).getFileListByMedia(MDC_MEDIA_TYPE_PLAYLIST)
        except AttributeError:      # an older CacheCockpit
            playlists = []
        paths = sorted((afile[MDC_IDX_PATH] for afile in playlists), key=lambda p: (os.path.basename(p).lower(), p))
        alist = [(f"{os.path.basename(p)}   ({os.path.dirname(p)})", p) for p in paths] + [(_("New playlist..."), NEW_PLAYLIST)]
        # the playlist of the last time is selected: files are added to the same one one after the other; failing that the one
        # that is shown
        wanted = config.plugins.mediacockpit.last_playlist.value
        selection = next((index for index, p in enumerate(paths) if p == wanted), None)
        if selection is None:
            selection = next((index for index, p in enumerate(paths) if self.playlist_path and p == self.playlist_path), 0)
        self.session.openWithCallback(
            lambda answer: self.playlistAddAnswer(path, answer),
            ChoiceBox,
            title=_("Add to playlist") + "\n" + os.path.basename(path),
            list=alist,
            selection=selection,
            windowTitle=_("Add to playlist"),
            allow_cancel=True,
        )

    def playlistAddAnswer(self, path, answer):
        if not answer:
            return
        if answer[1] == NEW_PLAYLIST:
            self.session.openWithCallback(
                lambda name: self.playlistNewName(path, name), VirtualKeyBoard, title=_("Name of the new playlist"), text="")
        else:
            self.addToPlaylist(path, answer[1])

    @staticmethod
    def rememberPlaylist(playlist_path):
        if config.plugins.mediacockpit.last_playlist.value != playlist_path:
            config.plugins.mediacockpit.last_playlist.value = playlist_path
            config.plugins.mediacockpit.last_playlist.save()

    def playlistNewName(self, path, name):
        if not name:
            return
        folder = os.path.dirname(path)      # next to the file; the playlist may list files from anywhere
        playlist_path = newPlaylistPath(folder, name)
        if playlist_path is None:
            self.toast.show(_("This name cannot be used."))
            return
        try:
            createPlaylist(playlist_path)
        except FileExistsError:
            self.toast.show(_("A playlist with this name exists already."))
            return
        except OSError as e:
            logger.error("cannot create %s: %s", playlist_path, e)
            self.toast.show(_("The playlist cannot be written: %s") % (e.strerror or e))
            return
        FileManager.getInstance(ID).loadDatabaseFile(playlist_path)      # so that it is shown and offered from now on
        self.addToPlaylist(path, playlist_path)
        if not self.playlist_path and self.current_dir == folder:
            self.readFileList(folder, path)      # the new playlist shows up in the folder

    def addToPlaylist(self, path, playlist_path):
        self.rememberPlaylist(playlist_path)
        playlist = readPlaylist(playlist_path)
        name = os.path.basename(playlist_path)
        if not playlist.add(path):
            self.toast.show(_("Already in %s.") % name)
            return
        if self.savePlaylist(playlist_path, playlist):
            self.toast.show(_("Added to %s.") % name)
            if playlist_path == self.playlist_path:
                self.readFileList("PLAYLIST", playlist_path, path)
