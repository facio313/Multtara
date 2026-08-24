import { CalendarDays, CircleUserRound, Compass, Droplets, Radio, Sparkles } from 'lucide-react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { useI18n } from '../../i18n';
import { BonifacioReturnLink } from './bonifacioReturn';
import LocaleSelector from './LocaleSelector';
import './Navigation.css';

const desktopNavItems = [
  { path: '/', labelKey: 'nav.home', icon: Droplets },
  { path: '/map', labelKey: 'nav.map', icon: Compass },
  { path: '/forecast', labelKey: 'nav.forecast', icon: CalendarDays },
  { path: '/livecam', labelKey: 'nav.livecam', icon: Radio },
];

const mobileNavItems = [
  { path: '/', labelKey: 'nav.home', icon: Droplets },
  { path: '/map', labelKey: 'nav.mapShort', icon: Compass },
  { path: '/concierge', labelKey: 'nav.concierge', icon: Sparkles, featured: true },
  { path: '/livecam', labelKey: 'nav.livecam', icon: Radio },
  { path: '/profile', labelKey: 'nav.profile', icon: CircleUserRound },
];

function Navigation() {
  const location = useLocation();
  const { t } = useI18n();

  if (location.pathname === '/onboarding') {
    return (
      <header className="app-navigation app-navigation--return-only">
        <div className="nav-container">
          <div className="nav-identity nav-identity--return-only">
            <BonifacioReturnLink />
          </div>
        </div>
      </header>
    );
  }

  return (
    <header className="app-navigation">
      <div className="nav-container">
        <div className="nav-identity">
          <Link to="/" className="nav-brand" aria-label={t('nav.brandHome')}>
            <span className="brand-mark"><Droplets size={19} /></span>
            <span>퐁당</span>
            <small>PONGDANG</small>
          </Link>
          <BonifacioReturnLink />
        </div>

        <nav className="nav-menu nav-menu-desktop" aria-label={t('nav.desktop')}>
          {desktopNavItems.map(({ path, labelKey, icon: Icon }) => (
            <NavLink
              end={path === '/'}
              key={path}
              to={path}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
            >
              <Icon className="nav-icon" size={19} aria-hidden="true" />
              <span className="nav-label">{t(labelKey)}</span>
            </NavLink>
          ))}
        </nav>

        <div className="nav-actions">
          <LocaleSelector />
          <Link className="nav-cta" to="/concierge">
            <Sparkles size={15} /> {t('nav.askAi')}
          </Link>
        </div>

        <LocaleSelector mobile />

        <nav className="nav-menu nav-menu-mobile" aria-label={t('nav.mobile')}>
          {mobileNavItems.map(({ path, labelKey, icon: Icon, featured }) => (
            <NavLink
              end={path === '/'}
              key={path}
              to={path}
              className={({ isActive }) => `nav-item${isActive ? ' active' : ''}${featured ? ' featured' : ''}`}
            >
              <span className="mobile-icon-wrap"><Icon className="nav-icon" size={19} aria-hidden="true" /></span>
              <span className="nav-label">{t(labelKey)}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}

export default Navigation;
