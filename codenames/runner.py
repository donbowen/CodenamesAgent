"""Game orchestration: Team definitions and GameRunner."""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from codenames.game import CodenamesGame, TeamColor
from codenames.agents import SpymasterAgent, GuesserAgent
from codenames.words import WORDS

logger = logging.getLogger(__name__)

# Maximum turns before declaring the game a draw to prevent infinite loops
MAX_TURNS = 50


@dataclass
class Team:
    """
    A pair of LLM agents (Spymaster + Guesser) that play on the same side.

    Both agents are created from the same *model* string so the team can be
    identified for ELO purposes by ``(name, model)``.
    """

    name: str
    model: str
    spymaster: SpymasterAgent = field(init=False)
    guesser: GuesserAgent = field(init=False)
    spymaster_prompt: str = ""
    guesser_prompt: str = ""
    litellm_kwargs: dict[str, Any] = field(default_factory=dict)
    prompt_log: Any = field(default=None)

    def __post_init__(self) -> None:
        from codenames.agents import (  # avoid circular import at module level
            SPYMASTER_SYSTEM_PROMPT,
            GUESSER_SYSTEM_PROMPT,
        )
        sp = self.spymaster_prompt or SPYMASTER_SYSTEM_PROMPT
        gp = self.guesser_prompt or GUESSER_SYSTEM_PROMPT
        self.spymaster = SpymasterAgent(model=self.model, system_prompt=sp, litellm_kwargs=self.litellm_kwargs, prompt_log=self.prompt_log)
        self.guesser = GuesserAgent(model=self.model, system_prompt=gp, litellm_kwargs=self.litellm_kwargs, prompt_log=self.prompt_log)


@dataclass
class GameResult:
    """Outcome of a completed game."""

    winner: TeamColor  # TeamColor.RED or TeamColor.BLUE
    winning_team_name: str
    losing_team_name: str
    total_turns: int
    game: CodenamesGame


class GameRunner:
    """
    Orchestrates a full Codenames game between two :class:`Team` instances.

    Usage::

        runner = GameRunner(red_team=team_a, blue_team=team_b)
        result = runner.run()
        print(result.winner, result.winning_team_name)
    """

    def __init__(
        self,
        red_team: Team,
        blue_team: Team,
        words: Optional[list] = None,
        first_team: TeamColor = TeamColor.RED,
        seed: Optional[int] = None,
        max_turns: int = MAX_TURNS,
        verbose: bool = False,
    ) -> None:
        self.red_team = red_team
        self.blue_team = blue_team
        self.words = words or WORDS
        self.first_team = first_team
        self.seed = seed
        self.max_turns = max_turns
        self.verbose = verbose

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> GameResult:
        """Play a full game and return the result."""
        game = CodenamesGame(
            words=self.words,
            first_team=self.first_team,
            seed=self.seed,
        )
        turns = 0

        while not game.is_over() and turns < self.max_turns:
            team = (
                self.red_team
                if game.current_team == TeamColor.RED
                else self.blue_team
            )
            self._play_turn(game, team)
            turns += 1

        if not game.is_over():
            # Forced draw — caller can handle this edge case
            logger.warning(
                "Game reached maximum turn limit (%d) without a winner.",
                self.max_turns,
            )
            # Decide by remaining cards: fewer remaining = winner
            if game.red_remaining <= game.blue_remaining:
                from codenames.game import GameStatus
                game.status = GameStatus.RED_WINS
            else:
                from codenames.game import GameStatus
                game.status = GameStatus.BLUE_WINS

        winner = game.get_winner()
        winning_name = (
            self.red_team.name if winner == TeamColor.RED else self.blue_team.name
        )
        losing_name = (
            self.blue_team.name if winner == TeamColor.RED else self.red_team.name
        )

        self._log(
            f"Game over! {winning_name} ({winner.value.upper()}) wins "
            f"after {turns} turn(s)."
        )

        return GameResult(
            winner=winner,
            winning_team_name=winning_name,
            losing_team_name=losing_name,
            total_turns=turns,
            game=game,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _play_turn(self, game: CodenamesGame, team: Team) -> None:
        """Run one full turn for *team*."""
        color = game.current_team
        self._log(
            f"\n--- {team.name} ({color.value.upper()}) turn | "
            f"Red: {game.red_remaining} | Blue: {game.blue_remaining} ---"
        )

        # Spymaster gives a clue
        view = game.get_spymaster_view()
        try:
            clue_word, number = team.spymaster.give_clue(view)
        except RuntimeError as exc:
            logger.error("Spymaster failed: %s — passing turn.", exc)
            # Cannot give clue; skip turn by giving a dummy clue with number 0
            # which is not allowed, so we directly end the turn
            game._end_turn()  # noqa: SLF001
            return

        self._log(f"  Spymaster clue: '{clue_word}' ({number})")

        try:
            game.give_clue(clue_word, number)
        except ValueError as exc:
            logger.error("Invalid spymaster clue '%s': %s", clue_word, exc)
            game._end_turn()  # noqa: SLF001
            return

        # Field Operative guesses
        while not game.is_over():
            gview = game.get_guesser_view()
            if gview["guesses_this_turn"] >= gview["max_guesses"]:
                break  # turn should already have ended, but guard anyway

            try:
                guess = team.guesser.make_guess(gview)
            except RuntimeError as exc:
                logger.error("Guesser failed: %s — passing.", exc)
                game.pass_turn()
                break

            if guess == "PASS":
                if gview["guesses_this_turn"] == 0:
                    logger.warning("Guesser tried to pass before guessing — forcing a guess.")
                    continue
                self._log("  Guesser passed.")
                game.pass_turn()
                break

            # Match guess back to a board word (case-insensitive)
            matched = next(
                (w for w in game.words if w.upper() == guess.upper()), None
            )
            if matched is None:
                logger.warning("Guesser returned unknown word '%s' — passing.", guess)
                game.pass_turn()
                break

            result = game.guess(matched)
            self._log(f"  Guessed '{matched}' → {result}")

            if result in ("assassin", "neutral", "wrong_team"):
                break  # turn has already ended inside game.guess()

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)
        logger.info(msg)
