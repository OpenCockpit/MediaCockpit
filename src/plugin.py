# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


from Components.config import config
from Plugins.Plugin import PluginDescriptor
from Plugins.SystemPlugins.MountCockpit.MountCockpit import MountCockpit
from .__init__ import _
from .Debug import logger
from .SkinUtils import loadPluginSkin
from .Version import ID, PLUGIN, VERSION
from .MediaCockpit import MediaCockpit
from . import ConfigInit  # noqa: F401, pylint: disable=unused-import


loadPluginSkin(PLUGIN)


def openMediaCockpit(session, **__):
    logger.info("...")
    session.open(MediaCockpit)


def autoStart(reason, **kwargs):
    if reason == 0:  # startup
        if "session" in kwargs:
            logger.info("+++ Version: %s starts...", VERSION)
            # session = kwargs["session"]
            MountCockpit.getInstance().registerBookmarks(
                ID, config.plugins.mediacockpit.bookmarks.value)
    elif reason == 1:  # shutdown
        logger.info("--- shutdown")


def Plugins(**__):
    descriptors = [
        PluginDescriptor(
            name="MediaCockpit",
            description=_("Pictures, Movies, and Slideshows"),
            where=[
                PluginDescriptor.WHERE_PLUGINMENU,
                PluginDescriptor.WHERE_EXTENSIONSMENU,
            ],
            fnc=openMediaCockpit,
            icon="plugin.png",
            needsRestart=True
        ),
        PluginDescriptor(
            where=[
                PluginDescriptor.WHERE_SESSIONSTART,
                PluginDescriptor.WHERE_AUTOSTART
            ],
            fnc=autoStart,
            needsRestart=True,
        ),
    ]
    try:
        descriptors += [
            PluginDescriptor(
                where=PluginDescriptor.WHERE_SKINCHANGE,
                fnc=loadPluginSkin
            )
        ]
    except Exception:
        pass

    return descriptors
