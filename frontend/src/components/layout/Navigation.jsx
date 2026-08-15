import { CalendarDays, CircleUserRound, Compass, Droplets, Globe2, Radio, Sparkles } from 'lucide-react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import './Navigation.css';

const desktopNavItems = [
  { path: '/', label: '홈', icon: Droplets },
  { path: '/map', label: '워터맵', icon: Compass },
  { path: '/forecast', label: '7일 예보', icon: CalendarDays },
  { path: '/livecam', label: '워터뷰', icon: Radio },
];

const mobileNavItems = [
  { path: '/', label: '홈', icon: Droplets },
  { path: '/map', label: '지도', icon: Compass },
  { path: '/concierge', label: 'AI 추천', icon: Sparkles, featured: true },
  { path: '/livecam', label: '워터뷰', icon: Radio },
  { path: '/profile', label: 'MY', icon: CircleUserRound },
];

function Navigation() {
  const location = useLocation();

  if (location.pathname === '/onboarding') return null;

  return (
    <header className="app-navigation">
      <div className="nav-container">
        <Link to="/" className="nav-brand" aria-label="퐁당 홈">
          <span className="brand-mark"><Droplets size={19} /></span>
          <span>퐁당</span>
          <small>PONGDANG</small>
        </Link>

        <nav className="nav-menu nav-menu-desktop" aria-label="데스크톱 주요 메뉴">
          {desktopNavItems.map(({ path, label, icon: Icon }) => (
            <NavLink
              end={path === '/'}
              key={path}
              to={path}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              <Icon className="nav-icon" size={19} aria-hidden="true" />
              <span className="nav-label">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="nav-actions">
          <button className="locale-button" type="button" title="현재 한국어 · English, 日本語, 中文 준비 중">
            <Globe2 size={15} /> KO
          </button>
          <Link className="nav-cta" to="/concierge">
            <Sparkles size={15} /> AI에게 물어보기
          </Link>
        </div>

        <nav className="nav-menu nav-menu-mobile" aria-label="모바일 주요 메뉴">
          {mobileNavItems.map(({ path, label, icon: Icon, featured }) => (
            <NavLink
              end={path === '/'}
              key={path}
              to={path}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}${featured ? ' featured' : ''}`}
            >
              <span className="mobile-icon-wrap"><Icon className="nav-icon" size={19} aria-hidden="true" /></span>
              <span className="nav-label">{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}

export default Navigation;
