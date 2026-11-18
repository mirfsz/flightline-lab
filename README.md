# Flightline Lab

Flightline Lab is a local, consent-based research proof of concept for testing whether aircraft-like Doppler traces in a recording can support a **coarse** region. It does not return exact coordinates, addresses, people, or real aircraft identities.

The bundled fixture is entirely synthetic. Real uploads receive signal analysis but remain `inconclusive` until a properly licensed historical flight archive and a validated calibration procedure are added.

## Synthetic evidence map

Choose **Run the synthetic demonstration** to inspect a responsive evidence map alongside the spectrogram. It shows a highlighted 10 km receiver cell, an invented aircraft track and closest-approach marker, and a microphone uncertainty disk enclosing the entire cell. The map uses a fictional local kilometre frame with no relationship to geographic coordinates, addresses, or real flights.

The ranked panel compares the same imaginary passage across three receiver-cell hypotheses; selecting a row updates the map and timing comparison. Tone-curve RMSE in Hz is a comparison score, not a probability. The timing comparison adds sound travel delay to passage time and compares the predicted audio arrival with a tone transition. That transition uses fitted source pitch, so it is a diagnostic of the same model, not independent confirmation. The uncertainty disk is illustrative, not a calibrated microphone location estimate.

Real uploads, including an uploaded copy of the fixture WAV, never receive map geometry or candidate identities. A future archive integration would require a regional pre-index/cache of historical data (such as adsb.lol daily archives); no archive is connected in this POC.

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
