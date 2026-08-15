import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import api from '../services/api';
import SpotPhoto from '../components/SpotPhoto';
import useAuthStore from '../stores/authStore';
import { scoreLabel, scoreTone } from '../utils/scoreColor';
import { ACTIVITY_LABELS, spotTypeLabel } from '../utils/spotType';
import { formatMinutes, safetyTone } from '../utils/twin';
import './SpotDetailPage.css';

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토'];

function formatValue(value, unit) {
  if (value == null || value === '') return '-';
  return `${value}${unit}`;
}

const QUALITY_LABELS = { 1: '좋음', 2: '보통', 3: '나쁨' };
const RISK_LABELS = { low: '낮음', medium: '보통', high: '높음' };

function labeled(value, map) {
  if (value == null || value === '') return '-';
  return map[value] || map[String(value)] || value;
}

const SpotDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const passport = useAuthStore((state) => state.passport);
  const checkin = useAuthStore((state) => state.checkin);
  const saveSafetyCard = useAuthStore((state) => state.saveSafetyCard);
  const safetyCards = useAuthStore((state) => state.safetyCards);
  const [spot, setSpot] = useState(null);
  const [forecast, setForecast] = useState([]);
  const [loading, setLoading] = useState(true);
  const [checkinMessage, setCheckinMessage] = useState('');
  const [checkingIn, setCheckingIn] = useState(false);
  const [cardMessage, setCardMessage] = useState('');
  const [savingCard, setSavingCard] = useState(false);
  const [shareWith, setShareWith] = useState('');

  useEffect(() => {
    const fetchSpot = async () => {
      try {
        const [spotRes, forecastRes] = await Promise.all([
          api.get(`/spots/${id}/`),
          api.get(`/spots/${id}/forecast/`),
        ]);
        setSpot(spotRes.data);
        setForecast(forecastRes.data);
      } catch (error) {
        console.error('Failed to fetch spot detail', error);
      } finally {
        setLoading(false);
      }
    };
    fetchSpot();
  }, [id]);

  if (loading) {
    return <div className="page"><p className="empty">불러오는 중</p></div>;
  }

  if (!spot) {
    return <div className="page"><p className="empty">장소를 찾을 수 없습니다.</p></div>;
  }

  const condition = spot.condition || {};
  const swimScore = spot.scores?.swim ?? spot.water_index;
  const activityScores = Object.entries(ACTIVITY_LABELS).filter(
    ([key]) => spot.scores?.[key] != null
  );
  const chartData = (forecast || []).map((row) => {
    const date = new Date(`${row.forecast_date}T00:00:00`);
    return { name: WEEKDAY[date.getDay()], score: Math.round(row.predicted_index) };
  });
  const tide = spot.tide || {};
  const nxt = tide.next;
  const safety = spot.safety || {};
  const live = spot.livecam || {};
  const visited = Boolean(passport?.stamps?.some((stamp) => String(stamp.spot_id) === String(spot.id)));
  const savedCard = safetyCards.find((row) => String(row.spot_id) === String(spot.id));

  const submitCheckin = async () => {
    setCheckingIn(true);
    setCheckinMessage('');
    const result = await checkin(spot.id);
    setCheckingIn(false);
    setCheckinMessage(result.ok ? '방문 인증을 남겼습니다.' : result.message);
  };

  const submitSafetyCard = async () => {
    setSavingCard(true);
    setCardMessage('');
    const names = shareWith.split(',').map((value) => value.trim()).filter(Boolean);
    const result = await saveSafetyCard(spot.id, names);
    setSavingCard(false);
    if (result.ok) {
      navigate(`/safety/${result.data.id}`);
      return;
    }
    setCardMessage(result.message);
  };

  return (
    <div className="page detail-page">
      <button className="text-back" onClick={() => navigate(-1)}>
        <ArrowLeft size={16} /> 뒤로
      </button>

      {live.is_live && live.embed_url ? (
        <div className="detail-live">
          <iframe
            title={`${spot.name} 라이브캠`}
            src={live.embed_url}
            allow="autoplay; encrypted-media; picture-in-picture"
            allowFullScreen
          />
        </div>
      ) : (
        <SpotPhoto className="detail-photo" spot={spot} alt={spot.name} />
      )}

      <header className="detail-head">
        <div>
          <p className="muted">{spot.region} · {spotTypeLabel(spot.type)}</p>
          <h1>{spot.name}</h1>
        </div>
        <div className="detail-score-wrap">
          <div className={`score is-${scoreTone(swimScore)} detail-score`}>{swimScore ?? '-'}</div>
          <p className="muted">{scoreLabel(swimScore)} · 물놀이 지수</p>
        </div>
      </header>

      <section className="passport-checkin">
        {!user && (
          <p className="muted">
            <Link to="/profile">로그인</Link>하면 방문 인증을 할 수 있습니다.
          </p>
        )}
        {user && visited && <p className="muted">이 장소를 인증했습니다.</p>}
        {user && !visited && (
          <>
            <button type="button" className="auth-submit" onClick={submitCheckin} disabled={checkingIn}>
              {checkingIn ? '인증 중' : '방문 인증'}
            </button>
            <p className="muted">장소 5km 안에서만 인증됩니다. 위치 권한이 필요합니다.</p>
          </>
        )}
        {checkinMessage && <p className={checkinMessage.includes('남겼') ? 'muted' : 'auth-error'}>{checkinMessage}</p>}
      </section>

      {safety.label && (
        <section className={`safety-card is-${safetyTone(safety.level)}`}>
          <h2>안전</h2>
          <p>
            <strong>{safety.label}</strong>
            {(safety.reasons || []).join(' · ')}
          </p>
          {!user && (
            <p className="muted">
              <Link to="/profile">로그인</Link>하면 오프라인 안전 카드를 저장할 수 있습니다.
            </p>
          )}
          {user && (
            <div className="safety-card-save">
              <label>
                공유할 사람 (선택)
                <input
                  value={shareWith}
                  onChange={(event) => setShareWith(event.target.value)}
                  placeholder="가족, 친구"
                />
              </label>
              <button type="button" className="auth-submit" onClick={submitSafetyCard} disabled={savingCard}>
                {savingCard ? '저장 중' : '안전 카드 저장'}
              </button>
              {savedCard && (
                <Link to={`/safety/${savedCard.id}`}>저장한 카드 보기</Link>
              )}
              {cardMessage && <p className="auth-error">{cardMessage}</p>}
            </div>
          )}
        </section>
      )}

      {nxt && (
        <section className="tide-card">
          <h2 className="section-title">물때</h2>
          <p className="tide-next">
            {nxt.is_tomorrow ? '내일 ' : ''}{nxt.label} {nxt.time}
            <em>{formatMinutes(nxt.minutes)}</em>
          </p>
          {spot.type === 'tidal_flat' && nxt.mudflat_window && (
            <p className="muted">간조가 가까워 갯벌 체험 적기입니다.</p>
          )}
          <p className="muted tide">
            간조 {(tide.low_tide || []).join(', ') || '-'} · 만조 {(tide.high_tide || []).join(', ') || '-'}
          </p>
        </section>
      )}

      <section>
        <h2 className="section-title">지금</h2>
        <dl className="facts">
          <div><dt>수온</dt><dd>{formatValue(condition.water_temp, '°C')}</dd></div>
          <div><dt>기온</dt><dd>{formatValue(condition.air_temp, '°C')}</dd></div>
          <div><dt>풍속</dt><dd>{formatValue(condition.wind_speed, ' m/s')}</dd></div>
          <div><dt>파고</dt><dd>{formatValue(condition.wave_height, ' m')}</dd></div>
          <div><dt>강수</dt><dd>{formatValue(condition.rainfall_recent, 'mm')}</dd></div>
          <div><dt>수위</dt><dd>{formatValue(condition.water_level, 'm')}</dd></div>
          <div><dt>자외선</dt><dd>{formatValue(condition.uv_index, '')}</dd></div>
          <div><dt>수질</dt><dd>{labeled(condition.water_quality_grade, QUALITY_LABELS)}</dd></div>
          <div><dt>이안류</dt><dd>{labeled(condition.rip_current_risk, RISK_LABELS)}</dd></div>
        </dl>
        {condition.weather_alert ? <p className="muted tide">{condition.weather_alert}</p> : null}
      </section>

      {activityScores.length > 0 && (
        <section>
          <h2 className="section-title">활동</h2>
          <ul className="spot-rows">
            {activityScores.map(([key, label]) => (
              <li key={key} className="spot-row">
                <span className="spot-copy"><strong>{label}</strong></span>
                <span className={`score is-${scoreTone(spot.scores[key])}`}>{spot.scores[key]}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {chartData.length > 0 && (
        <section>
          <h2 className="section-title">7일 예보</h2>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={chartData} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
                <XAxis dataKey="name" stroke="#a3a3a3" tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} stroke="#a3a3a3" tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{
                    background: '#ffffff',
                    border: '1px solid #ececec',
                    borderRadius: 8,
                    fontSize: 13,
                  }}
                  formatter={(value) => [value, '지수']}
                />
                <Area type="monotone" dataKey="score" stroke="#2b2eff" fill="#ececff" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {spot.livecam_url && !live.is_live && (
        <p className="muted">
          공개 CCTV가 없어 장소 사진을 보여 줍니다. <Link to="/livecam">라이브캠</Link>
        </p>
      )}

      {spot.description && (
        <section>
          <h2 className="section-title">소개</h2>
          <p className="body-copy">{spot.description}</p>
        </section>
      )}
    </div>
  );
};

export default SpotDetailPage;
