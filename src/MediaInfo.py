# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
import shutil
from datetime import datetime
from enigma import eConsoleAppContainer
from Screens.Screen import Screen
from Screens.HelpMenu import HelpableScreen
from Components.Pixmap import Pixmap
from Components.Button import Button
from Components.Sources.List import List
from Components.ActionMap import HelpableActionMap
from Tools.LoadPixmap import LoadPixmap
from .PixmapUtils import loadPixmap
from .__init__ import _
from .Debug import logger
from .FileManagerUtils import MDC_IDX_PATH, MDC_IDX_MEDIA, MDC_IDX_DATE
from .FileManagerUtils import MDC_MEDIA_TYPE_UP, MDC_MEDIA_TYPE_DIR, MDC_MEDIA_TYPE_PLAYLIST, MDC_MEDIA_TYPE_PICTURE, MDC_MEDIA_TYPE_MOVIE, MDC_MEDIA_TYPE_MUSIC, MDC_MEDIA_TYPE_UNAVAILABLE
from .PictureUtils import getExifData
from .FileUtils import deleteFile
from .SkinUtils import getSkinPath
from .FileListUtils import nextIndex, previousIndex
from .MediaCockpitSummary import MediaCockpitSummary
from .Display import Display


GRAB_SRC_LINK = "/tmp/mediacockpit_grab_src"   # symlink to the movie, see grabThumbnail()
GRAB_TMP = "/tmp/mediacockpit_grab" + ".jpg"   # the grabbed frame (a few KB). Not one literal: gitupdatepics takes a literal ending in .jpg for a skin picture


class MediaInfo(Screen, HelpableScreen, Display):

    def __init__(self, session, csel, file_list, file_index):
        self.csel = csel
        self.file_list = file_list
        self.file_index = file_index
        Screen.__init__(self, session)
        HelpableScreen.__init__(self)
        self.skinName = self.__class__.__name__
        Display.__init__(self, self)

        self["actions"] = HelpableActionMap(
            self,
            "CockpitActions",
            {
                "OK": (self.exit, _("Exit")),
                "RIGHTR": (self.moveRight, _("Next picture")),
                "LEFTR": (self.moveLeft, _("Previous picture")),
                "EXIT": (self.exit, _("Exit")),
                "RED": (self.exit, _("Exit")),
                "GREEN": (self.exit, _("Exit")),
                "BLUE": (self.grabThumbnail, _("Thumbnail"))
            },
            prio=-1
        )

        self.thumbnail = None
        self.setTitle(_("Media Infos"))
        self["list"] = List()
        self["icon"] = Pixmap()
        self["thumbnail"] = Pixmap()
        self["key_red"] = Button(_("Cancel"))
        self["key_green"] = Button(_("Ok"))
        self["key_yellow"] = Button()
        self["key_blue"] = Button(_("Thumbnail"))

        self.icons = {}
        self.icons[MDC_MEDIA_TYPE_PICTURE] = LoadPixmap(
            getSkinPath("images/" + "picture.svg"), cached=True)
        self.icons[MDC_MEDIA_TYPE_MOVIE] = LoadPixmap(
            getSkinPath("images/" + "movie.svg"), cached=True)
        self.icons[MDC_MEDIA_TYPE_MUSIC] = LoadPixmap(
            getSkinPath("images/" + "music.svg"), cached=True)
        self.icons[MDC_MEDIA_TYPE_DIR] = LoadPixmap(
            getSkinPath("images/" + "folder.svg"), cached=True)
        self.icons[MDC_MEDIA_TYPE_PLAYLIST] = LoadPixmap(
            getSkinPath("images/" + "playlist.svg"), cached=True)
        self.icons[MDC_MEDIA_TYPE_UNAVAILABLE] = LoadPixmap(
            getSkinPath("images/" + "unavailable.svg"), cached=True)
        self.icons[MDC_MEDIA_TYPE_UP] = LoadPixmap(
            getSkinPath("images/" + "dirup.svg"), cached=True)

        self.container = eConsoleAppContainer()
        self.container.appClosed.append(self.grabThumbnailCallback)
        self.onLayoutFinish.append(self.firstStart)

    def createSummary(self):
        return MediaCockpitSummary

    def firstStart(self):
        self.fillList()

    def moveLeft(self):
        self.file_index = previousIndex(self.file_index, len(self.file_list))
        self.fillList()

    def moveRight(self):
        self.file_index = nextIndex(self.file_index, len(self.file_list))
        self.fillList()

    def exit(self):
        if self.container.running():
            # no callback into a closed screen
            self.container.appClosed.remove(self.grabThumbnailCallback)
            self.container.kill()
            self.removeGrabFiles()
        self.close(self.file_index)

    def removeGrabFiles(self):
        for path in (GRAB_SRC_LINK, GRAB_TMP):
            if os.path.lexists(path):
                deleteFile(path)

    def grabThumbnail(self):
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE and not self.container.running():
            self["key_blue"].hide()
            filename = os.path.splitext(self.file[MDC_IDX_PATH])[0]
            self.thumbnail = filename + ".thumbnail.jpg"
            # enigma2 splits the command line itself and cannot escape a quote inside quotes, so a file name with an apostrophe
            # (or a space, if it were not quoted) cannot be passed. ffmpeg reads and writes names of our own instead.
            self.removeGrabFiles()
            try:
                os.symlink(self.file[MDC_IDX_PATH], GRAB_SRC_LINK)
            except OSError as e:
                logger.error("cannot link %s: %s", self.file[MDC_IDX_PATH], e)
                self["key_blue"].show()
                return
            cmd = f"ffmpeg -v quiet -i {GRAB_SRC_LINK} -ss 0.5 -vf scale=320:-1 -vframes 1 {GRAB_TMP} -y"
            self.container.execute(cmd)

    def grabThumbnailCallback(self, retval):
        thumbnail = self.thumbnail
        stored = False
        if retval == 0 and os.path.exists(GRAB_TMP) and os.path.getsize(GRAB_TMP) > 0:
            # copy next to the movie under a temporary name and rename, so a half copied file is never taken as a thumbnail
            tmp = thumbnail + ".tmp"
            try:
                shutil.copyfile(GRAB_TMP, tmp)
                os.replace(tmp, thumbnail)
                stored = True
            except OSError as e:
                logger.error("cannot store %s: %s", thumbnail, e)
                deleteFile(tmp)
        else:
            logger.info("no thumbnail grabbed, retval: %s", retval)
        self.removeGrabFiles()
        # the user may have moved on to another entry while ffmpeg was running
        is_current = self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE and thumbnail == os.path.splitext(self.file[MDC_IDX_PATH])[0] + ".thumbnail.jpg"
        if is_current:
            self["key_blue"].show()
            if stored:
                self.showThumbnail(thumbnail)

    def fillList(self):
        self.file = self.file_list[self.file_index]
        self.displayLCD(f"{self.file_index + 1}/{len(self.file_list)}",
                        os.path.basename(self.file[MDC_IDX_PATH]))
        self["thumbnail"].hide()
        ptr = self.icons.get(self.file[MDC_IDX_MEDIA]) or self.icons.get(MDC_MEDIA_TYPE_UNAVAILABLE)
        if ptr:     # an icon that could not be loaded is left out, nothing fails
            self["icon"].instance.setPixmap(ptr)
            self["icon"].show()
        else:
            self["icon"].hide()
        alist = []
        alist.append((_("Directory"), os.path.dirname(
            self.file[MDC_IDX_PATH]), None))
        alist.append((_("Filename"), os.path.basename(
            self.file[MDC_IDX_PATH]), None))
        date_time = datetime.fromtimestamp(
            self.file[MDC_IDX_DATE]).strftime("%Y-%m-%d %H:%M:%S")
        alist.append((_("Date"), date_time, None))
        alist.append(("", "", None))
        filename, ext = os.path.splitext(self.file[MDC_IDX_PATH])
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE:
            self["key_blue"].hide()
            exif_data = getExifData(self.file[MDC_IDX_PATH])
            logger.debug("exif_data: %s", str(exif_data))
            thumbnail = filename + ".thumbnail" + ext
            self.showThumbnail(thumbnail)
            MeteringModeDesc = (_("unknown"), "Average", "Center-weighted Average",
                                "Spot", "Multi-spot", "Multi-segment", "Partial", "Other")
            OrientDesc = ("Top-Left(0)", "Top-Left(1)", "Top-Right", "Bottom-Right",
                          "Bottom-Left", "Left-Top", "Right-Top", "Right-Bottom", "Left-Bottom")
            ExposureProgram = (_("not defined"), "Manual", "Program", "Aperture priority",
                               "Shutter priority", "Creative", "Action", "Portrait", "Landscape")

            if "Model" in exif_data:
                alist.append((_("Model"), exif_data["Model"], None))
            if "Producer" in exif_data:
                alist.append((_("Producer"), exif_data["Producer"], None))
            if "DateTimeOriginal" in exif_data:
                alist.append((_("Date") + "/" + _("Time"), exif_data["DateTimeOriginal"], None))
            if "ExifImageWidth" in exif_data and "ExifImageHeight" in exif_data:
                alist.append((_("Width") + "/" + _("Height"), f"{exif_data['ExifImageWidth']}x{exif_data['ExifImageHeight']}", None))
            if "Orientation" in exif_data:
                alist.append((_("Orientation"), OrientDesc[exif_data["Orientation"]], None))
            if "Flash" in exif_data:
                alist.append((_("Flash"), str(exif_data["Flash"]), None))
            if "MeteringMode" in exif_data:
                alist.append((_("Metering Mode"), MeteringModeDesc[exif_data["MeteringMode"]], None))
            if "ISOSpeedRating" in exif_data:
                alist.append((_("ISO Speed Rating"), exif_data["ISOSpeedRating"], None))
            if "PhotographicSensitivity" in exif_data:
                alist.append((_("Photographic Sensitivity"), exif_data["PhotographicSensitivity"], None))
            if "ExposureProgram" in exif_data:
                alist.append((_("Exposure Program"), ExposureProgram[exif_data["ExposureProgram"]], None))
            if "Software" in exif_data:
                alist.append((_("Software"), exif_data["Software"], None))
            if "GPSAltitude" in exif_data:
                alist.append((_("GPS Altitude"), exif_data["GPSAltitude"], None))
            if "GPSLatitude" in exif_data and "GPSLongitude" in exif_data:
                alist.append((_("GPS Latitude"), exif_data["GPSLatitude"], None))
                alist.append((_("GPS Longitude"), exif_data["GPSLongitude"], None))
            if "ExifVersion" in exif_data:
                alist.append((_("Exif Version"), exif_data["ExifVersion"], None))
        elif self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
            self["key_blue"].show()
            thumbnail = filename + ".thumbnail.jpg"
            self.showThumbnail(thumbnail)
        self["list"].setList(alist)
        self["list"].master.downstream_elements.setSelectionEnabled(0)

    def showThumbnail(self, path):
        if os.path.exists(path):
            ptr = loadPixmap(path)
            if ptr:
                self["thumbnail"].instance.setPixmap(ptr)
                self["thumbnail"].show()
                self["icon"].hide()
