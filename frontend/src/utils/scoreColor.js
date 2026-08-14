export function scoreTone(score) {
  if (score == null || Number.isNaN(Number(score))) return 'ok';
  const value = Number(score);
  if (value >= 80) return 'good';
  if (value >= 60) return 'ok';
  return 'poor';
}

export function scoreLabel(score) {
  const tone = scoreTone(score);
  if (score == null) return '정보 없음';
  if (tone === 'good') return '좋음';
  if (tone === 'ok') return '무난';
  return '주의';
}
