import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Thermometer, Wind, Waves, Activity, MapPin } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import api from '../services/api';
import './SpotDetailPage.css';

const SpotDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [spot, setSpot] = useState(null);
  const [loading, setLoading] = useState(true);

  // Dummy chart data since we don't have historical forecast API endpoints yet
  const chartData = [
    { name: '월', score: 65 },
    { name: '화', score: 72 },
    { name: '수', score: 85 },
    { name: '목', score: 90 },
    { name: '금', score: 88 },
    { name: '토', score: 95 },
    { name: '일', score: 92 },
  ];

  useEffect(() => {
    const fetchSpot = async () => {
      try {
        const response = await api.get(`/spots/${id}/`);
        setSpot(response.data);
      } catch (error) {
        console.error('Failed to fetch spot detail', error);
      } finally {
        setLoading(false);
      }
    };
    fetchSpot();
  }, [id]);

  if (loading) {
    return <div className="flex-center" style={{ height: '100vh' }}>데이터를 불러오는 중입니다...</div>;
  }

  if (!spot) {
    return <div className="flex-center" style={{ height: '100vh' }}>해당 스팟을 찾을 수 없습니다.</div>;
  }

  return (
    <div className="spot-detail-page">
      <div className="detail-header-image" style={{ backgroundImage: `url(${spot.image_url})` }}>
        <button className="back-btn glass-panel" onClick={() => navigate(-1)}>
          <ArrowLeft size={24} />
        </button>
        <div className="header-overlay">
          <span className="badge">{spot.type === 'sea' ? '바다' : spot.type}</span>
          <h1>{spot.name}</h1>
          <p><MapPin size={16} style={{display:'inline', marginRight:4}} />{spot.address}</p>
        </div>
      </div>

      <div className="detail-content">
        <section className="detail-section glass-panel">
          <h2>현재 물놀이 조건</h2>
          <div className="condition-grid">
            <div className="condition-card">
              <Thermometer size={28} color="var(--color-coral)" />
              <div className="cond-info">
                <span>수온</span>
                <strong>24.5°C</strong>
              </div>
            </div>
            <div className="condition-card">
              <Wind size={28} color="var(--color-aqua)" />
              <div className="cond-info">
                <span>풍속</span>
                <strong>3.2 m/s</strong>
              </div>
            </div>
            <div className="condition-card">
              <Waves size={28} color="var(--color-wave)" />
              <div className="cond-info">
                <span>파고</span>
                <strong>0.8 m</strong>
              </div>
            </div>
            <div className="condition-card">
              <Activity size={28} color="var(--color-nature)" />
              <div className="cond-info">
                <span>수질</span>
                <strong>좋음 (1등급)</strong>
              </div>
            </div>
          </div>
        </section>

        <section className="detail-section glass-panel">
          <h2>주간 퐁당 지수 예측</h2>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={chartData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorScore" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-wave)" stopOpacity={0.8}/>
                    <stop offset="95%" stopColor="var(--color-wave)" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <XAxis dataKey="name" stroke="var(--color-text-secondary)" />
                <YAxis stroke="var(--color-text-secondary)" />
                <Tooltip contentStyle={{ borderRadius: '8px', border: 'none', background: 'var(--color-surface)' }} />
                <Area type="monotone" dataKey="score" stroke="var(--color-wave)" fillOpacity={1} fill="url(#colorScore)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="detail-section glass-panel">
          <h2>스팟 정보</h2>
          <p className="description">{spot.description}</p>
          <div className="tags-container">
            {spot.tags && spot.tags.map((tag, i) => (
              <span key={i} className="tag-chip">{tag}</span>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
};

export default SpotDetailPage;
