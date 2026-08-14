import { useEffect, useState } from 'react';

export default function useGeolocation() {
  const [position, setPosition] = useState(null);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (result) => {
        setPosition({
          lat: result.coords.latitude,
          lng: result.coords.longitude,
        });
      },
      () => setPosition(null),
      { enableHighAccuracy: false, timeout: 4000, maximumAge: 300000 }
    );
  }, []);

  return position;
}
