import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  BadgeCheck,
  CalendarDays,
  Database,
  KeyRound,
  Leaf,
  LoaderCircle,
  LogIn,
  LogOut,
  MapPin,
  Images,
  Pencil,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  X,
  UserPlus,
  UserRound,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { useWaterSpots } from '../hooks/useWaterData';
import { useI18n } from '../i18n';
import {
  accountLocaleToUiLocale,
  changeAccountPassword,
  classifyAccountError,
  createActivity,
  createEcoAction,
  isMissingSession,
  listActivities,
  listEcoActions,
  listPassports,
  uiLocaleToAccountLocale,
} from '../services/accountApi';
import {
  createTripMemory,
  deleteTripMemory,
  listTripMemories,
  updateTripMemory,
} from '../services/memoryApi';
import useSessionStore from '../store/useSessionStore';
import { runtimeConfig } from '../services/api';
import './ProfilePage.css';

const PERSONA_TYPES = ['', 'active', 'family', 'wellness', 'local', 'stay'];
const ECO_ACTION_TYPES = ['cleanup', 'reusable', 'local', 'transit', 'safety_share'];
const VERIFICATION_STATES = new Set(['pending', 'verified', 'rejected']);

function refreshExpiredSession(error) {
  if (isMissingSession(error)) {
    void useSessionStore.getState().ensureSession({ force: true });
  }
}

function todayValue() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function dateTimeLocalValue(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) return '';
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function formatDate(value, locale, fallback) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

function safeVerificationState(value) {
  const state = String(value || '').toLowerCase();
  return VERIFICATION_STATES.has(state) ? state : 'pending';
}

function Feedback({ feedback, t }) {
  if (!feedback) return null;
  return (
    <p
      className={`account-feedback is-${feedback.type}`}
      role={feedback.type === 'error' ? 'alert' : 'status'}
    >
      {t(feedback.messageKey)}
    </p>
  );
}

function EmptyState({ title, description }) {
  return (
    <div className="account-empty">
      <Database size={20} aria-hidden="true" />
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
    </div>
  );
}

function SpotSelect({ id, value, onChange, spots, label, optional, t }) {
  return (
    <label className="account-field" htmlFor={id}>
      <span>{label}</span>
      <select id={id} value={value} onChange={onChange} required={!optional}>
        <option value="">{optional ? t('account.spot.optional') : t('account.spot.choose')}</option>
        {spots.map((spot) => (
          <option key={spot.apiId} value={spot.apiId}>
            {spot.name} · {spot.region}
          </option>
        ))}
      </select>
    </label>
  );
}

function GuestAccount({ mode, setMode, onLogin, onRegister, busy, feedback, locale, t }) {
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [registerForm, setRegisterForm] = useState({ username: '', email: '', password: '' });
  const tabRefs = useRef([]);

  const moveTab = (event, currentIndex) => {
    const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End'];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    let nextIndex = currentIndex;
    if (event.key === 'ArrowLeft') nextIndex = (currentIndex + 1) % 2;
    if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % 2;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = 1;
    setMode(nextIndex === 0 ? 'login' : 'register');
    tabRefs.current[nextIndex]?.focus();
  };

  const submitLogin = async (event) => {
    event.preventDefault();
    await onLogin(loginForm);
    setLoginForm((current) => ({ ...current, password: '' }));
  };

  const submitRegister = async (event) => {
    event.preventDefault();
    await onRegister({
      ...registerForm,
      preferred_locale: uiLocaleToAccountLocale(locale),
    });
    setRegisterForm((current) => ({ ...current, password: '' }));
  };

  return (
    <section className="account-auth-card" aria-labelledby="account-auth-title">
      <div className="account-section-heading">
        <div>
          <span>{t('account.eyebrow.access')}</span>
          <h2 id="account-auth-title">{t('account.auth.title')}</h2>
          <p>{t('account.auth.description')}</p>
        </div>
        <ShieldCheck size={28} aria-hidden="true" />
      </div>

      <div className="account-tabs" role="tablist" aria-label={t('account.auth.tabs')}>
        <button
          type="button"
          role="tab"
          id="account-login-tab"
          aria-controls="account-login-panel"
          aria-selected={mode === 'login'}
          tabIndex={mode === 'login' ? 0 : -1}
          onClick={() => setMode('login')}
          onKeyDown={(event) => moveTab(event, 0)}
          ref={(node) => { tabRefs.current[0] = node; }}
        >
          <LogIn size={16} aria-hidden="true" /> {t('account.auth.login')}
        </button>
        <button
          type="button"
          role="tab"
          id="account-register-tab"
          aria-controls="account-register-panel"
          aria-selected={mode === 'register'}
          tabIndex={mode === 'register' ? 0 : -1}
          onClick={() => setMode('register')}
          onKeyDown={(event) => moveTab(event, 1)}
          ref={(node) => { tabRefs.current[1] = node; }}
        >
          <UserPlus size={16} aria-hidden="true" /> {t('account.auth.register')}
        </button>
      </div>

      {mode === 'login' ? (
        <form
          id="account-login-panel"
          role="tabpanel"
          aria-labelledby="account-login-tab"
          className="account-form"
          onSubmit={submitLogin}
        >
          <label className="account-field" htmlFor="login-username">
            <span>{t('account.field.username')}</span>
            <input
              id="login-username"
              name="username"
              autoComplete="username"
              value={loginForm.username}
              onChange={(event) => setLoginForm({ ...loginForm, username: event.target.value })}
              maxLength="150"
              required
            />
          </label>
          <label className="account-field" htmlFor="login-password">
            <span>{t('account.field.password')}</span>
            <input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={loginForm.password}
              onChange={(event) => setLoginForm({ ...loginForm, password: event.target.value })}
              required
            />
          </label>
          <Feedback feedback={feedback} t={t} />
          <button className="account-primary-button" type="submit" disabled={busy}>
            {busy ? <LoaderCircle className="account-spinner" size={17} aria-hidden="true" /> : <LogIn size={17} aria-hidden="true" />}
            {busy ? t('common.loading') : t('account.auth.login')}
          </button>
        </form>
      ) : (
        <form
          id="account-register-panel"
          role="tabpanel"
          aria-labelledby="account-register-tab"
          className="account-form"
          onSubmit={submitRegister}
        >
          <label className="account-field" htmlFor="register-username">
            <span>{t('account.field.username')}</span>
            <input
              id="register-username"
              name="username"
              autoComplete="username"
              value={registerForm.username}
              onChange={(event) => setRegisterForm({ ...registerForm, username: event.target.value })}
              maxLength="150"
              required
            />
          </label>
          <label className="account-field" htmlFor="register-email">
            <span>{t('account.field.email')}</span>
            <input
              id="register-email"
              name="email"
              type="email"
              autoComplete="email"
              value={registerForm.email}
              onChange={(event) => setRegisterForm({ ...registerForm, email: event.target.value })}
              maxLength="254"
              required
            />
          </label>
          <label className="account-field" htmlFor="register-password">
            <span>{t('account.field.newPassword')}</span>
            <input
              id="register-password"
              name="new-password"
              type="password"
              autoComplete="new-password"
              value={registerForm.password}
              onChange={(event) => setRegisterForm({ ...registerForm, password: event.target.value })}
              aria-describedby="register-password-help"
              required
            />
            <small id="register-password-help">{t('account.password.help')}</small>
          </label>
          <Feedback feedback={feedback} t={t} />
          <button className="account-primary-button" type="submit" disabled={busy}>
            {busy ? <LoaderCircle className="account-spinner" size={17} aria-hidden="true" /> : <UserPlus size={17} aria-hidden="true" />}
            {busy ? t('common.loading') : t('account.auth.register')}
          </button>
        </form>
      )}
      <p className="account-security-note"><ShieldCheck size={15} aria-hidden="true" /> {t('account.auth.security')}</p>
    </section>
  );
}

function ProfilePage() {
  const { intlLocale, locale, setLocale, t } = useI18n();
  const session = useSessionStore();
  const { spots, spotStatus } = useWaterSpots(null, { loadConditions: false });
  const apiSpots = useMemo(
    () => spots.filter((spot) => Number.isInteger(Number(spot.apiId)) && Number(spot.apiId) > 0),
    [spots],
  );
  const [authMode, setAuthMode] = useState('login');
  const [authBusy, setAuthBusy] = useState(false);
  const [authFeedback, setAuthFeedback] = useState(null);
  const [records, setRecords] = useState({
    status: 'idle', activities: [], passports: [], ecoActions: [], memories: [], error: null,
  });
  const [profileForm, setProfileForm] = useState({
    email: '', first_name: '', last_name: '', persona_type: '', mood_state: '', home_region: '', preferred_locale: locale,
  });
  const [profileFeedback, setProfileFeedback] = useState(null);
  const [profileBusy, setProfileBusy] = useState(false);
  const [activityForm, setActivityForm] = useState({ spot: '', action: 'visit', rating: '5', review_text: '' });
  const [activityFeedback, setActivityFeedback] = useState(null);
  const [activityBusy, setActivityBusy] = useState(false);
  const [ecoForm, setEcoForm] = useState({
    spot: '', action_type: 'cleanup', note: '', evidence_url: '', occurred_on: todayValue(),
  });
  const [ecoFeedback, setEcoFeedback] = useState(null);
  const [ecoBusy, setEcoBusy] = useState(false);
  const [memoryForm, setMemoryForm] = useState({
    spot: '', photo_url: '', taken_at: dateTimeLocalValue(), estimated_location: '',
  });
  const [memoryFeedback, setMemoryFeedback] = useState(null);
  const [memoryBusy, setMemoryBusy] = useState(null);
  const [editingMemoryId, setEditingMemoryId] = useState(null);
  const [editingMemoryForm, setEditingMemoryForm] = useState(null);
  const [confirmingMemoryDelete, setConfirmingMemoryDelete] = useState(null);
  const [passwordForm, setPasswordForm] = useState({ current_password: '', new_password: '', confirm: '' });
  const [passwordFeedback, setPasswordFeedback] = useState(null);
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [deleteForm, setDeleteForm] = useState({ current_password: '', acknowledged: false });
  const [deleteFeedback, setDeleteFeedback] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  useEffect(() => {
    void session.ensureSession();
  }, [session]);

  useEffect(() => {
    if (session.status !== 'authenticated' || !session.user) return;
    const accountLocale = accountLocaleToUiLocale(session.user.preferred_locale);
    setProfileForm({
      email: session.user.email || '',
      first_name: session.user.first_name || '',
      last_name: session.user.last_name || '',
      persona_type: session.user.persona_type || '',
      mood_state: session.user.mood_state || '',
      home_region: session.user.home_region || '',
      preferred_locale: accountLocale,
    });
    setLocale(accountLocale);
  }, [session.status, session.user, setLocale]);

  const loadRecords = useCallback(async () => {
    setRecords((current) => ({ ...current, status: 'loading', error: null }));
    try {
      const [activities, passports, ecoActions, memories] = await Promise.all([
        listActivities(),
        listPassports(),
        listEcoActions(),
        listTripMemories(),
      ]);
      setRecords({ status: 'ready', activities, passports, ecoActions, memories, error: null });
    } catch (error) {
      refreshExpiredSession(error);
      setRecords((current) => ({
        ...current,
        status: 'error',
        error: classifyAccountError(error, 'records'),
      }));
    }
  }, []);

  useEffect(() => {
    if (session.status === 'authenticated') void loadRecords();
    if (session.status === 'guest') {
      setRecords({ status: 'idle', activities: [], passports: [], ecoActions: [], memories: [], error: null });
    }
  }, [loadRecords, session.status]);

  const visits = records.activities.filter((item) => item?.action === 'visit');
  const reviews = records.activities.filter((item) => item?.action === 'review');
  const legacyActivities = records.activities.filter((item) => item?.is_legacy);

  const handleLogin = async (payload) => {
    setAuthBusy(true);
    setAuthFeedback(null);
    try {
      await session.login(payload);
    } catch (error) {
      setAuthFeedback({ type: 'error', ...classifyAccountError(error, 'login') });
    } finally {
      setAuthBusy(false);
    }
  };

  const handleRegister = async (payload) => {
    setAuthBusy(true);
    setAuthFeedback(null);
    try {
      await session.register(payload);
    } catch (error) {
      setAuthFeedback({ type: 'error', ...classifyAccountError(error, 'register') });
    } finally {
      setAuthBusy(false);
    }
  };

  const handleLogout = async () => {
    setAuthBusy(true);
    setAuthFeedback(null);
    try {
      await session.logout();
    } catch (error) {
      refreshExpiredSession(error);
      setAuthFeedback({ type: 'error', ...classifyAccountError(error, 'logout') });
    } finally {
      setAuthBusy(false);
      // The central session remains authoritative even when the local session
      // has already expired or its logout request fails.
      if (runtimeConfig.ssoEnabled) {
        window.location.assign(`/sso/logout?rd=${encodeURIComponent(`${window.location.origin}/sso/`)}`);
      }
    }
  };

  const submitProfile = async (event) => {
    event.preventDefault();
    setProfileBusy(true);
    setProfileFeedback(null);
    try {
      await session.updateProfile({
        ...profileForm,
        preferred_locale: uiLocaleToAccountLocale(profileForm.preferred_locale),
      });
      setLocale(profileForm.preferred_locale);
      setProfileFeedback({ type: 'success', messageKey: 'account.profile.saved' });
    } catch (error) {
      refreshExpiredSession(error);
      setProfileFeedback({ type: 'error', ...classifyAccountError(error, 'profile') });
    } finally {
      setProfileBusy(false);
    }
  };

  const submitActivity = async (event) => {
    event.preventDefault();
    setActivityFeedback(null);
    if (!activityForm.spot) {
      setActivityFeedback({ type: 'error', messageKey: 'account.error.chooseSpot' });
      return;
    }
    if (activityForm.action === 'review' && !activityForm.rating && !activityForm.review_text.trim()) {
      setActivityFeedback({ type: 'error', messageKey: 'account.error.reviewRequired' });
      return;
    }
    setActivityBusy(true);
    try {
      const payload = {
        spot: Number(activityForm.spot),
        action: activityForm.action,
      };
      if (activityForm.action === 'review') {
        if (activityForm.rating) payload.rating = Number(activityForm.rating);
        payload.review_text = activityForm.review_text.trim();
      }
      const created = await createActivity(payload);
      setRecords((current) => ({ ...current, activities: [created, ...current.activities] }));
      setActivityForm((current) => ({ ...current, review_text: '' }));
      setActivityFeedback({ type: 'success', messageKey: 'account.activity.saved' });
    } catch (error) {
      refreshExpiredSession(error);
      setActivityFeedback({ type: 'error', ...classifyAccountError(error, 'activity') });
    } finally {
      setActivityBusy(false);
    }
  };

  const submitEco = async (event) => {
    event.preventDefault();
    setEcoBusy(true);
    setEcoFeedback(null);
    try {
      const payload = {
        action_type: ecoForm.action_type,
        note: ecoForm.note.trim(),
        evidence_url: ecoForm.evidence_url.trim(),
        occurred_on: ecoForm.occurred_on,
      };
      if (ecoForm.spot) payload.spot = Number(ecoForm.spot);
      const created = await createEcoAction(payload);
      setRecords((current) => ({ ...current, ecoActions: [created, ...current.ecoActions] }));
      setEcoForm((current) => ({ ...current, note: '', evidence_url: '' }));
      setEcoFeedback({ type: 'success', messageKey: 'account.eco.submitted' });
    } catch (error) {
      refreshExpiredSession(error);
      setEcoFeedback({ type: 'error', ...classifyAccountError(error, 'eco') });
    } finally {
      setEcoBusy(false);
    }
  };

  const submitMemory = async (event) => {
    event.preventDefault();
    setMemoryFeedback(null);
    if (!memoryForm.spot) {
      setMemoryFeedback({ type: 'error', messageKey: 'account.error.chooseSpot' });
      return;
    }
    const takenAt = new Date(memoryForm.taken_at);
    if (!Number.isFinite(takenAt.getTime()) || takenAt.getTime() > Date.now()) {
      setMemoryFeedback({ type: 'error', messageKey: 'account.memory.error.time' });
      return;
    }
    setMemoryBusy('create');
    try {
      const created = await createTripMemory({
        spot: Number(memoryForm.spot),
        photo_url: memoryForm.photo_url.trim(),
        taken_at: takenAt.toISOString(),
        estimated_location: memoryForm.estimated_location.trim(),
      });
      setRecords((current) => ({ ...current, memories: [created, ...current.memories] }));
      setMemoryForm((current) => ({
        ...current,
        photo_url: '',
        taken_at: dateTimeLocalValue(),
        estimated_location: '',
      }));
      setMemoryFeedback({ type: 'success', messageKey: 'account.memory.created' });
    } catch (error) {
      refreshExpiredSession(error);
      setMemoryFeedback({ type: 'error', ...classifyAccountError(error, 'memory') });
    } finally {
      setMemoryBusy(null);
    }
  };

  const beginMemoryEdit = (memory) => {
    setEditingMemoryId(memory.id);
    setEditingMemoryForm({
      spot: String(memory.spot),
      photo_url: memory.photo_url,
      taken_at: dateTimeLocalValue(memory.taken_at),
      estimated_location: memory.estimated_location,
    });
    setMemoryFeedback(null);
    setConfirmingMemoryDelete(null);
  };

  const saveMemoryEdit = async (event, id) => {
    event.preventDefault();
    const takenAt = new Date(editingMemoryForm?.taken_at);
    if (!editingMemoryForm?.spot || !Number.isFinite(takenAt.getTime()) || takenAt.getTime() > Date.now()) {
      setMemoryFeedback({ type: 'error', messageKey: 'account.memory.error.time' });
      return;
    }
    setMemoryBusy(`edit-${id}`);
    setMemoryFeedback(null);
    try {
      const updated = await updateTripMemory(id, {
        spot: Number(editingMemoryForm.spot),
        photo_url: editingMemoryForm.photo_url.trim(),
        taken_at: takenAt.toISOString(),
        estimated_location: editingMemoryForm.estimated_location.trim(),
      });
      setRecords((current) => ({
        ...current,
        memories: current.memories.map((item) => (item.id === updated.id ? updated : item)),
      }));
      setEditingMemoryId(null);
      setEditingMemoryForm(null);
      setMemoryFeedback({ type: 'success', messageKey: 'account.memory.updated' });
    } catch (error) {
      refreshExpiredSession(error);
      setMemoryFeedback({ type: 'error', ...classifyAccountError(error, 'memory') });
    } finally {
      setMemoryBusy(null);
    }
  };

  const removeMemory = async (id) => {
    setMemoryBusy(`delete-${id}`);
    setMemoryFeedback(null);
    try {
      await deleteTripMemory(id);
      setRecords((current) => ({
        ...current,
        memories: current.memories.filter((item) => item.id !== id),
      }));
      setConfirmingMemoryDelete(null);
      setMemoryFeedback({ type: 'success', messageKey: 'account.memory.deleted' });
    } catch (error) {
      refreshExpiredSession(error);
      setMemoryFeedback({ type: 'error', ...classifyAccountError(error, 'memory') });
    } finally {
      setMemoryBusy(null);
    }
  };

  const submitPassword = async (event) => {
    event.preventDefault();
    setPasswordFeedback(null);
    if (passwordForm.new_password !== passwordForm.confirm) {
      setPasswordFeedback({ type: 'error', messageKey: 'account.error.passwordMismatch' });
      return;
    }
    setPasswordBusy(true);
    try {
      await changeAccountPassword({
        current_password: passwordForm.current_password,
        new_password: passwordForm.new_password,
      });
      setPasswordFeedback({ type: 'success', messageKey: 'account.password.changed' });
    } catch (error) {
      refreshExpiredSession(error);
      setPasswordFeedback({ type: 'error', ...classifyAccountError(error, 'password') });
    } finally {
      setPasswordForm({ current_password: '', new_password: '', confirm: '' });
      setPasswordBusy(false);
    }
  };

  const submitDelete = async (event) => {
    event.preventDefault();
    setDeleteBusy(true);
    setDeleteFeedback(null);
    try {
      await session.removeAccount({ current_password: deleteForm.current_password });
      setAuthMode('register');
      setAuthFeedback({ type: 'success', messageKey: 'account.delete.completed' });
    } catch (error) {
      refreshExpiredSession(error);
      setDeleteFeedback({ type: 'error', ...classifyAccountError(error, 'delete') });
    } finally {
      setDeleteForm({ current_password: '', acknowledged: false });
      setDeleteBusy(false);
    }
  };

  if (session.status === 'idle' || session.status === 'loading') {
    return (
      <div className="profile-page account-page-state" role="status">
        <LoaderCircle className="account-spinner" size={24} aria-hidden="true" />
        <p>{t('account.session.loading')}</p>
      </div>
    );
  }

  if (session.status === 'error') {
    return (
      <div className="profile-page account-page-state" role="alert">
        <ShieldAlert size={24} aria-hidden="true" />
        <h1>{t('account.session.errorTitle')}</h1>
        <p>{t(session.error?.messageKey || 'account.error.network')}</p>
        <button type="button" onClick={() => session.ensureSession({ force: true })}>
          <RefreshCw size={16} aria-hidden="true" /> {t('common.retry')}
        </button>
      </div>
    );
  }

  if (session.status === 'guest') {
    if (runtimeConfig.ssoEnabled) {
      return (
        <div className="profile-page account-page-state" role="alert">
          <ShieldAlert size={24} aria-hidden="true" />
          <h1>{t('account.session.errorTitle')}</h1>
          <a href={`/sso/?rd=${encodeURIComponent(window.location.href)}`}>{t('common.retry')}</a>
        </div>
      );
    }
    return (
      <div className="profile-page account-profile-page">
        <header className="account-hero">
          <span className="account-live-label"><Database size={14} aria-hidden="true" /> {t('account.eyebrow.guest')}</span>
          <h1>{t('account.guest.title')}</h1>
          <p>{t('account.guest.description')}</p>
        </header>
        <GuestAccount
          mode={authMode}
          setMode={setAuthMode}
          onLogin={handleLogin}
          onRegister={handleRegister}
          busy={authBusy}
          feedback={authFeedback}
          locale={locale}
          t={t}
        />
      </div>
    );
  }

  return (
    <div className="profile-page account-profile-page">
      <header className="account-hero is-authenticated">
        <div>
          <span className="account-live-label"><ShieldCheck size={14} aria-hidden="true" /> {t('account.eyebrow.authenticated')}</span>
          <h1>{t('account.member.title', { username: session.user.username })}</h1>
          <p>{t('account.member.description')}</p>
          <small>{t('account.member.since', { date: formatDate(session.user.date_joined, intlLocale, t('common.noData')) })}</small>
        </div>
        <button type="button" className="account-secondary-button" onClick={handleLogout} disabled={authBusy}>
          <LogOut size={16} aria-hidden="true" /> {t('account.auth.logout')}
        </button>
      </header>
      <Feedback feedback={authFeedback} t={t} />

      <section className="account-section" aria-labelledby="account-profile-heading">
        <div className="account-section-heading">
          <div>
            <span>{t('account.eyebrow.profile')}</span>
            <h2 id="account-profile-heading">{t('account.profile.title')}</h2>
            <p>{t('account.profile.description')}</p>
          </div>
          <UserRound size={26} aria-hidden="true" />
        </div>
        <form className="account-form account-form-grid" onSubmit={submitProfile}>
          <label className="account-field" htmlFor="profile-username">
            <span>{t('account.field.username')}</span>
            <input id="profile-username" value={session.user.username} readOnly aria-readonly="true" />
          </label>
          <label className="account-field" htmlFor="profile-email">
            <span>{t('account.field.email')}</span>
            <input id="profile-email" type="email" autoComplete="email" maxLength="254" value={profileForm.email} onChange={(event) => setProfileForm({ ...profileForm, email: event.target.value })} readOnly={runtimeConfig.ssoEnabled} aria-readonly={runtimeConfig.ssoEnabled || undefined} />
          </label>
          <label className="account-field" htmlFor="profile-first-name">
            <span>{t('account.field.firstName')}</span>
            <input id="profile-first-name" autoComplete="given-name" maxLength="150" value={profileForm.first_name} onChange={(event) => setProfileForm({ ...profileForm, first_name: event.target.value })} />
          </label>
          <label className="account-field" htmlFor="profile-last-name">
            <span>{t('account.field.lastName')}</span>
            <input id="profile-last-name" autoComplete="family-name" maxLength="150" value={profileForm.last_name} onChange={(event) => setProfileForm({ ...profileForm, last_name: event.target.value })} />
          </label>
          <label className="account-field" htmlFor="profile-persona">
            <span>{t('account.field.persona')}</span>
            <select id="profile-persona" value={profileForm.persona_type} onChange={(event) => setProfileForm({ ...profileForm, persona_type: event.target.value })}>
              {PERSONA_TYPES.map((persona) => <option key={persona || 'none'} value={persona}>{t(`account.persona.${persona || 'none'}`)}</option>)}
            </select>
          </label>
          <label className="account-field" htmlFor="profile-locale">
            <span>{t('account.field.locale')}</span>
            <select id="profile-locale" value={profileForm.preferred_locale} onChange={(event) => setProfileForm({ ...profileForm, preferred_locale: event.target.value })}>
              {['ko', 'en', 'ja', 'zh'].map((value) => <option key={value} value={value}>{t(`locale.${value}`)}</option>)}
            </select>
          </label>
          <label className="account-field" htmlFor="profile-region">
            <span>{t('account.field.homeRegion')}</span>
            <input id="profile-region" autoComplete="address-level1" maxLength="100" value={profileForm.home_region} onChange={(event) => setProfileForm({ ...profileForm, home_region: event.target.value })} />
          </label>
          <label className="account-field" htmlFor="profile-mood">
            <span>{t('account.field.mood')}</span>
            <input id="profile-mood" maxLength="50" value={profileForm.mood_state} onChange={(event) => setProfileForm({ ...profileForm, mood_state: event.target.value })} />
          </label>
          <div className="account-form-actions">
            <Feedback feedback={profileFeedback} t={t} />
            <button className="account-primary-button" type="submit" disabled={profileBusy}>
              {profileBusy ? <LoaderCircle className="account-spinner" size={17} aria-hidden="true" /> : <ShieldCheck size={17} aria-hidden="true" />}
              {profileBusy ? t('common.loading') : t('account.profile.save')}
            </button>
          </div>
        </form>
      </section>

      <section className="account-section" aria-labelledby="account-activity-heading">
        <div className="account-section-heading">
          <div>
            <span>{t('account.eyebrow.activity')}</span>
            <h2 id="account-activity-heading">{t('account.activity.title')}</h2>
            <p>{t('account.activity.description')}</p>
          </div>
          <MapPin size={26} aria-hidden="true" />
        </div>
        <form className="account-form account-inline-form" onSubmit={submitActivity}>
          <SpotSelect id="activity-spot" value={activityForm.spot} onChange={(event) => setActivityForm({ ...activityForm, spot: event.target.value })} spots={apiSpots} label={t('account.field.spot')} t={t} />
          <label className="account-field" htmlFor="activity-kind">
            <span>{t('account.field.activityKind')}</span>
            <select id="activity-kind" value={activityForm.action} onChange={(event) => setActivityForm({ ...activityForm, action: event.target.value })}>
              <option value="visit">{t('account.activity.visit')}</option>
              <option value="review">{t('account.activity.review')}</option>
            </select>
          </label>
          {activityForm.action === 'review' ? (
            <>
              <label className="account-field" htmlFor="activity-rating">
                <span>{t('account.field.rating')}</span>
                <select id="activity-rating" value={activityForm.rating} onChange={(event) => setActivityForm({ ...activityForm, rating: event.target.value })}>
                  <option value="">{t('account.rating.noRating')}</option>
                  {[5, 4, 3, 2, 1].map((rating) => <option key={rating} value={rating}>{t('account.rating.value', { rating })}</option>)}
                </select>
              </label>
              <label className="account-field is-wide" htmlFor="activity-review">
                <span>{t('account.field.review')}</span>
                <textarea id="activity-review" rows="3" maxLength="2000" value={activityForm.review_text} onChange={(event) => setActivityForm({ ...activityForm, review_text: event.target.value })} />
              </label>
            </>
          ) : null}
          <div className="account-form-actions">
            <Feedback feedback={activityFeedback} t={t} />
            <button className="account-primary-button" type="submit" disabled={activityBusy || apiSpots.length === 0}>
              {activityBusy ? <LoaderCircle className="account-spinner" size={17} aria-hidden="true" /> : <MapPin size={17} aria-hidden="true" />}
              {activityBusy ? t('common.loading') : t('account.activity.submit')}
            </button>
          </div>
        </form>
        {apiSpots.length === 0 ? <p className="account-data-note" role="status">{['idle', 'loading'].includes(spotStatus) ? t('account.spot.loading') : t('account.spot.unavailable')}</p> : null}

        {records.status === 'loading' ? <p className="account-data-note" role="status"><LoaderCircle className="account-spinner" size={16} aria-hidden="true" /> {t('account.records.loading')}</p> : null}
        {records.status === 'error' ? (
          <div className="account-data-note is-error" role="alert">
            <span>{t(records.error?.messageKey || 'account.error.response')}</span>
            <button type="button" onClick={loadRecords}><RefreshCw size={15} aria-hidden="true" /> {t('common.retry')}</button>
          </div>
        ) : null}

        {records.status === 'ready' ? (
          <>
            <div className="account-record-columns">
              <div>
                <h3>{t('account.visits.title')}</h3>
                {visits.length === 0 ? <EmptyState title={t('account.visits.empty')} description={t('account.visits.emptyDescription')} /> : (
                  <ul className="account-record-list">
                    {visits.map((visit) => (
                      <li key={visit.id}>
                        <MapPin size={17} aria-hidden="true" />
                        <div><strong>{visit.spot_detail?.name || t('account.spot.unknown')}</strong><span>{formatDate(visit.created_at, intlLocale, t('common.noData'))}</span></div>
                        <span className="account-state is-self">{t('account.activity.selfReported')}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <h3>{t('account.reviews.title')}</h3>
                {reviews.length === 0 ? <EmptyState title={t('account.reviews.empty')} description={t('account.reviews.emptyDescription')} /> : (
                  <ul className="account-record-list">
                    {reviews.map((review) => (
                      <li key={review.id} className="is-review">
                        <div>
                          <strong>{review.spot_detail?.name || t('account.spot.unknown')}</strong>
                          <span>{review.rating ? t('account.rating.value', { rating: review.rating }) : t('account.rating.noRating')} · {formatDate(review.created_at, intlLocale, t('common.noData'))}</span>
                          {review.review_text ? <p>{review.review_text}</p> : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            {legacyActivities.length > 0 ? (
              <div className="account-legacy-records" role="status">
                <h3>{t('account.activity.legacyTitle')}</h3>
                <p>{t('account.activity.legacyDescription')}</p>
                <ul className="account-record-list">
                  {legacyActivities.map((item) => (
                    <li key={item.id}>
                      <Database size={17} aria-hidden="true" />
                      <div><strong>{item.spot_detail?.name || t('account.spot.unknown')}</strong><span>{formatDate(item.created_at, intlLocale, t('common.noData'))}</span></div>
                      <span className="account-state is-legacy">{t('account.activity.legacyReadOnly')}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </>
        ) : null}
      </section>

      <section className="account-section" aria-labelledby="account-memory-heading">
        <div className="account-section-heading">
          <div>
            <span>{t('account.eyebrow.memory')}</span>
            <h2 id="account-memory-heading">{t('account.memory.title')}</h2>
            <p>{t('account.memory.description')}</p>
          </div>
          <Images size={26} aria-hidden="true" />
        </div>
        <form className="account-form account-inline-form" onSubmit={submitMemory}>
          <SpotSelect id="memory-spot" value={memoryForm.spot} onChange={(event) => setMemoryForm({ ...memoryForm, spot: event.target.value })} spots={apiSpots} label={t('account.field.spot')} t={t} />
          <label className="account-field" htmlFor="memory-taken-at">
            <span>{t('account.memory.takenAt')}</span>
            <input id="memory-taken-at" type="datetime-local" max={dateTimeLocalValue()} value={memoryForm.taken_at} onChange={(event) => setMemoryForm({ ...memoryForm, taken_at: event.target.value })} required />
          </label>
          <label className="account-field" htmlFor="memory-location">
            <span>{t('account.memory.location')}</span>
            <input id="memory-location" maxLength="200" value={memoryForm.estimated_location} onChange={(event) => setMemoryForm({ ...memoryForm, estimated_location: event.target.value })} />
          </label>
          <label className="account-field" htmlFor="memory-photo">
            <span>{t('account.memory.photoUrl')}</span>
            <input id="memory-photo" type="url" inputMode="url" placeholder="https://" maxLength="200" value={memoryForm.photo_url} onChange={(event) => setMemoryForm({ ...memoryForm, photo_url: event.target.value })} aria-describedby="memory-photo-help" />
            <small id="memory-photo-help">{t('account.memory.photoHelp')}</small>
          </label>
          <div className="account-form-actions">
            <Feedback feedback={memoryFeedback} t={t} />
            <button className="account-primary-button" type="submit" disabled={memoryBusy !== null || apiSpots.length === 0}>
              {memoryBusy === 'create' ? <LoaderCircle className="account-spinner" size={17} aria-hidden="true" /> : <Images size={17} aria-hidden="true" />}
              {memoryBusy === 'create' ? t('common.loading') : t('account.memory.create')}
            </button>
          </div>
        </form>
        <p className="account-security-note"><ShieldCheck size={15} aria-hidden="true" /> {t('account.memory.privateNotice')}</p>
        {records.status === 'ready' && records.memories.length === 0 ? <EmptyState title={t('account.memory.empty')} description={t('account.memory.emptyDescription')} /> : null}
        {records.memories.length > 0 ? (
          <ul className="account-memory-list">
            {records.memories.map((memory) => (
              <li key={memory.id}>
                {editingMemoryId === memory.id ? (
                  <form className="account-form account-memory-edit" onSubmit={(event) => saveMemoryEdit(event, memory.id)}>
                    <SpotSelect id={`memory-edit-spot-${memory.id}`} value={editingMemoryForm?.spot || ''} onChange={(event) => setEditingMemoryForm({ ...editingMemoryForm, spot: event.target.value })} spots={apiSpots} label={t('account.field.spot')} t={t} />
                    <label className="account-field" htmlFor={`memory-edit-time-${memory.id}`}>
                      <span>{t('account.memory.takenAt')}</span>
                      <input id={`memory-edit-time-${memory.id}`} type="datetime-local" max={dateTimeLocalValue()} value={editingMemoryForm?.taken_at || ''} onChange={(event) => setEditingMemoryForm({ ...editingMemoryForm, taken_at: event.target.value })} required />
                    </label>
                    <label className="account-field" htmlFor={`memory-edit-location-${memory.id}`}>
                      <span>{t('account.memory.location')}</span>
                      <input id={`memory-edit-location-${memory.id}`} maxLength="200" value={editingMemoryForm?.estimated_location || ''} onChange={(event) => setEditingMemoryForm({ ...editingMemoryForm, estimated_location: event.target.value })} />
                    </label>
                    <label className="account-field" htmlFor={`memory-edit-photo-${memory.id}`}>
                      <span>{t('account.memory.photoUrl')}</span>
                      <input id={`memory-edit-photo-${memory.id}`} type="url" inputMode="url" maxLength="200" value={editingMemoryForm?.photo_url || ''} onChange={(event) => setEditingMemoryForm({ ...editingMemoryForm, photo_url: event.target.value })} />
                    </label>
                    <div className="account-memory-actions">
                      <button type="submit" disabled={memoryBusy !== null}>{t('account.memory.save')}</button>
                      <button type="button" onClick={() => { setEditingMemoryId(null); setEditingMemoryForm(null); }} disabled={memoryBusy !== null}><X size={14} aria-hidden="true" /> {t('account.memory.cancel')}</button>
                    </div>
                  </form>
                ) : (
                  <>
                    <div className="account-memory-icon"><Images size={20} aria-hidden="true" /></div>
                    <div className="account-memory-copy">
                      <strong>{memory.spot_detail.name}</strong>
                      <span>{formatDate(memory.taken_at, intlLocale, t('common.noData'))}</span>
                      <p>{memory.estimated_location || t('account.memory.noLocation')}</p>
                      {memory.photo_url ? <a href={memory.photo_url} target="_blank" rel="noreferrer">{t('account.memory.photoOpen')}</a> : <small>{t('account.memory.noPhoto')}</small>}
                    </div>
                    <div className="account-memory-actions">
                      <button type="button" onClick={() => beginMemoryEdit(memory)} disabled={memoryBusy !== null}><Pencil size={14} aria-hidden="true" /> {t('account.memory.edit')}</button>
                      {confirmingMemoryDelete !== memory.id ? (
                        <button type="button" className="is-delete" onClick={() => setConfirmingMemoryDelete(memory.id)} disabled={memoryBusy !== null}><Trash2 size={14} aria-hidden="true" /> {t('account.memory.delete')}</button>
                      ) : (
                        <>
                          <button type="button" className="is-delete" onClick={() => removeMemory(memory.id)} disabled={memoryBusy !== null}>{t('account.memory.confirmDelete')}</button>
                          <button type="button" onClick={() => setConfirmingMemoryDelete(null)} disabled={memoryBusy !== null}>{t('account.memory.cancel')}</button>
                        </>
                      )}
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="account-section" aria-labelledby="account-passport-heading">
        <div className="account-section-heading">
          <div>
            <span>{t('account.eyebrow.passport')}</span>
            <h2 id="account-passport-heading">{t('account.passport.title')}</h2>
            <p>{t('account.passport.description')}</p>
          </div>
          <BadgeCheck size={26} aria-hidden="true" />
        </div>
        {records.status === 'ready' && records.passports.length === 0 ? <EmptyState title={t('account.passport.empty')} description={t('account.passport.emptyDescription')} /> : null}
        {records.passports.length > 0 ? (
          <ul className="account-card-grid">
            {records.passports.map((passport) => (
              <li key={passport.id}>
                <BadgeCheck size={23} aria-hidden="true" />
                <strong>{passport.spot?.name || t('account.spot.unknown')}</strong>
                <span>{formatDate(passport.verified_at, intlLocale, t('common.noData'))}</span>
                <span className="account-state is-verified">{t('verification.verified')}</span>
                <small>{t(`account.passport.method.${passport.verification_method || 'operator'}`)}</small>
                {passport.evidence_url ? <a href={passport.evidence_url} target="_blank" rel="noreferrer">{t('account.passport.evidence')}</a> : null}
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="account-section" aria-labelledby="account-eco-heading">
        <div className="account-section-heading">
          <div>
            <span>{t('account.eyebrow.eco')}</span>
            <h2 id="account-eco-heading">{t('account.eco.title')}</h2>
            <p>{t('account.eco.description')}</p>
          </div>
          <Leaf size={26} aria-hidden="true" />
        </div>
        <form className="account-form account-inline-form" onSubmit={submitEco}>
          <SpotSelect id="eco-spot" value={ecoForm.spot} onChange={(event) => setEcoForm({ ...ecoForm, spot: event.target.value })} spots={apiSpots} label={t('account.field.spot')} optional t={t} />
          <label className="account-field" htmlFor="eco-kind">
            <span>{t('account.field.ecoKind')}</span>
            <select id="eco-kind" value={ecoForm.action_type} onChange={(event) => setEcoForm({ ...ecoForm, action_type: event.target.value })}>
              {ECO_ACTION_TYPES.map((kind) => <option key={kind} value={kind}>{t(`account.eco.kind.${kind}`)}</option>)}
            </select>
          </label>
          <label className="account-field" htmlFor="eco-date">
            <span>{t('account.field.occurredOn')}</span>
            <input id="eco-date" type="date" max={todayValue()} value={ecoForm.occurred_on} onChange={(event) => setEcoForm({ ...ecoForm, occurred_on: event.target.value })} required />
          </label>
          <label className="account-field" htmlFor="eco-evidence">
            <span>{t('account.field.evidenceUrl')}</span>
            <input id="eco-evidence" type="url" inputMode="url" placeholder="https://" maxLength="500" value={ecoForm.evidence_url} onChange={(event) => setEcoForm({ ...ecoForm, evidence_url: event.target.value })} aria-describedby="eco-evidence-help" />
            <small id="eco-evidence-help">{t('account.eco.evidenceHelp')}</small>
          </label>
          <label className="account-field is-wide" htmlFor="eco-note">
            <span>{t('account.field.note')}</span>
            <textarea id="eco-note" rows="3" maxLength="500" value={ecoForm.note} onChange={(event) => setEcoForm({ ...ecoForm, note: event.target.value })} />
          </label>
          <div className="account-form-actions">
            <Feedback feedback={ecoFeedback} t={t} />
            <button className="account-primary-button" type="submit" disabled={ecoBusy}>
              {ecoBusy ? <LoaderCircle className="account-spinner" size={17} aria-hidden="true" /> : <Leaf size={17} aria-hidden="true" />}
              {ecoBusy ? t('common.loading') : t('account.eco.submit')}
            </button>
          </div>
        </form>
        <p className="account-security-note"><ShieldAlert size={15} aria-hidden="true" /> {t('account.eco.pendingNotice')}</p>
        {records.status === 'ready' && records.ecoActions.length === 0 ? <EmptyState title={t('account.eco.empty')} description={t('account.eco.emptyDescription')} /> : null}
        {records.ecoActions.length > 0 ? (
          <ul className="account-card-grid">
            {records.ecoActions.map((action) => {
              const state = safeVerificationState(action.state);
              return (
                <li key={action.id}>
                  <Leaf size={22} aria-hidden="true" />
                  <strong>{t(`account.eco.kind.${action.action_type}`)}</strong>
                  <span>{action.spot_detail?.name || t('account.spot.noSpot')}</span>
                  <span className={`account-state is-${state}`}>{t(`verification.${state}`)}</span>
                  <small>{formatDate(action.occurred_on, intlLocale, t('common.noData'))}</small>
                  {action.note ? <p>{action.note}</p> : null}
                  {action.evidence_url ? <a href={action.evidence_url} target="_blank" rel="noreferrer">{t('account.eco.evidence')}</a> : null}
                </li>
              );
            })}
          </ul>
        ) : null}
      </section>

      {!runtimeConfig.ssoEnabled ? <section className="account-section account-security-section" aria-labelledby="account-security-heading">
        <div className="account-section-heading">
          <div>
            <span>{t('account.eyebrow.security')}</span>
            <h2 id="account-security-heading">{t('account.security.title')}</h2>
            <p>{t('account.security.description')}</p>
          </div>
          <KeyRound size={26} aria-hidden="true" />
        </div>
        <div className="account-security-grid">
          <form className="account-form" onSubmit={submitPassword}>
            <h3>{t('account.password.title')}</h3>
            <label className="account-field" htmlFor="password-current">
              <span>{t('account.field.currentPassword')}</span>
              <input id="password-current" type="password" autoComplete="current-password" value={passwordForm.current_password} onChange={(event) => setPasswordForm({ ...passwordForm, current_password: event.target.value })} required />
            </label>
            <label className="account-field" htmlFor="password-new">
              <span>{t('account.field.newPassword')}</span>
              <input id="password-new" type="password" autoComplete="new-password" value={passwordForm.new_password} onChange={(event) => setPasswordForm({ ...passwordForm, new_password: event.target.value })} aria-describedby="password-policy-help" required />
              <small id="password-policy-help">{t('account.password.help')}</small>
            </label>
            <label className="account-field" htmlFor="password-confirm">
              <span>{t('account.field.confirmPassword')}</span>
              <input id="password-confirm" type="password" autoComplete="new-password" value={passwordForm.confirm} onChange={(event) => setPasswordForm({ ...passwordForm, confirm: event.target.value })} required />
            </label>
            <Feedback feedback={passwordFeedback} t={t} />
            <button className="account-primary-button" type="submit" disabled={passwordBusy}>
              {passwordBusy ? <LoaderCircle className="account-spinner" size={17} aria-hidden="true" /> : <KeyRound size={17} aria-hidden="true" />}
              {passwordBusy ? t('common.loading') : t('account.password.submit')}
            </button>
          </form>

          <form className="account-form account-danger-zone" onSubmit={submitDelete}>
            <h3>{t('account.delete.title')}</h3>
            <p>{t('account.delete.description')}</p>
            <label className="account-field" htmlFor="delete-password">
              <span>{t('account.field.currentPassword')}</span>
              <input id="delete-password" type="password" autoComplete="current-password" value={deleteForm.current_password} onChange={(event) => setDeleteForm({ ...deleteForm, current_password: event.target.value })} required />
            </label>
            <label className="account-check" htmlFor="delete-acknowledge">
              <input id="delete-acknowledge" type="checkbox" checked={deleteForm.acknowledged} onChange={(event) => setDeleteForm({ ...deleteForm, acknowledged: event.target.checked })} required />
              <span>{t('account.delete.acknowledge')}</span>
            </label>
            <Feedback feedback={deleteFeedback} t={t} />
            <button className="account-danger-button" type="submit" disabled={deleteBusy || !deleteForm.acknowledged}>
              {deleteBusy ? <LoaderCircle className="account-spinner" size={17} aria-hidden="true" /> : <Trash2 size={17} aria-hidden="true" />}
              {deleteBusy ? t('common.loading') : t('account.delete.submit')}
            </button>
          </form>
        </div>
      </section> : null}

      <aside className="account-draft-link">
        <CalendarDays size={22} aria-hidden="true" />
        <div><strong>{t('account.itinerary.title')}</strong><p>{t('account.itinerary.description')}</p></div>
        <Link to="/concierge">{t('account.itinerary.open')}</Link>
      </aside>
    </div>
  );
}

export default ProfilePage;
