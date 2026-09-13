# Luna Extra High — audit repairs and continuing build loops

User-authorized sequence, 13 September 2026. Use `gpt-5.6-luna` with `xhigh` reasoning. This handoff is prepared in advance; it does not launch Luna. The executable work order is described in [the JSON loop plan](luna-build-loops.json), with concrete acceptance objectives G0–G5.

## Activation gate

Wait until DeepSeek finishes and stops writing. The coordinating reviewer then inspects its final commit/diff, reproduces claims and audits relevant code, integration behavior and evidence. Record findings in `docs/reports/deepseek-completion-audit.md` with severity, exact locations, reproduction, impact and required verification. That report is a planned output and must not be created as a fake passing audit now.

The coordinator assigns concrete repair findings to Luna and may record an
independent recheck checkpoint. Once the reviewed checkpoint is accepted, the
feature-build loops continue without a routine approval pause between slices.
The coordinator performs the next broad audit after the long authorized loops;
existing tests, summaries and DONE labels remain inputs to review, not proof
that the platform works perfectly.

Use the existing implementation task when it is confirmed idle and accessible; do not create another task automatically. Do not start an overlapping writer while DeepSeek runs. Use the user's final DeepSeek report/checkpoint as the completion signal; this document does not install a background watcher for the external model.

## Repair-stage prompt

```text
Use GPT Luna with Extra High reasoning to continue Willfly.
Read applicable repository instructions, README.md,
docs/brain-signal-product.md, docs/brain-product-tasks.json,
docs/next-build-tasks.json, docs/luna-build-loops.json,
docs/reports/astra-deep-audit.md and the coordinator's completed
docs/reports/deepseek-completion-audit.md.

First inspect current Git state. Preserve other work and be the sole
implementation writer. Repair the coordinator's findings in priority order,
with concrete regression/integration evidence. Fix root causes; never weaken
tests or completion gates merely to obtain green output. Record each repair,
its commit and verification. Record a repair checkpoint for the coordinator,
then continue into the dependency-ready feature-build stage. Do not wait for a
routine coordinator approval between build slices; preserve the checkpoint and
its open gates for the later broad audit. This review boundary is internal
coordination, not a request for routine user permission.
```

## Build-stage prompt

```text
Continue the authorized build loops using GPT Luna Extra High.
Work until the in-scope engineering and acceptance goals are actually met,
or record the exact external dependency that prevents a remaining gate.

The main product is a real-connectome model providing coin-entry, LP and exit
signals; the user executes manually through external tools; Willfly observes
wallet/position outcomes and learns from verified user, external-wallet and
historical evidence. Learning continues 24/7 without personal trades through
durable collection, outcome maturation, automatic candidate training and
evaluation. Qualified model promotion is separately versioned. A permanently
busy GPU is not required and unavailable data cannot produce invented labels.

Use B0–B10 for product priority and mapped M tasks for reused implementations
and economic/operational acceptance. Start actual biological-data loading and
offline training early; do not wait for every dashboard or economic task.
Conversely, do not call unfinished spot/LP math validated recommendations.
Keep the terminal design but do not expand generic monitoring at the expense
of the neural product. Target the user's Windows/WSL2 PC with 32 GB RAM and
RTX 4070 Ti; benchmark rather than promise whole-brain performance.

For each loop state a bounded objective, acceptance and target files; implement,
run relevant checks, review behavior, update JSON and logs, commit verified
changes and continue the next dependency-ready slice. Use the existing private
repository. Do not stage another writer's unfinished work. Record CI results
separately. Preserve original task IDs and historical evidence. Validate both
existing catalogues with scripts/check_planning.py, and validate B-task/loop
JSON identities, dependencies and references. Add ongoing validation coverage
for these new catalogues as part of implementation rather than claiming they
are already covered by the existing checker.

Do not stop after one small feature or ask routine permission between loops.
If external access is missing, continue independent work and keep affected
gates open. The 72-hour and 14-day windows need real elapsed evidence, and the
24/7 service needs actual installed infrastructure. Never turn fixture runs
into live acceptance or claim the service is running because it is packaged.

Automatic funded execution is outside this product version. No signing,
funding, paid subscriptions, restricted-source bypass, or extra agents/tasks.
Keep any unsupported adapter or LP capability explicitly unavailable.

At each phase checkpoint report what works, evidence, open findings and the
next objective. When session/usage limits intervene, preserve a restartable
checkpoint with exact commands and pending work; do not label it completion
or imply that an unscheduled background job will continue it.
```

## Completion meaning

The product is complete only when its declared functionality and evidence checks pass. Learning never promises continual improvement: bad candidate models must fail promotion. Spot, LP, connectome correctness, predictive value, manual feedback and operational uptime have distinct acceptance records. Negative scientific results are valid findings, not reasons to manipulate thresholds or claim a financial advantage.
