from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
WSL = ROOT / "deploy" / "wsl"


def _run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(command, cwd=ROOT, env=merged, text=True, capture_output=True, check=False)


def test_wsl_shell_and_systemd_files_parse() -> None:
    for script in ("install.sh", "run-service.sh", "smoke.sh", "willflyctl"):
        result = _run(["bash", "-n", str(WSL / script)])
        assert result.returncode == 0, result.stderr

    units = sorted((WSL / "systemd").glob("*.service")) + sorted((WSL / "systemd").glob("*.timer"))
    assert len(units) == 11
    for unit in units:
        text = unit.read_text(encoding="utf-8")
        if unit.suffix == ".service":
            assert "EnvironmentFile=%h/.config/willfly/willfly.env" in text
            assert "NoNewPrivileges=true" in text
            assert "ExecStart=" in text
        else:
            assert "[Timer]" in text and "Unit=willfly-" in text
    assert "MemoryMax=24G" in (WSL / "systemd" / "willfly-train.service").read_text(encoding="utf-8")


def test_wsl_offline_smoke_path() -> None:
    result = _run(["bash", str(WSL / "smoke.sh")], env={"WILLFLY_PYTHON": sys.executable})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WSL2 offline smoke: passed" in result.stdout


def test_capture_dry_run_is_bounded_and_does_not_create_state(tmp_path: Path) -> None:
    env = {
        "WILLFLY_ENV_FILE": str(tmp_path / "missing.env"),
        "WILLFLY_PROJECT_DIR": str(ROOT),
        "WILLFLY_PYTHON": sys.executable,
        "WILLFLY_STATE_DIR": str(tmp_path / "state"),
        "WILLFLY_SOURCE_CONFIG": str(ROOT / "configs/sources/robinhood-chain-v0.1.json"),
        "WILLFLY_WATCHER_CONFIG": str(ROOT / "configs/learning/watcher-v0.1.json"),
        "WILLFLY_SHADOW_CONFIG": str(ROOT / "configs/shadow/config.json"),
        "WILLFLY_CAPTURE_START_BLOCK": "61692800",
        "WILLFLY_CAPTURE_MAX_BLOCKS": "500",
    }
    result = _run(["bash", str(WSL / "run-service.sh"), "--dry-run", "capture"], env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "backfill" in result.stdout
    assert "61692800" in result.stdout
    assert not (tmp_path / "state").exists()
