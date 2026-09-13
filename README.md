# Willfly

Read-only research software for a connectome-derived crypto decision agent.

**Current build authority:** [Astra audit](docs/reports/astra-deep-audit.md), [next roadmap](docs/next-build-roadmap.md), [26-task JSON backlog](docs/next-build-tasks.json), and [Muse Sparks 1.3 handoff](docs/muse-sparks-1.3-handoff.md). The earlier handoffs and PDF are historical snapshots.

**Current direction — 13 September 2026:** Robinhood Chain first; discover new launches and pairs, study memecoin trajectories, and choose between spot trading, selective liquidity provision, waiting and exiting. Expansion to other chains is a later possibility.

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

The direction remains Robinhood launch discovery, spot decisions and separately validated LP. The audit found useful components but no operational end-to-end platform. Capture/backfill CLI commands currently produce plans with exit 3; the HTTP server starts with an empty store; shadow does not consume collected observations. The local suite now has 100 passing tests, including audit regressions. V4 replay, LP accounting, portfolio evaluation, trade-route attribution and live evidence still need the work listed in the audit. LP and funded execution remain disabled. A biological advantage is unproven.

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
```

The source-tree equivalent is `PYTHONPATH=src python3 -m willfly ...`. `doctor`
is intentionally read-only and reports an open launch-source gate until Pons V2
history and ABI evidence are complete.

## Verify and maintain planning

```text
.venv/bin/python -m pytest
python3 scripts/render_planning.py
python3 scripts/check_planning.py
```

JSON is canonical; rendering never resets statuses. Source-checkout/editable installs are the tested distribution mode. A standalone wheel with bundled configuration and fixtures has not been validated. `doctor` is an offline configuration check, not a live service-health certificate. The original PDF predates the audit and is not the active build specification.
