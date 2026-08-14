import React, { useState } from 'react';
import { Video, Search, Maximize2 } from 'lucide-react';
import './LivecamPage.css';

const MOCK_CAMS = [
  { id: 1, name: '해운대 해수욕장 1캠', region: '부산', url: 'https://picsum.photos/seed/cam1/800/600', tags: ['바다', '파도'] },
  { id: 2, name: '광안대교 야경', region: '부산', url: 'https://picsum.photos/seed/cam2/800/600', tags: ['바다', '야경'] },
  { id: 3, name: '제주 협재 해변', region: '제주', url: 'https://picsum.photos/seed/cam3/800/600', tags: ['바다', '맑음'] },
  { id: 4, name: '강릉 경포대', region: '강원', url: 'https://picsum.photos/seed/cam4/800/600', tags: ['바다', '일출'] },
  { id: 5, name: '가평 명지계곡', region: '경기', url: 'https://picsum.photos/seed/cam5/800/600', tags: ['계곡', '수량'] },
  { id: 6, name: '양양 서피비치', region: '강원', url: 'https://picsum.photos/seed/cam6/800/600', tags: ['서핑', '파도'] },
];

const LivecamPage = () => {
  const [filter, setFilter] = useState('전체');
  
  const filteredCams = filter === '전체' ? MOCK_CAMS : MOCK_CAMS.filter(c => c.region === filter || c.tags.includes(filter));

  return (
    <div className="livecam-page">
      <div className="page-header glass-panel">
        <h1><Video className="inline-icon" /> 실시간 물멍 라이브캠</h1>
        <p>전국 주요 물놀이 스팟의 실시간 상황을 확인하세요.</p>
        
        <div className="filter-chips">
          {['전체', '바다', '계곡', '제주', '강원', '부산'].map(f => (
            <button 
              key={f} 
              className={`chip ${filter === f ? 'active' : ''}`}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="cam-grid">
        {filteredCams.map(cam => (
          <div key={cam.id} className="cam-card glass-panel">
            <div className="cam-video-wrapper">
              <img src={cam.url} alt={cam.name} className="cam-video" />
              <div className="cam-overlay">
                <span className="live-badge">LIVE</span>
                <button className="fullscreen-btn"><Maximize2 size={18} /></button>
              </div>
            </div>
            <div className="cam-info">
              <h3>{cam.name}</h3>
              <p>{cam.region}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default LivecamPage;
