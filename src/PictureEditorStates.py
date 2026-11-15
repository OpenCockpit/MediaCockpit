# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# What the keys do on the picture screen, and what the screen shows when the slideshow tells it something, in one table. The screen
# (PictureEditor.py) turns a key or a message of the slideshow into an event of this table and performs the actions the table
# returns, in methods do_<action>(). The slideshow itself (timer, going on and back, videos, music) has its own table in
# SlideshowStates.py: its actions that start with view_ arrive here as the events SLIDE, RUN_STARTED and so on; the keys PLAY, STOP, NEXT and
# PREVIOUS go to the slideshow directly.
#
# State
#   chrome  HIDDEN    the picture covers the whole screen
#           SHOWN     the window with its header and footer is shown, the picture is in its body
# Facts (what is looked up when an event comes in; run and video are the state of the slideshow)
#   content PICTURE / MOVIE / OTHER: the type of the current file
#   run     STOPPED / RUNNING: a single picture or a paused slideshow / the slideshow runs
#   video   IDLE / STARTING / PLAYING: no video plays / a video was started / its frames are shown
#   picani  the PicAniCockpit viewer plays the transitions
#   editable  the current picture can be saved again by the editor (jpg, jpeg, png; a gif or bmp is only shown)
#   has_media  the list has a picture or a video

from .StateMachine import StateMachine, rule

HIDDEN, SHOWN = "HIDDEN", "SHOWN"
STOPPED, RUNNING = "STOPPED", "RUNNING"
IDLE, STARTING, PLAYING = "IDLE", "STARTING", "PLAYING"
PICTURE, MOVIE, OTHER = "PICTURE", "MOVIE", "OTHER"

FIELDS = {"chrome": (HIDDEN, SHOWN)}
INITIAL = {"chrome": HIDDEN}


def _ended(event, toast):
    return [
        rule(event, facts={"content": MOVIE}, do=("image_hide", "restore_picture", "show_screen", "show_chrome", "lcd_info", toast),
             to={"chrome": SHOWN}, note="the last slide was a video: the screen comes back, with its window"),
        rule(event, do=("image_hide", "restore_picture", "lcd_info", toast)),
    ]


RULES = [
    # The screen is laid out: the slideshow is started, which tells this screen what to show.
    rule("LAYOUT_DONE", facts={"has_media": False}, do="close_empty", note="nothing to show: leave at once"),
    rule("LAYOUT_DONE", do="start_slideshow"),
    rule("PREPARE", do="prepare", to={"chrome": HIDDEN}, note="the colours, the transition engine; the picture covers the screen"),
    rule("RUN_STARTED", do=("hide_chrome", "image_show"), to={"chrome": HIDDEN}, note="the slideshow runs: PLAY, or the autostart"),
    rule("VIEWER_STARTED", do="image_hide", note="a single picture"),

    # The slideshow tells what the screen shows.
    rule("SLIDE", facts={"content": PICTURE}, do=("hide_chrome", "show_screen", "display_picture", "lcd_info"), to={"chrome": HIDDEN}),
    rule("SLIDE", facts={"content": MOVIE}, do=("hide_chrome", "lcd_info"), to={"chrome": HIDDEN}),
    rule("SLIDE", do="hide_chrome", to={"chrome": HIDDEN}, note="not a picture or a video"),
    rule("PAUSED", do=("lcd_info", "image_hide", "restore_picture"), note="a paused slideshow: the viewer's picture is back"),
    rule("POSITION", do="lcd_info"),
    rule("VIDEO_PLAYING", do=("clear_picture", "image_hide", "hide_screen"), note="the picture goes and the screen is hidden: the video plane is seen"),
    rule("VIDEO_RETURNED", do=("show_screen", "show_chrome"), to={"chrome": SHOWN},
         note="the video of a paused slideshow is over: the screen comes back with its window"),
    rule("IMAGE_CHANGED", facts={"run": RUNNING, "picani": True}, do=("hide_picture", "prepare_next"),
         note="a transition has finished: the next picture is prepared"),
    rule("IMAGE_CHANGED", do="hide_picture"),
] + _ended("ENDED", "toast_end") + _ended("FAILED", "toast_video_failed") + [

    # OK: the window with the keys, or the picture over the whole screen
    rule("OK", facts={"video": IDLE}, when={"chrome": HIDDEN}, do="show_chrome", to={"chrome": SHOWN},
         note="a running slideshow with transitions shows its header line as a toast"),
    rule("OK", facts={"video": IDLE}, when={"chrome": SHOWN}, do=("hide_chrome", "hide_toast"), to={"chrome": HIDDEN}),

    # INFO
    rule("INFO", facts={"run": STOPPED, "content": (PICTURE, MOVIE)}, do="open_info", note="only while the slideshow is paused"),

    # The picture editor. RED, GREEN and BLUE work on a single picture and on a paused slideshow, like INFO; YELLOW turns by 90 degrees.
    rule("RED", facts={"run": STOPPED, "content": PICTURE}, do="delete_picture", note="asks first; the picture is renamed to .del"),
    rule("GREEN", facts={"run": STOPPED, "content": PICTURE, "editable": True}, do="rotate_free", note="the screen PictureRotate"),
    rule("BLUE", facts={"run": STOPPED, "content": PICTURE, "editable": True}, do="crop_picture", note="the screen PictureCrop"),
    rule("GREEN", facts={"run": STOPPED, "content": PICTURE}, do="toast_not_editable"),
    rule("BLUE", facts={"run": STOPPED, "content": PICTURE}, do="toast_not_editable"),
    rule("YELLOW", facts={"content": PICTURE}, do="rotate_picture"),
    rule("MENU", do="toggle_transition"),

    # EXIT
    rule("EXIT", do=("exit_slideshow", "stop_toast", "close")),
]

# The events a key can cause; the rest come from the slideshow and the widgets.
KEY_EVENTS = ("OK", "INFO", "RED", "GREEN", "YELLOW", "BLUE", "MENU", "EXIT")


def createPictureEditorMachine(owner, facts, log=None):
    """owner: has a do_<action>() method for every action of the table; facts: function() -> dict of the facts."""
    def perform(action, _event, _data):
        getattr(owner, "do_" + action)()
    return StateMachine("PictureEditor", FIELDS, INITIAL, RULES, perform, facts, log)
