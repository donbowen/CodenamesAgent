"""Core Codenames game engine."""

import random
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict


class TeamColor(str, Enum):
    """The two teams in Codenames."""
    RED = "red"
    BLUE = "blue"


class CardColor(str, Enum):
    """The four possible card colors on the board."""
    RED = "red"
    BLUE = "blue"
    NEUTRAL = "neutral"
    ASSASSIN = "assassin"


class GameStatus(str, Enum):
    """Overall game status."""
    ONGOING = "ongoing"
    RED_WINS = "red_wins"
    BLUE_WINS = "blue_wins"


@dataclass
class Card:
    """A single word card on the board."""
    word: str
    color: CardColor
    revealed: bool = False


@dataclass
class Clue:
    """A clue given by a Spymaster during their turn."""
    word: str
    number: int
    team: TeamColor


@dataclass
class GuessRecord:
    """A recorded guess by a Field Operative."""
    word: str
    result: str  # "correct", "wrong_team", "neutral", "assassin", "pass"
    team: TeamColor
    clue_word: str = ""
    clue_number: int = 0
    guess_number: int = 0  # 1-indexed position within the turn (0 = PASS with no prior guesses)


class CodenamesGame:
    """
    Core Codenames game engine.

    Standard rules:
      - 25 words on a 5×5 grid
      - First team gets 9 cards, second team gets 8
      - 7 neutral cards, 1 assassin
      - Spymaster gives a one-word clue + number each turn
      - Field Operative guesses up to (number + 1) words
      - Hitting assassin = immediate loss; revealing all own cards = win
    """

    GRID_SIZE = 25
    # Card count distribution depending on who goes first
    _COUNTS = {
        TeamColor.RED:  {"red": 9, "blue": 8, "neutral": 7, "assassin": 1},
        TeamColor.BLUE: {"red": 8, "blue": 9, "neutral": 7, "assassin": 1},
    }

    def __init__(
        self,
        words: List[str],
        first_team: TeamColor = TeamColor.RED,
        seed: Optional[int] = None,
    ) -> None:
        if len(words) < self.GRID_SIZE:
            raise ValueError(
                f"Need at least {self.GRID_SIZE} words, got {len(words)}"
            )

        self._rng = random.Random(seed)
        self.first_team = first_team
        self.current_team = first_team
        self.status = GameStatus.ONGOING

        # Turn state
        self.current_clue: Optional[Clue] = None
        self.guesses_this_turn: int = 0

        # History
        self.clue_history: List[Clue] = []
        self.guess_history: List[GuessRecord] = []

        # Build board
        selected = self._rng.sample(words, self.GRID_SIZE)
        counts = self._COUNTS[first_team]
        colors: List[CardColor] = (
            [CardColor.RED] * counts["red"]
            + [CardColor.BLUE] * counts["blue"]
            + [CardColor.NEUTRAL] * counts["neutral"]
            + [CardColor.ASSASSIN] * counts["assassin"]
        )
        self._rng.shuffle(colors)
        self.cards: Dict[str, Card] = {
            word: Card(word=word, color=color)
            for word, color in zip(selected, colors)
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def words(self) -> List[str]:
        return list(self.cards.keys())

    @property
    def unrevealed_words(self) -> List[str]:
        return [w for w, c in self.cards.items() if not c.revealed]

    @property
    def red_remaining(self) -> int:
        return sum(
            1 for c in self.cards.values()
            if c.color == CardColor.RED and not c.revealed
        )

    @property
    def blue_remaining(self) -> int:
        return sum(
            1 for c in self.cards.values()
            if c.color == CardColor.BLUE and not c.revealed
        )

    def is_over(self) -> bool:
        return self.status != GameStatus.ONGOING

    def get_winner(self) -> Optional[TeamColor]:
        if self.status == GameStatus.RED_WINS:
            return TeamColor.RED
        if self.status == GameStatus.BLUE_WINS:
            return TeamColor.BLUE
        return None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def give_clue(self, clue_word: str, number: int) -> None:
        """
        Spymaster gives a one-word clue and a number.

        Raises ValueError for invalid inputs (game over, mid-turn clue,
        bad number, or clue word that appears on the board).
        """
        if self.is_over():
            raise ValueError("Game is already over.")
        if self.current_clue is not None:
            raise ValueError("A clue has already been given this turn.")
        if number < 1:
            raise ValueError("Clue number must be at least 1.")

        clue_word = clue_word.strip().upper()
        board_upper = {w.upper() for w in self.words}
        if clue_word in board_upper:
            raise ValueError(f"Clue '{clue_word}' is a word on the board.")

        clue = Clue(word=clue_word, number=number, team=self.current_team)
        self.current_clue = clue
        self.clue_history.append(clue)
        self.guesses_this_turn = 0

    def guess(self, word: str) -> str:
        """
        Field Operative guesses a word.

        Returns one of: ``"correct"``, ``"wrong_team"``, ``"neutral"``,
        ``"assassin"``.

        Raises ValueError for invalid inputs.
        """
        if self.is_over():
            raise ValueError("Game is already over.")
        if self.current_clue is None:
            raise ValueError("No clue has been given yet this turn.")

        max_guesses = self.current_clue.number + 1
        if self.guesses_this_turn >= max_guesses:
            raise ValueError("Maximum guesses for this turn already used.")

        # Case-insensitive card lookup
        matched = next(
            (w for w in self.cards if w.upper() == word.strip().upper()), None
        )
        if matched is None:
            raise ValueError(f"'{word}' is not on the board.")
        card = self.cards[matched]
        if card.revealed:
            raise ValueError(f"'{word}' has already been revealed.")

        # Capture clue info before any _end_turn() call clears current_clue
        _clue_word = self.current_clue.word
        _clue_number = self.current_clue.number

        # Reveal and record
        card.revealed = True
        self.guesses_this_turn += 1

        own_color = CardColor(self.current_team.value)

        if card.color == CardColor.ASSASSIN:
            result = "assassin"
            # The team that guessed the assassin loses
            self.status = (
                GameStatus.BLUE_WINS
                if self.current_team == TeamColor.RED
                else GameStatus.RED_WINS
            )

        elif card.color == own_color:
            result = "correct"
            # Check immediate win, then check if turn should end
            if self.red_remaining == 0:
                self.status = GameStatus.RED_WINS
            elif self.blue_remaining == 0:
                self.status = GameStatus.BLUE_WINS
            elif self.guesses_this_turn >= max_guesses:
                self._end_turn()

        elif card.color == CardColor.NEUTRAL:
            result = "neutral"
            self._end_turn()

        else:
            # Opponent's card
            result = "wrong_team"
            if self.red_remaining == 0:
                self.status = GameStatus.RED_WINS
            elif self.blue_remaining == 0:
                self.status = GameStatus.BLUE_WINS
            else:
                self._end_turn()

        self.guess_history.append(
            GuessRecord(
                word=matched,
                result=result,
                team=self.current_team,
                clue_word=_clue_word,
                clue_number=_clue_number,
                guess_number=self.guesses_this_turn,
            )
        )
        return result

    def pass_turn(self) -> None:
        """Field Operative passes without guessing, ending the turn."""
        if self.is_over():
            raise ValueError("Game is already over.")
        if self.current_clue is None:
            raise ValueError("No clue has been given yet this turn.")
        self.guess_history.append(
            GuessRecord(
                word="PASS",
                result="pass",
                team=self.current_team,
                clue_word=self.current_clue.word,
                clue_number=self.current_clue.number,
                guess_number=self.guesses_this_turn + 1,
            )
        )
        self._end_turn()

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    def get_spymaster_view(self) -> dict:
        """
        Full board view for the Spymaster — all card colors are visible.
        """
        return {
            "cards": [
                {
                    "word": c.word,
                    "color": c.color.value,
                    "revealed": c.revealed,
                }
                for c in self.cards.values()
            ],
            "current_team": self.current_team.value,
            "red_remaining": self.red_remaining,
            "blue_remaining": self.blue_remaining,
            "clue_history": [
                {"word": cl.word, "number": cl.number, "team": cl.team.value}
                for cl in self.clue_history
            ],
            "guess_history": [
                {
                    "word": g.word,
                    "result": g.result,
                    "team": g.team.value,
                    "clue_word": g.clue_word,
                    "clue_number": g.clue_number,
                    "guess_number": g.guess_number,
                }
                for g in self.guess_history
            ],
        }

    def get_guesser_view(self) -> dict:
        """
        Board view for the Field Operative — unrevealed card colors are hidden.
        """
        return {
            "cards": [
                {
                    "word": c.word,
                    "color": c.color.value if c.revealed else "unknown",
                    "revealed": c.revealed,
                }
                for c in self.cards.values()
            ],
            "current_team": self.current_team.value,
            "red_remaining": self.red_remaining,
            "blue_remaining": self.blue_remaining,
            "current_clue": (
                {
                    "word": self.current_clue.word,
                    "number": self.current_clue.number,
                }
                if self.current_clue
                else None
            ),
            "clue_history": [
                {"word": cl.word, "number": cl.number, "team": cl.team.value}
                for cl in self.clue_history
            ],
            "guess_history": [
                {
                    "word": g.word,
                    "result": g.result,
                    "team": g.team.value,
                    "clue_word": g.clue_word,
                    "clue_number": g.clue_number,
                    "guess_number": g.guess_number,
                }
                for g in self.guess_history
            ],
            "guesses_this_turn": self.guesses_this_turn,
            "max_guesses": (
                self.current_clue.number + 1 if self.current_clue else 0
            ),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _end_turn(self) -> None:
        """Reset turn state and switch active team."""
        self.current_clue = None
        self.guesses_this_turn = 0
        self.current_team = (
            TeamColor.BLUE
            if self.current_team == TeamColor.RED
            else TeamColor.RED
        )
