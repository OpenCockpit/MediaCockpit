# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
from Screens.HelpMenu import HelpableScreen
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ActionMap import HelpableActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.Button import Button
from Components.config import config
try:
    from Plugins.SystemPlugins.PicAniCockpit import available as picAniAvailable
    from Plugins.SystemPlugins.PicAniCockpit.TransitionViewer import TransitionViewer
    picani_viewer = True
except Exception as e:  # noqa: BLE001 - optional package, the slideshow must work without it
    print(f"MDC: optional module not installed: {e}")
    picani_viewer = False
from Plugins.SystemPlugins.CacheCockpit.FileManager import FileManager
from enigma import ePoint, eSize, getDesktop, gPixmapPtr
from skin import parseColor
from .__init__ import _
from .MediaCockpitSummary import MediaCockpitSummary
from .Debug import logger
from .PictureUtils import getPicturePath, getExifData, rotatePicture, setExifOrientation
from .PixmapUtils import loadPixmap
from .PictureEdit import isEditable, deletePicture
from .PictureEditScreens import PictureRotate, PictureCrop
from .FileManagerUtils import MDC_IDX_MEDIA, MDC_IDX_PATH
from .FileManagerUtils import FILE_OP_DELETE
from .FileManagerUtils import MDC_MEDIA_TYPE_PICTURE
from .MediaInfo import MediaInfo
from .DelayTimer import DelayTimer
from .FileUtils import deleteFile
from .Slideshow import Slideshow
from .PictureEditorStates import createPictureEditorMachine
from .FileListUtils import findMediaIndex, getPath
from .Display import Display
from .Toast import Toast
from .Version import ID, PLUGIN

PICTURE_BACKGROUND = "md_surface_container_lowest"   # colour role of the skin: behind pictures that do not fill the screen
INFO_TOAST_TIMEOUT = 5      # seconds the picture number and name stay on the screen


class PictureEditor(Screen, Display, HelpableScreen):
    """The picture screen: the viewer, the picture editor (delete, turn, rotate, crop) and the place where a slideshow is shown. The
    slideshow itself, the timer, the videos and the music, is the engine in Slideshow.py with its own table; it tells this screen what to
    show. What a key does here is decided by the table in PictureEditorStates.py: this class turns keys and the messages of the
    slideshow into events of that table (self.sm.dispatch) and performs its actions (the do_<action> methods)."""

    def __init__(self, session, csel, file_list, file_index, start_slideshow=False, song_list=None):
        # only the numbers: the entries carry the EXIF data, a list of 18000 pictures made a log line of 20 MB that blocked the screen for 26 seconds
        logger.info("file_index: %s, start_slideshow: %s, pictures and videos: %s, songs: %s",
                    file_index, start_slideshow, len(file_list), len(song_list or ()))
        self.csel = csel
        self.sm = createPictureEditorMachine(self, self.facts, logger.info)
        self.info_line = ""     # number and name of the picture, what the header shows
        self["key_red"] = Button(_("Delete"))
        self["key_green"] = Button(_("Rotate"))
        self["key_yellow"] = Button(_("Turn 90°"))
        self["key_blue"] = Button(_("Crop"))
        self["body"] = Label()      # the place of the picture while the buttons are shown (its rectangle is set by the skin)
        self.toast = Toast(self)    # a short message inside the screen (the label "toast" of the skin)

        Display.__init__(self, self)
        Screen.__init__(self, session)
        HelpableScreen.__init__(self)
        self.skinName = self.__class__.__name__
        self.setTitle(PLUGIN)       # the header of the window, visible while the buttons are shown
        self["actions"] = HelpableActionMap(
            self,
            "CockpitActions",
            {
                "OK": (self.keyOk, _("Toggle buttons")),
                "INFO": (self.keyInfo, _("Information")),
                "PLAY": (self.keyPlay, _("Play/Pause") + " " + _("Slideshow")),
                "STOP": (self.keyStop, _("Stop video/slideshow")),
                "NEXT": (self.keyNext, _("Next picture")),
                "RIGHTR": (self.keyNext, _("Next picture")),
                "PREVIOUS": (self.keyPrevious, _("Previous picture")),
                "LEFTR": (self.keyPrevious, _("Previous picture")),
                "EXIT": (self.keyExit, _("Exit")),
                "RED": (self.keyRed, _("Delete picture")),
                "GREEN": (self.keyGreen, _("Rotate picture")),
                "YELLOW": (self.keyYellow, _("Rotate picture by 90 degrees")),
                "BLUE": (self.keyBlue, _("Crop picture")),
                "MENU": (self.keyMenu, _("Toggle transition")),
            },
            prio=-1
        )

        self["picture_background"] = Label()
        self["picture"] = Pixmap()
        self.deleted = []       # the paths of the pictures deleted here: the tile screen drops them from its list

        # PicAniCockpit plays the transitions. It is only used when its native module loaded and passed its self-test
        # (available()); otherwise the pictures are simply cut in. The skin has an "image" widget in any case.
        self.picani = picani_viewer and picAniAvailable()
        logger.info("PicAniCockpit: %s", "available" if self.picani else "not available")
        if self.picani:
            self["image"] = TransitionViewer()
            self["image"].connectImageChanged(self.imageChanged)
        else:
            self["image"] = Pixmap()
        self.desktop_size = getDesktop(0).size()

        # The slideshow engine. It needs this screen for its players, and tells it what to show (event()).
        self.slideshow = Slideshow(self, file_list, file_index, song_list, self.picani, start_slideshow)

        self.onLayoutFinish.append(self.onLayoutDone)

    def createSummary(self):
        return MediaCockpitSummary

    # what the slideshow knows, for the table of this screen and for whoever looks at the screen

    @property
    def file_list(self):
        return self.slideshow.file_list

    @property
    def file_index(self):
        return self.slideshow.file_index

    @property
    def file(self):
        return self.slideshow.file

    @property
    def slide_timer(self):
        return self.slideshow.slide_timer

    @property
    def video(self):
        return self.slideshow.video

    @property
    def music(self):
        return self.slideshow.music

    @property
    def slideshow_active(self):
        return self.slideshow.running

    def facts(self):
        """What the table asks for when an event comes in."""
        show = self.slideshow
        return {
            "content": show.content,
            "run": show.sm.state["run"],
            "video": show.sm.state["video"],
            "picani": self.picani,
            "editable": bool(show.file) and isEditable(show.file[MDC_IDX_PATH]),
            "has_media": findMediaIndex(show.file_list) >= 0,
        }

    # keys and the messages of the slideshow: events of the table. PLAY, STOP and the keys that go on and back are the slideshow's.

    def event(self, name):
        """The slideshow tells this screen something (its actions that start with view_)."""
        self.sm.dispatch(name)

    def keyOk(self):
        self.sm.dispatch("OK")

    def keyInfo(self):
        self.sm.dispatch("INFO")

    def keyPlay(self):
        self.slideshow.play()

    def keyStop(self):
        self.slideshow.stop()

    def keyNext(self):
        self.slideshow.next()

    def keyPrevious(self):
        self.slideshow.previous()

    def keyExit(self):
        self.sm.dispatch("EXIT")

    def keyRed(self):
        self.sm.dispatch("RED")

    def keyGreen(self):
        self.sm.dispatch("GREEN")

    def keyYellow(self):
        self.sm.dispatch("YELLOW")

    def keyBlue(self):
        self.sm.dispatch("BLUE")

    def keyMenu(self):
        self.sm.dispatch("MENU")

    def onLayoutDone(self):
        self.sm.dispatch("LAYOUT_DONE")

    def imageChanged(self):
        self.sm.dispatch("IMAGE_CHANGED")

    def markVideoPlayed(self):
        self.csel.video_played = True   # MediaCockpit has to clear the video plane when it comes back

    # The actions of the table (PictureEditorStates.py). Each one does one small thing; which of them a key leads to is decided
    # by the table, not here.

    def showButtons(self):
        """The picture moves into the body of the window, the header and the footer with the keys become visible.

        The key buttons are never hidden: the footer bar draws the buttons that are visible when the screen is shown and does not
        look again when one is shown or hidden later, so buttons hidden at that time (the screen starts without the window) would
        leave the bar empty for good. While the picture covers the screen the bar is covered with it."""
        logger.info("...")
        body = self["body"].instance
        self["picture"].instance.resize(body.size())
        self["picture"].instance.move(body.position())
        self["picture_background"].hide()
        if self.picani and self.slideshow_active:
            # The pictures of the running slideshow cover the window, so its header line would be plain text on the picture,
            # hard to read: the same line as a toast, which has a background.
            self.toast.show(self.info_line, INFO_TOAST_TIMEOUT)
        else:
            self["osd_info"].show()

    def hideButtons(self):
        logger.info("...")
        self["picture"].instance.resize(
            eSize(self.desktop_size.width(), self.desktop_size.height()))
        self["picture"].instance.move(ePoint(0, 0))
        self["picture_background"].show()
        self["osd_info"].hide()

    def do_show_chrome(self):
        self.showButtons()

    def do_hide_chrome(self):
        self.hideButtons()

    def do_hide_toast(self):
        self.toast.hide()       # the line of showButtons() while the slideshow runs

    # the screen

    def do_start_slideshow(self):
        self.slideshow.start()

    def do_prepare(self):
        """The first thing after the layout: the colours, the transition engine. The slideshow has made the first file the current one."""
        logger.debug("...")
        self.toast.hide()
        self.hideButtons()
        self.background_color = parseColor(PICTURE_BACKGROUND)
        self["picture_background"].instance.setBackgroundColor(
            self.background_color)
        self["picture_background"].instance.invalidate()
        if self.picani:
            self["image"].setTransitionDuration(int(config.plugins.mediacockpit.transition_duration.value))
            self["image"].setQuality(config.plugins.mediacockpit.transition_quality.value)
            self["image"].setBackground(self.background_color)
            self["image"].setKenBurns(config.plugins.mediacockpit.kenburns.value, self.slideshow.slideshow_duration)
        self.setSlideshowAnimation(self.slideshow.animation)

    def do_close_empty(self):
        # nothing to show (empty list or no picture/movie in it): without this the slideshow would skip forever
        self.toast.hide()
        self.close(getPath(self.file_list, self.file_index), self.deleted)

    def do_show_screen(self):
        self.show()

    def do_hide_screen(self):
        if self.execing:
            self.hide()
        else:
            # The first slide is started from onLayoutFinish, before the session shows the screen: a hide() now is undone by that
            # show(), and the picture background would cover the video (black first video).
            DelayTimer(1, self.hide)

    def do_image_show(self):
        self["image"].show()

    def do_image_hide(self):
        self["image"].hide()

    def do_hide_picture(self):
        self.hidePicture()

    def do_clear_picture(self):
        # The pictures must be gone when the screen shows again after the video: the next picture is cut in, not faded from the old
        # one, and the old one is not seen for a moment.
        self["picture"].instance.setPixmap(gPixmapPtr())

    def do_lcd_info(self):
        self.showLCDInfo()

    def showLCDInfo(self):
        path = self.file[MDC_IDX_PATH]
        adir = os.path.basename(os.path.dirname(path))
        direction = "> " if self.slideshow.direction else "< "
        if not self.slideshow_active:
            direction = ""
        self.displayLCD(
            f"{direction}{self.file_index + 1}/{len(self.file_list)}", adir)
        # the line in the header, visible while the buttons are shown (a toast while the slideshow runs, see showButtons())
        self.info_line = f"{_('Slideshow')}: {self.file_index + 1}/{len(self.file_list)} - {os.path.basename(path)}"
        self.displayOSD(self.info_line)

    def do_toast_end(self):
        self.toast.show(_("End of slideshow"))

    def do_toast_video_failed(self):
        self.toast.show(_("Video cannot be played"))

    def do_stop_toast(self):
        self.toast.stop()

    # the picture

    def do_display_picture(self):
        show = self.slideshow
        logger.info("file_index: %s, len(self.file_list): %s", self.file_index, len(self.file_list))
        manual, show.manual_navigation = show.manual_navigation, False
        path = getPicturePath(self.file[MDC_IDX_PATH])  # same file as showPicture(): a rotated copy wins
        shown = False
        if self.picani and self.slideshow_active:
            self["image"].show()
            # fast: after a key press the picture is cut in as soon as it is decoded unless it was prepared already
            shown = self["image"].setPicture(path, show.direction, manual)
        if not shown:
            if self.picani:
                self["image"].hide()  # also forgets the old picture: the next slideshow picture is cut in, not faded from it
            self.unhidePicture()
            self.showPicture(self.file[MDC_IDX_PATH])

    def do_restore_picture(self):
        """The slideshow was paused: the viewer's picture is gone with hide(), and imageChanged() had hidden the plain picture
        widget."""
        if self.picani and self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE:
            self.unhidePicture()
            self.showPicture(self.file[MDC_IDX_PATH])

    def do_prepare_next(self):
        """PicAniCockpit decodes and bakes the next picture during the hold time, so its transition starts at once. This is
        called when a transition has finished: a running one owns the layers."""
        path = self.slideshow.nextPicturePath()
        if path:
            self["image"].prepare(getPicturePath(path), self.slideshow.direction)

    def setSlideshowAnimation(self, animation):
        logger.debug("animation: %s", animation)
        if self.picani and str(animation) in [a[0] for a in self.slideshow.slideshow_animations]:
            self["image"].setTransitionMode(animation)

    def showPicture(self, path):
        logger.info("path: %s, index: %s", path, self.file_index)
        path = getPicturePath(path)
        self["picture"].instance.setPixmap(gPixmapPtr())
        picture = loadPixmap(path)
        if picture:
            self["picture"].instance.setPixmap(picture)

    def hidePicture(self):
        logger.info("...")
        self["picture"].hide()
        self["picture_background"].hide()

    def unhidePicture(self):
        logger.info("...")
        self["picture"].show()
        self["picture_background"].show()

    # transitions

    def do_toggle_transition(self):
        if not self.picani:
            self.toast.show(_("Transitions need PicAniCockpit"))
            return
        animation, name = self.slideshow.nextAnimation()
        self.setSlideshowAnimation(animation)
        self.toast.show(_("Animation") + " " + str(animation) + ": " + name)

    # rotating

    def do_rotate_picture(self):
        self.toast.show(_("Rotating picture..."))
        # rotating blocks the main loop for a while: give the toast a chance to be painted first
        DelayTimer(100, self.rotatePicture, self.file)

    def rotatePicture(self, afile):
        logger.debug("afile: %s", afile)
        path = afile[MDC_IDX_PATH]
        filename, ext = os.path.splitext(path)
        out_file = in_file = filename + ".transformed" + ext
        if not os.path.exists(in_file):
            in_file = path
        # clockwise, like the EXIF orientation sequence below (1 -> 6 -> 3 -> 8 -> 1): the rotated copy and the orientation
        # written to the original must show the same thing, otherwise the running slideshow (which decodes the original and
        # applies EXIF) turns the picture the other way than this screen does
        rc = rotatePicture(in_file, out_file, -90)
        if rc:
            FileManager.getInstance(ID).createThumbnail(path, True)

            # From the picture itself: the meta of the list entry is a JSON string (not a dict), and it is the one of the time the
            # list was read, so it is out of date after the first rotation of the same picture.
            orientation = getExifData(path)["Orientation"]
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

        self.redisplay(afile)

    def redisplay(self, afile):
        """Shows the picture of afile again after its file was changed (turned, cropped)."""
        path = afile[MDC_IDX_PATH]
        if afile is self.file:  # the slideshow may have moved on while the picture was being changed
            if self.picani and self.slideshow_active:
                # the viewer still shows the old picture: forget it and cut the new one in (no transition)
                self["image"].hide()
                self["image"].show()
                if self["image"].setPicture(getPicturePath(path), self.slideshow.direction, True):
                    return
                self.unhidePicture()
            self.showPicture(path)

    # the picture editor: delete, rotate by any angle, crop (the screens are in PictureEditScreens.py, the work is in PictureEdit.py)

    def do_toast_not_editable(self):
        self.toast.show(_("This kind of picture cannot be edited"))

    def do_rotate_free(self):
        self.session.openWithCallback(self.editDone, PictureRotate, self.file[MDC_IDX_PATH])

    def do_crop_picture(self):
        self.session.openWithCallback(self.editDone, PictureCrop, self.file[MDC_IDX_PATH])

    def editDone(self, saved):
        """The editor screen was left: when it saved, the thumbnail, the cache entry and the picture on the screen are renewed."""
        if not saved:
            return
        afile = self.file
        path = afile[MDC_IDX_PATH]
        logger.info("edited: %s", path)
        cache = FileManager.getInstance(ID)
        cache.createThumbnail(path, True)       # the thumbnail in the database is made again from the new picture
        cache.loadDatabaseFile(path)
        self.redisplay(afile)

    def do_delete_picture(self):
        name = os.path.basename(self.file[MDC_IDX_PATH])
        self.session.openWithCallback(self.deleteAnswer, MessageBox, _("Delete this picture?") + "\n\n" + name,
                                      MessageBox.TYPE_YESNO, default=False)

    def deleteAnswer(self, answer):
        """The picture is renamed to name.jpg.del (see PictureEdit.deletePicture), leaves the list and the cache, and the next one is shown."""
        if not answer:
            return
        path = self.file[MDC_IDX_PATH]
        if not deletePicture(path):
            self.toast.show(_("The picture could not be deleted"))
            return
        logger.info("deleted: %s", path)
        self.deleted.append(path)
        FileManager.getInstance(ID).execCacheOp(FILE_OP_DELETE, path, None)
        if self.slideshow.removeCurrent():
            self.slideshow.showSlide()
        else:
            self.sm.dispatch("EXIT")        # nothing left to show

    # information screen, leaving

    def do_open_info(self):
        self.session.openWithCallback(
            self.openInfoCallback, MediaInfo, self.csel, self.file_list, self.file_index)

    def openInfoCallback(self, file_index):
        self.slideshow.file_index = file_index
        self.sm.dispatch("LAYOUT_DONE")

    def do_exit_slideshow(self):
        self.slideshow.exit()

    def do_close(self):
        path = self.file[MDC_IDX_PATH]
        logger.debug("file_index: %s, path: %s", self.file_index, path)
        self.close(path, self.deleted)
