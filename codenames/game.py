"""Codenames game engine — board setup, state tracking, and rule enforcement."""

from __future__ import annotations

import enum
import random
from dataclasses import dataclass, field

from codenames.words import DEFAULT_WORDS

BOARD_SIZE = 25  # 5x5 grid
TEAM_FIRST_COUNT = 9  # team that goes first gets 9 words
TEAM_SECOND_COUNT = 8
ASSASSIN_COUNT = 1
NEUTRAL_COUNT = BOARD_SIZE - TEAM_FIRST_COUNT - TEAM_SECOND_COUNT - ASSASSIN_COUNT


class CardColor(enum.Enum):
    RED = "red"
    BLUE = "blue"
    NEUTRAL = "neutral"
    ASSASSIN = "assassin"


class Team(enum.Enum):
    RED = "red"
    BLUE = "blue"

    @property
    def opponent(self) -> Team:
        return Team.BLUE if self is Team.RED else Team.RED

    @property
    def card_color(self) -> CardColor:
        return CardColor.RED if self is Team.RED else CardColor.BLUE


class GuessOutcome(enum.Enum):
    CORRECT = "correct"
    WRONG_TEAM = "wrong_team"
    NEUTRAL = "neutral"
    ASSASSIN = "assassin"


@dataclass
class Card:
    word: str
    color: CardColor
    revealed: bool = False


@dataclass
class Clue:
    word: str
    count: int


@dataclass
class GameState:
    """Full game state. The board is a flat list of 25 cards (row-major 5x5)."""

    board: list[Card]
    first_team: Team
    current_team: Team
    guesses_remaining: int = 0
    clue_history: list[dict] = field(default_factory=list)
    winner: Team | None = None
    turn_number: int = 0

    # -- queries ---------------------------------------------------------------

    def remaining(self, color: CardColor) -> int:
        return sum(1 for c in self.board if c.color is color and not c.revealed)

    @property
    def unrevealed_words(self) -> list[str]:
        return [c.word for c in self.board if not c.revealed]

    def board_for_spymaster(self) -> list[dict]:
        """Full board info visible to the spymaster."""
        return [
            {"word": c.word, "color": c.color.value, "revealed": c.revealed}
            for c in self.board
        ]

    def board_for_guesser(self) -> list[dict]:
        """Board info visible to the guesser (hidden colors for unrevealed)."""
        return [
            {
                "word": c.word,
                "color": c.color.value if c.revealed else "unknown",
                "revealed": c.revealed,
            }
            for c in self.board
        ]

    def words_by_color(self, color: CardColor) -> list[str]:
        return [c.word for c in self.board if c.color is color and not c.revealed]

    # -- mutations -------------------------------------------------------------

    def apply_clue(self, team: Team, clue: Clue) -> None:
        self.clue_history.append(
            {"team": team.value, "word": clue.word, "count": clue.count, "turn": self.turn_number}
        )
        # count == 0 or "unlimited" means the team can guess up to remaining + 1
        if clue.count == 0:
            self.guesses_remaining = self.remaining(team.card_color) + 1
        else:
            self.guesses_remaining = clue.count + 1  # +1 bonus guess per rules

    def apply_guess(self, word: str) -> GuessOutcome:
        card = next((c for c in self.board if c.word == word and not c.revealed), None)
        if card is None:
            raise ValueError(f"Invalid guess: {word!r} is not an unrevealed word on the board")

        card.revealed = True
        self.guesses_remaining -= 1

        if card.color is CardColor.ASSASSIN:
            self.winner = self.current_team.opponent
            return GuessOutcome.ASSASSIN

        # Check if a team has all words revealed
        for team in Team:
            if self.remaining(team.card_color) == 0:
                self.winner = team
                break

        if card.color is self.current_team.card_color:
            if self.guesses_remaining <= 0:
                self._end_turn()
            return GuessOutcome.CORRECT

        self._end_turn()
        if card.color is self.current_team.opponent.card_color:
            return GuessOutcome.WRONG_TEAM
        return GuessOutcome.NEUTRAL

    def end_guessing(self) -> None:
        """Team voluntarily ends their turn."""
        self._end_turn()

    def _end_turn(self) -> None:
        self.guesses_remaining = 0
        self.current_team = self.current_team.opponent
        self.turn_number += 1


def new_game(
    words: list[str] | None = None,
    first_team: Team | None = None,
    seed: int | None = None,
) -> GameState:
    """Create a fresh game with a random board."""
    rng = random.Random(seed)
    word_pool = list(words or DEFAULT_WORDS)
    rng.shuffle(word_pool)
    chosen = word_pool[:BOARD_SIZE]

    if first_team is None:
        first_team = rng.choice(list(Team))

    second_team = first_team.opponent

    colors: list[CardColor] = (
        [first_team.card_color] * TEAM_FIRST_COUNT
        + [second_team.card_color] * TEAM_SECOND_COUNT
        + [CardColor.NEUTRAL] * NEUTRAL_COUNT
        + [CardColor.ASSASSIN] * ASSASSIN_COUNT
    )
    rng.shuffle(colors)

    board = [Card(word=w, color=c) for w, c in zip(chosen, colors)]

    return GameState(
        board=board,
        first_team=first_team,
        current_team=first_team,
    )
