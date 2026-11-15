# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# What the picture editor does to a picture file: delete (rename), rotate by any angle, crop. No enigma2 imports: the screens only show
# and ask, this module does the work and can be tested without a box.
#
# Files next to a picture "name.jpg":
#   name.thumbnail.jpg   the thumbnail of the tile (made by Thumbnail)
#   name.transformed.jpg the rotated copy a 90 degree rotation leaves (the original keeps its pixels, the EXIF orientation says how it
#                        is turned)
#   name.jpg.orig        the untouched original, kept by the first edit that changes pixels, so that an edit can be undone by hand
#   name.jpg.del         a picture that was deleted in the viewer: no media extension, so the lists do not show it, and renaming it
#                        back brings it back

import math
import os
from PIL import Image, ImageOps

EDITABLE = (".jpg", ".jpeg", ".png")        # pictures the editor can save again (a gif or bmp is only shown)
BACKUP_SUFFIX = ".orig"
DELETED_SUFFIX = ".del"
JPEG_QUALITY = 95
ORIENTATION = 0x0112
EXIF_IFD = 0x8769
EXIF_WIDTH, EXIF_HEIGHT = 0xA002, 0xA003

MIN_FRAME = 0.1         # the smallest crop frame, as a fraction of the picture


def isEditable(path):
    return os.path.splitext(path)[1].lower() in EDITABLE


def backupPath(path):
    return path + BACKUP_SUFFIX


def deletedPath(path):
    return path + DELETED_SUFFIX


def derivedFiles(path):
    """The files that are made from a picture and go away with it (the thumbnail and the rotated copy)."""
    root, ext = os.path.splitext(path)
    return [root + ".thumbnail" + ext, root + ".transformed" + ext]


def deletePicture(path):
    """Takes the picture out of the lists: it is renamed to name.jpg.del (an older .del of the same name is replaced) and its thumbnail
    and rotated copy are removed. Returns the new name, None if the rename failed (nothing is changed then)."""
    target = deletedPath(path)
    try:
        os.replace(path, target)
    except OSError:
        return None
    for derived in derivedFiles(path):
        try:
            os.remove(derived)
        except OSError:
            pass
    return target


# the pixels

def loadUpright(path):
    """The picture as it is to be seen: turned as its EXIF orientation says, the orientation tag is gone from the result."""
    with Image.open(path) as opened:
        img = ImageOps.exif_transpose(opened)
        img.load()
        img.format = opened.format
    return img


def loadPreview(path, max_width, max_height):
    """The picture, upright and no bigger than max_width x max_height, quickly: a JPEG is decoded at a fraction of its size."""
    with Image.open(path) as opened:
        if opened.format == "JPEG":
            side = max(max_width, max_height)
            opened.draft("RGB", (side, side))
        img = ImageOps.exif_transpose(opened)
        img.load()
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return preview(img, max_width, max_height)


def preview(img, max_width, max_height):
    """A copy of img that fits into max_width x max_height (never enlarged): the editor works on it while keys are pressed, the real
    picture is only touched when the result is saved."""
    small = img.copy()
    small.thumbnail((max_width, max_height), Image.BILINEAR)
    return small


def inscribedScale(width, height, degrees):
    """The size, as a fraction of the picture, of the largest rectangle with the proportions of the picture that fits into the picture
    turned by degrees without showing its empty corners."""
    angle = math.radians(abs(degrees) % 180)
    angle = min(angle, math.pi - angle)
    cos, sin = math.cos(angle), math.sin(angle)
    return min(width / (width * cos + height * sin), height / (width * sin + height * cos), 1.0)


def rotated(img, degrees, trim=True, resample=Image.BICUBIC):
    """img turned clockwise by degrees (as seen on the screen). trim: cut away the corners that the turn leaves empty (a smaller
    picture with the proportions of the first one); otherwise they are black."""
    if not degrees:
        return img.copy()
    turned = img.rotate(-degrees, resample=resample, expand=False)
    if trim:
        width, height = img.size
        scale = inscribedScale(width, height, degrees)
        new_w, new_h = max(1, int(width * scale)), max(1, int(height * scale))
        left, top = (width - new_w) // 2, (height - new_h) // 2
        turned = turned.crop((left, top, left + new_w, top + new_h))
    return turned


class CropFrame:
    """The frame of the crop: starts as big as the picture, gets smaller and bigger (always with the proportions of the picture) and is
    moved, never out of the picture. box() is in the pixels of a picture of the size it was made for."""

    def __init__(self, width, height):
        self.width, self.height = width, height
        self.reset()

    def reset(self):
        self.scale = 1.0
        self.cx, self.cy = self.width / 2, self.height / 2

    @property
    def frame_width(self):
        return self.width * self.scale

    @property
    def frame_height(self):
        return self.height * self.scale

    def _clamp(self):
        half_w, half_h = self.frame_width / 2, self.frame_height / 2
        self.cx = min(max(self.cx, half_w), self.width - half_w)
        self.cy = min(max(self.cy, half_h), self.height - half_h)

    def smaller(self, step):
        """step: a fraction of the picture (0.05 = 5 %)."""
        self.scale = max(MIN_FRAME, round(self.scale - step, 6))
        self._clamp()

    def bigger(self, step):
        self.scale = min(1.0, round(self.scale + step, 6))
        self._clamp()

    def move(self, dx, dy):
        """dx, dy: fractions of the frame (0.1 = a tenth of its width or height)."""
        self.cx += dx * self.frame_width
        self.cy += dy * self.frame_height
        self._clamp()

    @property
    def is_whole(self):
        return self.scale >= 1.0

    def box(self, width=None, height=None):
        """(left, top, right, bottom) of the frame in a picture of width x height (the size it was made for by default)."""
        factor_x = (width or self.width) / self.width
        factor_y = (height or self.height) / self.height
        left = int(round((self.cx - self.frame_width / 2) * factor_x))
        top = int(round((self.cy - self.frame_height / 2) * factor_y))
        right = int(round((self.cx + self.frame_width / 2) * factor_x))
        bottom = int(round((self.cy + self.frame_height / 2) * factor_y))
        return left, top, max(right, left + 1), max(bottom, top + 1)


def cropped(img, box):
    return img.crop(box)


# saving

def _exifOf(img, width, height):
    """The EXIF of img for the saved file: the orientation is reset (the pixels are upright) and the size tags say the new size."""
    exif = img.getexif()
    if ORIENTATION in exif:
        del exif[ORIENTATION]
    ifd = exif.get_ifd(EXIF_IFD)
    if EXIF_WIDTH in ifd:
        ifd[EXIF_WIDTH] = width
    if EXIF_HEIGHT in ifd:
        ifd[EXIF_HEIGHT] = height
    return exif


def saveEdited(path, img):
    """Writes the edited img as path. The untouched original is kept as name.jpg.orig by the first edit (a second edit does not replace
    it). The rotated copy of a 90 degree rotation is not valid any more and goes. The new file is written to a temporary one first, so
    a failure leaves the picture as it was. Returns True when the file was written."""
    backup = backupPath(path)
    root, ext = os.path.splitext(path)
    tmp = root + ".tmp" + ext
    try:
        if not os.path.exists(backup):
            with open(path, "rb") as src, open(backup + ".tmp", "wb") as dst:
                dst.write(src.read())
            os.replace(backup + ".tmp", backup)
        kwargs = {}
        fmt = (img.format or ("PNG" if ext.lower() == ".png" else "JPEG")).upper()
        if fmt == "JPEG":
            kwargs["quality"] = JPEG_QUALITY
            kwargs["exif"] = _exifOf(img, *img.size)
            if img.mode not in ("RGB", "L", "CMYK"):
                img = img.convert("RGB")
        img.save(tmp, format=fmt, **kwargs)
        os.replace(tmp, path)
    except Exception:       # pylint: disable=broad-except
        for leftover in (tmp, backup + ".tmp"):
            if os.path.exists(leftover):
                os.remove(leftover)
        return False
    for derived in derivedFiles(path):
        if ".transformed" in derived and os.path.exists(derived):
            os.remove(derived)
    return True
