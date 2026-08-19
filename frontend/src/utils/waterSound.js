function noiseBuffer(ctx, seconds = 2) {
  const length = Math.floor(ctx.sampleRate * seconds);
  const buffer = ctx.createBuffer(1, length, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  let last = 0;
  for (let i = 0; i < length; i += 1) {
    const white = Math.random() * 2 - 1;
    last = (last + 0.02 * white) / 1.02;
    data[i] = last * 3.5;
  }
  return buffer;
}

export function startWaterSound(soundType, score = 60) {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return null;
  const ctx = new AudioContextClass();
  const master = ctx.createGain();
  const intensity = Math.min(1, Math.max(0.15, Number(score) / 100));
  master.gain.value = 0.18 + intensity * 0.22;
  master.connect(ctx.destination);

  const source = ctx.createBufferSource();
  source.buffer = noiseBuffer(ctx, 3);
  source.loop = true;

  const filter = ctx.createBiquadFilter();
  if (soundType === 'wave') {
    filter.type = 'lowpass';
    filter.frequency.value = 380 + intensity * 420;
  } else if (soundType === 'waterfall') {
    filter.type = 'highpass';
    filter.frequency.value = 900;
  } else if (soundType === 'valley') {
    filter.type = 'bandpass';
    filter.frequency.value = 700;
  } else if (soundType === 'tidal') {
    filter.type = 'lowpass';
    filter.frequency.value = 220;
  } else {
    filter.type = 'lowpass';
    filter.frequency.value = 1400;
  }

  const lfo = ctx.createOscillator();
  const lfoGain = ctx.createGain();
  lfo.frequency.value = soundType === 'wave' ? 0.12 : 0.25;
  lfoGain.gain.value = 80 + intensity * 60;
  lfo.connect(lfoGain);
  lfoGain.connect(filter.frequency);

  source.connect(filter);
  filter.connect(master);
  source.start();
  lfo.start();

  return {
    stop() {
      try {
        source.stop();
        lfo.stop();
        ctx.close();
      } catch {
        // Already closed.
      }
    },
  };
}
