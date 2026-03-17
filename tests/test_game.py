"""Unit tests for the Codenames game engine."""

import pytest

from codenames.game import (
    CardColor,
    CodenamesGame,
    GameStatus,
    TeamColor,
)
from codenames.words import WORDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_game(seed: int = 0, first_team: TeamColor = TeamColor.RED) -> CodenamesGame:
    return CodenamesGame(words=WORDS, first_team=first_team, seed=seed)


def _cards_of_color(game: CodenamesGame, color: CardColor):
    return [c for c in game.cards.values() if c.color == color]


# ---------------------------------------------------------------------------
# Board setup
# ---------------------------------------------------------------------------

class TestBoardSetup:
    def test_board_has_25_cards(self):
        game = make_game()
        assert len(game.cards) == 25

    def test_card_color_distribution_red_first(self):
        game = make_game(first_team=TeamColor.RED)
        assert len(_cards_of_color(game, CardColor.RED)) == 9
        assert len(_cards_of_color(game, CardColor.BLUE)) == 8
        assert len(_cards_of_color(game, CardColor.NEUTRAL)) == 7
        assert len(_cards_of_color(game, CardColor.ASSASSIN)) == 1

    def test_card_color_distribution_blue_first(self):
        game = make_game(first_team=TeamColor.BLUE)
        assert len(_cards_of_color(game, CardColor.RED)) == 8
        assert len(_cards_of_color(game, CardColor.BLUE)) == 9
        assert len(_cards_of_color(game, CardColor.NEUTRAL)) == 7
        assert len(_cards_of_color(game, CardColor.ASSASSIN)) == 1

    def test_all_words_unique(self):
        game = make_game()
        assert len(set(game.words)) == 25

    def test_seed_produces_deterministic_board(self):
        game1 = make_game(seed=42)
        game2 = make_game(seed=42)
        assert game1.words == game2.words
        assert [c.color for c in game1.cards.values()] == [
            c.color for c in game2.cards.values()
        ]

    def test_different_seeds_produce_different_boards(self):
        game1 = make_game(seed=1)
        game2 = make_game(seed=2)
        assert game1.words != game2.words

    def test_too_few_words_raises(self):
        with pytest.raises(ValueError, match="at least 25"):
            CodenamesGame(words=["word"] * 10)


# ---------------------------------------------------------------------------
# Clue giving
# ---------------------------------------------------------------------------

class TestClue:
    def test_valid_clue(self):
        game = make_game()
        game.give_clue("OCEAN", 2)
        assert game.current_clue is not None
        assert game.current_clue.word == "OCEAN"
        assert game.current_clue.number == 2

    def test_clue_word_normalized_to_uppercase(self):
        game = make_game()
        game.give_clue("ocean", 1)
        assert game.current_clue.word == "OCEAN"

    def test_clue_word_on_board_raises(self):
        game = make_game()
        board_word = game.words[0]
        with pytest.raises(ValueError, match="board"):
            game.give_clue(board_word, 1)

    def test_clue_number_zero_raises(self):
        game = make_game()
        with pytest.raises(ValueError, match="at least 1"):
            game.give_clue("OCEAN", 0)

    def test_double_clue_raises(self):
        game = make_game()
        game.give_clue("OCEAN", 2)
        with pytest.raises(ValueError, match="already been given"):
            game.give_clue("RIVER", 1)

    def test_clue_added_to_history(self):
        game = make_game()
        game.give_clue("RIVER", 2)
        assert len(game.clue_history) == 1


# ---------------------------------------------------------------------------
# Guessing
# ---------------------------------------------------------------------------

class TestGuessing:
    def _setup_turn(self, game: CodenamesGame, number: int = 3):
        """Give a clue to start a turn."""
        game.give_clue("TESTCLUE", number)

    def test_correct_guess(self):
        game = make_game()
        own_color = CardColor(game.current_team.value)
        own_card = next(c for c in game.cards.values() if c.color == own_color)
        self._setup_turn(game)
        result = game.guess(own_card.word)
        assert result == "correct"
        assert own_card.revealed

    def test_neutral_guess_ends_turn(self):
        game = make_game()
        first_team = game.current_team
        neutral = next(c for c in game.cards.values() if c.color == CardColor.NEUTRAL)
        self._setup_turn(game)
        result = game.guess(neutral.word)
        assert result == "neutral"
        assert game.current_team != first_team  # turn switched

    def test_assassin_guess_ends_game(self):
        game = make_game()
        assassin = next(c for c in game.cards.values() if c.color == CardColor.ASSASSIN)
        self._setup_turn(game)
        result = game.guess(assassin.word)
        assert result == "assassin"
        assert game.is_over()

    def test_wrong_team_guess_ends_turn(self):
        game = make_game()
        first_team = game.current_team
        opp_color = CardColor.BLUE if first_team == TeamColor.RED else CardColor.RED
        opp_card = next(c for c in game.cards.values() if c.color == opp_color)
        self._setup_turn(game)
        result = game.guess(opp_card.word)
        assert result == "wrong_team"
        assert game.current_team != first_team

    def test_max_guesses_ends_turn(self):
        game = make_game()
        first_team = game.current_team
        own_color = CardColor(first_team.value)
        own_cards = [c for c in game.cards.values() if c.color == own_color]
        game.give_clue("TESTCLUE", 1)  # number=1 → max 2 guesses
        game.guess(own_cards[0].word)  # guess 1
        game.guess(own_cards[1].word)  # guess 2 → max reached, turn ends
        assert game.current_team != first_team

    def test_exceeding_max_guesses_raises(self):
        # After the maximum guesses are used the turn ends (clue is cleared).
        # Any further guess on what is now a new turn (no clue yet) must fail.
        game = make_game()
        own_color = CardColor(game.current_team.value)
        own_cards = [c for c in game.cards.values() if c.color == own_color]
        game.give_clue("TESTCLUE", 1)
        game.guess(own_cards[0].word)  # guess 1 of 2
        game.guess(own_cards[1].word)  # guess 2 of 2 → turn ends
        # Turn has ended: guessing now must raise a ValueError
        with pytest.raises(ValueError):
            game.guess(own_cards[2].word)

    def test_unknown_word_raises(self):
        game = make_game()
        self._setup_turn(game)
        with pytest.raises(ValueError, match="not on the board"):
            game.guess("XYZNOTAWORD")

    def test_already_revealed_raises(self):
        game = make_game()
        own_color = CardColor(game.current_team.value)
        own_card = next(c for c in game.cards.values() if c.color == own_color)
        self._setup_turn(game)
        game.guess(own_card.word)  # reveals it
        game.pass_turn()  # end turn (switch team)
        game.give_clue("AGAIN", 1)
        with pytest.raises(ValueError, match="already been revealed"):
            game.guess(own_card.word)

    def test_guess_without_clue_raises(self):
        game = make_game()
        with pytest.raises(ValueError, match="No clue"):
            game.guess(game.words[0])

    def test_guess_added_to_history(self):
        game = make_game()
        own_color = CardColor(game.current_team.value)
        own_card = next(c for c in game.cards.values() if c.color == own_color)
        self._setup_turn(game)
        game.guess(own_card.word)
        assert len(game.guess_history) == 1


# ---------------------------------------------------------------------------
# Pass turn
# ---------------------------------------------------------------------------

class TestPassTurn:
    def test_pass_switches_team(self):
        game = make_game()
        first_team = game.current_team
        game.give_clue("OCEAN", 2)
        game.pass_turn()
        assert game.current_team != first_team

    def test_pass_without_clue_raises(self):
        game = make_game()
        with pytest.raises(ValueError, match="No clue"):
            game.pass_turn()


# ---------------------------------------------------------------------------
# Win conditions
# ---------------------------------------------------------------------------

class TestWinConditions:
    def _reveal_all_of_color(self, game: CodenamesGame, color: CardColor):
        """Directly reveal all cards of a given color to simulate a win."""
        for card in game.cards.values():
            if card.color == color:
                card.revealed = True

    def test_red_wins_by_revealing_all_red_cards(self):
        game = make_game()
        # Reveal all red cards except one, then guess the last
        red_cards = [c for c in game.cards.values() if c.color == CardColor.RED]
        for card in red_cards[:-1]:
            card.revealed = True
        game.give_clue("WIN", 1)
        game.guess(red_cards[-1].word)
        assert game.status == GameStatus.RED_WINS

    def test_assassin_causes_opponent_to_win(self):
        game = make_game()
        assassin = next(c for c in game.cards.values() if c.color == CardColor.ASSASSIN)
        game.give_clue("LOSE", 1)
        game.guess(assassin.word)
        assert game.status == GameStatus.BLUE_WINS

    def test_cannot_act_after_game_over(self):
        game = make_game()
        assassin = next(c for c in game.cards.values() if c.color == CardColor.ASSASSIN)
        game.give_clue("LOSE", 1)
        game.guess(assassin.word)
        with pytest.raises(ValueError, match="already over"):
            game.give_clue("AGAIN", 1)


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class TestViews:
    def test_spymaster_view_contains_all_colors(self):
        game = make_game()
        view = game.get_spymaster_view()
        colors = {c["color"] for c in view["cards"]}
        assert colors == {"red", "blue", "neutral", "assassin"}

    def test_guesser_view_hides_unrevealed_colors(self):
        game = make_game()
        view = game.get_guesser_view()
        unrevealed = [c for c in view["cards"] if not c["revealed"]]
        for card in unrevealed:
            assert card["color"] == "unknown"

    def test_guesser_view_shows_revealed_colors(self):
        game = make_game()
        own_color = CardColor(game.current_team.value)
        own_card = next(c for c in game.cards.values() if c.color == own_color)
        own_card.revealed = True
        view = game.get_guesser_view()
        found = next(c for c in view["cards"] if c["word"] == own_card.word)
        assert found["color"] == own_color.value
