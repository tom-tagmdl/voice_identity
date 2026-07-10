# VI-119a Voiceprint Enrollment Phrase Optimization

## Status

Research and architecture-validation recommendation for pre-VI-120 planning.

## Scope and Constraints

This document is research-only and architecture-only.

Out of scope:
- Enrollment workflow implementation
- Concierge workflow implementation
- Enrollment UI implementation
- Generation pipeline behavior implementation changes

## Method

Technology-first approach:
1. Identify actual model stack implemented in this repository.
2. Evaluate best practices for that class of speaker-recognition systems.
3. Derive corpus and capture recommendations for Home Assistant household conditions.

---

## Phase 1: Voiceprint Technology Analysis

## 1.1 Actual stack in this repository today

Observed implementation state:
- No production speaker encoder runtime is implemented yet.
- Model execution path uses an unavailable fail-closed backend by default.
- Model preference defaults to ecapa_v1 but this is configuration intent, not active encoder deployment.

Evidence in repository:
- Unavailable backend placeholder in model execution runtime.
- No runtime dependencies in project dependencies.
- README states no production fingerprint engine/model runtime is implemented.

Implication:
- The current repository cannot empirically validate phrase-level optimization against a running encoder yet.
- Any phrase recommendation must be a design recommendation for the planned encoder class, not measured integration output.

## 1.2 Planned model class signal

Architecture and config indicate ECAPA-class speaker embeddings as intended direction.

For ECAPA-style systems, the common pattern is:
- text-independent speaker embeddings
- fixed-length embedding from variable-length speech
- cosine-style embedding comparison in verification/identification flows

Key consequence:
- Enrollment quality is usually driven more by acoustic coverage and channel/noise robustness than by memorizing exact command text.

## 1.3 Published recommendations relevant to planned stack

From publicly available ECAPA/embedding model documentation and literature (for example ECAPA-TDNN references and practical embedding toolkits):
- 16 kHz mono speech is common training/inference assumption.
- Text-independent embeddings generally benefit from several seconds to tens of seconds of clean speech.
- Robustness improves with acoustic variability that matches deployment reality.

Important limitation:
- These are model-class recommendations, not this repository's measured production numbers, because the runtime backend is not implemented yet.

---

## Phase 2: Enrollment Science Findings

## 2.1 What tends to matter most for text-independent household speaker attribution

High impact factors:
- Total usable speech duration
- Signal quality (SNR, clipping avoidance)
- Microphone/channel match to deployment
- Distance/noise diversity representative of real usage

Medium impact factors:
- Utterance diversity and prosodic variation
- Phonetic coverage across corpus

Lower impact than often assumed:
- Exact command wording alone
- Excessive phrase count without quality control

## 2.2 Best-practice enrollment ranges applicable to local household systems

For text-independent embeddings in smart-home conditions, practical guidance converges on:
- Minimum usable speech: about 20 to 30 seconds clean net speech
- Stronger baseline: about 35 to 60 seconds net speech
- Typical phrase count band: 6 to 12 utterances, depending on utterance length and quality

Interpretation for this project:
- Phrase count should be selected from duration and diversity targets first.
- More phrases are not useful if they are acoustically redundant or noisy.

---

## Phase 3: Enrollment Corpus Analysis

## 3.1 Is current Concierge corpus appropriate?

Current corpus in Concierge panel has 8 long smart-home phrases.

Assessment:
- Positive: realistic domain vocabulary and household command context.
- Gap: over-weighted toward long imperative phrasing, limited short utterances, limited pure conversational/statement coverage.

Conclusion:
- Appropriate as a starting set, not optimal as final corpus.

## 3.2 Does phrase content materially affect quality for planned encoder class?

For text-independent embedding models:
- Phonetic and prosodic diversity matter.
- Mixed sentence forms matter.
- Exact command semantics matter less than acoustic/phonetic variety.

Therefore:
- Command-only corpus is not preferred.
- Mixed commands/questions/statements/conversational utterances is preferred.

## 3.3 Recommended corpus composition

Recommended category balance for v1 English corpus:
- Commands: 3
- Questions: 2
- Statements/context: 3
- Multi-clause conversational utterances: 2

Recommended utterance length balance:
- Short: 3
- Medium: 4
- Long: 3

Recommended count and duration targets:
- Minimum completion gate: 8 phrases and >= 30 seconds usable speech
- Recommended completion gate: 10 phrases and >= 45 seconds usable speech

## 3.4 Recommended phrase corpus v1 (English baseline)

1. Turn on the kitchen lights.
2. What is the temperature in the living room right now?
3. Close the bedroom shades halfway.
4. I am in the family room.
5. Please play soft music in the office.
6. What can I do here?
7. I want a calm and detailed answer.
8. If the garage door opens, notify me right away.
9. Give me a short weather and home summary for this morning.
10. Set the dining lights to forty percent and start a ten minute timer.

Reasoning:
- Keeps Home Assistant relevance without forcing command-only enrollment.
- Improves phonetic/prosodic coverage and short/medium/long balance.

---

## Phase 4: Capture Strategy Analysis

## 4.1 Factor ranking by expected impact on recognition reliability

Ranked highest to lowest expected impact:
1. Audio quality and clipping control
2. Total usable speech duration
3. Microphone/channel match to deployment
4. Distance and background-noise realism
5. Multiple recording conditions (near and mid field)
6. Phonetic and utterance diversity
7. Phrase count
8. Exact phrase wording

## 4.2 Recommended capture strategy

Microphone guidance:
- Capture at the same device class expected for regular use when possible.
- Prefer 16 kHz mono normalized input path.

Distance guidance:
- Include both near-field and mid-field samples in enrollment set.
- Suggested split for 10 phrases: 6 near-field, 4 mid-field.

Noise guidance:
- Majority clean samples, minority realistic household background samples.
- Suggested split for 10 phrases: 7 cleaner, 3 realistic ambient.

Quality requirements:
- Reject clipped, severely low-level, or highly corrupted captures.
- Gate on usable duration as first-class criterion, not phrase count only.

Retry requirements:
- Retry only weakest 1 to 3 samples.
- Prefer retries in missing acoustic condition buckets (distance/noise/style).

Completion criteria:
- Pass minimum phrase count
- Pass minimum usable speech duration
- Pass diversity checks (category + condition coverage)

---

## Phase 5: Real-World Concierge Deployment Analysis

## 5.1 Home Assistant household realities

Deployment conditions likely include:
- Home Assistant Voice PE and varied microphones
- Multiple rooms and reverberation profiles
- Near-field and mid-field usage
- Non-stationary household noise

Resulting recommendation:
- Enrollment should deliberately capture multiple distances and at least limited background variability.

## 5.2 Demographic and speech variability considerations

For elderly/children/accent/speaking-rate variation:
- Keep prompts simple and intelligible.
- Include both short and longer utterances.
- Avoid requiring overly complex phrase memorization.
- Ensure retry flow can swap problematic phrases without restarting full session.

---

## Deliverable: Architecture Impact Assessment

## VI-111 Sample Validation Pipeline

Recommended design changes:
- Add additive diagnostics for usable-duration checks.
- Add additive diagnostics for category and condition coverage.
- Add additive diagnostics for recording condition buckets (near/mid, clean/noisy).

No boundary changes required.

## VI-112 Quality Scoring Engine

Recommended design changes:
- Add additive scoring factors for:
  - usable speech duration
  - condition diversity
  - utterance diversity
- Keep deterministic, explainable score breakdown and safe reason codes.

No service contract break required if added as new score components.

## VI-120 Concierge Enrollment Workflow Integration

Recommended design requirements:
- Completion logic must include duration and diversity gates, not count-only.
- Retry must be targeted to weakest/missing-condition samples.
- Prompting should preserve mixed category corpus and ordering.

---

## ADR Recommendation

A formal ADR is required before VI-120 implementation is finalized.

Proposed ADR scope:
- Corpus v1 and ordering
- Minimum and recommended duration gates
- Minimum and recommended phrase count gates
- Condition diversity requirements
- Retry and re-enrollment policy

Reason:
- These are architecture decisions affecting validation, quality scoring, and workflow behavior across issues VI-111, VI-112, and VI-120.

---

## Mandatory Decision

1. Is the current Concierge enrollment corpus appropriate?
- Partially. It is a useful baseline but not optimal as final corpus.

2. Is the current phrase count appropriate?
- 8 is acceptable as minimum fallback, not ideal as default target.

3. What phrase count is recommended?
- Recommended default: 10.
- Minimum gate: 8.
- Optional robust mode: 12.

4. What enrollment duration is recommended?
- Minimum gate: >= 30 seconds usable speech.
- Recommended target: >= 45 seconds usable speech.

5. What capture strategy is recommended?
- Mixed distance capture (near + mid field).
- Mostly clean plus limited realistic ambient noise.
- Targeted retries of weakest samples.
- Completion gated by count + duration + diversity.

6. What must change before VI-120 begins?
- Freeze corpus and gates in ADR.
- Define duration/diversity diagnostics for VI-111.
- Define duration/diversity scoring inputs for VI-112.
- Define targeted retry and completion semantics in VI-120 design.

7. GO / NO-GO recommendation for proceeding with Concierge enrollment implementation.
- NO-GO for full VI-120 implementation with current implicit count-only, command-leaning corpus assumptions.
- GO after ADR-backed corpus and completion gates are finalized.

Reason for NO-GO:
- Current repository does not yet include a production encoder backend, so phrase strategy must be architecture-frozen now to prevent workflow and scoring rework once the runtime stack lands.
