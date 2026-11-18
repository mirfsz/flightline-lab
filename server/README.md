# Local offline research service

From the project root, using Python 3.11 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r server/requirements-dev.txt
.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Install `ffmpeg` separately (`brew install ffmpeg` on macOS) to accept compressed audio and video. If it is missing, mono/stereo 16-bit PCM WAV at 8–96 kHz remains supported. Numpy and SciPy are required; missing scientific packages cause a clear Python import/install error at startup. Run `.venv/bin/python -m pytest tests -q` for verification. Interactive API documentation is at http://127.0.0.1:8000/docs.

`POST /api/fixtures/analyze` synthesizes a deterministic 45-second tone passage and compares its ridge to a fixed 10 km imaginary grid. `GET /api/fixtures/demo.wav` downloads the corresponding reproducible fixture. This fixture uses no recordings of people, geographic coordinates, real flights, online APIs, or identity data.

`POST /api/analyze` accepts multipart `media`, timezone-aware ISO `recording_time`, `time_uncertainty_minutes` (0–1440), `search_region` (1–200 characters), and `consent_confirmed=true`. Use only recordings you own or have permission to process. Uploaded recordings return spectral evidence and **inconclusive**, because no real historical flight archive is installed. The provided time and region are validated metadata, not evidence of archive coverage. Even uploading the demo WAV does not enable real-world matching. Fixture matches are available only through the explicit fixture route.

The response contains `decision`, `reason_codes`, `coarse_cells` (opaque cell ID, label, and qualitative confidence), `evidence_summary`, a bounded `spectrogram.values` row matrix, and `limitations`. No geographic coordinates or flight IDs are exposed. Grid cells are always at least 10 km. Fit labels are not calibrated probabilities. The toy model assumes constant emitted tone, constant speed and altitude, stationary receiver, constant sound speed, and known fixture time origin; real-world ambiguities invalidate those assumptions.

Uploads are capped at 25 MB before multipart parsing (plus a small bounded form overhead). Each file is copied in bounded chunks into a private temporary directory using a fixed generated basename, never its submitted filename. ffmpeg runs without a shell, with one decode/encode thread, no network input protocols, a 30-second timeout, and at most 91 seconds of mono 8 kHz decoded output. The extra second lets the service reject recordings exceeding the 90-second duration limit. Requests are gated before multipart parsing and processed one at a time; concurrent analysis gets 429. Browser requests from non-local origins are rejected before decoding. WAV fallback validates rate, channels, frame count, and sample width before reading. These are practical local POC limits, not authentication or an OS sandbox: only process trusted, consented input locally, keep ffmpeg updated, and bind to loopback.

Temporary upload and decoded files are removed on success and handled failure, and multipart handles are closed. No recording, result, or metadata database exists. `DELETE /api/recordings` confirms no retained recordings; it does not cancel an in-flight request. A hard process kill or machine failure can leave an OS temporary directory, which should be removed using normal OS temporary-file maintenance. `GET /api/health` reports decoding capability and configured limits.
