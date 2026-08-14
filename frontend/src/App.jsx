import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Navigation from './components/layout/Navigation';
import HomePage from './pages/HomePage';
import MapPage from './pages/MapPage';
import SpotDetailPage from './pages/SpotDetailPage';
import ForecastPage from './pages/ForecastPage';
import LivecamPage from './pages/LivecamPage';
import ProfilePage from './pages/ProfilePage';
import './App.css';

// Placeholder Page for Onboarding
const PageContainer = ({ title, emoji }) => (
  <div style={{ padding: '2rem', textAlign: 'center', height: '100vh', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
    <div style={{ fontSize: '4rem', marginBottom: '1rem' }}>{emoji}</div>
    <h1 className="text-gradient" style={{ fontSize: '2rem' }}>{title}</h1>
    <p style={{ color: 'var(--color-text-secondary)' }}>이 페이지는 기획서 내용에 따라 추후 구현됩니다.</p>
  </div>
);

const OnboardingPage = () => <PageContainer title="페르소나 분석" emoji="🤖" />;

function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <Navigation />
        <main className="app-main">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/forecast" element={<ForecastPage />} />
            <Route path="/livecam" element={<LivecamPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/spot/:id" element={<SpotDetailPage />} />
            <Route path="/onboarding" element={<OnboardingPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
