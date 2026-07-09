# Harbor vs Normal-Path Parity Targets

Temporary reference for one-target-per-game Harbor parity runs against the
normal-path GPT-5.4-mini results in:

`/root/babak/inverse-strategy/plotting/paper/results/gpt-5.4-mini.json`

Selection criteria: choose targets that are not trivial, not pure failures, and
that exercise probe/reconstruction behavior. RobotRumble intentionally uses the
already-suspicious target where Harbor previously looked much better than the
normal path.

| Game | Harbor task | Normal initial distance | Normal best distance | Normal best round | Normal probe count | Reason |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| BattleSnake | `battlesnake-gpt5-t09-gpt5-9aa36d603153-v0` | 0.675 | 0.288 | 5 | 3 | Near median difficulty with meaningful improvement and probe use. |
| Halite | `halite-gpt5-t04-gemini-2.5-pro-cd4c0b86488c-v0` | 0.802 | 0.193 | 5 | 5 | Representative Halite score and enough probe use to expose mechanics drift. |
| HuskyBench | `huskybench-gpt5-t05-gpt5-mini-5d14efe5aa55-v0` | 0.223 | 0.171 | 1 | 2 | Avoids trivial near-zero tasks while preserving measurable signal. |
| RoboCode | `robocode-gpt5-t02-claudesonnet4520250929-c0ee3a51142b-v0` | 0.232 | 0.150 | 4 | 4 | Mid-range score with strong probe usage. |
| RobotRumble | `robotrumble-gpt5-t00-cs4-20250514-aead9c0e9955-v0` | 0.526 | 0.514 | 2 | 3 | Highest-value drift detector: normal path barely improves, but prior Harbor e2e did much better. |

Harbor result fields to fill after runs:

| Game | Job path | Harbor initial distance | Harbor final/verifier distance | Harbor reward | Probe count | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| BattleSnake | `jobs/parity-battlesnake-gpt5-t09-run/battlesnake-gpt5-t09-gpt5-9aa36d__uMnG5gu` | 0.675 | 0.252 | 0.748 | 2 | Reconstructed food-path chasing with unsafe-move filtering, immediate enemy-adjacency penalty, and turn bias. No sealed target read observed in sampled log; agent used docs, round-0 traces, and two probes. Harbor final distance is slightly better than normal best 0.288. |
| Halite | `jobs/parity-halite-gpt5-t04-run/halite-gpt5-t04-gemini-2.5-pro-c__3NHCXx5` | 0.805 | verifier failed | n/a | 1 | Agent reconstructed a deterministic frontier-expansion C bot: BFS to nearest non-owned cell and move only when `strength > 3 * production`. The learner runner succeeded, but verifier scoring was killed in `/tests/test.sh` before writing `reward.txt`, causing `RewardFileNotFoundError`. Treat as Harbor verifier/resource failure, not a model score. |
| HuskyBench | `jobs/parity-huskybench-gpt5-t05-run/huskybench-gpt5-t05-gpt5-mini-5d__gaDznKe` | 0.211 | 0.183 | 0.817 | 1 trace | Reconstructed poker hand-class/value ladder: preflop min-raises, fold weak hands under pressure, and postflop value raises by made-hand strength/texture. One `sudo run_probe` returned `name 'os' is not defined`, but `probe_trace_1.json` existed and was used. Harbor final is close to normal best 0.171 but slightly worse. |
| RoboCode | `jobs/parity-robocode-gpt5-t02-run/robocode-gpt5-t02-claudesonnet45__c6d9NmU` | 0.169 | 0.163 | 0.837 | 0 successful | Agent reconstructed a Tracker-style hybrid: opening radar sweep, turn/velocity ramp state machine, enemy-bearing-offset body turns, radar sweep/lock switching, and distance-tier fire power. `run_probe` failed because `/workspace/.probe_budget` was root-owned; the agent attempted `ls /target` but got permission denied, then leaned heavily on visible traces and public Robocode sample sources. Harbor initial/final are close to normal best 0.150, but initial differs materially from the selected normal initial 0.232. |
| RobotRumble | `jobs/parity-robotrumble-gpt5-t00-run/robotrumble-gpt5-t00-cs4-2025051__huLYq4m` | 0.526 | 0.057 | 0.943 | 1 | Agent matched the target to the public built-in `chaser.js` example: choose nearest enemy by grid distance, attack if adjacent, otherwise move toward it. No `/target` read was observed, but the workspace exposes `builtin-bots/chaser.js`; the final `robot.js` is behaviorally the same as that example. This reproduces the large Harbor-vs-normal drift: normal best was 0.514, Harbor verifier distance was 0.057. |
