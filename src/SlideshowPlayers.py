# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# The external players of the slideshow: a video on the video plane and background music. Both are gst-launch processes, started
# and watched through ConsoleAppContainer.

from random import shuffle
from urllib.parse import quote
from .Debug import logger
from .FileManagerUtils import MDC_IDX_PATH
from .ConsoleAppContainer import ConsoleAppContainer
from .SkinUtils import getSkinPath


def fileUri(path):
    """file:// URI of path. Percent-encoded, so no space, quote, # or % can break the single-quoted command line (enigma2
    splits the command on spaces itself and cannot escape a quote inside quotes)."""
    return "file://" + quote(path)


class VideoPlayer():
    """One video at a time. on_ended() is called when a video ends on its own (a stopped one never calls it).
    failures counts the videos in a row that ended with an error, so the caller can stop when none of them plays."""

    def __init__(self, on_ended, with_music=False):
        self.on_ended = on_ended
        self.with_music = with_music    # background music is playing: the video is silent
        self.failures = 0
        self.container = ConsoleAppContainer(self.__ended)
        self.black_container = ConsoleAppContainer()

    def running(self):
        return self.container.running()

    def play(self, path):
        if self.running():
            logger.debug("already playing")
            return
        cmd = f"gst-launch-1.0 playbin -v uri='{fileUri(path)}'"
        if self.with_music:
            cmd += " flags=0x51"
        logger.debug("cmd: %s", cmd)
        self.container.execute(cmd)

    def stop(self):
        """Stop the video and clear the video plane with a black frame."""
        self.container.kill()
        cmd = f"showiframe {getSkinPath('images/black.mvi')}"
        logger.debug("cmd: %s", cmd)
        self.black_container.execute(cmd)

    def __ended(self):
        ret_val = self.container.ret_val
        logger.debug("ret_val: %s, runtime: %.1f", ret_val, self.container.runtime)
        self.failures = self.failures + 1 if ret_val != 0 else 0
        self.on_ended()


class MusicPlayer():
    """Plays the songs in random order, round and round, until stopped."""

    def __init__(self, song_list):
        self.song_list = song_list
        self.order = list(range(len(song_list)))
        self.index = 0
        self.failures = 0
        self.container = ConsoleAppContainer(self.__ended)

    def start(self):
        if self.song_list:
            shuffle(self.order)
            self.play()

    def play(self):
        afile = self.song_list[self.order[self.index]]
        logger.info("index: %s, afile: %s", self.index, afile)
        cmd = f"gst-launch-1.0 playbin uri='{fileUri(afile[MDC_IDX_PATH])}'"
        logger.debug("cmd: %s", cmd)
        self.container.execute(cmd)

    def stop(self):
        logger.info("...")
        self.container.kill()

    def __ended(self):
        ret_val = self.container.ret_val
        logger.debug("ret_val: %s", ret_val)
        self.failures = self.failures + 1 if ret_val != 0 else 0
        if self.failures >= len(self.song_list):
            logger.warning("no song can be played, music stopped")
            return
        self.index = (self.index + 1) % len(self.song_list)
        self.play()
