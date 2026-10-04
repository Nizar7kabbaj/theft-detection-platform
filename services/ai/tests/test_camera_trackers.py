from types import SimpleNamespace

from app.camera_trackers import CameraTrackers


class FakeModel:
    def __init__(self) -> None:
        self.predictor = None
        self.seen: list[tuple[str, object, dict]] = []

    def track(self, frame, persist, **kwargs):
        assert persist is True
        if self.predictor is None:
            self.predictor = SimpleNamespace(trackers=[object()])
        self.seen.append((frame, self.predictor.trackers[0], kwargs))
        return [frame]


def fresh(predictor, persist):
    assert persist is False
    predictor.trackers = [object()]


def test_each_camera_keeps_its_own_tracker():
    model = FakeModel()
    trackers = CameraTrackers(fresh=fresh)
    for frame in ("a1", "b1", "a2", "b2", "a3"):
        trackers.track(model, frame[0], frame)
    used = {frame: tracker for frame, tracker, _ in model.seen}
    assert used["a1"] is used["a2"] is used["a3"]
    assert used["b1"] is used["b2"]
    assert used["a1"] is not used["b1"]
    assert trackers.cameras() == ["a", "b"]


def test_first_camera_keeps_the_tracker_the_model_built():
    model = FakeModel()
    trackers = CameraTrackers(fresh=fresh)
    trackers.track(model, "a", "a1")
    built = model.predictor.trackers[0]
    trackers.track(model, "b", "b1")
    trackers.track(model, "a", "a2")
    assert model.seen[2][1] is built


def test_options_reach_the_model():
    model = FakeModel()
    CameraTrackers(fresh=fresh).track(model, "a", "a1", classes=[0], conf=0.7, verbose=False)
    assert model.seen[0][2] == {"classes": [0], "conf": 0.7, "verbose": False}
