from pathlib import Path
import subprocess

import pytest

from server.media import MediaError, decode_media


def test_missing_ffmpeg_video_has_actionable_error(monkeypatch, tmp_path):
    monkeypatch.setattr("server.media.shutil.which", lambda _: None)
    with pytest.raises(MediaError) as failure:
        decode_media(tmp_path / "source.mp4", tmp_path)
    assert failure.value.code == "FFMPEG_REQUIRED"


def test_decoder_timeout_is_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr("server.media.shutil.which", lambda _: "/test/ffmpeg")

    def timed_out(command, **kwargs):
        assert kwargs["timeout"] == 30
        assert "-nostdin" in command
        assert "-protocol_whitelist" in command
        assert command[command.index("-protocol_whitelist") + 1] == "file,pipe"
        assert "-t" in command
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("server.media.subprocess.run", timed_out)
    with pytest.raises(MediaError) as failure:
        decode_media(tmp_path / "source.mp4", tmp_path)
    assert failure.value.code == "DECODE_TIMEOUT"
