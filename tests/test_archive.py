from datetime import datetime
from io import BytesIO
import json
import math
import wave

from fastapi.testclient import TestClient
import numpy as np
import pytest
from pydantic import ValidationError

from server.archive import (PACK_DIRECTORY, archive_coverage, demo_pack, installed_packs,
                            load_pack, public_demo_samples, received_ratios, select_pack)
from server.main import app, processing_slot
from server.signal import SAMPLE_RATE

client = TestClient(app)


def demo_form():
    demo = archive_coverage()["demo"]
    return {"recording_time": demo["recording_time"], "search_region": demo["search_region"],
            "time_uncertainty_minutes": str(demo["time_uncertainty_minutes"]), "consent_confirmed": "true"}


def upload(wav, **changes):
    return client.post("/api/analyze", data=dict(demo_form(), **changes),
                       files={"media": ("demo.wav", wav, "audio/wav")})


def test_coverage_exposes_honest_bounded_licensed_span():
    response = client.get("/api/archive/coverage")
    assert response.status_code == 200
    coverage = response.json()
    assert coverage["offline"] is True
    pack = coverage["packs"][0]
    assert pack["region_id"] == "singapore"
    assert pack["date_utc"] == "2026-11-18"
    assert pack["observation_count"] == 3
    assert pack["observation_span_seconds"] == 24.007
    assert pack["complete_regional_coverage"] is False
    assert pack["provenance"]["license"] == "ODbL-1.0"
    assert "adsb.lol" in pack["provenance"]["attribution"]
    assert len(pack["content_sha256"]) == 64
    demo = coverage["demo"]
    assert demo["recording_time"] == "2026-11-18T15:00:20.001Z"
    assert demo["audio_is_synthetic"] is True
    assert demo["time_uncertainty_minutes"] == 0


def test_pack_loader_is_immutable_and_rejects_extra_identity_fields(tmp_path):
    pack = demo_pack()
    assert isinstance(installed_packs(), tuple)
    assert isinstance(pack.observations, tuple)
    with pytest.raises(ValidationError):
        pack.region_id = "changed"
    payload = pack.model_dump(mode="json")
    payload["observations"][0]["callsign"] = "not permitted"
    path = tmp_path / "invalid.json"
    # pytest writes a temporary malformed pack, never an installed archive.
    path.write_text(json.dumps(payload))
    with pytest.raises(ValidationError):
        load_pack(path)
    payload["observations"][0].pop("callsign")
    payload["observations"].reverse()
    path.write_text(json.dumps(payload))
    with pytest.raises(ValidationError):
        load_pack(path)


def test_demo_uses_public_observations_and_exposes_only_coarse_receiver_cells():
    response = client.post("/api/demo/analyze")
    assert response.status_code == 200
    result = response.json()
    assert result["decision"] == "coarse_region_supported"
    assert result["evidence_kind"] == "public_observation"
    assert result["synthetic_only"] is False
    assert result["audio_is_synthetic"] is True
    assert result["archive_match"]["status"] == "installed_overlap"
    assert result["grid_resolution_km"] >= 10
    evidence = result["evidence_map"]
    assert evidence["coordinate_frame"] == "geographic coarse cells"
    assert evidence["synthetic_only"] is False
    assert evidence["passage_label"] == "Anonymous passage A"
    assert len(evidence["track_points"]) == 3
    for candidate in evidence["candidates"]:
        assert candidate["label"] == "Anonymous passage A"
        bounds = candidate["cell_bounds"]
        assert (bounds["north"] - bounds["south"]) * 111.195 >= 10
        assert (bounds["east"] - bounds["west"]) * 111.195 * math.cos(math.radians(bounds["north"])) >= 10
        assert set(candidate) == {"label", "cell_id", "supported", "doppler_rmse_hz", "cell_bounds"}
    assert all(cell["confidence_label"] == "compatible coarse cell" for cell in result["coarse_cells"])
    serialized = json.dumps(result).lower()
    for private_key in ("callsign", '"hex"', "icao", "receiver_lat", "receiver_lon", "microphone_area_center", "closest_approach"):
        assert private_key not in serialized
    assert any("not a calibrated probability" in line for line in result["limitations"])


def test_downloaded_public_demo_reaches_public_pack_via_normal_upload(monkeypatch, tmp_path):
    import server.media as media_module
    import server.main as main_module
    from tempfile import TemporaryDirectory
    monkeypatch.setattr(media_module.shutil, "which", lambda _: None)
    monkeypatch.setattr(main_module, "TemporaryDirectory", lambda **kwargs: TemporaryDirectory(dir=tmp_path, **kwargs))
    wav = client.get("/api/demo/demo.wav")
    assert wav.headers["x-audio-is-synthetic"] == "true"
    assert wav.headers["x-recording-time"] == demo_form()["recording_time"]
    assert wav.headers["x-search-region"] == "Singapore"
    with wave.open(BytesIO(wav.content)) as reader:
        assert reader.getnframes() == SAMPLE_RATE * 20
    result = upload(wav.content).json()
    assert result["decision"] == "coarse_region_supported"
    assert result["evidence_kind"] == "public_observation"
    # Uploaded bytes alone cannot establish whether audio is synthetic.
    assert result["audio_is_synthetic"] is None
    assert result["archive_match"]["pack_id"] == demo_pack().pack_id
    assert result["evidence_map"]["coordinate_frame"] == "geographic coarse cells"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("changes,status", [
    ({"recording_time": "2026-11-17T15:00:20.001Z"}, "time_unavailable"),
    ({"search_region": "Tokyo"}, "region_unavailable"),
])
def test_unsupported_date_or_region_is_structured_coverage_result(changes, status):
    wav = client.get("/api/demo/demo.wav").content
    response = upload(wav, **changes)
    assert response.status_code == 200
    result = response.json()
    assert result["decision"] == "inconclusive"
    assert result["evidence_kind"] == "no_archive"
    assert result["archive_match"]["status"] == status
    assert result["evidence_map"] is None
    assert result["coarse_cells"] == []


def test_synthetic_fixture_is_separate_even_when_uploaded_with_public_metadata():
    fixture = client.post("/api/fixtures/analyze").json()
    assert fixture["evidence_kind"] == "synthetic_fixture"
    assert fixture["evidence_map"]["synthetic_only"] is True
    wav = client.get("/api/fixtures/demo.wav").content
    result = upload(wav).json()
    assert result["decision"] == "inconclusive"
    assert result["coarse_cells"] == []
    assert result["evidence_map"] is None
    assert result["synthetic_only"] is False


def test_public_demo_is_deterministic_and_does_not_extrapolate():
    np.testing.assert_array_equal(public_demo_samples(), public_demo_samples())
    _, valid = received_ratios(demo_pack(), 1.25, 103.95, np.array([-1., 10., 30., 1000.]))
    assert valid.tolist() == [False, True, True, False]
    # Timestamp aliases resolve to the same absolute public observation window.
    pack, coverage = select_pack(datetime.fromisoformat("2026-11-18T23:00:20.001+08:00"), 20, 0, " SG ")
    assert pack == demo_pack()
    assert coverage.status == "installed_overlap"


@pytest.mark.parametrize("path,method", [("/api/demo/analyze", "post"), ("/api/demo/demo.wav", "get")])
def test_public_demo_is_covered_by_origin_and_processing_gate(path, method):
    response = getattr(client, method)(path, headers={"Origin": "https://attacker.example"})
    assert response.status_code == 403
    assert processing_slot.acquire(blocking=False)
    try:
        response = getattr(client, method)(path)
        assert response.status_code == 429
    finally:
        processing_slot.release()


def test_installed_pack_contains_no_aircraft_identifiers():
    for path in PACK_DIRECTORY.glob("*.json"):
        payload = json.loads(path.read_text())
        assert set(payload["observations"][0]) == {
            "captured_ms", "latitude", "longitude", "alt_geom_ft", "gs_knots", "track_deg"}
        assert "/hex/" not in payload["provenance"]["source_url"]
