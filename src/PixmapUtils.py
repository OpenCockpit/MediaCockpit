# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
from enigma import loadJPG, loadPNG
from Tools.LoadPixmap import LoadPixmap
from .Debug import logger


def loadPixmap(path, cached=False):
    """LoadPixmap only accepts lowercase .png/.jpg/.svg, but pictures and their thumbnails keep whatever extension the camera
    wrote (C1.JPG, C1.thumbnail.JPG). Pick the loader by the lowercased extension instead. Returns None if the file cannot be
    loaded, so that callers can fall back to an icon instead of failing half way through painting a screen."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".jpg", ".jpeg"):
            return loadJPG(path, 1 if cached else 0)
        if ext == ".png":
            return loadPNG(path, 0, 1 if cached else 0)
        return LoadPixmap(path, cached=cached)
    except Exception as e:  # noqa: BLE001
        logger.error("path: %s, e: %s", path, e)
        return None
