# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


from enigma import eTimer
from Components.Label import Label


TOAST_TIMEOUT = 3   # seconds


class Toast():
    """A short message inside a screen: the label "toast" of its skin, hidden again after a few seconds.

    Notifications (Tools.Notifications) are no alternative: only the InfoBar shows them, so while one of our screens is open they
    would pile up and appear after it was left. The screen hides the label when its layout is finished (hide()) and stops the
    timer when it is closed (stop())."""

    def __init__(self, csel, timeout=TOAST_TIMEOUT):
        self.csel = csel
        self.timeout = timeout
        csel["toast"] = Label()
        self.timer = eTimer()
        self.timer.callback.append(self.hide)

    def show(self, text, timeout=None):
        self.csel["toast"].setText(text)
        self.csel["toast"].show()
        self.timer.start((timeout or self.timeout) * 1000, True)

    def hide(self):
        self.csel["toast"].hide()

    def stop(self):
        self.timer.stop()
