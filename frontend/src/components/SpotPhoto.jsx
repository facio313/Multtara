import React, { useState } from 'react';
import { spotImage } from '../utils/spotImage';

const SpotPhoto = ({ spot, className, alt = '' }) => {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return <div className={`spot-photo-fallback ${className || ''}`} aria-hidden="true" />;
  }

  return (
    <img
      className={className}
      src={spotImage(spot)}
      alt={alt}
      onError={() => setFailed(true)}
    />
  );
};

export default SpotPhoto;
