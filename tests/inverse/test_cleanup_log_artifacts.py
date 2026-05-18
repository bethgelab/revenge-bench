"""Unit tests for revenge_bench.scripts.inverse.cleanup_log_artifacts.repack_round_tar."""
from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest

from revenge_bench.scripts.inverse.cleanup_log_artifacts import repack_round_tar


def _build_round_tar(dst: Path, round_num: int = 0) -> Path:
    """Create a synthetic round tar with the standard mix of contents.

    `src` is built INSIDE `dst` (not in `dst.parent`) because pytest's
    tmp_path is per-test but tmp_path.parent is shared across tests in a
    session — putting src in the parent causes FileExistsError collisions
    between tests that use the same round_num.
    """
    src = dst / f"src_{round_num}"
    src.mkdir()
    rdir = src / str(round_num)
    rdir.mkdir()
    (rdir / "traces.json").write_text(json.dumps({"mean_distance": 0.5}))
    (rdir / "results.json").write_text(json.dumps([{"winner": "target"}]))
    code = rdir / "learner_code" / "workspace"
    code.mkdir(parents=True)
    (code / "binary").write_bytes(b"x" * 4096)  # large junk
    opp = rdir / "opp_0"
    opp.mkdir()
    (opp / "sim_0.json").write_text(json.dumps({"sim": 0}))

    tar_path = dst / f"round_{round_num}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(rdir, arcname=str(round_num))
    return tar_path


def _kept_file_names(tar_path: Path) -> list[str]:
    """Return sorted basenames of regular-file members.

    Helper to assert what the repack kept. Note: tarfile includes directory
    members in getnames() WITHOUT a trailing slash (e.g. '0/learner_code'),
    so filtering by name suffix is wrong — filter by m.isfile() instead.
    """
    with tarfile.open(tar_path, "r:gz") as tar:
        return sorted(m.name for m in tar.getmembers() if m.isfile())


def test_repack_keeps_only_traces_and_results(tmp_path):
    tar_path = _build_round_tar(tmp_path)
    bytes_before = tar_path.stat().st_size

    bytes_saved = repack_round_tar(tar_path)

    assert bytes_saved > 0
    assert _kept_file_names(tar_path) == ["0/results.json", "0/traces.json"]
    assert tar_path.stat().st_size < bytes_before


def test_repack_is_idempotent(tmp_path):
    tar_path = _build_round_tar(tmp_path)
    repack_round_tar(tar_path)
    size_after_first = tar_path.stat().st_size

    bytes_saved_second = repack_round_tar(tar_path)

    assert bytes_saved_second == 0
    assert tar_path.stat().st_size == size_after_first


def test_repack_preserves_round_number(tmp_path):
    """Round tar for round 3 must keep '3/' as the inner prefix, not hardcode '0/'."""
    tar_path = _build_round_tar(tmp_path, round_num=3)
    repack_round_tar(tar_path)
    assert _kept_file_names(tar_path) == ["3/results.json", "3/traces.json"]


def test_repack_handles_missing_traces_gracefully(tmp_path):
    """If a round tar has no traces.json (e.g. crashed mid-round), keep results.json
    and don't raise."""
    src = tmp_path / "src"
    src.mkdir()
    rdir = src / "0"
    rdir.mkdir()
    (rdir / "results.json").write_text("[]")
    (rdir / "opp_0").mkdir()
    (rdir / "opp_0" / "sim_0.json").write_text("{}")
    tar_path = tmp_path / "round_0.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(rdir, arcname="0")

    repack_round_tar(tar_path)
    assert _kept_file_names(tar_path) == ["0/results.json"]


def test_repack_does_not_match_misplaced_traces_json(tmp_path):
    """A 'traces.json' deeper in the tree (e.g. learner_code/.../traces.json) must
    NOT make the tar look already-minimal, and must NOT be kept by the repack."""
    src = tmp_path / "src"
    src.mkdir()
    rdir = src / "0"
    rdir.mkdir()
    (rdir / "traces.json").write_text(json.dumps({"mean_distance": 0.5}))
    (rdir / "results.json").write_text("[]")
    code = rdir / "learner_code" / "workspace"
    code.mkdir(parents=True)
    # Pathological filename collision — agent's workspace happens to have a
    # file literally named 'traces.json'. Must NOT be kept by repack.
    (code / "traces.json").write_text("not the real traces")
    tar_path = tmp_path / "round_0.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(rdir, arcname="0")

    repack_round_tar(tar_path)
    assert _kept_file_names(tar_path) == ["0/results.json", "0/traces.json"]


def test_cli_dryrun_does_not_modify(tmp_path):
    # Build a fake pool: <pool>/battlesnake/target<hash>/seed42/{players/learner/, rounds/}
    pool = tmp_path / "fake_pool_20260101_000000"
    seed = pool / "battlesnake" / "targetabcdef123456" / "seed42"
    (seed / "players" / "learner").mkdir(parents=True)
    (seed / "players" / "learner" / "changes_r1.json").write_text("x" * 100)
    (seed / "rounds").mkdir()
    tar_path = _build_round_tar(seed / "rounds", round_num=0)

    bytes_before_changes = (seed / "players" / "learner" / "changes_r1.json").stat().st_size
    bytes_before_tar = tar_path.stat().st_size

    from revenge_bench.scripts.inverse.cleanup_log_artifacts import main
    rc = main([str(pool), "--tier", "both"])  # no --apply

    assert rc == 0
    assert (seed / "players" / "learner" / "changes_r1.json").stat().st_size == bytes_before_changes
    assert tar_path.stat().st_size == bytes_before_tar


def test_cli_apply_tier1_deletes(tmp_path):
    pool = tmp_path / "fake_pool_20260101_000000"
    seed = pool / "battlesnake" / "targetabcdef123456" / "seed42"
    (seed / "players" / "learner").mkdir(parents=True)
    f = seed / "players" / "learner" / "changes_r1.json"
    f.write_text("x" * 100)

    from revenge_bench.scripts.inverse.cleanup_log_artifacts import main
    rc = main([str(pool), "--tier", "1", "--apply"])
    assert rc == 0
    assert not f.exists()
