# Private repository publication

13 September 2026

The user authorized review, corrections, a commit and push to a new private repository. Target: `jxstme22/willfly`, under the account verified by GitHub CLI. The name was checked before creation. Publication succeeded. GitHub independently reported `isPrivate: true` before upload, and its branch API returned the same commit SHA as the local reviewed baseline.

Pre-publication checks:

- All 100 tests pass in the original environment and in a new Python 3.12 environment installed from the pinned dependency files.
- The installed `willfly fixture-check` verifies 16 synthetic contract/fixture checks.
- Both task catalogues pass dependency, DONE evidence and generated Markdown checks.
- Candidate file scan found no matches for common GitHub/API credentials, private-key headers, AWS access-key IDs or URL-embedded passwords. This is a bounded heuristic scan, not proof that every possible secret format is absent.
- Temporary probe output/renderings, environments, raw datasets, caches and generated model artifacts are excluded by `.gitignore`. The shadow artifact directory includes only its README marker. Source model code remains included.
- The historical research Markdown and PDF are intentionally preserved; README marks the PDF and earlier handoffs as historical.

CI definition: Python 3.12 on Ubuntu, pinned official checkout/setup actions, dependency installation, full tests, fixture validation and planning validation. The baseline CI run completed successfully on GitHub.

The published project is a reviewed research prototype with explicit open audit findings. Publication does not establish operational or financial readiness.

## Verified remote evidence

- Repository: [jxstme22/willfly](https://github.com/jxstme22/willfly), private.
- Branch: `codex/astra-reviewed-baseline`.
- Reviewed baseline commit: `e1f06133f1aceb16d633258471e00ad5e650d96e`.
- Baseline CI: [Python checks, successful](https://github.com/jxstme22/willfly/actions/runs/34735860670).
- The reviewed baseline contains 160 tracked files; the checked file inventory includes no temporary probes, raw data, Parquet datasets, SQLite databases, bytecode or environment directories.
- A follow-up documentation commit records this evidence and marks M0-03 accepted. Its parent is the reviewed/tested baseline above; the final remote HEAD is reported to the user after pushing.
