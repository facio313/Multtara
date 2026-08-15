import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import api, { unwrapList } from '../services/api';
import SpotPhoto from '../components/SpotPhoto';
import { scoreTone } from '../utils/scoreColor';
import { spotTypeLabel } from '../utils/spotType';
import { formatMinutes, tempColor } from '../utils/twin';
import './MapPage.css';

const TYPE_FILTERS = [
  { id: '', label: '전체' },
  { id: 'sea', label: '바다' },
  { id: 'valley', label: '계곡' },
  { id: 'hotspring', label: '온천' },
  { id: 'tidal_flat', label: '갯벌' },
  { id: 'lake', label: '호수' },
];

const LAYERS = [
  { id: 'index', label: '지수' },
  { id: 'temp', label: '수온' },
];

function scoreIcon(score) {
  return L.divIcon({
    className: 'score-marker',
    html: `<div class="score-marker-inner is-${scoreTone(score)}">${score ?? '-'}</div>`,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
  });
}

function tempIcon(temp) {
  const label = temp == null || Number.isNaN(Number(temp)) ? '-' : Math.round(Number(temp));
  return L.divIcon({
    className: 'score-marker',
    html: `<div class="temp-marker-inner" style="background:${tempColor(temp)}">${label}</div>`,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
  });
}

const MapPage = () => {
  const [spots, setSpots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [spotType, setSpotType] = useState('');
  const [layer, setLayer] = useState('index');

  useEffect(() => {
    const fetchSpots = async () => {
      try {
        const response = await api.get('/spots/', {
          params: { page_size: 100, ...(spotType ? { type: spotType } : {}) },
        });
        setSpots(unwrapList(response.data));
      } catch (error) {
        console.error('Failed to fetch spots', error);
        setSpots([]);
      } finally {
        setLoading(false);
      }
    };
    setLoading(true);
    fetchSpots();
  }, [spotType]);

  const filteredSpots = useMemo(
    () =>
      spots.filter(
        (spot) =>
          spot.name.includes(search) ||
          spot.region.includes(search) ||
          spotTypeLabel(spot.type).includes(search)
      ),
    [spots, search]
  );

  return (
    <div className="page map-page">
      <header className="page-head">
        <h1>워터 트윈</h1>
        <p>지수 또는 수온으로 지금 상태 좋은 물을 찾습니다.</p>
      </header>

      <div className="map-toolbar">
        <input
          type="search"
          placeholder="장소 또는 지역"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <div className="chip-row">
          {TYPE_FILTERS.map((item) => (
            <button
              key={item.label}
              className={`chip ${spotType === item.id ? 'active' : ''}`}
              onClick={() => setSpotType(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="chip-row">
          {LAYERS.map((item) => (
            <button
              key={item.id}
              className={`chip ${layer === item.id ? 'active' : ''}`}
              onClick={() => setLayer(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="map-split">
        <div className="map-list">
          {loading && <p className="empty">불러오는 중</p>}
          {!loading && filteredSpots.length === 0 && (
            <p className="empty">해당하는 장소가 없습니다.</p>
          )}
          <ul className="spot-rows">
            {filteredSpots.map((spot) => (
              <li key={spot.id}>
                <Link to={`/spot/${spot.id}`} className="spot-row">
                  <SpotPhoto className="spot-thumb" spot={spot} />
                  <span className="spot-copy">
                    <strong>{spot.name}</strong>
                    <em>
                      {spot.region} · {spotTypeLabel(spot.type)}
                      {spot.safety?.label ? ` · ${spot.safety.label}` : ''}
                    </em>
                  </span>
                  <span
                    className={
                      layer === 'temp'
                        ? 'score temp-score'
                        : `score is-${scoreTone(spot.water_index)}`
                    }
                    style={
                      layer === 'temp'
                        ? { color: tempColor(spot.condition?.water_temp) }
                        : undefined
                    }
                  >
                    {layer === 'temp'
                      ? spot.condition?.water_temp != null
                        ? `${Math.round(spot.condition.water_temp)}°`
                        : '-'
                      : (spot.water_index ?? '-')}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div className="map-frame">
          {!loading && (
            <MapContainer center={[36.5, 127.8]} zoom={7} style={{ height: '100%', width: '100%' }}>
              <TileLayer
                attribution="&copy; OpenStreetMap &copy; CARTO"
                url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
              />
              {filteredSpots.map((spot) => (
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
          )}
          {layer === 'temp' && (
            <div className="map-legend">
              <span style={{ background: '#2b6cb0' }}>18°↓</span>
              <span style={{ background: '#4c9adf' }}>22°</span>
              <span style={{ background: '#e07a3d' }}>26°</span>
              <span style={{ background: '#d64545' }}>26°↑</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MapPage;
