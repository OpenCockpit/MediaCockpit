# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
from shlex import quote
from twisted.web.client import downloadPage
from twisted.web.client import getPage
from Tools.BoundFunction import boundFunction
from .Debug import logger
from .FileUtils import createDirectory


class Cover():

    def __init__(self, download_dir, coverDownloadFinished, coverDownloadFailed):
        logger.debug("download_dir: %s", download_dir)
        self.download_dir = download_dir
        self.coverDownloadFinished = coverDownloadFinished
        self.coverDownloadFailed = coverDownloadFailed
        if not os.path.exists(self.download_dir):
            createDirectory(self.download_dir)

    def determineContentURL(self, artist, album, title):
        logger.error(
            "overridden in child class: artist: %s, album: %s, title: %s", artist, album, title)
        return ""

    def determineCoverURL(self, result):
        logger.error("overridden in child class: result: %s", result)
        return ""

    def determinePath(self, artist, album, title):
        logger.debug("artist: %s, album: %s, title: %s", artist, album, title)
        if artist and album:
            path = os.path.join(self.download_dir, quote(artist + "_" + album))
        else:
            path = os.path.join(self.download_dir, quote(title))
        return path

    def getCover(self, artist, album, title):
        logger.debug("artist: %s, album: %s, title: %s", artist, album, title)
        path = self.determinePath(artist, album, title)
        if os.path.exists(path):
            self.coverDownloadFinished(path, None)
        else:
            url = self.determineContentURL(artist, album, title)
            if url:
                agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36"
                try:
                    getPage(url, timeout=4, agent=agent).addCallback(boundFunction(
                        self.getCoverCallback, path)).addErrback(self.coverDownloadFailed)
                except ValueError:
                    self.coverDownloadFailed("failed")

    def getCoverCallback(self, filename, result):
        logger.debug("filename: %s, result: %s", filename, result)
        url = self.determineCoverURL(result)
        if url:
            logger.debug("downloading cover from %s to %s", url, filename)
            downloadPage(url, filename).addCallback(boundFunction(
                self.coverDownloadFinished, filename)).addErrback(self.coverDownloadFailed)
        else:
            logger.error("no cover found")
            self.coverDownloadFailed(None)
