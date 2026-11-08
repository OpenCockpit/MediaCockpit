# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


from enigma import eConsoleAppContainer


class ConsoleAppContainer():

    def __init__(self, callback=None):
        self.callback = callback
        self.container = None

    def execute(self, cmd):
        self.container = eConsoleAppContainer()
        self.container.appClosed.append(self.__callback)
        self.container.execute(cmd)

    def __callback(self, _ret_val=None):
        self.container = None
        if self.callback is not None:
            self.callback()

    def kill(self):
        if self.container is not None:
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
