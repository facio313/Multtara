import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import './Navigation.css';

const navItems = [
  { path: '/', label: '홈', icon: '🏠' },
  { path: '/map', label: '지도', icon: '📍' },
  { path: '/forecast', label: '예보', icon: '📅' },
  { path: '/livecam', label: '물멍', icon: '📹' },
  { path: '/profile', label: 'MY', icon: '👤' },
];

const Navigation = () => {
  const location = useLocation();

  if (location.pathname === '/onboarding') return null;

  return (
    <header className="app-navigation">
      <div className="nav-container">
        {/* Desktop Logo */}
        <Link to="/" className="nav-brand text-gradient">
          <span className="brand-icon">🌊</span> 퐁당
        </Link>

        {/* Navigation Links */}
        <nav className="nav-menu">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`nav-item ${isActive ? 'active' : ''}`}
              >
                <span className="nav-icon">{item.icon}</span>
                <span className="nav-label">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
};

export default Navigation;
