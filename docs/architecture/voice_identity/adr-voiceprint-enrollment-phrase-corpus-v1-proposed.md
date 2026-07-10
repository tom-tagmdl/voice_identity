# ADR: Voiceprint Enrollment Phrase Corpus v1

## 1. Status

PROPOSED

## 2. Purpose

Formalize a stable phrase corpus and completion gates before VI-120 Concierge Enrollment Workflow implementation.

## 3. Context

Voice Identity and Concierge now have generation, validation, scoring, and metadata integration boundaries established. Enrollment workflow remains pending.

Current phrase selection exists in Concierge frontend but is not yet architecture-frozen with explicit diversity and coverage criteria.

## 4. Decision

Adopt an enrollment phrase corpus v1 with:
- 10 phrase default set
- deterministic phrase order
- mixed category composition
- explicit duration, completion, and quality gates

## 5. Phrase Corpus v1 (English baseline)

1. Turn on the kitchen lights.
2. What is the temperature in the living room?
3. Close the bedroom shades halfway.
4. I am getting ready for bed now.
5. Please play soft music in the office.
6. Set the dining lights to forty percent and start a ten minute timer.
7. If the garage door opens, notify me right away.
8. I am in the family room and I want a calm response.
9. Good morning, give me weather and a short home summary.
10. What can I do here right now?

## 6. Enrollment Sequence

Use fixed order from shorter to longer and from simple to multi-clause utterances.

## 7. Completion Gates

Hard gates:
- minimum completed phrases: 8
- minimum usable speech duration: 30 seconds
- corpus-level required phonetic class coverage: pass

Target gates:
- recommended completed phrases: 10
- recommended usable speech duration: 45 seconds
- condition diversity coverage: near-field and mid-field samples present
- category diversity diagnostics: pass

## 8. Retry Policy

- Retry weakest 1 to 3 phrases first.
- Prefer replacement prompts from missing categories/coverage classes and missing recording conditions.
- Full restart only after repeated failure.

## 9. Boundary Compliance

This decision does not change service ownership boundaries:
- Concierge remains enrollment UX/orchestration owner.
- Voice Identity remains generation/quality/identity owner.

No Voice Identity internals are exposed.

## 10. Impact

### VI-111 Sample Validation Pipeline

Add additive diagnostics for phrase category, duration, and condition-diversity readiness.

### VI-112 Quality Scoring Engine

Add additive score factors for duration adequacy, phrase diversity, and coverage completeness.

### VI-120 Concierge Enrollment Workflow Integration

Use phrase sequence and completion gates defined here.

## 11. Consequences

Positive:
- reduced enrollment workflow rework
- better speaker-discrimination readiness for future attribution
- clearer acceptance criteria for cross-repo integration

Tradeoff:
- slightly longer enrollment flow than 8-phrase baseline

## 12. Rollout Guidance

- Freeze phrase corpus and gates before final VI-120 implementation.
- Keep locale-specific corpus extension as a future additive design.
