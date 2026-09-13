# Experiment plan — draft 1.1

Date: 13 September 2026. Planning document, not implementation status or evidence of performance.

The detailed implementation sequence, numerical feasibility defaults and phase gates are now specified in the [build roadmap](build-roadmap.md), with individual work items in the [77-task backlog](build-tasks.md). This document retains the scientific design; use the roadmap for build order.

## Primary question

Does a fly-derived recurrent model improve new-token decisions after realistic costs, compared with simple strategies and ordinary machine learning given the same information?

Secondary question: does liquidity-provider behavior add predictive value beyond token price, trades and holder features? Evaluate this separately so an improvement from LP data is not incorrectly attributed to the connectome.

## Proposed system

1. **Observation adapters:** chain events and scanner APIs, with both event time and actual arrival time. Persist raw evidence, source identity, factory/version and missingness.
2. **Feature pipeline:** numerical market sequences and optional structured text features. No future data or hidden action recommendation in the encoder.
3. **Decision candidates:** simple rules, conventional learned models, random reservoirs and the fly-derived reservoir, all using comparable information and tuning budgets.
4. **Policy and constraints:** map outputs to watch/enter/hold/reduce/exit initially. Add LP and sizing only after the restricted task is evaluable. Validate action feasibility independently of the model.
5. **Replay and ledger:** simulate delayed fills, costs and exits; reconcile every action with portfolio balances.
6. **Research interface:** an LLM retrieves evidence, summarizes narratives, explains recorded decisions and supports experiment analysis. Market content is untrusted input, never authority to change wallet permissions or system rules.

The initial model should operate without an LLM in its critical path. Add timestamped LLM features as a measured intervention. Natural-language explanations must refer to actual evidence and model outputs rather than inventing a neural rationale.

## How training could work

### A. Train a readout first

Keep the chosen recurrent graph fixed. Encode past market observations into activity; train a small output layer on historical outcomes. This is training a decision interface, not fine-tuning a pretrained financial brain. A static graph does not come with financial knowledge or an intrinsic learning rule.

Candidate targets include executable forward returns, adverse excursion, exit failure risk and liquidity deterioration over predeclared horizons. Missing or impossible exits must not silently disappear from labels. Start with one target family and one fixed sizing policy, selected after data feasibility is known.

### B. Train constrained parameters later

If A shows useful representation, train a limited input encoder, neuron time constants/gains, edge scaling or selected synaptic weights. Preserve graph masks or signs only where scientifically justified, and record every assumption. Differentiable rate models can use ordinary gradients; spiking models need an appropriate method such as surrogate gradients or derivative-free optimization. These are candidate engineering approaches pending targeted source verification.

Changing the model to fit markets reduces the strength of claims about reproducing fly physiology. Keep useful market computation and biological fidelity as separate evaluation goals.

### C. Test policy learning and plasticity separately

Later options include imitation of successful behaviors, offline reinforcement learning and explicit reward-modulated plasticity. Wallet actions do not reveal all information, hedges or objectives available to their owners, so copy data is not an unquestionable expert label. Historical trajectories also do not tell us the consequences of every unchosen action.

Only consider online learning in replay or shadow operation first. Demonstrate retention, stability and performance after regime changes. Stimulating a neuron labeled as dopaminergic does not automatically implement credit assignment or profitable learning.

## Stages and deliverables

| Stage | Work | Completion evidence |
|---|---|---|
| 0. Research specification | Select one launchpad/factory and DEX destination; verify versions, data licensing, APIs, history and costs; define capital scenarios and train/test horizons | Written source/endpoint matrix; unresolved gaps explicit; proposed target and evaluation frozen before final holdout |
| 1. Observation feasibility | Record all launches from the chosen source, including dead/failed tokens; join trades, liquidity and wallet observations | Coverage audit against chain logs; duplicate/reorg handling; measured arrival delay and missingness; versioned schema |
| 2. Replay and baselines | Build complete entry-to-exit ledger; test watch-only, simple confirmation/momentum and conventional predictors | Reconciled sample transactions; stated fill assumptions; failures retained; costs and delays stressed |
| 3. Neural representation test | Compare fixed fly reservoir with raw-feature readout, random reservoir, shuffled graph and compact conventional recurrent model | Chronological unseen evaluation; several seeds; matched tuning; paired uncertainty estimates; meaningful ablations |
| 4. Hybrid tool/LLM experiment | Add LP-wallet features and then structured LLM features, one at a time | Marginal benefit, latency, source reliability and cost measured; results compared with the unchanged baseline |
| 5. LP action experiment | Add selected ranges and LP-vs-spot-vs-idle decisions for supported pools | Fee attribution, tick behavior, hook effects and liquidation economics validated; no double-counting IL/LVR |
| 6. Shadow operation | Record live hypothetical decisions using actual arrival times | Stable ingestion and decision latency; replay/live mismatch report; predefined observation period completed |

Funded deployment is a separate later decision, based on evidence. No stage here authorizes it. Avoid promising calendar durations until data access and compute requirements are known.

## Evaluation contract

- Primary financial outcome: net portfolio change in a declared numeraire, under fixed capital and exposure rules, measured against the strongest preselected baseline. Report absolute outcomes as well as excess outcomes.
- Report drawdown, tail losses, exit failures, turnover, capital utilization, prediction calibration, latency and costs. Do not optimize solely for win rate.
- Split chronologically; purge overlapping label horizons. Group related token/deployer episodes where appropriate to reduce cross-split leakage. Fit normalization and select models using training/validation only.
- Preserve launches that fail, never graduate, lose liquidity or become unsellable. Track unresolved outcomes explicitly; conservative valuation assumptions need sensitivity tests.
- Historical LLM enrichment must use only information available at the decision time. A present-day model may know subsequent outcomes, even from a token name. Prefer contemporaneous archived text, identity masking and a no-LLM baseline; use prospective shadow tests where leakage cannot be excluded.
- Model transaction delay, fees, slippage and failed exits. Candles alone cannot validate exact LP fees or executable fills in thin markets. Small-position assumptions do not establish scalability.
- Compare LP versus spot under matched initial capital and clearly stated inventory benchmarks. Do not subtract IL or LVR again if already represented in complete balance changes.
- Ablations: remove recurrent state, remove LP features, remove LLM features, randomize topology with relevant graph statistics matched, and freeze learning. Isolate which component contributes.

## Go / revise / stop criteria

Advance only if the candidate beats both a strong practical baseline and a matched nonbiological model on the predeclared metric, with acceptable drawdown and robustness across unseen periods and realistic cost stress. Set numerical thresholds after a feasibility sample, before looking at the final holdout.

If recurrence helps but fly topology does not, retain the useful ordinary model and report the negative biological result. If no method has a robust net advantage, improve observations or revise the task; do not deploy because the narrative is appealing.

## Training research update

[Training and hybrid AI design](training-design.md) now records the targeted source check performed after this initial plan was written. It identifies trainable parameters, feedback requirements, connectome constraints and LLM/tool interfaces. The next planning task is Stage 0's source/endpoint matrix and narrow dataset/target specification.

Foundational references and current tool evidence are in [the literature review](../output/fly-connectomes-research.md) and [project direction](project-direction.md). No new literature search was performed before writing this initial plan.

## Scanner and follower-outcome amendment

Use [the scanner integration specification](scanner-integration-plan.md) alongside the roadmap. Classify genuine swaps separately from transfers, gifts and ambiguous estimated activity before building flow features. Freeze tracked-wallet selection with as-of evidence. Evaluate follower outcomes using signal arrival and executable entry/exit costs, separately from leader PnL. External trader, risk and social features receive distinct ablations; the same features and costs apply to biological and ordinary model comparisons. Missing cohort history or unsupported scanner access requires prospective collection or an unavailable experiment outcome.
