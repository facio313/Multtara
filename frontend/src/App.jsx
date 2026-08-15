import { useEffect } from 'react';
import { BrowserRouter, Link, Route, Routes, useLocation } from 'react-router-dom';
import Navigation from './components/layout/Navigation';
import HomePage from './pages/HomePage';
import MapPage from './pages/MapPage';
import SpotDetailPage from './pages/SpotDetailPage';
import ForecastPage from './pages/ForecastPage';
import LivecamPage from './pages/LivecamPage';
import ProfilePage from './pages/ProfilePage';
import OnboardingPage from './pages/OnboardingPage';
import ConciergePage from './pages/ConciergePage';
import './App.css';

function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, [pathname]);

  return null;
}

function NotFoundPage() {
  return (
    <div className="page-state">
      <div>
        <p>404 · 물길을 잠시 놓쳤어요.</p>
        <h1>찾는 페이지가 없어요.</h1>
        <Link to="/">퐁당 홈으로 돌아가기</Link>
      </div>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <a className="skip-link" href="#main-content">본문으로 건너뛰기</a>
        <ScrollToTop />
        <Navigation />
        <main className="app-main" id="main-content" tabIndex="-1">
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
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
