# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
import glob
from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Screens.LocationBox import LocationBox
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Components.ActionMap import HelpableActionMap
from Components.config import config
from Components.Button import Button
from Components.Sources.StaticText import StaticText
from enigma import getDesktop
from Plugins.SystemPlugins.MountCockpit.MountCockpit import MountCockpit
from Plugins.SystemPlugins.CacheCockpit.FileManager import FileManager
from .__init__ import _
from .Version import ID, PLUGIN
from .Debug import logger
from .FileManagerUtils import FILE_OP_LOAD
from .FileManagerUtils import MDC_IDX_MEDIA, MDC_IDX_PATH, MDC_IDX_TYPE, MDC_IDX_BOOKMARK
from .FileManagerUtils import MDC_TYPE_FILE, MDC_MEDIA_TYPE_FILE, MDC_MEDIA_TYPE_UP, MDC_MEDIA_TYPE_DIR, MDC_MEDIA_TYPE_PLAYLIST, MDC_MEDIA_TYPE_PICTURE, MDC_MEDIA_TYPE_MOVIE, MDC_MEDIA_TYPE_MUSIC, MDC_MEDIA_TYPE_UNAVAILABLE
from .FileListUtils import getFile, getDir, getPath, getIndex, nextIndex, findMediaIndex, splitMediaSongList, scanPlaylistFiles
from .FileUtils import deleteFile, deleteFiles
from .MediaInfo import MediaInfo
from .Tiles import Tiles
from .Slideshow import Slideshow
from .ListStates import createListMachine, SLIDESHOW, PICTURE, MOVIE, MUSIC, DIR, UP, PLAYLIST, UNAVAILABLE, NONE
from .ReturnTarget import ReturnTarget, parentTarget
from .Toast import Toast
from .CockpitPlayer import CockpitPlayer
from .CockpitMusicPlayer import CockpitMusicPlayer
from .ServiceUtils import getService
from .DelayTimer import DelayTimer
from .Transcoder import Transcoder, LISTEN_DELAY
from .ServiceCenter import ServiceCenter
from .FileListUtils import createBookmarkEntries, createParentDirEntry, createUnavailableEntry, sortList, getPosition
from .ConfigInit import MANUAL_SORT
from .OrderUtils import writeOrder, positionsOf, moved
from .MediaCockpitSummary import MediaCockpitSummary
from .FileManagerProgress import FileManagerProgress
from .Menu import Menu
from .SetupScreen import SetupScreen


MEDIA_NAMES = {MDC_MEDIA_TYPE_DIR: DIR, MDC_MEDIA_TYPE_UP: UP, MDC_MEDIA_TYPE_PLAYLIST: PLAYLIST, MDC_MEDIA_TYPE_PICTURE: PICTURE,
               MDC_MEDIA_TYPE_MOVIE: MOVIE, MDC_MEDIA_TYPE_MUSIC: MUSIC, MDC_MEDIA_TYPE_UNAVAILABLE: UNAVAILABLE}   # for the table of ListStates
LOAD_DIR, LOAD_TREE = "dir", "tree"     # the answers of the load cache directory query
PLAYLIST_LOAD_LIMIT = 50    # playlist files that are added to the cache each time a playlist is read


class MediaCockpit(Screen, Tiles, Menu, HelpableScreen):

    def __init__(self, session):
        logger.info("session: %s", session)
        Screen.__init__(self, session)
        self.skinName = "MediaCockpit"
        Tiles.__init__(self, self)
        Menu.__init__(self)
        self.file_list = []
        self.file_index = -1
        self.media_list = []
        self.media_index = -1
        self.song_list = []
        self.playlist_path = ""     # the .m3u whose entries are listed, "" when a folder is shown
        self.first_start = True
        # The live service is restarted and stopped again to clear the video plane ("clear video buffer"). Every play of the
        # service makes the service list search all bouquets (~0.5 s, main thread blocked), so it is only done when needed:
        # whenever the screen is shown, except after a slideshow in which no video was played (the video plane was not touched).
        self.clear_video_buffer = True
        self.video_played = False   # set by the Slideshow when it plays a video
        self.service_center = ServiceCenter()
        self.target = ReturnTarget()    # where the tile screen goes back to when it is shown again
        self.transcoder = Transcoder()  # converts the video that the decoder cannot play, while the player shows it
        self.closed_path = ""       # what the screen that was opened (slideshow, music player) returned
        self.sm = createListMachine(self, self.facts, logger.info)

        self["key_red"] = Button(_("Exit"))
        self["key_green"] = Button(_("Home"))
        self["key_yellow"] = Button(_("Load cache directory"))
        self["key_blue"] = Button(_("Bookmarks"))
        # the buttons bar shows an action key only if its source has a true boolean: StaticText with text, not Button
        self["key_menu"] = StaticText(_("MENU"))
        self["key_info"] = StaticText(_("INFO"))
        self["key_play"] = StaticText(_("PLAY"))
        self["key_previous"] = StaticText(_("Move backward"))   # PREVIOUS / NEXT move the selected file within its folder
        self["key_next"] = StaticText(_("Move forward"))
        self["key_text"] = StaticText(_("Previous directory"))   # TEXT goes up one level
        self["key_0"] = StaticText(_("0"))
        self.toast = Toast(self)    # a short message inside the screen (the label "toast" of the skin)
        self.onLayoutFinish.append(self.toast.hide)
        self.onClose.append(self.toast.stop)

        HelpableScreen.__init__(self)

        self.desktop_size = getDesktop(0).size()

        self["actions"] = HelpableActionMap(
            self,
            "CockpitActions",
            {
                "PLAY": (self.playpause, _("Play/Pause") + " " + _("Slideshow")),
                "CHANNELUPR": (self.prevPage, _("Previous page")),
                "CHANNELDOWNR": (self.nextPage, _("Next page")),
                "RIGHTR": (self.moveRight, _("Next picture")),
                "LEFTR": (self.moveLeft, _("Previous picture")),
                "UPR": (self.moveUp, _("Previous row")),
                "DOWNR": (self.moveDown, _("Next row")),
                "OK": (self.processOk, _("Ok")),
                "INFO": (self.openInfo, _("Information")),
                "MENU": (self.openMenu, _("Context menu")),
                "RED": (self.exit, _("Exit")),
                "GREEN": (self.goHome, _("Home")),
                "YELLOW": (self.loadCacheDir, _("Load cache directory")),
                "BLUE": (self.openBookmarks, _("Menu")),
                "EXIT": (self.keyExit, _("Previous directory")),
                "POWER": (self.exit, _("Exit")),
                "0": (self.moveTop, _("Start of list")),
                "8": (self.showLoadProgress, _("Show load progress")),
                "TEXT": (self.goUp, _("Previous directory")),
                "PREVIOUS": (self.moveBackward, _("Move file backward")),
                "NEXT": (self.moveForward, _("Move file forward")),
            },
            prio=-1
        )

        self.initConfig()
        self.last_service = self.session.nav.getCurrentlyPlayingServiceReference()
        logger.info("self.last_service: %s",
                    self.last_service.toString() if self.last_service else None)
        logger.debug("bookmarks: %s", self.bookmarks)
        self.last_path = config.plugins.mediacockpit.last_path.value
        logger.info("last_path: %s", self.last_path)
        self.target.folder("" if self.last_path in self.bookmarks else os.path.dirname(self.last_path), self.last_path)

        self.onShow.append(self.onDialogShow)
        self.onHide.append(self.onDialogHide)

        self.setTitle(PLUGIN)

    def initConfig(self):
        self.bookmarks = config.plugins.mediacockpit.bookmarks.value
        self.show_dirup_tile = config.plugins.mediacockpit.show_dirup_tile.value

    def onDialogShow(self):
        logger.info("...")
        FileManager.getInstance(ID).onDatabaseLoaded(self.loadList)
        # FileManager.getInstance(ID).onDatabaseChanged(self.loadList)
        clear = self.clear_video_buffer
        self.clear_video_buffer = True
        if clear:
            self.stopService(self.session, self.last_service)
        else:
            logger.debug("no video was played: video plane not touched, nothing to clear")
        if self.first_start:
            self.loadList()

    def loadList(self):
        logger.info("...")
        if self.first_start and config.plugins.mediacockpit.start_home_dir.value:
            self.target.folder("", MountCockpit.getInstance().getHomeDir(ID))
        elif self.target.dir in self.bookmarks and self.target.path == self.target.dir:
            self.target.dir = ""
        # whatever start_home_dir says: the first load is done. Otherwise every show() of the screen (after a slideshow, the
        # player, ...) would read the list again, and start the slideshow again if it was started with PLAY.
        self.first_start = False
        logger.debug("target: %s", self.target)
        self.readFileList(self.target.dir, self.target.path, self.target.take_entry())

    def onDialogHide(self):
        FileManager.getInstance(ID).onDatabaseLoaded()
        FileManager.getInstance(ID).onDatabaseChanged()
        logger.debug("file_index: %s", self.file_index)
        # the entries of a playlist live in any folder: the target is the playlist then, not the folder of the entry
        self.target.remember(self.playlist_path, getDir(self.file_list, self.file_index), getPath(self.file_list, self.file_index))
        logger.info("target: %s", self.target)

    def onSelectionChange(self):
        logger.info("...")      # the red key always leaves, there is nothing to show for the selected tile

    def createSummary(self):
        return MediaCockpitSummary

    def readFileList(self, load_dir, load_path="", cursor_path=""):
        """cursor_path: the entry that gets the cursor when a playlist is read (load_path is the .m3u then)"""
        logger.debug("load_dir: %s, load_path: %s, cursor_path: %s", load_dir, load_path, cursor_path)
        self.hideTiles()
        self.playlist_path = load_path if load_dir == "PLAYLIST" and load_path else ""
        self.current_dir = self.playlist_path or load_dir   # what the tile screen shows when the list is empty
        if load_dir == "":
            self.file_list = createBookmarkEntries(self.bookmarks)
        else:
            self.file_list = []
            if load_dir == "PLAYLIST" and load_path:
                if self.show_dirup_tile:
                    self.file_list.append(createParentDirEntry(load_path))
                playlist = scanPlaylistFiles(load_path)
                load_path = cursor_path
                self.file_list += self.getPlaylistFiles(playlist)
            else:
                if self.show_dirup_tile:
                    self.file_list.append(createParentDirEntry(load_dir))
                self.file_list += sortList(
                    FileManager.getInstance(ID).getDirList(load_dir))
                self.file_list += sortList(
                    FileManager.getInstance(ID).getFileList(load_dir))
        self.media_list, self.song_list = splitMediaSongList(self.file_list)
        self.file_index = getIndex(self.file_list, load_path)
        if self.file_index >= 0:
            logger.debug("file_index: %s, path: %s, len(file_list): %s", self.file_index, getPath(
                self.file_list, self.file_index), len(self.file_list))
        logger.debug("media_index: %s", self.media_index)

        self.sm.dispatch("LIST_READ")

    def getPlaylistFiles(self, playlist):
        """The entries of a playlist in the order of the .m3u (a playlist is not sorted), one for every file of it. A file that
        cannot be found, or that the cache does not have, is an entry of the type unavailable.
        Files that exist but are not in the cache yet (their folder was never loaded) are added to it, up to PLAYLIST_LOAD_LIMIT
        at a time because every one is read from disk (EXIF, thumbnail) in the main thread."""
        file_manager = FileManager.getInstance(ID)
        paths = list(dict.fromkeys(playlist))
        files = {afile[MDC_IDX_PATH]: afile for afile in file_manager.getFileListByList(paths)}
        to_load = [path for path in paths if path not in files and os.path.isfile(path)]
        if to_load:
            logger.info("%s of %s playlist entries are not in the cache", len(to_load), len(paths))
            for path in to_load[:PLAYLIST_LOAD_LIMIT]:
                file_manager.loadDatabaseFile(path)
            files = {afile[MDC_IDX_PATH]: afile for afile in file_manager.getFileListByList(paths)}
            later = [path for path in to_load if path not in files]
            if later:
                logger.warning("not in the cache: %s", later)
                self.toast.show(_("%d entries of the playlist are not in the cache yet. Open the playlist again to add more, or load their directory with the yellow key.") % len(later))
        return [files[path] if path in files else createUnavailableEntry(path) for path in paths]

    def moveBackward(self):
        self.moveEntry(-1)

    def moveForward(self):
        self.moveEntry(1)

    def moveEntry(self, step):
        """Move the selected file one place backward (-1) or forward (+1) in its folder. The order is stored in the folder (a file
        .mediacockpit_order, see OrderUtils) and in the cache, and the folder is shown in the manual sort mode from then on. The
        first move stores the order the files are shown in now, so that nothing else changes place."""
        afile = getFile(self.file_list, self.file_index)
        if not afile or afile[MDC_IDX_TYPE] != MDC_TYPE_FILE or afile[MDC_IDX_MEDIA] not in MDC_MEDIA_TYPE_FILE:
            return      # a folder, the parent tile, a playlist or an unavailable entry has no place of its own
        if self.playlist_path:
            self.toast.show(_("The entries of a playlist cannot be moved."))
            return
        adir = self.current_dir
        files = [entry for entry in self.file_list if entry[MDC_IDX_TYPE] == MDC_TYPE_FILE and entry[MDC_IDX_MEDIA] in MDC_MEDIA_TYPE_FILE]
        names = [os.path.basename(entry[MDC_IDX_PATH]) for entry in files]
        new_names = moved(names, os.path.basename(afile[MDC_IDX_PATH]), step)
        if new_names is None:
            self.toast.show(_("This is the first file.") if step < 0 else _("This is the last file."))
            return
        try:
            writeOrder(adir, new_names)
        except OSError as e:
            logger.error("cannot write the order of %s: %s", adir, e)
            self.toast.show(_("The order cannot be stored: %s") % (e.strerror or e))
            return
        positions = positionsOf(new_names)
        old = {entry[MDC_IDX_PATH]: getPosition(entry) for entry in files}
        FileManager.getInstance(ID).setPositions(
            {path: positions[os.path.basename(path)] for path in old if old[path] != positions[os.path.basename(path)]})
        if config.plugins.mediacockpit.sort.value != MANUAL_SORT:
            config.plugins.mediacockpit.sort.value = MANUAL_SORT
            config.plugins.mediacockpit.sort.save()
            self.toast.show(_("Sort mode set to manual sort."))
        self.readFileList(adir, afile[MDC_IDX_PATH])

    def goHome(self):
        self.changeDir("")

    def goUp(self):
        if self.playlist_path:
            # inside a playlist the entries can live anywhere: up always leads to the folder of the .m3u, cursor on the .m3u
            logger.debug("playlist: %s", self.playlist_path)
            self.changeDir(os.path.dirname(self.playlist_path), self.playlist_path)
            return
        target = parentTarget(self.current_dir, self.bookmarks)
        logger.debug("current_dir: %s, up: %s", self.current_dir, target)
        if target:
            self.changeDir(*target)

    def keyExit(self):
        """EXIT goes up one folder. Only the red key leaves MediaCockpit, so that EXIT, which one presses without thinking to get
        out of a folder, cannot leave it by accident. In the list of favorites there is no folder above: say how to leave."""
        if self.playlist_path or parentTarget(self.current_dir, self.bookmarks):
            self.goUp()
        else:
            self.toast.show(_("Press the red key to leave MediaCockpit."))

    def changeDir(self, target_dir, target_path=""):
        logger.debug("target_dir: %s, target_path: %s",
                     target_dir, target_path)
        if not target_path:
            target_path = target_dir
        self.readFileList(target_dir, target_path)

    # OK, PLAY, the end of reading a list and the closing of the screens that were opened are events of the table (ListStates.py)

    @property
    def slideshow(self):
        """PLAY was pressed and the list is being read: the slideshow starts when it is ready."""
        return self.sm.state["pending"] == SLIDESHOW

    def facts(self):
        """What the table asks for when an event comes in."""
        afile = self.file_list[self.file_index] if self.file_list and 0 <= self.file_index < len(self.file_list) else None
        media = MEDIA_NAMES.get(afile[MDC_IDX_MEDIA], NONE) if afile else NONE
        return {
            "media": media,
            "next_media": MEDIA_NAMES.get(self.file_list[(self.file_index + 1) % len(self.file_list)][MDC_IDX_MEDIA], NONE) if afile else NONE,
            "has_media": findMediaIndex(self.file_list, self.file_index) >= 0 and bool(self.media_list),
            "has_songs": bool(self.song_list),
        }

    def playpause(self):
        self.sm.dispatch("PLAY")

    def processOk(self):
        self.sm.dispatch("OK")

    def SlideshowCallback(self, path):
        self.closed_path = path
        self.sm.dispatch("SLIDESHOW_CLOSED")

    def MusicPlayerCallback(self, path=""):
        self.closed_path = path
        self.sm.dispatch("MUSIC_CLOSED")

    def CockpitPlayerCallback(self, _reopen=False):
        self.transcoder.stop()
        self.sm.dispatch("MOVIE_CLOSED")

    # the actions of the table

    def selectedPath(self):
        afile = getFile(self.file_list, self.file_index)
        return afile[MDC_IDX_PATH] if afile else ""

    def do_change_dir(self):
        self.changeDir(self.selectedPath())

    def do_read_dir(self):
        self.readFileList(self.selectedPath())

    def do_go_up(self):
        self.goUp()

    def do_open_playlist(self):
        self.readFileList("PLAYLIST", self.selectedPath())

    def do_next_entry(self):
        self.file_index = nextIndex(self.file_index, len(self.file_list))

    def do_toast_unavailable(self):
        self.toast.show(_("The file is not available."))

    def do_paint_tiles(self):
        self.paintTiles()

    def do_repaint_tiles(self):
        self.repaintTiles()

    def do_open_music(self):
        """Play the songs of the list, starting with the selected one (the first one if the selected entry is not a song)."""
        afile = getFile(self.file_list, self.file_index)
        path = afile[MDC_IDX_PATH] if afile and afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MUSIC else ""
        logger.info("path: %s, songs: %s", path, len(self.song_list))
        self.hide()
        self.session.openWithCallback(self.MusicPlayerCallback, CockpitMusicPlayer, self.song_list, getIndex(self.song_list, path))

    def do_open_slideshow(self):
        # start at the selected entry, or at the next picture/movie when it is a folder, parent tile or song
        start_path = getPath(self.file_list, findMediaIndex(self.file_list, self.file_index))
        self.media_index = getIndex(self.media_list, start_path)
        self.hide()
        self.session.openWithCallback(self.SlideshowCallback, Slideshow, self,
                                      self.media_list, self.media_index, self.slideshow, self.song_list)

    def do_open_viewer(self):
        """A single picture: the slideshow screen without a running slideshow."""
        self.hide()
        media_index = getIndex(self.media_list, self.selectedPath())
        self.session.openWithCallback(self.SlideshowCallback, Slideshow, self, self.media_list, media_index, False)

    def do_open_movie(self):
        self.hide()
        path = getPath(self.file_list, self.file_index)
        url = self.transcoder.prepare(path)
        if url:
            # ffmpeg needs a moment until it serves the converted video
            DelayTimer(LISTEN_DELAY, self.openMovie, getService(url))
        else:
            self.openMovie(getService(path))

    def openMovie(self, service):
        self.session.openWithCallback(self.CockpitPlayerCallback, CockpitPlayer, service, config.plugins.mediacockpit, True, 0, None, self.service_center)

    def do_restore_after_slideshow(self):
        # the video buffer is cleared by onDialogShow() (self.show() in setTilesCursor), once, and only if a video was played
        self.clear_video_buffer = self.video_played
        self.video_played = False
        self.setTilesCursor(getIndex(self.file_list, self.closed_path))
        self.clear_video_buffer = True   # if the screen was not hidden, onDialogShow() did not consume it

    def do_restore_after_music(self):
        # the cursor goes to the song that was playing last, also when loadList() reads the list again after the screen is shown
        self.target.cursor_on(self.closed_path, bool(self.playlist_path))
        self.clear_video_buffer = False     # only the audio service was used: the video plane is untouched
        self.setTilesCursor(getIndex(self.file_list, self.closed_path))
        self.clear_video_buffer = True      # if the screen was not hidden, onDialogShow() did not consume it

    def do_restore_after_movie(self):
        # the player used the service: the video buffer is cleared by onDialogShow() (self.show() in setTilesCursor)
        self.clear_video_buffer = True
        self.setTilesCursor(self.file_index)

    def setTilesCursor(self, file_index):
        self.show()
        self.file_index = file_index
        self.repaintTiles()     # a picture may have been rotated, a song or video played, ... while the screen was away

    def exit(self):
        logger.info("...")
        last_path = ""
        if self.file_list:
            last_path = getPath(self.file_list, self.file_index)
        config.plugins.mediacockpit.last_path.value = last_path
        config.plugins.mediacockpit.save()
        self.startService(self.session, self.last_service)
        self.close()

    def deleteFile(self):
        afile = getFile(self.file_list, self.file_index)
        if afile and afile[MDC_IDX_TYPE] == MDC_TYPE_FILE and afile[MDC_IDX_MEDIA] != MDC_MEDIA_TYPE_UNAVAILABLE:
            self.session.openWithCallback(self.deleteFileCallback, MessageBox, _(
                "Do you really want to delete the file?"))

    def deleteFileCallback(self, answer=None):
        if answer:
            afile = getFile(self.file_list, self.file_index)
            path = afile[MDC_IDX_PATH]
            filename, ext = os.path.splitext(path)
            logger.debug("filename: %s", filename)
            if afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE:
                # only the picture and its own derived files: IMG_1.* would also take IMG_1.CR2 or IMG_1.mp4 with it
                for sidecar in (path, filename + ".thumbnail" + ext, filename + ".thumbnail.jpg", filename + ".transformed" + ext):
                    deleteFile(sidecar)
            else:
                # recordings have many files with the same stem (.ts.cuts, .eit, .srt, ...)
                deleteFiles(glob.escape(filename) + ".*")
            del self.file_list[self.file_index]
            self.media_list, self.song_list = splitMediaSongList(self.file_list)  # the slideshow must not see the deleted file
            FileManager.getInstance(ID).delete(path)
            if not self.file_index < len(self.file_list):
                self.file_index -= 1
            self.target.path = getPath(self.file_list, self.file_index)
            self.repaintTiles()

    def openInfo(self):
        if self.file_list:
            afile = self.file_list[self.file_index]
            if afile[MDC_IDX_MEDIA] in MDC_MEDIA_TYPE_FILE:
                self.session.openWithCallback(
                    self.setTilesCursor, MediaInfo, self, self.file_list, self.file_index)

    def selectDirectory(self, callback, title):
        logger.debug("bookmarks: %s",
                     config.plugins.mediacockpit.bookmarks.value)
        self.session.openWithCallback(
            callback,
            LocationBox,
            windowTitle=title,
            text=_("Select directory"),
            currDir=config.plugins.mediacockpit.bookmarks.value[0],
            bookmarks=config.plugins.mediacockpit.bookmarks,
            autoAdd=False,
            editDir=True,
            inhibitDirs=["/bin", "/boot", "/dev", "/etc", "/home",
                         "/lib", "/proc", "/run", "/sbin", "/sys", "/usr", "/var"],
            minFree=None
        )

    def openConfigScreen(self):
        logger.info("...")
        self.session.openWithCallback(
            self.openConfigScreenCallback, SetupScreen)

    def openConfigScreenCallback(self, _restart=False):
        logger.info("...")
        self.initConfig()
        self.initTileConfig()

    def openBookmarks(self):
        self.selectDirectory(
            self.openBookmarksCallback,
            _("Bookmarks")
        )

    def openBookmarksCallback(self, path):
        logger.info("path: %s", path)
        self.bookmarks = []
        for bookmark in config.plugins.mediacockpit.bookmarks.value:
            self.bookmarks.append(os.path.normpath(bookmark))
        config.plugins.mediacockpit.bookmarks.value = self.bookmarks[:]
        config.plugins.mediacockpit.bookmarks.save()
        MountCockpit.getInstance().registerBookmarks(
            ID, config.plugins.mediacockpit.bookmarks.value)
        self.target.bookmarks()
        self.readFileList("")

    def stopService(self, session, service):
        logger.debug("clear video buffer")
        session.nav.stopService()
        session.nav.playService(service)
        session.nav.stopService()

    def startService(self, session, service):
        logger.debug("...")
        session.nav.playService(service)

    def showLoadProgress(self):
        self.session.open(FileManagerProgress, FILE_OP_LOAD)

    def loadCacheDir(self):
        adir = getDir(self.file_list, self.file_index)
        if not adir:
            return
        if self.is_mounted:
            # the first entry (this directory only) is the default, EXIT and the last entry abort
            self.session.openWithCallback(
                self.loadCacheDirResponse,
                ChoiceBox,
                title=_("Load the following directory into the cache?") + "\n" + adir,
                list=[
                    (_("This directory only"), LOAD_DIR),
                    (_("This directory and all its subdirectories"), LOAD_TREE),
                    (_("Cancel"), None),
                ],
                windowTitle=_("Load cache directory"),
                allow_cancel=True,
            )
        else:
            self.session.open(
                MessageBox,
                _("Can't load directory because it is not mounted."),
                MessageBox.TYPE_INFO
            )

    def loadCacheDirResponse(self, answer=None):
        if not answer or answer[1] is None:
            logger.info("cancelled")
            return
        adir = getDir(self.file_list, self.file_index)
        recursive = answer[1] == LOAD_TREE
        logger.info("adir: %s, recursive: %s", adir, recursive)
        FileManager.getInstance(ID).loadDatabaseDir(adir, recursive)
        self.session.open(FileManagerProgress, FILE_OP_LOAD)
        self.target.folder(adir, getPath(self.file_list, self.file_index))
        logger.debug("target: %s", self.target)

    def loadCacheBookmark(self):
        if not self.file_list:
            return
        if self.is_mounted:
            self.session.openWithCallback(
                self.loadCacheBookmarkResponse,
                MessageBox,
                _("Do you really want to load the following bookmark?") + "\n" + getFile(self.file_list, self.file_index)[MDC_IDX_BOOKMARK],
                MessageBox.TYPE_YESNO
            )
        else:
            self.session.open(
                MessageBox,
                _("Can't load bookmark because it is not mounted."),
                MessageBox.TYPE_INFO
            )

    def loadCacheBookmarkResponse(self, response):
        if response:
            FileManager.getInstance(ID).loadDatabaseDir(
                getFile(self.file_list, self.file_index)[MDC_IDX_BOOKMARK], True)
            self.session.open(FileManagerProgress, FILE_OP_LOAD)
            self.target.folder(getFile(self.file_list, self.file_index)[MDC_IDX_BOOKMARK])
            logger.debug("target: %s", self.target)
