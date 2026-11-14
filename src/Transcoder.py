# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# Videos that the video decoder of the receiver cannot play (Motion-JPEG, as the cameras of 2008 wrote it): enigma2 finds no video
# sink for them and shows its radio screen while only the sound plays. ffmpeg turns such a video into H.264 on the fly and serves it
# once on a local port; the player plays that address instead of the file. Nothing is written to a disk, and the box converts
# several times faster than the video plays.

import os
import subprocess
from .ConsoleAppContainer import ConsoleAppContainer
from .Debug import logger
from .ServiceUtils import MDC_EXT_VIDEO

# video codecs that dvbvideosink has no input for
UNSUPPORTED_CODECS = ("mjpeg", "mjpegb", "theora", "av1", "prores", "dvvideo", "rawvideo", "cinepak", "indeo3", "indeo5", "svq1", "svq3")
PORT_BASE = 18700
PORTS = 100
URL_PREFIX = "http://127.0.0.1:"
PROBE_TIMEOUT = 3       # seconds
LISTEN_DELAY = 600      # ms ffmpeg needs until it listens
# Quality against speed on the receiver (2 cores, a 640x480 clip): ultrafast with crf 23 converts 4.3x faster than the video plays but
# has the lowest quality; superfast with crf 18 still 2.4x (the player and the GUI need the rest) and keeps the detail of the camera. veryfast is
# 1.7x, too close to real time.
X264_PRESET = "superfast"
X264_CRF = "18"


def videoCodec(path):
    """The codec of the first video stream, "" if there is none or it cannot be told."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0",
                              path], capture_output=True, text=True, timeout=PROBE_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as err:
        logger.debug("ffprobe: %s", err)
        return ""
    return out.stdout.strip().split(",")[0]


def isConverted(path):
    """path is the address of a converted video, not a file."""
    return path.startswith(URL_PREFIX)


def needsTranscode(path):
    if os.path.splitext(path)[1].lower() not in MDC_EXT_VIDEO:
        return False
    codec = videoCodec(path)
    logger.debug("path: %s, codec: %s", path, codec)
    return codec in UNSUPPORTED_CODECS


class Transcoder():
    """One conversion at a time. prepare() starts ffmpeg and returns the address to play, or None when the file plays as it is."""

    def __init__(self):
        self.container = ConsoleAppContainer()
        self.port = PORTS - 1   # a new port for every conversion: the one of the last is not free for a moment

    def prepare(self, path):
        self.stop()
        if not needsTranscode(path):
            return None
        self.port = (self.port + 1) % PORTS
        url = f"{URL_PREFIX}{PORT_BASE + self.port}"
        logger.info("path: %s, url: %s", path, url)
        # args instead of a command line: no quoting of the path
        self.container.execute("ffmpeg", "ffmpeg", "-v", "error", "-i", path, "-c:v", "libx264", "-preset", X264_PRESET, "-crf", X264_CRF,
                               "-pix_fmt", "yuv420p", "-c:a", "aac", "-f", "mpegts", "-listen", "1", url)
        return url

    def stop(self):
        self.container.kill()
