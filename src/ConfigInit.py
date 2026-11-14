# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


import os
from collections import namedtuple
from Components.config import config, ConfigSet, ConfigDirectory, ConfigInteger, ConfigText, ConfigSelection, ConfigYesNo, ConfigSubsection
from .__init__ import _
from .Debug import logger


# Define namedtuple for sort configuration
SortConfig = namedtuple('SortConfig', ['sort_type', 'reverse'])
SortMode = namedtuple('SortMode', ['config', 'description'])

sort_modes = {
    "0": SortMode(SortConfig("date", False), _("Date sort down")),
    "1": SortMode(SortConfig("date", True), _("Date sort up")),
    "2": SortMode(SortConfig("alpha", False), _("Alpha sort up")),
    "3": SortMode(SortConfig("alpha", True), _("Alpha sort down")),
}

choices_sort = [(k, v.description) for k, v in list(sort_modes.items())]

# Slideshow transitions are played by PicAniCockpit (ids 100-118 and 199 = random). Only its pure Python part is imported here, to
# get the list: the native module is loaded when a slideshow starts. Without the package the list holds a placeholder.
try:
    from Plugins.SystemPlugins.PicAniCockpit import Effects as PicAniEffects
    pic_slideshow_animations = PicAniEffects.effectChoices()
except Exception as e:  # noqa: BLE001 - the package is optional
    logger.info("PicAniCockpit not installed: %r", e)
    pic_slideshow_animations = [("0", _("none"))]


def initBookmarks():
    logger.info("...")
    bookmarks = []
    adir = "/media"
    for afile in os.listdir(adir):
        path = os.path.join(adir, afile)
        bookmarks.append(path)
    if not bookmarks:
        bookmarks.append(adir)
    logger.debug("bookmarks: %s", bookmarks)
    return bookmarks


logger.debug("...")

if not hasattr(config.plugins, "mediacockpit"):
    config.plugins.mediacockpit = ConfigSubsection()
config.plugins.mediacockpit.sort = ConfigSelection(
    default="2", choices=choices_sort)
config.plugins.mediacockpit.last_path = ConfigText(default="")
config.plugins.mediacockpit.start_home_dir = ConfigYesNo(default=True)
config.plugins.mediacockpit.frame = ConfigYesNo(default=True)
config.plugins.mediacockpit.create_thumbnails = ConfigYesNo(
    default=True)
# Size of the picture tiles of the shipped skin. Tiles.initTileAttribs() replaces it with the real size of the skin in use; the default
# makes sure that CacheCockpit can create thumbnails before the tile screen was ever opened.
config.plugins.mediacockpit.thumbnail_size_width = ConfigInteger(
    default=304)
config.plugins.mediacockpit.thumbnail_size_height = ConfigInteger(
    default=254)
config.plugins.mediacockpit.show_dirup_tile = ConfigYesNo(default=True)
config.plugins.mediacockpit.selection_size_offset = ConfigInteger(
    default=10, limits=(0, 50))
config.plugins.mediacockpit.selection_font_offset = ConfigInteger(
    default=2, limits=(0, 10))
config.plugins.mediacockpit.slideshow_loop = ConfigYesNo(default=False)
config.plugins.mediacockpit.slideshow_duration = ConfigInteger(
    default=5, limits=(3, 30))
config.plugins.mediacockpit.animation = ConfigSelection(
    default=pic_slideshow_animations[0][0], choices=pic_slideshow_animations)
config.plugins.mediacockpit.transition_duration = ConfigSelection(
    default="1200", choices=[(str(ms), f"{ms / 1000:.1f} s") for ms in (600, 900, 1200, 1600, 2000)])
config.plugins.mediacockpit.transition_quality = ConfigSelection(
    default="normal", choices=[("low", _("low")), ("normal", _("normal")), ("high", _("high"))])
config.plugins.mediacockpit.kenburns = ConfigYesNo(default=False)
config.plugins.mediacockpit.sort_across_dirs = ConfigYesNo(
    default=False)
config.plugins.mediacockpit.database_directory = ConfigDirectory(
    default="/etc/enigma2")
config.plugins.mediacockpit.movie_resume_at_last_pos = ConfigYesNo(
    default=False)
config.plugins.mediacockpit.movie_start_position = ConfigSelection(default="beginning", choices=[(
    "beginning", _("beginning")), ("first_mark", _("first mark")), ("event_start", _("event start"))])
config.plugins.mediacockpit.bookmarks = ConfigSet([], [])
if not config.plugins.mediacockpit.bookmarks.value:
    config.plugins.mediacockpit.bookmarks.value = initBookmarks()
    config.plugins.mediacockpit.bookmarks.save()
