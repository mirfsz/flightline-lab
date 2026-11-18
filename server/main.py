"""Run with: uvicorn server.main:app --host 127.0.0.1 --port 8000."""

from datetime import datetime
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import threading

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from server.matcher import analyze_features
from server.archive import analyze_public, archive_coverage, demo_metadata, public_demo_samples
from server.media import ALLOWED_SUFFIXES, MAX_DURATION_SECONDS, MAX_UPLOAD_BYTES, MediaError, decode_media
from server.schemas import AnalysisResult, HealthResult
from server.signal import extract_features, synthetic_samples, wav_bytes


class RequestSizeLimit:
    """Count bytes before multipart parsing can spool an unbounded request to disk."""

    def __init__(self, app: ASGIApp, limit: int):
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        try:
            declared_size = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared_size = self.limit + 1
        if declared_size > self.limit:
            response = JSONResponse({"detail": {"code": "UPLOAD_LIMIT", "message": "Upload limit is 25 MB."}}, status_code=413)
            return await response(scope, receive, send)
        total = 0

        async def limited_receive() -> Message:
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > self.limit:
                raise HTTPException(413, {"code": "UPLOAD_LIMIT", "message": "Upload limit is 25 MB."})
            return message

        await self.app(scope, limited_receive, send)


class LocalAnalysisGate:
    """Reject cross-site calls and serialize analysis before body parsing."""

    protected_paths = {"/api/analyze", "/api/fixtures/analyze", "/api/demo/analyze", "/api/demo/demo.wav"}

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") not in self.protected_paths:
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        origin = headers.get(b"origin", b"").decode("latin-1")
        fetch_site = headers.get(b"sec-fetch-site", b"").decode("latin-1")
        host = headers.get(b"host", b"").decode("latin-1")
        forwarded_proto = headers.get(b"x-forwarded-proto", b"http").decode("latin-1").split(",")[0].strip()
        same_origin = f"{forwarded_proto}://{host}" if host else ""
        if origin and origin not in ALLOWED_UI_ORIGINS and origin != same_origin:
            response = JSONResponse(
                {"detail": {"code": "LOCAL_ORIGIN_REQUIRED", "message": "Analysis requests must come from the local Flightline Lab UI."}},
                status_code=403,
            )
            return await response(scope, receive, send)
        if fetch_site == "cross-site":
            response = JSONResponse(
                {"detail": {"code": "CROSS_SITE_REQUEST", "message": "Cross-site analysis requests are blocked."}},
                status_code=403,
            )
            return await response(scope, receive, send)
        if not processing_slot.acquire(blocking=False):
            response = JSONResponse(
                {"detail": {"code": "PROCESSOR_BUSY", "message": "One recording is already processing. Retry when it finishes."}},
                status_code=429,
            )
            return await response(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            processing_slot.release()


ALLOWED_UI_ORIGINS = {"http://localhost:5174", "http://127.0.0.1:5174"}
ALLOWED_UI_ORIGINS.update(
    origin.strip() for origin in os.getenv("FLIGHTLINE_UI_ORIGINS", "").split(",") if origin.strip()
)
processing_slot = threading.BoundedSemaphore(1)
app = FastAPI(title="FlightlineLab offline research API", version="0.1.0")
app.add_middleware(RequestSizeLimit, limit=MAX_UPLOAD_BYTES + 128 * 1024)
app.add_middleware(CORSMiddleware, allow_origins=sorted(ALLOWED_UI_ORIGINS),
                   allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])
app.add_middleware(LocalAnalysisGate)


@app.get("/api/health", response_model=HealthResult)
def health() -> HealthResult:
    return HealthResult(status="ok", ffmpeg_available=shutil.which("ffmpeg") is not None,
                        max_upload_mb=25, max_duration_seconds=MAX_DURATION_SECONDS)


@app.post("/api/analyze", response_model=AnalysisResult)
def analyze(
    media: UploadFile = File(...),
    recording_time: str = Form(...),
    time_uncertainty_minutes: float = Form(5, ge=0, le=1440),
    search_region: str = Form("Offline research region", min_length=1, max_length=200),
    consent_confirmed: bool = Form(False),
) -> AnalysisResult:
    if not consent_confirmed:
        media.file.close()
        raise HTTPException(400, {"code": "CONSENT_REQUIRED", "message": "Confirm that you own or have permission to process the recording."})
    try:
        timestamp = datetime.fromisoformat(recording_time.replace("Z", "+00:00"))
        if timestamp.utcoffset() is None:
            raise ValueError("timezone required")
    except ValueError as exc:
        media.file.close()
        raise HTTPException(422, {"code": "INVALID_RECORDING_TIME", "message": "Use an ISO recording time including its UTC offset."}) from exc
    suffix = Path(media.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        media.file.close()
        raise HTTPException(415, {"code": "UNSUPPORTED_MEDIA", "message": "Use WAV, MP3, M4A, AAC, FLAC, OGG, MP4, MOV, or WebM."})
    try:
        with TemporaryDirectory(prefix="flightlinelab-") as temp:
            directory = Path(temp)
            source = directory / f"source{suffix}"
            total = 0
            with source.open("xb") as target:
                while chunk := media.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, {"code": "UPLOAD_LIMIT", "message": "Upload limit is 25 MB."})
                    target.write(chunk)
            if total == 0:
                raise HTTPException(400, {"code": "EMPTY_MEDIA", "message": "Choose a nonempty recording."})
            samples = decode_media(source, directory)
            return analyze_public(extract_features(samples), timestamp, time_uncertainty_minutes, search_region)
    except MediaError as exc:
        raise HTTPException(422, {"code": exc.code, "message": str(exc)}) from exc
    finally:
        media.file.close()


@app.post("/api/fixtures/analyze", response_model=AnalysisResult)
def analyze_fixture() -> AnalysisResult:
    return analyze_features(extract_features(synthetic_samples()), synthetic=True)


@app.get("/api/fixtures/demo.wav")
def fixture_wav() -> Response:
    return Response(wav_bytes(synthetic_samples()), media_type="audio/wav",
                    headers={"Content-Disposition": 'attachment; filename="flightlinelab-synthetic.wav"'})


@app.get("/api/archive/coverage")
def coverage() -> dict:
    return archive_coverage()


@app.post("/api/demo/analyze", response_model=AnalysisResult)
def analyze_demo() -> AnalysisResult:
    metadata = demo_metadata()
    timestamp = datetime.fromisoformat(metadata["recording_time"].replace("Z", "+00:00"))
    return analyze_public(extract_features(public_demo_samples()), timestamp, 0,
                          metadata["search_region"], audio_is_synthetic=True)


@app.get("/api/demo/demo.wav")
def public_demo_wav() -> Response:
    metadata = demo_metadata()
    return Response(wav_bytes(public_demo_samples()), media_type="audio/wav",
                    headers={"Content-Disposition": 'attachment; filename="flightlinelab-public-trajectory-synthetic-audio.wav"',
                             "X-Recording-Time": metadata["recording_time"],
                             "X-Search-Region": metadata["search_region"],
                             "X-Audio-Is-Synthetic": "true"})


@app.delete("/api/recordings")
def clear_recordings() -> dict[str, object]:
    # There is no retained recording store. Active requests clean their own private
    # TemporaryDirectory on success or failure; this endpoint does not disrupt them.
    return {"deleted": 0, "retained_recordings": 0,
            "message": "Recordings are deleted automatically when each request finishes."}


frontend_directory = Path(__file__).resolve().parents[1] / "dist"
if frontend_directory.is_dir():
    app.mount("/", StaticFiles(directory=frontend_directory, html=True), name="frontend")
