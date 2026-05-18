"""Image-variant detection for Codex-backed tournaments.

Pure dict-based tests; no docker, no arena init. We exercise the
`_uses_codex_learner` / `_image_variant_suffix` / `image_name` /
`sif_path` properties via a minimal CodeArena subclass instance.
"""

from revenge_bench.arenas.arena import CodeArena


class _StubArena(CodeArena):
    """Concrete CodeArena subclass that satisfies the abstract methods.

    The image-variant properties under test don't touch any arena
    behavior — we just need a non-abstract class so we can `__new__` it.
    """

    name = "BattleSnake"

    def execute_round(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def get_results(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def validate_code(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError


def _make_arena(players: list[dict]) -> CodeArena:
    """Build an arena instance bypassing __init__ side effects.

    The properties under test only read `self.config` and `self.name`,
    so we construct a bare object and stuff in those attributes.
    """
    obj = _StubArena.__new__(_StubArena)
    obj.config = {"players": players, "game": {"name": "BattleSnake"}}
    return obj


class TestUsesCodexLearner:
    def test_no_codex_player(self):
        arena = _make_arena([{"agent": "inverse"}, {"agent": "static"}])
        assert arena._uses_codex_learner is False

    def test_inverse_codex_player_present(self):
        arena = _make_arena([
            {"agent": "inverse_codex", "name": "learner"},
            {"agent": "static", "name": "target"},
        ])
        assert arena._uses_codex_learner is True

    def test_empty_players_list(self):
        arena = _make_arena([])
        assert arena._uses_codex_learner is False


class TestImageVariantSuffix:
    def test_suffix_when_codex_present(self):
        arena = _make_arena([{"agent": "inverse_codex"}])
        assert arena._image_variant_suffix == "-codex"

    def test_no_suffix_otherwise(self):
        arena = _make_arena([{"agent": "inverse"}])
        assert arena._image_variant_suffix == ""


class TestImageName:
    def test_codex_variant_name(self):
        arena = _make_arena([{"agent": "inverse_codex"}])
        assert arena.image_name == "revenge_bench/battlesnake-codex"

    def test_default_name(self):
        arena = _make_arena([{"agent": "inverse"}])
        assert arena.image_name == "revenge_bench/battlesnake"


class TestSifPath:
    def test_codex_sif_filename(self, tmp_path, monkeypatch):
        # Patch inspect.getfile to return a deterministic path so the
        # arena_file.parent computation is stable across environments.
        from revenge_bench.arenas import arena as arena_mod
        fake_arena_file = tmp_path / "battlesnake" / "BattleSnake.py"
        fake_arena_file.parent.mkdir()
        fake_arena_file.write_text("")
        monkeypatch.setattr(
            arena_mod.inspect, "getfile", lambda cls: str(fake_arena_file)
        )

        codex_arena = _make_arena([{"agent": "inverse_codex"}])
        assert codex_arena.sif_path.name == "battlesnake-codex.sif"

        plain_arena = _make_arena([{"agent": "inverse"}])
        assert plain_arena.sif_path.name == "battlesnake.sif"
