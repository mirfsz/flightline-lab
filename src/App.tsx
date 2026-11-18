import { ChangeEvent, DragEvent, FormEvent, ReactNode, useEffect, useRef, useState } from 'react'

type Decision = 'coarse_region_supported' | 'inconclusive' | 'no_usable_aircraft_signal' | 'insufficient_track_coverage' | 'unsupported_input'

type CoarseCell = {
  cell_id: string
  label: string
  confidence_label?: string
}

type SpectrogramData = {
  width: number
  height: number
  values: number[] | number[][]
  min_frequency_hz?: number
  max_frequency_hz?: number
}

type AnalysisResult = {
  decision: Decision
  reason_codes: string[]
  coarse_cells: CoarseCell[]
  evidence_summary: {
    duration_seconds: number
    tonal_motion_candidates: number
    audio_quality: string
    archive_coverage: string
  }
  spectrogram?: SpectrogramData
  limitations: string[]
}

const stages = ['Extract audio', 'Find tonal motion', 'Load track fixture', 'Test coarse cells', 'Check ambiguity']

function Icon({ name }: { name: 'upload' | 'shield' | 'wave' | 'clock' | 'region' | 'trash' | 'play' }) {
  const paths: Record<typeof name, ReactNode> = {
    upload: <><path d="M12 16V3m0 0L7 8m5-5 5 5"/><path d="M4 15v5h16v-5"/></>,
    shield: <path d="M12 3l7 3v5c0 4.8-2.7 8.1-7 10-4.3-1.9-7-5.2-7-10V6l7-3z"/>,
    wave: <path d="M3 12h3l2-7 4 14 3-10 2 3h4"/>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    region: <><path d="M4 6l5-2 6 2 5-2v14l-5 2-6-2-5 2V6z"/><path d="M9 4v14m6-12v14"/></>,
    trash: <><path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7"/><path d="M10 11v6m4-6v6"/></>,
    play: <path d="M8 5l11 7-11 7V5z"/>,
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>
}

function formatDuration(seconds?: number) {
  if (seconds === undefined) return '--:--'
  const whole = Math.max(0, Math.round(seconds))
  return `${String(Math.floor(whole / 60)).padStart(2, '0')}:${String(whole % 60).padStart(2, '0')}`
}

function apiErrorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== 'object' || !('detail' in payload)) return fallback
  const detail = (payload as { detail?: unknown }).detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail && typeof detail.message === 'string') return detail.message
  if (Array.isArray(detail)) {
    return detail.map((item) => item && typeof item === 'object' && 'msg' in item ? String(item.msg) : '').filter(Boolean).join(' ') || fallback
  }
  return fallback
}

function Spectrogram({ data, durationSeconds }: { data?: SpectrogramData, durationSeconds?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const ratio = window.devicePixelRatio || 1
    const rect = canvas.getBoundingClientRect()
    canvas.width = Math.max(1, Math.floor(rect.width * ratio))
    canvas.height = Math.max(1, Math.floor(rect.height * ratio))
    ctx.scale(ratio, ratio)
    ctx.fillStyle = '#102a3a'
    ctx.fillRect(0, 0, rect.width, rect.height)

    ctx.strokeStyle = 'rgba(232,238,242,.16)'
    ctx.lineWidth = 1
    for (let i = 1; i < 6; i += 1) {
      ctx.beginPath()
      ctx.moveTo((rect.width / 6) * i, 0)
      ctx.lineTo((rect.width / 6) * i, rect.height)
      ctx.stroke()
    }

    if (!data) {
      ctx.fillStyle = 'rgba(232,238,242,.55)'
      ctx.font = '13px Avenir Next, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('No signal loaded', rect.width / 2, rect.height / 2)
      return
    }

    const rows = Array.isArray(data.values[0])
      ? data.values as number[][]
      : Array.from({ length: data.height }, (_, y) =>
          (data.values as number[]).slice(y * data.width, (y + 1) * data.width),
        )
    const cellW = rect.width / data.width
    const cellH = rect.height / data.height
    rows.forEach((row, y) => row.forEach((value, x) => {
      if (value < 0.13) return
      const alpha = Math.max(0, Math.min(1, value))
      ctx.fillStyle = alpha > 0.68
        ? `rgba(255,90,54,${0.42 + alpha * 0.58})`
        : `rgba(74,152,255,${alpha * 0.72})`
      ctx.fillRect(x * cellW, rect.height - (y + 1) * cellH, cellW + 0.5, cellH + 0.5)
    }))
  }, [data])

  return (
    <div className="spectrum">
      <canvas ref={canvasRef} aria-label="Spectrogram showing detected moving tonal traces" />
      <div className="spectrum-axis spectrum-axis-y"><span>{data ? `${data.max_frequency_hz ?? 1800} Hz` : '—'}</span><span>frequency</span><span>{data ? `${data.min_frequency_hz ?? 80} Hz` : '—'}</span></div>
      <div className="spectrum-axis spectrum-axis-x"><span>{data ? '00:00' : '--:--'}</span><span>recording time</span><span>{formatDuration(durationSeconds)}</span></div>
    </div>
  )
}

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [recordingTime, setRecordingTime] = useState('')
  const [uncertainty, setUncertainty] = useState('5')
  const [region, setRegion] = useState('synthetic-evaluation-area')
  const [consent, setConsent] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [status, setStatus] = useState<'idle' | 'running' | 'complete' | 'error'>('idle')
  const [activeStage, setActiveStage] = useState(-1)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState('')

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    if (status === 'running') return
    setFile(event.target.files?.[0] ?? null)
    setResult(null)
    setError('')
  }

  function receiveDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    if (status === 'running') return
    setDragging(false)
    const dropped = event.dataTransfer.files?.[0]
    if (dropped) {
      setFile(dropped)
      setResult(null)
      setError('')
    }
  }

  async function runAnalysis(event: FormEvent) {
    event.preventDefault()
    if (!file || !consent || !recordingTime) return
    setStatus('running')
    setResult(null)
    setError('')
    setActiveStage(0)

    const form = new FormData()
    form.append('media', file)
    form.append('recording_time', new Date(recordingTime).toISOString())
    form.append('time_uncertainty_minutes', uncertainty)
    form.append('search_region', region)
    form.append('consent_confirmed', 'true')

    try {
      const response = await fetch('/api/analyze', { method: 'POST', body: form })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(apiErrorMessage(payload, 'The local analyzer could not process this file.'))
      setResult(payload as AnalysisResult)
      const archiveUnavailable = Array.isArray(payload?.reason_codes) && payload.reason_codes.includes('OFFLINE_ARCHIVE_UNAVAILABLE')
      setActiveStage(archiveUnavailable ? 2 : stages.length)
      setStatus('complete')
    } catch (requestError) {
      setStatus('error')
      setError(requestError instanceof Error ? requestError.message : 'Analysis failed.')
    }
  }

  async function runDemo() {
    setStatus('running')
    setResult(null)
    setError('')
    setActiveStage(0)
    try {
      const response = await fetch('/api/fixtures/analyze', { method: 'POST' })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(apiErrorMessage(payload, 'The synthetic fixture could not be analyzed.'))
      setResult(payload as AnalysisResult)
      setActiveStage(stages.length)
      setStatus('complete')
    } catch (requestError) {
      setStatus('error')
      setError(requestError instanceof Error ? requestError.message : 'Synthetic analysis failed.')
    }
  }

  function reset() {
    setFile(null)
    setResult(null)
    setStatus('idle')
    setActiveStage(-1)
    setError('')
  }

  const canAnalyze = Boolean(file && recordingTime && consent && status !== 'running')
  const decisionTitle = result?.decision === 'coarse_region_supported'
    ? 'Coarse region supported'
    : result?.decision === 'inconclusive'
      ? 'Evidence is inconclusive'
      : result?.decision?.replaceAll('_', ' ')

  return (
    <div className="app-shell">
      <header className="masthead">
        <a className="brand" href="#top" aria-label="Flightline Lab home">
          <span className="brand-mark"><Icon name="wave" /></span>
          <span>Flightline Lab</span>
        </a>
        <div className="privacy-note"><Icon name="shield" />Local research mode</div>
      </header>

      <main id="top">
        <section className="intro">
          <div>
            <h1>Test what aircraft sound can reveal.</h1>
            <p>Inspect a consented recording for aircraft-like tonal motion, or validate the coarse matcher with an offline synthetic fixture.</p>
          </div>
          <button className="text-button" type="button" onClick={runDemo} disabled={status === 'running'}>
            <Icon name="play" />Run the synthetic demonstration
          </button>
        </section>

        <section className="workbench" aria-label="Aircraft Doppler analysis workbench">
          <form className="control-panel" onSubmit={runAnalysis}>
            <div className="panel-heading">
              <span>Input</span>
              <span>Media stays on this machine</span>
            </div>

            <label
              className={`drop-zone ${dragging ? 'is-dragging' : ''} ${file ? 'has-file' : ''}`}
              onDragEnter={() => status !== 'running' && setDragging(true)}
              onDragLeave={() => setDragging(false)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={receiveDrop}
            >
              <input type="file" accept="audio/*,video/*" onChange={chooseFile} disabled={status === 'running'} />
              <span className="drop-icon"><Icon name="upload" /></span>
              {file ? (
                <>
                  <strong>{file.name}</strong>
                  <span>{(file.size / 1_048_576).toFixed(1)} MB · ready for local extraction</span>
                </>
              ) : (
                <>
                  <strong>Drop audio or video here</strong>
                  <span>WAV, MP3, M4A, MP4 or WebM · maximum 25 MB</span>
                </>
              )}
            </label>

            <div className="field-grid">
              <label className="field full-field">
                <span><Icon name="clock" />Approximate recording time</span>
                <input type="datetime-local" value={recordingTime} onChange={(event) => setRecordingTime(event.target.value)} disabled={status === 'running'} required />
              </label>
              <label className="field">
                <span>Uncertainty</span>
                <select value={uncertainty} onChange={(event) => setUncertainty(event.target.value)} disabled={status === 'running'}>
                  <option value="1">± 1 minute</option>
                  <option value="5">± 5 minutes</option>
                  <option value="15">± 15 minutes</option>
                  <option value="30">± 30 minutes</option>
                </select>
              </label>
              <label className="field">
                <span><Icon name="region" />Search fixture</span>
                <select value={region} onChange={(event) => setRegion(event.target.value)} disabled={status === 'running'}>
                  <option value="synthetic-evaluation-area">Synthetic evaluation area</option>
                  <option value="synthetic-coastal-area">Synthetic coastal area</option>
                  <option value="synthetic-inland-area">Synthetic inland area</option>
                </select>
              </label>
            </div>

            <p className="scope-note">Time and region define the intended future search scope. This version does not query real flight archives.</p>

            <label className="consent-row">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} disabled={status === 'running'} />
              <span>I own this recording or have permission to analyze it.</span>
            </label>

            <div className="form-actions">
              <button className="primary-button" type="submit" disabled={!canAnalyze}>
                {status === 'running' ? 'Analyzing locally…' : 'Analyze recording'}
              </button>
              {file && <button className="icon-button" type="button" onClick={reset} disabled={status === 'running'} aria-label="Remove recording"><Icon name="trash" /></button>}
            </div>
            {error && <p className="error-message" role="alert">{error} Check that the local API is running, or try the synthetic demonstration.</p>}
          </form>

          <div className="evidence-panel">
            <div className="panel-heading">
              <span>Evidence</span>
              <span>{result ? `${result.evidence_summary.tonal_motion_candidates} tonal-motion candidate${result.evidence_summary.tonal_motion_candidates === 1 ? '' : 's'}` : 'Waiting for a recording'}</span>
            </div>
            <Spectrogram data={result?.spectrogram} durationSeconds={result?.evidence_summary.duration_seconds} />

            <div className="stage-strip" aria-label="Analysis progress">
              {stages.map((stage, index) => (
                <div className={`stage ${index < activeStage ? 'is-done' : ''} ${index === activeStage ? 'is-active' : ''}`} key={stage}>
                  <span>{index < activeStage ? '✓' : index + 1}</span>
                  <p>{stage}</p>
                </div>
              ))}
            </div>

            <div className={`result-area ${result ? 'has-result' : ''}`} aria-live="polite">
              {!result ? (
                <div className="empty-result">
                  <Icon name="wave" />
                  <p>The analyzer will show detected tonal motion and only report a region when the evidence survives ambiguity checks.</p>
                </div>
              ) : (
                <>
                  <div className="result-heading">
                    <div>
                      <span className={`decision-light ${result.decision === 'coarse_region_supported' ? 'supported' : ''}`} />
                      <h2>{decisionTitle}</h2>
                    </div>
                    <span>{Math.round(result.evidence_summary.duration_seconds)} sec analyzed</span>
                  </div>

                  {result.coarse_cells.length > 0 && (
                    <div className="cell-list">
                      {result.coarse_cells.map((cell) => (
                        <div className="cell-row" key={cell.cell_id}>
                          <div className="cell-grid" aria-hidden="true">{Array.from({ length: 9 }, (_, i) => <i key={i} className={i === 4 ? 'selected' : ''} />)}</div>
                          <div><strong>{cell.label}</strong><span>Fixed 10 km research cell</span></div>
                          <em>{cell.confidence_label ?? 'Plausible'}</em>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="evidence-metrics">
                    <div><span>Audio</span><strong>{result.evidence_summary.audio_quality}</strong></div>
                    <div><span>Track fixture</span><strong>{result.evidence_summary.archive_coverage}</strong></div>
                  </div>
                  <div className="reason-list" aria-label="Decision reasons">
                    {result.reason_codes.map((code) => <span key={code}>{code.replaceAll('_', ' ').toLowerCase()}</span>)}
                  </div>
                  <ul className="limitations">
                    {result.limitations.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer>
        <p>Flightline Lab is a feasibility instrument. It does not identify people, addresses, or exact coordinates.</p>
        <span>POC 0.1 · offline fixtures</span>
      </footer>
    </div>
  )
}

export default App
