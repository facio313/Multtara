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
const CROWD_LABELS = { high: '혼잡', medium: '보통', low: '여유' };
const SOUND_LABELS = { wave: '파도', valley: '계곡', waterfall: '폭포', tidal: '갯벌', rain: '비' };

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
  const logEco = useAuthStore((state) => state.logEco);
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
  const [ecoChecked, setEcoChecked] = useState(false);
  const [ecoBusy, setEcoBusy] = useState(false);

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
  const visitedStamp = passport?.stamps?.find((stamp) => String(stamp.spot_id) === String(spot.id));
  const visited = Boolean(visitedStamp);
  const hasEco = Boolean(visitedStamp?.eco_action);
  const savedCard = safetyCards.find((row) => String(row.spot_id) === String(spot.id));

  const submitCheckin = async () => {
    setCheckingIn(true);
    setCheckinMessage('');
    const result = await checkin(spot.id, ecoChecked ? 'plogging' : '');
    setCheckingIn(false);
    setCheckinMessage(result.ok ? '방문 인증을 남겼습니다.' : result.message);
  };

  const submitEco = async () => {
    setEcoBusy(true);
    setCheckinMessage('');
    const result = await logEco(spot.id, 'plogging');
    setEcoBusy(false);
    setCheckinMessage(result.ok ? '플로깅을 남겼습니다.' : result.message);
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
            <label className="muted">
              <input
                type="checkbox"
                checked={ecoChecked}
                onChange={(event) => setEcoChecked(event.target.checked)}
              />{' '}
              플로깅했어요
            </label>
            <button type="button" className="auth-submit" onClick={submitCheckin} disabled={checkingIn}>
              {checkingIn ? '인증 중' : '방문 인증'}
            </button>
            <p className="muted">장소 5km 안에서만 인증됩니다. 위치 권한이 필요합니다.</p>
          </>
        )}
        {user && visited && !hasEco && (
          <button type="button" className="auth-submit" onClick={submitEco} disabled={ecoBusy}>
            {ecoBusy ? '기록 중' : '플로깅 인증'}
          </button>
        )}
        {user && hasEco && <p className="muted">이 장소에서 에코 액션을 남겼습니다.</p>}
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

      {spot.crowd?.predicted_level && (
        <section>
          <h2 className="section-title">혼잡</h2>
          <dl className="facts">
            <div>
              <dt>예상</dt>
              <dd>{CROWD_LABELS[spot.crowd.predicted_level] || spot.crowd.predicted_level}</dd>
            </div>
            <div>
              <dt>추천 시간</dt>
              <dd>{spot.crowd.recommended_time || '-'}</dd>
            </div>
            <div>
              <dt>주차</dt>
              <dd>{spot.crowd.parking_availability || '-'}</dd>
            </div>
          </dl>
        </section>
      )}

      {spot.facilities?.length > 0 && (
        <section>
          <h2 className="section-title">주변 시설</h2>
          <ul className="spot-rows">
            {spot.facilities.map((row) => (
              <li key={`${row.type}-${row.name}`} className="spot-row">
                <span className="spot-copy">
                  <strong>{row.name}</strong>
                  <em>{row.label}</em>
                </span>
                <span className="muted">{row.distance_min}분</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {spot.catch && (
        <section>
          <h2 className="section-title">채집 안내</h2>
          <dl className="facts">
            <div>
              <dt>어종</dt>
              <dd>{spot.catch.species}</dd>
            </div>
            <div>
              <dt>금지</dt>
              <dd>{spot.catch.banned_species || '-'}</dd>
            </div>
            <div>
              <dt>적기</dt>
              <dd>{spot.catch.best_time || '-'}</dd>
            </div>
          </dl>
          {spot.catch.season_restriction && (
            <p className="muted tide">{spot.catch.season_restriction}</p>
          )}
        </section>
      )}

      {spot.hotspring && (
        <section>
          <h2 className="section-title">온천</h2>
          <dl className="facts">
            <div>
              <dt>성분</dt>
              <dd>{spot.hotspring.minerals}</dd>
            </div>
            <div>
              <dt>효능</dt>
              <dd>{spot.hotspring.benefits}</dd>
            </div>
          </dl>
        </section>
      )}

      {spot.golden?.length > 0 && (
        <section>
          <h2 className="section-title">골든 타임</h2>
          <ul className="spot-rows">
            {spot.golden.map((row) => (
              <li key={`${row.date}-${row.time}-${row.type}`} className="spot-row">
                <span className="spot-copy">
                  <strong>{row.label}</strong>
                  <em>
                    {row.time}
                    {row.sunset ? ` · 일몰 ${row.sunset}` : ''}
                  </em>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {spot.asmr && (
        <section>
          <h2 className="section-title">물소리</h2>
          <dl className="facts">
            <div>
              <dt>소리</dt>
              <dd>{SOUND_LABELS[spot.asmr.sound_type] || spot.asmr.sound_type}</dd>
            </div>
            <div>
              <dt>ASMR</dt>
              <dd>{spot.asmr.asmr_score ?? '-'}</dd>
            </div>
          </dl>
        </section>
      )}

      {spot.analytics && (
        <section>
          <h2 className="section-title">한눈에</h2>
          <dl className="facts">
            <div>
              <dt>평균 수온</dt>
              <dd>{formatValue(spot.analytics.avg_water_temp, '°C')}</dd>
            </div>
            <div>
              <dt>수질 추이</dt>
              <dd>{spot.analytics.quality_trend || '-'}</dd>
            </div>
            <div>
              <dt>추천 계절</dt>
              <dd>{spot.analytics.best_season || '-'}</dd>
            </div>
          </dl>
        </section>
      )}

      {spot.quality_trust && (
        <section>
          <h2 className="section-title">수질 신뢰</h2>
          <p className="muted">
            공식 {labeled(spot.quality_trust.official_grade, QUALITY_LABELS)} ·{' '}
            {spot.quality_trust.review_signal}
            {spot.quality_trust.agrees_with_official === true ? ' · 후기와 비슷' : ''}
            {spot.quality_trust.agrees_with_official === false ? ' · 후기와 다름' : ''}
          </p>
        </section>
      )}

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
