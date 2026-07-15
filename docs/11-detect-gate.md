# Detect gate

Running pose extraction and a theft classifier on every frame of an empty room is wasted compute. Most of the time a camera watches nothing happening. The detect gate is the cheap filter that sits in front of the expensive pipeline: a small model that answers one question — is a person in view — and only when the answer flips does the rest of the system wake up.

The gate reads frames off the camera's stream, runs a person detector on each, feeds the yes/no into a state machine that tracks whether someone is present, and streams entry and exit events to the ai-service. It carries no pose model and no classifier. Its whole job is to turn a continuous frame stream into a small number of edges — a person entered, a person left — that gate the work downstream.

## Reading the stream

The gate is a consumer of the frame transport. It reads `frame:<camera_id>` as the `gate` ACL user, which holds `+xread` and `+xlen` on `frame:*` and nothing else — it can read the stream and can't write to it, can't touch any other key.

The read is a blocking `XREAD` from the special `$` id:

```python
res = client.xread({self._stream_key: "$"}, count=1, block=self._read_block_ms)
```

`$` means "only entries that arrive after this call," so the gate never reads a backlog. On connect it starts from the newest frame and moves forward; frames written while the gate was down are skipped, not replayed. For a live presence check that's the right behavior — a gate catching up on a minute of stale frames would fire entry and exit events for people who already came and went. It wants now, not history.

The blocking read runs in a thread pool executor so the event loop stays free while `XREAD` waits. Each frame comes off the stream as JPEG bytes and is decoded back to an array for the detector:

```python
frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
```

A read error drops the connection, backs off exponentially, and reconnects — the gate rides out a transport restart the same way the publisher does on the write side. A frame that fails to decode is logged and skipped rather than crashing the loop.

## The detector

The person check is yolov8n — the smallest YOLO model — run with the class filter pinned to person and everything else discarded. It doesn't localize, count, or track. It answers one boolean and returns the top confidence alongside it:

```python
results = self._yolo(
    frame,
    classes=[self._person_class],
    conf=self._confidence,
    verbose=False,
)
```

The detector sits behind a Protocol, so the concrete yolov8n implementation is swappable. That's what lets the gate run against a recorded clip instead of a live camera — the main loop picks a camera stream source or a clip-file source from config, and the detector doesn't know or care which. The gate logic can be exercised end to end without a camera plugged in.

The model call blocks, so it runs in the same single-worker thread pool as the stream read, off the event loop:

```python
result = await loop.run_in_executor(pool, detector.detect, frame)
```

One worker, not many, on purpose. The frames arrive in order and the state machine depends on that order — a person's presence is a sequence, not a set of independent frames. Running detection concurrently across a pool would let frame N+1 finish before frame N and feed the state machine out of order. A single worker keeps the sequence intact.

## Presence state machine

The state machine turns a stream of per-frame booleans into three states and two edges. States are unknown, absent, present. Edges are entered and left. The machine's whole logic is when to move between states and which move emits an edge.

```python
def observe(self, person_seen: bool) -> PresenceEdge:
    if person_seen:
        self._empty_streak = 0
        if self._state is not PresenceState.PRESENT:
            self._state = PresenceState.PRESENT
            return PresenceEdge.ENTERED
        return PresenceEdge.NONE
    self._empty_streak += 1
    if self._state is PresenceState.PRESENT and self._empty_streak >= self._exit_debounce_frames:
        self._state = PresenceState.ABSENT
        return PresenceEdge.LEFT
    if self._state is PresenceState.UNKNOWN and self._empty_streak >= self._exit_debounce_frames:
        self._state = PresenceState.ABSENT
    return PresenceEdge.NONE
```

Entry is instant. The first frame with a person flips the state to present and emits entered, no waiting. The frames at the very start of someone walking into view are the ones the downstream pipeline most needs, so the gate opens on the first sight.

Exit is debounced. A single empty frame doesn't mean the person left — the detector misses a frame when someone turns side-on, is partly occluded, or the confidence dips below threshold for a moment. If the gate emitted left on the first empty frame, a person standing still in view would generate a stream of spurious enter/leave pairs every time detection flickered. So exit waits for a run of empty frames: presence holds until 30 consecutive frames with no person, and only then flips to absent and emits left. At the gate's 15 fps, 30 frames is two seconds of continuous emptiness — long enough to ride through detection dropouts, short enough that a genuinely empty room settles quickly.

The empty streak resets to zero on any frame with a person, so the 30 have to be consecutive. One detection in the middle of a quiet stretch restarts the count.

The unknown state handles startup. When the gate boots into an empty room, the state is unknown, not absent — and the machine settles unknown to absent after the same debounce without emitting an edge. A gate that started in an empty room would otherwise have no clean way to distinguish "was present, now gone" from "was never anyone here," and a spurious left on startup would tell the ai-service someone left who was never there. The silent unknown-to-absent transition avoids that: the room settles to absent quietly, and the first real edge is a true entry.

## Streaming events to the ai-service

Edges go to the ai-service over a bidirectional gRPC stream. The contract is one method:

```protobuf
service PresenceService {
  rpc StreamPresence(stream PresenceEvent) returns (stream PresenceAck);
}
```

The gate sends a stream of presence events, the ai-service sends back a stream of acks. Bidirectional rather than a plain call per event because the connection stays open across the life of the gate — events flow as they happen, acks flow back as they're processed, neither side blocks on the other. Each event carries a unique id built from camera, session, and a per-gate sequence number, the edge kind, a timestamp, the detection confidence, and the source frame index, so the ai-service can order events, dedupe on the id, and tie an event back to the exact frame that produced it.

Events queue before they send. The client holds a bounded async queue between the frame loop that produces edges and the stream coroutine that sends them, so a slow or reconnecting stream doesn't block the detection loop. The queue's backpressure choice is deliberate:

```python
try:
    self._queue.put_nowait(event)
except asyncio.QueueFull:
    _ = self._queue.get_nowait()
    self._queue.put_nowait(event)
    logger.warning("presence queue full, dropped oldest event")
```

When the queue fills, the oldest event drops to make room for the newest. This is the opposite of the frame transport, and for a reason. Frames are interchangeable — any recent frame is as good as another, so under pressure the transport keeps flowing whatever it can. Presence events are not interchangeable — each one is a distinct entry or exit. Dropping the oldest keeps the most recent state transitions, which are the ones that describe the room now. In practice the queue holds 64 events and the gate produces one event per entry or exit, so it only fills if the ai-service is unreachable for a long stretch, at which point the newest edges are the ones worth keeping.

A lost stream reconnects with exponential backoff, and the connect uses `channel_ready` with a timeout rather than sending blind — a lazy gRPC channel would otherwise hang on the first event with a dead peer instead of failing and backing off.

## How the container runs

The gate boots the same shape as the camera service: an async main that builds the source, detector, state machine, and presence client, wires them, installs signal handlers, and runs the frame loop and the stream client as tasks until a stop signal. Shutdown cancels the loop, drains the client, closes the source, and unloads the model.

Liveness is a heartbeat file touched at the top of every frame-loop pass, checked by the container healthcheck the same way the camera service checks its capture thread. The detection work runs in a thread pool and the loop that drives it runs on the event loop; touching the heartbeat inside the loop proves the loop is turning. A frame loop that stalled — a wedged read, a hung executor — lets the heartbeat go stale and the container is marked unhealthy.

The presence state is exposed as a metric alongside frame, detection, entry, and exit counters, so the dashboard shows the room's occupancy over time and how often the gate opens and closes — the shape that tells whether the confidence threshold and debounce are tuned right for the space.
