export function currentPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('이 기기에서 위치를 쓸 수 없습니다.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        }),
      (error) => {
        if (error && error.code === 1) {
          reject(new Error('위치 권한이 필요합니다.'));
          return;
        }
        reject(new Error('위치를 확인하지 못했습니다.'));
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 30000 }
    );
  });
}
