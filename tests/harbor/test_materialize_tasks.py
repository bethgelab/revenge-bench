from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from revenge_bench.harbor.inventory import build_inventory
from revenge_bench.harbor.materialize import materialize_tasks
from revenge_bench.harbor.prompt import game_for_task, render_task_instruction


REPO_ROOT = Path(__file__).resolve().parents[2]
TASKS = REPO_ROOT / "harbor" / "tasks"


def test_prompt_accepts_canonical_materialized_task_names():
    task = "robotrumble-gpt5-t14-qwen3-coder-plus-2025-09-23-e4f4e89c46f1-v0"

    assert game_for_task(task) == "robotrumble"
    assert render_task_instruction(task) == render_task_instruction(
        "robotrumble-gpt5-9aa3-v0"
    )


def test_materialize_tasks_creates_self_consistent_canonical_dirs(tmp_path: Path):
    out = tmp_path / "tasks"
    generated = materialize_tasks(
        tasks_root=out,
        template_root=TASKS,
        games=["robotrumble"],
        target_count=2,
    )
    inventory = build_inventory(games=["robotrumble"], target_count=2)

    assert [task.task_name for task in generated] == [
        entry["task_name"] for entry in inventory["tasks"]
    ]

    for task, entry in zip(generated, inventory["tasks"], strict=True):
        task_dir = out / entry["task_name"]
        assert task.path == task_dir
        assert task_dir.is_dir()
        assert not (task_dir / "environment" / "wheels").exists()
        assert not (task_dir / "environment" / "staging").exists()

        assert json.loads((task_dir / "task_config.json").read_text()) == {
            "benchmark_config": entry["normal_path_key"]["benchmark_config"],
            "target_index": entry["normal_path_key"]["target_index"],
        }
        assert json.loads((task_dir / "resolved_task.json").read_text()) == entry[
            "resolved"
        ]

        task_toml = (task_dir / "task.toml").read_text()
        assert f'name = "revengebench/{entry["task_name"]}"' in task_toml
        assert f'docker_image = "{entry["docker_image"]}"' in task_toml
        assert "robotrumble-gpt5-9aa3-v0:latest" not in task_toml

        build_context = (task_dir / "build_context.sh").read_text()
        assert 'revenge_bench.harbor.prompt "$(basename "$HERE")"' in build_context


def test_materialize_tasks_stage_populates_docker_copy_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    out = tmp_path / "tasks"

    def fake_run(cmd, *, cwd, check):
        assert cmd[:3] == ["uv", "build", "--wheel"]
        wheel_dir = Path(cmd[-1])
        wheel_dir.mkdir(parents=True, exist_ok=True)
        (wheel_dir / "revenge_bench-0.0.0-py3-none-any.whl").write_bytes(b"wheel")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    generated = materialize_tasks(
        tasks_root=out,
        template_root=TASKS,
        target_indices=[1],
        stage=True,
    )

    assert len(generated) == 5
    for task in generated:
        environment = task.path / "environment"
        assert list((environment / "wheels").glob("revenge_bench-*.whl"))
        assert (environment / "staging" / "target").exists()
        assert (environment / "staging" / "resolved_task.json").exists()

        dockerfile = (environment / "Dockerfile").read_text()
        for line in dockerfile.splitlines():
            if not line.startswith("COPY "):
                continue
            src = line.split()[1].rstrip("/")
            assert (environment / src).exists(), f"missing Docker COPY source {src}"


def test_materialize_tasks_can_select_one_target_index_per_game(tmp_path: Path):
    out = tmp_path / "tasks"
    generated = materialize_tasks(
        tasks_root=out,
        template_root=TASKS,
        target_indices=[1],
        include_wheels=False,
    )

    assert len(generated) == 5
    assert {task.game for task in generated} == {
        "battlesnake",
        "halite",
        "huskybench",
        "robocode",
        "robotrumble",
    }
    assert {task.target_index for task in generated} == {1}
    assert all("-t01-" in task.task_name for task in generated)


def test_materialize_tasks_preserves_halite_scorer_diagnostic_cap(tmp_path: Path):
    out = tmp_path / "tasks"
    generated = materialize_tasks(
        tasks_root=out,
        template_root=TASKS,
        games=["halite"],
        target_indices=[1],
    )

    assert len(generated) == 1
    scorer = generated[0].path / "environment" / "score_halite_submission.py"
    text = scorer.read_text()
    assert "MAX_NONZERO_DISTANCES = 200" in text
    assert "max_nonzero_distances=MAX_NONZERO_DISTANCES" in text
    assert "nonzero_distances_truncated" in text


def test_materialize_tasks_preserves_probe_trace_chown(tmp_path: Path):
    out = tmp_path / "tasks"
    generated = materialize_tasks(
        tasks_root=out,
        template_root=TASKS,
        games=["huskybench", "robocode"],
        target_indices=[1],
    )

    assert {task.game for task in generated} == {"huskybench", "robocode"}
    for task in generated:
        text = (task.path / "environment" / "run_probe_impl.py").read_text()
        assert "shutil.chown(out, user=\"agent\", group=\"agent\")" in text
        assert "os.chown(" not in text
