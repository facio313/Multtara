import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import api, { unwrapList } from '../services/api';
import SpotPhoto from '../components/SpotPhoto';
import WaterSoundPlayer from '../components/WaterSoundPlayer';
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
  const [sounds, setSounds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [watching, setWatching] = useState(null);

  useEffect(() => {
    api
      .get('/spots/livecams/', { params: { page_size: 50 } })
      .then((response) => setCams(unwrapList(response.data)))
      .catch(() => setCams([]))
      .finally(() => setLoading(false));
    api
      .get('/spots/sounds/')
      .then((response) => setSounds(Array.isArray(response.data) ? response.data : []))
      .catch(() => setSounds([]));
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
  const liveCount = filteredCams.filter((cam) => cam.livecam?.is_live).length;

  return (
    <div className="page cam-page">
      <header className="page-head">
        <h1>라이브캠</h1>
        <p>
          {liveCount > 0
            ? `공개 스트림 ${liveCount}곳 · 나머지는 장소 사진입니다.`
            : '지자체 CCTV URL이 없어 지금은 장소 사진입니다. 공개 스트림을 넣으면 여기서 재생됩니다.'}
        </p>
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
        {filteredCams.map((cam) => {
          const live = cam.livecam?.is_live && cam.livecam?.embed_url;
          return (
            <article key={cam.id} className="cam-card">
              {live ? (
                <button
                  type="button"
                  className="cam-live-btn"
                  onClick={() => setWatching(cam)}
                >
                  <iframe
                    title={cam.name}
                    src={cam.livecam.embed_url}
                    allow="autoplay; encrypted-media"
                  />
                  <span className="live-badge">LIVE</span>
                </button>
              ) : (
                <Link to={`/spot/${cam.id}`}>
                  <SpotPhoto className="cam-image" spot={cam} alt={cam.name} />
                </Link>
              )}
              <div className="cam-meta">
                <h2>
                  <Link to={`/spot/${cam.id}`}>{cam.name}</Link>
                </h2>
                <p className="muted">
                  {cam.region} · {spotTypeLabel(cam.type)}
                  {live ? '' : ' · 사진'}
                </p>
                <span className={`score is-${scoreTone(cam.water_index)}`}>
                  {cam.water_index ?? '-'}
                </span>
              </div>
            </article>
          );
        })}
      </div>

      {sounds.length > 0 && (
        <section>
          <h2 className="section-title">물소리 라이브러리</h2>
          <p className="muted">오늘 파고·풍속으로 예측한 ASMR 지수입니다.</p>
          <ul className="spot-rows">
            {sounds.slice(0, 8).map((row) => (
              <li key={row.id} className="spot-row">
                <span className="spot-copy">
                  <strong>
                    <Link to={`/spot/${row.id}`}>{row.name}</Link>
                  </strong>
                  <em>
                    {row.region} · {row.sound_label} · {row.mood}
                  </em>
                </span>
                <span className={`score is-${scoreTone(row.asmr_score)}`}>{row.asmr_score}</span>
                <WaterSoundPlayer
                  compact
                  soundType={row.sound_type}
                  score={row.asmr_score}
                  label="듣기"
                />
              </li>
            ))}
          </ul>
        </section>
      )}

      {watching?.livecam?.embed_url && (
        <div className="cam-theater" role="dialog" aria-label="라이브 물멍">
          <iframe
            title={watching.name}
            src={watching.livecam.embed_url}
            allow="autoplay; encrypted-media; picture-in-picture"
            allowFullScreen
          />
          <div className="cam-theater-bar">
            <strong>{watching.name}</strong>
            <span className={`score is-${scoreTone(watching.water_index)}`}>
              {watching.water_index ?? '-'}
            </span>
            <button type="button" onClick={() => setWatching(null)}>닫기</button>
            {watching.asmr && (
              <WaterSoundPlayer
                compact
                soundType={watching.asmr.sound_type}
                score={watching.asmr.asmr_score}
                label="물소리"
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default LivecamPage;
