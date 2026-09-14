# Willfly

Read-only research software for a connectome-derived crypto decision agent.

**Current build authority:** [Astra audit](docs/reports/astra-deep-audit.md), [next roadmap](docs/next-build-roadmap.md), [26-task JSON backlog](docs/next-build-tasks.json), and [Luna Extra High continuation handoff](docs/luna-extra-high-handoff.md). The earlier handoffs and PDF are historical snapshots.

**Current direction — 13 September 2026:** Robinhood Chain first; discover new launches and pairs, study memecoin trajectories, and choose between spot trading, selective liquidity provision, waiting and exiting. Expansion to other chains is a later possibility.

**Main product priority:** [Brain signals with manual execution and verified learning](docs/brain-signal-product.md), with a [dedicated JSON plan](docs/brain-product-tasks.json). After the current DeepSeek batch, bring actual connectome training forward: coin/LP entry and exit signals, user execution through external tools, wallet feedback, and learning from historical/user/other-wallet evidence. Observation, outcome scoring and scheduled candidate training continue 24/7 even when the user makes no trades; evaluated model promotion is recorded separately. Monitoring supports this product. Automatic execution is outside this version.

**Next builder:** GPT Luna Extra High, taking over after DeepSeek reached its usage limit. The [interrupted-checkpoint audit](docs/reports/deepseek-completion-audit.md) and repaired checkpoint are preserved. Follow the [staged handoff](docs/luna-extra-high-handoff.md) and [goal/loop JSON](docs/luna-build-loops.json): continue dependency-aware M and B build loops without routine coordinator pauses; the later broad audit remains separate.

## Project documents

- [Current decisions and tool assessment](docs/project-direction.md) — authoritative current scope, evidence and open questions.
- [Experiment plan](docs/experiment-plan.md) — proposed stages, training options, measurements and progression gates.
- [Training and hybrid AI design](docs/training-design.md) — trainable components, primary evidence and LLM/tool interfaces.
- [Luna implementation handoff](docs/luna-build-handoff.md) — new-session starting prompt, first build batch and progress rules.
- [Scanner integration plan](docs/scanner-integration-plan.md) — RHTrenches/Mezzanine evidence, data contracts and mapped build requirements.
- [Build roadmap](docs/build-roadmap.md) — first release, phases, architecture, estimates and acceptance gates.
- [Build tasks](docs/build-tasks.md) — 77 tasks with dependencies, target paths and completion evidence; also available as [JSON](docs/build-tasks.json).
- [Original literature review](output/fly-connectomes-research.md) — foundational neuroscience and LP research; its original LP-first recommendation has been superseded by the current direction.
- [Updated project PDF](output/pdf/fly-connectomes-and-crypto-liquidity.pdf) — review snapshot containing direction, training design, roadmap, tasks and the historical literature appendix. It predates the scanner amendments; Markdown/JSON version 1.1 is authoritative.

## Status

The direction remains Robinhood launch discovery, spot decisions and separately validated LP. The current checkpoint connects durable capture/backfill, header persistence, receipt attribution, immutable projections, API/dashboard loading, a read-only signal inbox and position/training views, versioned brain signal contracts, a verified MaleCNS v1.0 subset smoke run, restart-safe learning-watcher tick/status commands, typed signal snapshot loading/building, guarded candidate evaluation/status commands, durable causal-feedback import/status, an explicit multi-seed MaleCNS feedback-training runner, and public-wallet activity import/status. The latest local suite reports 219 passed and two sandbox socket skips; the skipped checks are loopback-only fixtures and do not represent product failures. These checks do not certify Observatory acceptance, whole-CNS coverage, model quality or financial advantage. Live source/archive, timed, economic and biological/model gates remain open. LP and funded execution remain disabled.

The existing 77-task tracker now distinguishes pre-audit fixture completion from full acceptance; use the new 26-task backlog for implementation order. Task status corrections preserve code and prior evidence rather than erasing progress.

## Development

Supported runtime: Python 3.12. The runtime uses standard-library HTTP for explicit read requests. Tests and
fixture-check are offline; dependency installation needs package access:

```text
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock -r requirements-export.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pytest
.venv/bin/willfly fixture-check
.venv/bin/willfly doctor
.venv/bin/willfly shadow
.venv/bin/willfly operator-check
.venv/bin/willfly watcher-status --state-db /path/to/watcher.sqlite3
.venv/bin/willfly feedback-status --feedback-dir /path/to/feedback --as-of-time 2026-09-14T00:00:00Z
.venv/bin/willfly wallet-status --wallet-dir /path/to/wallet-store --wallet 0x... --as-of-time 2026-09-14T00:00:00Z --arrival-cutoff 2026-09-14T00:00:00Z
```

The source-tree equivalent is `PYTHONPATH=src python3 -m willfly ...`. `doctor`
is intentionally read-only and reports an open launch-source gate until Pons V2
history and ABI evidence are complete. `shadow` refuses to start until an
operator freezes the prospective config. A frozen config can be exercised with
`willfly shadow-run` against a controlled observation JSON file; it records
hypothetical decisions only and never signs or broadcasts.
See [the operator runbook](docs/runbooks/operator.md) for WSL2 setup,
controlled shadow replay and bounded live capture.

## Verify and maintain planning

```text
.venv/bin/python -m pytest
python3 scripts/render_planning.py
python3 scripts/check_planning.py
```

JSON is canonical; rendering never resets statuses. Source-checkout/editable installs are the tested distribution mode. A standalone wheel with bundled configuration and fixtures has not been validated. `doctor` is an offline configuration check, not a live service-health certificate. The original PDF predates the audit and is not the active build specification.
