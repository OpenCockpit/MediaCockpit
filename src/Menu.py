# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


from Screens.ChoiceBox import ChoiceBox
from .__init__ import _
from .Debug import logger
from .Version import PLUGIN
from .FileManagerUtils import FILE_OP_LOAD
from .FileManagerProgress import FileManagerProgress
from .About import about


class Menu():
    def __init__(self):
        logger.info("...")

    def openMenu(self):
        logger.info("...")
        alist = [
            (f"{_('Load cache directory')}", "load_cache_dir"),
            (f"{_('Load cache bookmark')}", "load_cache_bookmark"),
            (f"{_('Show load progress')}", "show_load_progress"),
            (f"{_('Setup')}", "open_setup"),
            (f"{_('About')}", "about")
        ]

        self.session.openWithCallback(
            self.openMenuCallback,
            ChoiceBox,
            title=PLUGIN,
            list=alist,
            windowTitle=_("Menu"),
            allow_cancel=True,
            titlebartext=_("Input")
        )

    def openMenuCallback(self, answer=None):
        logger.info("...")
        if answer:
            screen = answer[1]
            if screen == "load_cache_dir":
                self.loadCacheDir()
            elif screen == "load_cache_bookmark":
                self.loadCacheBookmark()
            elif screen == "show_load_progress":
                self.session.open(FileManagerProgress, FILE_OP_LOAD)
            elif screen == "open_setup":
                self.openConfigScreen()
            elif screen == "about":
                about(self.session)
