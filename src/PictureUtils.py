# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
from PIL import Image
from PIL import ImageFile
from PIL.ExifTags import TAGS
from .Debug import logger
from . import pexif


ImageFile.LOAD_TRUNCATED_IMAGES = True


def getPicturePath(path):
    filename, ext = os.path.splitext(path)
    path_transformed = filename + ".transformed" + ext
    return path_transformed if os.path.exists(path_transformed) else path


def _jsonSafeExifValue(value):
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, dict):
        return {key: _jsonSafeExifValue(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonSafeExifValue(item) for item in value]
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        # e.g. PIL.TiffImagePlugin.IFDRational (XResolution, GPS coords, ...)
        return float(value)
    return str(value)


def getExifData(path):
    logger.debug("path: %s", path)
    exif_data = {}
    exif = {}
    width = 0
    height = 0
    try:
        img = Image.open(path)
        width, height = img.size
        exif_data = img._getexif()
    except Exception as e:
        logger.error("exception: %s", e)
    # logger.debug("exif_data: %s", str(exif_data))
    if exif_data:
        for key, value in list(exif_data.items()):
            if key in TAGS:
                tag = TAGS[key]
                if tag not in {"UserComment", "MakerNote"}:
                    exif[tag] = _jsonSafeExifValue(value)
    if "ExifImageWidth" not in exif and width:
        exif["ExifImageWidth"] = width
    if "ExifImageHeight" not in exif and height:
        exif["ExifImageHeight"] = height
    if "Orientation" not in exif:
        exif["Orientation"] = 1
    logger.debug("exif: %s", str(exif))
    return exif


def setExifOrientation(path, orientation):
    logger.debug("path: %s, orientation: %s", path, orientation)
    ext = os.path.splitext(path)[1]
    if ext.lower() == ".jpg":
        try:
            img = pexif.JpegFile.fromFile(path)
            img.exif.primary.Orientation = [orientation]
            img.writeFile(path)
        except Exception as e:
            logger.error("path: %s, exception: %s", path, e)


def rotatePicture(in_path, out_path, degrees):
    try:
        img = Image.open(in_path)
        if img:
            # Use Image.Resampling.NEAREST for Pillow >= 10.0.0
            resample = Image.Resampling.NEAREST
            tmpimg = img.rotate(degrees, resample=resample, expand=True)
            tmpimg.save(out_path)
    except Exception as e:
        logger.error("in_path: %s, exception: %s", in_path, e)
        return False
    return True


def transformPicture(path, orientation):
    logger.debug("path: %s, orientation: %s", path, orientation)
    filename, ext = os.path.splitext(path)
    output_file = filename + ".transformed" + ext
    try:
        img = Image.open(path)
        if img:
            if orientation == 8:
                rotatePicture(path, output_file, 90)
            if orientation == 6:
                rotatePicture(path, output_file, -90)
            if orientation == 3:
                rotatePicture(path, output_file, -180)
            if orientation in {3, 6, 8}:
                setExifOrientation(output_file, 1)
    except Exception as e:
        logger.error("path: %s, e: %s", path, e)


def createThumbnail(path, size, create=False):
    logger.debug("path: %s, size: %s", path, str(size))
    filename, ext = os.path.splitext(path)
    thumbnail_path = filename + ".thumbnail" + ext
    if not os.path.exists(thumbnail_path) or create:
        logger.info("creating %s", thumbnail_path)
        input_path = filename + ".transformed" + ext
        if not os.path.exists(input_path):
            input_path = path
        width = size.width()
        height = size.height()
        side = max(width, height)
        try:
            img = Image.open(input_path)
            img.thumbnail((side, side))
            img.save(thumbnail_path)
        except Exception as e:
            logger.error("path: %s, exception: %s", path, e)
