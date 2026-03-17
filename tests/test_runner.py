"""Tests for the GameRunner, using mocked LLM agents."""

import pytest
from unittest.mock import MagicMock, patch

from codenames.game import CodenamesGame, TeamColor, CardColor, GameStatus
from codenames.runner import GameRunner, Team, GameResult
from codenames.words import WORDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_team(name: str, model: str = "mock-model") -> Team:
    """Return a Team with real agent objects replaced by MagicMocks."""
    team = object.__new__(Team)
    team.name = name
    team.model = model
    team.spymaster = MagicMock()
    team.guesser = MagicMock()
    return team


def _red_cards(game: CodenamesGame):
    return [c for c in game.cards.values() if c.color == CardColor.RED and not c.revealed]


def _blue_cards(game: CodenamesGame):
    return [c for c in game.cards.values() if c.color == CardColor.BLUE and not c.revealed]


# ---------------------------------------------------------------------------
# Team construction
# ---------------------------------------------------------------------------

class TestTeamConstruction:
    def test_team_creates_spymaster_and_guesser(self):
        team = Team(name="TestBot", model="gpt-4o")
        assert team.spymaster is not None
        assert team.guesser is not None
        assert team.spymaster.model == "gpt-4o"
        assert team.guesser.model == "gpt-4o"

    def test_custom_prompts_are_passed_to_agents(self):
        team = Team(
            name="TestBot",
            model="gpt-4o",
            spymaster_prompt="Custom spymaster prompt",
            guesser_prompt="Custom guesser prompt",
        )
        assert team.spymaster.system_prompt == "Custom spymaster prompt"
        assert team.guesser.system_prompt == "Custom guesser prompt"


# ---------------------------------------------------------------------------
# GameRunner – happy path
# ---------------------------------------------------------------------------

class TestGameRunnerHappyPath:
    def _run_with_scripts(self, red_script, blue_script, seed=0):
        """
        Run a game where agent behaviours are driven by pre-defined scripts.

        *red_script* and *blue_script* are lists of (clue, number, guesses)
        tuples, where guesses is a list of words (or "PASS").
        """
        red = _make_mock_team("RedBot")
        blue = _make_mock_team("BlueBot")

        # Script iterators
        red_it = iter(red_script)
        blue_it = iter(blue_script)

        def make_spymaster(it):
            def give_clue(view):
                clue, number, _ = next(it)
                return clue, number
            return give_clue

        def make_guesser(red_or_blue_it, blue_or_red_it, color):
            guess_queue = []

            def make_guess(view):
                nonlocal guess_queue
                if not guess_queue:
                    # Peek at the script entry for the current team
                    # We store guesses on the mock side — use a shared closure
                    if not guess_queue:
                        return "PASS"
                return guess_queue.pop(0)

            return make_guess

        # Simpler approach: track which clue index we're on per team
        red_turn = [0]
        blue_turn = [0]

        def red_spymaster(view):
            entry = red_script[red_turn[0]]
            return entry[0], entry[1]

        def _resolve_guess(g, view, turn_idx):
            """Return g, but if PASS is requested before any guess has been made,
            substitute the first unrevealed word so the mandatory-first-guess rule
            is satisfied."""
            if g == "PASS" and view["guesses_this_turn"] == 0:
                return next(c["word"] for c in view["cards"] if not c["revealed"])
            return g

        def red_guesser(view):
            idx = red_turn[0]
            entry = red_script[idx]
            guesses = entry[2]
            used = view["guesses_this_turn"]
            if used < len(guesses):
                g = _resolve_guess(guesses[used], view, idx)
                if guesses[used] == "PASS" and view["guesses_this_turn"] > 0:
                    red_turn[0] += 1
                    return "PASS"
                return g
            red_turn[0] += 1
            return "PASS"

        def blue_spymaster(view):
            entry = blue_script[blue_turn[0]]
            return entry[0], entry[1]

        def blue_guesser(view):
            idx = blue_turn[0]
            entry = blue_script[idx]
            guesses = entry[2]
            used = view["guesses_this_turn"]
            if used < len(guesses):
                g = _resolve_guess(guesses[used], view, idx)
                if guesses[used] == "PASS" and view["guesses_this_turn"] > 0:
                    blue_turn[0] += 1
                    return "PASS"
                return g
            blue_turn[0] += 1
            return "PASS"

        red.spymaster.give_clue.side_effect = red_spymaster
        red.guesser.make_guess.side_effect = red_guesser
        blue.spymaster.give_clue.side_effect = blue_spymaster
        blue.guesser.make_guess.side_effect = blue_guesser

        runner = GameRunner(
            red_team=red,
            blue_team=blue,
            words=WORDS,
            seed=seed,
        )
        return runner, runner.run()

    def test_game_returns_game_result(self):
        # Build a game and verify red wins by only guessing red cards
        game = CodenamesGame(words=WORDS, seed=42, first_team=TeamColor.RED)
        red_words = [c.word for c in game.cards.values() if c.color == CardColor.RED]

        # Red guesses all 9 red cards across 3 turns (3 per turn)
        red_script = [
            ("CLUE", 3, red_words[0:3]),
            ("CLUE", 3, red_words[3:6]),
            ("CLUE", 3, red_words[6:9]),
        ]
        # Blue never gets a chance to finish (red wins first)
        blue_script = [("BLUE", 1, ["PASS"])] * 10

        _, result = self._run_with_scripts(red_script, blue_script, seed=42)
        assert isinstance(result, GameResult)
        assert result.winner == TeamColor.RED

    def test_blue_wins_when_red_guesses_assassin(self):
        game = CodenamesGame(words=WORDS, seed=7, first_team=TeamColor.RED)
        assassin = next(c for c in game.cards.values() if c.color == CardColor.ASSASSIN)

        red_script = [("OOPS", 1, [assassin.word])]
        blue_script = [("BLUE", 1, ["PASS"])] * 10

        _, result = self._run_with_scripts(red_script, blue_script, seed=7)
        assert result.winner == TeamColor.BLUE
        assert result.winning_team_name == "BlueBot"

    def test_result_contains_correct_team_names(self):
        game = CodenamesGame(words=WORDS, seed=42, first_team=TeamColor.RED)
        red_words = [c.word for c in game.cards.values() if c.color == CardColor.RED]

        red_script = [
            ("CLUE", 3, red_words[0:3]),
            ("CLUE", 3, red_words[3:6]),
            ("CLUE", 3, red_words[6:9]),
        ]
        blue_script = [("BLUE", 1, ["PASS"])] * 10

        _, result = self._run_with_scripts(red_script, blue_script, seed=42)
        assert result.winning_team_name == "RedBot"
        assert result.losing_team_name == "BlueBot"


# ---------------------------------------------------------------------------
# GameRunner – error resilience
# ---------------------------------------------------------------------------

class TestGameRunnerResilience:
    def test_spymaster_failure_advances_turn(self):
        """If the spymaster always fails, the runner should still terminate."""
        red = _make_mock_team("RedBot")
        blue = _make_mock_team("BlueBot")

        # Blue wins by revealing all its cards one by one
        game_ref = CodenamesGame(words=WORDS, seed=0, first_team=TeamColor.RED)
        blue_words = [
            c.word for c in game_ref.cards.values() if c.color == CardColor.BLUE
        ]

        red.spymaster.give_clue.side_effect = RuntimeError("LLM unavailable")
        red.guesser.make_guess.return_value = "PASS"

        blue_turn = [0]
        blue_script = [
            ("B", 1, [blue_words[i]]) for i in range(len(blue_words))
        ]

        def blue_spy(view):
            return blue_script[blue_turn[0]][0], blue_script[blue_turn[0]][1]

        def blue_guess(view):
            idx = blue_turn[0]
            guesses = blue_script[idx][2]
            used = view["guesses_this_turn"]
            if used < len(guesses):
                return guesses[used]
            blue_turn[0] += 1
            return "PASS"

        blue.spymaster.give_clue.side_effect = blue_spy
        blue.guesser.make_guess.side_effect = blue_guess

        runner = GameRunner(red_team=red, blue_team=blue, words=WORDS, seed=0)
        result = runner.run()
        assert result.winner == TeamColor.BLUE
