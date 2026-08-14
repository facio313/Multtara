import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Calendar, Video, Activity, Droplets, Wind, Waves, Thermometer } from 'lucide-react';
import api from '../services/api';
import './HomePage.css';

const HomePage = () => {
  const [spots, setSpots] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSpots = async () => {
      try {
        const response = await api.get('/spots/');
        let results = [];
        if (response.data && Array.isArray(response.data.results)) {
          results = response.data.results;
        } else if (Array.isArray(response.data)) {
          results = response.data;
        }
        setSpots(results.slice(0, 3));
      } catch (error) {
        console.error('Failed to fetch spots', error);
      } finally {
        setLoading(false);
      }
    };
    fetchSpots();
  }, []);

  return (
    <div className="home-dashboard">
      <section className="dashboard-section hero-section glass-panel">
        <h1 className="text-gradient">PongDang</h1>
        <p>오늘, 가장 완벽한 물 여행지를 만나보세요.</p>
      </section>

      <div className="dashboard-grid">
        {/* Top Spots */}
        <section className="dashboard-card glass-panel">
          <h2 className="flex-center" style={{ justifyContent: 'flex-start', gap: '8px' }}>
            <MapPin size={24} color="var(--color-wave)" /> 추천 스팟
          </h2>
          {loading ? (
            <p style={{ color: 'var(--color-text-secondary)' }}>데이터를 불러오는 중입니다...</p>
          ) : (
            <ul className="spot-list">
              {spots.length > 0 ? (
                spots.map((spot, index) => (
                  <Link to={`/spot/${spot.id}`} key={spot.id || index} style={{ textDecoration: 'none', color: 'inherit' }}>
                    <li className="spot-list-item">
                      <div className="spot-info">
                        <strong>{index + 1}. {spot.name}</strong>
                        <span className="spot-region">{spot.region}</span>
                      </div>
                      <span className="spot-badge">{spot.type === 'sea' ? '바다' : spot.type === 'valley' ? '계곡' : spot.type}</span>
                    </li>
                  </Link>
                ))
              ) : (
                <li style={{ color: 'var(--color-text-secondary)' }}>스팟 데이터가 없습니다.</li>
              )}
            </ul>
          )}
        </section>

        {/* Forecast Summary */}
        <section className="dashboard-card glass-panel">
          <h2 className="flex-center" style={{ justifyContent: 'flex-start', gap: '8px' }}>
            <Calendar size={24} color="var(--color-aqua)" /> 이번 주 물놀이 지수
          </h2>
          <div className="forecast-summary flex-center">
            <div className="forecast-day">
              <span className="day">금</span>
              <div className="bar" style={{ height: '60%', background: 'var(--color-aqua)' }}></div>
              <span className="score">85</span>
            </div>
            <div className="forecast-day">
              <span className="day">토</span>
              <div className="bar" style={{ height: '90%', background: 'var(--gradient-water)' }}></div>
              <span className="score" style={{ color: 'var(--color-wave)', fontWeight: 'bold' }}>98</span>
            </div>
            <div className="forecast-day">
              <span className="day">일</span>
              <div className="bar" style={{ height: '40%', background: 'var(--color-sunset)' }}></div>
              <span className="score">65</span>
            </div>
          </div>
        </section>

        {/* Livecam Picks */}
        <section className="dashboard-card glass-panel livecam-card">
          <h2 className="flex-center" style={{ justifyContent: 'flex-start', gap: '8px' }}>
            <Video size={24} color="var(--color-coral)" /> 실시간 라이브캠
          </h2>
          <div className="livecam-grid">
            <div className="livecam-feed">
              <img src="https://picsum.photos/seed/cam1/400/300" alt="cam1" />
              <span className="cam-label">해운대</span>
            </div>
            <div className="livecam-feed">
              <img src="https://picsum.photos/seed/cam2/400/300" alt="cam2" />
              <span className="cam-label">협재 해변</span>
            </div>
            <div className="livecam-feed">
              <img src="https://picsum.photos/seed/cam3/400/300" alt="cam3" />
              <span className="cam-label">가평 계곡</span>
            </div>
            <div className="livecam-feed">
              <img src="https://picsum.photos/seed/cam4/400/300" alt="cam4" />
              <span className="cam-label">경포대</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default HomePage;
