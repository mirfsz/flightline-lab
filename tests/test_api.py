from io import BytesIO
import wave

from fastapi.testclient import TestClient
import numpy as np

from server.main import app
from server.media import MAX_UPLOAD_BYTES
from server.signal import SAMPLE_RATE, wav_bytes

client = TestClient(app)
FORM = {"recording_time": "2026-11-18T10:00:00+08:00", "time_uncertainty_minutes": "5",
        "search_region": "Imaginary test region", "consent_confirmed": "true"}


def test_health_and_fixture():
    assert client.get("/api/health").json()["offline"] is True
    response = client.post("/api/fixtures/analyze")
    assert response.status_code == 200
    assert response.json()["decision"] == "coarse_region_supported"
    fixture = client.get("/api/fixtures/demo.wav")
    assert fixture.status_code == 200
    with wave.open(BytesIO(fixture.content)) as reader:
        assert reader.getnframes() == SAMPLE_RATE * 45


def test_upload_requires_consent():
    form = dict(FORM, consent_confirmed="false")
    response = client.post("/api/analyze", data=form, files={"media": ("recording.wav", b"abc", "audio/wav")})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "CONSENT_REQUIRED"


def test_silent_wav_upload_without_ffmpeg_and_cleanup(monkeypatch, tmp_path):
    import server.media as media_module
    import server.main as main_module
    from tempfile import TemporaryDirectory
    monkeypatch.setattr(media_module.shutil, "which", lambda _: None)
    monkeypatch.setattr(main_module, "TemporaryDirectory", lambda **kwargs: TemporaryDirectory(dir=tmp_path, **kwargs))
    response = client.post("/api/analyze", data=FORM,
                           files={"media": ("../../recording.wav", wav_bytes(np.zeros(20 * SAMPLE_RATE)), "audio/wav")})
    assert response.status_code == 200
    assert response.json()["decision"] == "inconclusive"
    assert "SILENCE_OR_NEAR_SILENCE" in response.json()["reason_codes"]
    assert list(tmp_path.iterdir()) == []


def test_invalid_recording_time_and_media():
    response = client.post("/api/analyze", data=dict(FORM, recording_time="2026-11-18T10:00"),
                           files={"media": ("recording.wav", b"bad", "audio/wav")})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_RECORDING_TIME"
    response = client.post("/api/analyze", data=FORM, files={"media": ("recording.exe", b"bad", "audio/wav")})
    assert response.status_code == 415


def test_duration_limit_without_ffmpeg(monkeypatch):
    import server.media as media_module
    monkeypatch.setattr(media_module.shutil, "which", lambda _: None)
    response = client.post("/api/analyze", data=FORM,
                           files={"media": ("recording.wav", wav_bytes(np.zeros(91 * SAMPLE_RATE)), "audio/wav")})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "DURATION_LIMIT"


def test_request_size_is_rejected_before_parsing():
    response = client.post("/api/analyze", content=b"small", headers={"Content-Length": str(MAX_UPLOAD_BYTES * 2)})
    assert response.status_code == 413


def test_cross_site_analysis_is_rejected_before_processing():
    response = client.post(
        "/api/analyze",
        headers={"Origin": "https://attacker.example", "Sec-Fetch-Site": "cross-site"},
        data=FORM,
        files={"media": ("recording.wav", b"bad", "audio/wav")},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "LOCAL_ORIGIN_REQUIRED"


def test_delete_endpoint_reports_no_retained_recordings():
    assert client.delete("/api/recordings").json()["retained_recordings"] == 0


def test_invalid_media_is_cleaned_up(monkeypatch, tmp_path):
    import server.media as media_module
    import server.main as main_module
    from tempfile import TemporaryDirectory
    monkeypatch.setattr(media_module.shutil, "which", lambda _: None)
    monkeypatch.setattr(main_module, "TemporaryDirectory", lambda **kwargs: TemporaryDirectory(dir=tmp_path, **kwargs))
    response = client.post("/api/analyze", data=FORM,
                           files={"media": ("recording.wav", b"not a real wave", "audio/wav")})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_MEDIA"
    assert list(tmp_path.iterdir()) == []
