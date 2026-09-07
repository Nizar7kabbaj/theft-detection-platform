from __future__ import annotations

from enum import StrEnum


class PresenceState(StrEnum):
    UNKNOWN = "unknown"
    ABSENT = "absent"
    PRESENT = "present"


class PresenceEdge(StrEnum):
    NONE = "none"
    ENTERED = "entered"
    LEFT = "left"


class PresenceStateMachine:
    def __init__(self, exit_debounce_frames: int) -> None:
        self._exit_debounce_frames = exit_debounce_frames
        self._state = PresenceState.UNKNOWN
        self._empty_streak = 0
        self._cold_start_absent = False

    @property
    def state(self) -> PresenceState:
        return self._state

    @property
    def cold_start_absent(self) -> bool:
        return self._cold_start_absent

    def observe(self, person_seen: bool) -> PresenceEdge:
        if person_seen:
            self._empty_streak = 0
            if self._state is not PresenceState.PRESENT:
                self._state = PresenceState.PRESENT
                self._cold_start_absent = False
                return PresenceEdge.ENTERED
            return PresenceEdge.NONE
        self._empty_streak += 1
        if (
            self._state is PresenceState.PRESENT
            and self._empty_streak >= self._exit_debounce_frames
        ):
            self._state = PresenceState.ABSENT
            return PresenceEdge.LEFT
        if (
            self._state is PresenceState.UNKNOWN
            and self._empty_streak >= self._exit_debounce_frames
        ):
            self._state = PresenceState.ABSENT
            self._cold_start_absent = True
            return PresenceEdge.LEFT
        return PresenceEdge.NONE
