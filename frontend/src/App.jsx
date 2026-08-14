import React from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Navigation from './components/layout/Navigation';
import ForecastPage from './pages/ForecastPage';
import HomePage from './pages/HomePage';
import LivecamPage from './pages/LivecamPage';
import MapPage from './pages/MapPage';
import ProfilePage from './pages/ProfilePage';
import SpotDetailPage from './pages/SpotDetailPage';
import './App.css';

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
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
