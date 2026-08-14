import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import api, { unwrapList } from '../services/api';
import SpotPhoto from '../components/SpotPhoto';
import { scoreTone } from '../utils/scoreColor';
import { spotTypeLabel } from '../utils/spotType';
import './LivecamPage.css';

const FILTERS = [
  { id: '전체' },
  { id: '바다', type: 'sea' },
  { id: '계곡', type: 'valley' },
  { id: '제주', region: '제주' },
  { id: '강원', region: '강원' },
  { id: '부산', region: '부산' },
];

const LivecamPage = () => {
  const [filter, setFilter] = useState('전체');
  const [cams, setCams] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get('/spots/livecams/', { params: { page_size: 50 } })
      .then((response) => setCams(unwrapList(response.data)))
      .catch(() => setCams([]))
      .finally(() => setLoading(false));
  }, []);

  const selected = FILTERS.find((item) => item.id === filter) || FILTERS[0];
  const filteredCams = useMemo(
    () =>
      cams.filter((cam) => {
        if (selected.type) return cam.type === selected.type;
        if (selected.region) return cam.region === selected.region;
        return true;
      }),
    [cams, selected]
  );

  return (
    <div className="page cam-page">
      <header className="page-head">
        <h1>미리보기</h1>
        <p>실시간 CCTV가 아니라 장소 사진입니다.</p>
      </header>

      <div className="chip-row">
        {FILTERS.map((item) => (
          <button
            key={item.id}
            className={`chip ${filter === item.id ? 'active' : ''}`}
            onClick={() => setFilter(item.id)}
          >
            {item.id}
          </button>
        ))}
      </div>

      {loading && <p className="empty">불러오는 중</p>}

      {!loading && filteredCams.length === 0 && (
        <p className="empty">해당하는 장소가 없습니다.</p>
      )}

      <div className="cam-grid">
        {filteredCams.map((cam) => (
          <Link to={`/spot/${cam.id}`} key={cam.id} className="cam-card">
            <SpotPhoto className="cam-image" spot={cam} alt={cam.name} />
            <div className="cam-meta">
              <h2>{cam.name}</h2>
              <p className="muted">
                {cam.region} · {spotTypeLabel(cam.type)}
              </p>
              <span className={`score is-${scoreTone(cam.water_index)}`}>
                {cam.water_index ?? '-'}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
};

export default LivecamPage;
