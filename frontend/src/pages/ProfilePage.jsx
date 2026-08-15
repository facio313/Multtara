import React, { useEffect, useState } from 'react';
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

const ProfilePage = () => {
  const { user, ready, login, register, logout, changePassword } = useAuthStore();
  const [mode, setMode] = useState('login');
  const [authForm, setAuthForm] = useState(EMPTY_AUTH);
  const [passwordForm, setPasswordForm] = useState(EMPTY_PASSWORD);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

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
        <p>로그인되어 있습니다. 패스포트는 다음 단계에서 붙입니다.</p>
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
      </dl>

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
