import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  BONIFACIO_RETURN_HREF,
  BONIFACIO_RETURN_LABEL,
  BonifacioReturnLink,
} from './bonifacioReturn.js';

const appSource = readFileSync(new URL('../../App.jsx', import.meta.url), 'utf8');
const appStyles = readFileSync(new URL('../../App.css', import.meta.url), 'utf8');
const navigationSource = readFileSync(new URL('./Navigation.jsx', import.meta.url), 'utf8');
const navigationStyles = readFileSync(new URL('./Navigation.css', import.meta.url), 'utf8');

test('keeps the shared Bonifacio return-link contract', () => {
  assert.equal(BONIFACIO_RETURN_HREF, 'https://bonifacio.work/');
  assert.equal(BONIFACIO_RETURN_LABEL, '← Bonifacio');
  assert.equal(
    renderToStaticMarkup(BonifacioReturnLink()),
    '<a class="bonifacio-return-link" href="https://bonifacio.work/">← Bonifacio</a>',
  );
});

test('keeps the mobile return link in the shared shell outside the filtered navigation', () => {
  assert.match(
    appSource,
    /<div className="bonifacio-return-mobile">\s*<BonifacioReturnLink \/>\s*<\/div>\s*<Navigation \/>/,
  );
  assert.match(
    appStyles,
    /@media \(max-width: 720px\)[\s\S]*?\.bonifacio-return-mobile \{[\s\S]*?position: fixed;[\s\S]*?top: 0;[\s\S]*?display: flex;/,
  );
});

test('keeps desktop and onboarding return links in Navigation', () => {
  assert.match(
    navigationSource,
    /location\.pathname === '\/onboarding'[\s\S]*?app-navigation--return-only[\s\S]*?<BonifacioReturnLink \/>/,
  );
  assert.match(
    navigationSource,
    /<div className="nav-identity">[\s\S]*?<Link[\s\S]*?<BonifacioReturnLink \/>/,
  );
  assert.equal(navigationSource.match(/<BonifacioReturnLink \/>/g)?.length, 2);
  assert.match(
    navigationStyles,
    /@media \(max-width: 720px\)[\s\S]*?\.app-navigation--return-only \{\s*display: none;[\s\S]*?\.nav-identity,[\s\S]*?\.nav-brand \{\s*display: none;/,
  );
});
