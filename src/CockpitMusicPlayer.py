# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
import weakref
from enigma import ePicLoad, iPlayableService, iServiceInformation
from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Components.ActionMap import HelpableActionMap
from Components.Button import Button
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Components.Sources.COCCurrentService import COCCurrentService
from Components.ServiceEventTracker import ServiceEventTracker
from Tools.LoadPixmap import LoadPixmap
from .__init__ import _
from .Debug import logger
from .Display import Display
from .FileManagerUtils import MDC_IDX_PATH
from .MediaCockpitSummary import MediaCockpitSummary
from .SkinUtils import getSkinPath
from .SlideshowPlayers import ServicePlayer
from .SongQueue import SongQueue, REPEAT_ALL, REPEAT_ONE
from .MusicStates import createMusicMachine
from .Version import PLUGIN

EMBEDDED_COVER = "/tmp/.id3coverart"    # written by the gst service when the song has a picture inside
# The cover of the folder of a song. The names are put together: gitupdatepics takes every literal like "name.jpg" in a source
# for a picture of the skin and complains that it is missing.
FOLDER_COVER_NAMES = ("folder", "Folder", "cover", "Cover", "coverArt")
FOLDER_COVER_EXTENSIONS = (".png", ".jpg")
SEEK_SECONDS = 30
PTS_PER_SECOND = 90000


class CockpitMusicPlayer(Screen, HelpableScreen, Display):
    """Plays the songs of a list one after the other through enigma2's own service (no extra decoder, no extra process).

    song_list: the song entries of MediaCockpit (the path is at MDC_IDX_PATH), song_index: the one to start with.
    Closes with the path of the song that was playing last.

    What a key does is decided by the table in MusicStates.py: the key methods of this class turn keys and player events into
    events of that table (self.sm.dispatch) and the do_<action> methods perform its actions."""

    def __init__(self, session, song_list, song_index):
        logger.info("song_index: %s, songs: %s", song_index, len(song_list))
        self.song_list = song_list
        self.queue = SongQueue(len(song_list), song_index)
        self.sm = createMusicMachine(self, self.facts, logger.info)
        Screen.__init__(self, session)
        HelpableScreen.__init__(self)
        self.skinName = "CockpitMusicPlayer"
        Display.__init__(self, self)
        self.setTitle(PLUGIN)       # the header of the full size window, as in the tile screen: title and osd_info text

        self["actions"] = HelpableActionMap(
            self,
            "CockpitActions",
            {
                "EXIT": (self.exit, _("Exit")),
                "RED": (self.exit, _("Exit")),
                "STOP": (self.exit, _("Stop playback")),
                "PLAY": (self.playpause, _("Play/Pause") + " " + _("Song")),
                "OK": (self.playSelected, _("Play selected song")),
                "RIGHTR": (self.playNext, _("Next song")),
                "NEXT": (self.playNext, _("Next song")),
                "LEFTR": (self.playPrevious, _("Previous song")),
                "PREVIOUS": (self.playPrevious, _("Previous song")),
                "UPR": (self.moveUp, _("Previous row")),
                "DOWNR": (self.moveDown, _("Next row")),
                "CHANNELUP": (self.seekForward, _("Skip forward")),
                "CHANNELDOWN": (self.seekBackward, _("Skip backward")),
                "GREEN": (self.toggleShuffle, _("Toggle shuffle")),
                "YELLOW": (self.toggleRepeat, _("Toggle repeat")),
            },
            prio=-1
        )

        self["Service"] = COCCurrentService(session.nav, self)   # position, length and remaining time of the skin
        self["cover"] = Pixmap()
        self["icon"] = Pixmap()
        self["song_title"] = Label()
        self["artist"] = Label()
        self["album"] = Label()
        self["details"] = Label()
        self["status"] = Label()
        self["next_title"] = Label()
        self["shuffle"] = Label()
        self["repeat"] = Label()
        self["list"] = List()
        self["key_red"] = Button(_("Exit"))
        self["key_green"] = Button(_("Shuffle"))
        self["key_yellow"] = Button(_("Repeat"))
        self["key_blue"] = Button()
        self["key_play"] = StaticText(_("PLAY"))
        self["key_previous"] = StaticText(_("PREVIOUS"))
        self["key_next"] = StaticText(_("NEXT"))

        self.player = ServicePlayer(self, self.songEnded)
        self.tags = None           # what the labels show now, to skip updates that change nothing
        self.cover_size = None
        self.icon_pixmap = None
        self.cover_busy = False     # ePicLoad decodes one picture at a time
        self.cover_next = None      # the one to decode when it is done
        self.picload = ePicLoad()
        # no bound method of this screen: the signal would keep it alive after it is closed
        ref = weakref.ref(self)
        self.picload_callback = lambda info="", r=ref: r() and r().coverDecoded()
        self.picload.PictureData.get().append(self.picload_callback)

        self._event_tracker = ServiceEventTracker(
            screen=self,
            eventmap={
                iPlayableService.evUpdatedInfo: self.updateTags,
                iPlayableService.evUpdateTags: self.updateTags,
                iPlayableService.evUpdateIDv3Cover: self.embeddedCover,
            }
        )
        self.onClose.append(self.cleanup)
        self.onLayoutFinish.append(self.firstStart)

    def createSummary(self):
        return MediaCockpitSummary

    def cleanup(self):
        self.player.stop()
        self.picload.PictureData.get().remove(self.picload_callback)

    def firstStart(self):
        logger.debug("...")
        self.sm.dispatch("START")

    def facts(self):
        """What the table asks for when an event comes in."""
        return {
            "has_next": self.queue.peekNext() >= 0,
            "all_failed": self.player.failures >= len(self.song_list),
        }

    # keys and player events: all of them are events of the table

    def songEnded(self):
        """The song ended on its own, or could not be played."""
        self.sm.dispatch("SONG_ENDED")

    def playNext(self):
        self.sm.dispatch("NEXT")

    def playPrevious(self):
        self.sm.dispatch("PREV")

    def playSelected(self):
        self.sm.dispatch("OK")

    def playpause(self):
        self.sm.dispatch("PLAY")

    def seekForward(self):
        self.sm.dispatch("SEEK_FORWARD")

    def seekBackward(self):
        self.sm.dispatch("SEEK_BACKWARD")

    def toggleShuffle(self):
        self.sm.dispatch("SHUFFLE")

    def toggleRepeat(self):
        self.sm.dispatch("REPEAT")

    def moveUp(self):
        self.sm.dispatch("UP")

    def moveDown(self):
        self.sm.dispatch("DOWN")

    def exit(self):
        self.sm.dispatch("EXIT")

    # the actions of the table (MusicStates.py)

    def do_init_widgets(self):
        self.cover_size = self["cover"].instance.size()
        icon_size = self["icon"].instance.size()
        self.icon_pixmap = LoadPixmap(getSkinPath("images/music.svg"), cached=True, width=icon_size.width(), height=icon_size.height())

    def do_fill_list(self):
        self.fillList()

    def do_show_modes(self):
        self.showModes()

    def do_play_current(self):
        if self.queue.current < 0:
            return
        path = self.currentPath()
        logger.info("position: %s, path: %s", self.queue.position, path)
        self.player.stop()
        self.tags = None
        self.showFile(path)
        self.player.play(path)
        self.showState(_("Playing"))
        self.showPosition()

    def do_stop_player(self):
        self.player.stop()

    def do_show_cannot_play(self):
        logger.warning("no song can be played")
        self.showState(_("Cannot play"))

    def do_show_stopped(self):
        self.showState(_("Stopped"))

    def do_show_position(self):
        self.showPosition()

    def do_queue_next(self):
        self.queue.next()

    def do_queue_previous(self):
        self.queue.previous()

    def do_queue_ended(self):
        self.queue.songEnded()

    def do_select_song(self):
        position = self["list"].getIndex()
        if position is not None and 0 <= position < len(self.song_list):
            self.queue.position = position

    def do_pause(self):
        self.pauseService(True)

    def do_unpause(self):
        self.pauseService(False)

    def pauseService(self, pause):
        service = self.session.nav.getCurrentService()
        pausable = service.pause() if service else None
        if pausable:
            if pause:
                pausable.pause()
            else:
                pausable.unpause()
            self.showState(_("Paused") if pause else _("Playing"))

    def do_seek_forward(self):
        self.seekRelative(1)

    def do_seek_backward(self):
        self.seekRelative(-1)

    def seekRelative(self, direction):
        seekable = self.getSeek()
        if seekable and self.player.running():
            seekable.seekRelative(direction, SEEK_SECONDS * PTS_PER_SECOND)

    def do_toggle_shuffle(self):
        self.queue.toggleShuffle()
        self.fillList()
        self.showModes()

    def do_toggle_repeat(self):
        self.queue.cycleRepeat()
        self.showModes()

    def do_move_up(self):
        self["list"].selectPrevious()

    def do_move_down(self):
        self["list"].selectNext()

    def do_close(self):
        logger.info("position: %s", self.queue.position)
        self.close(self.currentPath())

    # play order

    def currentFile(self):
        return self.song_list[self.queue.current]

    def currentPath(self):
        return self.currentFile()[MDC_IDX_PATH] if self.song_list else ""

    # What the COCCurrentService source ("Service" of the skin) and the COCServicePosition converters ask their player for: the
    # screen is that player. Without getLength() the skin cannot be loaded (the progress bar fails, and every widget after it
    # is missing). Lengths and positions are in 90 kHz units, None when nothing is playing.

    def getSeek(self):
        service = self.session.nav.getCurrentService()
        return service.seek() if service else None

    def getLength(self):
        seek = self.getSeek()
        if seek is None:
            return None
        length = seek.getLength()
        return 0 if length[0] else length[1]

    def getPosition(self):
        seek = self.getSeek()
        if seek is None:
            return None
        position = seek.getPlayPosition()
        return 0 if position[0] else position[1]

    def getCutList(self):
        return []

    def getInfo(self):
        service = self.session.nav.getCurrentService()
        return service.info() if service else None

    def getEvent(self):
        return None

    # what the screen shows

    def songTitle(self, afile):
        return os.path.splitext(os.path.basename(afile[MDC_IDX_PATH]))[0]

    def fillList(self):
        self["list"].setList([(str(position + 1), self.songTitle(self.song_list[song])) for position, song in enumerate(self.queue.order)])
        self["list"].setIndex(self.queue.position)

    def showModes(self):
        self["shuffle"].setText(_("Shuffle") + ": " + (_("on") if self.queue.shuffle else _("off")))
        repeat = {REPEAT_ALL: _("all"), REPEAT_ONE: _("song")}.get(self.queue.repeat, _("off"))
        self["repeat"].setText(_("Repeat") + ": " + repeat)
        self.showNext()

    def showNext(self):
        song = self.queue.peekNext()
        self["next_title"].setText(_("Next") + ": " + self.songTitle(self.song_list[song]) if song >= 0 else "")

    def showState(self, text):
        self["status"].setText(text)

    def showPosition(self):
        self["list"].setIndex(self.queue.position)
        self.showNext()
        self.displayLCD(f"{self.queue.position + 1}/{len(self.song_list)}", self.songTitle(self.currentFile()))
        self.displayOSD(f"{_('Music player')}: {self.queue.position + 1}/{len(self.song_list)} - {os.path.dirname(self.currentPath())}")

    def showFile(self, path):
        """The song is about to start: its tags are not known yet, show what the file name says."""
        self.setTexts(os.path.splitext(os.path.basename(path))[0], "", "", "")
        self.cover_next = None
        self.showIcon()
        self.showFolderCover(path)

    def setTexts(self, title, artist, album, details):
        self["song_title"].setText(title)
        self["artist"].setText(artist)
        self["album"].setText(album)
        self["details"].setText(details)

    def updateTags(self):
        if not self.player.running():
            return
        service = self.session.nav.getCurrentService()
        if not service:
            return
        info = service.info()
        title = info.getInfoString(iServiceInformation.sTagTitle)
        artist = info.getInfoString(iServiceInformation.sTagArtist)
        album = info.getInfoString(iServiceInformation.sTagAlbum)
        genre = info.getInfoString(iServiceInformation.sTagGenre)
        year = info.getInfoString(iServiceInformation.sTagDate)
        number = info.getInfo(iServiceInformation.sTagTrackNumber)
        count = info.getInfo(iServiceInformation.sTagTrackCount)
        tags = (title, artist, album, genre, year, number, count)
        if tags == self.tags:
            return
        self.tags = tags
        track = ""
        if number and number > 0:
            track = _("Track") + f" {number}/{count}" if count and count > 0 else _("Track") + f" {number}"
        details = " - ".join(part for part in (genre, year, track) if part)
        file_title = self.songTitle(self.currentFile())
        logger.debug("title: %s, artist: %s, album: %s, details: %s", title, artist, album, details)
        self.setTexts(title or file_title, artist, album, details)
        self.displayLCD(f"{self.queue.position + 1}/{len(self.song_list)}", title or file_title)

    # cover

    def showIcon(self):
        self["cover"].hide()
        if self.icon_pixmap:
            self["icon"].instance.setPixmap(self.icon_pixmap)
        self["icon"].show()

    def showFolderCover(self, path):
        adir = os.path.dirname(path)
        for name in FOLDER_COVER_NAMES:
            for extension in FOLDER_COVER_EXTENSIONS:
                cover = os.path.join(adir, name + extension)
                if os.path.isfile(cover):
                    logger.debug("cover of the folder: %s", cover)
                    self.decodeCover(cover)
                    return

    def embeddedCover(self):
        if self.player.running():
            logger.debug("cover inside the song")
            self.decodeCover(EMBEDDED_COVER)

    def decodeCover(self, path):
        if not self.cover_size:
            return
        if self.cover_busy:
            self.cover_next = path
            return
        self.startCoverDecode(path)

    def startCoverDecode(self, path):
        self.cover_busy = True
        # width, height, keep aspect, aspect style, no cache, better resize, background (the cover is letterboxed), auto rotate
        self.picload.setPara([self.cover_size.width(), self.cover_size.height(), 1, 1, 0, 1, "#ff000000", True])
        if self.picload.startDecode(path):
            logger.warning("cannot decode the cover: %s", path)
            self.cover_busy = False

    def coverDecoded(self):
        self.cover_busy = False
        if self.cover_next:
            path, self.cover_next = self.cover_next, None
            self.startCoverDecode(path)     # the song has changed meanwhile: this picture is out of date
            return
        pixmap = self.picload.getData()
        if pixmap:
            self["cover"].instance.setPixmap(pixmap)
            self["cover"].show()
            self["icon"].hide()
