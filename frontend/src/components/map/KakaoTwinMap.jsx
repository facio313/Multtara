import React, { useEffect, useRef } from 'react'
import { loadKakaoMaps } from '../../utils/kakaoMap'
import { spotPopupHtml } from '../../utils/mapPopup'
import { scoreTone } from '../../utils/scoreColor'
import { tempColor } from '../../utils/twin'

function markerHtml(spot, layer) {
  if (layer === 'temp') {
    const temp = spot.condition?.water_temp
    const label = temp == null || Number.isNaN(Number(temp)) ? '-' : Math.round(Number(temp))
    return `<div class="temp-marker-inner" style="background:${tempColor(temp)}">${label}</div>`
  }
  const score = spot.water_index ?? '-'
  return `<div class="score-marker-inner is-${scoreTone(spot.water_index)}">${score}</div>`
}

const KakaoTwinMap = ({ spots, layer, onError }) => {
  const containerRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    const overlays = []
    let infoWindow = null
    let map = null

    loadKakaoMaps()
      .then((kakao) => {
        if (cancelled || !containerRef.current) return
        const center = new kakao.maps.LatLng(36.5, 127.8)
        map = new kakao.maps.Map(containerRef.current, { center, level: 13 })
        infoWindow = new kakao.maps.InfoWindow({ zIndex: 20, removable: true })

        spots.forEach((spot) => {
          if (spot.lat == null || spot.lng == null) return
          const position = new kakao.maps.LatLng(spot.lat, spot.lng)
          const content = document.createElement('div')
          content.className = 'kakao-pin score-marker'
          content.innerHTML = markerHtml(spot, layer)
          const overlay = new kakao.maps.CustomOverlay({
            position,
            content,
            xAnchor: 0.5,
            yAnchor: 0.5,
            zIndex: 4,
          })
          overlay.setMap(map)
          overlays.push(overlay)
          content.addEventListener('click', () => {
            infoWindow.setContent(spotPopupHtml(spot))
            infoWindow.setPosition(position)
            infoWindow.open(map)
          })
        })

        kakao.maps.event.addListener(map, 'click', () => infoWindow.close())
        setTimeout(() => map.relayout(), 0)
      })
      .catch((error) => {
        if (!cancelled) onError?.(error)
      })

    return () => {
      cancelled = true
      overlays.forEach((overlay) => overlay.setMap(null))
      infoWindow?.close()
    }
  }, [spots, layer, onError])

  return <div ref={containerRef} className="kakao-map" />
}

export default KakaoTwinMap
