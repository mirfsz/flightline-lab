import { ChangeEvent, DragEvent, FormEvent, ReactNode, useEffect, useRef, useState } from 'react'
import EvidenceMap, { EvidenceMapData } from './EvidenceMap'

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
  evidence_kind?: 'synthetic_fixture' | 'public_observation' | 'no_archive'
  audio_is_synthetic?: boolean
  archive_match?: { status: string, message: string, attribution?: string | null }
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
  evidence_map?: EvidenceMapData | null
}

const stages = ['Read recording', 'Find pitch changes', 'Check flight records', 'Compare areas', 'Check other explanations']

const reasonLabels: Record<string, string> = {
  SILENCE_OR_NEAR_SILENCE: 'The recording is too quiet',
  LOW_RIDGE_SIGNAL_TO_NOISE: 'Background noise hides the sound',
  INSUFFICIENT_DURATION: 'A longer recording is needed',
  OFFLINE_ARCHIVE_UNAVAILABLE: 'No flight records for this search',
  INSUFFICIENT_DOPPLER_VARIATION: 'Too little change in pitch',
  NO_COHERENT_SYNTHETIC_FIT: 'No demo area matches the sound',
  AMBIGUOUS_GRID_FIT: 'Several areas sound equally likely',
  SYNTHETIC_FIXTURE_ONLY: 'Uses an invented flight and generated sound',
  COARSE_GRID_FIT: 'A broad area matches the sound',
  ARCHIVE_REGION_UNAVAILABLE: 'No flight records for this area',
  ARCHIVE_TIME_UNAVAILABLE: 'No flight records for this date and time',
  NO_COMPATIBLE_PUBLIC_CELL: 'No area matches this sound clearly enough',
  PUBLIC_OBSERVATION_PACK: 'Compared with public flight positions',
  COARSE_CELL_COMPATIBILITY_ONLY: 'A broad area could fit the sound',
  SHORT_OBSERVATION_SPAN: 'Only a short part of one flight is available',
}

const audioLabels: Record<string, string> = { usable: 'Clear enough to compare', weak: 'Hard to hear above the noise', silent: 'Too quiet to compare' }

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
      ctx.fillText('Your sound will appear here', rect.width / 2, rect.height / 2)
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
      <canvas ref={canvasRef} role="img" aria-label={data ? 'Sound chart: bright lines show how pitch changes during the recording' : 'Sound chart waiting for a recording'} />
      <div className="spectrum-axis spectrum-axis-y"><span>{data ? `${data.max_frequency_hz ?? 1800} Hz` : '—'}</span><span>sound pitch</span><span>{data ? `${data.min_frequency_hz ?? 80} Hz` : '—'}</span></div>
      <div className="spectrum-axis spectrum-axis-x"><span>{data ? '00:00' : '--:--'}</span><span>recording time</span><span>{formatDuration(durationSeconds)}</span></div>
    </div>
  )
}

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [recordingTime, setRecordingTime] = useState('')
  const [uncertainty, setUncertainty] = useState('5')
  const [region, setRegion] = useState('')
  const [consent, setConsent] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [status, setStatus] = useState<'idle' | 'running' | 'complete' | 'error'>('idle')
  const [activeStage, setActiveStage] = useState(-1)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

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
    if (!file || !consent || !recordingTime || !region.trim()) return
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
      if (!response.ok) throw new Error(apiErrorMessage(payload, 'This recording could not be checked. Try a shorter audio or video file.'))
      setResult(payload as AnalysisResult)
      const archiveUnavailable = Array.isArray(payload?.reason_codes) && payload.reason_codes.includes('OFFLINE_ARCHIVE_UNAVAILABLE')
      setActiveStage(archiveUnavailable ? 2 : stages.length)
      setStatus('complete')
    } catch (requestError) {
      setStatus('error')
      setError(requestError instanceof Error ? requestError.message : 'Analysis failed.')
    }
  }

  async function runDemo(kind: 'public' | 'simple') {
    setStatus('running')
    setResult(null)
    setError('')
    setActiveStage(0)
    try {
      const response = await fetch(kind === 'public' ? '/api/demo/analyze' : '/api/fixtures/analyze', { method: 'POST' })
      const payload = await response.json().catch(() => null)
      if (!response.ok) throw new Error(apiErrorMessage(payload, 'The demo could not be loaded. Please try again.'))
      setResult(payload as AnalysisResult)
      setActiveStage(stages.length)
      setStatus('complete')
    } catch (requestError) {
      setStatus('error')
      setError(requestError instanceof Error ? requestError.message : 'The demo could not be loaded.')
    }
  }

  function reset() {
    setFile(null)
    setResult(null)
    setStatus('idle')
    setActiveStage(-1)
    setError('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const canAnalyze = Boolean(file && recordingTime && region.trim() && consent && status !== 'running')
  const isDemo = result?.evidence_kind === 'synthetic_fixture' || result?.audio_is_synthetic || Boolean(result?.evidence_map?.synthetic_only)
  const isPublic = result?.evidence_kind === 'public_observation'
  const isPublicDemo = isPublic && isDemo
  const coverageLabel = result?.archive_match?.status === 'region_unavailable' ? 'None available for this area'
    : result?.archive_match?.status === 'time_unavailable' ? 'None available for this date and time'
      : isPublic ? 'A short part of one public flight path'
        : isDemo ? 'Invented flight for this demo' : 'None available for this search'
  const decisionTitles: Record<Decision, string> = {
    coarse_region_supported: isDemo ? 'A possible area in this demo' : 'A possible recording area',
    inconclusive: 'There isn’t enough evidence yet',
    no_usable_aircraft_signal: 'No clear aircraft sound found',
    insufficient_track_coverage: 'Not enough flight records',
    unsupported_input: 'This recording can’t be checked',
  }
  const decisionTitle = result ? decisionTitles[result.decision] : ''

  return (
    <div className="app-shell">
      <header className="masthead">
        <a className="brand" href="#top" aria-label="Flightline Lab home">
          <span className="brand-mark"><Icon name="wave" /></span>
          <span>Flightline Lab</span>
        </a>
        <div className="privacy-note"><Icon name="shield" />A sound & flight experiment</div>
      </header>

      <main id="top">
        <section className="intro">
          <div>
            <h1>Could a passing plane help place a recording?</h1>
            <p>Start with a recording, a rough time, and a general area. Flightline Lab compares changes in aircraft sound with flight paths to explore where it could have been recorded.</p>
          </div>
        </section>

        <details className="demo-guide" open>
          <summary>See how it works</summary>
          <div className="demo-content">
            <div><h2>A flight path, a changing sound, a possible area.</h2><p>Explore a real public flight path with computer-generated sound. Then see why the result stays broad. The sound is made for this test; it is not a recording of that flight.</p></div>
            <div className="demo-actions">
              <button className="demo-button" type="button" onClick={() => runDemo('public')} disabled={status === 'running'}><Icon name="play" />Try the public flight-data demo</button>
              <button className="text-button" type="button" onClick={() => runDemo('simple')} disabled={status === 'running'}>Try the simple sound demo</button>
              <span>The simple demo uses an invented flight.</span>
            </div>
          </div>
        </details>

        <section className="workbench" aria-label="Find a possible recording area">
          <form className="control-panel" onSubmit={runAnalysis}>
            <div className="panel-heading">
              <span>Your recording</span>
              <span>Deleted after each check</span>
            </div>

            <h2 className="step-heading"><span>1</span>Upload a recording</h2>

            <label
              className={`drop-zone ${dragging ? 'is-dragging' : ''} ${file ? 'has-file' : ''}`}
              onDragEnter={() => status !== 'running' && setDragging(true)}
              onDragLeave={() => setDragging(false)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={receiveDrop}
            >
              <input ref={fileInputRef} type="file" accept="audio/*,video/*" onChange={chooseFile} disabled={status === 'running'} aria-label="Choose an audio or video recording" />
              <span className="drop-icon"><Icon name="upload" /></span>
              {file ? (
                <>
                  <strong>{file.name}</strong>
                  <span>{(file.size / 1_048_576).toFixed(1)} MB · select to change recording</span>
                </>
              ) : (
                <>
                  <strong>Choose a file or drop it here</strong>
                  <span>Audio or video · up to 25 MB</span>
                </>
              )}
            </label>

            <h2 className="step-heading"><span>2</span>When and roughly where?</h2>
            <div className="field-grid">
              <label className="field full-field">
                <span><Icon name="clock" />Recording date and time</span>
                <input type="datetime-local" value={recordingTime} onChange={(event) => setRecordingTime(event.target.value)} disabled={status === 'running'} required />
                <small>Use the time in your device’s time zone.</small>
              </label>
              <label className="field">
                <span>How close is that time?</span>
                <select value={uncertainty} onChange={(event) => setUncertainty(event.target.value)} disabled={status === 'running'}>
                  <option value="1">± 1 minute</option>
                  <option value="5">± 5 minutes</option>
                  <option value="15">± 15 minutes</option>
                  <option value="30">± 30 minutes</option>
                </select>
              </label>
              <label className="field full-field">
                <span><Icon name="region" />General area</span>
                <input type="text" value={region} onChange={(event) => setRegion(event.target.value)} disabled={status === 'running'} placeholder="City or region, e.g. Singapore" maxLength={200} required />
                <small>A broad area is enough. No address needed.</small>
              </label>
            </div>

            <p className="scope-note">This prototype can only compare areas when matching flight records are available. Your recording may return no location. Try a demo to explore a complete comparison.</p>

            <h2 className="step-heading"><span>3</span>Confirm permission</h2>
            <label className="consent-row">
              <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} disabled={status === 'running'} />
              <span>I own this recording or have permission to analyze it.</span>
            </label>

            <div className="form-actions">
              <button className="primary-button" type="submit" disabled={!canAnalyze}>
                {status === 'running' ? 'Checking the sound…' : 'Find possible area'}
              </button>
              {file && <button className="icon-button" type="button" onClick={reset} disabled={status === 'running'} aria-label="Remove recording"><Icon name="trash" /></button>}
            </div>
            {!canAnalyze && status !== 'running' && <p className="form-hint">Add a recording, time, and general area, then confirm permission to continue.</p>}
            {error && <p className="error-message" role="alert">{error}</p>}
          </form>

          <div className="evidence-panel">
            <div className="panel-heading">
              <span>What the sound reveals</span>
              <span>{result ? `${result.evidence_summary.tonal_motion_candidates} possible aircraft sound${result.evidence_summary.tonal_motion_candidates === 1 ? '' : 's'}` : 'Waiting for a recording'}</span>
            </div>
            <p className="chart-guide">Bright lines show changes in pitch. A plane’s sound can rise as it approaches and fall as it moves away.</p>
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
                  <p>{status === 'running' ? 'Reading the sound and checking possible explanations. This can take a moment.' : 'Your result will appear here. A match suggests a broad area, never an exact recording spot. Start with your recording or open “See how it works” to try a demo.'}</p>
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

                  <p className="result-explanation">{isDemo ? (isPublicDemo ? 'Demo result: public aircraft positions are compared with generated sound. This shows the method working under controlled conditions, not a location found from a real recording.' : 'Demo result: both the flight and sound were made for this test. The highlighted area shows a possible match in an invented scene.') : result.decision === 'coarse_region_supported' ? 'The sound is consistent with this broad area. Other flight paths, background noise, and timing errors can produce a similar result.' : 'The sound alone cannot place this recording. A clear aircraft sound and matching flight records are both needed.'}</p>

                  {result.coarse_cells.length > 0 && (
                    <div className="cell-list">
                      {result.coarse_cells.map((cell) => (
                        <div className="cell-row" key={cell.cell_id}>
                          <div className="cell-grid" aria-hidden="true">{Array.from({ length: 9 }, (_, i) => <i key={i} className={i === 4 ? 'selected' : ''} />)}</div>
                          <div><strong>{cell.label.replace('Synthetic cell ', 'Demo area ').replace(' · 10 km grid', '').replace(' cell ', ' area ').replace(' · ≥10 km', '')}</strong><span>At least 10 km wide, not an exact spot</span></div>
                          <em>{cell.confidence_label?.includes('ambiguous') ? 'Other areas also fit' : 'Possible match'}</em>
                        </div>
                      ))}
                    </div>
                  )}

                  {result.decision === 'coarse_region_supported' && result.evidence_map && (
                    <EvidenceMap data={result.evidence_map} audioIsSynthetic={Boolean(result.audio_is_synthetic || result.evidence_map.synthetic_only)} />
                  )}

                  <div className="evidence-metrics">
                    <div><span>Sound quality</span><strong>{audioLabels[result.evidence_summary.audio_quality] ?? result.evidence_summary.audio_quality}</strong></div>
                    <div><span>Flight records</span><strong>{coverageLabel}</strong></div>
                  </div>
                  <div className="reason-list" aria-label="Decision reasons">
                    {result.reason_codes.filter(code => reasonLabels[code]).map((code) => <span key={code}>{reasonLabels[code]}</span>)}
                  </div>
                  <details className="limits-details"><summary>Why the result stays broad</summary><ul className="limitations">{isPublic && <li>Only a short stretch of public aircraft positions is available. Other planes and times are not covered.</li>}<li>A similar change in sound can fit more than one area.</li><li>Wind, echoes, changing engine noise, and an uncertain time can change the match.</li><li>These comparisons are not a percentage chance of being right.</li><li>No exact recording spot or person is identified.</li></ul>{result.archive_match?.attribution && <p className="source-note">Flight data: {result.archive_match.attribution}</p>}</details>
                </>
              )}
            </div>
          </div>
        </section>
      </main>

      <footer>
        <p>A research prototype exploring sound and flight paths. Results suggest broad areas, not addresses or people.</p>
        <span>Flightline Lab · experiment 0.1</span>
      </footer>
    </div>
  )
}

export default App
