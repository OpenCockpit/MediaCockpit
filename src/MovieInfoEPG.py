# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


from Screens.EventView import EventViewSimple
from .__init__ import _


class MovieInfoEPG(EventViewSimple):

    def __init__(self, session, event, service_reference):
        EventViewSimple.__init__(self, session, event, service_reference)
        self.skinName = ["EventViewSimple", "EventView"]

    def setService(self, service):
        EventViewSimple.setService(self, service)
        if self.isRecording:
            self["channel"].setText("")

    def setEvent(self, event):
        EventViewSimple.setEvent(self, event)
        if self.isRecording and event.getDuration() == 0:
            self["duration"].setText("")
        else:
            self["duration"].setText(
                f"{event.getDuration() // 60} {_('min')}")
            self["datetime"].setText(event.getBeginTimeString())
