# pylint: disable=no-member
# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.config import config
from enigma import eSize, ePoint, eTimer, gFont
from enigma import BT_SCALE, BT_HALIGN_CENTER, BT_VALIGN_CENTER, BT_KEEP_ASPECT_RATIO
from Tools.LoadPixmap import LoadPixmap
from Plugins.SystemPlugins.MountCockpit.MountCockpit import MountCockpit
from skin import parseColor
from .SkinUtils import getSkinPath
from .PixmapUtils import loadPixmap
from .Debug import logger
from .__init__ import _
from .FileManagerUtils import MDC_IDX_MEDIA, MDC_IDX_PATH
from .FileManagerUtils import MDC_MEDIA_TYPE_FILE, MDC_MEDIA_TYPE_UP, MDC_MEDIA_TYPE_DIR, MDC_MEDIA_TYPE_PLAYLIST, MDC_MEDIA_TYPE_PICTURE, MDC_MEDIA_TYPE_MOVIE, MDC_MEDIA_TYPE_MUSIC
from .FileListUtils import getDir
from .PictureUtils import createThumbnail
from .Display import Display
from .Version import ID


class Tiles(Display):

    def __init__(self, csel):
        self.csel = csel
        Display.__init__(self, self)
        self.tile_columns = 5
        self.tile_rows = 3
        self.file_list = []
        self.current_dir = None
        self.tiles = self.tile_columns * self.tile_rows
        self.initTileConfig()
        for tile_pos in range(self.tiles):
            self.csel[f"Frame{tile_pos}"] = Label()
            self.csel[f"Frame{tile_pos}"].hide()
            self.csel[f"Tile{tile_pos}"] = Label()
            self.csel[f"Tile{tile_pos}"].hide()
            self.csel[f"Picture{tile_pos}"] = Pixmap()
            self.csel[f"Icon{tile_pos}"] = Pixmap()
            self.csel[f"Text{tile_pos}"] = Label()

        self.icons = {}
        self.last_tile_pos = -1
        self.is_mounted = False
        self.thumbnail_size = eSize(0, 0)
        self.thumbnail_todo = []        # file indexes of the visible page whose thumbnail is still missing
        self.thumbnail_failed = set()   # pictures that could not be turned into a thumbnail: not tried again
        self.thumbnail_timer = eTimer()
        self.thumbnail_timer.callback.append(self.createNextThumbnail)
        self.onShow.append(self.initTileAttribs)
        self.onClose.append(self.thumbnail_timer.stop)

    def initTileConfig(self):
        self.selection_size_offset = config.plugins.mediacockpit.selection_size_offset.value
        self.selection_font_offset = config.plugins.mediacockpit.selection_font_offset.value
        self.normal_background_color = parseColor(
            config.plugins.mediacockpit.normal_background_color.value)
        self.selection_background_color = parseColor(
            config.plugins.mediacockpit.selection_background_color.value)
        self.normal_foreground_color = parseColor(
            config.plugins.mediacockpit.normal_foreground_color.value)
        self.selection_foreground_color = parseColor(
            config.plugins.mediacockpit.selection_foreground_color.value)
        self.selection_frame_color = parseColor(
            config.plugins.mediacockpit.selection_frame_color.value)

    def initTileAttribs(self):
        logger.debug("...")
        self.icons = {}
        # initTileAttribs() runs every time the screen is shown, possibly while tile 0 is selected: the selected tile is
        # enlarged by 2 * selection_size_offset, and icons rendered at that size are clipped in the normal tiles. Measure a tile
        # that is not selected.
        ref = 1 if self.last_tile_pos == 0 and self.tiles > 1 else 0
        self.icon_size = self.csel[f"Icon{ref}"].instance.size()
        self.thumbnail_size = self.csel[f"Picture{ref}"].instance.size()
        if self.thumbnail_size.width() > 0 and self.thumbnail_size.height() > 0:
            # CacheCockpit creates thumbnails of this size while scanning
            config.plugins.mediacockpit.thumbnail_size_width.value = self.thumbnail_size.width()
            config.plugins.mediacockpit.thumbnail_size_width.save()
            config.plugins.mediacockpit.thumbnail_size_height.value = self.thumbnail_size.height()
            config.plugins.mediacockpit.thumbnail_size_height.save()
        self.icons[MDC_MEDIA_TYPE_PICTURE] = LoadPixmap(getSkinPath(
            "images/" + "picture.svg"), cached=True, width=self.icon_size.width(), height=self.icon_size.height())
        logger.info("...")
        self.icons[MDC_MEDIA_TYPE_MOVIE] = LoadPixmap(getSkinPath(
            "images/" + "movie.svg"), cached=True, width=self.icon_size.width(), height=self.icon_size.height())
        self.icons[MDC_MEDIA_TYPE_MUSIC] = LoadPixmap(getSkinPath(
            "images/" + "music.svg"), cached=True, width=self.icon_size.width(), height=self.icon_size.height())
        self.icons[MDC_MEDIA_TYPE_DIR] = LoadPixmap(getSkinPath(
            "images/" + "folder.svg"), cached=True, width=self.icon_size.width(), height=self.icon_size.height())
        self.icons[MDC_MEDIA_TYPE_PLAYLIST] = LoadPixmap(getSkinPath(
            "images/" + "playlist.svg"), cached=True, width=self.icon_size.width(), height=self.icon_size.height())
        self.icons[MDC_MEDIA_TYPE_UP] = LoadPixmap(getSkinPath(
            "images/" + "dirup.svg"), cached=True, width=self.icon_size.width(), height=self.icon_size.height())

        for tile_pos in range(self.tiles):
            for tile_element in ("Tile%d", "Text%d"):
                self.csel[tile_element % tile_pos].instance.setForegroundColor(
                    self.normal_foreground_color)
                self.csel[tile_element % tile_pos].instance.setBackgroundColor(
                    self.normal_background_color)
            self.csel[f"Frame{tile_pos}"].instance.setBackgroundColor(
                self.selection_frame_color)
            self.csel[f"Picture{tile_pos}"].instance.setPixmapScale(
                BT_SCALE | BT_HALIGN_CENTER | BT_VALIGN_CENTER | BT_KEEP_ASPECT_RATIO)

        font = self.csel["Text0"].instance.getFont()
        self.font_family = font.family
        self.font_size = font.pointSize

    def selectTile(self, tile_pos):
        logger.debug("tile_pos: %s, last_tile_pos: %s",
                     tile_pos, self.last_tile_pos)
        if self.file_list and self.last_tile_pos < 0 <= tile_pos:
            if config.plugins.mediacockpit.frame.value:
                self.csel[f"Frame{tile_pos}"].show()
            for tile_element in ("Frame%d", "Tile%d", "Picture%d", "Icon%d", "Text%d"):
                size = self.csel[tile_element % tile_pos].instance.size()
                pos = self.csel[tile_element % tile_pos].instance.position()
                self.csel[tile_element % tile_pos].instance.resize(eSize(size.width(
                ) + self.selection_size_offset * 2, size.height() + self.selection_size_offset * 2))
                self.csel[tile_element % tile_pos].instance.move(ePoint(
                    pos.x() - self.selection_size_offset, pos.y() - self.selection_size_offset))
            for tile_element in ("Tile%d", "Text%d"):
                self.csel[tile_element % tile_pos].instance.setBackgroundColor(
                    self.selection_background_color)
                self.csel[tile_element % tile_pos].instance.setForegroundColor(
                    self.selection_foreground_color)
            self.csel[f"Text{tile_pos}"].instance.setFont(
                gFont(self.font_family, self.font_size + self.selection_font_offset))
            pos = self.csel[f"Text{tile_pos}"].instance.position()
            self.csel[f"Text{tile_pos}"].move(
                ePoint(pos.x(), pos.y() + self.selection_size_offset))
            self.last_tile_pos = tile_pos

    def unselectTile(self, tile_pos):
        logger.debug("tile_pos: %s, last_tile_pos: %s",
                     tile_pos, self.last_tile_pos)
        if self.last_tile_pos > -1 and tile_pos >= 0:
            self.csel[f"Frame{tile_pos}"].hide()
            for tile_element in ("Frame%d", "Tile%d", "Picture%d", "Icon%d", "Text%d"):
                size = self.csel[tile_element % tile_pos].instance.size()
                pos = self.csel[tile_element % tile_pos].instance.position()
                self.csel[tile_element % tile_pos].instance.resize(eSize(size.width(
                ) - self.selection_size_offset * 2, size.height() - self.selection_size_offset * 2))
                self.csel[tile_element % tile_pos].instance.move(ePoint(
                    pos.x() + self.selection_size_offset, pos.y() + self.selection_size_offset))
            for tile_element in ("Tile%d", "Text%d"):
                self.csel[tile_element % tile_pos].instance.setBackgroundColor(
                    self.normal_background_color)
                self.csel[tile_element % tile_pos].instance.setForegroundColor(
                    self.normal_foreground_color)
            self.csel[f"Text{tile_pos}"].instance.setFont(
                gFont(self.font_family, self.font_size))
            pos = self.csel[f"Text{tile_pos}"].instance.position()
            self.csel[f"Text{tile_pos}"].move(
                ePoint(pos.x(), pos.y() - self.selection_size_offset))
        self.last_tile_pos = -1

    def hideTile(self, tile_pos):
        for tile_element in ("Frame%d", "Tile%d", "Picture%d", "Icon%d", "Text%d"):
            self.csel[tile_element % tile_pos].hide()

    def hideTiles(self):
        self.unselectTile(self.last_tile_pos)
        for tile_pos in range(self.tiles):
            self.hideTile(tile_pos)

    def paintTile(self, idx, tile_pos):
        logger.debug("idx: %s, tile_pos: %s", idx, tile_pos)
        path = self.file_list[idx][MDC_IDX_PATH]
        atype = self.file_list[idx][MDC_IDX_MEDIA]
        logger.debug("path: %s", path)
        self.csel[f"Tile{tile_pos}"].show()
        if atype == MDC_MEDIA_TYPE_UP:
            self.csel[f"Text{tile_pos}"].setText("..")
        else:
            self.csel[f"Text{tile_pos}"].setText(os.path.basename(path))
        thumbnail_path = None
        if atype != MDC_MEDIA_TYPE_UP:
            filename, ext = os.path.splitext(path)
            for thumbnail in (filename + ".thumbnail" + ext, filename + ".thumbnail.jpg"):
                if os.path.exists(thumbnail):
                    thumbnail_path = thumbnail
                    break
        thumbnail = loadPixmap(thumbnail_path) if thumbnail_path else None
        if thumbnail:
            self.csel[f"Picture{tile_pos}"].instance.setPixmap(thumbnail)
            self.csel[f"Icon{tile_pos}"].hide()
            self.csel[f"Text{tile_pos}"].hide()
            self.csel[f"Picture{tile_pos}"].show()
        else:
            self.csel[f"Picture{tile_pos}"].hide()
            self.csel[f"Icon{tile_pos}"].instance.setPixmap(
                self.icons[atype])
            self.csel[f"Icon{tile_pos}"].show()
            self.csel[f"Text{tile_pos}"].show()

    def paintTiles(self):
        logger.info("file_index: %s, len(file_list): %s",
                    self.file_index, len(self.file_list))
        adir = getDir(self.file_list, self.file_index)
        bookmark = MountCockpit.getInstance().getBookmark(ID, adir)
        logger.debug("bookmark: %s", bookmark)
        mounted_bookmarks = MountCockpit.getInstance().getMountedBookmarks(ID)
        logger.debug("mounted_bookmarks: %s", mounted_bookmarks)
        self.is_mounted = bookmark in mounted_bookmarks
        file_list_len = len(self.file_list)
        first_idx = self.file_index // self.tiles * self.tiles
        last_idx = first_idx + self.tiles

        logger.debug("first_idx: %s, last_idx: %s", first_idx, last_idx)
        for idx in range(first_idx, last_idx):
            tile_pos = idx % self.tiles
            if file_list_len and idx < file_list_len:
                self.paintTile(idx, tile_pos)
            else:
                self.hideTile(tile_pos)

        tile_pos = self.file_index % self.tiles
        logger.debug("tile_pos: %s, last_tile_pos: %s",
                     tile_pos, self.last_tile_pos)
        self.unselectTile(self.last_tile_pos)
        self.selectTile(tile_pos)
        self.showInfo(self.is_mounted)
        self.onSelectionChange()
        self.queueThumbnails(first_idx, min(last_idx, file_list_len))

# missing thumbnails

    @staticmethod
    def thumbnailPath(path):
        filename, ext = os.path.splitext(path)
        return filename + ".thumbnail" + ext

    def queueThumbnails(self, first_idx, last_idx):
        """The scan (CacheCockpit) creates thumbnails, but pictures that were scanned before the size was known, or that came with
        a copy of the database, have none. They are made here for the tiles on the screen, one per timer tick so that the remote
        stays responsive."""
        self.thumbnail_timer.stop()
        self.thumbnail_todo = []
        if not config.plugins.mediacockpit.create_thumbnails.value or self.thumbnail_size.width() <= 0:
            return
        for idx in range(first_idx, last_idx):
            afile = self.file_list[idx]
            path = afile[MDC_IDX_PATH]
            if afile[MDC_IDX_MEDIA] == MDC_MEDIA_TYPE_PICTURE and path not in self.thumbnail_failed and not os.path.exists(self.thumbnailPath(path)):
                self.thumbnail_todo.append(idx)
        if self.thumbnail_todo:
            self.thumbnail_timer.start(100, True)

    def createNextThumbnail(self):
        if not self.thumbnail_todo:
            return
        idx = self.thumbnail_todo.pop(0)
        try:
            if idx < len(self.file_list):
                path = self.file_list[idx][MDC_IDX_PATH]
                createThumbnail(path, self.thumbnail_size)
                if os.path.exists(self.thumbnailPath(path)):
                    if idx // self.tiles == self.file_index // self.tiles:  # still on the screen
                        self.paintTile(idx, idx % self.tiles)
                else:
                    self.thumbnail_failed.add(path)
        except Exception as e:  # noqa: BLE001 - never let a broken picture stop the tile screen
            logger.error("idx: %s, exception: %s", idx, e)
        if self.thumbnail_todo:
            self.thumbnail_timer.start(100, True)

    def showInfo(self, is_mounted=True):
        if self.file_list:
            afile = self.file_list[self.file_index]
            path = afile[MDC_IDX_PATH]
            filetype = _(
                "File") if afile[MDC_IDX_MEDIA] in MDC_MEDIA_TYPE_FILE else _("Path")
        else:
            path = self.current_dir
            filetype = _("Path")
        logger.debug("path: %s", path)
        page = self.file_index // self.tiles + 1
        pages = len(self.file_list) // self.tiles + 1
        pages = pages if len(self.file_list) % self.tiles else pages - 1
        mounted = "" if is_mounted else "(" + _("not mounted") + ")"
        self.displayLCD(f"{self.file_index + 1}/{len(self.file_list)}", os.path.basename(path))
        self.displayOSD(f"{_('Page')}: {page:g}/{pages:g} - {filetype}: {path} {mounted}")

# cursor moves

    def moveTop(self):
        self.file_index = 0
        self.paintTiles()

    def moveLeft(self):
        self.file_index -= 1
        if self.file_index < 0:
            self.file_index = len(self.file_list) - 1
        self.paintTiles()

    def moveRight(self):
        self.file_index += 1
        if self.file_index > len(self.file_list) - 1:
            self.file_index = 0
        self.paintTiles()

    def moveUp(self):
        self.file_index -= self.tile_columns
        if self.file_index < 0:
            self.file_index = len(self.file_list) - 1
        self.paintTiles()

    def moveDown(self):
        self.file_index += self.tile_columns
        if self.file_index > len(self.file_list) - 1:
            self.file_index = 0
        self.paintTiles()

    def nextPage(self):
        self.file_index += self.tiles
        self.file_index = self.file_index // self.tiles * self.tiles
        if self.file_index > len(self.file_list) - 1:
            self.file_index = 0
        self.paintTiles()

    def prevPage(self):
        self.file_index -= self.tiles
        if self.file_index < 0:
            self.file_index = len(self.file_list) - 1
        self.file_index = self.file_index // self.tiles * self.tiles
        self.paintTiles()
