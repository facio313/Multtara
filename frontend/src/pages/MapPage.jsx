import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import KakaoTwinMap from '../components/map/KakaoTwinMap';
import LeafletTwinMap from '../components/map/LeafletTwinMap';
import api, { unwrapList } from '../services/api';
import SpotPhoto from '../components/SpotPhoto';
import { kakaoMapKey } from '../utils/kakaoMap';
import { scoreTone } from '../utils/scoreColor';
import { spotTypeLabel } from '../utils/spotType';
import { tempColor } from '../utils/twin';
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

const MapPage = () => {
  const [spots, setSpots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [spotType, setSpotType] = useState('');
  const [layer, setLayer] = useState('index');
  const [mapEngine, setMapEngine] = useState(() => (kakaoMapKey() ? 'kakao' : 'leaflet'));

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

  const handleKakaoError = useCallback(() => {
    setMapEngine('leaflet');
  }, []);

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
          {!loading && mapEngine === 'kakao' && (
            <KakaoTwinMap spots={filteredSpots} layer={layer} onError={handleKakaoError} />
          )}
          {!loading && mapEngine === 'leaflet' && (
            <LeafletTwinMap spots={filteredSpots} layer={layer} />
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
