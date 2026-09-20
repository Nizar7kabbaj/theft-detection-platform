from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6
LEFT_WRIST = 9
RIGHT_WRIST = 10
LEFT_HIP = 11
RIGHT_HIP = 12
TORSO_KEYPOINTS = (LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP)
MATCH_HEIGHTS = 1.5


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
class _Item:
    item_id: int
    class_name: str
    bbox: tuple[float, float, float, float]
    rest_x: float
    rest_y: float
    rest_height: float
    last_seen_at: float
    last_seen_frame: int
    held: bool = False
    held_by_track: int = 0
    held_wrist_index: int = -1
    held_wrist_x: float = 0.0
    held_wrist_y: float = 0.0
    held_distance: float = 0.0
    fired: bool = False


def _centre(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0


def _height(bbox: tuple[float, float, float, float]) -> float:
    return max(bbox[3] - bbox[1], 1.0)


def _edge_distance(x: float, y: float, bbox: tuple[float, float, float, float]) -> float:
    dx = max(bbox[0] - x, 0.0, x - bbox[2])
    dy = max(bbox[1] - y, 0.0, y - bbox[3])
    return math.hypot(dx, dy)


def _contains(x: float, y: float, bbox: tuple[float, float, float, float]) -> bool:
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def _near(
    bbox: tuple[float, float, float, float],
    other: tuple[float, float, float, float],
) -> tuple[bool, float]:
    x, y = _centre(bbox)
    other_x, other_y = _centre(other)
    distance = math.hypot(x - other_x, y - other_y)
    return distance <= MATCH_HEIGHTS * max(_height(bbox), _height(other)), distance


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
        move_ratio: float,
        missing_seconds: float,
        keypoint_confidence: float,
        expiry_seconds: float,
    ) -> None:
        self._grab_ratio = grab_ratio
        self._move_ratio = move_ratio
        self._missing_seconds = missing_seconds
        self._keypoint_confidence = keypoint_confidence
        self._expiry_seconds = expiry_seconds
        self._items: dict[str, list[_Item]] = {}
        self._persons: dict[tuple[str, int], float] = {}
        self._last_fired: dict[str, float] = {}
        self._ids = itertools.count(1)

    def retune(
        self,
        grab_ratio: float,
        missing_seconds: float,
        keypoint_confidence: float,
        expiry_seconds: float,
    ) -> None:
        self._grab_ratio = grab_ratio
        self._missing_seconds = missing_seconds
        self._keypoint_confidence = keypoint_confidence
        self._expiry_seconds = expiry_seconds

    def observe(
        self,
        camera_id: str,
        frame_index: int,
        captured_at: float,
        persons: list[
            tuple[int, list[tuple[float, float, float]], tuple[float, float, float, float]]
        ],
        objects: list[tuple[str, tuple[float, float, float, float]]],
    ) -> tuple[list[int], list[ConcealmentVerdict]]:
        for track_id, _keypoints, _bbox in persons:
            self._persons[(camera_id, track_id)] = captured_at
        bodies = {track_id: bbox for track_id, _keypoints, bbox in persons}
        items = self._items.setdefault(camera_id, [])
        free = list(items)
        object_ids: list[int] = []
        for class_name, bbox in objects:
            item = self._match(free, class_name, bbox, bodies)
            if item is None:
                x, y = _centre(bbox)
                item = _Item(
                    item_id=next(self._ids),
                    class_name=class_name,
                    bbox=bbox,
                    rest_x=x,
                    rest_y=y,
                    rest_height=_height(bbox),
                    last_seen_at=captured_at,
                    last_seen_frame=frame_index,
                )
                items.append(item)
            else:
                free.remove(item)
            item.bbox = bbox
            item.last_seen_at = captured_at
            item.last_seen_frame = frame_index
            item.fired = False
            self._update_hold(item, persons, bodies)
            object_ids.append(item.item_id)
        verdicts = self._collect(camera_id, frame_index, captured_at, persons, objects)
        return object_ids, verdicts

    def _match(
        self,
        free: list[_Item],
        class_name: str,
        bbox: tuple[float, float, float, float],
        bodies: dict[int, tuple[float, float, float, float]],
    ) -> _Item | None:
        x, y = _centre(bbox)
        best: _Item | None = None
        best_distance = math.inf
        for item in free:
            if item.class_name != class_name:
                continue
            near, distance = _near(bbox, item.bbox)
            holder = bodies.get(item.held_by_track) if item.held else None
            on_holder = holder is not None and _contains(x, y, holder)
            if (near or on_holder) and distance < best_distance:
                best = item
                best_distance = distance
        return best

    def _closest_wrist(
        self,
        bbox: tuple[float, float, float, float],
        persons: list[
            tuple[int, list[tuple[float, float, float]], tuple[float, float, float, float]]
        ],
    ) -> tuple[float, int, int, float, float] | None:
        closest: tuple[float, int, int, float, float] | None = None
        for track_id, keypoints, _bbox in persons:
            if not _has_torso(keypoints, self._keypoint_confidence):
                continue
            reference = _reference_length(keypoints)
            for wrist_index in (LEFT_WRIST, RIGHT_WRIST):
                wrist_x, wrist_y, wrist_confidence = keypoints[wrist_index]
                if wrist_confidence < self._keypoint_confidence:
                    continue
                distance = _edge_distance(wrist_x, wrist_y, bbox) / reference
                if distance > self._grab_ratio:
                    continue
                if closest is None or distance < closest[0]:
                    closest = (distance, track_id, wrist_index, wrist_x, wrist_y)
        return closest

    def _update_hold(
        self,
        item: _Item,
        persons: list[
            tuple[int, list[tuple[float, float, float]], tuple[float, float, float, float]]
        ],
        bodies: dict[int, tuple[float, float, float, float]],
    ) -> None:
        x, y = _centre(item.bbox)
        moved = math.hypot(x - item.rest_x, y - item.rest_y) / item.rest_height
        closest = self._closest_wrist(item.bbox, persons)
        if closest is not None:
            item.held = True
            item.held_distance = closest[0]
            item.held_by_track = closest[1]
            item.held_wrist_index = closest[2]
            item.held_wrist_x = closest[3]
            item.held_wrist_y = closest[4]
            return
        holder = bodies.get(item.held_by_track)
        on_holder = holder is not None and _contains(x, y, holder)
        item.held = item.held and moved >= self._move_ratio and on_holder

    def _still_visible(
        self,
        item: _Item,
        objects: list[tuple[str, tuple[float, float, float, float]]],
    ) -> bool:
        return any(
            class_name == item.class_name and _near(bbox, item.bbox)[0]
            for class_name, bbox in objects
        )

    def _hand_on_spot(
        self,
        item: _Item,
        persons: list[
            tuple[int, list[tuple[float, float, float]], tuple[float, float, float, float]]
        ],
    ) -> bool:
        for track_id, keypoints, _bbox in persons:
            if track_id != item.held_by_track:
                continue
            if not _has_torso(keypoints, self._keypoint_confidence):
                return True
            reference = _reference_length(keypoints)
            visible = False
            for wrist_index in (LEFT_WRIST, RIGHT_WRIST):
                wrist_x, wrist_y, wrist_confidence = keypoints[wrist_index]
                if wrist_confidence < self._keypoint_confidence:
                    continue
                visible = True
                if _edge_distance(wrist_x, wrist_y, item.bbox) / reference <= self._grab_ratio:
                    return True
            return not visible
        return True

    def _holder_present(self, camera_id: str, item: _Item, captured_at: float) -> bool:
        seen = self._persons.get((camera_id, item.held_by_track))
        return seen is not None and captured_at - seen <= self._missing_seconds

    def _ready(
        self,
        camera_id: str,
        item: _Item,
        captured_at: float,
        persons: list[
            tuple[int, list[tuple[float, float, float]], tuple[float, float, float, float]]
        ],
        objects: list[tuple[str, tuple[float, float, float, float]]],
    ) -> bool:
        if item.fired or not item.held:
            return False
        if captured_at - item.last_seen_at < self._missing_seconds:
            return False
        if self._still_visible(item, objects):
            return False
        if self._hand_on_spot(item, persons):
            return False
        return self._holder_present(camera_id, item, captured_at)

    def _collect(
        self,
        camera_id: str,
        frame_index: int,
        captured_at: float,
        persons: list[
            tuple[int, list[tuple[float, float, float]], tuple[float, float, float, float]]
        ],
        objects: list[tuple[str, tuple[float, float, float, float]]],
    ) -> list[ConcealmentVerdict]:
        verdicts: list[ConcealmentVerdict] = []
        last_fired = self._last_fired.get(camera_id)
        muted = last_fired is not None and captured_at - last_fired < self._expiry_seconds
        kept: list[_Item] = []
        for item in self._items.get(camera_id, []):
            if captured_at - item.last_seen_at > self._expiry_seconds:
                continue
            kept.append(item)
            if not self._ready(camera_id, item, captured_at, persons, objects):
                continue
            item.fired = True
            if muted:
                continue
            self._last_fired[camera_id] = captured_at
            muted = True
            verdicts.append(
                ConcealmentVerdict(
                    object_track_id=item.item_id,
                    object_class=item.class_name,
                    last_seen_bbox=item.bbox,
                    last_seen_frame=item.last_seen_frame,
                    missing_frames=frame_index - item.last_seen_frame,
                    person_track_id=item.held_by_track,
                    wrist_index=item.held_wrist_index,
                    wrist_x=item.held_wrist_x,
                    wrist_y=item.held_wrist_y,
                    grab_distance=item.held_distance,
                )
            )
        self._items[camera_id] = kept
        stale = [
            key
            for key, seen in self._persons.items()
            if key[0] == camera_id and captured_at - seen > self._expiry_seconds
        ]
        for key in stale:
            del self._persons[key]
        return verdicts
