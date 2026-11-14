# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# What the keys and the timers of the slideshow screen do, in one table. The screen (Slideshow.py) turns a key, a timer or a
# player event into an event of this table and performs the actions the table returns, in methods do_<action>().
#
# State
#   run     STOPPED   a single picture, or a paused slideshow: the screen waits for keys
#           RUNNING   the slideshow runs: a timer brings the next slide
#   chrome  HIDDEN    the picture covers the whole screen
#           SHOWN     the window with its header and footer is shown, the picture is in its body
#   slide   CURRENT   the slide of the current file is the one on the screen
#           PENDING   the current file was selected, its slide is waiting for the short delay before it is shown
#   video   IDLE      no video plays
#           STARTING  a video was started and has no first frame yet (the picture still covers the video plane)
#           PLAYING   the video shows its frames: the screen is hidden so that the video plane can be seen
# Facts (what is looked up when an event comes in)
#   content PICTURE / MOVIE / OTHER: the type of the current file
#   at_end, at_end_forward, at_end_back: "Slideshow endless loop" is off and the current file is the last one, in the direction
#           of the slideshow, forward, backward
#   picani  the PicAniCockpit viewer plays the transitions
#   all_failed  every video in a row could not be played
#   has_media, autostart  see LAYOUT_DONE

from .StateMachine import StateMachine, rule

STOPPED, RUNNING = "STOPPED", "RUNNING"
HIDDEN, SHOWN = "HIDDEN", "SHOWN"
CURRENT, PENDING = "CURRENT", "PENDING"
IDLE, STARTING, PLAYING = "IDLE", "STARTING", "PLAYING"
PICTURE, MOVIE, OTHER = "PICTURE", "MOVIE", "OTHER"

FIELDS = {
    "run": (STOPPED, RUNNING),
    "chrome": (HIDDEN, SHOWN),
    "slide": (CURRENT, PENDING),
    "video": (IDLE, STARTING, PLAYING),
}
INITIAL = {"run": STOPPED, "chrome": HIDDEN, "slide": CURRENT, "video": IDLE}

# leave the slide that is shown and go on with the next one: the video is stopped, a slide that was waiting is forgotten
ADVANCE = ("stop_slide_timer", "cancel_pending", "stop_video", "advance", "schedule_slide")
LEAVE = ("stop_slide_timer", "cancel_pending", "stop_video")
FRESH = {"slide": CURRENT, "video": IDLE}
PENDING_SLIDE = {"slide": PENDING, "video": IDLE}

END_ACTIONS = ("stop_slide_timer", "cancel_pending", "music_resume", "image_hide", "restore_picture")   # as if paused
END_ACTIONS_VIDEO = END_ACTIONS + ("show_screen", "show_chrome")      # the last slide was a video: the screen was hidden


def _navigation(event, direction, end_fact):
    return [
        rule(event, when={"run": RUNNING}, facts={end_fact: True}, do=(f"go_{direction}",) + LEAVE, to=FRESH, then="END_SLIDESHOW",
             note="the last slide: the slideshow ends"),
        rule(event, do=(f"go_{direction}",) + ADVANCE, to=PENDING_SLIDE),
    ]


def _end(event, toast):
    return [
        rule(event, facts={"content": MOVIE}, do=END_ACTIONS_VIDEO + ("lcd_info", toast),
             to={"run": STOPPED, "chrome": SHOWN, "slide": CURRENT, "video": IDLE}, note="the screen comes back, with its window"),
        rule(event, do=END_ACTIONS + ("lcd_info", toast), to={"run": STOPPED, "slide": CURRENT, "video": IDLE}),
    ]


RULES = [
    # The screen is laid out: show the first slide.
    rule("LAYOUT_DONE", facts={"has_media": False}, do="close_empty", note="nothing to show: leave at once"),
    rule("LAYOUT_DONE", facts={"autostart": True}, do=("prepare", "music_start", "image_show"),
         to={"run": RUNNING, "chrome": HIDDEN, "slide": CURRENT, "video": IDLE}, then="SHOW_SLIDE", note="PLAY in the tile screen"),
    rule("LAYOUT_DONE", do=("prepare", "image_hide"), to={"run": STOPPED, "chrome": HIDDEN, "slide": CURRENT, "video": IDLE},
         then="SHOW_SLIDE", note="OK on a picture; also after the information screen"),

    # The slide of the current file is shown.
    rule("SHOW_SLIDE", when={"run": RUNNING}, facts={"content": PICTURE},
         do=("hide_chrome", "reset_failures", "music_resume", "show_screen", "display_picture", "arm_slide_timer", "lcd_info"),
         to={"chrome": HIDDEN, "slide": CURRENT, "video": IDLE}, note="the next slide comes after the slideshow duration"),
    rule("SHOW_SLIDE", when={"run": STOPPED}, facts={"content": PICTURE},
         do=("hide_chrome", "reset_failures", "music_resume", "show_screen", "display_picture", "lcd_info"),
         to={"chrome": HIDDEN, "slide": CURRENT, "video": IDLE}),
    rule("SHOW_SLIDE", when={"video": IDLE}, facts={"content": MOVIE},
         do=("hide_chrome", "music_suspend", "start_video", "lcd_info"),
         to={"chrome": HIDDEN, "slide": CURRENT, "video": STARTING}, note="the video has its own sound: the music waits"),
    rule("SHOW_SLIDE", when={"video": (STARTING, PLAYING)}, facts={"content": MOVIE}, do=("hide_chrome", "lcd_info"),
         to={"chrome": HIDDEN, "slide": CURRENT}, note="the video already plays (PLAY pressed while it plays)"),
    rule("SHOW_SLIDE", facts={"content": OTHER}, do="hide_chrome", to={"chrome": HIDDEN, "slide": CURRENT}, then="TIMER",
         note="not a picture or a video: skip"),

    # The timer of the slide, or whatever else says that the next slide is due.
    rule("TIMER", when={"run": RUNNING}, facts={"at_end": True}, do=LEAVE, to=FRESH, then="END_SLIDESHOW",
         note="the last slide: the slideshow ends"),
    rule("TIMER", do=ADVANCE, to=PENDING_SLIDE),

    # PLAY, GREEN: start or pause the slideshow
    rule("PLAY", when={"run": STOPPED}, do=("cancel_pending", "hide_chrome", "image_show"),
         to={"run": RUNNING, "chrome": HIDDEN, "slide": CURRENT}, then="SHOW_SLIDE", note="the slide is shown again, now with the timer"),
    rule("PLAY", when={"run": RUNNING},
         do=("cancel_pending", "stop_slide_timer", "stop_video", "music_resume", "lcd_info", "image_hide", "restore_picture"),
         to={"run": STOPPED, "slide": CURRENT, "video": IDLE}, note="a video is stopped, the music goes on"),

    # STOP
    rule("STOP", facts={"content": MOVIE}, do=("stop_video", "delay_video_stopped"), to={"video": IDLE},
         note="stops the video and goes on with the next slide when the slideshow runs (VIDEO_STOPPED)"),
    rule("STOP", do=("stop_slide_timer", "lcd_info"), to={"run": STOPPED}, note="pause"),
    rule("VIDEO_STOPPED", when={"run": RUNNING}, then="TIMER"),
    rule("VIDEO_STOPPED", when={"run": STOPPED}, do="music_resume", note="no next slide to bring the music back"),

    # RIGHT, NEXT / LEFT, PREVIOUS
] + _navigation("NEXT", "forward", "at_end_forward") + _navigation("PREV", "back", "at_end_back") + [

    # OK: the window with the keys, or the picture over the whole screen
    rule("OK", when={"video": IDLE, "chrome": HIDDEN}, do="show_chrome", to={"chrome": SHOWN},
         note="a running slideshow with transitions shows its header line as a toast"),
    rule("OK", when={"video": IDLE, "chrome": SHOWN}, do=("hide_chrome", "hide_toast"), to={"chrome": HIDDEN}),

    # INFO
    rule("INFO", when={"run": STOPPED}, facts={"content": (PICTURE, MOVIE)}, do="open_info", note="only while the slideshow is paused"),

    # The player and the viewer tell what happened.
    rule("VIDEO_STARTED", when={"video": STARTING}, facts={"content": MOVIE}, do=("clear_picture", "image_hide", "hide_screen"),
         to={"video": PLAYING}, note="the picture goes and the screen is hidden: the video plane is seen"),
    rule("VIDEO_ENDED", when={"run": RUNNING}, facts={"all_failed": True}, to={"video": IDLE}, then="END_FAILED",
         note="every slide failed in a row: carrying on would spin forever"),
    rule("VIDEO_ENDED", when={"run": RUNNING}, to={"video": IDLE}, then="TIMER"),
    rule("VIDEO_ENDED", when={"run": STOPPED}, do=("music_resume", "show_screen", "show_chrome"), to={"video": IDLE, "chrome": SHOWN},
         note="the video of a paused slideshow is over: the screen comes back with its window and the music goes on"),
    rule("IMAGE_CHANGED", when={"run": RUNNING}, facts={"picani": True}, do=("hide_picture", "prepare_next"),
         note="a transition has finished: the next picture is prepared"),
    rule("IMAGE_CHANGED", do="hide_picture"),
] + _end("END_SLIDESHOW", "toast_end") + _end("END_FAILED", "toast_video_failed") + [

    # YELLOW, BLUE, EXIT, RED
    rule("YELLOW", facts={"content": PICTURE}, do="rotate_picture"),
    rule("BLUE", do="toggle_transition"),
    rule("EXIT", do=("stop_slide_timer", "cancel_pending", "stop_toast", "stop_delays", "stop_video", "stop_music", "save_animation", "close"),
         to={"slide": CURRENT, "video": IDLE}),
]

# The events a key can cause; the rest come from timers and the players.
KEY_EVENTS = ("OK", "INFO", "PLAY", "STOP", "NEXT", "PREV", "YELLOW", "BLUE", "EXIT")


def createSlideshowMachine(owner, facts, log=None):
    """owner: has a do_<action>() method for every action of the table; facts: function() -> dict of the facts."""
    def perform(action, _event, _data):
        getattr(owner, "do_" + action)()
    return StateMachine("Slideshow", FIELDS, INITIAL, RULES, perform, facts, log)
