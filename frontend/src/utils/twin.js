export function tempColor(temp) {
  if (temp == null || Number.isNaN(Number(temp))) return '#a3a3a3';
  const value = Number(temp);
  if (value < 18) return '#2b6cb0';
  if (value < 22.5) return '#4c9adf';
  if (value < 26) return '#e07a3d';
  return '#d64545';
}

export function formatMinutes(minutes) {
  if (minutes == null || Number.isNaN(Number(minutes))) return '';
  const value = Math.max(0, Number(minutes));
  if (value < 60) return `${value}분 후`;
  const hours = Math.floor(value / 60);
  const rest = value % 60;
  if (rest === 0) return `${hours}시간 후`;
  return `${hours}시간 ${rest}분 후`;
}

export function safetyTone(level) {
  if (level === 'danger') return 'danger';
  if (level === 'caution') return 'caution';
  return 'safe';
}
