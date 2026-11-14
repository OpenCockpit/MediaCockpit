# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import time
from enigma import eConsoleAppContainer


class ConsoleAppContainer():
    """One external process at a time. The callback runs only when the process ends on its own, never after kill().

    After the callback ran, ret_val holds the exit code and runtime the seconds it ran, so a caller can tell a normal end from
    a failed start (a player that dies at once)."""

    def __init__(self, callback=None):
        self.callback = callback
        self.container = None
        self.done = False       # the process ended on its own
        self.ret_val = 0
        self.runtime = 0.0
        self._start = 0.0

    def execute(self, cmd, *args):
        # a still running process would be orphaned (nobody could kill it any more) and its end would later be mistaken
        # for the end of the new one
        self.kill()
        container = eConsoleAppContainer()
        self.container = container
        self.done = False
        self.ret_val = 0
        self._start = time.monotonic()
        container.appClosed.append(self.__callback)
        if container.execute(cmd, *args):
            # could not even be started: appClosed will not come
            self.__callback(-1)

    def running(self):
        return self.container is not None and not self.done

    def __callback(self, ret_val=None):
        # The container object is NOT released here: dropping the last reference inside its own appClosed signal can free
        # it while enigma2 is still running its method. It is released by the next execute().
        self.done = True
        self.ret_val = ret_val if ret_val is not None else 0
        self.runtime = time.monotonic() - self._start
        if self.callback is not None:
            self.callback()

    def kill(self):
        if self.running():
            # appClosed fires asynchronously even for a killed process, so
            # without unregistering first, __callback() would still run and
            # invoke self.callback() later for a deliberate kill - not just
            # for a natural exit. For the video container that spuriously
            # re-triggers slideshow advance (nextSlide -> stopVideo -> kill
            # -> another slide -> killed again by the next real navigation),
            # which is why video playback kept getting cut short.
            self.container.appClosed.remove(self.__callback)
            self.container.kill()
            self.container = None
