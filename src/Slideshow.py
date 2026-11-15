# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# The slideshow engine: the list of the files, which one is the current one, the timer of the slides, the videos and the music.
# What it does on a key, a timer or a player event is decided by the table in SlideshowStates.py. It knows nothing about widgets:
# the screen (PictureEditor.py) is its "view", and what the screen has to show is told to it by the actions that start with view_
# (each of them is one event of the table of the screen, PictureEditorStates.py).

from Components.config import config
from enigma import eTimer
from .Debug import logger
from .FileManagerUtils import MDC_IDX_MEDIA, MDC_IDX_PATH
from .FileManagerUtils import MDC_MEDIA_TYPE_PICTURE, MDC_MEDIA_TYPE_MOVIE
from .DelayTimer import DelayTimer
from .SlideshowPlayers import ServicePlayer, BackgroundMusic
from .SlideshowStates import createSlideshowMachine, RUNNING, PICTURE, MOVIE, OTHER
from .FileListUtils import previousIndex, nextIndex, findMediaIndex
from .ConfigInit import pic_slideshow_animations


class Slideshow():
    """view: the screen. It has the methods event(name) (one event of its own table), show() (the screen over the video plane) and
    markVideoPlayed(); the players need it as the screen they belong to."""

    def __init__(self, view, file_list, file_index, song_list, picani, start_slideshow=False):
        self.view = view
        self.sm = createSlideshowMachine(self, self.facts, logger.info)
        self.picani = picani
        self.start_slideshow = start_slideshow
        self.file_list = file_list
        self.file_index = file_index
        self.file = None
        self.song_list = song_list if song_list is not None else []
        self.direction = True
        self.slide_timer = eTimer()
        self.slide_timer.callback.append(self.slideTimerExpired)
        self.show_timer = None      # DelayTimer of the slide that is about to be shown
        self.manual_navigation = False  # the slide about to be shown was selected with a key, not by the slideshow timer
        self.previous_file = None   # the file that was shown before the current one
        self.slideshow_duration = 0
        self.slideshow_animations = pic_slideshow_animations
        self.animation = int(pic_slideshow_animations[0][0])
        for animation in self.slideshow_animations:
            if animation[0] == config.plugins.mediacockpit.animation.value:
                self.animation = int(animation[0])
                break
        logger.debug("animation: %s", self.animation)

        # enigma2 plays the videos, with their sound, and the background music. Only one service plays at a time: the music is
        # suspended while a movie plays and goes on after it.
        self.video = ServicePlayer(view, self.videoEnded, self.videoStarted)
        self.music = BackgroundMusic(view, self.song_list)

    @property
    def running(self):
        return self.sm.state["run"] == RUNNING

    @property
    def content(self):
        media = self.file[MDC_IDX_MEDIA] if self.file else None
        return PICTURE if media == MDC_MEDIA_TYPE_PICTURE else MOVIE if media == MDC_MEDIA_TYPE_MOVIE else OTHER

    def facts(self):
        """What the table asks for when an event comes in."""
        count = len(self.file_list)
        loop = config.plugins.mediacockpit.slideshow_loop.value
        return {
            "content": self.content,
            "at_end": not loop and self.file_index == (count - 1 if self.direction else 0),
            "at_end_forward": not loop and self.file_index == count - 1,
            "at_end_back": not loop and self.file_index == 0,
            "picani": self.picani,
            "all_failed": self.video.failures >= count,
            "autostart": self.start_slideshow,
        }

    # keys, timers and player events: all of them are events of the table

    def start(self):
        self.sm.dispatch("START")

    def play(self):
        self.sm.dispatch("PLAY")

    def stop(self):
        self.sm.dispatch("STOP")

    def next(self):
        self.sm.dispatch("NEXT")

    def previous(self):
        self.sm.dispatch("PREV")

    def exit(self):
        self.sm.dispatch("EXIT")

    def showSlide(self):
        self.sm.dispatch("SHOW_SLIDE")

    def slideTimerExpired(self):
        self.sm.dispatch("TIMER")

    def videoStarted(self):
        self.sm.dispatch("VIDEO_STARTED")

    def videoEnded(self):
        """The video ended on its own (a stopped or skipped one never gets here)."""
        self.sm.dispatch("VIDEO_ENDED")

    # the list

    def selectFile(self, file_index):
        """Another file is the current one (the information screen was left); its slide is shown by showSlide()."""
        self.file_index = file_index
        self.file = self.file_list[file_index]

    def removeCurrent(self):
        """The current file is gone from the list (deleted): the next picture or video becomes the current one. False when there is
        none left."""
        index = self.file_index
        del self.file_list[index]
        next_index = findMediaIndex(self.file_list, min(index, len(self.file_list) - 1)) if self.file_list else -1
        if next_index < 0:
            return False
        self.selectFile(next_index)
        return True

    def nextPicturePath(self):
        """The path of the picture that comes after the current one in the direction of the slideshow, None when a video comes first
        or the slideshow ends there (PicAniCockpit prepares it during the hold time, so that its transition starts at once)."""
        loop = config.plugins.mediacockpit.slideshow_loop.value
        index = self.file_index
        for _i in range(len(self.file_list)):
            if not loop and index == (len(self.file_list) - 1 if self.direction else 0):
                return None
            index = nextIndex(index, len(self.file_list)) if self.direction else previousIndex(index, len(self.file_list))
            afile = self.file_list[index]
            if afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE:
                return afile[MDC_IDX_PATH]
            if afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_MOVIE:
                return None
        return None

    def nextAnimation(self):
        """The next transition of the list of the engine in use (the ids of PicAniCockpit are not consecutive): (id, name)."""
        ids = [animation[0] for animation in self.slideshow_animations]
        index = ids.index(str(self.animation)) if str(self.animation) in ids else -1
        self.animation = int(ids[(index + 1) % len(ids)])
        logger.debug("animation: %s", self.animation)
        name = "n/a"
        for animation in self.slideshow_animations:
            if animation[0] == str(self.animation):
                name = animation[1]
                break
        return self.animation, name

    # The actions of the table (SlideshowStates.py). Each one does one small thing; which of them a key leads to is decided
    # by the table, not here.

    def do_prepare(self):
        """The first thing after the layout: the first file and the duration of a slide; the screen sets its widgets up."""
        logger.debug("...")
        self.file = self.file_list[self.file_index]
        self.slideshow_duration = config.plugins.mediacockpit.slideshow_duration.value * 1000
        self.start_slideshow = False   # the autostart is used up: the screen starts the engine again after the information screen
        self.view.event("PREPARE")

    def do_view_run_started(self):
        self.view.event("RUN_STARTED")

    def do_view_viewer_started(self):
        self.view.event("VIEWER_STARTED")

    def do_view_slide(self):
        self.view.event("SLIDE")

    def do_view_paused(self):
        self.view.event("PAUSED")

    def do_view_position(self):
        self.view.event("POSITION")

    def do_view_video_playing(self):
        self.view.event("VIDEO_PLAYING")

    def do_view_video_returned(self):
        self.view.event("VIDEO_RETURNED")

    def do_view_ended(self):
        logger.info("end of slideshow")
        self.view.event("ENDED")

    def do_view_failed(self):
        logger.info("end of slideshow: no video can be played")
        self.view.event("FAILED")

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
            self.view.show()     # the screen was hidden for the video: cover the video plane at once, not after the delay below

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

    # videos and music

    def do_start_video(self):
        filename = self.file[MDC_IDX_PATH]
        logger.info("filename: %s", filename)
        self.view.markVideoPlayed()   # MediaCockpit has to clear the video plane when it comes back
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

    def do_save_animation(self):
        if self.picani:  # without it the list holds only a placeholder, which must not replace the saved choice
            config.plugins.mediacockpit.animation.value = str(self.animation)
            config.plugins.mediacockpit.animation.save()
