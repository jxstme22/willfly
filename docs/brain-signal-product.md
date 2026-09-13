# Brain signals and manual execution — product definition

User-confirmed priority, 13 September 2026. This is the next product track after the current DeepSeek Observatory batch. It supersedes the earlier assumption that the entire trading laboratory must finish before an actual connectome experiment can start. Existing acceptance evidence and safety boundaries remain valid.

## Main user loop

The connectome-derived model evaluates coins and supported pools, produces spot-entry, LP-entry and exit proposals, and can choose hold or abstain. The user executes manually through Zenith or another tool. Willfly observes public-wallet activity, reconciles the resulting positions and costs, links actions to proposals where justified, and prepares verified outcomes for subsequent training. The product is decision support with an observable learning cycle. Automatic transaction execution is outside this version.

The biological component is a mathematical model using a verified measured connectome, not living tissue or an uploaded mind. A real graph must drive the model's recurrent computation. An ordinary model or LLM must not silently stand in for it. A documented subnetwork is acceptable if clearly identified; a whole-brain label requires actual whole-brain coverage.

## What the user sees

- A terminal-style signal inbox with exact chain/token/pool identity, proposed action, horizon, creation and expiry times, evidence cutoff, model version, uncertainty and reasons grounded in recorded inputs. Never fabricate a confidence probability from an uncalibrated score.
- Separate spot and LP signals; LP proposals identify the supported protocol, range and cost assumptions. Exit proposals distinguish selling tokens, removing liquidity, collecting fees and converting residual inventory. Prediction-only or unsupported modes are visibly research-only.
- Open positions and actual wallet actions, including manual overrides, partial changes, failed transactions and unresolved records. Signals can expire or be explicitly invalidated; history is retained.
- Results showing predicted versus observed outcomes, realized proceeds versus marked values, costs, missing evidence, and comparisons against ordinary and shuffled-network controls.
- Training runs that can be launched/resumed on the user's Windows/WSL2 PC, with dataset/code/model hashes and a report. Benchmark the 32 GB RAM / RTX 4070 Ti machine before promising whole-network throughput or GPU memory fit.

## Data and feedback

Track the user's configured public wallet addresses and position ownership without requiring private keys. Discover relevant transactions through supported indexed data or bounded block/receipt scanning, including failed transactions that emit no successful transfer logs. Follow internal routes and position-manager identities; do not equate transaction sender or pool-level liquidity events with user ownership. Unsupported routes remain unresolved. Backfill downtime and reconcile fork revisions without duplicate economic actions.

External manual transactions can be recorded without a Zenith control API when ownership and on-chain evidence suffice. Zenith integration is not yet implemented; API/export access and protocol coverage must be verified. Off-chain clicks, rejected quotes, undisclosed charges and motivations cannot be reconstructed solely from chain data.

Record every signal before its outcome is known. Match manual actions conservatively using transaction hash, wallet, position and action identity; ask for a manual link when ambiguous. Preserve signal origin, user override and unrelated-manual-action labels. A successful user trade is not automatically proof that the model made a good prediction.

Learn from three inputs: the user's full action history, declared external-wallet cohorts and broader historical market sequences. Keep negative and incomplete examples, deposits/withdrawals, fees, unsellable holdings and losses. Vendor PnL is evidence to reconcile, not a training oracle. Select external wallets using information available at the selection time; freeze cohort versions and use wallet/token/time separation to test memorization and leakage. Do not infer common ownership or intentions from wallet relationships alone.

Historical data reconstructed today is retrospective evidence: record when it was actually obtained. Do not invent historical arrival timestamps or claim it was prospectively available. Follower evaluation uses achievable observation and execution delays, not another wallet's entry price. Human delays and changed sizes are separate from model quality. Observe ignored/abstained candidates too; counterfactual outcomes are explicitly simulated and cannot be mixed with actual fills.

## Continuous learning without user trades

A user-confirmed core requirement is a 24/7 learning service that does not depend on the user placing trades. While the host is running and sources are available, continuously collect supported market and external-wallet observations, generate versioned predictions, and score them when their outcome horizons mature. Feed verified new examples and versioned historical replay into automatically scheduled candidate training. Personal trades are an additional feedback source, never the trigger required for learning to continue.

Maintain separate durable queues/checkpoints for observation, outcome maturation, training and evaluation. A scheduled cycle with insufficient new evidence reports waiting for labels/data instead of claiming learning occurred. The training schedule is bounded by available examples, CPU/GPU memory, runtime and provider budgets; 24/7 operation does not require a permanently saturated GPU. Training must not interrupt collection or signal delivery. After downtime, backfill and reconcile revised evidence before using it for new training; record actual gaps and never claim uninterrupted operation while the host was off.

Score untraded opportunities using directly observed market targets where possible. Hypothetical trade/LP returns require the validated execution/accounting model and remain simulated. The model's own recommendations are not truth labels. Include failures, abstentions and negative examples, and balance recent data with older replay to test forgetting. Keep an untouched final test and rotate forward evaluation windows: repeatedly selecting models on the same holdout turns it into training feedback.

The terminal UI must expose last observation, latest mature label, training queued/running/waiting/failed state, candidate version, last evaluation, active version and promotion/rollback history. Acceptance includes an observation period with zero user trades in which external evidence produces mature examples, a candidate training run and a reproducible evaluation without manual triggering. A deterministic clock fixture validates scheduling only; retain separate real wall-clock evidence.

## Training and release discipline

Begin with verified fixed biological wiring and a trained readout; evaluate input encoding choices explicitly. Internal-weight adaptation is a separately versioned experiment. Use the same data, tuning budget and available features for practical ordinary, random/shuffled and no-state controls. Start with defined measurable prediction targets, then test policy outcomes with independently validated spot/LP economics.

Automatic capture updates the evidence store; automatic scheduled training consumes qualified examples to create candidate models even with no personal trades. The active model stays fixed within each recorded version; successful candidate training alone cannot replace it. Chronological holdout, comparison, calibration and risk checks precede promotion; keep the old version and rollback support. Learning from observed actions does not reveal the outcomes of unchosen actions, and cannot establish causal benefit without an appropriate evaluation design.

Offline biological experiments can begin before M1-07's 72-hour audit and M3-03's 14-day shadow gate finish. Those gates still govern their original operational/prospective claims. Spot and LP recommendation readiness are separate: do not block all biological work on LP validation, and do not turn incomplete LP math into actionable recommendations. No funded performance guarantee follows from a completed training run.

## Scope and sequence

The companion [JSON plan](brain-product-tasks.json) defines B0 through B10 with dependencies, deliverables and acceptance checks. It adds the missing wallet-feedback and signal-product work without rewriting active M1 statuses. Existing M2/M5 economic tasks can satisfy mapped acceptance requirements when verified; reuse their implementations. The current DeepSeek batch continues; the following session prioritizes the biological laboratory and manual-feedback product instead of expanding generic scanner features.

The first release should demonstrate a verified biological graph responding to market data, a reproducible trained prediction compared with controls, a research-labelled entry/exit proposal, and an independently decoded manual transaction linked to an outcome. If live examples are unavailable, fixtures prove mechanics only and the live-feedback acceptance remains open. Qualified LP proposals follow validation of one supported LP family.

## Selected next implementation model

After DeepSeek finishes, the coordinator audits its final work; GPT Luna Extra High repairs findings, the coordinator rechecks them, and Luna continues the authorized build loops. See the [handoff](luna-extra-high-handoff.md) and [JSON goals](luna-build-loops.json). This staged assignment is prepared only; no new model session or background monitoring has been started.
