# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# The two screens of the picture editor that the picture editor screen (PictureEditor.py) opens: PictureRotate (any angle, in steps of 2 degrees) and
# PictureCrop (a frame that gets smaller and is moved). They only show the picture and handle keys, the work is done by PictureEdit.py.
# Both close with True when they changed the file (the viewer then renews the thumbnail and the cache entry), else with False.

from Screens.HelpMenu import HelpableScreen
from Screens.Screen import Screen
from Components.ActionMap import HelpableActionMap
from Components.Button import Button
from Components.Label import Label
from Components.Pixmap import Pixmap
from PIL import Image
from enigma import ePoint, eSize
from .__init__ import _
from .Debug import logger
from .DelayTimer import DelayTimer
from .PictureEdit import loadPreview, loadUpright, rotated, cropped, saveEdited, CropFrame
from .PixmapUtils import loadPixmap
from .Toast import Toast

# one picture in RAM for the preview, the same file every time. Not one literal: gitupdatepics takes a literal ending in .jpg for a
# picture of the skin.
PREVIEW_FILE = "/tmp/.mediacockpit_preview" + ".jpg"
PREVIEW_QUALITY = 85

ANGLE_STEP = 2          # degrees for one press of the bouquet key
ANGLE_MAX = 45          # more is what the 90 degree rotation of the viewer is for
SCALE_STEP = 0.05       # the crop frame gets 5 % of the picture smaller or bigger with one press
MOVE_STEP = 0.05        # ... and moves by 5 % of its size


# Keys that repeat are bound by their R name only (UPR, LEFTR, CHANNELUPR ...: the keymap sends them on the press and while it is held); the
# plain name is sent on the press too, so binding both would move twice.


class PictureEditBase(Screen, HelpableScreen):
    """What both screens have: the window with its four key buttons, the preview in its body, the line in the header and the toast."""

    TITLE = ""

    def __init__(self, session, path):
        Screen.__init__(self, session)
        HelpableScreen.__init__(self)
        self.skinName = self.__class__.__name__
        self.path = path
        self.base = None            # the preview picture the keys work on
        self.busy = False           # the picture is being saved
        self["key_red"] = Button(_("Cancel"))
        self["key_green"] = Button(_("Save"))
        self["key_yellow"] = Button(_("Reset"))
        self["key_blue"] = Button("")
        self["body"] = Label()      # the place of the picture (its rectangle is set by the skin, nothing is drawn)
        self["preview"] = Pixmap()
        self["osd_info"] = Label()  # what the keys have set, in the header
        self.toast = Toast(self)
        self.setTitle(self.TITLE)
        self.keys = {
            "RED": (self.cancel, _("Cancel")),
            "EXIT": (self.cancel, _("Cancel")),
            "GREEN": (self.save, _("Save")),
            "YELLOW": (self.reset, _("Reset")),
        }
        self.onLayoutFinish.append(self.layoutDone)

    def addKeys(self, keys):
        self.keys.update(keys)
        self["actions"] = HelpableActionMap(self, "CockpitActions", self.keys, prio=-1)

    def layoutDone(self):
        body = self["body"].instance
        self.body_pos = (body.position().x(), body.position().y())
        self.body_size = (body.size().width(), body.size().height())
        self.toast.hide()
        try:
            self.base = loadPreview(self.path, *self.body_size)
        except Exception as e:  # noqa: BLE001 - a broken file must not leave the user in an empty screen
            logger.error("path: %s, exception: %s", self.path, e)
            self.close(False)
            return
        self.start()

    def showPicture(self, img):
        """img in the body, centred, in its own size (the body is not scaled: what is seen is what the frame positions refer to)."""
        img.convert("RGB").save(PREVIEW_FILE, format="JPEG", quality=PREVIEW_QUALITY)
        width, height = img.size
        x = self.body_pos[0] + (self.body_size[0] - width) // 2
        y = self.body_pos[1] + (self.body_size[1] - height) // 2
        self.picture_pos = (x, y)
        self.picture_size = (width, height)
        widget = self["preview"].instance
        widget.move(ePoint(x, y))
        widget.resize(eSize(width, height))
        pixmap = loadPixmap(PREVIEW_FILE)
        if pixmap:
            widget.setPixmap(pixmap)

    def save(self):
        if self.busy:
            return
        if not self.changed():
            self.close(False)
            return
        self.busy = True
        self.toast.show(_("Saving picture..."), 60)
        # saving blocks the main loop for a while: give the toast a chance to be painted first
        DelayTimer(100, self.saveNow)

    def saveNow(self):
        ok = False
        try:
            ok = self.work()
        except Exception as e:  # noqa: BLE001 - the picture was not touched (saveEdited works on a temporary file)
            logger.error("path: %s, exception: %s", self.path, e)
        self.toast.stop()
        if not ok:
            self.busy = False
            self.toast.show(_("The picture could not be saved"))
            return
        self.close(True)

    def cancel(self):
        if not self.busy:
            self.close(False)

    # what the two screens do differently

    def start(self):
        raise NotImplementedError

    def changed(self):
        raise NotImplementedError

    def work(self):
        raise NotImplementedError

    def reset(self):
        raise NotImplementedError


class PictureRotate(PictureEditBase):
    """Turns the picture by any angle: the bouquet keys in steps of 2 degrees. The empty corners are cut away (blue) so that the picture
    stays a rectangle without black wedges; the part that is kept has the proportions of the picture."""

    TITLE = _("Rotate picture")

    def __init__(self, session, path):
        PictureEditBase.__init__(self, session, path)
        self.angle = 0              # degrees, clockwise
        self.trim = True
        self["key_blue"].setText(_("Cut corners"))
        self.addKeys({
            "CHANNELUPR": (self.clockwise, _("Rotate clockwise")),
            "CHANNELDOWNR": (self.counterClockwise, _("Rotate counterclockwise")),
            "BLUE": (self.toggleTrim, _("Cut away the empty corners")),
        })

    def start(self):
        self.update()

    def update(self):
        self.showPicture(rotated(self.base, self.angle, self.trim, resample=Image.BILINEAR))   # the preview is not the saved picture: fast first
        self["osd_info"].setText(f"{_('Angle')}: {self.angle:+d}°    {_('Cut corners')}: {_('on') if self.trim else _('off')}")
        self["osd_info"].show()

    def clockwise(self):
        self.turn(ANGLE_STEP)

    def counterClockwise(self):
        self.turn(-ANGLE_STEP)

    def turn(self, step):
        if self.busy or self.base is None:
            return
        self.angle = max(-ANGLE_MAX, min(ANGLE_MAX, self.angle + step))
        self.update()

    def toggleTrim(self):
        if not self.busy and self.base is not None:
            self.trim = not self.trim
            self.update()

    def reset(self):
        if not self.busy and self.base is not None:
            self.angle = 0
            self.update()

    def changed(self):
        return self.angle != 0

    def work(self):
        logger.info("path: %s, angle: %s, trim: %s", self.path, self.angle, self.trim)
        return saveEdited(self.path, rotated(loadUpright(self.path), self.angle, self.trim))


class PictureCrop(PictureEditBase):
    """The frame starts as big as the picture. The bouquet keys make it smaller and bigger (always with the proportions of the picture),
    the arrow keys move it, OK or green crops the picture to what is inside."""

    TITLE = _("Crop picture")

    def __init__(self, session, path):
        PictureEditBase.__init__(self, session, path)
        self.frame = None
        for name in ("frame", "dim_top", "dim_bottom", "dim_left", "dim_right"):
            self[name] = Label()
        self.addKeys({
            "OK": (self.save, _("Crop")),
            "CHANNELDOWNR": (self.smaller, _("Smaller frame")),
            "CHANNELUPR": (self.bigger, _("Bigger frame")),
            "LEFTR": (self.left, _("Move frame left")),
            "RIGHTR": (self.right, _("Move frame right")),
            "UPR": (self.up, _("Move frame up")),
            "DOWNR": (self.down, _("Move frame down")),
        })
        self["key_green"].setText(_("Crop"))

    def start(self):
        self.showPicture(self.base)
        self.frame = CropFrame(*self.picture_size)
        self.update()

    def update(self):
        left, top, right, bottom = self.frame.box()
        x, y = self.picture_pos
        width, height = self.picture_size
        self.place("frame", x + left, y + top, right - left, bottom - top)
        self.place("dim_top", x, y, width, top)
        self.place("dim_bottom", x, y + bottom, width, height - bottom)
        self.place("dim_left", x, y + top, left, bottom - top)
        self.place("dim_right", x + right, y + top, width - right, bottom - top)
        self["osd_info"].setText(f"{_('Frame')}: {right - left} x {bottom - top}    {round(self.frame.scale * 100)} %")
        self["osd_info"].show()

    def place(self, name, x, y, width, height):
        widget = self[name].instance
        widget.move(ePoint(x, y))
        widget.resize(eSize(max(width, 0), max(height, 0)))

    def adjust(self, change):
        if self.busy or self.frame is None:
            return
        change()
        self.update()

    def smaller(self):
        self.adjust(lambda: self.frame.smaller(SCALE_STEP))

    def bigger(self):
        self.adjust(lambda: self.frame.bigger(SCALE_STEP))

    def left(self):
        self.adjust(lambda: self.frame.move(-MOVE_STEP, 0))

    def right(self):
        self.adjust(lambda: self.frame.move(MOVE_STEP, 0))

    def up(self):
        self.adjust(lambda: self.frame.move(0, -MOVE_STEP))

    def down(self):
        self.adjust(lambda: self.frame.move(0, MOVE_STEP))

    def reset(self):
        self.adjust(self.frame.reset)

    def changed(self):
        return self.frame is not None and not self.frame.is_whole

    def work(self):
        full = loadUpright(self.path)
        box = self.frame.box(*full.size)
        logger.info("path: %s, box: %s of %s", self.path, box, full.size)
        return saveEdited(self.path, cropped(full, box))
