"""Runtime attribution context store interfaces and in-memory implementation.

Voice Identity owns attribution context persistence and lifecycle.
Concierge consumes safe records only.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Protocol

from .contracts import RuntimeAttributionRecord


def _parse_utc_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value or "").strip())
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class VoiceIdentityAttributionContextStore(Protocol):
    """Voice Identity-owned attribution context store contract."""

    def upsert(self, record: RuntimeAttributionRecord) -> RuntimeAttributionRecord:
        """Insert or replace one runtime attribution record."""

    def resolve_current_speaker(
        self,
        *,
        conversation_id: str | None,
        device_id: str | None,
        satellite_id: str | None,
        room_id: str | None,
        now: datetime,
    ) -> RuntimeAttributionRecord | None:
        """Resolve the freshest attribution record for current speaker context."""

    def invalidate_by_conversation(self, conversation_id: str) -> None:
        """Remove records bound to one conversation."""

    def invalidate_by_device_satellite(self, *, device_id: str | None, satellite_id: str | None) -> None:
        """Remove records bound to a device/satellite pair."""

    def sweep_expired(self, *, now: datetime) -> int:
        """Remove expired records and return number removed."""


class InMemoryAttributionContextStore:
    """Short-lived in-memory runtime attribution context store."""

    def __init__(self, *, fallback_window_seconds: int = 10) -> None:
        self._records: dict[str, RuntimeAttributionRecord] = {}
        self._fallback_window_seconds = max(0, fallback_window_seconds)

    def upsert(self, record: RuntimeAttributionRecord) -> RuntimeAttributionRecord:
        normalized = record.normalized()
        self._records[normalized.attribution_id] = normalized
        return normalized

    def resolve_current_speaker(
        self,
        *,
        conversation_id: str | None,
        device_id: str | None,
        satellite_id: str | None,
        room_id: str | None,
        now: datetime,
    ) -> RuntimeAttributionRecord | None:
        self.sweep_expired(now=now)
        now_utc = now.astimezone(timezone.utc)

        def _eligible(record: RuntimeAttributionRecord) -> bool:
            state = record.decision.state
            if state in {"unknown", "unavailable"}:
                return False
            return _parse_utc_iso(record.expires_at_utc) > now_utc

        candidates = [record for record in self._records.values() if _eligible(record)]
        if not candidates:
            return None

        if conversation_id:
            matched = [
                record
                for record in candidates
                if (record.binding.conversation_id or "") == conversation_id
                and (room_id is None or record.binding.room_id in {None, room_id})
            ]
            if matched:
                return self._with_runtime_freshness(self._latest(matched), now=now_utc)

        # Fallback path is intentionally narrow and short-lived.
        fallback = [
            record
            for record in candidates
            if (record.binding.device_id or "") == (device_id or "")
            and (record.binding.satellite_id or "") == (satellite_id or "")
            and (room_id is None or record.binding.room_id in {None, room_id})
            and (now_utc - _parse_utc_iso(record.issued_at_utc)).total_seconds() <= self._fallback_window_seconds
        ]
        if fallback:
            return self._with_runtime_freshness(self._latest(fallback), now=now_utc)

        return None

    def invalidate_by_conversation(self, conversation_id: str) -> None:
        conversation = str(conversation_id or "").strip()
        if not conversation:
            return
        to_remove = [
            record_id
            for record_id, record in self._records.items()
            if (record.binding.conversation_id or "") == conversation
        ]
        for record_id in to_remove:
            self._records.pop(record_id, None)

    def invalidate_by_device_satellite(self, *, device_id: str | None, satellite_id: str | None) -> None:
        device = str(device_id or "")
        satellite = str(satellite_id or "")
        to_remove = [
            record_id
            for record_id, record in self._records.items()
            if (record.binding.device_id or "") == device
            and (record.binding.satellite_id or "") == satellite
        ]
        for record_id in to_remove:
            self._records.pop(record_id, None)

    def sweep_expired(self, *, now: datetime) -> int:
        now_utc = now.astimezone(timezone.utc)
        to_remove = [
            record_id
            for record_id, record in self._records.items()
            if _parse_utc_iso(record.expires_at_utc) <= now_utc
        ]
        for record_id in to_remove:
            self._records.pop(record_id, None)
        return len(to_remove)

    @staticmethod
    def _latest(records: list[RuntimeAttributionRecord]) -> RuntimeAttributionRecord:
        return max(records, key=lambda item: _parse_utc_iso(item.issued_at_utc))

    def with_freshness(self, record: RuntimeAttributionRecord, *, age_ms: int, freshness_class: str) -> RuntimeAttributionRecord:
        """Return a copy with updated freshness data for projection workflows."""
        return replace(
            record,
            freshness=replace(
                record.freshness,
                attribution_age_ms=int(age_ms),
                freshness_class=str(freshness_class),
            ),
        )

    def _with_runtime_freshness(self, record: RuntimeAttributionRecord, *, now: datetime) -> RuntimeAttributionRecord:
        issued_at = _parse_utc_iso(record.issued_at_utc)
        expires_at = _parse_utc_iso(record.expires_at_utc)

        age_ms = max(0, int((now - issued_at).total_seconds() * 1000))
        ttl_ms = max(0, int((expires_at - issued_at).total_seconds() * 1000))
        remaining_ms = int((expires_at - now).total_seconds() * 1000)

        if remaining_ms <= 0:
            freshness_class = "expired"
        elif ttl_ms <= 0:
            freshness_class = "not_applicable"
        elif remaining_ms <= min(5000, ttl_ms // 2 if ttl_ms > 1 else 1):
            freshness_class = "stale"
        else:
            freshness_class = "fresh"

        return self.with_freshness(record, age_ms=age_ms, freshness_class=freshness_class)
