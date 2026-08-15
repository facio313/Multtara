import { spotTypeLabel } from './spotType'
import { formatMinutes } from './twin'

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function spotPopupHtml(spot) {
  const facts = (spot.twin_facts || [])
    .map(
      (fact) =>
        `<li><span>${escapeHtml(fact.label)}</span><em>${escapeHtml(fact.value)}</em></li>`
    )
    .join('')
  const next = spot.tide?.next
  const tide = next
    ? `<p class="twin-next">${escapeHtml(next.label)} ${escapeHtml(next.time)}${
        next.is_tomorrow ? ' (내일)' : ''
      } · ${escapeHtml(formatMinutes(next.minutes))}</p>`
    : ''
  const safety = spot.safety?.label ? ` · ${escapeHtml(spot.safety.label)}` : ''
  return `
    <div class="map-popup">
      <strong>${escapeHtml(spot.name)}</strong>
      <p>${escapeHtml(spot.region)} · ${escapeHtml(spotTypeLabel(spot.type))}${safety}</p>
      ${facts ? `<ul class="twin-facts">${facts}</ul>` : ''}
      ${tide}
      <a href="/spot/${encodeURIComponent(spot.id)}">자세히</a>
    </div>
  `
}
