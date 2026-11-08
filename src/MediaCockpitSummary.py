# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


from Components.Pixmap import Pixmap
from Screens.Screen import ScreenSummary


class MediaCockpitSummary(ScreenSummary):

    def __init__(self, session, parent):
        ScreenSummary.__init__(self, session, parent=parent)
        self["lcd_pic_loading"] = Pixmap()
        self["background"] = Pixmap()
