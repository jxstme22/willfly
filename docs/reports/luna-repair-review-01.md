# Coordinator review of Luna repair checkpoint 01

14 September 2026. **Disposition: changes requested; G0 remains open.** Reviewed the unstaged repair delta against `521f156` while the implementation task was idle. This report does not modify source code or discard the repair work.

## Independent verification

Full suite: 141 passed, one localhost test skipped by the sandbox. Both existing planning catalogues, compileall and whitespace checks pass. Re-ran the diagnostic probes and independently inspected canonicalization, anchor storage, runner and CLI changes. No live-chain qualification or endurance acceptance is claimed.

DS-02's out-of-range classification is repaired and tested through restart. DS-06's top-level anchor import rejects the reproduced coercions. DS-03's explicit invalid-candidate/corrected-retry scenario is repaired. The false-genesis and unreached-anchor cases now fail closed. However, the larger DS-01/DS-05 qualification boundary is not yet satisfied, and DS-04's restart change introduced an old-tip selection regression.

## R1 — P1: an uploaded assertion still substitutes for independent verification

**Original findings:** DS-01 and DS-05 remain OPEN.

`src/willfly/cli.py::_qualify_anchor` reads both `header` and `independent_header` from the same user-supplied JSON, copies `independent_provider`, and manufactures `verification="independent_header_match"`. It performs no provider query and records no separately verified source check. `assess_ancestry_anchor` then accepts the matching fields. The existing CLI test itself demonstrates that two fabricated headers and `fixture.archive-review` qualify against the production source configuration without observing that chain. Structured assertions are better validated than prose, but still are not evidence of a performed independent check.

**Required repair:** distinguish offline imported declarations from independently verified anchors. Offline/fixture bundles must not qualify production namespaces merely by choosing a provider label. Add a bounded read-only verifier using the configured primary source and an explicitly configured independent source, checking each source's chain and the requested header identity; record performed reads and their provenance under a declared trust policy. Reject missing checks, unavailable or mismatched sources, and identical configured endpoints. Independence beyond endpoint identity must be stated as a configured trust assumption, not claimed cryptographically proven. Keep finality claims separate. Tests can use actual local fixture RPC servers through the real subprocess CLI; label fixture mode and ensure it cannot masquerade as production evidence. Alternatively leave offline imports explicitly unverified until this verifier exists, but DS-05 cannot be marked implemented/qualified merely from parsing.

Use an explicit positive resolved-state condition (`qualified` plus reached-anchor/no-gap invariant) rather than an expanding denylist. Validate types inside structured evidence too. Preserve previous positive proofs and trusted-anchor data only when their qualification can actually be established.

## R2 — P1: backfill chooses old stored fork tip before fresh evidence

**New regression in the DS-04 repair.** `backfill_to_store` initializes `all_headers` with `store.list_headers()`, appends freshly fetched headers, then `_reconcile_if_tipped` selects the first header with the target height. Therefore the old stored branch wins over the newly observed branch. Reproduced two consecutive backfills over heights 0–1 on the same store: first tip hash ends `03e9`, next RPC tip ends `03ea`; the second manifest still selects `03e9`. Header count reports four for a two-header run because stored headers are mixed into run evidence.

**Required repair:** choose the tip from fresh, hash-matched active-source observations, independently of historical ancestry storage. A no-op resume must revalidate its tip, or expose a stale/unverified state when the source is unavailable; never choose a fork by insertion order. Keep current-run counts/provenance separate from restored historical headers. Fetch only bounded anchor/tip evidence needed for qualification rather than prefetching an arbitrary full backfill range before page limits apply.

**Acceptance:** backfill A, reopen store, observe replacement B with a quiet tip, then select B and repair old/new event classifications. Exercise no-op checkpoint resume, unavailable tip, both insertion orders and truthful run header counts. The original capture/backfill genesis parity remains required.

## Recovery documentation still required

The runbook has no concrete trusted-anchor requalification workflow despite the checkpoint claiming it documents recovery. Conflicting anchors remain immutable by source. Provide an explicit recoverable procedure (for example a new versioned source namespace with new verified evidence, retained old source and linked supersession metadata) and test that it works after a boundary-crossing fork. Do not silently delete or overwrite trusted history.

## Next action

Luna should repair R1/R2 and the recovery gap, retain the successful existing fixes, add focused negative and fresh-process tests, and return another repair checkpoint for independent review. No feature loops yet. No extra user approval is needed for this internal repair cycle. All live source/archive, elapsed-time and financial/biological acceptance gates remain open.
