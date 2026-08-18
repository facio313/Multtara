import {
  lazy,
  Suspense,
  useEffect,
  useRef,
} from 'react';
import { BrowserRouter, Link, Route, Routes, useLocation } from 'react-router-dom';
import Navigation from './components/layout/Navigation';
import { useI18n } from './i18n';
import './App.css';

const HomePage = lazy(() => import('./pages/HomePage'));
const MapPage = lazy(() => import('./pages/MapPage'));
const SpotDetailPage = lazy(() => import('./pages/SpotDetailPage'));
const ForecastPage = lazy(() => import('./pages/ForecastPage'));
const LivecamPage = lazy(() => import('./pages/LivecamPage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage'));
const ConciergePage = lazy(() => import('./pages/ConciergePage'));

function RouteEffects() {
  const { pathname } = useLocation();
  const { t } = useI18n();
  const previousPath = useRef(null);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
    if (previousPath.current !== null && previousPath.current !== pathname) {
      document.getElementById('main-content')?.focus({ preventScroll: true });
    }
    previousPath.current = pathname;
  }, [pathname]);

  useEffect(() => {
    let titleKey = 'notFound.title';
    if (pathname === '/') titleKey = 'nav.home';
    else if (pathname === '/map') titleKey = 'nav.map';
    else if (pathname === '/forecast') titleKey = 'nav.forecast';
    else if (['/livecam', '/livecams'].includes(pathname)) titleKey = 'nav.livecam';
    else if (['/profile', '/me'].includes(pathname)) titleKey = 'nav.profile';
    else if (pathname === '/onboarding') titleKey = 'profile.cta.findTaste';
    else if (pathname === '/concierge') titleKey = 'nav.concierge';
    else if (/^\/spots?\//.test(pathname)) titleKey = 'common.details';
    document.title = `${t(titleKey)} | PongDang`;
  }, [pathname, t]);

  return null;
}

function NotFoundPage() {
  const { t } = useI18n();

  return (
    <div className="page-state">
      <div>
        <p>{t('notFound.kicker')}</p>
        <h1>{t('notFound.title')}</h1>
        <Link to="/">{t('notFound.home')}</Link>
      </div>
    </div>
  );
}

function RouteFallback() {
  const { t } = useI18n();

  return (
    <div className="page-state" role="status" aria-live="polite">
      <div>
        <p>{t('app.routeLoading')}</p>
      </div>
    </div>
  );
}

function App() {
  const { t } = useI18n();

  return (
    <BrowserRouter>
      <div className="app-shell">
        <a className="skip-link" href="#main-content">{t('app.skip')}</a>
        <RouteEffects />
        <Navigation />
        <main className="app-main" id="main-content" tabIndex="-1">
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/map" element={<MapPage />} />
              <Route path="/forecast" element={<ForecastPage />} />
              <Route path="/livecam" element={<LivecamPage />} />
              <Route path="/livecams" element={<LivecamPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/me" element={<ProfilePage />} />
              <Route path="/spot/:id" element={<SpotDetailPage />} />
              <Route path="/spots/:id" element={<SpotDetailPage />} />
              <Route path="/onboarding" element={<OnboardingPage />} />
              <Route path="/concierge" element={<ConciergePage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
