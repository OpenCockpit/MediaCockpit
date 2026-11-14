# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# What the keys and the end of a song do in the music player, in one table. The screen (CockpitMusicPlayer.py) turns a key or a
# player event into an event of this table and performs the actions the table returns, in methods do_<action>().
#
# State
#   play  PLAYING   a song plays
#         PAUSED    a song is paused
#         ENDED     no song plays: the list is finished (repeat is off), or no song can be played
# Facts
#   has_next    the queue has a song after the current one (repeat, shuffle and the end of the list taken into account)
#   all_failed  every song in a row could not be played

from .StateMachine import StateMachine, rule

PLAYING, PAUSED, ENDED = "PLAYING", "PAUSED", "ENDED"

FIELDS = {"play": (PLAYING, PAUSED, ENDED)}
INITIAL = {"play": ENDED}

RULES = [
    # The screen is laid out: the list, the modes and the first song.
    rule("START", do=("init_widgets", "fill_list", "show_modes", "play_current"), to={"play": PLAYING}),

    # PLAY: pause or go on; with nothing playing, start the current song again
    rule("PLAY", when={"play": PLAYING}, do="pause", to={"play": PAUSED}),
    rule("PLAY", when={"play": PAUSED}, do="unpause", to={"play": PLAYING}),
    rule("PLAY", when={"play": ENDED}, do="play_current", to={"play": PLAYING}),

    # the song to play changes
    rule("OK", do=("select_song", "play_current"), to={"play": PLAYING}, note="the song under the cursor of the queue"),
    rule("NEXT", do=("queue_next", "play_current"), to={"play": PLAYING}, note="round and round, whatever repeat says"),
    rule("PREV", do=("queue_previous", "play_current"), to={"play": PLAYING}),

    # the song ended on its own, or could not be played
    rule("SONG_ENDED", facts={"all_failed": True}, do=("stop_player", "show_cannot_play"), to={"play": ENDED},
         note="carrying on would spin forever"),
    rule("SONG_ENDED", facts={"has_next": False}, do=("stop_player", "show_stopped", "show_position"), to={"play": ENDED},
         note="the last song and repeat is off"),
    rule("SONG_ENDED", do=("queue_ended", "play_current"), to={"play": PLAYING}),

    # CHANNEL+, CHANNEL-: skip inside the song
    rule("SEEK_FORWARD", when={"play": (PLAYING, PAUSED)}, do="seek_forward"),
    rule("SEEK_BACKWARD", when={"play": (PLAYING, PAUSED)}, do="seek_backward"),

    # modes and the cursor of the queue
    rule("SHUFFLE", do="toggle_shuffle"),
    rule("REPEAT", do="toggle_repeat"),
    rule("UP", do="move_up"),
    rule("DOWN", do="move_down"),

    # EXIT, RED, STOP
    rule("EXIT", do=("stop_player", "close"), to={"play": ENDED}),
]

KEY_EVENTS = ("PLAY", "OK", "NEXT", "PREV", "SEEK_FORWARD", "SEEK_BACKWARD", "SHUFFLE", "REPEAT", "UP", "DOWN", "EXIT")


def createMusicMachine(owner, facts, log=None):
    """owner: has a do_<action>() method for every action of the table; facts: function() -> dict of the facts."""
    def perform(action, _event, _data):
        getattr(owner, "do_" + action)()
    return StateMachine("MusicPlayer", FIELDS, INITIAL, RULES, perform, facts, log)
