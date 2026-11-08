# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


from enigma import eSize
from Components.config import config
from .PictureUtils import createThumbnail


class Thumbnail():

    def __init__(self):
        self.thumbnail_size = eSize(
            int(config.plugins.mediacockpit.thumbnail_size_width.value),
            int(config.plugins.mediacockpit.thumbnail_size_height.value)
        )

    def createThumbnail(self, path, create=False):
        createThumbnail(path, self.thumbnail_size, create)
