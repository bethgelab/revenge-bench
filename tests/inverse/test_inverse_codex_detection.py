"""main.py routing for inverse_codex configs.

`get_tournament_class`, `get_tournament_prefix`, and `_get_learner_model_name`
must treat `agent: inverse_codex` like `agent: inverse` for the fallback
detection path, while reading the model name from `config.codex.model`
instead of `config.model.model_name`.
"""

from main import (
    _get_learner_model_name,
    get_tournament_class,
    get_tournament_prefix,
)
from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
from revenge_bench.tournaments.inverse_strategy_interventionist import (
    InverseStrategyInterventionistTournament,
)
from revenge_bench.tournaments.pvp import PvpTournament


def _config(agent_type: str, *, with_explicit_type: str | None = None) -> dict:
    cfg: dict = {
        "players": [
            {
                "agent": agent_type,
                "name": "learner",
                "config": {
                    # mini-swe shape
                    "model": {"model_name": "openai/gpt-5"},
                    # codex shape
                    "codex": {"model": "openai/gpt-5-mini"},
                },
            },
        ],
    }
    if with_explicit_type is not None:
        cfg["tournament"] = {"type": with_explicit_type}
    return cfg


class TestGetTournamentClass:
    def test_inverse_codex_falls_through_to_inverse_tournament(self):
        cfg = _config("inverse_codex")
        assert get_tournament_class(cfg) is InverseStrategyTournament

    def test_inverse_codex_with_explicit_interventionist_type(self):
        cfg = _config("inverse_codex", with_explicit_type="interventionist")
        assert (
            get_tournament_class(cfg) is InverseStrategyInterventionistTournament
        )

    def test_legacy_inverse_still_routes(self):
        cfg = _config("inverse")
        assert get_tournament_class(cfg) is InverseStrategyTournament

    def test_non_inverse_agent_falls_through_to_pvp(self):
        cfg = _config("static")
        assert get_tournament_class(cfg) is PvpTournament


class TestGetTournamentPrefix:
    def test_inverse_codex_uses_inverse_prefix(self):
        assert get_tournament_prefix(_config("inverse_codex")) == "InverseStrategy"

    def test_inverse_codex_with_explicit_type_uses_type_prefix(self):
        assert (
            get_tournament_prefix(
                _config("inverse_codex", with_explicit_type="interventionist")
            )
            == "Interventionist"
        )


class TestGetLearnerModelName:
    def test_inverse_codex_reads_codex_model(self):
        assert _get_learner_model_name(_config("inverse_codex")) == "gpt-5-mini"

    def test_inverse_reads_minisweagent_model(self):
        assert _get_learner_model_name(_config("inverse")) == "gpt-5"

    def test_unknown_when_no_inverse_player(self):
        assert _get_learner_model_name(_config("static")) == "unknown"

    def test_inverse_codex_with_no_codex_block_falls_back(self):
        cfg = {
            "players": [
                {"agent": "inverse_codex", "name": "learner", "config": {}}
            ]
        }
        assert _get_learner_model_name(cfg) == "unknown"
