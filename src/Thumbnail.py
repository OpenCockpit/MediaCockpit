# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


from enigma import eSize
from Components.config import config
from .PictureUtils import createThumbnail


DEFAULT_THUMBNAIL_SIZE = (304, 254)   # picture tile of the shipped MediaCockpit skin


class Thumbnail():

    def __init__(self):
        # the size is stored by MediaCockpit when its tile screen is shown; before that (or if the config is not there) use a default
        mdc = getattr(config.plugins, "mediacockpit", None)
        width = int(getattr(getattr(mdc, "thumbnail_size_width", None), "value", 0) or DEFAULT_THUMBNAIL_SIZE[0])
        height = int(getattr(getattr(mdc, "thumbnail_size_height", None), "value", 0) or DEFAULT_THUMBNAIL_SIZE[1])
        self.thumbnail_size = eSize(width, height)

    def createThumbnail(self, path, create=False):
        createThumbnail(path, self.thumbnail_size, create)
