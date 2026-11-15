# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import io
import os
from PIL import Image
from PIL import ImageFile
from PIL import ImageOps
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
        get_exif = getattr(img, "_getexif", None)    # only JPEG (and PNG) have it
        exif_data = get_exif() if get_exif else None
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
    if ext.lower() in {".jpg", ".jpeg"}:
        try:
            img = pexif.JpegFile.fromFile(path)
            img.exif.primary.Orientation = [orientation]
            img.writeFile(path)
        except Exception as e:
            logger.error("path: %s, exception: %s", path, e)


def rotatePicture(in_path, out_path, degrees):
    try:
        with Image.open(in_path) as img:
            # Use Image.Resampling.NEAREST for Pillow >= 10.0.0
            resample = Image.Resampling.NEAREST
            tmpimg = img.rotate(degrees, resample=resample, expand=True)
            # every rotation re-encodes the previous result: keep JPEG losses small
            _savePicture(tmpimg, out_path, img.format)
    except Exception as e:
        logger.error("in_path: %s, exception: %s", in_path, e)
        return False
    return True


def transformPicture(path, orientation):
    logger.debug("path: %s, orientation: %s", path, orientation)
    degrees = {8: 90, 6: -90, 3: -180}.get(orientation)
    if degrees is None:
        return  # upright (or mirrored, which is not handled): nothing to do, do not even open the picture
    filename, ext = os.path.splitext(path)
    output_file = filename + ".transformed" + ext
    # rotatePicture() writes no EXIF, so the copy is upright by itself and needs no orientation reset
    rotatePicture(path, output_file, degrees)


def _savePicture(img, out_path, img_format=None):
    """Save img as out_path. The result is written to a temporary file first and renamed: a failed save would otherwise leave an
    empty or truncated file behind, which then counts as an existing thumbnail/rotated copy forever."""
    root, ext = os.path.splitext(out_path)
    tmp_path = root + ".tmp" + ext
    kwargs = {}
    if img_format == "JPEG":
        kwargs["quality"] = 95
        if img.mode not in {"RGB", "L", "CMYK"}:
            img = img.convert("RGB")
    try:
        img.save(tmp_path, format=img_format, **kwargs)
        os.replace(tmp_path, out_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


THUMBNAIL_QUALITY = 90


def makeThumbnail(path, size):
    """The thumbnail of a picture as the bytes of a small JPEG (a PNG when the picture has transparency), None when it cannot be made.
    It is the picture turned upright, no bigger than size in the longer side. A rotated copy (name.transformed.jpg) is used when
    there is one. A JPEG is decoded at a fraction of its size, which is several times faster than decoding all of it."""
    logger.debug("path: %s, size: %s", path, str(size))
    side = max(size.width(), size.height())
    if side <= 0:
        logger.error("path: %s, no thumbnail size known yet: %s", path, str(size))
        return None
    filename, ext = os.path.splitext(path)
    input_path = filename + ".transformed" + ext
    if not os.path.exists(input_path):
        input_path = path
    try:
        with Image.open(input_path) as img:
            if img.format == "JPEG":
                img.draft("RGB", (side, side))
            img.thumbnail((side, side))
            if input_path == path:
                # the thumbnail does not keep the EXIF orientation of the original: apply it to the pixels
                # (after shrinking, which is much cheaper; the box is square, so the rotation does not matter for it)
                img = ImageOps.exif_transpose(img)
            out = io.BytesIO()
            if img.mode in {"RGBA", "LA"} or (img.mode == "P" and "transparency" in img.info):
                img.convert("RGBA").save(out, format="PNG")
            else:
                img.convert("RGB").save(out, format="JPEG", quality=THUMBNAIL_QUALITY)
            return out.getvalue()
    except Exception as e:  # pylint: disable=broad-except
        logger.error("path: %s, exception: %s", path, e)
        return None
