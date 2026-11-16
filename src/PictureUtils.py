# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import io
import os
import shutil
import struct
from PIL import Image
from PIL import ImageFile
from PIL import ImageOps
from PIL.ExifTags import TAGS
try:
    from .Debug import logger
except ImportError:         # the standalone cache loader (no enigma2)
    import logging
    logger = logging.getLogger("PictureUtils")


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


ORIENTATION_TAG = 0x0112
EXIF_HEADER = b"Exif\x00\x00"


def _tiffByteOrder(tiff):
    """"<" or ">" for the TIFF block of an EXIF segment, None if it is not one."""
    if len(tiff) < 8:
        return None
    order = {b"II": "<", b"MM": ">"}.get(bytes(tiff[:2]))
    if order is None or struct.unpack(order + "H", tiff[2:4])[0] != 42:
        return None
    return order


def _exifSegment(data):
    """(start, end) of the EXIF segment of a JPEG: the marker, the length and the data; (position after the first segment if it
    is JFIF else 2, None) if there is none; None if data is no JPEG."""
    if data[:2] != b"\xff\xd8":
        return None
    pos = 2
    insert_at = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            return None
        marker = data[pos + 1]
        if marker == 0xFF:      # fill byte
            pos += 1
            continue
        if marker in {0xD8, 0x01} or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        if marker in {0xDA, 0xD9}:      # the picture data starts: no EXIF segment before it
            break
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        end = pos + 2 + length
        if length < 2 or end > len(data):
            return None
        if marker == 0xE1 and data[pos + 4:pos + 10] == EXIF_HEADER:
            return pos, end
        if marker == 0xE0 and pos == 2:         # JFIF: the EXIF segment goes after it
            insert_at = end
        pos = end
    return insert_at, None


def _segment(tiff):
    """An EXIF segment (APP1) with this TIFF block, None if it is too long for one."""
    length = 2 + len(EXIF_HEADER) + len(tiff)
    if length > 0xFFFF:
        return None
    return b"\xff\xe1" + struct.pack(">H", length) + EXIF_HEADER + tiff


def patchOrientation(data, orientation):
    """The bytes of a JPEG with the EXIF orientation set (1 to 8), None if that cannot be done (not a JPEG, damaged EXIF data). The
    picture data is not touched, so nothing is lost: a tag that is there is overwritten in place; if the picture has EXIF data
    without it, the first table of tags is copied to the end of the EXIF segment with the tag added (nothing else moves, so
    every offset stays right); a picture without EXIF data gets a segment with this one tag."""
    if not isinstance(orientation, int) or not 1 <= orientation <= 8:
        return None
    found = _exifSegment(bytes(data))
    if found is None:
        return None
    data = bytes(data)
    start, end = found
    if end is None:
        # no EXIF data: a minimal block (big endian, one table with one tag) after the JFIF segment, or at the start
        tiff = b"MM\x00\x2a\x00\x00\x00\x08" + struct.pack(">HHHIHH", 1, ORIENTATION_TAG, 3, 1, orientation, 0) + b"\x00\x00\x00\x00"
        segment = _segment(tiff)
        return None if segment is None else data[:start] + segment + data[start:]
    tiff = bytearray(data[start + 4 + len(EXIF_HEADER):end])
    order = _tiffByteOrder(tiff)
    if order is None:
        return None
    ifd = struct.unpack(order + "I", tiff[4:8])[0]
    if ifd < 8 or ifd + 2 > len(tiff):
        return None
    count = struct.unpack(order + "H", tiff[ifd:ifd + 2])[0]
    entries_end = ifd + 2 + 12 * count
    if entries_end + 4 > len(tiff):
        return None
    value = struct.pack(order + "H", orientation) + b"\x00\x00"
    for pos in range(ifd + 2, entries_end, 12):
        tag, kind, number = struct.unpack(order + "HHI", tiff[pos:pos + 8])
        if tag == ORIENTATION_TAG:
            if kind != 3 or number != 1:
                return None
            tiff[pos + 8:pos + 12] = value
            segment = _segment(bytes(tiff))
            return data[:start] + segment + data[end:]
    # no such tag: the table is copied to the end, with the tag in its place (the tags are in the order of their numbers)
    entries = [bytes(tiff[pos:pos + 12]) for pos in range(ifd + 2, entries_end, 12)]
    entries.append(struct.pack(order + "HHI", ORIENTATION_TAG, 3, 1) + value)
    entries.sort(key=lambda entry: struct.unpack(order + "H", entry[:2])[0])
    if len(tiff) % 2:
        tiff.append(0)
    new_ifd = len(tiff)
    tiff += struct.pack(order + "H", len(entries)) + b"".join(entries) + bytes(tiff[entries_end:entries_end + 4])
    tiff[4:8] = struct.pack(order + "I", new_ifd)
    segment = _segment(bytes(tiff))
    return None if segment is None else data[:start] + segment + data[end:]


def setExifOrientation(path, orientation):
    """Write the EXIF orientation into a JPEG (the file is replaced as a whole, so an interrupted write leaves the old one). Other
    formats have no EXIF data we can write. Returns True if it was written."""
    logger.debug("path: %s, orientation: %s", path, orientation)
    if os.path.splitext(path)[1].lower() not in {".jpg", ".jpeg"}:
        return False
    tmp_path = path + ".tmp"
    try:
        with open(path, "rb") as picture_file:
            data = picture_file.read()
        patched = patchOrientation(data, orientation)
        if patched is None:
            logger.error("path: %s, the EXIF data cannot be written", path)
            return False
        with open(tmp_path, "wb") as picture_file:
            picture_file.write(patched)
        shutil.copymode(path, tmp_path)
        os.replace(tmp_path, path)
        return True
    except OSError as e:
        logger.error("path: %s, exception: %s", path, e)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False


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
