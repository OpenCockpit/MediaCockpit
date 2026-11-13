# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


from random import shuffle as shuffleList


REPEAT_ALL = 0      # at the end of the list start again (the default)
REPEAT_ONE = 1      # the same song again and again
REPEAT_OFF = 2      # stop after the last song
REPEAT_MODES = (REPEAT_ALL, REPEAT_ONE, REPEAT_OFF)     # in the order the key cycles through them


class SongQueue():
    """The order in which the songs of a list are played. Songs are identified by their index in the list; the queue only keeps
    the play order (natural or shuffled) and the position in it."""

    def __init__(self, count, index=0):
        self.count = count
        self.order = list(range(count))
        self.position = index if 0 <= index < count else 0
        self.shuffle = False
        self.repeat = REPEAT_ALL

    @property
    def current(self):
        """Index in the song list of the song to play, -1 for an empty list."""
        return self.order[self.position] if self.order else -1

    def songAt(self, position):
        return self.order[position]

    def next(self):
        """The user asks for the next song: always goes on, round and round."""
        if self.count:
            self.position = (self.position + 1) % self.count
        return self.current

    def previous(self):
        if self.count:
            self.position = (self.position - 1) % self.count
        return self.current

    def songEnded(self):
        """The current song ended on its own. Returns the song to play next, or -1 when the list is finished."""
        if not self.count:
            return -1
        if self.repeat == REPEAT_ONE:
            return self.current
        if self.position + 1 >= self.count and self.repeat == REPEAT_OFF:
            return -1
        return self.next()

    def peekNext(self):
        """The song that songEnded() would play, -1 if there is none. Does not move."""
        if not self.count:
            return -1
        if self.repeat == REPEAT_ONE:
            return self.current
        if self.position + 1 >= self.count and self.repeat == REPEAT_OFF:
            return -1
        return self.order[(self.position + 1) % self.count]

    def jump(self, song_index):
        """Make the song with this index in the song list the current one."""
        if song_index in self.order:
            self.position = self.order.index(song_index)
        return self.current

    def toggleShuffle(self):
        """Shuffled, the current song stays first and the rest is mixed; unshuffled, the natural order comes back with the
        current song still the current one."""
        current = self.current
        self.shuffle = not self.shuffle
        if self.shuffle:
            rest = [i for i in self.order if i != current]
            shuffleList(rest)
            self.order = [current] + rest if current >= 0 else rest
            self.position = 0
        else:
            self.order = list(range(self.count))
            self.position = current if current >= 0 else 0
        return self.shuffle

    def cycleRepeat(self):
        self.repeat = REPEAT_MODES[(REPEAT_MODES.index(self.repeat) + 1) % len(REPEAT_MODES)]
        return self.repeat
