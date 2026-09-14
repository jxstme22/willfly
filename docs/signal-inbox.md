# Signal inbox and position view

B6 adds a read-only signal inbox to the local API and terminal dashboard. It
renders the versioned model ID/version, proposed versus displayed action,
expiry, confidence semantics, evidence references, manual-only status and
reasons. Research-only or unsupported spot/LP readiness gates display an
abstain action; expired and invalidated proposals also abstain. The original
proposal is not mutated.

The API exposes `GET /signals` for paginated inbox entries, `GET /positions`
for observed LP ownership states, `GET /training` for the current
training/waiting summary, and `GET /models` for an optional attached model
registry. The existing `GET /dashboard` includes signal, position,
manual-link status, training and model-registry sections; `/signals` exposes
the same manual-link status in its JSON rows.

For a local controlled run, `willfly serve --signals-file PATH` loads a typed
`willfly.signal-snapshot.v0.1` JSON bundle containing predictions, proposals,
readiness gates, training state, optional manual actions and optional
public-wallet activities. The file is validated through the domain contracts;
manual links are recomputed conservatively at load time. It is display-only
and cannot enable signing or broadcast. Without the file (or a populated
application store), the inbox truthfully shows no signals.

An optional `--model-registry` plus `--initial-active-version` on `serve`
attaches the local registry as read-only model state. The server refuses a
missing registry file or missing initial version rather than creating hidden
model state during a display run.

The lab-output boundary is explicit: `signal-build` consumes a versioned model
output bundle containing template predictions, output values, a model/run
identity and an action mapping. It writes the same signal snapshot schema that
`serve` reads. Generated confidence is `unavailable` until calibrated evidence
is supplied; proposals remain `research_only` and manual-only.

```text
.venv/bin/willfly signal-build \
  --input /path/to/model-output.json \
  --output /path/to/signals.json
```

It remains a local read-only surface: there is no signer, broadcast, funding
control, or automatic execution. B6 fixture checks prove rendering and gates;
live model promotion, complete economic qualification and manual-action
linkage remain open for B7/B8/B10.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_signal_inbox.py tests/test_ui.py tests/test_api.py
```
