from __future__ import annotations

from datetime import datetime, timedelta, timezone

from custom_components.voice_identity.attribution_context_store import InMemoryAttributionContextStore
from custom_components.voice_identity.contracts import (
    AttributionBinding,
    AttributionConfidence,
    AttributionDecision,
    AttributionDiagnostics,
    AttributionFreshness,
    AttributionIntegrity,
    AttributionSubject,
    RuntimeAttributionRecord,
)


def _record(
    *,
    attribution_id: str,
    issued_at: datetime,
    expires_after_seconds: int,
    conversation_id: str | None,
    device_id: str | None,
    satellite_id: str | None,
    room_id: str | None,
    person_id: str | None,
    state: str,
    confidence_band: str,
) -> RuntimeAttributionRecord:
    expires_at = issued_at + timedelta(seconds=expires_after_seconds)
    return RuntimeAttributionRecord(
        contract_version="1.0.0",
        attribution_id=attribution_id,
        issued_at_utc=issued_at.isoformat(),
        expires_at_utc=expires_at.isoformat(),
        producer="voice_identity",
        binding=AttributionBinding(
            conversation_id=conversation_id,
            device_id=device_id,
            satellite_id=satellite_id,
            pipeline_id=None,
            turn_index=None,
            room_id=room_id,
        ),
        subject=AttributionSubject(
            person_id=person_id,
            display_name=None,
            profile_id=None,
        ),
        confidence=AttributionConfidence(score=None, band=confidence_band),
        decision=AttributionDecision(
            state=state,
            reason_code=f"identity_{state}",
            recommended_action="allow",
        ),
        freshness=AttributionFreshness(
            attribution_age_ms=0,
            valid_until_utc=expires_at.isoformat(),
            freshness_class="fresh",
        ),
        diagnostics=AttributionDiagnostics(),
        integrity=AttributionIntegrity(),
    )


def test_store_inserts_and_resolves_fresh_conversation_record() -> None:
    store = InMemoryAttributionContextStore()
    now = datetime.now(timezone.utc)
    record = _record(
        attribution_id="a1",
        issued_at=now,
        expires_after_seconds=30,
        conversation_id="conv-1",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        person_id="person_1",
        state="known",
        confidence_band="high",
    )

    store.upsert(record)
    resolved = store.resolve_current_speaker(
        conversation_id="conv-1",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=now + timedelta(seconds=1),
    )

    assert resolved is not None
    assert resolved.attribution_id == "a1"
    assert resolved.freshness.freshness_class == "fresh"


def test_store_rejects_expired_record() -> None:
    store = InMemoryAttributionContextStore()
    now = datetime.now(timezone.utc)
    store.upsert(
        _record(
            attribution_id="a-expired",
            issued_at=now - timedelta(seconds=40),
            expires_after_seconds=5,
            conversation_id="conv-1",
            device_id="dev-1",
            satellite_id="sat-1",
            room_id="room-1",
            person_id="person_1",
            state="known",
            confidence_band="high",
        )
    )

    resolved = store.resolve_current_speaker(
        conversation_id="conv-1",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=now,
    )

    assert resolved is None


def test_store_does_not_reuse_unknown_or_unavailable() -> None:
    store = InMemoryAttributionContextStore()
    now = datetime.now(timezone.utc)
    store.upsert(
        _record(
            attribution_id="a-unknown",
            issued_at=now,
            expires_after_seconds=20,
            conversation_id="conv-1",
            device_id="dev-1",
            satellite_id="sat-1",
            room_id="room-1",
            person_id=None,
            state="unknown",
            confidence_band="none",
        )
    )
    store.upsert(
        _record(
            attribution_id="a-unavailable",
            issued_at=now,
            expires_after_seconds=20,
            conversation_id="conv-1",
            device_id="dev-1",
            satellite_id="sat-1",
            room_id="room-1",
            person_id=None,
            state="unavailable",
            confidence_band="none",
        )
    )

    resolved = store.resolve_current_speaker(
        conversation_id="conv-1",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=now,
    )

    assert resolved is None


def test_store_speaker_handoff_same_conversation_prefers_newer_record() -> None:
    store = InMemoryAttributionContextStore()
    now = datetime.now(timezone.utc)
    older = _record(
        attribution_id="a-old",
        issued_at=now,
        expires_after_seconds=30,
        conversation_id="conv-1",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        person_id="person_1",
        state="known",
        confidence_band="high",
    )
    newer = _record(
        attribution_id="a-new",
        issued_at=now + timedelta(seconds=2),
        expires_after_seconds=30,
        conversation_id="conv-1",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        person_id="person_2",
        state="known",
        confidence_band="high",
    )

    store.upsert(older)
    store.upsert(newer)

    resolved = store.resolve_current_speaker(
        conversation_id="conv-1",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=now + timedelta(seconds=3),
    )

    assert resolved is not None
    assert resolved.attribution_id == "a-new"
    assert resolved.subject.person_id == "person_2"


def test_store_device_satellite_fallback_is_time_bounded() -> None:
    store = InMemoryAttributionContextStore(fallback_window_seconds=10)
    now = datetime.now(timezone.utc)
    record = _record(
        attribution_id="a-fallback",
        issued_at=now,
        expires_after_seconds=30,
        conversation_id=None,
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        person_id="person_1",
        state="known",
        confidence_band="medium",
    )
    store.upsert(record)

    in_window = store.resolve_current_speaker(
        conversation_id="unknown-conv",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=now + timedelta(seconds=9),
    )
    out_of_window = store.resolve_current_speaker(
        conversation_id="unknown-conv",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=now + timedelta(seconds=11),
    )

    assert in_window is not None
    assert out_of_window is None


def test_store_sweep_expired_removes_records() -> None:
    store = InMemoryAttributionContextStore()
    now = datetime.now(timezone.utc)
    store.upsert(
        _record(
            attribution_id="a-expired",
            issued_at=now - timedelta(seconds=20),
            expires_after_seconds=5,
            conversation_id="conv-1",
            device_id="dev-1",
            satellite_id="sat-1",
            room_id="room-1",
            person_id="person_1",
            state="known",
            confidence_band="high",
        )
    )
    store.upsert(
        _record(
            attribution_id="a-fresh",
            issued_at=now,
            expires_after_seconds=30,
            conversation_id="conv-1",
            device_id="dev-1",
            satellite_id="sat-1",
            room_id="room-1",
            person_id="person_1",
            state="known",
            confidence_band="high",
        )
    )

    removed = store.sweep_expired(now=now)
    resolved = store.resolve_current_speaker(
        conversation_id="conv-1",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=now,
    )

    assert removed == 1
    assert resolved is not None
    assert resolved.attribution_id == "a-fresh"


def test_store_marks_record_stale_when_near_expiry() -> None:
    store = InMemoryAttributionContextStore()
    now = datetime.now(timezone.utc)
    store.upsert(
        _record(
            attribution_id="a-stale",
            issued_at=now - timedelta(seconds=26),
            expires_after_seconds=30,
            conversation_id="conv-1",
            device_id="dev-1",
            satellite_id="sat-1",
            room_id="room-1",
            person_id="person_1",
            state="known",
            confidence_band="high",
        )
    )

    resolved = store.resolve_current_speaker(
        conversation_id="conv-1",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=now,
    )

    assert resolved is not None
    assert resolved.freshness.freshness_class == "stale"
    assert resolved.freshness.attribution_age_ms > 0


def test_store_can_resolve_not_required_state_without_identity_authority() -> None:
    store = InMemoryAttributionContextStore()
    now = datetime.now(timezone.utc)
    store.upsert(
        _record(
            attribution_id="a-not-required",
            issued_at=now,
            expires_after_seconds=10,
            conversation_id="conv-1",
            device_id="dev-1",
            satellite_id="sat-1",
            room_id="room-1",
            person_id=None,
            state="not_required",
            confidence_band="none",
        )
    )

    resolved = store.resolve_current_speaker(
        conversation_id="conv-1",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=now + timedelta(seconds=1),
    )

    assert resolved is not None
    assert resolved.decision.state == "not_required"
    assert resolved.subject.person_id is None


def test_store_deterministic_freshness_boundary_transitions() -> None:
    store = InMemoryAttributionContextStore()
    issued_at = datetime(2026, 7, 23, 12, 0, 0, tzinfo=timezone.utc)
    store.upsert(
        _record(
            attribution_id="a-boundary",
            issued_at=issued_at,
            expires_after_seconds=30,
            conversation_id="conv-boundary",
            device_id="dev-1",
            satellite_id="sat-1",
            room_id="room-1",
            person_id="person_1",
            state="known",
            confidence_band="high",
        )
    )

    fresh = store.resolve_current_speaker(
        conversation_id="conv-boundary",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=issued_at + timedelta(seconds=24),
    )
    stale = store.resolve_current_speaker(
        conversation_id="conv-boundary",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=issued_at + timedelta(seconds=25),
    )
    expired = store.resolve_current_speaker(
        conversation_id="conv-boundary",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="room-1",
        now=issued_at + timedelta(seconds=31),
    )

    assert fresh is not None
    assert fresh.freshness.freshness_class == "fresh"
    assert stale is not None
    assert stale.freshness.freshness_class == "stale"
    assert expired is None


def test_store_room_id_constraint_prevents_cross_room_resolution() -> None:
    store = InMemoryAttributionContextStore()
    now = datetime(2026, 7, 23, 12, 30, 0, tzinfo=timezone.utc)
    store.upsert(
        _record(
            attribution_id="a-room-scope",
            issued_at=now,
            expires_after_seconds=30,
            conversation_id="conv-room",
            device_id="dev-1",
            satellite_id="sat-1",
            room_id="kitchen",
            person_id="person_1",
            state="known",
            confidence_band="high",
        )
    )

    wrong_room = store.resolve_current_speaker(
        conversation_id="conv-room",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="office",
        now=now + timedelta(seconds=1),
    )
    correct_room = store.resolve_current_speaker(
        conversation_id="conv-room",
        device_id="dev-1",
        satellite_id="sat-1",
        room_id="kitchen",
        now=now + timedelta(seconds=1),
    )

    assert wrong_room is None
    assert correct_room is not None
    assert correct_room.attribution_id == "a-room-scope"


def test_store_partial_device_satellite_correlation_does_not_resolve_identity() -> None:
    store = InMemoryAttributionContextStore(fallback_window_seconds=10)
    now = datetime(2026, 7, 23, 12, 45, 0, tzinfo=timezone.utc)
    store.upsert(
        _record(
            attribution_id="a-partial-correlation",
            issued_at=now,
            expires_after_seconds=30,
            conversation_id=None,
            device_id="dev-1",
            satellite_id="sat-1",
            room_id="kitchen",
            person_id="person_1",
            state="known",
            confidence_band="high",
        )
    )

    missing_satellite = store.resolve_current_speaker(
        conversation_id=None,
        device_id="dev-1",
        satellite_id=None,
        room_id="kitchen",
        now=now + timedelta(seconds=1),
    )
    missing_device = store.resolve_current_speaker(
        conversation_id=None,
        device_id=None,
        satellite_id="sat-1",
        room_id="kitchen",
        now=now + timedelta(seconds=1),
    )

    assert missing_satellite is None
    assert missing_device is None
