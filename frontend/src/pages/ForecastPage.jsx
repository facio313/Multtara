import React, { useEffect, useState } from 'react';
import api from '../services/api';
import { scoreLabel, scoreTone } from '../utils/scoreColor';
import './ForecastPage.css';

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토'];
const REGIONS = ['전국', '부산', '강원', '제주', '경기', '충남', '인천', '경북', '전북', '충북'];

const ForecastPage = () => {
  const [selectedRegion, setSelectedRegion] = useState('전국');
  const [weeklyData, setWeeklyData] = useState([]);
  const [message, setMessage] = useState('');
  const [bestDate, setBestDate] = useState('');
  const [source, setSource] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const params = selectedRegion === '전국' ? {} : { region: selectedRegion };
        const response = await api.get('/spots/forecast-summary/', { params });
        const days = (response.data.days || []).map((row, index) => {
          const date = new Date(`${row.forecast_date}T00:00:00`);
          return {
            id: index,
            day: WEEKDAY[date.getDay()],
            date: `${date.getMonth() + 1}/${date.getDate()}`,
            score: row.predicted_index,
            forecastDate: row.forecast_date,
          };
        });
        setWeeklyData(days);
        setMessage(response.data.message || '');
        setBestDate(response.data.best_date || '');
        setSource(response.data.source || '');
      } catch (error) {
        console.error('Failed to load forecast', error);
        setWeeklyData([]);
        setMessage('예보를 불러오지 못했습니다.');
        setSource('');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [selectedRegion]);

  return (
    <div className="page forecast-page">
      <header className="page-head">
        <h1>7일 예보</h1>
        <p>
          {source === 'kma'
            ? '기상청 단기·중기예보로 계산한 값입니다.'
            : '저장된 컨디션으로 계산한 값입니다. 공공API를 갱신하면 기상청 예보가 반영됩니다.'}
        </p>
      </header>

      <div className="chip-row">
        {REGIONS.map((region) => (
          <button
            key={region}
            className={`chip ${selectedRegion === region ? 'active' : ''}`}
            onClick={() => setSelectedRegion(region)}
          >
            {region}
          </button>
        ))}
      </div>

      {message && <p className="week-lead">{message}</p>}

      {loading && <p className="empty">불러오는 중</p>}

      {!loading && weeklyData.length === 0 && (
        <p className="empty">이 지역의 예보가 없습니다.</p>
      )}

      <div className="forecast-table">
        {weeklyData.map((day) => (
          <div
            className={`forecast-row${day.forecastDate === bestDate ? ' is-best' : ''}`}
            key={day.id}
          >
            <span className="forecast-day">{day.day}</span>
            <span className="muted">{day.date}</span>
            <div className={`meter score is-${scoreTone(day.score)}`}>
              <span style={{ width: `${day.score}%` }} />
            </div>
            <span className={`score is-${scoreTone(day.score)}`}>{day.score}</span>
            <span className="muted">{scoreLabel(day.score)}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ForecastPage;
