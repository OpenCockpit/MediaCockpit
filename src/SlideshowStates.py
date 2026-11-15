# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# What the slideshow does, in one table: the timer of the slides, going on and back, the videos and the music. The engine
# (Slideshow.py) turns a key, a timer or a player event into an event of this table and performs the actions the table returns, in
# methods do_<action>(). It knows nothing about widgets: what the screen has to do is told to the screen (PictureEditor.py, whose
# own table is in PictureEditorStates.py) by the actions that start with view_, each of them one event of the table of the screen.
#
# State
#   run     STOPPED   a single picture, or a paused slideshow: the engine waits for keys
#           RUNNING   the slideshow runs: a timer brings the next slide
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
#   autostart  the slideshow starts at once (PLAY in the tile screen)

from .StateMachine import StateMachine, rule

STOPPED, RUNNING = "STOPPED", "RUNNING"
CURRENT, PENDING = "CURRENT", "PENDING"
IDLE, STARTING, PLAYING = "IDLE", "STARTING", "PLAYING"
PICTURE, MOVIE, OTHER = "PICTURE", "MOVIE", "OTHER"

FIELDS = {
    "run": (STOPPED, RUNNING),
    "slide": (CURRENT, PENDING),
    "video": (IDLE, STARTING, PLAYING),
}
INITIAL = {"run": STOPPED, "slide": CURRENT, "video": IDLE}

# leave the slide that is shown and go on with the next one: the video is stopped, a slide that was waiting is forgotten
ADVANCE = ("stop_slide_timer", "cancel_pending", "stop_video", "advance", "schedule_slide")
LEAVE = ("stop_slide_timer", "cancel_pending", "stop_video")
FRESH = {"slide": CURRENT, "video": IDLE}
PENDING_SLIDE = {"slide": PENDING, "video": IDLE}


def _navigation(event, direction, end_fact):
    return [
        rule(event, when={"run": RUNNING}, facts={end_fact: True}, do=(f"go_{direction}",) + LEAVE, to=FRESH, then="END_SLIDESHOW",
             note="the last slide: the slideshow ends"),
        rule(event, do=(f"go_{direction}",) + ADVANCE, to=PENDING_SLIDE),
    ]


def _end(event, tell):
    # the engine stops as if paused, the screen shows what the end looks like
    return [
        rule(event, do=("stop_slide_timer", "cancel_pending", "music_resume", tell),
             to={"run": STOPPED, "slide": CURRENT, "video": IDLE}),
    ]


RULES = [
    # The screen is laid out: the first slide.
    rule("START", facts={"autostart": True}, do=("prepare", "music_start", "view_run_started"),
         to={"run": RUNNING, "slide": CURRENT, "video": IDLE}, then="SHOW_SLIDE", note="PLAY in the tile screen"),
    rule("START", do=("prepare", "view_viewer_started"), to={"run": STOPPED, "slide": CURRENT, "video": IDLE},
         then="SHOW_SLIDE", note="OK on a picture; also after the information screen"),

    # The slide of the current file is shown.
    rule("SHOW_SLIDE", when={"run": RUNNING}, facts={"content": PICTURE},
         do=("reset_failures", "music_resume", "view_slide", "arm_slide_timer"),
         to={"slide": CURRENT, "video": IDLE}, note="the next slide comes after the slideshow duration"),
    rule("SHOW_SLIDE", when={"run": STOPPED}, facts={"content": PICTURE}, do=("reset_failures", "music_resume", "view_slide"),
         to={"slide": CURRENT, "video": IDLE}),
    rule("SHOW_SLIDE", when={"video": IDLE}, facts={"content": MOVIE}, do=("music_suspend", "start_video", "view_slide"),
         to={"slide": CURRENT, "video": STARTING}, note="the video has its own sound: the music waits"),
    rule("SHOW_SLIDE", when={"video": (STARTING, PLAYING)}, facts={"content": MOVIE}, do="view_slide",
         to={"slide": CURRENT}, note="the video already plays (PLAY pressed while it plays)"),
    rule("SHOW_SLIDE", facts={"content": OTHER}, do="view_slide", to={"slide": CURRENT}, then="TIMER",
         note="not a picture or a video: skip"),

    # The timer of the slide, or whatever else says that the next slide is due.
    rule("TIMER", when={"run": RUNNING}, facts={"at_end": True}, do=LEAVE, to=FRESH, then="END_SLIDESHOW",
         note="the last slide: the slideshow ends"),
    rule("TIMER", do=ADVANCE, to=PENDING_SLIDE),

    # PLAY: start or pause the slideshow
    rule("PLAY", when={"run": STOPPED}, do=("cancel_pending", "view_run_started"), to={"run": RUNNING, "slide": CURRENT},
         then="SHOW_SLIDE", note="the slide is shown again, now with the timer"),
    rule("PLAY", when={"run": RUNNING}, do=("cancel_pending", "stop_slide_timer", "stop_video", "music_resume", "view_paused"),
         to={"run": STOPPED, "slide": CURRENT, "video": IDLE}, note="a video is stopped, the music goes on"),

    # STOP
    rule("STOP", facts={"content": MOVIE}, do=("stop_video", "delay_video_stopped"), to={"video": IDLE},
         note="stops the video and goes on with the next slide when the slideshow runs (VIDEO_STOPPED)"),
    rule("STOP", do=("stop_slide_timer", "view_position"), to={"run": STOPPED}, note="pause"),
    rule("VIDEO_STOPPED", when={"run": RUNNING}, then="TIMER"),
    rule("VIDEO_STOPPED", when={"run": STOPPED}, do="music_resume", note="no next slide to bring the music back"),

    # RIGHT, NEXT / LEFT, PREVIOUS
] + _navigation("NEXT", "forward", "at_end_forward") + _navigation("PREV", "back", "at_end_back") + [

    # The player tells what happened.
    rule("VIDEO_STARTED", when={"video": STARTING}, facts={"content": MOVIE}, do="view_video_playing", to={"video": PLAYING},
         note="the picture goes and the screen is hidden: the video plane is seen"),
    rule("VIDEO_ENDED", when={"run": RUNNING}, facts={"all_failed": True}, to={"video": IDLE}, then="END_FAILED",
         note="every slide failed in a row: carrying on would spin forever"),
    rule("VIDEO_ENDED", when={"run": RUNNING}, to={"video": IDLE}, then="TIMER"),
    rule("VIDEO_ENDED", when={"run": STOPPED}, do=("music_resume", "view_video_returned"), to={"video": IDLE},
         note="the video of a paused slideshow is over: the screen comes back with its window and the music goes on"),
] + _end("END_SLIDESHOW", "view_ended") + _end("END_FAILED", "view_failed") + [

    # EXIT
    rule("EXIT", do=("stop_slide_timer", "cancel_pending", "stop_delays", "stop_video", "stop_music", "save_animation"),
         to={"slide": CURRENT, "video": IDLE}),
]

# The events a key can cause; the rest come from timers and the players.
KEY_EVENTS = ("PLAY", "STOP", "NEXT", "PREV", "EXIT")


def createSlideshowMachine(owner, facts, log=None):
    """owner: has a do_<action>() method for every action of the table; facts: function() -> dict of the facts."""
    def perform(action, _event, _data):
        getattr(owner, "do_" + action)()
    return StateMachine("Slideshow", FIELDS, INITIAL, RULES, perform, facts, log)
