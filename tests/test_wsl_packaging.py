from __future__ import annotations

import json
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
    installer = (WSL / "install.sh").read_text(encoding="utf-8")
    for key in ("WILLFLY_PIPELINE_CONFIG", "WILLFLY_PIPELINE_STATE_DB", "WILLFLY_SIGNALS_FILE"):
        assert f"^{key}=.*" in installer


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


def test_wsl_installer_materializes_all_generated_paths(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {
        "HOME": str(home),
        "WILLFLY_PROJECT_DIR": str(ROOT),
        "WILLFLY_STATE_DIR": str(tmp_path / "state"),
        "WILLFLY_PYTHON": sys.executable,
        "WILLFLY_SKIP_PACKAGE_INSTALL": "1",
    }
    result = _run(["bash", str(WSL / "install.sh")], env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    generated = (home / ".config" / "willfly" / "willfly.env").read_text(encoding="utf-8")
    assert "/path/to" not in generated and "/home/user" not in generated
    runtime_pipeline = home / ".local" / "share" / "willfly" / "pipeline.json"
    assert f'WILLFLY_PIPELINE_CONFIG="{runtime_pipeline}"' in generated
    assert f'WILLFLY_SIGNALS_FILE="{tmp_path / "state" / "pipeline" / "signals-latest.json"}"' in generated
    pipeline = json.loads(runtime_pipeline.read_text(encoding="utf-8"))
    assert pipeline["paths"]["store_dir"] == str(tmp_path / "state" / "observatory")
    assert pipeline["paths"]["feedback_dir"] == str(tmp_path / "state" / "feedback")
    assert pipeline["paths"]["artifact_dir"] == str(tmp_path / "state" / "pipeline")


def test_wsl_installer_migrates_legacy_env_and_rejects_unsupported_runtime_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env_dir = home / ".config" / "willfly"
    env_dir.mkdir(parents=True)
    (env_dir / "willfly.env").write_text(
        "\n".join(
            [
                'WILLFLY_PROJECT_DIR="/path/to/willfly"',
                'WILLFLY_VENV="/home/user/.local/share/willfly/venv"',
                'WILLFLY_STATE_DIR="/home/user/.local/state/willfly"',
                'WILLFLY_SOURCE_CONFIG="/path/to/willfly/configs/sources/robinhood-chain-v0.1.json"',
                'WILLFLY_WATCHER_CONFIG="/path/to/willfly/configs/learning/watcher-v0.1.json"',
                'WILLFLY_PIPELINE_CONFIG="/path/to/willfly/configs/learning/pipeline-v0.1.json"',
                'WILLFLY_SIGNALS_FILE="/home/user/.local/state/willfly/pipeline/signals-latest.json"',
                'WILLFLY_TRAIN_DATA_ROOT="/home/user/.local/state/willfly/connectome"',
                'WILLFLY_TRAIN_REPORT_DIR="/home/user/.local/state/willfly/training"',
                'WILLFLY_TRAIN_LATEST_REPORT="/home/user/.local/state/willfly/training/candidate-latest.json"',
                'WILLFLY_TRAIN_CHECKPOINT_DIR="/home/user/.local/state/willfly/training/checkpoints"',
                'WILLFLY_EVALUATION_REPORT_DIR="/home/user/.local/state/willfly/evaluation"',
                'WILLFLY_EVALUATION_LATEST_REPORT="/home/user/.local/state/willfly/evaluation/evaluation-latest.json"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = {
        "HOME": str(home),
        "WILLFLY_PROJECT_DIR": str(ROOT),
        "WILLFLY_STATE_DIR": str(tmp_path / "state"),
        "WILLFLY_PYTHON": sys.executable,
        "WILLFLY_SKIP_PACKAGE_INSTALL": "1",
    }
    result = _run(["bash", str(WSL / "install.sh")], env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    generated = (env_dir / "willfly.env").read_text(encoding="utf-8")
    assert "/path/to" not in generated and "/home/user" not in generated
    assert f'WILLFLY_TRAIN_DATA_ROOT="{tmp_path / "state" / "connectome"}"' in generated
    assert f'WILLFLY_TRAIN_REPORT_DIR="{tmp_path / "state" / "training"}"' in generated
    assert f'WILLFLY_EVALUATION_REPORT_DIR="{tmp_path / "state" / "evaluation"}"' in generated
    rejected = _run(
        ["bash", str(WSL / "install.sh"), "--dry-run"],
        env=env | {"WILLFLY_RUNTIME_DIR": str(tmp_path / "unsupported-runtime")},
    )
    assert rejected.returncode != 0
    assert "unsupported" in rejected.stderr
