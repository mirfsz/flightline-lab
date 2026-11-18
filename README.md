# Flightline Lab

Flightline Lab is a local, consent-based research proof of concept for testing whether aircraft-like Doppler traces in a recording can support a **coarse** region. It does not return exact coordinates, addresses, people, or real aircraft identities.

The bundled fixture is entirely synthetic. Real uploads receive signal analysis but remain `inconclusive` until a properly licensed historical flight archive and a validated calibration procedure are added.

## Start locally

Requirements: Node.js, Python 3.11+, and optionally FFmpeg for compressed audio/video.

```sh
npm install
python3 -m venv .venv
.venv/bin/python -m pip install -r server/requirements-dev.txt
```

Run the API in one terminal:

```sh
.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Run the UI in another:

```sh
npm run dev
```

Open <http://127.0.0.1:5174>. The Vite proxy sends `/api` requests to the local FastAPI service.

## Verify

```sh
npm run build
.venv/bin/python -m pytest tests -q
```

See `server/README.md` for endpoint details, limits, cleanup behaviour, and model assumptions.
