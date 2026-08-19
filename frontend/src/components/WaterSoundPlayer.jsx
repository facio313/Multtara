import React, { useEffect, useState } from 'react';
import { startWaterSound } from '../utils/waterSound';
import './WaterSoundPlayer.css';

const WaterSoundPlayer = ({ soundType, score, label, compact = false }) => {
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return undefined;
    const handle = startWaterSound(soundType, score);
    if (!handle) {
      setPlaying(false);
      return undefined;
    }
    return () => handle.stop();
  }, [playing, soundType, score]);

  return (
    <div className={`sound-player${compact ? ' is-compact' : ''}`}>
      <button
        type="button"
        className={`auth-submit ${playing ? 'is-playing' : ''}`}
        onClick={() => setPlaying((value) => !value)}
      >
        {playing ? '소리 끄기' : `${label || '물소리'} 듣기`}
      </button>
      {!compact && (
        <p className="muted">파고·풍속으로 예측한 백색소음입니다. 실제 녹음이 있으면 그 파일을 재생합니다.</p>
      )}
    </div>
  );
};

export default WaterSoundPlayer;
