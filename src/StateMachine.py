# Copyright (C) 2018-2026 by xcentaurix
# License: GNU General Public License v3.0


# A small table driven state machine. No enigma2 imports: the tables can be tested and printed without a box.
#
# The state is a set of named fields (run: stopped/running, chrome: shown/hidden, ...), each with a list of allowed values.
# Facts are things that are not state but are looked up when an event comes in (the type of the current file, whether the
# slideshow is at its last picture, ...): a function of the owner returns them.
#
# A rule says: when this EVENT comes, and the state fields and facts match, do these ACTIONS and go to these field values.
# Rules are tried in the order of the table, the first one that matches wins. A field or fact that a rule does not mention
# matches everything. A value can be a single value, a tuple of values, or Not(...) of values.
#
# The new state is set first and the actions are performed afterwards, so an action sees the state it leads to. An action is
# the name of a method of the owner (perform(name) is called). Events that are dispatched while an action runs are queued
# and handled after the current one is complete: no recursion, and the order is always the order of the dispatches. A rule can
# also name events that follow it (then): they are dispatched after its actions.


class Not:
    """Matches every value except the given ones."""

    def __init__(self, *values):
        self.values = values

    def __repr__(self):
        return "not " + "/".join(str(value) for value in self.values)


class Rule:
    def __init__(self, event, when, facts, do, to, then, note):
        self.event = event
        self.when = when    # state field -> value(s)
        self.facts = facts  # fact -> value(s)
        self.do = do        # tuple of action names
        self.to = to        # state field -> new value
        self.then = then    # events that are dispatched after the actions
        self.note = note

    def __repr__(self):
        return f"Rule({self.event}, when={self.when}, facts={self.facts}, do={self.do}, to={self.to}, then={self.then})"


def rule(event, when=None, facts=None, do=(), to=None, then=(), note=""):
    """One row of a table. do and then: a name or a tuple of names."""
    if isinstance(do, str):
        do = (do,)
    if isinstance(then, str):
        then = (then,)
    return Rule(event, dict(when or {}), dict(facts or {}), tuple(do), dict(to or {}), tuple(then), note)


def _matches(wanted, value):
    if isinstance(wanted, Not):
        return value not in wanted.values
    if isinstance(wanted, (tuple, list, set, frozenset)):
        return value in wanted
    return value == wanted


def _text(wanted):
    if isinstance(wanted, (tuple, list, set, frozenset)):
        return "/".join(str(value) for value in wanted)
    return str(wanted)


class StateMachine:
    """fields: {name: (allowed values...)}, initial: {name: value}, rules: list of rule(), perform: function(action, event, data),
    facts: function() -> dict, called for every event that has a rule for it, log: function(text)."""

    def __init__(self, name, fields, initial, rules, perform, facts=None, log=None):
        self.name = name
        self.fields = {field: tuple(values) for field, values in fields.items()}
        self.rules = list(rules)
        self.perform = perform
        self.facts = facts or (lambda: {})
        self.log = log or (lambda text: None)
        self.state = {}
        self.events = {r.event for r in self.rules} | {event for r in self.rules for event in r.then}
        self._queue = []
        self._busy = False
        self._check(initial)
        self.state = dict(initial)

    def _check(self, initial):
        """A typo in a table must not become a rule that never matches."""
        if set(initial) != set(self.fields):
            raise ValueError(f"{self.name}: initial state {sorted(initial)} does not set exactly the fields {sorted(self.fields)}")
        for field, value in initial.items():
            if value not in self.fields[field]:
                raise ValueError(f"{self.name}: {value!r} is not a value of {field}")
        for r in self.rules:
            for field, wanted in r.when.items():
                if field not in self.fields:
                    raise ValueError(f"{self.name}: {r.event}: unknown state field {field}")
                values = wanted.values if isinstance(wanted, Not) else (wanted if isinstance(wanted, (tuple, list, set, frozenset)) else (wanted,))
                for value in values:
                    if value not in self.fields[field]:
                        raise ValueError(f"{self.name}: {r.event}: {value!r} is not a value of {field}")
            for field, value in r.to.items():
                if field not in self.fields:
                    raise ValueError(f"{self.name}: {r.event}: unknown state field {field} in to")
                if value not in self.fields[field]:
                    raise ValueError(f"{self.name}: {r.event}: {value!r} is not a value of {field}")

    def find(self, event, facts=None):
        """The rule that handles the event in the current state, or None."""
        if facts is None:
            facts = self.facts()
        for r in self.rules:
            if r.event != event:
                continue
            if all(_matches(wanted, self.state[field]) for field, wanted in r.when.items()) and \
                    all(_matches(wanted, facts.get(fact)) for fact, wanted in r.facts.items()):
                return r
        return None

    def dispatch(self, event, data=None):
        """Handle the event now, or after the event that is being handled."""
        self._queue.append((event, data))
        if self._busy:
            return
        self._busy = True
        try:
            while self._queue:
                self._step(*self._queue.pop(0))
        finally:
            self._busy = False
            self._queue.clear()

    def _step(self, event, data):
        r = self.find(event)
        if r is None:
            self.log(f"{self.name}: {event} in {self.state}: ignored")
            return
        self.log(f"{self.name}: {event} in {self.state} -> {r.to or 'same'}: {', '.join(r.do) or 'nothing'}")
        self.state.update(r.to)
        for action in r.do:
            self.perform(action, event, data)
        for following in r.then:
            self.dispatch(following)

    def describe(self):
        """The table as Markdown, one row per rule (documentation, and a review aid)."""
        lines = [f"### {self.name}", "", "| Event | State | Facts | Actions | Next state | Then | Note |", "|---|---|---|---|---|---|---|"]
        for r in self.rules:
            when = ", ".join(f"{field}={_text(value)}" for field, value in r.when.items()) or "any"
            facts = ", ".join(f"{fact}={_text(value)}" for fact, value in r.facts.items()) or "-"
            to = ", ".join(f"{field}={value}" for field, value in r.to.items()) or "same"
            lines.append(f"| {r.event} | {when} | {facts} | {', '.join(r.do) or '-'} | {to} | {', '.join(r.then) or '-'} | {r.note} |")
        return "\n".join(lines) + "\n"
