import React from 'react';
import { User, Award, CheckCircle, Clock } from 'lucide-react';
import './ProfilePage.css';

const ProfilePage = () => {
  return (
    <div className="profile-page">
      <div className="profile-header glass-panel">
        <div className="profile-avatar">
          <User size={40} color="var(--color-ocean)" />
        </div>
        <div className="profile-info">
          <h1>물놀이 마스터</h1>
          <p>모험가 페르소나 (서핑/액티비티 선호)</p>
        </div>
      </div>

      <div className="profile-stats">
        <div className="stat-card glass-panel">
          <span className="stat-num text-gradient">12</span>
          <span className="stat-label">방문한 스팟</span>
        </div>
        <div className="stat-card glass-panel">
          <span className="stat-num text-gradient">8</span>
          <span className="stat-label">획득 뱃지</span>
        </div>
        <div className="stat-card glass-panel">
          <span className="stat-num text-gradient">24</span>
          <span className="stat-label">남긴 리뷰</span>
        </div>
      </div>

      <div className="passport-section glass-panel">
        <div className="section-title">
          <Award className="inline-icon" color="var(--color-wave)" />
          <h2>나의 워터 패스포트</h2>
        </div>
        
        <div className="badge-grid">
          <div className="badge-item earned">
            <div className="badge-icon">🏄</div>
            <span className="badge-name">파도 타기 명인</span>
          </div>
          <div className="badge-item earned">
            <div className="badge-icon">♻️</div>
            <span className="badge-name">플로깅 용사</span>
          </div>
          <div className="badge-item earned">
            <div className="badge-icon">🏕️</div>
            <span className="badge-name">계곡 마스터</span>
          </div>
          <div className="badge-item locked">
            <div className="badge-icon">♨️</div>
            <span className="badge-name">온천 매니아</span>
          </div>
          <div className="badge-item locked">
            <div className="badge-icon">📸</div>
            <span className="badge-name">물멍 사진가</span>
          </div>
        </div>
      </div>

      <div className="activity-section glass-panel">
        <div className="section-title">
          <Clock className="inline-icon" color="var(--color-sunset)" />
          <h2>최근 활동</h2>
        </div>
        <ul className="activity-list">
          <li className="activity-item">
            <div className="activity-icon"><CheckCircle size={18} color="var(--color-nature)" /></div>
            <div className="activity-content">
              <strong>해운대 해수욕장</strong> 방문 스탬프 획득
              <span className="activity-time">2일 전</span>
            </div>
          </li>
          <li className="activity-item">
            <div className="activity-icon"><CheckCircle size={18} color="var(--color-nature)" /></div>
            <div className="activity-content">
              <strong>송정 해수욕장</strong> 서핑 리뷰 작성
              <span className="activity-time">1주일 전</span>
            </div>
          </li>
          <li className="activity-item">
            <div className="activity-icon"><CheckCircle size={18} color="var(--color-nature)" /></div>
            <div className="activity-content">
              <strong>플로깅 용사</strong> 뱃지 획득
              <span className="activity-time">2주일 전</span>
            </div>
          </li>
        </ul>
      </div>
    </div>
  );
};

export default ProfilePage;
