import React from 'react';
import { NavLink } from 'react-router-dom';
import { House, Map, CalendarDays, Video, User } from 'lucide-react';
import BrandMark from '../BrandMark';
import './Navigation.css';

const navItems = [
  { path: '/', label: '홈', icon: House },
  { path: '/map', label: '지도', icon: Map },
  { path: '/forecast', label: '예보', icon: CalendarDays },
  { path: '/livecam', label: '미리보기', icon: Video },
  { path: '/profile', label: '내 정보', icon: User },
];

const Navigation = () => {
  return (
    <header className="app-navigation">
      <div className="nav-container">
        <NavLink to="/" className="nav-brand">
          <BrandMark />
        </NavLink>
        <nav className="nav-menu">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
              >
                <Icon size={18} strokeWidth={1.75} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>
    </header>
  );
};

export default Navigation;
