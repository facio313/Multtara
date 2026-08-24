import { createElement } from 'react';

export const BONIFACIO_RETURN_HREF = 'https://bonifacio.work/';
export const BONIFACIO_RETURN_LABEL = '← Bonifacio';

export function BonifacioReturnLink() {
  return createElement(
    'a',
    { className: 'bonifacio-return-link', href: BONIFACIO_RETURN_HREF },
    BONIFACIO_RETURN_LABEL,
  );
}
