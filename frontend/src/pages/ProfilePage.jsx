import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import useAuthStore from '../stores/authStore';
import './ProfilePage.css';

const EMPTY_AUTH = {
  username: '',
  password: '',
  passwordConfirm: '',
  homeRegion: '',
};

const EMPTY_PASSWORD = {
  currentPassword: '',
  newPassword: '',
  newPasswordConfirm: '',
};

const PERSONA_OPTIONS = [
  { id: 'swim', label: '물놀이' },
  { id: 'surf', label: '서핑' },
  { id: 'relax', label: '물멍' },
  { id: 'onsen', label: '온천' },
  { id: 'mudflat', label: '갯벌' },
  { id: 'rafting', label: '래프팅' },
  { id: 'family', label: '가족' },
  { id: 'healing', label: '힐링' },
];

const MOOD_OPTIONS = [
  { id: 'healing', label: '힐링' },
  { id: 'release', label: '해소' },
  { id: 'energetic', label: '활기' },
  { id: 'calm', label: '차분' },
];

const TRANSPORT_OPTIONS = [
  { id: 'car', label: '자동차' },
  { id: 'public', label: '대중교통' },
  { id: 'walk', label: '도보' },
];

const ProfilePage = () => {
  const {
    user,
    passport,
    safetyCards,
    itineraries,
    itineraryPlan,
    ready,
    login,
    register,
    logout,
    changePassword,
    updateProfile,
    createItinerary,
  } = useAuthStore();
  const [mode, setMode] = useState('login');
  const [authForm, setAuthForm] = useState(EMPTY_AUTH);
  const [passwordForm, setPasswordForm] = useState(EMPTY_PASSWORD);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [itineraryForm, setItineraryForm] = useState({
    start_point: '',
    transport: 'car',
    is_day_trip: true,
    party_size: 2,
    budget: '',
    activity: '',
  });

  useEffect(() => {
    setMessage('');
  }, [mode, user]);

  const submitAuth = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    const result =
      mode === 'register'
        ? await register({
            username: authForm.username,
            password: authForm.password,
            password_confirm: authForm.passwordConfirm,
            home_region: authForm.homeRegion,
          })
        : await login({
            username: authForm.username,
            password: authForm.password,
          });
    setBusy(false);
    if (!result.ok) {
      setMessage(result.message);
      return;
    }
    setAuthForm(EMPTY_AUTH);
  };

  const submitPassword = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    const result = await changePassword({
      current_password: passwordForm.currentPassword,
      new_password: passwordForm.newPassword,
      new_password_confirm: passwordForm.newPasswordConfirm,
    });
    setBusy(false);
    if (!result.ok) {
      setMessage(result.message);
      return;
    }
    setPasswordForm(EMPTY_PASSWORD);
    setMessage('비밀번호를 바꿨습니다.');
  };

  const savePersona = async (field, value) => {
    setBusy(true);
    setMessage('');
    const result = await updateProfile({ [field]: value });
    setBusy(false);
    if (!result.ok) setMessage(result.message);
  };

  const submitItinerary = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage('');
    const result = await createItinerary({
      start_point: itineraryForm.start_point,
      transport: itineraryForm.transport,
      is_day_trip: itineraryForm.is_day_trip,
      party_size: Number(itineraryForm.party_size) || 1,
      budget: itineraryForm.budget === '' ? null : Number(itineraryForm.budget),
      activity: itineraryForm.activity,
    });
    setBusy(false);
    if (!result.ok) {
      setMessage(result.message);
      return;
    }
    setMessage('하루 일정을 만들었습니다.');
  };

  if (!ready) {
    return (
      <div className="page profile-page">
        <p className="empty">불러오는 중</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="page profile-page">
        <header className="page-head">
          <h1>{mode === 'register' ? '가입' : '로그인'}</h1>
          <p>세션 쿠키로 로그인합니다. 비밀번호는 브라우저에 저장하지 않습니다.</p>
        </header>

        <div className="chip-row">
          <button
            type="button"
            className={`chip ${mode === 'login' ? 'active' : ''}`}
            onClick={() => setMode('login')}
          >
            로그인
          </button>
          <button
            type="button"
            className={`chip ${mode === 'register' ? 'active' : ''}`}
            onClick={() => setMode('register')}
          >
            가입
          </button>
        </div>

        <form className="auth-form" onSubmit={submitAuth} autoComplete="on">
          <label>
            아이디
            <input
              name="username"
              autoComplete="username"
              value={authForm.username}
              onChange={(event) => setAuthForm({ ...authForm, username: event.target.value })}
              required
              minLength={3}
              maxLength={30}
              pattern="[A-Za-z][A-Za-z0-9._]{2,29}"
              title="영문으로 시작, 3~30자"
            />
          </label>
          {mode === 'register' && (
            <label>
              주로 가는 지역 (선택)
              <input
                name="home_region"
                value={authForm.homeRegion}
                onChange={(event) => setAuthForm({ ...authForm, homeRegion: event.target.value })}
                maxLength={100}
              />
            </label>
          )}
          <label>
            비밀번호
            <input
              type="password"
              name="password"
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              value={authForm.password}
              onChange={(event) => setAuthForm({ ...authForm, password: event.target.value })}
              required
              minLength={12}
              maxLength={128}
            />
          </label>
          {mode === 'register' && (
            <label>
              비밀번호 확인
              <input
                type="password"
                name="passwordConfirm"
                autoComplete="new-password"
                value={authForm.passwordConfirm}
                onChange={(event) =>
                  setAuthForm({ ...authForm, passwordConfirm: event.target.value })
                }
                required
                minLength={12}
                maxLength={128}
              />
            </label>
          )}
          {mode === 'register' && (
            <p className="muted">12자 이상, 흔한 비밀번호는 사용할 수 없습니다.</p>
          )}
          {message && <p className="auth-error">{message}</p>}
          <button type="submit" className="auth-submit" disabled={busy}>
            {busy ? '처리 중' : mode === 'register' ? '가입하고 로그인' : '로그인'}
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="page profile-page">
      <header className="page-head">
        <h1>{user.username}</h1>
        <p>
          방문 {passport?.visited_count ?? 0}곳 · 배지 {passport?.badges?.length ?? 0}개
        </p>
      </header>

      <dl className="facts">
        <div>
          <dt>아이디</dt>
          <dd>{user.username}</dd>
        </div>
        <div>
          <dt>지역</dt>
          <dd>{user.home_region || '-'}</dd>
        </div>
        <div>
          <dt>성향</dt>
          <dd>{PERSONA_OPTIONS.find((row) => row.id === user.persona_type)?.label || '-'}</dd>
        </div>
        <div>
          <dt>기분</dt>
          <dd>{MOOD_OPTIONS.find((row) => row.id === user.mood_state)?.label || '-'}</dd>
        </div>
      </dl>

      <section>
        <h2 className="section-title">성향 · 기분</h2>
        <p className="muted">추천과 컨시어지에 반영됩니다.</p>
        <div className="chip-row">
          {PERSONA_OPTIONS.map((row) => (
            <button
              key={row.id}
              type="button"
              className={`chip ${user.persona_type === row.id ? 'active' : ''}`}
              disabled={busy}
              onClick={() => savePersona('persona_type', row.id)}
            >
              {row.label}
            </button>
          ))}
        </div>
        <div className="chip-row">
          {MOOD_OPTIONS.map((row) => (
            <button
              key={row.id}
              type="button"
              className={`chip ${user.mood_state === row.id ? 'active' : ''}`}
              disabled={busy}
              onClick={() => savePersona('mood_state', row.id)}
            >
              {row.label}
            </button>
          ))}
        </div>
      </section>

      {passport?.badges?.length > 0 && (
        <section>
          <h2 className="section-title">배지</h2>
          <ul className="badge-list">
            {passport.badges.map((badge) => (
              <li key={badge.id}>
                <strong>{badge.title}</strong>
                <span>{badge.description}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {passport?.collection?.length > 0 && (
        <section>
          <h2 className="section-title">도감</h2>
          <ul className="collection-list">
            {passport.collection.map((row) => (
              <li key={row.type}>
                <span>
                  {row.label} {row.visited}/{row.total}
                </span>
                <progress max={row.total} value={row.visited} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {passport?.stamps?.length > 0 && (
        <section>
          <h2 className="section-title">스탬프</h2>
          <ul className="stamp-list">
            {passport.stamps.map((stamp) => (
              <li key={stamp.id}>
                <Link to={`/spot/${stamp.spot_id}`}>
                  <strong>{stamp.name}</strong>
                  <em>{stamp.region}</em>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {passport && passport.visited_count === 0 && (
        <p className="muted">장소 상세에서 방문 인증을 하면 스탬프가 쌓입니다.</p>
      )}

      {safetyCards?.length > 0 && (
        <section>
          <h2 className="section-title">안전 카드</h2>
          <ul className="stamp-list">
            {safetyCards.map((card) => (
              <li key={card.id}>
                <Link to={`/safety/${card.id}`}>
                  <strong>{card.spot?.name || '안전 카드'}</strong>
                  <em>{card.safety?.label || '저장됨'}</em>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <form className="auth-form" onSubmit={submitItinerary}>
        <h2 className="section-title">하루 일정</h2>
        <label>
          출발 지역
          <input
            value={itineraryForm.start_point}
            onChange={(event) =>
              setItineraryForm({ ...itineraryForm, start_point: event.target.value })
            }
            placeholder="부산"
            required
            maxLength={200}
          />
        </label>
        <div className="chip-row">
          {TRANSPORT_OPTIONS.map((row) => (
            <button
              key={row.id}
              type="button"
              className={`chip ${itineraryForm.transport === row.id ? 'active' : ''}`}
              onClick={() => setItineraryForm({ ...itineraryForm, transport: row.id })}
            >
              {row.label}
            </button>
          ))}
        </div>
        <div className="chip-row">
          <button
            type="button"
            className={`chip ${itineraryForm.is_day_trip ? 'active' : ''}`}
            onClick={() => setItineraryForm({ ...itineraryForm, is_day_trip: true })}
          >
            당일치기
          </button>
          <button
            type="button"
            className={`chip ${!itineraryForm.is_day_trip ? 'active' : ''}`}
            onClick={() => setItineraryForm({ ...itineraryForm, is_day_trip: false })}
          >
            1박
          </button>
        </div>
        <label>
          인원
          <input
            type="number"
            min={1}
            max={20}
            value={itineraryForm.party_size}
            onChange={(event) =>
              setItineraryForm({ ...itineraryForm, party_size: event.target.value })
            }
          />
        </label>
        <label>
          예산 (선택)
          <input
            type="number"
            min={0}
            value={itineraryForm.budget}
            onChange={(event) => setItineraryForm({ ...itineraryForm, budget: event.target.value })}
            placeholder="80000"
          />
        </label>
        <label>
          활동 (선택)
          <input
            value={itineraryForm.activity}
            onChange={(event) =>
              setItineraryForm({ ...itineraryForm, activity: event.target.value })
            }
            placeholder="swim"
          />
        </label>
        <button type="submit" className="auth-submit" disabled={busy}>
          {busy ? '만드는 중' : '일정 만들기'}
        </button>
      </form>

      {(itineraryPlan?.legs?.length > 0 || itineraries.length > 0) && (
        <section>
          <h2 className="section-title">최근 일정</h2>
          {itineraryPlan?.legs?.length > 0 && (
            <ul className="stamp-list">
              {itineraryPlan.legs.map((leg) => (
                <li key={`${leg.time}-${leg.spot_id}`}>
                  <Link to={`/spot/${leg.spot_id}`}>
                    <strong>
                      {leg.time} {leg.name}
                    </strong>
                    <em>
                      {leg.region} · {leg.type}
                    </em>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {itineraryPlan?.note && <p className="muted">{itineraryPlan.note}</p>}
        </section>
      )}

      <form className="auth-form" onSubmit={submitPassword} autoComplete="off">
        <h2 className="section-title">비밀번호 변경</h2>
        <label>
          현재 비밀번호
          <input
            type="password"
            autoComplete="current-password"
            value={passwordForm.currentPassword}
            onChange={(event) =>
              setPasswordForm({ ...passwordForm, currentPassword: event.target.value })
            }
            required
          />
        </label>
        <label>
          새 비밀번호
          <input
            type="password"
            autoComplete="new-password"
            value={passwordForm.newPassword}
            onChange={(event) =>
              setPasswordForm({ ...passwordForm, newPassword: event.target.value })
            }
            required
            minLength={12}
            maxLength={128}
          />
        </label>
        <label>
          새 비밀번호 확인
          <input
            type="password"
            autoComplete="new-password"
            value={passwordForm.newPasswordConfirm}
            onChange={(event) =>
              setPasswordForm({ ...passwordForm, newPasswordConfirm: event.target.value })
            }
            required
            minLength={12}
            maxLength={128}
          />
        </label>
        {message && <p className={message.includes('바꿨') ? 'muted' : 'auth-error'}>{message}</p>}
        <button type="submit" className="auth-submit" disabled={busy}>
          {busy ? '처리 중' : '비밀번호 바꾸기'}
        </button>
      </form>

      <button type="button" className="text-back" onClick={logout}>
        로그아웃
      </button>
    </div>
  );
};

export default ProfilePage;
