"""The virtual camera's live view is offered only when there is a video behind it.

A camera that advertises STREAM with nothing to play puts a live-view button in
the UI that fails when pressed. A cloned camera may carry its own STREAM flag
from the real one, so that flag must not decide it either: the clip does.
"""

import custom_components.virtual.camera as cam
from homeassistant.components.camera import CameraEntityFeature
from custom_components.virtual.camera import CAMERA_SCHEMA, VirtualCamera

STREAM = int(CameraEntityFeature.STREAM)


def make(**extra):
    return VirtualCamera(CAMERA_SCHEMA({"name": "Test Cam", **extra}), False)


def test_live_view_is_offered_when_the_clip_is_there():
    assert cam.VIDEO_FILE.is_file(), "the bundled clip is missing from the package"
    assert make().supported_features & STREAM


def test_live_view_is_not_offered_without_the_clip(monkeypatch, tmp_path):
    monkeypatch.setattr(cam, "VIDEO_FILE", tmp_path / "gone.mp4")
    assert not make().supported_features & STREAM


def test_a_clone_that_advertised_live_view_does_not_get_it_without_the_clip(monkeypatch, tmp_path):
    monkeypatch.setattr(cam, "VIDEO_FILE", tmp_path / "gone.mp4")
    assert not make(supported_features=STREAM).supported_features & STREAM


def test_a_clone_that_did_not_advertise_it_still_gets_it_with_the_clip():
    assert make(supported_features=0).supported_features & STREAM


ON_OFF = int(CameraEntityFeature.ON_OFF)


def features(**extra):
    return int(make(**extra).supported_features)


def test_a_clone_keeps_its_other_features_and_gains_live_view_from_the_clip():
    assert features(supported_features=ON_OFF) == ON_OFF | STREAM


def test_a_clone_that_already_had_live_view_keeps_it_and_its_other_features():
    assert features(supported_features=ON_OFF | STREAM) == ON_OFF | STREAM
    assert features(supported_features=STREAM) == STREAM


def test_without_the_clip_a_clone_keeps_only_its_other_features(monkeypatch, tmp_path):
    monkeypatch.setattr(cam, "VIDEO_FILE", tmp_path / "gone.mp4")
    assert features(supported_features=ON_OFF | STREAM) == ON_OFF


def test_a_camera_with_no_stated_features_gets_live_view_and_nothing_else():
    assert features() == STREAM


def test_the_stream_source_is_the_clip_or_nothing(monkeypatch, tmp_path):
    import asyncio
    assert asyncio.run(make().stream_source()) == str(cam.VIDEO_FILE)
    monkeypatch.setattr(cam, "VIDEO_FILE", tmp_path / "gone.mp4")
    assert asyncio.run(make().stream_source()) is None


def _top_level_boxes(data):
    """(type, start, size) for each top-level MP4 box; stops at anything malformed."""
    boxes, pos = [], 0
    while pos + 8 <= len(data):
        size = int.from_bytes(data[pos:pos + 4], "big")
        kind = data[pos + 4:pos + 8]
        if size < 8 or pos + size > len(data):
            break
        boxes.append((kind, pos, size))
        pos += size
    return boxes, pos


def test_the_clip_is_a_whole_small_h264_mp4():
    data = cam.VIDEO_FILE.read_bytes()
    boxes, end = _top_level_boxes(data)
    kinds = [k for k, _, _ in boxes]
    assert kinds[0] == b"ftyp", "not an MP4 container"
    assert end == len(data), "the file is truncated or has trailing junk"
    assert b"moov" in kinds and b"mdat" in kinds, "no movie header or no video data"
    moov = next((s, n) for k, s, n in boxes if k == b"moov")
    assert b"avc1" in data[moov[0]:moov[0] + moov[1]], "not H.264, which HA's stream expects"
    assert len(data) < 1_000_000, "it ships with every install: keep it small"
