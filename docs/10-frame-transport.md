# Frame transport

The camera service and the detect-gate service run in separate containers, and frames have to cross from one to the other. The path is a Redis stream. The camera writes each encoded frame to a stream keyed by camera id, and the gate reads from it. A stream rather than a queue because the design assumes more than one reader. The gate reads today, a clip extractor later, and a Redis stream lets many consumers read the same entries independently without one draining what another needs.

The stream key is `frame:<camera_id>`, so `frame:cam-01` for the first camera. One stream per camera keeps a busy camera from crowding a quiet one and lets a consumer subscribe to a single camera or fan out across several by key pattern. The instance is a dedicated Redis on its own container, separate from the cache and broker instances, holding nothing but frame streams.

## Writing frames

The publisher runs on its own thread inside the camera service, fed by the capture loop through a bounded in-memory queue. Capture pushes each encoded frame onto the queue and moves on; the publisher thread drains the queue and writes to Redis. The two are decoupled on purpose. A Redis write that stalls can't be allowed to block the grab, so capture never touches Redis directly. It hands off to the queue and returns immediately.

```python
def push(self, frame: CapturedFrame) -> None:
    with self._queue_lock:
        if len(self._queue) == self._queue.maxlen:
            self._dropped_overflow_total += 1
        self._queue.append(frame)
    self._wakeup.set()
```

The queue is bounded. When it fills, whether the publisher is falling behind a fast capture or Redis is unreachable, the oldest frame drops and the count is tracked. A bounded queue that drops old frames is the right failure mode for live video: a detection pipeline wants the newest frame, not a backlog of stale ones, so under pressure the transport sheds the past rather than the present.

The write is a single `XADD` with an approximate length cap:

```python
client.xadd(
    self._stream_key,
    {
        "payload": frame.payload,
        "session_id": frame.session_id,
        "frame_index": frame.frame_index,
        "camera_id": frame.camera_id,
        "timestamp_unix": frame.timestamp_unix,
    },
    maxlen=self._maxlen,
    approximate=True,
)
```

The payload is the JPEG bytes. The rest are the fields a consumer needs to place the frame: which capture session it belongs to, its index within that session, which camera, when it was taken. `maxlen` with `approximate=True` trims the stream as it grows, capping it near a fixed length without forcing Redis to trim to an exact count on every write. The approximate trim is cheaper, since Redis removes whole macro-nodes when it can, and the exact cap doesn't matter here, only that the stream stays bounded.

A failed write backs off and retries. The publisher counts the failure, sleeps with exponential backoff up to a ceiling, and keeps the frame it was holding. It doesn't drop on a Redis error, it waits for Redis to come back. Backoff resets on the first frame that lands. The connection is a pooled client built lazily on first use, so a publisher that starts before Redis is ready doesn't fail at construction.

## Access control

The stream instance runs with an ACL user per client, each holding the narrowest set of grants its job needs. The camera writes and the gate reads, and neither can do the other's work.
```
user default on #<REDACTED> ~* &* -@all +ping +@connection
user camera on #<REDACTED> ~frame:* resetchannels -@all +@connection +xadd +client +ping
user gate on #<REDACTED> ~frame:* resetchannels -@all +@connection +xread +xlen +client +ping
user ai on #<REDACTED> ~ai:track:* resetchannels -@all +@connection +xadd +xrange +xlen +ttl +expire +del +client +ping
user exporter on #<REDACTED> resetchannels ~* -@all +@connection +info +client +ping +latency +slowlog
```
The camera user can run `xadd` and nothing else that touches data, scoped to keys matching `frame:*`. It can't read the stream back, can't write anywhere outside the frame namespace, can't run any other data command. The gate user can `xread` and `xlen` on the same key pattern and can't write at all. A client that only ever produces frames holds no read grant; a client that only ever consumes holds no write grant. The blast radius of a leaked camera credential is limited to writing frame streams: it can't read them, can't reach the ai namespace, can't flush anything.

The `default` user is stripped to `+ping +@connection` and nothing more. Every client that does real work connects as a named user, so the password on `default` is a fallback that grants no data access even if used. New consumers get the same treatment: a clip extractor would connect as its own read-only user scoped to `frame:*`, not by sharing the gate's credential.

## Bounding memory

The instance caps at 1500mb with `maxmemory-policy allkeys-lru`. The cap sizes to the stream's real footprint: the camera publishes native MJPG frames straight from the device, no re-encode, so each entry carries the camera's own JPEG at roughly 490KB rather than a re-compressed frame at a fixed quality. At `MAXLEN` 900, thirty seconds of pre-trigger history at 30fps, a full stream sits near 440MB of payload plus stream overhead, and the cap leaves room for that working set to breathe without crowding the instance. Measured under sustained 30fps capture the instance holds around 340MB resident, roughly a quarter of the cap.

The publisher's `MAXLEN` trim is what keeps the stream bounded in normal running. Every write caps the stream near 900 entries, so it never climbs toward the memory ceiling on its own. The eviction policy is the backstop for the abnormal case: a consumer backlog, a second producer, a key pattern the sizing didn't account for. Under `allkeys-lru` Redis sheds the least-recently-used entries and capture keeps writing. For a live pipeline the frame being captured now matters more than a frame from a few seconds ago, so shedding the old to keep accepting the new is the failure mode that keeps the camera running rather than stalling it on a full instance.

Persistence is off, with `appendonly no` and `save ""`. Frames are live data with a lifetime measured in seconds; there's nothing to gain from writing them to disk, and a stream that's trimmed to a few hundred entries and never restored from an old dump is the correct behavior across a restart. `FLUSHALL`, `FLUSHDB`, and `DEBUG` are renamed to empty strings, so no client, even one holding the default password, can wipe the instance or drop into debug commands.
