import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import api, { unwrapList } from '../services/api';
import SpotPhoto from '../components/SpotPhoto';
import { scoreTone } from '../utils/scoreColor';
import { spotTypeLabel } from '../utils/spotType';
import './MapPage.css';

const TYPE_FILTERS = [
  { id: '', label: '전체' },
  { id: 'sea', label: '바다' },
  { id: 'valley', label: '계곡' },
  { id: 'hotspring', label: '온천' },
  { id: 'tidal_flat', label: '갯벌' },
  { id: 'lake', label: '호수' },
];

function scoreIcon(score) {
  return L.divIcon({
    className: 'score-marker',
    html: `<div class="score-marker-inner is-${scoreTone(score)}">${score ?? '-'}</div>`,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
  });
}

const MapPage = () => {
  const [spots, setSpots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [spotType, setSpotType] = useState('');

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
        <h1>지도</h1>
        <p>숫자는 물놀이 지수입니다.</p>
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
                    <em>{spot.region} · {spotTypeLabel(spot.type)}</em>
                  </span>
                  <span className={`score is-${scoreTone(spot.water_index)}`}>
                    {spot.water_index ?? '-'}
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
                attribution='&copy; OpenStreetMap &copy; CARTO'
                url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
              />
              {filteredSpots.map((spot) => (
                <Marker key={spot.id} position={[spot.lat, spot.lng]} icon={scoreIcon(spot.water_index)}>
                  <Popup>
                    <div className="map-popup">
                      <strong>{spot.name}</strong>
                      <p>{spot.region} · {spotTypeLabel(spot.type)}</p>
                      <Link to={`/spot/${spot.id}`}>자세히</Link>
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          )}
        </div>
      </div>
    </div>
  );
};

export default MapPage;
