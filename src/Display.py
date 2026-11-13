# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


from Components.Label import Label
from Components.Sources.StaticText import StaticText
from .__init__ import _


class Display():
    def __init__(self, csel):
        self.csel = csel
        self.csel["osd_info"] = Label()
        self.csel["lcd_info"] = StaticText()
        self.csel["lcd_title"] = StaticText()

    def displayLCD(self, title, info):
        self.csel["lcd_title"].setText(title)
        self.csel["lcd_info"].setText(info)

    def displayOSD(self, info):
        self.csel["osd_info"].setText(_("MediaCockpit") + " - " + info)
