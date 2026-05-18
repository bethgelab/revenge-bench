from revenge_bench.cli import (
    _get_learner_model_name,
    _get_player_source_path,
    _override_target_source,
    get_tournament_class,
    get_tournament_prefix,
    main_cli,
    run_strategy_pool,
    write_benchmark_summary,
)

__all__ = [
    "_get_learner_model_name",
    "_get_player_source_path",
    "_override_target_source",
    "get_tournament_class",
    "get_tournament_prefix",
    "main_cli",
    "run_strategy_pool",
    "write_benchmark_summary",
]


if __name__ == "__main__":
    main_cli()
