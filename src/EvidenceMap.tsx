import { useId, useState } from 'react'

type Point = { x_km: number, y_km: number }
type Candidate = {
  label: string
  cell_id: string
  supported: boolean
  doppler_rmse_hz: number
  cell_bounds: { min_x_km: number, min_y_km: number, max_x_km: number, max_y_km: number }
  microphone_area_center: Point
  microphone_uncertainty_radius_km: number
  track_points: (Point & { emission_seconds: number })[]
  closest_approach: Point & {
    emission_seconds: number
    predicted_arrival_seconds: number
    observed_transition_seconds: number | null
    timing_residual_seconds: number | null
    propagation_delay_seconds: number
  }
}

export type EvidenceMapData = {
  coordinate_frame: 'fictional local kilometres'
  synthetic_only: true
  candidates: Candidate[]
}

const seconds = (value: number) => `${value.toFixed(2)} s`

export default function EvidenceMap({ data }: { data: EvidenceMapData }) {
  const [selected, setSelected] = useState(0)
  const id = useId()
  const candidate = data.candidates[selected] ?? data.candidates[0]
  if (!candidate || !data.synthetic_only) return null
  const { cell_bounds: cell, microphone_area_center: mic, closest_approach: event } = candidate
  const radius = candidate.microphone_uncertainty_radius_km
  const xs = [...candidate.track_points.map(point => point.x_km), mic.x_km - radius, mic.x_km + radius]
  const ys = [...candidate.track_points.map(point => point.y_km), mic.y_km - radius, mic.y_km + radius]
  const minX = Math.floor((Math.min(...xs) - 3) / 10) * 10
  const maxX = Math.ceil((Math.max(...xs) + 3) / 10) * 10
  const minY = Math.floor((Math.min(...ys) - 3) / 10) * 10
  const maxY = Math.ceil((Math.max(...ys) + 3) / 10) * 10
  const scale = Math.min(520 / (maxX - minX), 290 / (maxY - minY))
  const left = (600 - (maxX - minX) * scale) / 2
  const top = (370 - (maxY - minY) * scale) / 2
  const x = (value: number) => left + (value - minX) * scale
  const y = (value: number) => top + (maxY - value) * scale
  const xLines = Array.from({ length: Math.round((maxX - minX) / 10) + 1 }, (_, index) => minX + index * 10)
  const yLines = Array.from({ length: Math.round((maxY - minY) / 10) + 1 }, (_, index) => minY + index * 10)

  return (
    <section className="evidence-map" aria-labelledby={`${id}-heading`}>
      <div className="map-heading">
        <h3 id={`${id}-heading`}>Evidence map</h3>
        <span>Fictional scene · 10 km grid</span>
      </div>
      <div className="map-plot">
        <svg className="map-svg" viewBox="0 0 600 400" role="img" aria-labelledby={`${id}-title ${id}-description`}>
          <title id={`${id}-title`}>{candidate.label}: synthetic evidence map</title>
          <desc id={`${id}-description`}>An invented aircraft passage, its closest approach, a highlighted 10 kilometre receiver cell, and a disk enclosing the entire cell. These local kilometre coordinates have no geographic reference. The disk is illustrative uncertainty, not a calibrated location estimate.</desc>
          <g className="map-grid">
            {xLines.map(value => <line key={`x${value}`} x1={x(value)} x2={x(value)} y1={y(minY)} y2={y(maxY)} />)}
            {yLines.map(value => <line key={`y${value}`} x1={x(minX)} x2={x(maxX)} y1={y(value)} y2={y(value)} />)}
          </g>
          <rect className="map-cell" x={x(cell.min_x_km)} y={y(cell.max_y_km)} width={(cell.max_x_km - cell.min_x_km) * scale} height={(cell.max_y_km - cell.min_y_km) * scale} />
          <circle className="map-uncertainty" cx={x(mic.x_km)} cy={y(mic.y_km)} r={radius * scale} />
          <polyline className="map-track" points={candidate.track_points.map(point => `${x(point.x_km)},${y(point.y_km)}`).join(' ')} />
          {candidate.track_points.map((point, index) => <circle className="map-track-point" key={index} cx={x(point.x_km)} cy={y(point.y_km)} r="3" />)}
          <circle className="map-event-ring" cx={x(event.x_km)} cy={y(event.y_km)} r="15" />
          <path className="map-aircraft" transform={`translate(${x(event.x_km)} ${y(event.y_km)})`} d="M11 0 1-3-4-11-7-11-5-3-11-3-13-6-15-6-13 0-15 6-13 6-11 3-5 3-7 11-4 11 1 3Z" />
          <text className="map-event-label" x={x(event.x_km)} y={y(event.y_km) - 24} textAnchor="middle">Closest approach</text>
          <text className="map-cell-label" x={x(cell.min_x_km) + 8} y={y(cell.min_y_km) - 9}>{candidate.cell_id}</text>
          <g className="map-scale">
            <path d={`M40 366v6h${10 * scale}v-6`} />
            <text x="40" y="390">10 km · local frame</text>
          </g>
          <text className="map-frame-note" x="560" y="390" textAnchor="end">No real geography</text>
        </svg>
      </div>
      <div className="map-legend" aria-label="Map legend">
        <span><i className="legend-cell" />10 km cell</span>
        <span><i className="legend-track" />Synthetic track</span>
        <span><i className="legend-disk" />Microphone uncertainty area</span>
      </div>

      <div className="timing-match">
        <h4>Timing comparison</h4>
        <p>Closest-approach sound is heard after it travels to the receiver cell.</p>
        <div className="timing-equation">
          <div><span>Passage time</span><strong>{seconds(event.emission_seconds)}</strong></div>
          <span aria-hidden="true">+</span>
          <div><span>Sound travel</span><strong>{seconds(event.propagation_delay_seconds)}</strong></div>
          <span aria-hidden="true">=</span>
          <div><span>Predicted in audio</span><strong>{seconds(event.predicted_arrival_seconds)}</strong></div>
        </div>
        <p className="timing-observed">Tone transition: <strong>{event.observed_transition_seconds === null ? 'not resolved' : seconds(event.observed_transition_seconds)}</strong>
          <span>Residual: <strong>{event.timing_residual_seconds === null ? 'unavailable' : `${event.timing_residual_seconds > 0 ? '+' : ''}${seconds(event.timing_residual_seconds)}`}</strong></span>
        </p>
        <p className="map-caveat">Seconds are relative to the fixture start. The transition uses the fitted source pitch; it is a diagnostic of the same fit, not independent confirmation.</p>
      </div>

      <div className="candidate-ranking">
        <div className="ranking-heading"><h4>Ranked cell hypotheses</h4><span>Tone error · lower is better</span></div>
        <ol aria-label="Ranked synthetic candidates">
          {data.candidates.map((item, index) => (
            <li key={item.cell_id}>
              <button type="button" aria-pressed={index === selected} onClick={() => setSelected(index)}>
                <span className="candidate-rank">{index + 1}</span>
                <span className="candidate-name"><strong>{item.label}</strong><small>{item.supported ? 'Within synthetic fit gate' : 'Outside synthetic fit gate'}</small></span>
                <span className="candidate-score">{item.doppler_rmse_hz.toFixed(2)}<small>Hz RMSE</small></span>
              </button>
            </li>
          ))}
        </ol>
        <p className="map-caveat">One invented passage, tested across coarse receiver cells. Errors are comparison scores, not probabilities. The disk encloses the whole cell and does not locate a microphone within it.</p>
      </div>
    </section>
  )
}
