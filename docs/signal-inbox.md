# Signal inbox and position view

B6 adds a read-only signal inbox to the local API and terminal dashboard. It
renders the versioned model ID/version, proposed versus displayed action,
expiry, confidence semantics, evidence references, manual-only status and
reasons. Research-only or unsupported spot/LP readiness gates display an
abstain action; expired and invalidated proposals also abstain. The original
proposal is not mutated.

The API exposes `GET /signals` for paginated inbox entries, `GET /positions`
for observed LP ownership states, and `GET /training` for the current
training/waiting summary. The existing `GET /dashboard` includes signal,
position and training sections.

For a local controlled run, `willfly serve --signals-file PATH` loads a typed
`willfly.signal-snapshot.v0.1` JSON bundle containing predictions, proposals,
readiness gates and training state. The file is validated through the domain
contracts and is display-only; it cannot enable signing or broadcast. Without
the file (or a populated application store), the inbox truthfully shows no
signals.

It remains a local read-only surface: there is no signer, broadcast, funding
control, or automatic execution. B6 fixture checks prove rendering and gates;
live model promotion, complete economic qualification and manual-action
linkage remain open for B7/B8/B10.

Reproduction:

```text
.venv/bin/python -m pytest -q tests/test_signal_inbox.py tests/test_ui.py tests/test_api.py
```
