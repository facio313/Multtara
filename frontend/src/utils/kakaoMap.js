let pending = null

export function kakaoMapKey() {
  return String(import.meta.env.VITE_KAKAO_MAP_KEY || '').trim()
}

export function loadKakaoMaps() {
  const key = kakaoMapKey()
  if (!key) {
    return Promise.reject(new Error('missing kakao key'))
  }
  if (window.kakao?.maps) {
    return new Promise((resolve) => {
      window.kakao.maps.load(() => resolve(window.kakao))
    })
  }
  if (pending) return pending

  pending = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&autoload=false`
    script.async = true
    script.onload = () => {
      if (!window.kakao?.maps) {
        pending = null
        reject(new Error('kakao sdk missing'))
        return
      }
      window.kakao.maps.load(() => resolve(window.kakao))
    }
    script.onerror = () => {
      pending = null
      reject(new Error('kakao sdk failed'))
    }
    document.head.appendChild(script)
  })
  return pending
}
