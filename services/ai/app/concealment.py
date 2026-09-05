from __future__ import annotations

import math
from dataclasses import dataclass

LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_WRIST = 9
RIGHT_WRIST = 10
LEFT_HIP = 11
RIGHT_HIP = 12
TORSO_KEYPOINTS = (LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP)


@dataclass(frozen=True, slots=True)
class ConcealmentVerdict:
    object_track_id: int
    object_class: str
    last_seen_bbox: tuple[float, float, float, float]
    last_seen_frame: int
    missing_frames: int
    person_track_id: int
    wrist_index: int
    wrist_x: float
    wrist_y: float
    grab_distance: float


@dataclass(slots=True)
class _ObjectState:
    class_name: str
    bbox: tuple[float, float, float, float]
    last_seen_frame: int
    held_by_track: int
    held_wrist_index: int
    held_wrist_x: float
    held_wrist_y: float
    held_distance: float
    held_frame: int
    fired: bool


def _centre(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def _has_torso(keypoints: list[tuple[float, float, float]], min_confidence: float) -> bool:
    if len(keypoints) <= max(TORSO_KEYPOINTS):
        return False
    return all(keypoints[index][2] >= min_confidence for index in TORSO_KEYPOINTS)


def _reference_length(keypoints: list[tuple[float, float, float]]) -> float:
    shoulder_x = (keypoints[LEFT_SHOULDER][0] + keypoints[RIGHT_SHOULDER][0]) / 2.0
    shoulder_y = (keypoints[LEFT_SHOULDER][1] + keypoints[RIGHT_SHOULDER][1]) / 2.0
    hip_x = (keypoints[LEFT_HIP][0] + keypoints[RIGHT_HIP][0]) / 2.0
    hip_y = (keypoints[LEFT_HIP][1] + keypoints[RIGHT_HIP][1]) / 2.0
    return max(math.hypot(shoulder_x - hip_x, shoulder_y - hip_y), 1.0)


class ConcealmentTracker:
    def __init__(
        self,
        grab_ratio: float,
        missing_frames: int,
        keypoint_confidence: float,
        expiry_frames: int,
    ) -> None:
        self._grab_ratio = grab_ratio
        self._missing_frames = missing_frames
        self._keypoint_confidence = keypoint_confidence
        self._expiry_frames = expiry_frames
        self._objects: dict[tuple[str, int], _ObjectState] = {}
        self._persons: dict[tuple[str, int], int] = {}
        self._last_fired: dict[str, int] = {}

    def observe(
        self,
        camera_id: str,
        frame_index: int,
        persons: list[tuple[int, list[tuple[float, float, float]]]],
        objects: list[tuple[int, str, tuple[float, float, float, float]]],
    ) -> list[ConcealmentVerdict]:
        for track_id, _keypoints in persons:
            self._persons[(camera_id, track_id)] = frame_index
        visible = {track_id for track_id, _name, _bbox in objects}
        for track_id, class_name, bbox in objects:
            key = (camera_id, track_id)
            state = self._objects.get(key)
            if state is None:
                state = _ObjectState(
                    class_name=class_name,
                    bbox=bbox,
                    last_seen_frame=frame_index,
                    held_by_track=0,
                    held_wrist_index=-1,
                    held_wrist_x=0.0,
                    held_wrist_y=0.0,
                    held_distance=0.0,
                    held_frame=-1,
                    fired=False,
                )
                self._objects[key] = state
            state.class_name = class_name
            state.bbox = bbox
            state.last_seen_frame = frame_index
            state.fired = False
            self._update_hold(state, bbox, persons, frame_index)
        return self._collect(camera_id, frame_index, visible)

    def _update_hold(
        self,
        state: _ObjectState,
        bbox: tuple[float, float, float, float],
        persons: list[tuple[int, list[tuple[float, float, float]]]],
        frame_index: int,
    ) -> None:
        object_x, object_y = _centre(bbox)
        best_distance = None
        for track_id, keypoints in persons:
            if not _has_torso(keypoints, self._keypoint_confidence):
                continue
            reference = _reference_length(keypoints)
            for wrist_index in (LEFT_WRIST, RIGHT_WRIST):
                if wrist_index >= len(keypoints):
                    continue
                wrist_x, wrist_y, wrist_confidence = keypoints[wrist_index]
                if wrist_confidence < self._keypoint_confidence:
                    continue
                distance = math.hypot(wrist_x - object_x, wrist_y - object_y) / reference
                if distance > self._grab_ratio:
                    continue
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    state.held_by_track = track_id
                    state.held_wrist_index = wrist_index
                    state.held_wrist_x = wrist_x
                    state.held_wrist_y = wrist_y
                    state.held_distance = distance
                    state.held_frame = frame_index

    def _hold_is_recent(self, state: _ObjectState) -> bool:
        if state.held_wrist_index < 0 or state.held_frame < 0:
            return False
        return state.last_seen_frame - state.held_frame <= self._missing_frames

    def _holder_was_present(self, camera_id: str, state: _ObjectState) -> bool:
        seen = self._persons.get((camera_id, state.held_by_track))
        if seen is None:
            return False
        return state.last_seen_frame - seen <= self._missing_frames

    def _collect(
        self,
        camera_id: str,
        frame_index: int,
        visible: set[int],
    ) -> list[ConcealmentVerdict]:
        verdicts: list[ConcealmentVerdict] = []
        expired: list[tuple[str, int]] = []
        last_fired = self._last_fired.get(camera_id)
        muted = last_fired is not None and frame_index - last_fired < self._expiry_frames
        for key, state in self._objects.items():
            if key[0] != camera_id:
                continue
            if key[1] in visible:
                continue
            missing = frame_index - state.last_seen_frame
            if missing > self._expiry_frames:
                expired.append(key)
                continue
            if state.fired:
                continue
            if missing < self._missing_frames:
                continue
            if not self._hold_is_recent(state):
                continue
            if not self._holder_was_present(camera_id, state):
                continue
            state.fired = True
            if muted:
                continue
            self._last_fired[camera_id] = frame_index
            muted = True
            verdicts.append(
                ConcealmentVerdict(
                    object_track_id=key[1],
                    object_class=state.class_name,
                    last_seen_bbox=state.bbox,
                    last_seen_frame=state.last_seen_frame,
                    missing_frames=missing,
                    person_track_id=state.held_by_track,
                    wrist_index=state.held_wrist_index,
                    wrist_x=state.held_wrist_x,
                    wrist_y=state.held_wrist_y,
                    grab_distance=state.held_distance,
                )
            )
        for key in expired:
            del self._objects[key]
        stale = [
            key
            for key, seen in self._persons.items()
            if key[0] == camera_id and frame_index - seen > self._expiry_frames
        ]
        for key in stale:
            del self._persons[key]
        return verdicts
