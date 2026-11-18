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

type SyntheticEvidenceMapData = {
  coordinate_frame: 'fictional local kilometres'
  synthetic_only: true
  candidates: Candidate[]
}

type PublicEvidenceMapData = {
  coordinate_frame: 'geographic coarse cells'
  synthetic_only: false
  passage_label: string
  track_points: { latitude: number, longitude: number, observed_at: string }[]
  candidates: {
    label: string
    cell_id: string
    supported: boolean
    doppler_rmse_hz: number
    cell_bounds: { south: number, west: number, north: number, east: number }
  }[]
}

export type EvidenceMapData = SyntheticEvidenceMapData | PublicEvidenceMapData

const seconds = (value: number) => `${value.toFixed(2)} s`

function SyntheticEvidenceMap({ data }: { data: SyntheticEvidenceMapData }) {
  const [selected, setSelected] = useState(0)
  const id = useId()
  const candidate = data.candidates[selected] ?? data.candidates[0]
  if (!candidate) return null
  const isPublic = false
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
        <h3 id={`${id}-heading`}>How the possible area compares</h3>
        <span>{isPublic ? 'Public flight path · generated sound' : 'Invented scene · generated sound'}</span>
      </div>
      <p className="map-reading">The orange square is the area being compared. The blue line is the plane’s path. The dashed circle surrounds the whole square; it does not mark an exact recording spot.</p>
      <div className="map-plot">
        <svg className="map-svg" viewBox="0 0 600 400" role="img" aria-labelledby={`${id}-title ${id}-description`}>
          <title id={`${id}-title`}>Possible area {selected + 1}: {isPublic ? 'public flight path with generated sound' : 'invented flight and sound'}</title>
          <desc id={`${id}-description`}>A plane’s path, the point where it passes nearest the possible area, an orange 10 kilometre-wide square, and a dashed circle surrounding that square. {isPublic ? 'The flight positions come from public records. The sound was made for this comparison.' : 'This scene is invented and does not map to a real place.'} The circle is an illustration of the broad area being tested, not an exact location or a measured confidence range.</desc>
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
          <text className="map-event-label" x={x(event.x_km)} y={y(event.y_km) - 24} textAnchor="middle">Nearest pass</text>
          <text className="map-cell-label" x={x(cell.min_x_km) + 8} y={y(cell.min_y_km) - 9}>Area {selected + 1}</text>
          <g className="map-scale">
            <path d={`M40 366v6h${10 * scale}v-6`} />
            <text x="40" y="390">10 km</text>
          </g>
          <text className="map-frame-note" x="560" y="390" textAnchor="end">{isPublic ? 'Flight path comparison' : 'An invented scene'}</text>
        </svg>
      </div>
      <div className="map-legend" aria-label="Map legend">
        <span><i className="legend-cell" />Possible 10 km area</span>
        <span><i className="legend-track" />{isPublic ? 'Public flight path' : 'Invented flight path'}</span>
        <span><i className="legend-disk" />Whole area, not a pin</span>
      </div>

      <div className="timing-match">
        <h4>Why the sound arrives later</h4>
        <p>Sound takes time to travel. We compare when the plane passes with when you would hear it in this area.</p>
        <div className="timing-equation">
          <div><span>Plane passes</span><strong>{seconds(event.emission_seconds)}</strong></div>
          <span aria-hidden="true">+</span>
          <div><span>Sound travels</span><strong>{seconds(event.propagation_delay_seconds)}</strong></div>
          <span aria-hidden="true">=</span>
          <div><span>You would hear it</span><strong>{seconds(event.predicted_arrival_seconds)}</strong></div>
        </div>
        <p className="timing-observed">Pitch change heard: <strong>{event.observed_transition_seconds === null ? 'not clear enough' : seconds(event.observed_transition_seconds)}</strong>
          <span>Timing difference: <strong>{event.timing_residual_seconds === null ? 'unavailable' : `${event.timing_residual_seconds > 0 ? '+' : ''}${seconds(event.timing_residual_seconds)}`}</strong></span>
        </p>
        <p className="map-caveat">Times start at the beginning of the demo. The pitch change is calculated from the same sound comparison, so it is not a second, independent confirmation.</p>
      </div>

      <div className="candidate-ranking">
        <div className="ranking-heading"><h4>Compare possible areas</h4><span>Sound difference · smaller is closer</span></div>
        <ol aria-label="Possible areas, ordered by sound match">
          {data.candidates.map((item, index) => (
            <li key={item.cell_id}>
              <button type="button" aria-pressed={index === selected} onClick={() => setSelected(index)}>
                <span className="candidate-rank">{index + 1}</span>
                <span className="candidate-name"><strong>Area {index + 1}</strong><small>{item.supported ? 'Could fit this sound' : 'A weaker sound match'}</small></span>
                <span className="candidate-score">{item.doppler_rmse_hz.toFixed(2)}<small>Hz difference</small></span>
              </button>
            </li>
          ))}
        </ol>
        <p className="map-caveat">Select an area to see how it compares. A smaller number means the predicted sound is closer to the demo sound; it is not a percentage chance of being right. Even a good match covers a whole 10 km-wide area.</p>
      </div>
    </section>
  )
}

function PublicEvidenceMap({ data, audioIsSynthetic }: { data: PublicEvidenceMapData, audioIsSynthetic: boolean }) {
  const [selected, setSelected] = useState(0)
  const id = useId()
  const candidate = data.candidates[selected] ?? data.candidates[0]
  if (!candidate || !data.track_points.length) return null
  const cell = candidate.cell_bounds
  const centerLat = (cell.north + cell.south) / 2
  const kmPerLongitude = 111.32 * Math.cos(centerLat * Math.PI / 180)
  const toX = (longitude: number) => longitude * kmPerLongitude
  const toY = (latitude: number) => latitude * 111.32
  const xs = [...data.track_points.map(point => toX(point.longitude)), toX(cell.west), toX(cell.east)]
  const ys = [...data.track_points.map(point => toY(point.latitude)), toY(cell.south), toY(cell.north)]
  const minX = Math.floor((Math.min(...xs) - 5) / 10) * 10
  const maxX = Math.ceil((Math.max(...xs) + 5) / 10) * 10
  const minY = Math.floor((Math.min(...ys) - 5) / 10) * 10
  const maxY = Math.ceil((Math.max(...ys) + 5) / 10) * 10
  const scale = Math.min(520 / (maxX - minX), 290 / (maxY - minY))
  const left = (600 - (maxX - minX) * scale) / 2
  const top = (370 - (maxY - minY) * scale) / 2
  const x = (longitude: number) => left + (toX(longitude) - minX) * scale
  const y = (latitude: number) => top + (maxY - toY(latitude)) * scale
  const xLines = Array.from({ length: Math.round((maxX - minX) / 10) + 1 }, (_, index) => left + index * 10 * scale)
  const yLines = Array.from({ length: Math.round((maxY - minY) / 10) + 1 }, (_, index) => top + index * 10 * scale)
  const middle = data.track_points[Math.floor(data.track_points.length / 2)]

  return (
    <section className="evidence-map" aria-labelledby={`${id}-heading`}>
      <div className="map-heading"><h3 id={`${id}-heading`}>How the possible area compares</h3><span>Public flight path{audioIsSynthetic ? ' · generated sound' : ''}</span></div>
      <p className="map-reading">The blue line comes from recorded aircraft positions. The orange square is a possible area at least 10 km wide. {audioIsSynthetic ? 'The sound was generated for this test, so this is a demonstration of the method.' : 'The sound could fit this broad area, but it cannot identify an exact recording spot.'}</p>
      <div className="map-plot">
        <svg className="map-svg" viewBox="0 0 600 400" role="img" aria-labelledby={`${id}-title ${id}-description`}>
          <title id={`${id}-title`}>Public flight path and possible area {selected + 1}</title>
          <desc id={`${id}-description`}>A north-up geographic sketch of a publicly observed flight path in blue and a broad possible recording area in orange. Each grid square is approximately 10 kilometres wide. No exact recording spot is shown. {audioIsSynthetic ? 'The comparison uses generated sound, not a recording of this flight.' : 'The comparison uses the supplied recording; a similar sound could fit another area.'}</desc>
          <g className="map-grid">{xLines.map((value, index) => <line key={`x${index}`} x1={value} x2={value} y1={top} y2={top + (maxY - minY) * scale} />)}{yLines.map((value, index) => <line key={`y${index}`} x1={left} x2={left + (maxX - minX) * scale} y1={value} y2={value} />)}</g>
          <rect className="map-cell" x={x(cell.west)} y={y(cell.north)} width={(toX(cell.east) - toX(cell.west)) * scale} height={(toY(cell.north) - toY(cell.south)) * scale} />
          <polyline className="map-track" points={data.track_points.map(point => `${x(point.longitude)},${y(point.latitude)}`).join(' ')} />
          {data.track_points.map((point, index) => <circle className="map-track-point" key={index} cx={x(point.longitude)} cy={y(point.latitude)} r="2.7" />)}
          <path className="map-aircraft" transform={`translate(${x(middle.longitude)} ${y(middle.latitude)})`} d="M11 0 1-3-4-11-7-11-5-3-11-3-13-6-15-6-13 0-15 6-13 6-11 3-5 3-7 11-4 11 1 3Z" />
          <text className="map-cell-label" x={x(cell.west) + 8} y={y(cell.south) - 9}>Area {selected + 1}</text>
          <g className="map-scale"><path d={`M40 366v6h${10 * scale}v-6`} /><text x="40" y="390">10 km</text></g>
          <text className="map-frame-note" x="560" y="390" textAnchor="end">Geographic sketch · north up</text>
        </svg>
      </div>
      <div className="map-legend" aria-label="Map legend"><span><i className="legend-cell" />Possible broad area</span><span><i className="legend-track" />Observed flight path</span></div>
      <div className="candidate-ranking">
        <div className="ranking-heading"><h4>Compare possible areas</h4><span>Sound difference · smaller is closer</span></div>
        <ol aria-label="Possible areas, ordered by sound match">{data.candidates.map((item, index) => <li key={item.cell_id}><button type="button" aria-pressed={index === selected} onClick={() => setSelected(index)}><span className="candidate-rank">{index + 1}</span><span className="candidate-name"><strong>Area {index + 1}</strong><small>{item.supported ? 'Could fit this sound' : 'A weaker sound match'}</small></span><span className="candidate-score">{item.doppler_rmse_hz.toFixed(2)}<small>Hz difference</small></span></button></li>)}</ol>
        <p className="map-caveat">Select an area to compare it with the flight path. A smaller number means a closer sound match, not a percentage chance of being right. The whole square remains a possibility; there is no exact recording pin.</p>
      </div>
    </section>
  )
}

export default function EvidenceMap({ data, audioIsSynthetic = false }: { data: EvidenceMapData, audioIsSynthetic?: boolean }) {
  return data.synthetic_only ? <SyntheticEvidenceMap data={data} /> : <PublicEvidenceMap data={data} audioIsSynthetic={audioIsSynthetic} />
}
