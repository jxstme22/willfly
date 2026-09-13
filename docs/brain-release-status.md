# Brain product release status

The current release status is `research_release_only`. The signal contracts,
read-only inbox, public-wallet observer, feedback queue, checkpointable
connectome laboratory, evaluation registry and learning watcher are available
as implemented mechanics. The MaleCNS v1.0 source is verified for the bounded
subset loader, not claimed as a whole-brain model.

Spot and LP recommendations are not qualified. Live labelled training,
forward evaluation/calibration, public-wallet coverage, manual-feedback
demonstration, exact spot/LP economic gates, and a real zero-personal-trade
continuous-learning interval remain open. Automatic signing, funding and
transaction execution are disabled.

The status matrix is reproducible offline:

```text
.venv/bin/python scripts/check_brain_release.py
.venv/bin/python -m pytest -q tests/test_brain_release.py
```
