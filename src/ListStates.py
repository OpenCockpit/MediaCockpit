# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# What OK and PLAY do in the tile screen, and what happens when a screen that it opened is closed, in one table. The screen
# (MediaCockpit.py) turns a key, or the end of reading a list, or the closing of a child screen into an event of this table and
# performs the actions the table returns, in methods do_<action>().
#
# State
#   mode     LIST       the tiles are shown and wait for keys
#            SLIDESHOW  the slideshow screen is open (it shows a slideshow or a single picture)
#            MUSIC      the music player is open
#            MOVIE      the video player is open
#   pending  NONE       nothing is waiting
#            SLIDESHOW  PLAY was pressed: when the list that is being read is ready, the slideshow starts (or the music player,
#                       when the list has songs only)
# Facts
#   media       the type of the entry under the cursor: PICTURE, MOVIE, MUSIC, DIR, UP, PLAYLIST, UNAVAILABLE, NONE (no entry)
#   next_media  the type of the entry after the one under the cursor
#   has_media   the list has a picture or a video
#   has_songs   the list has a song

from .StateMachine import StateMachine, rule, Not

LIST, SLIDESHOW, MUSIC, MOVIE = "LIST", "SLIDESHOW", "MUSIC", "MOVIE"
NONE = "NONE"
PICTURE, DIR, UP, PLAYLIST, UNAVAILABLE = "PICTURE", "DIR", "UP", "PLAYLIST", "UNAVAILABLE"

FIELDS = {
    "mode": (LIST, SLIDESHOW, MUSIC, MOVIE),
    "pending": (NONE, SLIDESHOW),
}
INITIAL = {"mode": LIST, "pending": NONE}

RULES = [
    # OK: open what is under the cursor. A slideshow that was waiting is forgotten.
    rule("OK", when={"mode": LIST}, facts={"media": DIR}, do="change_dir", to={"pending": NONE}),
    rule("OK", when={"mode": LIST}, facts={"media": UP}, do="go_up", to={"pending": NONE}),
    rule("OK", when={"mode": LIST}, facts={"media": PLAYLIST}, do="open_playlist", to={"pending": NONE}),
    rule("OK", when={"mode": LIST}, facts={"media": MUSIC}, do="open_music", to={"pending": NONE, "mode": MUSIC}),
    rule("OK", when={"mode": LIST}, facts={"media": UNAVAILABLE}, do="toast_unavailable", to={"pending": NONE}),
    rule("OK", when={"mode": LIST}, facts={"media": PICTURE}, do="open_viewer", to={"pending": NONE, "mode": SLIDESHOW},
         note="a single picture: the slideshow screen without a running slideshow"),
    rule("OK", when={"mode": LIST}, facts={"media": MOVIE}, do="open_movie", to={"pending": NONE, "mode": MOVIE}),

    # PLAY: a slideshow, from the entry under the cursor
    rule("PLAY", when={"mode": LIST}, facts={"media": (PICTURE, MOVIE, MUSIC)}, to={"pending": SLIDESHOW}, then="START_SHOW"),
    rule("PLAY", when={"mode": LIST}, facts={"media": UP, "next_media": PLAYLIST}, do="next_entry", then="PLAY",
         note="a folder of playlists: PLAY on the parent tile plays the first playlist"),
    rule("PLAY", when={"mode": LIST}, facts={"media": (UP, UNAVAILABLE)}, do="next_entry", to={"pending": SLIDESHOW}, then="START_SHOW",
         note="the slideshow starts at the next picture or video"),
    rule("PLAY", when={"mode": LIST}, facts={"media": DIR}, do="read_dir", to={"pending": SLIDESHOW},
         note="the folder is read, then the slideshow starts (LIST_READ)"),
    rule("PLAY", when={"mode": LIST}, facts={"media": PLAYLIST}, do="open_playlist", to={"pending": SLIDESHOW}),

    # A list was read.
    rule("LIST_READ", when={"mode": Not(LIST)}, do="paint_tiles",
         note="the screen was shown before the callback of the child screen came: only paint, never start a slideshow again"),
    rule("LIST_READ", when={"pending": SLIDESHOW}, then="START_SHOW"),
    rule("LIST_READ", do="paint_tiles"),

    # The slideshow starts: at the picture or video that is found from the cursor on, or in the music player when there are only songs.
    rule("START_SHOW", facts={"has_media": True}, do="open_slideshow", to={"mode": SLIDESHOW}),
    rule("START_SHOW", facts={"has_media": False, "has_songs": True}, do="open_music", to={"pending": NONE, "mode": MUSIC},
         note="only songs: the music player plays them, from the selected one"),
    rule("START_SHOW", facts={"has_media": False}, do="repaint_tiles", to={"pending": NONE}, note="nothing to show"),

    # A screen that was opened is closed: the tiles come back, with the cursor where the user was.
    rule("SLIDESHOW_CLOSED", do="restore_after_slideshow", to={"mode": LIST, "pending": NONE}),
    rule("MUSIC_CLOSED", do="restore_after_music", to={"mode": LIST, "pending": NONE}),
    rule("MOVIE_CLOSED", do="restore_after_movie", to={"mode": LIST, "pending": NONE}),
]

KEY_EVENTS = ("OK", "PLAY")


def createListMachine(owner, facts, log=None):
    """owner: has a do_<action>() method for every action of the table; facts: function() -> dict of the facts."""
    def perform(action, _event, _data):
        getattr(owner, "do_" + action)()
    return StateMachine("TileScreen", FIELDS, INITIAL, RULES, perform, facts, log)
