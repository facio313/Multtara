"""Next high/low tide from a stored daily schedule."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
KIND_LABELS = {"low": "간조", "high": "만조"}


def parse_clock(value: Any) -> time | None:
    text = str(value or "").strip().replace("시", ":").replace("분", "")
    if " " in text:
        text = text.split(" ")[-1]
    if len(text) >= 5 and text[2] == ":":
        try:
            return time(int(text[:2]), int(text[3:5]))
        except ValueError:
            return None
    if len(text) == 4 and text.isdigit():
        try:
            return time(int(text[:2]), int(text[2:]))
        except ValueError:
            return None
    return None


def _events(schedule: dict) -> list[tuple[str, str, time]]:
    events: list[tuple[str, str, time]] = []
    for kind, key in (("low", "low_tide"), ("high", "high_tide")):
        for raw in schedule.get(key) or []:
            clock = parse_clock(raw)
            if clock is None:
                continue
            label = clock.strftime("%H:%M")
            events.append((kind, label, clock))
    events.sort(key=lambda item: (item[2].hour, item[2].minute, item[0]))
    return events


def next_tide(schedule: dict | None, now: datetime | None = None) -> dict | None:
    events = _events(schedule or {})
    if not events:
        return None

    current = now or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    else:
        current = current.astimezone(KST)

    today = current.date()
    candidates: list[tuple[datetime, str, str]] = []
    for kind, label, clock in events:
        stamp = datetime.combine(today, clock, tzinfo=KST)
        if stamp <= current:
            stamp = datetime.combine(today + timedelta(days=1), clock, tzinfo=KST)
        candidates.append((stamp, kind, label))

    stamp, kind, label = min(candidates, key=lambda item: item[0])
    minutes = max(0, int((stamp - current).total_seconds() // 60))
    return {
        "kind": kind,
        "label": KIND_LABELS[kind],
        "time": stamp.strftime("%H:%M"),
        "minutes": minutes,
        "is_tomorrow": stamp.date() != today,
        "mudflat_window": kind == "low" and minutes <= 180,
    }


def summarize_tide(schedule: dict | None, now: datetime | None = None) -> dict:
    payload = schedule or {}
    return {
        "low_tide": list(payload.get("low_tide") or []),
        "high_tide": list(payload.get("high_tide") or []),
        "next": next_tide(payload, now),
    }
