import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api, { unwrapList } from '../services/api';
import useGeolocation from '../hooks/useGeolocation';
import SpotPhoto from '../components/SpotPhoto';
import BrandMark from '../components/BrandMark';
import { scoreLabel, scoreTone } from '../utils/scoreColor';
import { ACTIVITY_LABELS, spotTypeLabel } from '../utils/spotType';
import { formatMinutes, safetyTone } from '../utils/twin';
import './HomePage.css';

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토'];

const HomePage = () => {
  const [activity, setActivity] = useState('swim');
  const [ranking, setRanking] = useState([]);
  const [forecast, setForecast] = useState([]);
  const [forecastMessage, setForecastMessage] = useState('');
  const [bestDate, setBestDate] = useState('');
  const [cams, setCams] = useState([]);
  const [nearby, setNearby] = useState([]);
  const [firstSwim, setFirstSwim] = useState([]);
  const [tides, setTides] = useState([]);
  const [radar, setRadar] = useState([]);
  const [recs, setRecs] = useState([]);
  const [recReason, setRecReason] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const position = useGeolocation();

  useEffect(() => {
    api
      .get('/spots/forecast-summary/')
      .then((response) => {
        setForecast(response.data.days || []);
        setForecastMessage(response.data.message || '');
        setBestDate(response.data.best_date || '');
      })
      .catch(() => {
        setForecast([]);
        setForecastMessage('');
      });

    api
      .get('/spots/livecams/', { params: { page_size: 5 } })
      .then((response) => setCams(unwrapList(response.data)))
      .catch(() => setCams([]));

    api
      .get('/spots/first-swim/', { params: { page_size: 6 } })
      .then((response) => setFirstSwim(unwrapList(response.data)))
      .catch(() => setFirstSwim([]));

    api
      .get('/spots/', { params: { type: 'tidal_flat', page_size: 12 } })
      .then((response) => setTides(unwrapList(response.data)))
      .catch(() => setTides([]));

    api
      .get('/spots/safety-radar/')
      .then((response) => setRadar(Array.isArray(response.data) ? response.data.slice(0, 6) : []))
      .catch(() => setRadar([]));

    api
      .get('/spots/recommend/', { params: { page_size: 6 } })
      .then((response) => {
        setRecs(unwrapList(response.data));
        setRecReason(response.data.reason || '');
      })
      .catch(() => {
        setRecs([]);
        setRecReason('');
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    api
      .get('/spots/ranking/', { params: { activity, page_size: 9 } })
      .then((response) => {
        if (!cancelled) setRanking(unwrapList(response.data));
      })
      .catch(() => {
        if (!cancelled) {
          setRanking([]);
          setError(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activity]);

  useEffect(() => {
    if (!position) return;
    api
      .get('/spots/nearby/', { params: { lat: position.lat, lng: position.lng, radius: 120 } })
      .then((response) => setNearby(unwrapList(response.data).slice(0, 5)))
      .catch(() => setNearby([]));
  }, [position]);

  const featured = ranking[0];
  const rest = ranking.slice(1);

  return (
    <div className="page home-page">
      <div className="home-top">
        <div className="home-brand">
          <BrandMark />
        </div>
        <h1>지금 가기 좋은 <em>물</em></h1>
        <div className="chip-row">
          {Object.entries(ACTIVITY_LABELS).map(([key, label]) => (
            <button
              key={key}
              className={`chip ${activity === key ? 'active' : ''}`}
              onClick={() => setActivity(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="home-board">
          <div className="skeleton photo" />
          <div className="skeleton copy" />
        </div>
      )}

      {error && <p className="empty">순위를 불러오지 못했습니다.</p>}

      {!loading && featured && (
        <div className="home-board">
          <Link to={`/spot/${featured.id}`} className="lead-poster">
            <SpotPhoto className="lead-photo" spot={featured} alt={featured.name} />
            <div className="lead-copy">
              <span className={`lead-score score is-${scoreTone(featured.water_index)}`}>
                {featured.water_index ?? '-'}
              </span>
              <span className="lead-kicker">
                {featured.region} · {spotTypeLabel(featured.type)}
              </span>
              <h2>{featured.name}</h2>
              <p>{scoreLabel(featured.water_index)} · {ACTIVITY_LABELS[activity]}</p>
            </div>
          </Link>

          {rest.length > 0 && (
            <section className="rank-panel">
              <h3>순위</h3>
              <ul>
                {rest.map((spot, index) => (
                  <li key={spot.id}>
                    <Link to={`/spot/${spot.id}`} className="rank-row">
                      <span className="rank-no">{String(index + 2).padStart(2, '0')}</span>
                      <span className="rank-copy">
                        <strong>{spot.name}</strong>
                        <em>{spot.region}</em>
                      </span>
                      <span className={`score is-${scoreTone(spot.water_index)}`}>
                        {spot.water_index ?? '-'}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      {!loading && !featured && !error && (
        <p className="empty">이 활동에 맞는 장소가 없습니다.</p>
      )}

      {recs.length > 0 && (
        <section>
          <h3 className="section-title">AI 추천</h3>
          {recReason && <p className="muted home-note">{recReason}</p>}
          <ul className="rank-list">
            {recs.map((spot) => (
              <li key={spot.id}>
                <Link to={`/spot/${spot.id}`} className="rank-row">
                  <span className="rank-copy">
                    <strong>{spot.name}</strong>
                    <em>
                      {spot.region} · {spotTypeLabel(spot.type)}
                    </em>
                  </span>
                  <span className={`score is-${scoreTone(spot.water_index)}`}>
                    {spot.water_index ?? '-'}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {forecast.length > 0 && (
        <section className="week-block">
          <div className="week-head">
            <h3>이번 주</h3>
            {forecastMessage && <p>{forecastMessage}</p>}
          </div>
          <div className="week-strip">
            {forecast.map((day) => {
              const date = new Date(`${day.forecast_date}T00:00:00`);
              const isBest = day.forecast_date === bestDate;
              return (
                <div className={`week-cell${isBest ? ' is-best' : ''}`} key={day.forecast_date}>
                  <span>{WEEKDAY[date.getDay()]}</span>
                  <strong className={`score is-${scoreTone(day.predicted_index)}`}>
                    {day.predicted_index}
                  </strong>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {tides.some((spot) => spot.tide?.next) && (
        <section>
          <h3 className="section-title">지금 물때</h3>
          <ul className="rank-list tide-list">
            {tides
              .filter((spot) => spot.tide?.next)
              .slice(0, 4)
              .map((spot) => (
                <li key={spot.id}>
                  <Link to={`/spot/${spot.id}`} className="rank-row">
                    <span className="rank-copy">
                      <strong>{spot.name}</strong>
                      <em>
                        {spot.tide.next.is_tomorrow ? '내일 ' : ''}
                        {spot.tide.next.label} {spot.tide.next.time}
                        {spot.tide.next.mudflat_window ? ' · 체험 적기' : ''}
                      </em>
                    </span>
                    <span className="muted">{formatMinutes(spot.tide.next.minutes)}</span>
                  </Link>
                </li>
              ))}
          </ul>
        </section>
      )}

      {radar.length > 0 && (
        <section>
          <h3 className="section-title">계곡·바다 안전</h3>
          <ul className="rank-list">
            {radar.map((spot) => (
              <li key={spot.id}>
                <Link to={`/spot/${spot.id}`} className="rank-row">
                  <span className="rank-copy">
                    <strong>{spot.name}</strong>
                    <em>{(spot.safety?.reasons || []).join(' · ')}</em>
                  </span>
                  <span className={`safety-pill is-${safetyTone(spot.safety?.level)}`}>
                    {spot.safety?.label || '-'}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {(firstSwim.length > 0 || nearby.length > 0) && (
        <div className="home-duo">
          {firstSwim.length > 0 && (
            <section>
              <h3 className="section-title">올해 첫 입수</h3>
              <p className="muted home-note">수온 22.5℃를 넘긴 해변입니다.</p>
              <div className="temp-grid">
                {firstSwim.map((spot) => (
                  <Link to={`/spot/${spot.id}`} key={spot.id} className="temp-card">
                    <SpotPhoto className="temp-image" spot={spot} alt="" />
                    <span>
                      <strong>{spot.name}</strong>
                      <em>{spot.condition?.water_temp ? `${spot.condition.water_temp}°` : spot.region}</em>
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          )}
          {nearby.length > 0 && (
            <section>
              <h3 className="section-title">근처</h3>
              <ul className="rank-list">
                {nearby.map((spot) => (
                  <li key={spot.id}>
                    <Link to={`/spot/${spot.id}`} className="rank-row">
                      <span className="rank-copy">
                        <strong>{spot.name}</strong>
                        <em>{spot.region}</em>
                      </span>
                      <span className={`score is-${scoreTone(spot.water_index)}`}>
                        {spot.water_index ?? '-'}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      {cams.length > 0 && (
        <section>
          <h3 className="section-title">라이브캠</h3>
          <div className="preview-mosaic">
            {cams.map((cam) => (
              <Link to={`/spot/${cam.id}`} key={cam.id} className="preview-card">
                <SpotPhoto className="preview-image" spot={cam} alt={cam.name} />
                <span>{cam.name}</span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default HomePage;
