"""
Bayesian Program Inference Tournament.

A passive baseline that generates N candidate policies via independent LLM calls,
evaluates each on passive traces, then selects the best using Bayesian-style scoring.

Pipeline:
1. Round 0: Simulate target vs opponent → passive traces (same as base class)
2. Generate N candidate policies: run N independent edit phases (reset mode)
   - Diversity promoted via: opponent subsampling, diverse prompting
3. Evaluate each candidate on round 0 traces → compute mean_distance
4. Score: score_i = -beta * mean_distance_i - alpha * complexity_i
5. Softmax normalization → posterior weights
6. MAP selection: pick argmax

This baseline uses ONLY passive observations — no active probing.
"""

import json
import math
import random
import shutil
from pathlib import Path
from typing import Any

from revenge_bench.constants import DIR_LOGS
from revenge_bench.tournaments.inverse_strategy import InverseStrategyTournament
from revenge_bench.utils.environment import copy_from_container, copy_to_container, create_file_in_container


class BayesianProgramInferenceTournament(InverseStrategyTournament):
    """
    Tournament that generates N candidate policies and selects the best
    using distance-based Bayesian scoring.

    Config additions (under tournament):
        num_candidates: int       — Number of candidate policies to generate (default: 5)
        beta: float               — Distance penalty weight (default: 10.0)
        alpha: float              — Complexity penalty weight (default: 0.01)

    Diversity config (under tournament.diversity):
        bootstrap_observations: bool           — If true, each candidate sees a bootstrap-resampled view of opponents
        diverse_prompts: list[str] | null      — Approach hints injected per candidate (cycled)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        tournament_cfg = self.config.get("tournament", {})
        self.num_candidates: int = tournament_cfg.get("num_candidates", 5)
        self.beta: float = tournament_cfg.get("beta", 1.0)
        self.alpha: float = tournament_cfg.get("alpha", 0.01)

        # ── Diversity configuration ──
        diversity_cfg = tournament_cfg.get("diversity", {})
        self.bootstrap_observations: bool = diversity_cfg.get(
            "bootstrap_observations", False
        )
        self.diverse_prompts: list[str] | None = diversity_cfg.get(
            "diverse_prompts", None
        )
        self._diversity_rng = random.Random(42)

    def get_metadata(self) -> dict:
        metadata = super().get_metadata()
        metadata["tournament_type"] = "bayesian_program_inference"
        metadata["num_candidates"] = self.num_candidates
        metadata["beta"] = self.beta
        metadata["alpha"] = self.alpha
        metadata["diversity"] = {
            "bootstrap_observations": self.bootstrap_observations,
            "diverse_prompts": self.diverse_prompts,
        }
        return metadata

    def run(self, *, opponents: list[Path] | None = None) -> None:
        """Main execution: generate N candidates, score, select best."""
        try:
            # ── Step 1: Run simulation (round 0) to get passive traces ──
            if opponents:
                self._run_multi_opponent_sim(0, opponents)
            else:
                self.run_simulation_phase(0)
            self.run_evaluation_phase(0)

            # ── Step 1b: Save initial commit hash for clean resets ──
            self._initial_commit = self._get_learner_initial_commit()

            # ── Step 1c: Tag initial state (normally done by pre_run_hook on first call) ──
            try:
                self.learner_agent._tag_round(0)
            except Exception:
                pass  # Tag may already exist if container was reused

            # ── Step 1d: Prepare per-candidate opponent subsets for diversity ──
            self._opponent_subsets = self._build_opponent_subsets(opponents)

            # ── Step 2: Generate N candidate policies ──
            candidates_dir = self.local_output_dir / "candidates"
            candidates_dir.mkdir(parents=True, exist_ok=True)

            candidate_results: list[dict[str, Any]] = []

            for candidate_idx in range(self.num_candidates):
                self.logger.info(
                    f"Generating candidate {candidate_idx + 1}/{self.num_candidates}"
                )

                # Deliver per-candidate observation (with subsampled opponents)
                self._deliver_candidate_observation(candidate_idx)

                result = self._generate_candidate(
                    candidate_idx, candidates_dir, opponents
                )
                candidate_results.append(result)
                self.logger.info(
                    f"  Candidate {candidate_idx}: "
                    f"mean_dist={result.get('mean_distance', 'N/A')}, "
                    f"complexity={result.get('complexity', 'N/A')}"
                )

            # ── Step 3: Bayesian scoring and selection ──
            selection = self._bayesian_select(candidate_results)
            self._metadata["candidate_results"] = candidate_results
            self._metadata["selection"] = selection

            # ── Step 4: Install winner and do final evaluation ──
            winner_idx = selection["selected_idx"]
            winner_dir = candidates_dir / f"candidate_{winner_idx}" / "workspace"

            if winner_dir.exists():
                self._install_winner(winner_dir)
                self.logger.info(
                    f"Selected candidate {winner_idx} "
                    f"(score={selection['scores'][winner_idx]:.4f}, "
                    f"weight={selection['weights'][winner_idx]:.4f})"
                )

                # Re-load winner's module for final evaluation
                # (candidate eval loop leaves _learner_move_func pointing to last candidate)
                winner_code_dir = candidates_dir / f"candidate_{winner_idx}"
                self._load_learner_module(winner_code_dir)

                # Final evaluation on round 0 traces (confirms distance)
                round_dir = self.game.log_local / "rounds" / str(0)
                final_summary = self._process_traces(round_dir, round_num=1)
                if final_summary:
                    self._metadata.setdefault("distance_history", {})[1] = (
                        final_summary.get("mean_distance")
                    )
                    self._metadata.setdefault("submission_status_per_round", {})[1] = "ok"
            else:
                self.logger.warning(
                    f"Winner directory not found: {winner_dir}. "
                    f"All candidates may have failed."
                )
                self._metadata.setdefault("distance_history", {})[1] = None
                self._metadata.setdefault("submission_status_per_round", {})[1] = (
                    "all_candidates_failed"
                )

            self._save()
        finally:
            self.end()

    def _generate_candidate(
        self,
        candidate_idx: int,
        candidates_dir: Path,
        opponents: list[Path] | None,
    ) -> dict[str, Any]:
        """Generate a single candidate policy via one edit phase.

        Returns a result dict with distance, complexity, and code path.

        Isolation guarantees:
        - Workspace is hard-reset to initial commit before each candidate
        - A fresh ClashAgent + LLM model is created inside run() each time
        - Trajectory is saved with candidate-specific naming
        - Observations in /logs/ persist (outside /workspace git)

        Diversity mechanisms:
        - Diverse prompting: approach hint appended to observation file
        """
        result: dict[str, Any] = {
            "idx": candidate_idx,
            "total_distance": None,
            "mean_distance": None,
            "complexity": None,
            "code_path": None,
            "status": "failed",
            "diverse_prompt": None,
        }

        # Use a unique round number per candidate so trajectories don't collide
        candidate_round = candidate_idx + 1

        try:
            # Hard-reset workspace to initial commit (clean slate for each candidate)
            self._reset_learner_code()

            # ── Apply diverse prompt hint ──
            if self.diverse_prompts:
                hint = self.diverse_prompts[candidate_idx % len(self.diverse_prompts)]
                result["diverse_prompt"] = hint
                self._inject_diversity_hint(candidate_idx, hint)
                self.logger.info(f"  Candidate {candidate_idx}: hint='{hint[:50]}...'")

            # pre_run_hook equivalent — same structure, skip the tag that would conflict
            self._candidate_pre_run_hook(candidate_round)

            # Run the edit phase (MiniSWEAgent.run creates a fresh ClashAgent,
            # saves trajectory to learner_r{round}.traj.json, records agent_stats)
            self.learner_agent.run()

            # post_run_hook equivalent — commit + save changes, skip push + conflicting tag
            self._candidate_post_run_hook(candidate_round)

            # Copy candidate code from container
            candidate_dir = candidates_dir / f"candidate_{candidate_idx}"
            candidate_dir.mkdir(parents=True, exist_ok=True)
            copy_from_container(
                self.learner_agent.environment,
                Path("/workspace"),
                candidate_dir,
            )

            # Copy trajectory to candidate dir (also lives in players/ dir)
            traj_src = (
                self.learner_agent.game_context.log_local
                / "players"
                / self.learner_agent.name
                / f"{self.learner_agent.name}_r{candidate_round}.traj.json"
            )
            if traj_src.exists():
                traj_dst = candidate_dir / "trajectory.json"
                shutil.copy2(traj_src, traj_dst)

            # Save the diff (what did the agent change from initial code?)
            diff_out = self.learner_agent.environment.execute(
                f"cd /workspace && git diff {self._initial_commit}"
            )
            diff_text = diff_out.get("output", "")
            if diff_text.strip():
                (candidate_dir / "changes.diff").write_text(diff_text)

            # Evaluate candidate on round 0 traces
            eval_result = self._evaluate_candidate(candidate_dir)
            if eval_result and eval_result.get("total_actions", 0) > 0:
                result["total_distance"] = eval_result.get("total_distance")
                result["mean_distance"] = eval_result.get("mean_distance")
                result["total_actions"] = eval_result.get("total_actions")
                result["status"] = "ok"
            elif eval_result:
                # Module loaded but produced 0 action comparisons — treat as failed
                result["error"] = "evaluation produced 0 actions (module likely broken)"
                self.logger.warning(
                    f"Candidate {candidate_idx}: evaluation returned 0 actions"
                )

            # Compute complexity (line count of submission)
            result["complexity"] = self._compute_complexity(candidate_dir)
            result["code_path"] = str(candidate_dir)

            # Record agent stats for this candidate
            agent_stats = self.learner_agent._metadata.get("agent_stats", {}).get(
                candidate_round, {}
            )
            result["agent_stats"] = agent_stats

        except Exception as e:
            self.logger.warning(
                f"Candidate {candidate_idx} generation failed: {e}"
            )
            import traceback
            traceback.print_exc()
            result["error"] = str(e)

        return result

    def _candidate_pre_run_hook(self, candidate_round: int) -> None:
        """Pre-run setup for a candidate (mirrors Player.pre_run_hook).

        Same as pre_run_hook but:
        - Skips _tag_round(0) — already done once in run()
        - Sets round to candidate-specific value for unique trajectory naming
        """
        self.learner_agent.game_context.round = candidate_round
        self.learner_agent.game_context.distance_history = (
            self._metadata.get("distance_history", {})
        )
        self.learner_agent.game_context.evaluation_errors = (
            self._metadata.get("evaluation_errors", {})
        )

    def _candidate_post_run_hook(self, candidate_round: int) -> None:
        """Post-run cleanup for a candidate (mirrors Player.post_run_hook).

        Same as post_run_hook but:
        - Uses standard round tag naming so _write_changes_to_file works
        - Deletes the tag afterward (before next candidate resets the workspace)
        - Skips git push (not needed for local candidate evaluation)
        """
        # Commit changes
        for cmd in [
            "git add -A",
            f"git commit --allow-empty -m 'Candidate {candidate_round} submission'",
        ]:
            self.learner_agent.environment.execute(f"cd /workspace && {cmd}")

        # Create standard round tag so _write_changes_to_file / _get_round_diff works
        tag_name = self.learner_agent._get_round_tag_name(candidate_round)
        self.learner_agent.environment.execute(
            f"cd /workspace && git tag -a {tag_name} -m 'Candidate {candidate_round}'"
        )
        self.learner_agent._metadata.setdefault("round_tags", {})[candidate_round] = tag_name

        # Write changes file (produces changes_r{N}.json in players/{name}/)
        self.learner_agent._write_changes_to_file(round=candidate_round)

    def _get_learner_initial_commit(self) -> str:
        """Get the initial commit hash from the learner's container."""
        out = self.learner_agent.environment.execute(
            "cd /workspace && git rev-parse HEAD"
        )
        return out["output"].strip().splitlines()[-1]

    def _deliver_traces_to_learner(self, round_num: int, prev_round: int) -> None:
        """Deliver observation data to the learner's container."""
        if self.observation_mode == "nl_summary":
            self._deliver_nl_observation(round_num, prev_round)
        else:
            copy_to_container(
                self.learner_agent.environment,
                self.game.log_local / "rounds" / str(prev_round),
                DIR_LOGS / "rounds" / str(prev_round),
            )

    def _reset_learner_code(self) -> None:
        """Hard-reset learner's workspace to the initial commit.

        Uses git reset --hard to ensure no state leaks between candidates.
        The /logs/ directory (outside workspace) is preserved so observations
        remain available.
        """
        self.learner_agent.environment.execute(
            f"cd /workspace && git reset --hard {self._initial_commit} && git clean -fd"
        )

    def _evaluate_candidate(self, candidate_dir: Path) -> dict[str, Any] | None:
        """Evaluate candidate on round 0 traces using the game-specific handler.

        Uses the same evaluation path as the main pipeline: _process_traces
        dispatches to the appropriate game handler (compiled binary for Halite,
        class-based for HuskyBench, JS subprocess for RobotRumble, etc.).

        The container still holds this candidate's code at call time, so
        _setup_learner_for_eval (called inside each handler) will copy the
        correct code.

        Returns trace summary dict or None on failure.
        """
        round_dir = self.game.log_local / "rounds" / str(0)
        try:
            summary = self._process_traces(round_dir, round_num=0)
            # Save per-candidate evaluation alongside its code
            if summary:
                eval_file = candidate_dir / "eval_result.json"
                eval_file.write_text(json.dumps(summary, indent=2))
            return summary
        except Exception as e:
            self.logger.warning(f"Evaluation failed for {candidate_dir}: {e}")
            return None

    def _compute_complexity(self, candidate_dir: Path) -> float:
        """Compute code complexity as num_lines / 100."""
        workspace_dir = candidate_dir / "workspace"
        if not workspace_dir.exists():
            workspace_dir = candidate_dir

        submission = self.game.submission
        submission_py = workspace_dir / submission
        if not submission_py.exists():
            submission_py = workspace_dir / "main.py"

        if not submission_py.exists():
            return 0.0

        try:
            lines = submission_py.read_text().splitlines()
            # Count non-empty, non-comment lines
            code_lines = [
                l for l in lines
                if l.strip() and not l.strip().startswith("#")
            ]
            return len(code_lines) / 100.0
        except Exception:
            return 0.0

    def _bayesian_select(
        self, candidate_results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Apply Bayesian scoring and MAP selection.

        score_i = -beta * mean_distance_i - alpha * complexity_i
        weight_i = exp(score_i) / sum_j exp(score_j)
        selected = argmax_i score_i

        Returns dict with scores, weights, and selected index.
        """
        scores: list[float] = []
        for r in candidate_results:
            if r["status"] != "ok" or r["mean_distance"] is None:
                # Failed candidates get -inf score
                scores.append(float("-inf"))
                continue

            distance = r["mean_distance"]
            complexity = r.get("complexity", 0.0) or 0.0
            score = -self.beta * distance - self.alpha * complexity
            scores.append(score)

        # Softmax normalization (numerically stable)
        weights = self._softmax(scores)

        # MAP selection
        selected_idx = max(range(len(scores)), key=lambda i: scores[i])

        return {
            "scores": scores,
            "weights": weights,
            "selected_idx": selected_idx,
            "selected_score": scores[selected_idx],
            "selected_weight": weights[selected_idx],
            "beta": self.beta,
            "alpha": self.alpha,
        }

    @staticmethod
    def _softmax(scores: list[float]) -> list[float]:
        """Numerically stable softmax over scores."""
        # Filter out -inf for max computation
        finite_scores = [s for s in scores if s != float("-inf")]
        if not finite_scores:
            # All failed — uniform over all
            n = len(scores)
            return [1.0 / n] * n

        max_score = max(finite_scores)
        exp_scores = []
        for s in scores:
            if s == float("-inf"):
                exp_scores.append(0.0)
            else:
                exp_scores.append(math.exp(s - max_score))

        total = sum(exp_scores)
        if total == 0:
            n = len(scores)
            return [1.0 / n] * n

        return [e / total for e in exp_scores]

    def _install_winner(self, winner_workspace: Path) -> None:
        """Copy the winning candidate's code back to the learner container."""
        # Clear workspace and copy winner's files
        self.learner_agent.environment.execute("rm -rf /workspace/*")
        copy_to_container(
            self.learner_agent.environment,
            winner_workspace,
            Path("/workspace"),
        )

    # ──────────────────────────────────────────────────────────────────────
    #  Diversity mechanisms
    # ──────────────────────────────────────────────────────────────────────

    def _build_opponent_subsets(
        self, opponents: list[Path] | None
    ) -> list[list[int]]:
        """Pre-compute per-candidate opponent index subsets for observation diversity.

        Uses bootstrap resampling: each candidate sees the same NUMBER of opponent
        traces as evaluation (n_opps), but drawn with replacement so the distribution
        differs per candidate. Some opponents may appear multiple times while others
        are absent, creating diverse training signals without reducing sample count.

        If bootstrap_observations is disabled, all candidates share the identical
        full set (no diversity).
        """
        if opponents is None or not self.bootstrap_observations:
            return [list(range(len(opponents))) if opponents else []]

        n_opps = len(opponents)
        subsets = []
        for _ in range(self.num_candidates):
            # Bootstrap: sample n_opps indices WITH replacement
            subset = sorted(self._diversity_rng.choices(range(n_opps), k=n_opps))
            subsets.append(subset)
        return subsets

    def _deliver_candidate_observation(self, candidate_idx: int) -> None:
        """Deliver a (possibly bootstrap-resampled) observation to the learner's container.

        If bootstrap_observations is enabled, each candidate sees traces from a
        bootstrap sample of opponents (same total count, different distribution).
        If disabled, all candidates share the identical full set.
        """
        # Clear previous observation in container
        self.learner_agent.environment.execute(
            "rm -rf /logs/rounds/0/observations_round_0.txt"
        )

        if not self.bootstrap_observations:
            # No bootstrap — deliver full traces
            self._deliver_traces_to_learner(round_num=1, prev_round=0)
            return

        # Subsampled: generate NL summary from only this candidate's opponent subset
        subset = self._opponent_subsets[candidate_idx] if candidate_idx < len(self._opponent_subsets) else []

        if self.observation_mode == "nl_summary":
            self._deliver_subsampled_nl_observation(candidate_idx, subset)
        else:
            # Raw mode with subsampling: copy only subset opponent dirs
            self._deliver_subsampled_raw_traces(candidate_idx, subset)

    def _deliver_subsampled_nl_observation(
        self, candidate_idx: int, opp_indices: list[int]
    ) -> None:
        """Generate NL summary from a subset of opponents' traces."""
        from revenge_bench.tournaments.observation_summarizer import (
            generate_nl_observation,
        )

        round_dir = self.game.log_local / "rounds" / str(0)
        traces_file = round_dir / "traces.json"

        if not traces_file.exists():
            summary_text = f"[No observations available for round 0]"
        else:
            traces_json = json.loads(traces_file.read_text())
            game_name = self.config.get("game", {}).get("name", "Unknown")

            # Filter traces to only include the subsampled opponents
            filtered_traces = self._filter_traces_by_opponents(
                traces_json, opp_indices
            )

            model_name = self.summarizer_model_config.get(
                "model_name", "openai/gpt-4o-mini"
            )
            model_kwargs = {}
            if "api_base" in self.summarizer_model_config:
                model_kwargs["api_base"] = self.summarizer_model_config["api_base"]
            if "api_key" in self.summarizer_model_config:
                model_kwargs["api_key"] = self.summarizer_model_config["api_key"]

            summary_text = generate_nl_observation(
                traces_json=filtered_traces,
                sim_dir=round_dir,
                game_name=game_name,
                round_num=0,
                model_name=model_name,
                model_kwargs=model_kwargs if model_kwargs else None,
            )

        self.logger.info(
            f"  Candidate {candidate_idx}: NL summary from "
            f"{len(set(opp_indices))}/{len(self._opponent_subsets[0]) if self._opponent_subsets else '?'} "
            f"unique opponents (bootstrap, {len(summary_text)} chars)"
        )

        container_round_dir = DIR_LOGS / "rounds" / str(0)
        create_file_in_container(
            self.learner_agent.environment,
            content=summary_text,
            dest_path=container_round_dir / "observations_round_0.txt",
        )

    def _deliver_subsampled_raw_traces(
        self, candidate_idx: int, opp_indices: list[int]
    ) -> None:
        """Deliver raw traces from only a subset of opponents."""
        round_dir = self.game.log_local / "rounds" / str(0)
        traces_file = round_dir / "traces.json"

        if not traces_file.exists():
            return

        traces_json = json.loads(traces_file.read_text())
        filtered_traces = self._filter_traces_by_opponents(traces_json, opp_indices)

        # Write filtered traces to container
        container_round_dir = DIR_LOGS / "rounds" / str(0)
        create_file_in_container(
            self.learner_agent.environment,
            content=json.dumps(filtered_traces, indent=2),
            dest_path=container_round_dir / "traces.json",
        )

    def _filter_traces_by_opponents(
        self, traces_json: dict[str, Any], opp_indices: list[int]
    ) -> dict[str, Any]:
        """Filter a traces.json dict to include only specified opponent indices.

        traces_json typically has keys like 'opp_0', 'opp_1', ... or 'nonzero_distances'
        with per-opponent sub-keys. We keep only those matching opp_indices.
        """
        if not traces_json:
            return traces_json

        filtered = {}
        opp_keys = {f"opp_{i}" for i in opp_indices}

        for key, value in traces_json.items():
            if key.startswith("opp_"):
                if key in opp_keys:
                    filtered[key] = value
            elif isinstance(value, dict):
                # Nested dict (e.g., 'nonzero_distances' → {opp_0: ..., opp_1: ...})
                sub_filtered = {}
                for sub_key, sub_val in value.items():
                    if sub_key.startswith("opp_"):
                        if sub_key in opp_keys:
                            sub_filtered[sub_key] = sub_val
                    else:
                        sub_filtered[sub_key] = sub_val
                filtered[key] = sub_filtered
            else:
                # Scalars, metadata — keep as-is
                filtered[key] = value

        return filtered

    def _inject_diversity_hint(self, candidate_idx: int, hint: str) -> None:
        """Append a diversity hint to the observation file in the container.

        The hint steers the candidate toward a particular reasoning approach
        without changing the underlying data, promoting diverse hypotheses.
        """
        hint_block = (
            f"\n\n## Approach Guidance (Candidate {candidate_idx})\n\n"
            f"{hint}\n"
        )
        # Append to the observation file
        self.learner_agent.environment.execute(
            f"echo {json.dumps(hint_block)} >> "
            f"/logs/rounds/0/observations_round_0.txt"
        )
