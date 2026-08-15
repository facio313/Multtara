import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import api from '../services/api';
import useAuthStore from '../stores/authStore';
import { safetyTone } from '../utils/twin';
import { findSafetyCard } from '../utils/safetyCardCache';
import './SafetyCardPage.css';

function shareText(card) {
  if (!card) return '';
  const spot = card.spot || {};
  const safety = card.safety || {};
  return [
    `퐁당 안전 카드 · ${spot.name || ''}`.trim(),
    [spot.region, spot.address].filter(Boolean).join(' · '),
    `상태: ${safety.label || '-'}`,
    (card.risk_factors || []).join(' · '),
    spot.lat != null && spot.lng != null ? `위치: ${spot.lat}, ${spot.lng}` : '',
    card.nearest_safety_facility ? `가까운 시설: ${card.nearest_safety_facility}` : '',
    `긴급: ${card.emergency || '119'}`,
  ]
    .filter(Boolean)
    .join('\n');
}

const SafetyCardPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const ready = useAuthStore((state) => state.ready);
  const cachedSafetyCard = useAuthStore((state) => state.cachedSafetyCard);
  const [card, setCard] = useState(null);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ready) return undefined;
    const local = cachedSafetyCard(id) || findSafetyCard(user?.id, id);
    if (local) {
      setCard(local);
      setLoading(false);
    }
    if (!user) {
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    api
      .get(`/safety-card/${id}/`)
      .then((response) => {
        if (!cancelled) setCard(response.data);
      })
      .catch(() => {
        if (!cancelled && !local) setCard(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cachedSafetyCard, id, ready, user]);

  const text = useMemo(() => shareText(card), [card]);
  const safety = card?.safety || {};
  const condition = card?.condition_snapshot?.condition || {};

  const shareCard = async () => {
    setMessage('');
    try {
      if (navigator.share) {
        await navigator.share({ title: '퐁당 안전 카드', text });
        return;
      }
      await navigator.clipboard.writeText(text);
      setMessage('위치와 안전 정보를 복사했습니다.');
    } catch (error) {
      if (error?.name === 'AbortError') return;
      setMessage('공유하지 못했습니다.');
    }
  };

  if (!ready || loading) {
    return <div className="page"><p className="empty">불러오는 중</p></div>;
  }

  if (!card) {
    return (
      <div className="page">
        <p className="empty">저장된 안전 카드가 없습니다.</p>
        <Link to="/profile">내 정보</Link>
      </div>
    );
  }

  const spot = card.spot || {};

  return (
    <div className="page safety-card-page">
      <button className="text-back" type="button" onClick={() => navigate(-1)}>
        <ArrowLeft size={16} /> 뒤로
      </button>

      <article className={`offline-card is-${safetyTone(safety.level)}`}>
        <p className="muted">오프라인 안전 카드</p>
        <h1>{spot.name}</h1>
        <p className="muted">{[spot.region, spot.address].filter(Boolean).join(' · ')}</p>
        <p>
          <strong>{safety.label || '-'}</strong>
          {(card.risk_factors || []).join(' · ')}
        </p>
        <dl className="facts">
          <div><dt>수온</dt><dd>{condition.water_temp ?? '-'}{condition.water_temp != null ? '°C' : ''}</dd></div>
          <div><dt>강수</dt><dd>{condition.rainfall_recent ?? '-'}{condition.rainfall_recent != null ? 'mm' : ''}</dd></div>
          <div><dt>수위</dt><dd>{condition.water_level ?? '-'}{condition.water_level != null ? 'm' : ''}</dd></div>
          <div><dt>파고</dt><dd>{condition.wave_height ?? '-'}{condition.wave_height != null ? 'm' : ''}</dd></div>
        </dl>
        <p>가까운 시설 {card.nearest_safety_facility || spot.address || '-'}</p>
        <p>긴급 {card.emergency || '119'}</p>
        {spot.lat != null && (
          <p className="muted">위치 {spot.lat}, {spot.lng}</p>
        )}
      </article>

      <div className="safety-card-actions">
        <button type="button" className="auth-submit" onClick={shareCard}>
          위치 공유
        </button>
        <button type="button" className="text-back" onClick={() => window.print()}>
          인쇄 / 저장
        </button>
      </div>
      {message && <p className="muted">{message}</p>}
    </div>
  );
};

export default SafetyCardPage;
