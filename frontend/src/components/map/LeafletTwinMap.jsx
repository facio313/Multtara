import React from 'react'
import { Link } from 'react-router-dom'
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { scoreTone } from '../../utils/scoreColor'
import { spotTypeLabel } from '../../utils/spotType'
import { formatMinutes, tempColor } from '../../utils/twin'

function scoreIcon(score) {
  return L.divIcon({
    className: 'score-marker',
    html: `<div class="score-marker-inner is-${scoreTone(score)}">${score ?? '-'}</div>`,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
  })
}

function tempIcon(temp) {
  const label = temp == null || Number.isNaN(Number(temp)) ? '-' : Math.round(Number(temp))
  return L.divIcon({
    className: 'score-marker',
    html: `<div class="temp-marker-inner" style="background:${tempColor(temp)}">${label}</div>`,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
  })
}

const LeafletTwinMap = ({ spots, layer }) => (
  <MapContainer center={[36.5, 127.8]} zoom={7} style={{ height: '100%', width: '100%' }}>
    <TileLayer
      attribution="&copy; OpenStreetMap &copy; CARTO"
      url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
    />
    {spots.map((spot) => (
      <Marker
        key={`${spot.id}-${layer}`}
        position={[spot.lat, spot.lng]}
        icon={
          layer === 'temp'
            ? tempIcon(spot.condition?.water_temp)
            : scoreIcon(spot.water_index)
        }
      >
        <Popup>
          <div className="map-popup">
            <strong>{spot.name}</strong>
            <p>
              {spot.region} · {spotTypeLabel(spot.type)}
              {spot.safety?.label ? ` · ${spot.safety.label}` : ''}
            </p>
            {(spot.twin_facts || []).length > 0 && (
              <ul className="twin-facts">
                {spot.twin_facts.map((fact) => (
                  <li key={fact.label}>
                    <span>{fact.label}</span>
                    <em>{fact.value}</em>
                  </li>
                ))}
              </ul>
            )}
            {spot.tide?.next && (
              <p className="twin-next">
                {spot.tide.next.label} {spot.tide.next.time}
                {spot.tide.next.is_tomorrow ? ' (내일)' : ''} ·{' '}
                {formatMinutes(spot.tide.next.minutes)}
              </p>
            )}
            <Link to={`/spot/${spot.id}`}>자세히</Link>
          </div>
        </Popup>
      </Marker>
    ))}
  </MapContainer>
)

export default LeafletTwinMap
