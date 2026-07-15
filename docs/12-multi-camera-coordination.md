# Multi-camera coordination

One camera watches one place. It reads its own frame stream, gates on presence, tracks people inside its own view, and never needs to know another camera exists. The single-camera path in chapters 9 through 11 is complete on those terms a camera is one process, one id, one stream, sealed off from every other camera by its Redis ACL.

That seal is the problem this layer solves. Put three cameras in a store and a person walking the floor crosses from one view to the next. Camera A knows him as track 5. He leaves A's frame, enters B's, and B has never heard of him a fresh stranger, track 3. Same person, two ids, no shared memory. If A had already flagged him for concealing an item, that suspicion dies at the boundary of A's view. B starts him from zero.

This chapter designs the layer that carries a person's identity and incident state across camera boundaries. It settles three things: who owns the per-camera zone definitions, how a track hands off from one camera to the next with its incident state intact, and how the system avoids raising two alerts for one event seen by two cameras. The first two get decided here. The third is left open, because deciding it without real overlapping camera feeds would be guessing, and a guess baked into a contract is expensive to unwind.

Nothing below is built or proven. It is a design and a set of contract sketches. The build waits for hardware that can produce two real overlapping views.

## Where the coordination lives

The obvious question first: does this logic go into the gate, into the ai-service, or somewhere new.

Not the gate. The gate is deliberately identity-blind. It takes a boolean — person seen or not and emits an edge entered or left. It carries no track id, no notion of who, no memory beyond a single empty-frame counter. Teaching it about other cameras would break the one thing it does well. It also reads its stream as an ACL user scoped to `frame:*` read-only; cross-camera state would need write access to keys it has no business touching.

Not the camera either. A camera writes to `frame:<its own id>` and nothing else. Its ACL user holds write on `frame:*` and no read anywhere. A camera that reached into another camera's state, or into a shared registry, would need a wider grant than its job justifies, and the isolation that makes the frame transport safe would be gone.

The ai-service is closer it already receives presence events from every gate over the bidirectional `StreamPresence` stream, so it is the one process that sees more than one camera at a time. But its job is running the pose model and the classifier on flagged clips. Loading cross-camera track bookkeeping into it mixes two concerns that fail differently and scale differently: model inference is GPU-bound and bursty, track handoff is state-bound and continuous.

So the coordination is a service of its own. A coordinator that consumes presence events, owns the cross-camera track registry, and holds the incident state that has to survive a boundary crossing. It sits above the per-camera pipeline and depends on it through the existing presence contract, not by reaching into any camera's or gate's internals. It gets its own Redis identity, scoped to the keys it owns and nothing else.

## Who owns the zones

A zone is a labelled region of one camera's view — this rectangle is the exit, that one is the shelf, this line is the checkout boundary. The single-camera config has none of this. Read `camera/app/core/config.py` and there is no zone field anywhere: a camera knows its id, its device, its frame size, its stream key, and nothing about the meaning of what it sees. Zones are greenfield.

Zones are per-camera because they describe physical geometry that only makes sense inside one camera's frame. A rectangle at pixel coordinates 800,200 to 1100,600 is "the exit" for the camera pointed at the door and meaningless for the camera pointed at the checkout. So the definitions are keyed by camera id, one set of zones per camera.

The ownership question is where they live and who loads them. Two shapes are worth weighing.

The zones could live with the camera an extra file or config block the camera process reads at boot and publishes. This keeps a camera's full description in one place. It also pushes zone semantics into a process whose entire design is to be dumb about meaning: the camera captures frames and forwards them, it does not interpret them. Making it the owner of zone semantics widens its responsibility for no gain, since the camera never acts on a zone it only captures the pixels a zone is drawn over.

The zones could instead live with the coordinator, which is the process that actually reasons about where a person is and what it means. A person crossing from the shelf zone toward the exit zone is a signal the coordinator cares about; the camera does not. Putting zone ownership where zone reasoning happens keeps each camera a pure capture device and gives the meaning-layer a single place to hold the map of every camera's regions.

The call: the coordinator owns the zones. It loads them from its own config store, keyed by camera id, at startup, and holds them in memory as the authority on what each region of each camera's view means. A camera stays a capture device with no opinion about meaning. When a camera is added, its zone definitions are registered with the coordinator, not bolted onto the camera process.

The zone shape itself stays minimal for now: a camera id, a zone id, a label, and a polygon or rectangle in that camera's pixel space. Enough to say "this region of this camera is the exit" and no more. Refinement — overlap semantics, real-world coordinates, camera-to-camera geometry — waits until there are real feeds to calibrate against.

## Handing off a track

This is the hard part. A person leaves one camera's view and enters another's, and the system has to recognize that the two local tracks are one person and carry forward everything already known about them.

Start from what the presence contract already gives. `PresenceEvent` carries `camera_id`, a local `track_id`, a `session_id`, a confidence, and the source frame index. The `track_id` is local to one camera — camera A's track 5 and camera B's track 5 are unrelated. The contract has no field that means "this is the same person as that other track over there," because until now there was no over there.

So the handoff needs a person identity that spans cameras — call it a global track id and a way to decide that a fresh local track on camera B is a continuation of a departed local track on camera A rather than a new person. The coordinator owns that mapping: local `(camera_id, track_id)` pairs on one side, a global track id on the other.

The matching decision is B's new track the same person as A's departed one is the part that genuinely needs real data to get right. The honest shape here is a seam the coordinator reasons over: when a track leaves camera A (a `left` edge), the coordinator holds A's global track id as a recently-departed candidate for a short window. When a fresh track appears on camera B (an `entered` edge) inside that window, the coordinator has a candidate handoff. Whether it confirms the match on timing alone, on timing plus a zone adjacency hint, or on a visual descriptor carried in the event, is left to the build, because the right threshold is empirical. What the design fixes is the shape: departed-track candidates on one side, fresh-track arrivals on the other, matched inside a time-and-geometry window by the one process that sees both cameras.

Incident state rides the global track, not the local one. When camera A's classifier flags a person, that flag attaches to the global track id in the coordinator's registry. On a confirmed handoff, the incident state is already on the global id B's local track is bound to the same global id, so B inherits the flag automatically. The person does not get re-innocented at the boundary because the suspicion was never stored on A's local track to begin with. It lived on the person.

For this to work the presence contract has to grow. Today `PresenceEvent` says "someone entered camera A as local track 5." The coordinator needs to answer back "local track 5 on camera A is global track G," and it needs a channel to push incident state onto a global track and to notify a camera's downstream that an arriving local track is already carrying a flag. That is a new contract, sketched below, layered beside the presence contract rather than crammed into it presence stays the thin per-camera signal it is, and coordination is its own vocabulary.

## Deduplicating clips across cameras

An event happens where two cameras overlap. Both see it, both may record a clip, both may raise an alert. One real event, two alerts, two clips. The store operator gets paged twice for one shoplifter.

This is the open decision. Here are the options and what each costs.

Match on the global track. If both clips are tagged with the same global track id which the handoff layer already produces two clips carrying the same global id inside a short window are candidates for the same event, and the coordinator keeps one. This reuses machinery the handoff already needs and adds nothing new to build. It leans entirely on the global track id being correct; a missed handoff means two global ids for one person means two clips slip through as distinct.

Match on time and space. Two clips whose timestamps overlap and whose cameras are known to view the same physical area are treated as one event, independent of track identity. This survives a missed handoff because it never depends on the identity match. It needs a camera adjacency map which cameras overlap which and a tolerance window, both of which need real geometry to set and are the same calibration the design is deferring elsewhere.

Match on content. Compare the clips themselves visual similarity, or a shared detected object and merge on a similarity threshold. This is the most robust against both missed handoffs and unknown geometry and by far the most expensive: it means running a comparison model over clip pairs, on the same GPU already carrying pose and classification. For a laptop-class deployment that is likely the wrong trade, but it is the option that degrades most gracefully as cameras and events scale.

No decision here. The global-track match is the cheapest and reuses the most, the time-and-space match is the most robust for the least model cost, and the content match is the most correct and the least affordable. Which one fits depends on how reliable the handoff turns out to be and what camera geometry the real deployment has, neither of which is known without hardware. The contract sketch below leaves room for all three so that picking one later does not force a redesign.

## Contract sketch

The coordination vocabulary is a new proto beside `presence.proto`, not an edit to it. Presence stays the per-camera entry/exit signal. Coordination is the cross-camera layer, and keeping them separate means a change to one does not churn the other.

The sketch below is interface-only messages and service shape, no field is load-bearing yet, no server implements it. It exists to pin the boundaries the design commits to: a global track id distinct from local track ids, incident state attached to the global track, and a handoff notification a camera's downstream can act on. Field numbers and exact types settle when the build starts against real events.

```proto
syntax = "proto3";

package theftdetection.v1;

import "google/protobuf/timestamp.proto";

message LocalTrackRef {
  string camera_id = 1;
  int32 track_id = 2;
  int64 session_id = 3;
}

message TrackBinding {
  string global_track_id = 1;
  LocalTrackRef local = 2;
  google.protobuf.Timestamp bound_at = 3;
}

enum IncidentStateKind {
  INCIDENT_STATE_KIND_UNSPECIFIED = 0;
  INCIDENT_STATE_KIND_CLEAR = 1;
  INCIDENT_STATE_KIND_FLAGGED = 2;
}

message IncidentState {
  string global_track_id = 1;
  IncidentStateKind kind = 2;
  google.protobuf.Timestamp updated_at = 3;
}

message HandoffNotice {
  string global_track_id = 1;
  LocalTrackRef arriving = 2;
  IncidentState carried_state = 3;
}

service CoordinationService {
  rpc BindTrack(LocalTrackRef) returns (TrackBinding);
  rpc PushIncidentState(IncidentState) returns (IncidentState);
  rpc StreamHandoffs(stream LocalTrackRef) returns (stream HandoffNotice);
}
```

`BindTrack` is how a local track gets its global id the coordinator either matches it to a recently-departed track and returns that global id, or mints a fresh one. `PushIncidentState` is how a flag from a classifier attaches to the person rather than to one camera's local track. `StreamHandoffs` is the channel that tells a camera's downstream an arriving local track is already carrying state, so it never treats a flagged person as a fresh face.

None of the three dedup options is encoded here, on purpose. `HandoffNotice` gives the global-track match everything it needs already. The time-and-space match would add a camera adjacency map the coordinator loads alongside its zones. The content match would add a clip-comparison call. All three fit above this contract without changing it, which is the point of leaving the decision open the sketch does not force the choice.

## What this layer depends on and what it does not

It depends on the presence contract, unchanged every gate already emits entry and exit events, and the coordinator consumes them. It depends on each camera keeping its stable id, which is already the join key across the whole system. It adds one Redis identity for the coordinator, scoped to the registry keys it owns.

It does not touch the gate, which stays identity-blind. It does not touch the camera, which stays a capture device writing only its own stream. It does not change how frames move or how presence is detected. The single-camera path is a dependency, not a thing this layer edits which is why adding coordination later, on hardware, does not mean reopening chapters 9 through 11.
