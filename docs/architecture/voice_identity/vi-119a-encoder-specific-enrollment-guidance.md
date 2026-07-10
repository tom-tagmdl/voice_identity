# VI-119a Encoder-Specific Enrollment Guidance

## 1. Executive Summary

This document closes the remaining VI-119a gap by translating model-specific evidence into enrollment guidance for Voice Identity.

Key conclusions:
- ECAPA-TDNN remains the recommended model class for Voice Identity household attribution.
- ONNX Runtime remains the recommended production inference path for Home Assistant local-first deployment.
- Current repository state does not yet implement a concrete production encoder runtime.
- Enrollment should be duration-gated and condition-diversity-gated, not count-only.
- Current 8-phrase Concierge corpus is usable but should be replaced by a mixed-style corpus and duration-first completion gates before VI-120 final implementation.

Confidence labels used in this document:
- Model-specific evidence: directly from candidate model docs/cards/repos.
- Literature/industry evidence: broader speaker-recognition references.
- Engineering guidance: repository-specific recommendation where direct model docs do not define a value.

## 2. Current Repository Findings

### 2.1 What the repo currently specifies

Repository currently contains:
- model-family intent: ECAPA-class (via config defaults such as model_preference=ecapa_v1)
- placeholder abstraction: model execution backend defaults to unavailable fail-closed backend
- no concrete production encoder selection and no active model runtime implementation

Evidence in repository:
- model execution backend is placeholder and unavailable by default
- README states no production fingerprint engine/model runtime is implemented
- project dependencies do not include production speaker-encoder runtime packages

### 2.2 Implication for VI-119a

Any final enrollment values today are architecture guidance to drive VI-120 and subsequent benchmarking, not measured final optimums from this codebase.

## 3. Candidate Encoder Comparison

## 3.1 Candidate set reviewed

Minimum required candidates reviewed:
- SpeechBrain ECAPA-TDNN VoxCeleb model
- WeSpeaker ECAPA family models
- pyannote embedding model
- NVIDIA NeMo speaker embedding models (TitaNet and ECAPA options)

## 3.2 Comparison summary (practical Home Assistant perspective)

1. SpeechBrain ECAPA-TDNN VoxCeleb
- Architecture: ECAPA-TDNN with attentive statistics pooling (model-specific evidence)
- Embedding size: 192 (model-specific evidence from hyperparams lin_neurons)
- Input: 16 kHz, mono expectation (model-specific evidence)
- Runtime: PyTorch-native; ONNX path not first-class in model card (engineering note)
- License: Apache-2.0 (model-specific evidence)
- CPU suitability: good for offline inference, but packaging for HA may be heavier than ONNX-native runtime (engineering guidance)
- Strength: mature model ecosystem and clear speaker-verification workflow examples
- Limitation: model card does not prescribe enrollment duration targets

2. WeSpeaker ECAPA (for example ECAPA512/ECAPA1024 families)
- Architecture: ECAPA family among many supported embedding backbones (model-specific evidence)
- Embedding size: model-dependent (for example ECAPA512/ECAPA1024 naming) (model-specific evidence)
- Input: 16 kHz wav examples in docs (model-specific evidence)
- Runtime: explicit runtime ONNX support; pretrained runtime .onnx artifacts documented (model-specific evidence)
- License: toolkit Apache-2.0, pretrained model license follows dataset (for VoxCeleb typically CC-BY-4.0) (model-specific evidence)
- CPU suitability: strong practical fit due to ONNX runtime path and production-oriented toolkit focus
- Strength: direct ONNX workflow and production-oriented runtime options
- Limitation: exact household enrollment duration recommendations not explicitly prescribed in docs

3. pyannote/embedding
- Architecture: x-vector TDNN with SincNet frontend (model-specific evidence)
- Embedding size: not explicitly stated in accessible model card sections reviewed
- Input: full-file or sliding-window extraction workflows supported
- Runtime: PyTorch/pyannote stack; no ONNX-first deployment path in reviewed model card
- License: MIT (model-specific evidence)
- Access constraints: Hugging Face gated terms acceptance required (model-specific evidence)
- Strength: strong embedding quality reported and mature diarization ecosystem alignment
- Limitation: gating and runtime stack complexity are less ideal for frictionless HA offline packaging

4. NVIDIA NeMo speaker models (TitaNet-Large as practical reference)
- Architecture: depth-wise separable conv1D TitaNet; NeMo also supports ECAPA configs (model-specific evidence)
- Model size: TitaNet-Large about 23M params (model-specific evidence)
- Input: 16 kHz mono wav (model-specific evidence)
- Runtime: NeMo/PyTorch-native, rich tooling; ONNX deployment path not the simplest baseline for HA add-on style distribution
- License: model card lists CC-BY-4.0 for referenced model (model-specific evidence)
- Strength: strong documented benchmark performance and mature training/fine-tuning workflows
- Limitation: ecosystem heavier than needed for first local HA household rollout

## 3.3 Candidate suitability ranking for Voice Identity

Engineering recommendation ranking for initial production direction:
1. WeSpeaker ECAPA ONNX runtime model as primary production candidate
2. SpeechBrain ECAPA as secondary fallback if PyTorch-first bootstrap is temporarily needed
3. NeMo TitaNet/ECAPA as strong R&D candidate but heavier for initial HA packaging path
4. pyannote embedding as technically strong but deployment/access friction higher for this project constraints

## 4. Recommended Encoder Direction

Recommended production direction for Voice Identity:
- Model class: ECAPA-TDNN family (confirmed)
- Preferred concrete path: WeSpeaker ECAPA runtime .onnx model (for example ECAPA512_LM-class path) evaluated against SpeechBrain ECAPA baseline in benchmark plan
- Runtime: ONNX Runtime CPU-first
- Scoring baseline: cosine similarity with calibrated confidence bands
- Future optional backend: PLDA-style calibrated backend if enough in-domain calibration data is collected

Why this path:
- Matches repository architecture intent (ECAPA + local-first)
- Minimizes runtime/dependency burden in Home Assistant environments
- Gives direct ONNX artifacts and runtime flow evidence

## 5. Encoder-Specific Enrollment Guidance

This section distinguishes evidence sources explicitly.

## 5.1 Enrollment duration

Model-specific documentation:
- Candidate model cards/docs reviewed do not provide strict household enrollment duration prescriptions.

Literature/industry evidence:
- Text-independent embedding systems generally improve with more clean, diverse speech up to practical diminishing returns.

Engineering guidance for Voice Identity:
- Minimum acceptable net usable speech: 30 seconds
- Recommended net usable speech: 45 to 60 seconds
- Diminishing returns expectation: typically after about 60 to 90 seconds for household personalization use cases, but must be empirically verified in planned benchmark
- 30 seconds: acceptable floor, not preferred default
- 45 to 60 seconds: justified default target for robust household attribution under mixed conditions

## 5.2 Utterance count

Model-specific documentation:
- No candidate model documentation reviewed defines hard utterance-count requirements.

Engineering guidance:
- 8 utterances: minimum workflow floor
- 10 utterances: recommended default target
- 12 utterances: high-robustness option for difficult households

Decision:
- Utterance count is primarily a UX and coverage mechanism, not a hard model requirement.
- Duration and quality should be primary gates.

## 5.3 Corpus style

Model-specific + engineering interpretation for text-independent embeddings:
- Fixed passphrase-style prompts are not required.
- Natural speech can be sufficient if duration and acoustic quality are strong.
- Prompted phrases remain useful to force diversity and predictable capture coverage.

Recommended corpus structure (10 utterances):
- Commands: 3
- Questions: 2
- Statements/context: 3
- Longer multi-clause conversational utterances: 2

Required corpus characteristics:
- Mixed short/medium/long utterances
- Mixed speaking style and prosody
- Corpus-level phonetic diversity checks (not rigid per-utterance checks)

## 5.4 Required audio quality gates

Hard reject conditions:
- clipping/saturation
- severely low signal level
- dominant overlap speech
- excessive corruption where speaker characteristics are unreliable

Required quality gates before completion:
- net usable duration threshold passed
- minimum count threshold passed
- category/diversity threshold passed
- condition diversity threshold passed

## 6. Capture Workflow Guidance

## 6.1 Microphone guidance

- Prefer enrollment on the same device class expected for daily attribution (Voice PE path when available).
- Record and retain device/microphone metadata for calibration and diagnostics.

## 6.2 Distance guidance

- Include near-field and mid-field captures in enrollment profile.
- Avoid far-field-only enrollment as primary source.

Recommended distribution for 10 utterances:
- near-field: 6
- mid-field: 4

## 6.3 Noise guidance

- Majority clean captures with some realistic household ambient captures.

Recommended distribution for 10 utterances:
- cleaner: 7
- normal household ambient: 3

## 6.4 Retry guidance

- Retry weakest 1 to 3 captures only.
- Prioritize retries for missing coverage buckets:
  - duration shortfall
  - missing distance category
  - missing style/category diversity
  - low-SNR outliers

## 6.5 Completion criteria

Enrollment complete only when all pass:
- count gate: >= 8 utterances
- duration gate: >= 30 seconds usable speech
- recommended target gate: 10 utterances and >= 45 seconds usable speech
- diversity gate: mixed corpus categories satisfied
- condition gate: near + mid field present
- quality gate: no hard-reject captures in final accepted set

## 7. Benchmark Plan (Design Only)

Do not implement now. This is the validation plan for after encoder integration.

## 7.1 Scenarios to compare

Corpus and duration scenarios:
- current Concierge corpus (8)
- revised 8-phrase corpus
- revised 10-phrase corpus
- 30 seconds natural speech
- 45 to 60 seconds mixed speech

Condition scenarios:
- near-field only
- near-field plus mid-field
- clean-room only
- clean-room plus normal household ambience

## 7.2 Metrics

Primary:
- correct speaker identification rate
- false match rate
- unknown/abstention rate
- confidence stability
- nearest-neighbor margin
- score separation between household members

Secondary:
- per-device performance differences
- per-room performance differences

## 7.3 Test population

Minimum:
- at least two primary household members

Recommended additions:
- one similar-voice/challenging speaker
- optional child/elderly/accent variation participants where relevant

## 7.4 Success criteria to lock post-benchmark defaults

- revised 10-utterance mixed corpus outperforms or matches alternatives in false-match + abstention tradeoff
- duration-gated strategy outperforms count-only strategy
- condition-diverse enrollment outperforms near-field-only for multi-room attribution

## 8. Architecture Impact

## 8.1 VI-111 Sample Validation Pipeline

Should support:
- net usable speech duration
- phrase/utterance count (as secondary gate)
- capture condition metadata validation
- microphone/device metadata validation
- distance and noise category coverage checks

## 8.2 VI-112 Quality Scoring Engine

Should support additive scoring for:
- duration adequacy
- acoustic quality and SNR proxies
- condition diversity
- corpus diversity
- confidence band readiness for downstream attribution decisions

## 8.3 VI-113 Model Execution Provider

Should support:
- concrete encoder selection metadata
- embedding version metadata
- device/runtime metadata in diagnostics
- optional per-device calibration hooks

## 8.4 VI-114 GenerateVoiceprint Operation

Should support projection of:
- accepted duration summary
- accepted condition coverage summary
- quality gate pass/fail reason codes

## 8.5 VI-120 Concierge Enrollment Workflow Integration

Should implement enrollment using:
- duration-first completion semantics
- targeted retry for weak/missing-condition samples
- clear capture guidance per step (distance/noise/style)

## 8.6 Voiceprint registry metadata

Should include safe fields for:
- enrollment profile type
- capture condition summary
- device class summary
- confidence band calibration version
- re-enrollment recommendation state

## 8.7 ADR updates

Required:
- ADR for encoder-specific enrollment corpus and capture strategy
- ADR should explicitly define which values are initial defaults vs benchmark-tunable values

## 9. Final Decision

1. Is ECAPA-TDNN still the recommended model class?
- Yes.

2. Is ONNX Runtime still the recommended runtime path?
- Yes.

3. Is the current 8-phrase model sufficient?
- Sufficient as a minimum fallback only, not sufficient as final recommended default.

4. Should the corpus change?
- Yes. Shift to mixed-style corpus with explicit diversity targets.

5. Should the count change?
- Yes. Recommended default should be 10 utterances, with 8 as minimum and 12 as robust option.

6. Should enrollment be duration-gated?
- Yes. Duration must be primary gate.

7. Should enrollment include capture-condition diversity?
- Yes. Include near + mid field and limited realistic ambient conditions.

8. Can VI-120 proceed after this guidance is incorporated?
- Yes, with this guidance incorporated into VI-120 design and architecture specs.

9. What remains unresolved until empirical benchmarking?
- Final tuned defaults for:
  - exact duration target within 45 to 60 second band
  - exact count default (10 vs 12 for specific household profiles)
  - threshold calibration per device and room
  - confidence band boundaries for abstain vs assign decisions

## Evidence Notes and Certainty

Known with high certainty:
- repository currently has model-family intent + placeholder runtime, not concrete encoder deployment
- candidate models broadly expect 16 kHz mono workflows
- text-independent embedding behavior supports duration and acoustic diversity emphasis

Known with medium certainty:
- recommended default bands (10 utterances, 45 to 60 seconds) as best engineering fit for this architecture and deployment goals

Unknown until benchmark:
- final optimal default for this specific project/hardware mix
- per-device and per-room threshold tuning values
