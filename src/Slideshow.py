# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
from random import shuffle
from Screens.HelpMenu import HelpableScreen
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Tools import Notifications
from Tools.LoadPixmap import LoadPixmap
from Components.ActionMap import HelpableActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Button import Button
from Components.config import config
try:
    from Components.MerlinPictureViewerWidget import MerlinPictureViewer
    merlin_picture_viewer = True
except ImportError as e:
    print(f"MDC: optional module not installed: {e}")
    merlin_picture_viewer = False
from Plugins.SystemPlugins.CacheCockpit.FileManager import FileManager
from enigma import ePoint, eSize, eTimer, getDesktop, gPixmapPtr
from skin import colors as colorNames
from .__init__ import _
from .MediaCockpitSummary import MediaCockpitSummary
from .Debug import logger
from .PictureUtils import getPicturePath, rotatePicture, setExifOrientation
from .FileManagerUtils import MDC_IDX_MEDIA, MDC_IDX_PATH, MDC_IDX_META
from .FileManagerUtils import MDC_MEDIA_TYPE_FILE, MDC_MEDIA_TYPE_PICTURE, MDC_MEDIA_TYPE_MOVIE
from .SkinUtils import getSkinPath
from .MediaInfo import MediaInfo
from .DelayTimer import DelayTimer
from .FileUtils import deleteFile
from .ConsoleAppContainer import ConsoleAppContainer
from .FileListUtils import previousIndex, nextIndex
from .ConfigInit import int_slideshow_animations, ext_slideshow_animations
from .Thumbnail import Thumbnail
from .Display import Display
from .Version import ID

TOAST_ID = "MDC_toast"
TOAST_TIMEOUT = 5


def showToast(text, timeout=TOAST_TIMEOUT):
    """A short message that does not stop the slideshow: an info popup (Tools.Notifications) that any key or the timeout
    closes and that replaces the one still showing."""
    Notifications.RemovePopup(TOAST_ID)
    Notifications.AddPopup(text, MessageBox.TYPE_INFO, timeout=timeout, close_on_any_key=True, id=TOAST_ID)


class Slideshow(Screen, Thumbnail, Display, HelpableScreen):

    def __init__(self, session, csel, file_list, file_index, start_slideshow=False, song_list=None):
        logger.info("file_index: %s, start_slideshow: %s, file_list: %s, song_list: %s",
                    file_index, start_slideshow, file_list, song_list)
        self.csel = csel
        self.slideshow_active = False
        self.start_slideshow = start_slideshow
        self["key_red"] = Button(_("Exit"))
        self["key_green"] = Button(_("Slideshow"))
        self["key_yellow"] = Button(_("Rotate picture"))
        self["key_blue"] = Button(_("Toggle Transition"))
        self["bar_background"] = Label()
        self["bar_separator"] = Label()

        Thumbnail.__init__(self)
        Display.__init__(self, self)
        Screen.__init__(self, session)
        HelpableScreen.__init__(self)
        self.skinName = self.__class__.__name__
        self["actions"] = HelpableActionMap(
            self,
            "CockpitActions",
            {
                "OK": (self.toggleButtons, _("Toggle buttons")),
                "INFO": (self.openInfo, _("Information")),
                "PLAY": (self.playpause, _("Play/Pause") + " " + _("Slideshow")),
                "STOP": (self.stop, _("Stop video/slideshow")),
                "NEXT": (self.right, _("Next picture")),
                "RIGHTR": (self.right, _("Next picture")),
                "PREVIOUS": (self.left, _("Previous picture")),
                "LEFTR": (self.left, _("Previous picture")),
                "EXIT": (self.exit, _("Exit")),
                "RED": (self.exit, _("Exit")),
                "GREEN": (self.playpause, _("Slideshow")),
                "YELLOW": (self.yellow, _("Rotate picture")),
                "BLUE": (self.toggleTransitionMode, _("Toggle transition")),
            },
            prio=-1
        )

        self["picture_background"] = Label()
        self["picture"] = Pixmap()

        if not merlin_picture_viewer:
            self["image"] = Pixmap()
            self.slideshow_animations = int_slideshow_animations
            self.animation = int(int_slideshow_animations[0][0])
            self.external_slideshow = False
        else:
            self["image"] = MerlinPictureViewer()
            self["image"].connectImageChanged(self.imageChanged)
            self.slideshow_animations = ext_slideshow_animations
            self.animation = int(ext_slideshow_animations[0][0])
            self.external_slideshow = True

        self.file_list = file_list
        self.file_index = file_index
        self.file = None
        self.song_list = song_list if song_list is not None else []
        self.song_index = 0
        self.song_index_list = list(range(len(self.song_list)))
        self.direction = True
        self.desktop_size = getDesktop(0).size()
        self.slide_timer = eTimer()
        self.slide_timer.callback.append(self.nextSlide)

        self.video_container = ConsoleAppContainer(self.showVideoCallback)
        self.audio_container = ConsoleAppContainer(self.playSongCallback)
        self.black_container = ConsoleAppContainer(self.blackScreenCallback)

        for animation in self.slideshow_animations:
            if animation[0] == config.plugins.mediacockpit.animation.value:
                self.animation = int(animation[0])
                break
        logger.debug("animation: %s", self.animation)

        self.onLayoutFinish.append(self.__onLayoutFinish)

    def createSummary(self):
        return MediaCockpitSummary

    def showButtons(self):
        logger.info("...")
        size = self["picture"].instance.size()
        self["picture"].instance.resize(
            eSize(size.width() * 9 // 10, size.height() * 9 // 10))
        self["picture"].instance.move(
            ePoint(self.desktop_size.width() // 10 // 2, self.desktop_size.height() // 10 // 4))
        self["picture_background"].hide()
        self["bar_background"].show()
        self["bar_separator"].show()
        self["key_red"].show()
        self["key_green"].show()
        self["key_yellow"].show()
        self["key_blue"].show()

    def hideButtons(self):
        logger.info("...")
        self["picture"].instance.resize(
            eSize(self.desktop_size.width(), self.desktop_size.height()))
        self["picture"].instance.move(ePoint(0, 0))
        self["picture_background"].show()
        self["bar_background"].hide()
        self["bar_separator"].hide()
        self["key_red"].hide()
        self["key_green"].hide()
        self["key_yellow"].hide()
        self["key_blue"].hide()

    def toggleButtons(self):
        if self.desktop_size.width() == self["picture"].instance.size().width():
            self.showButtons()
        else:
            self.hideButtons()

    def __onLayoutFinish(self):
        logger.debug("...")
        if self.file_list:
            self.hideButtons()
            self.file = self.file_list[self.file_index]
            self.background_color = colorNames[config.plugins.mediacockpit.picture_background.value]
            self.foreground_color = colorNames[config.plugins.mediacockpit.picture_foreground.value]
            self["picture_background"].instance.setBackgroundColor(
                self.background_color)
            self["picture_background"].instance.invalidate()
            self.slideshow_duration = config.plugins.mediacockpit.slideshow_duration.value * 1000
            if self.external_slideshow:
                self["image"].scaleToScreen(True)
            self.setSlideshowAnimation(self.animation)
            if self.start_slideshow:
                self["image"].show()
                self.start_slideshow = False
                if self.song_list:
                    self["image"].hide()
                    shuffle(self.song_index_list)
                    self.playSong(
                        self.song_list[self.song_index_list[self.song_index]])
                    logger.debug("song_index: %s, song_list: %s",
                                 self.song_index, self.song_list)
                self.playpause()
            else:
                self["image"].hide()
                self.showSlide()
        else:
            self.close(self.file_index)

    def setSlideshowAnimation(self, animation):
        logger.debug("animation: %s", animation)
        for slideshow_animation in self.slideshow_animations:
            if slideshow_animation[0] == str(animation):
                if self.external_slideshow:
                    logger.debug("external: %s", str(animation))
                    self["image"].setTransitionMode(animation)
                else:
                    logger.debug("internal: %s", str(animation))
                    if hasattr(self["picture"].instance, "setShowHideAnimation"):
                        self["picture"].instance.setShowHideAnimation(
                            str(animation))
                        self["picture"].instance.invalidate()
                    else:
                        logger.debug("ePixmap has no setShowHideAnimation - skipping")
                break

    def showLCDInfo(self):
        # logger.info("file_index: %s, len(file_list): %s, slideshow_active: %s", self.file_index, len(self.file_list), self.slideshow_active)
        path = self.file[MDC_IDX_PATH]
        adir = os.path.basename(os.path.dirname(path))
        direction = "> " if self.direction else "< "
        if not self.slideshow_active:
            direction = ""
        self.displayLCD(
            f"{direction}{self.file_index + 1}/{len(self.file_list)}", adir)

# slide functions

    def nextSlide(self):
        self.slide_timer.stop()
        self.stopVideo()
        if self.direction:
            self.file_index = nextIndex(self.file_index, len(self.file_list))
        else:
            self.file_index = previousIndex(
                self.file_index, len(self.file_list))
        logger.info("***************   %s   ******************",
                    self.file_index)
        self.file = self.file_list[self.file_index]
        DelayTimer(500, self.showSlide)

    def showSlide(self):
        logger.info("file_index: %s, len(self.file_list): %s, media: %s",
                    self.file_index, len(self.file_list), self.file[MDC_IDX_MEDIA])
        self.hideButtons()
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE:
            self.show()
            if self.external_slideshow and self.slideshow_active:
                self["image"].setPicture(self.file[MDC_IDX_PATH])
            else:
                self.unhidePicture()
                self.showPicture(self.file[MDC_IDX_PATH])
            if self.slideshow_active:
                self.slide_timer.start(self.slideshow_duration, True)
        elif self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
            self.hide()
            self.showVideo(self.file[MDC_IDX_PATH])
        else:
            logger.debug("skip slide: %s", self.file[MDC_IDX_MEDIA])
            self.nextSlide()
        self.showLCDInfo()

# picture functions

    def showPicture(self, path):
        logger.info("path: %s, index: %s", path, self.file_index)
        path = getPicturePath(path)
        self["picture"].instance.setPixmap(gPixmapPtr())
        picture = LoadPixmap(path, cached=False)
        self["picture"].instance.setPixmap(picture)

    def hidePicture(self):
        logger.info("...")
        self["picture"].hide()
        self["picture_background"].hide()

    def unhidePicture(self):
        logger.info("...")
        self["picture"].show()
        self["picture_background"].show()

# video functions

    def showVideo(self, filename):
        logger.info("filename: %s", filename)
        self["picture"].instance.setPixmap(gPixmapPtr())
        cmd = f"gst-launch-1.0 playbin -v uri='file://{filename}'"
        if self.song_list:
            cmd += ' flags=0x51'
        logger.debug("cmd: %s", cmd)
        self.video_container.execute(cmd)

    def showVideoCallback(self):
        logger.debug("slideshow_active: %s", self.slideshow_active)
        if self.slideshow_active:
            self.nextSlide()

    def stopVideo(self):
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
            logger.debug("media: %s", self.file[MDC_IDX_MEDIA])
            self.video_container.kill()
            self.blackScreen()

    def blackScreen(self):
        logger.info("...")
        filename = getSkinPath("images/black.mvi")
        cmd = f"showiframe {filename}"
        logger.debug("cmd: %s", cmd)
        self.black_container.execute(cmd)

    def blackScreenCallback(self):
        logger.info("...")

# external slideshow

    def toggleTransitionMode(self):
        max_animations = len(ext_slideshow_animations) if self.external_slideshow else len(
            ext_slideshow_animations) + len(int_slideshow_animations)
        self.animation = (self.animation + 1) % max_animations
        self.animation = int(self.slideshow_animations[0][0]) if self.animation < int(
            self.slideshow_animations[0][0]) else self.animation
        logger.debug("animation: %s", self.animation)
        self.setSlideshowAnimation(self.animation)

        sanimation = "n/a"
        for animation in self.slideshow_animations:
            if animation[0] == str(self.animation):
                sanimation = animation[1]
                break
        showToast(_("Animation") + " " + str(self.animation) + ": " + sanimation)

    def imageChanged(self):
        logger.debug("...")
        self.hidePicture()

# song functions

    def playSong(self, afile):
        logger.info("song_index: %s, afile: %s", self.song_index, afile)
        cmd = f"gst-launch-1.0 playbin uri='file://{afile[MDC_IDX_PATH]}' audio-sink='alsasink'"
        logger.debug("cmd: %s", cmd)
        self.audio_container.execute(cmd)

    def playSongCallback(self):
        logger.debug("...")
        self.song_index = (self.song_index + 1) % len(self.song_list)
        self.playSong(self.song_list[self.song_index_list[self.song_index]])

    def stopSong(self):
        logger.info("...")
        self.audio_container.kill()

# picture functions

    def rotatePicture(self):
        logger.debug("file_index: %s", self.file_index)
        path = self.file[MDC_IDX_PATH]
        filename, ext = os.path.splitext(path)
        out_file = in_file = filename + ".transformed" + ext
        if not os.path.exists(in_file):
            in_file = path
        rc = rotatePicture(in_file, out_file, 90)
        if rc:
            self.createThumbnail(path, True)

            orientation = self.file[MDC_IDX_META]["Orientation"]
            new_orientation = orientation  # Default to current orientation
            if orientation == 1:
                new_orientation = 6
            elif orientation == 6:
                new_orientation = 3
            elif orientation == 3:
                new_orientation = 8
            elif orientation == 8:
                new_orientation = 1
                deleteFile(out_file)

            setExifOrientation(path, new_orientation)
            FileManager.getInstance(ID).loadDatabaseFile(path)
            if new_orientation == 1:
                deleteFile(out_file)

        self.showPicture(path)

# key functions

    def exit(self):
        self.slide_timer.stop()
        DelayTimer.stopAll()
        self.stopVideo()
        self.stopSong()
        config.plugins.mediacockpit.animation.value = str(self.animation)
        config.plugins.mediacockpit.animation.save()
        path = self.file[MDC_IDX_PATH]
        logger.debug("file_index: %s, path: %s", self.file_index, path)
        self.close(path)

    def yellow(self):
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE:
            showToast(_("Rotating picture..."))
            self.rotatePicture()

    def right(self):
        self.direction = True
        self.nextSlide()

    def left(self):
        self.direction = False
        self.nextSlide()

    def stop(self):
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
            self.stopVideo()
            DelayTimer(250, self.showVideoCallback)
        else:
            self.slideshow_active = False
            self.slide_timer.stop()
            self.showLCDInfo()

    def playpause(self):
        logger.debug("...")
        self.slideshow_active = not self.slideshow_active
        if self.slideshow_active:
            self.hideButtons()
            self["image"].show()
            self.showSlide()
        else:
            self.slide_timer.stop()
            self.stopVideo()
            self.showLCDInfo()
            self["image"].hide()

    def openInfo(self):
        if not self.slideshow_active and self.file[MDC_IDX_MEDIA] in MDC_MEDIA_TYPE_FILE:
            self.session.openWithCallback(
                self.openInfoCallback, MediaInfo, self.csel, self.file_list, self.file_index)

    def openInfoCallback(self, file_index):
        self.file_index = file_index
        self.__onLayoutFinish()
