# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# The players of the slideshow: the videos and the background music. Both are played by enigma2 itself, through its service
# layer (ServicePlayer), like the CockpitPlayer does. Only one service plays at a time and owns the decoders: the background
# music is suspended while a movie plays and resumed afterwards (BackgroundMusic).

import time
from random import randrange
from enigma import eTimer, iPlayableService
from Components.ServiceEventTracker import ServiceEventTracker
from .Debug import logger
from .FileManagerUtils import MDC_IDX_PATH
from .ServiceUtils import getService
from .SongQueue import SongQueue

PTS_PER_SECOND = 90000


class ServicePlayer():
    """Plays one file at a time through enigma2 itself (session.nav.playService), like the CockpitPlayer does. Used for the
    videos and the background music of the slideshow and for the songs of the music player.

    An external gst-launch process opened the video decoder behind the back of enigma2 and now and then stalled in
    dvbvideosink right after the start (no frame, no EOS, never exited), which froze the slideshow. Here the service tells when
    it has a first frame (for a song: when it plays) and when it reached the end, and a start that does not happen within
    START_TIMEOUT is stopped and tried once more.

    on_ended() is called when the file ended on its own or could not be played (a stopped one never calls it); failures counts
    the files in a row that could not be played, so the caller can stop when none of them plays. on_started() is called when
    the first frame is there."""

    START_TIMEOUT = 8000    # ms until the first frame, else the start is repeated once and then counted as a failure
    RETRIES = 1

    def __init__(self, screen, on_ended, on_started=None):
        self.session = screen.session
        self.on_ended = on_ended
        self.on_started = on_started
        self.failures = 0
        self.playing = False        # a video was started and has neither ended nor been stopped
        self.started = False        # ... and it has shown its first frame
        self.service_active = False  # the service of a video is running and has to be stopped
        self.path = None
        self.retries = 0
        self._begin = 0.0
        self.start_timer = eTimer()
        self.start_timer.callback.append(self._startTimeout)
        # The callback of on_ended() is not made from inside the service event: stopping the service within its own event
        # (nextSlide() -> stop()) is not safe.
        self.end_timer = eTimer()
        self.end_timer.callback.append(self._callOnEnded)
        self.has_first_frame = hasattr(iPlayableService, "evFirstFrame")
        eventmap = {
            iPlayableService.evStart: self._evStart,
            iPlayableService.evEOF: self._evEOF,
            iPlayableService.evEnd: self._evEnd,
            iPlayableService.evUser + 11: self._evVideoCodecMissing,
        }
        if self.has_first_frame:
            eventmap[iPlayableService.evFirstFrame] = self._markStarted
        self.tracker = ServiceEventTracker(screen=screen, eventmap=eventmap)

    def running(self):
        return self.playing

    def play(self, path):
        if self.playing:
            logger.debug("already playing")
            return
        logger.debug("path: %s", path)
        self.path = path
        self.retries = self.RETRIES
        self.end_timer.stop()
        self._startService()

    def _startService(self):
        service = getService(self.path)
        self.started = False
        self.playing = True
        self._begin = time.monotonic()
        self.start_timer.start(self.START_TIMEOUT, True)
        # playService() reports the end of the previous service first (evEnd): _evEnd() ignores it while not started
        self.session.nav.playService(service)
        self.service_active = True

    def stop(self):
        """Stop the video. The picture of the next slide covers the video plane, MediaCockpit clears it when it comes back."""
        self.playing = False
        self.started = False
        self.start_timer.stop()
        self.end_timer.stop()
        if self.service_active:
            self.service_active = False
            self.session.nav.stopService()

    def _markStarted(self):
        if self.playing and not self.started:
            self.started = True
            self.start_timer.stop()
            logger.debug("first frame after %.1f s", time.monotonic() - self._begin)
            if self.on_started:
                self.on_started()

    def _evStart(self):
        if not self.has_first_frame:
            self._markStarted()

    def _evEOF(self):
        if self.playing:
            self._finish(0 if self.started else 1)

    def _evEnd(self):
        # the end of a service we did not stop ourselves, e.g. a read error. Before the first frame this is the end of the
        # previous service (see _startService()).
        if self.playing and self.started:
            self._finish(1)

    def _evVideoCodecMissing(self):
        if self.playing:
            logger.warning("no video decoder for %s", self.path)
            self._finish(1)

    def _startTimeout(self):
        logger.warning("no first frame within %s ms: %s", self.START_TIMEOUT, self.path)
        if not self.playing or self.started:
            return
        self.session.nav.stopService()
        self.service_active = False
        if self.retries > 0:
            self.retries -= 1
            logger.info("start again, retries left: %s", self.retries)
            self._startService()
        else:
            self._finish(1)

    def _finish(self, ret_val):
        logger.debug("ret_val: %s, runtime: %.1f", ret_val, time.monotonic() - self._begin)
        self.playing = False
        self.start_timer.stop()
        self.failures = self.failures + 1 if ret_val != 0 else 0
        self.end_timer.start(10, True)

    def _callOnEnded(self):
        self.on_ended()


class BackgroundMusic():
    """The songs of a slideshow in random order, round and round, played through the enigma2 service.

    A movie plays with its own sound and needs the service for itself: suspend() stops the music before the movie and
    remembers the song and the position in it, resume() goes on there after the movie. stop() ends the music for good."""

    def __init__(self, screen, song_list):
        self.session = screen.session
        self.song_list = song_list
        count = len(song_list)
        self.queue = SongQueue(count, randrange(count) if count else 0)
        self.queue.toggleShuffle()      # starts with a random song, the others follow mixed
        self.player = ServicePlayer(screen, self._songEnded, self._songStarted)
        self.wanted = False         # start() was called, stop() was not: the music plays whenever no movie does
        self.suspended = False      # a movie plays
        self.resume_pts = 0         # where in the song to go on (90 kHz), applied when the song has started

    def start(self):
        if not self.song_list:
            return
        self.wanted = True
        self.suspended = False
        self._play(0)

    def suspend(self):
        """A movie is about to start."""
        if not self.wanted or self.suspended:
            return
        self.suspended = True
        if self.player.started:
            seekable = self._seekable()
            position = seekable.getPlayPosition() if seekable else None
            self.resume_pts = 0 if position is None or position[0] else position[1]
        # else: the song has not started (again) yet, the position it is to go on at is still the one saved
        logger.info("music suspended in song %s at %.1f s", self.queue.current, self.resume_pts / PTS_PER_SECOND)
        self.player.stop()

    def resume(self):
        """The movie is over: go on in the same song at the same position."""
        if not self.wanted or not self.suspended:
            return
        self.suspended = False
        logger.info("music resumed in song %s at %.1f s", self.queue.current, self.resume_pts / PTS_PER_SECOND)
        self._play(self.resume_pts)

    def stop(self):
        logger.info("...")
        self.wanted = False
        self.suspended = False
        self.resume_pts = 0
        self.player.stop()

    def _play(self, pts):
        self.resume_pts = pts
        path = self.song_list[self.queue.current][MDC_IDX_PATH]
        logger.info("position: %s, path: %s, at %.1f s", self.queue.position, path, pts / PTS_PER_SECOND)
        self.player.stop()      # play() does nothing while a song is still marked as playing
        self.player.play(path)

    def _seekable(self):
        service = self.session.nav.getCurrentService()
        return service.seek() if service else None

    def _songStarted(self):
        if self.resume_pts > 0:
            seekable = self._seekable()
            if seekable:
                seekable.seekTo(self.resume_pts)
            self.resume_pts = 0

    def _songEnded(self):
        """The song ended on its own, or could not be played."""
        if not self.wanted or self.suspended:
            return
        if self.player.failures >= len(self.song_list):
            logger.warning("no song can be played, music stopped")
            self.wanted = False
            self.player.stop()
            return
        self.queue.songEnded()
        self._play(0)
