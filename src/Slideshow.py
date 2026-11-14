# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
from Screens.HelpMenu import HelpableScreen
from Screens.Screen import Screen
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
from enigma import ePoint, eSize, eTimer, getDesktop, gPixmapPtr
from skin import parseColor
from .__init__ import _
from .MediaCockpitSummary import MediaCockpitSummary
from .Debug import logger
from .PictureUtils import getPicturePath, getExifData, rotatePicture, setExifOrientation
from .PixmapUtils import loadPixmap
from .FileManagerUtils import MDC_IDX_MEDIA, MDC_IDX_PATH
from .FileManagerUtils import MDC_MEDIA_TYPE_PICTURE, MDC_MEDIA_TYPE_MOVIE
from .MediaInfo import MediaInfo
from .DelayTimer import DelayTimer
from .FileUtils import deleteFile
from .SlideshowPlayers import ServicePlayer, BackgroundMusic
from .SlideshowStates import createSlideshowMachine, RUNNING, PICTURE, MOVIE, OTHER
from .FileListUtils import previousIndex, nextIndex, findMediaIndex, getPath
from .ConfigInit import pic_slideshow_animations
from .Thumbnail import Thumbnail
from .Display import Display
from .Toast import Toast
from .Version import ID, PLUGIN

PICTURE_BACKGROUND = "md_surface_container_lowest"   # colour role of the skin: behind pictures that do not fill the screen
INFO_TOAST_TIMEOUT = 5      # seconds the picture number and name stay on the screen


class Slideshow(Screen, Thumbnail, Display, HelpableScreen):
    """The slideshow and the picture viewer. What a key or a timer does is decided by the table in SlideshowStates.py: this
    class turns keys, timers and player events into events of that table (self.sm.dispatch) and performs its actions
    (the do_<action> methods)."""

    def __init__(self, session, csel, file_list, file_index, start_slideshow=False, song_list=None):
        logger.info("file_index: %s, start_slideshow: %s, file_list: %s, song_list: %s",
                    file_index, start_slideshow, file_list, song_list)
        self.csel = csel
        self.sm = createSlideshowMachine(self, self.facts, logger.info)
        self.info_line = ""     # number and name of the picture, what the header shows
        self.start_slideshow = start_slideshow
        self["key_red"] = Button(_("Exit"))
        self["key_green"] = Button(_("Slideshow"))
        self["key_yellow"] = Button(_("Rotate picture"))
        self["key_blue"] = Button(_("Toggle Transition"))
        self["body"] = Label()      # the place of the picture while the buttons are shown (its rectangle is set by the skin)
        self.toast = Toast(self)    # a short message inside the screen (the label "toast" of the skin)

        Thumbnail.__init__(self)
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
                "RED": (self.keyExit, _("Exit")),
                "GREEN": (self.keyPlay, _("Slideshow")),
                "YELLOW": (self.keyYellow, _("Rotate picture")),
                "BLUE": (self.keyBlue, _("Toggle transition")),
            },
            prio=-1
        )

        self["picture_background"] = Label()
        self["picture"] = Pixmap()

        # PicAniCockpit plays the transitions. It is only used when its native module loaded and passed its self-test
        # (available()); otherwise the pictures are simply cut in. The skin has an "image" widget in any case.
        self.picani = picani_viewer and picAniAvailable()
        logger.info("PicAniCockpit: %s", "available" if self.picani else "not available")
        if self.picani:
            self["image"] = TransitionViewer()
            self["image"].connectImageChanged(self.imageChanged)
        else:
            self["image"] = Pixmap()
        self.slideshow_animations = pic_slideshow_animations
        self.animation = int(pic_slideshow_animations[0][0])

        self.file_list = file_list
        self.file_index = file_index
        self.file = None
        self.song_list = song_list if song_list is not None else []
        self.direction = True
        self.desktop_size = getDesktop(0).size()
        self.slide_timer = eTimer()
        self.slide_timer.callback.append(self.slideTimerExpired)
        self.show_timer = None      # DelayTimer of the slide that is about to be shown
        self.manual_navigation = False  # the slide about to be shown was selected with a key, not by the slideshow timer
        self.previous_file = None   # the file that was shown before the current one

        # enigma2 plays the videos, with their sound, and the background music. Only one service plays at a time: the music is
        # suspended while a movie plays and goes on after it.
        self.video = ServicePlayer(self, self.videoEnded, self.videoStarted)
        self.music = BackgroundMusic(self, self.song_list)

        for animation in self.slideshow_animations:
            if animation[0] == config.plugins.mediacockpit.animation.value:
                self.animation = int(animation[0])
                break
        logger.debug("animation: %s", self.animation)

        self.onLayoutFinish.append(self.onLayoutDone)

    def createSummary(self):
        return MediaCockpitSummary

    @property
    def slideshow_active(self):
        return self.sm.state["run"] == RUNNING

    def facts(self):
        """What the table asks for when an event comes in."""
        count = len(self.file_list)
        media = self.file[MDC_IDX_MEDIA] if self.file else None
        loop = config.plugins.mediacockpit.slideshow_loop.value
        return {
            "content": PICTURE if media == MDC_MEDIA_TYPE_PICTURE else MOVIE if media == MDC_MEDIA_TYPE_MOVIE else OTHER,
            "at_end": not loop and self.file_index == (count - 1 if self.direction else 0),
            "at_end_forward": not loop and self.file_index == count - 1,
            "at_end_back": not loop and self.file_index == 0,
            "picani": self.picani,
            "all_failed": self.video.failures >= count,
            "has_media": findMediaIndex(self.file_list) >= 0,
            "autostart": self.start_slideshow,
        }

    # keys, timers and player events: all of them are events of the table

    def keyOk(self):
        self.sm.dispatch("OK")

    def keyInfo(self):
        self.sm.dispatch("INFO")

    def keyPlay(self):
        self.sm.dispatch("PLAY")

    def keyStop(self):
        self.sm.dispatch("STOP")

    def keyNext(self):
        self.sm.dispatch("NEXT")

    def keyPrevious(self):
        self.sm.dispatch("PREV")

    def keyExit(self):
        self.sm.dispatch("EXIT")

    def keyYellow(self):
        self.sm.dispatch("YELLOW")

    def keyBlue(self):
        self.sm.dispatch("BLUE")

    def onLayoutDone(self):
        self.sm.dispatch("LAYOUT_DONE")

    def slideTimerExpired(self):
        self.sm.dispatch("TIMER")

    def videoStarted(self):
        self.sm.dispatch("VIDEO_STARTED")

    def videoEnded(self):
        """The video ended on its own (a stopped or skipped one never gets here)."""
        self.sm.dispatch("VIDEO_ENDED")

    def imageChanged(self):
        self.sm.dispatch("IMAGE_CHANGED")

    # The actions of the table (SlideshowStates.py). Each one does one small thing; which of them a key leads to is decided
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

    def do_prepare(self):
        """The first thing after the layout: the first file, the colours, the transition engine."""
        logger.debug("...")
        self.toast.hide()
        self.hideButtons()
        self.file = self.file_list[self.file_index]
        self.background_color = parseColor(PICTURE_BACKGROUND)
        self["picture_background"].instance.setBackgroundColor(
            self.background_color)
        self["picture_background"].instance.invalidate()
        self.slideshow_duration = config.plugins.mediacockpit.slideshow_duration.value * 1000
        if self.picani:
            self["image"].setTransitionDuration(int(config.plugins.mediacockpit.transition_duration.value))
            self["image"].setQuality(config.plugins.mediacockpit.transition_quality.value)
            self["image"].setBackground(self.background_color)
            self["image"].setKenBurns(config.plugins.mediacockpit.kenburns.value, self.slideshow_duration)
        self.setSlideshowAnimation(self.animation)
        self.start_slideshow = False   # the autostart is used up: openInfoCallback() lays the screen out again

    def do_close_empty(self):
        # nothing to show (empty list or no picture/movie in it): without this the slideshow would skip forever
        self.toast.hide()
        self.close(getPath(self.file_list, self.file_index))

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
        direction = "> " if self.direction else "< "
        if not self.slideshow_active:
            direction = ""
        self.displayLCD(
            f"{direction}{self.file_index + 1}/{len(self.file_list)}", adir)
        # the line in the header, visible while the buttons are shown (a toast while the slideshow runs, see showButtons())
        self.info_line = f"{_('Slideshow')}: {self.file_index + 1}/{len(self.file_list)} - {os.path.basename(path)}"
        self.displayOSD(self.info_line)

    def do_toast_end(self):
        logger.info("end of slideshow")
        self.toast.show(_("End of slideshow"))

    def do_toast_video_failed(self):
        logger.info("end of slideshow: no video can be played")
        self.toast.show(_("Video cannot be played"))

    def do_stop_toast(self):
        self.toast.stop()

    # the slides

    def do_stop_slide_timer(self):
        self.slide_timer.stop()

    def do_arm_slide_timer(self):
        self.slide_timer.start(self.slideshow_duration, True)

    def do_cancel_pending(self):
        """Forget a slide that is waiting for its delay: every navigation would otherwise queue one more slide and a video
        would be started several times."""
        if self.show_timer is not None:
            self.show_timer.stop()
            self.show_timer = None

    def do_go_forward(self):
        self.direction = True
        self.manual_navigation = True

    def do_go_back(self):
        self.direction = False
        self.manual_navigation = True

    def do_advance(self):
        """The next file in the direction of the slideshow becomes the current one."""
        if self.direction:
            self.file_index = nextIndex(self.file_index, len(self.file_list))
        else:
            self.file_index = previousIndex(self.file_index, len(self.file_list))
        logger.info("***************   %s   ******************", self.file_index)
        self.previous_file, self.file = self.file, self.file_list[self.file_index]
        if self.previous_file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
            self.show()     # the screen was hidden for the video: cover the video plane at once, not after the delay below

    def do_schedule_slide(self):
        # The delay lets the video player or the black frame (showiframe) finish before the next slide starts. Between two
        # pictures with PicAniCockpit it would only stretch the hold time: the transition has been prepared long ago.
        if self.picani and MDC_MEDIA_TYPE_MOVIE not in (self.previous_file[MDC_IDX_MEDIA], self.file[MDC_IDX_MEDIA]):
            self.sm.dispatch("SHOW_SLIDE")
        else:
            self.show_timer = DelayTimer(500, self.slideDelayOver)

    def slideDelayOver(self):
        self.show_timer = None
        self.sm.dispatch("SHOW_SLIDE")

    def do_reset_failures(self):
        self.video.failures = 0

    def do_display_picture(self):
        logger.info("file_index: %s, len(self.file_list): %s", self.file_index, len(self.file_list))
        manual, self.manual_navigation = self.manual_navigation, False
        path = getPicturePath(self.file[MDC_IDX_PATH])  # same file as showPicture(): a rotated copy wins
        shown = False
        if self.picani and self.slideshow_active:
            self["image"].show()
            # fast: after a key press the picture is cut in as soon as it is decoded unless it was prepared already
            shown = self["image"].setPicture(path, self.direction, manual)
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
        loop = config.plugins.mediacockpit.slideshow_loop.value
        index = self.file_index
        for _i in range(len(self.file_list)):
            if not loop and index == (len(self.file_list) - 1 if self.direction else 0):
                return
            index = nextIndex(index, len(self.file_list)) if self.direction else previousIndex(index, len(self.file_list))
            afile = self.file_list[index]
            if afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE:
                self["image"].prepare(getPicturePath(afile[MDC_IDX_PATH]), self.direction)
                return
            if afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
                return  # a video comes next: nothing to prepare

    def setSlideshowAnimation(self, animation):
        logger.debug("animation: %s", animation)
        if self.picani and str(animation) in [a[0] for a in self.slideshow_animations]:
            self["image"].setTransitionMode(animation)

    # picture functions

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

    # videos and music

    def do_start_video(self):
        filename = self.file[MDC_IDX_PATH]
        logger.info("filename: %s", filename)
        self.csel.video_played = True   # MediaCockpit has to clear the video plane when it comes back
        self.video.play(filename)

    def do_stop_video(self):
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
            logger.debug("media: %s", self.file[MDC_IDX_MEDIA])
            self.video.stop()

    def do_delay_video_stopped(self):
        DelayTimer(250, self.sm.dispatch, "VIDEO_STOPPED")

    def do_music_start(self):
        self.music.start()

    def do_music_suspend(self):
        self.music.suspend()    # the movie has its own sound and needs the service

    def do_music_resume(self):
        self.music.resume()     # after a movie: the music goes on where it was interrupted

    def do_stop_music(self):
        self.music.stop()

    def do_stop_delays(self):
        DelayTimer.stopAll()

    # transitions

    def do_toggle_transition(self):
        if not self.picani:
            self.toast.show(_("Transitions need PicAniCockpit"))
            return
        # next entry of the list of the engine in use (the ids of PicAniCockpit are not consecutive)
        ids = [animation[0] for animation in self.slideshow_animations]
        index = ids.index(str(self.animation)) if str(self.animation) in ids else -1
        self.animation = int(ids[(index + 1) % len(ids)])
        logger.debug("animation: %s", self.animation)
        self.setSlideshowAnimation(self.animation)

        sanimation = "n/a"
        for animation in self.slideshow_animations:
            if animation[0] == str(self.animation):
                sanimation = animation[1]
                break
        self.toast.show(_("Animation") + " " + str(self.animation) + ": " + sanimation)

    def do_save_animation(self):
        if self.picani:  # without it the list holds only a placeholder, which must not replace the saved choice
            config.plugins.mediacockpit.animation.value = str(self.animation)
            config.plugins.mediacockpit.animation.save()

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
            self.createThumbnail(path, True)

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

        if afile is self.file:  # the slideshow may have moved on while the picture was being rotated
            if self.picani and self.slideshow_active:
                # the viewer still shows the old picture: forget it and cut the rotated one in (no transition)
                self["image"].hide()
                self["image"].show()
                if self["image"].setPicture(getPicturePath(path), self.direction, True):
                    return
                self.unhidePicture()
            self.showPicture(path)

    # information screen, leaving

    def do_open_info(self):
        self.session.openWithCallback(
            self.openInfoCallback, MediaInfo, self.csel, self.file_list, self.file_index)

    def openInfoCallback(self, file_index):
        self.file_index = file_index
        self.sm.dispatch("LAYOUT_DONE")

    def do_close(self):
        path = self.file[MDC_IDX_PATH]
        logger.debug("file_index: %s, path: %s", self.file_index, path)
        self.close(path)
