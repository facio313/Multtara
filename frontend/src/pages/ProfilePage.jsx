import React from 'react';
import './ProfilePage.css';

const ProfilePage = () => {
  return (
    <div className="page profile-page">
      <header className="page-head">
        <h1>내 정보</h1>
        <p>로그인과 패스포트는 아직 없습니다.</p>
      </header>
      <p className="body-note">
        지금은 장소의 물 상태와 7일 지수를 보는 단계입니다.
      </p>
    </div>
  );
};

export default ProfilePage;
