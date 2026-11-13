# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
import glob
from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Screens.LocationBox import LocationBox
from Screens.MessageBox import MessageBox
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
from .FileManagerUtils import MDC_TYPE_FILE, MDC_MEDIA_TYPE_FILE, MDC_MEDIA_TYPE_UP, MDC_MEDIA_TYPE_DIR, MDC_MEDIA_TYPE_PLAYLIST, MDC_MEDIA_TYPE_PICTURE, MDC_MEDIA_TYPE_MOVIE, MDC_MEDIA_TYPE_MUSIC
from .FileListUtils import getFile, getDir, getPath, getIndex, nextIndex, findMediaIndex, splitMediaSongList, scanPlaylistFiles
from .FileUtils import deleteFile, deleteFiles
from .MediaInfo import MediaInfo
from .Tiles import Tiles
from .Slideshow import Slideshow
from .CockpitPlayer import CockpitPlayer
from .CockpitMusicPlayer import CockpitMusicPlayer
from .ServiceUtils import getService
from .ServiceCenter import ServiceCenter
from .FileListUtils import createBookmarkEntries, createParentDirEntry, sortList
from .MediaCockpitSummary import MediaCockpitSummary
from .FileManagerProgress import FileManagerProgress
from .Menu import Menu
from .SetupScreen import SetupScreen


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
        self.slideshow = False
        self.first_start = True
        # The live service is restarted and stopped again to clear the video plane ("clear video buffer"). Every play of the
        # service makes the service list search all bouquets (~0.5 s, main thread blocked), so it is only done when needed:
        # whenever the screen is shown, except after a slideshow in which no video was played (the video plane was not touched).
        self.clear_video_buffer = True
        self.video_played = False   # set by the Slideshow when it plays a video
        self.service_center = ServiceCenter()
        self.return_dir = ""
        self.return_path = ""
        self.return_entry = ""      # the entry of a playlist that has the cursor when the playlist is restored

        self["key_red"] = Button(_("Delete file"))
        self["key_green"] = Button(_("Home"))
        self["key_yellow"] = Button(_("Load cache directory"))
        self["key_blue"] = Button(_("Bookmarks"))
        # the buttons bar shows an action key only if its source has a true boolean: StaticText with text, not Button
        self["key_menu"] = StaticText(_("MENU"))
        self["key_info"] = StaticText(_("INFO"))
        self["key_play"] = StaticText(_("PLAY"))
        self["key_previous"] = StaticText(_("PREVIOUS"))
        self["key_0"] = StaticText(_("0"))

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
                "RED": (self.deleteFile, _("Delete file")),
                "GREEN": (self.goHome, _("Home")),
                "YELLOW": (self.loadCacheDir, _("Load cache directory")),
                "BLUE": (self.openBookmarks, _("Menu")),
                "EXIT": (self.exit, _("Exit")),
                "POWER": (self.exit, _("Exit")),
                "0": (self.moveTop, _("Start of list")),
                "8": (self.showLoadProgress, _("Show load progress")),
                "PREVIOUS": (self.goUp, _("Previous directory")),
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
        self.return_path = self.last_path
        if self.return_path in self.bookmarks:
            self.return_dir = ""
        else:
            self.return_dir = os.path.dirname(self.return_path)

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
            self.return_dir = ""
            self.return_path = MountCockpit.getInstance().getHomeDir(ID)
            self.first_start = False
        elif self.return_dir in self.bookmarks and self.return_path == self.return_dir:
            self.return_dir = ""
        logger.debug("return_dir: %s, return_path: %s, return_entry: %s",
                     self.return_dir, self.return_path, self.return_entry)
        return_entry, self.return_entry = self.return_entry, ""
        self.readFileList(self.return_dir, self.return_path, return_entry)

    def onDialogHide(self):
        FileManager.getInstance(ID).onDatabaseLoaded()
        FileManager.getInstance(ID).onDatabaseChanged()
        logger.debug("file_index: %s", self.file_index)
        if self.playlist_path:
            # The entries of a playlist live in any folder: the folder of the selected entry would show that folder instead of
            # the playlist when the screen comes back (e.g. after a slideshow).
            self.return_dir = "PLAYLIST"
            self.return_path = self.playlist_path
            self.return_entry = getPath(self.file_list, self.file_index)
        else:
            self.return_dir = getDir(self.file_list, self.file_index)
            self.return_path = getPath(self.file_list, self.file_index)
            self.return_entry = ""
        logger.info("self.return_dir: %s, self.return_path: %s, self.return_entry: %s",
                    self.return_dir, self.return_path, self.return_entry)

    def onSelectionChange(self):
        logger.info("...")
        afile = getFile(self.file_list, self.file_index)
        if afile[MDC_IDX_TYPE] == MDC_TYPE_FILE:
            logger.debug("file")
            self["key_red"].setText(_("Delete file"))
        else:
            logger.debug("no file")
            self["key_red"].setText("")

    def createSummary(self):
        return MediaCockpitSummary

    def readFileList(self, load_dir, load_path="", cursor_path=""):
        """cursor_path: the entry that gets the cursor when a playlist is read (load_path is the .m3u then)"""
        logger.debug("load_dir: %s, load_path: %s, cursor_path: %s", load_dir, load_path, cursor_path)
        self.hideTiles()
        self.playlist_path = load_path if load_dir == "PLAYLIST" and load_path else ""
        if load_dir == "":
            self.file_list = createBookmarkEntries(self.bookmarks)
        else:
            self.file_list = []
            if load_dir == "PLAYLIST" and load_path:
                if self.show_dirup_tile:
                    self.file_list.append(createParentDirEntry(load_path))
                playlist = scanPlaylistFiles(load_path)
                load_path = cursor_path
                # a playlist keeps the order of the .m3u, it is not sorted
                order = {path: i for i, path in enumerate(playlist)}
                files = list(FileManager.getInstance(ID).getFileListByList(playlist))
                files.sort(key=lambda afile: order.get(afile[MDC_IDX_PATH], len(order)))
                self.file_list += files
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

        if self.slideshow:
            self.startSlideshow()
        else:
            self.paintTiles()

    def goHome(self):
        self.changeDir("")

    def goUp(self):
        if self.playlist_path:
            # inside a playlist the entries can live anywhere: up always leads to the folder of the .m3u, cursor on the .m3u
            logger.debug("playlist: %s", self.playlist_path)
            self.changeDir(os.path.dirname(self.playlist_path), self.playlist_path)
            return
        afile = getFile(self.file_list, self.file_index)
        logger.debug("afile: %s", afile)
        path = afile[MDC_IDX_PATH]
        if path not in self.bookmarks:
            adir = os.path.dirname(path)
            if adir in self.bookmarks:
                logger.debug("home")
                path = adir
                adir = ""
            else:
                logger.debug("not home")
                if os.path.splitext(path)[1] != ".m3u":
                    logger.debug("not playlist")
                    path = adir
                    adir = os.path.dirname(adir)
                else:
                    logger.debug("playlist")
            logger.debug("adir: %s, path: %s", adir, path)
            self.changeDir(adir, path)

    def changeDir(self, target_dir, target_path=""):
        logger.debug("target_dir: %s, target_path: %s",
                     target_dir, target_path)
        if not target_path:
            target_path = target_dir
        self.readFileList(target_dir, target_path)

    def startSlideshow(self):
        # start at the selected entry, or at the next picture/movie when it is a folder, parent tile or song
        start_index = findMediaIndex(self.file_list, self.file_index)
        if start_index < 0 or not self.media_list:
            logger.debug("nothing to show")
            self.slideshow = False
            if self.song_list:
                # only songs: the music player plays them, from the selected one
                afile = getFile(self.file_list, self.file_index)
                self.openMusicPlayer(afile[MDC_IDX_PATH] if afile and afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MUSIC else "")
            else:
                self.paintTiles()
            return
        self.hide()
        start_path = getPath(self.file_list, start_index)
        self.media_index = getIndex(self.media_list, start_path)
        self.session.openWithCallback(self.SlideshowCallback, Slideshow, self,
                                      self.media_list, self.media_index, self.slideshow, self.song_list)

    def SlideshowCallback(self, path):
        # the video buffer is cleared by onDialogShow() (self.show() in setTilesCursor), once, and only if a video was played
        self.clear_video_buffer = self.video_played
        self.video_played = False
        self.setTilesCursor(getIndex(self.file_list, path))
        self.clear_video_buffer = True   # if the screen was not hidden, onDialogShow() did not consume it

    def openMusicPlayer(self, path=""):
        """Play the songs of the list, starting with the one at path (the first one if it is not a song of the list)."""
        logger.info("path: %s, songs: %s", path, len(self.song_list))
        self.slideshow = False
        self.hide()
        self.session.openWithCallback(self.MusicPlayerCallback, CockpitMusicPlayer, self.song_list, getIndex(self.song_list, path))

    def MusicPlayerCallback(self, path=""):
        # the cursor goes to the song that was playing last, also when loadList() reads the list again after the screen is shown
        if path:
            if self.playlist_path:
                self.return_entry = path
            else:
                self.return_path = path
        self.clear_video_buffer = False     # only the audio service was used: the video plane is untouched
        self.setTilesCursor(getIndex(self.file_list, path))
        self.clear_video_buffer = True      # if the screen was not hidden, onDialogShow() did not consume it

    def CockpitPlayerCallback(self, _reopen=False):
        # the player used the service: the video buffer is cleared by onDialogShow() (self.show() in setTilesCursor)
        self.clear_video_buffer = True
        self.setTilesCursor(self.file_index)

    def setTilesCursor(self, file_index):
        self.show()
        self.file_index = file_index
        self.slideshow = False
        self.paintTiles()

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
        if afile[MDC_IDX_TYPE] == MDC_TYPE_FILE:
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
            self.return_path = getPath(self.file_list, self.file_index)
            self.paintTiles()

    def playpause(self):
        if self.file_list:
            self.slideshow = True
            afile = self.file_list[self.file_index]
            logger.info("afile: %s", afile)
            if afile[MDC_IDX_MEDIA] in MDC_MEDIA_TYPE_FILE:
                self.startSlideshow()
            elif afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_UP:
                self.file_index = nextIndex(
                    self.file_index, len(self.file_list))
                self.startSlideshow()
            elif afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_DIR:
                self.readFileList(afile[MDC_IDX_PATH])
            elif afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PLAYLIST:
                self.readFileList("PLAYLIST", afile[MDC_IDX_PATH])
            else:
                self.slideshow = False

    def processOk(self):
        if self.file_list:
            self.slideshow = False
            afile = self.file_list[self.file_index]
            path = afile[MDC_IDX_PATH]
            logger.info("path: %s", path)
            if afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_DIR:
                self.changeDir(path)
            elif afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_UP:
                self.goUp()
            elif afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PLAYLIST:
                path = afile[MDC_IDX_PATH]
                self.readFileList("PLAYLIST", path)
            elif afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MUSIC:
                self.openMusicPlayer(path)
            elif afile[MDC_IDX_MEDIA] in [MDC_MEDIA_TYPE_PICTURE, MDC_MEDIA_TYPE_MOVIE]:
                self.hide()
                if afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE:
                    media_index = getIndex(self.media_list, path)
                    self.session.openWithCallback(
                        self.SlideshowCallback, Slideshow, self, self.media_list, media_index, False)
                elif afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
                    self.session.openWithCallback(self.CockpitPlayerCallback, CockpitPlayer, getService(getPath(
                        self.file_list, self.file_index)), config.plugins.mediacockpit, True, 0, None, self.service_center)

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
        self.return_dir = self.return_path = ""
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
        if self.is_mounted:
            self.session.openWithCallback(
                self.loadCacheDirResponse,
                MessageBox,
                _("Do you really want to load the following directory?") + "\n" + getDir(self.file_list, self.file_index),
                MessageBox.TYPE_YESNO
            )
        else:
            self.session.open(
                MessageBox,
                _("Can't load directory because it is not mounted."),
                MessageBox.TYPE_INFO
            )

    def loadCacheDirResponse(self, response):
        if response:
            FileManager.getInstance(ID).loadDatabaseDir(
                getDir(self.file_list, self.file_index), False)
            self.session.open(FileManagerProgress, FILE_OP_LOAD)
            self.return_dir = getDir(self.file_list, self.file_index)
            self.return_path = getPath(self.file_list, self.file_index)
            logger.debug("return_dir: %s, return_path: %s",
                         self.return_dir, self.return_path)

    def loadCacheBookmark(self):
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
            self.return_dir = getFile(self.file_list, self.file_index)[
                MDC_IDX_BOOKMARK]
            self.return_path = ""
            logger.debug("return_dir: %s, return_path: %s",
                         self.return_dir, self.return_path)
