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
from .FileManagerUtils import MDC_MEDIA_TYPE_FILE, MDC_MEDIA_TYPE_PICTURE, MDC_MEDIA_TYPE_MOVIE
from .MediaInfo import MediaInfo
from .DelayTimer import DelayTimer
from .FileUtils import deleteFile
from .SlideshowPlayers import ServicePlayer, BackgroundMusic
from .FileListUtils import previousIndex, nextIndex, findMediaIndex, getPath
from .ConfigInit import pic_slideshow_animations
from .Thumbnail import Thumbnail
from .Display import Display
from .Toast import Toast
from .Version import ID, PLUGIN

PICTURE_BACKGROUND = "md_surface_container_lowest"   # colour role of the skin: behind pictures that do not fill the screen
INFO_TOAST_TIMEOUT = 5      # seconds the picture number and name stay on the screen


class Slideshow(Screen, Thumbnail, Display, HelpableScreen):

    def __init__(self, session, csel, file_list, file_index, start_slideshow=False, song_list=None):
        logger.info("file_index: %s, start_slideshow: %s, file_list: %s, song_list: %s",
                    file_index, start_slideshow, file_list, song_list)
        self.csel = csel
        self.slideshow_active = False
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
        self.slide_timer.callback.append(self.nextSlide)
        self.show_timer = None      # DelayTimer of the slide that is about to be shown
        self.manual_navigation = False  # the slide about to be shown was selected with a key, not by the slideshow timer

        # enigma2 plays the videos, with their sound, and the background music. Only one service plays at a time: the music is
        # suspended while a movie plays and goes on after it.
        self.video = ServicePlayer(self, self.showVideoCallback, self.videoStarted)
        self.music = BackgroundMusic(self, self.song_list)

        for animation in self.slideshow_animations:
            if animation[0] == config.plugins.mediacockpit.animation.value:
                self.animation = int(animation[0])
                break
        logger.debug("animation: %s", self.animation)

        self.onLayoutFinish.append(self.__onLayoutFinish)

    def createSummary(self):
        return MediaCockpitSummary

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

    def toggleButtons(self):
        if self.desktop_size.width() == self["picture"].instance.size().width():
            self.showButtons()
        else:
            self.hideButtons()
            self.toast.hide()       # the line of showButtons() while the slideshow runs

    def __onLayoutFinish(self):
        logger.debug("...")
        self.toast.hide()
        if findMediaIndex(self.file_list) >= 0:
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
            if self.start_slideshow:
                self["image"].show()
                self.start_slideshow = False
                if self.song_list:
                    self["image"].hide()
                    self.music.start()
                self.playpause()
            else:
                self["image"].hide()
                self.showSlide()
        else:
            # nothing to show (empty list or no picture/movie in it): without this the slideshow would skip forever
            self.close(getPath(self.file_list, self.file_index))

    def setSlideshowAnimation(self, animation):
        logger.debug("animation: %s", animation)
        if self.picani and str(animation) in [a[0] for a in self.slideshow_animations]:
            self["image"].setTransitionMode(animation)

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

# slide functions

    def atLastSlide(self):
        return self.file_index == (len(self.file_list) - 1 if self.direction else 0)

    def endSlideshow(self, text=None):
        """The running slideshow reached its last picture and "Slideshow endless loop" is off (or it cannot go on)."""
        logger.info("end of slideshow")
        self.slideshow_active = False
        self.slide_timer.stop()
        self.cancelShow()
        self.music.resume()     # the last slide was a movie: the music goes on until the screen is left
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
            # the screen is hidden while a video plays: bring it back, or only a black picture would be left
            self.show()
            self.showButtons()
        self.showLCDInfo()
        self.toast.show(text or _("End of slideshow"))

    def cancelShow(self):
        """Forget a slide that is waiting for its delay: every navigation would otherwise queue one more showSlide() and
        a video would be started several times."""
        if self.show_timer is not None:
            self.show_timer.stop()
            self.show_timer = None

    def nextSlide(self):
        self.slide_timer.stop()
        self.cancelShow()
        self.stopVideo()
        if self.slideshow_active and not config.plugins.mediacockpit.slideshow_loop.value and self.atLastSlide():
            self.endSlideshow()
            return
        if self.direction:
            self.file_index = nextIndex(self.file_index, len(self.file_list))
        else:
            self.file_index = previousIndex(
                self.file_index, len(self.file_list))
        logger.info("***************   %s   ******************",
                    self.file_index)
        previous, self.file = self.file, self.file_list[self.file_index]
        if previous[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
            self.show()     # the screen was hidden for the video: cover the video plane at once, not after the delay below
        # The delay lets the video player or the black frame (showiframe) finish before the next slide starts. Between two
        # pictures with PicAniCockpit it would only stretch the hold time: the transition has been prepared long ago.
        if self.picani and MDC_MEDIA_TYPE_MOVIE not in (previous[MDC_IDX_MEDIA], self.file[MDC_IDX_MEDIA]):
            self.showSlide()
        else:
            self.show_timer = DelayTimer(500, self.showSlide)

    def showSlide(self):
        self.show_timer = None
        logger.info("file_index: %s, len(self.file_list): %s, media: %s",
                    self.file_index, len(self.file_list), self.file[MDC_IDX_MEDIA])
        self.hideButtons()
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE:
            self.video.failures = 0
            self.music.resume()     # after a movie: the music goes on where it was interrupted
            self.show()
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
            if self.slideshow_active:
                self.slide_timer.start(self.slideshow_duration, True)
        elif self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
            # Neither the screen nor the last picture are taken away yet: until the video has its first frame (videoStarted()) the
            # video plane would show what it held before, for a moment. The picture, or the dark background, covers that.
            self.music.suspend()    # the movie has its own sound and needs the service
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

# video functions

    def showVideo(self, filename):
        logger.info("filename: %s", filename)
        if self.video.running():
            logger.debug("already playing")
            return
        self.csel.video_played = True   # MediaCockpit has to clear the video plane when it comes back
        self.video.play(filename)

    def videoStarted(self):
        """The video has its first frame: the picture goes and the screen is hidden, so that the video plane is seen."""
        if self.file[MDC_IDX_MEDIA] != MDC_MEDIA_TYPE_MOVIE or not self.video.running():
            return
        # The pictures must be gone when the screen shows again after the video: the next picture is cut in, not faded from the old
        # one, and the old one is not seen for a moment.
        self["picture"].instance.setPixmap(gPixmapPtr())
        if self.picani:
            self["image"].hide()
        if self.execing:
            self.hide()
        else:
            # The first slide is started from onLayoutFinish, before the session shows the screen: a hide() now is undone by that
            # show(), and the picture background would cover the video (black first video).
            DelayTimer(1, self.hide)

    def showVideoCallback(self):
        """The video ended on its own (a stopped or skipped one never gets here)."""
        logger.debug("slideshow_active: %s, failures: %s", self.slideshow_active, self.video.failures)
        if self.slideshow_active:
            if self.video.failures >= len(self.file_list):
                # every slide failed in a row: carrying on would spin forever
                self.endSlideshow(_("Video cannot be played"))
                return
            self.nextSlide()

    def videoStopped(self):
        """STOP on a video: carry on with the next slide when the slideshow runs."""
        if self.slideshow_active:
            self.nextSlide()
        else:
            self.music.resume()     # no next slide to bring the music back

    def stopVideo(self):
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
            logger.debug("media: %s", self.file[MDC_IDX_MEDIA])
            self.video.stop()

# external slideshow

    def toggleTransitionMode(self):
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

    def imageChanged(self):
        logger.debug("...")
        self.hidePicture()
        if self.picani and self.slideshow_active:
            self.prepareNext()

    def prepareNext(self):
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

# picture functions

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

# key functions

    def exit(self):
        self.slide_timer.stop()
        self.toast.stop()
        DelayTimer.stopAll()
        self.stopVideo()
        self.music.stop()
        if self.picani:  # without it the list holds only a placeholder, which must not replace the saved choice
            config.plugins.mediacockpit.animation.value = str(self.animation)
            config.plugins.mediacockpit.animation.save()
        path = self.file[MDC_IDX_PATH]
        logger.debug("file_index: %s, path: %s", self.file_index, path)
        self.close(path)

    def yellow(self):
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE:
            self.toast.show(_("Rotating picture..."))
            # rotating blocks the main loop for a while: give the toast a chance to be painted first
            DelayTimer(100, self.rotatePicture, self.file)

    def right(self):
        self.direction = True
        self.manual_navigation = True
        self.nextSlide()

    def left(self):
        self.direction = False
        self.manual_navigation = True
        self.nextSlide()

    def stop(self):
        if self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
            self.stopVideo()
            DelayTimer(250, self.videoStopped)
        else:
            self.slideshow_active = False
            self.slide_timer.stop()
            self.showLCDInfo()

    def playpause(self):
        logger.debug("...")
        self.slideshow_active = not self.slideshow_active
        self.cancelShow()
        if self.slideshow_active:
            self.hideButtons()
            self["image"].show()
            self.showSlide()
        else:
            self.slide_timer.stop()
            self.stopVideo()
            self.music.resume()     # a movie was stopped: the music goes on (no effect when none was playing)
            self.showLCDInfo()
            self["image"].hide()
            if self.picani and self.file[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE:
                # the viewer's picture is gone with hide(), and imageChanged() had hidden the plain picture widget
                self.unhidePicture()
                self.showPicture(self.file[MDC_IDX_PATH])

    def openInfo(self):
        if not self.slideshow_active and self.file[MDC_IDX_MEDIA] in MDC_MEDIA_TYPE_FILE:
            self.session.openWithCallback(
                self.openInfoCallback, MediaInfo, self.csel, self.file_list, self.file_index)

    def openInfoCallback(self, file_index):
        self.file_index = file_index
        self.__onLayoutFinish()
