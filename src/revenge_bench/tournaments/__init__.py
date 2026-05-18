"""Tournament implementations for CodeClash."""

from revenge_bench.tournaments.tournament import AbstractTournament
from revenge_bench.tournaments.pvp import PvpTournament

# Lazy import to avoid circular dependency with agents module
def __getattr__(name):
    if name == "InverseStrategyTournament":
        from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
        return InverseStrategyTournament
    if name == "InverseStrategyInterventionistTournament":
        from revenge_bench.tournaments.inverse_strategy_interventionist import InverseStrategyInterventionistTournament
        return InverseStrategyInterventionistTournament
    if name == "BayesianProgramInferenceTournament":
        from revenge_bench.tournaments.bayesian_program_inference import BayesianProgramInferenceTournament
        return BayesianProgramInferenceTournament
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "AbstractTournament",
    "PvpTournament",
    "InverseStrategyTournament",
    "InverseStrategyInterventionistTournament",
    "BayesianProgramInferenceTournament",
]
