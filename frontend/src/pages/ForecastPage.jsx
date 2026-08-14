import React, { useState } from 'react';
import { Calendar, Sun, CloudRain, Wind } from 'lucide-react';
import classNames from 'classnames';
import './ForecastPage.css';

const ForecastPage = () => {
  const [selectedRegion, setSelectedRegion] = useState('전국');
  
  // Dummy forecast map data
  const regions = ['전국', '수도권', '강원', '충청', '전라', '경상', '제주'];
  
  const generateDummyForecast = () => {
    return Array.from({ length: 7 }).map((_, i) => {
      const date = new Date();
      date.setDate(date.getDate() + i);
      const score = Math.floor(Math.random() * 50) + 50; // 50~100
      
      let condition = 'good';
      if (score < 60) condition = 'bad';
      else if (score < 80) condition = 'normal';

      return {
        id: i,
        day: ['일', '월', '화', '수', '목', '금', '토'][date.getDay()],
        date: `${date.getMonth() + 1}/${date.getDate()}`,
        score,
        condition
      };
    });
  };

  const weeklyData = generateDummyForecast();

  return (
    <div className="forecast-page">
      <div className="page-header glass-panel">
        <h1><Calendar className="inline-icon" /> 7일 퐁당 예보</h1>
        <p>빅데이터가 예측하는 일주일 치 물놀이 지수입니다.</p>
        
        <div className="region-selector">
          {regions.map(r => (
            <button 
              key={r}
              className={classNames('region-btn', { active: selectedRegion === r })}
              onClick={() => setSelectedRegion(r)}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <div className="forecast-content">
        <section className="forecast-timeline glass-panel">
          <h2>{selectedRegion} 주간 예보 요약</h2>
          <div className="timeline-cards">
            {weeklyData.map(day => (
              <div key={day.id} className={classNames('day-card', day.condition)}>
                <div className="day-header">
                  <span className="day-name">{day.day}</span>
                  <span className="day-date">{day.date}</span>
                </div>
                <div className="day-score">
                  <span className="score-val">{day.score}</span>
                  <span className="score-label">점</span>
                </div>
                <div className="day-icon">
                  {day.condition === 'good' ? <Sun size={24} /> : 
                   day.condition === 'normal' ? <Wind size={24} /> : 
                   <CloudRain size={24} />}
                </div>
                <span className="status-text">
                  {day.condition === 'good' ? '물놀이 추천' : 
                   day.condition === 'normal' ? '무난함' : '주의 요망'}
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="forecast-details glass-panel">
          <h2>예측 분석 리포트</h2>
          <div className="report-content">
            <p className="report-text">
              이번 주 <strong>{selectedRegion}</strong> 지역은 주말에 기온이 크게 오르고 수온이 안정화되면서 
              물놀이에 매우 적합한 조건(평균 지수 85점 이상)이 형성될 것으로 예측됩니다.
              다만 목요일 오전에는 일시적인 강수와 높은 파고가 예상되므로 해상 활동에 주의하시기 바랍니다.
            </p>
            <div className="report-factors">
              <div className="factor">
                <span className="f-label">평균 기온 예측</span>
                <div className="f-bar-bg"><div className="f-bar-fill" style={{width: '70%', background: 'var(--color-sunset)'}}></div></div>
                <span className="f-val">26~32°C</span>
              </div>
              <div className="factor">
                <span className="f-label">평균 파고 예측</span>
                <div className="f-bar-bg"><div className="f-bar-fill" style={{width: '30%', background: 'var(--color-wave)'}}></div></div>
                <span className="f-val">0.5~1.2m</span>
              </div>
              <div className="factor">
                <span className="f-label">수질 위험도</span>
                <div className="f-bar-bg"><div className="f-bar-fill" style={{width: '15%', background: 'var(--color-nature)'}}></div></div>
                <span className="f-val">안전</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default ForecastPage;
