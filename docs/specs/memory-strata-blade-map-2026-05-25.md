# Memory Strata WS1-WS10 Blade Map — 2026-05-25

Status: active non-stop line  
Scope: `openclaw-mem` WS1–WS10 completion + local install/enable where applicable  
Authority: CK approved `櫻花刀舞` + `non-stop` + run-to-empty within same-line/same-risk/rollbackable bounds  
Topology posture: runtime/config/install changes require explicit verifier + second-brain review before promotion; push/tag require review gate.

## Total goal

Complete WS1–WS10 for the memory-strata architecture line with verifier-backed artifacts, public-facing docs/skill updates when product surfaces change, WAL along the way, local install/enable where applicable, and release/tag closure after review acceptance.

## Non-goals

- No hidden runtime/default flips without baseline + review.
- No private CK/Lyria ops policy silently promoted into product defaults.
- No external push before push review.
- No tag before closure review accepts release readiness.

## Execution order

### Milestone 1 — Read-only baseline
- WS1 Product architecture audit
- WS10 Retrieval regression baseline
- outcome: current state receipts, no runtime mutation

### Milestone 2 — Evidence lanes
- WS3 Episodic posture review
- WS4 Episodic semantic lane evaluation
- WS8 Pack integration review

### Milestone 3 — Activation quality
- WS2 Durable/long-term policy hardening
- WS5 Working Set contract

### Milestone 4 — Relationship layer
- WS7 Graph/topology governance

### Milestone 5 — Bootstrap/document truth split
- WS6 Docs cold lane + bootstrap slimming

### Milestone 6 — Governed promotion
- WS9 Promotion/writeback governor

### Milestone 7 — Install / enable / release closure
- local install/enable where applicable
- public-facing docs + skill updates
- push review
- WAL / release receipt / tag

## Verifier doctrine

Every milestone requires:
- artifact receipt
- counterfactual check where meaningful
- Claude second-brain review before advancing to next milestone when product/runtime/install surface changed materially
- WAL note when durable truth changes

## Stop-loss

Stop and surface decisions if:
- same root cause fails twice
- a second durable write path is about to be introduced
- privacy/scope boundary becomes ambiguous
- a verifier cannot distinguish working from broken
- an install/enable step lacks rollback
