"""
Tests for the BattleSnake trace parser.

Run with: pytest tests/test_battlesnake_traces.py -v
"""


import pytest

from revenge_bench.traces import (
    GameOutcome,
    TraceCollector,
    TraceWriter,
    get_state_action_dataset,
    read_trace,
    write_trace,
)
from revenge_bench.traces.parsers.battlesnake import (
    BattleSnakeTraceParser,
)

# Sample BattleSnake JSONL output (mimics real game engine output)
SAMPLE_BATTLESNAKE_JSONL = """{"id":"test-game-001","ruleset":{"name":"standard","version":"cli","settings":{"foodSpawnChance":15,"minimumFood":1,"hazardDamagePerTurn":14}},"map":"standard","timeout":500}
{"game":{"id":"test-game-001","ruleset":{"name":"standard","version":"cli","settings":{"foodSpawnChance":15,"minimumFood":1,"hazardDamagePerTurn":14}},"map":"standard","timeout":500,"source":""},"turn":0,"board":{"height":11,"width":11,"snakes":[{"id":"snake-1","name":"Player1","latency":"0","health":100,"body":[{"x":1,"y":1},{"x":1,"y":1},{"x":1,"y":1}],"head":{"x":1,"y":1},"length":3,"shout":""},{"id":"snake-2","name":"Player2","latency":"0","health":100,"body":[{"x":9,"y":9},{"x":9,"y":9},{"x":9,"y":9}],"head":{"x":9,"y":9},"length":3,"shout":""}],"food":[{"x":5,"y":5}],"hazards":[]},"you":{"id":"snake-1","name":"Player1","latency":"0","health":100,"body":[{"x":1,"y":1},{"x":1,"y":1},{"x":1,"y":1}],"head":{"x":1,"y":1},"length":3,"shout":""}}
{"game":{"id":"test-game-001","ruleset":{"name":"standard","version":"cli","settings":{"foodSpawnChance":15,"minimumFood":1,"hazardDamagePerTurn":14}},"map":"standard","timeout":500,"source":""},"turn":1,"board":{"height":11,"width":11,"snakes":[{"id":"snake-1","name":"Player1","latency":"5","health":99,"body":[{"x":2,"y":1},{"x":1,"y":1},{"x":1,"y":1}],"head":{"x":2,"y":1},"length":3,"shout":""},{"id":"snake-2","name":"Player2","latency":"3","health":99,"body":[{"x":8,"y":9},{"x":9,"y":9},{"x":9,"y":9}],"head":{"x":8,"y":9},"length":3,"shout":""}],"food":[{"x":5,"y":5}],"hazards":[]},"you":{"id":"snake-1","name":"Player1","latency":"5","health":99,"body":[{"x":2,"y":1},{"x":1,"y":1},{"x":1,"y":1}],"head":{"x":2,"y":1},"length":3,"shout":""}}
{"game":{"id":"test-game-001","ruleset":{"name":"standard","version":"cli","settings":{"foodSpawnChance":15,"minimumFood":1,"hazardDamagePerTurn":14}},"map":"standard","timeout":500,"source":""},"turn":2,"board":{"height":11,"width":11,"snakes":[{"id":"snake-1","name":"Player1","latency":"4","health":98,"body":[{"x":2,"y":2},{"x":2,"y":1},{"x":1,"y":1}],"head":{"x":2,"y":2},"length":3,"shout":""},{"id":"snake-2","name":"Player2","latency":"2","health":98,"body":[{"x":7,"y":9},{"x":8,"y":9},{"x":9,"y":9}],"head":{"x":7,"y":9},"length":3,"shout":""}],"food":[{"x":5,"y":5}],"hazards":[]},"you":{"id":"snake-1","name":"Player1","latency":"4","health":98,"body":[{"x":2,"y":2},{"x":2,"y":1},{"x":1,"y":1}],"head":{"x":2,"y":2},"length":3,"shout":""}}
{"winnerId":"snake-1","winnerName":"Player1","isDraw":false}"""


class TestBattleSnakeParser:
    """Tests for BattleSnakeTraceParser."""

    def test_parse_content_basic(self):
        """Test parsing JSONL content."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        # Check metadata
        assert trace.game_id == "test-game-001"
        assert trace.game_type == "BattleSnake"
        assert len(trace.metadata.players) == 2
        assert trace.metadata.players[0]["name"] == "Player1"
        assert trace.metadata.players[1]["name"] == "Player2"

        # Check config
        assert trace.metadata.config["width"] == 11
        assert trace.metadata.config["height"] == 11

    def test_parse_turns(self):
        """Test that turns are parsed correctly."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        # Should have 3 turns (0, 1, 2)
        assert trace.total_turns == 3
        assert trace.turns[0].turn == 0
        assert trace.turns[1].turn == 1
        assert trace.turns[2].turn == 2

    def test_parse_state(self):
        """Test that game state is captured correctly."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        # Check turn 0 state
        turn0 = trace.turns[0]
        assert turn0.state["board"]["width"] == 11
        assert turn0.state["board"]["height"] == 11
        assert len(turn0.state["board"]["snakes"]) == 2
        assert len(turn0.state["board"]["food"]) == 1
        assert turn0.state["board"]["food"][0] == {"x": 5, "y": 5}

    def test_parse_player_states(self):
        """Test that per-player states are created."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        turn0 = trace.turns[0]

        # Each player should have their own state view
        assert "Player1" in turn0.player_states
        assert "Player2" in turn0.player_states

        # Player1's view should have "you" pointing to Player1
        p1_state = turn0.player_states["Player1"]
        assert p1_state["you"]["name"] == "Player1"

        # Player2's view should have "you" pointing to Player2
        p2_state = turn0.player_states["Player2"]
        assert p2_state["you"]["name"] == "Player2"

    def test_infer_actions(self):
        """Test that actions are inferred from position changes."""
        parser = BattleSnakeTraceParser(infer_actions=True)
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        # Turn 0 has no actions (initial state)
        assert len(trace.turns[0].actions) == 0

        # Turn 1 should have inferred actions from turn 0->1
        turn1_actions = trace.turns[1].actions
        assert len(turn1_actions) == 2

        # Player1: (1,1) -> (2,1) = right
        p1_action = next(a for a in turn1_actions if a.player_name == "Player1")
        assert p1_action.action == "right"
        assert p1_action.turn == 0  # Action taken on turn 0

        # Player2: (9,9) -> (8,9) = left
        p2_action = next(a for a in turn1_actions if a.player_name == "Player2")
        assert p2_action.action == "left"

    def test_infer_all_directions(self):
        """Test action inference for all four directions."""
        parser = BattleSnakeTraceParser()

        # Test each direction
        assert parser._infer_action((5, 5), (6, 5)) == "right"
        assert parser._infer_action((5, 5), (4, 5)) == "left"
        assert parser._infer_action((5, 5), (5, 6)) == "up"
        assert parser._infer_action((5, 5), (5, 4)) == "down"

    def test_parse_results(self):
        """Test that game results are parsed correctly."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        assert trace.winner == "Player1"
        assert not trace.is_draw

        # Check player results
        assert len(trace.results) == 2

        p1_result = next(r for r in trace.results if r.player_name == "Player1")
        assert p1_result.outcome == GameOutcome.WIN

        p2_result = next(r for r in trace.results if r.player_name == "Player2")
        assert p2_result.outcome == GameOutcome.LOSS

    def test_parse_draw(self):
        """Test parsing a draw game."""
        draw_jsonl = SAMPLE_BATTLESNAKE_JSONL.replace(
            '{"winnerId":"snake-1","winnerName":"Player1","isDraw":false}',
            '{"winnerId":"","winnerName":"","isDraw":true}',
        )

        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(draw_jsonl)

        assert trace.is_draw
        assert trace.winner == ""

    def test_get_state_action_pairs(self):
        """Test extracting state-action pairs for a player."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        pairs = trace.get_state_action_pairs("Player1")

        # Should have 2 pairs (actions on turns 0 and 1)
        assert len(pairs) == 2

        # First pair: state from turn 1, action "right"
        state, action = pairs[0]
        assert action == "right"
        assert state["you"]["name"] == "Player1"

    def test_valid_actions_included(self):
        """Test that valid_actions are included in PlayerAction."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        for turn in trace.turns[1:]:  # Skip turn 0 (no actions)
            for action in turn.actions:
                assert action.valid_actions == ["up", "down", "left", "right"]

    def test_latency_parsed(self):
        """Test that latency is parsed from snake data."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        # Turn 1 actions should have latency
        turn1_actions = trace.turns[1].actions
        p1_action = next(a for a in turn1_actions if a.player_name == "Player1")
        assert p1_action.latency_ms == 5


class TestTraceWriterReader:
    """Tests for writing and reading traces."""

    def test_write_read_jsonl(self, tmp_path):
        """Test writing and reading JSONL format."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        # Write
        output_path = tmp_path / "test_trace.jsonl"
        write_trace(trace, output_path, format="jsonl")

        assert output_path.exists()

        # Read back
        loaded = read_trace(output_path)

        assert loaded.game_id == trace.game_id
        assert loaded.total_turns == trace.total_turns
        assert loaded.winner == trace.winner
        assert len(loaded.metadata.players) == len(trace.metadata.players)

    def test_write_read_json(self, tmp_path):
        """Test writing and reading JSON format."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        # Write
        output_path = tmp_path / "test_trace.json"
        write_trace(trace, output_path, format="json")

        # Read back
        loaded = read_trace(output_path)

        assert loaded.game_id == trace.game_id
        assert loaded.total_turns == trace.total_turns

    def test_streaming_write(self, tmp_path):
        """Test streaming write mode."""
        parser = BattleSnakeTraceParser()
        trace = parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)

        output_path = tmp_path / "streamed.jsonl"

        with TraceWriter(output_path, format="jsonl") as writer:
            writer.write_metadata(trace.metadata)
            for turn in trace.turns:
                writer.write_turn(turn)
            writer.write_results(trace.results, trace.winner, trace.is_draw)

        # Read back and verify
        loaded = read_trace(output_path)
        assert loaded.total_turns == trace.total_turns


class TestTraceCollector:
    """Tests for TraceCollector."""

    def test_collect_from_files(self, tmp_path):
        """Test collecting traces from simulation files."""
        # Create mock simulation files
        rounds_dir = tmp_path / "rounds" / "0"
        rounds_dir.mkdir(parents=True)

        (rounds_dir / "sim_0.jsonl").write_text(SAMPLE_BATTLESNAKE_JSONL)
        (rounds_dir / "sim_1.jsonl").write_text(SAMPLE_BATTLESNAKE_JSONL)

        # Collect
        collector = TraceCollector(game_type="BattleSnake")
        traces = collector.collect_from_round(rounds_dir)

        assert len(traces) == 2
        assert all(t.game_type == "BattleSnake" for t in traces)

    def test_save_traces(self, tmp_path):
        """Test saving collected traces."""
        parser = BattleSnakeTraceParser()
        traces = [parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)]

        collector = TraceCollector(game_type="BattleSnake")
        output_dir = tmp_path / "traces"

        saved = collector.save_traces(traces, output_dir)

        assert len(saved) == 1
        assert saved[0].exists()


class TestStateActionDataset:
    """Tests for dataset extraction functions."""

    def test_get_state_action_dataset(self):
        """Test extracting flat dataset from traces."""
        parser = BattleSnakeTraceParser()
        traces = [parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)]

        dataset = get_state_action_dataset(traces)

        # Should have 4 state-action pairs (2 players x 2 actions each)
        assert len(dataset) == 4

        # Check structure
        for item in dataset:
            assert "game_id" in item
            assert "game_type" in item
            assert "turn" in item
            assert "player_name" in item
            assert "state" in item
            assert "action" in item

    def test_get_state_action_dataset_filtered(self):
        """Test filtering dataset by player."""
        parser = BattleSnakeTraceParser()
        traces = [parser.parse_content(SAMPLE_BATTLESNAKE_JSONL)]

        dataset = get_state_action_dataset(traces, player_filter="Player1")

        # Should only have Player1's actions
        assert len(dataset) == 2
        assert all(item["player_name"] == "Player1" for item in dataset)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
