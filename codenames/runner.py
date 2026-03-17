"""Game runner — plays a full Codenames game between two LLM teams."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from codenames.agents import get_guesser_guesses, get_spymaster_clue
from codenames.game import GameState, GuessOutcome, Team, new_game
from codenames.llm import LLMConfig

log = logging.getLogger(__name__)

MAX_TURNS = 50  # safety limit


@dataclass
class GameResult:
    winner: Team
    red_model: str
    blue_model: str
    turns: int
    log: list[dict]


def play_game(
    red_config: LLMConfig,
    blue_config: LLMConfig,
    seed: int | None = None,
    verbose: bool = True,
) -> GameResult:
    """Play a full game of Codenames between two LLM teams."""
    state = new_game(seed=seed)
    configs = {Team.RED: red_config, Team.BLUE: blue_config}
    game_log: list[dict] = []

    if verbose:
        print(f"\n{'='*60}")
        print(f"CODENAMES: {red_config.display_name} (RED) vs {blue_config.display_name} (BLUE)")
        print(f"First team: {state.first_team.value.upper()}")
        print(f"Red words: {state.remaining(Team.RED.card_color)} | Blue words: {state.remaining(Team.BLUE.card_color)}")
        print(f"{'='*60}\n")

    while state.winner is None and state.turn_number < MAX_TURNS:
        team = state.current_team
        config = configs[team]

        if verbose:
            print(f"\n--- Turn {state.turn_number + 1}: {team.value.upper()} team ---")
            print(f"Remaining - Red: {state.remaining(Team.RED.card_color)}, Blue: {state.remaining(Team.BLUE.card_color)}")

        # Spymaster gives clue
        clue = get_spymaster_clue(config, state, team)
        state.apply_clue(team, clue)

        if verbose:
            print(f"Spymaster clue: \"{clue.word}\" for {clue.count}")

        turn_entry = {
            "turn": state.turn_number,
            "team": team.value,
            "clue": {"word": clue.word, "count": clue.count},
            "guesses": [],
        }

        # Guesser makes guesses
        guesses = get_guesser_guesses(config, state, team, clue)

        for guess in guesses:
            if state.winner is not None or state.guesses_remaining <= 0:
                break

            try:
                outcome = state.apply_guess(guess)
            except ValueError as e:
                log.warning(f"Invalid guess skipped: {e}")
                continue

            turn_entry["guesses"].append({"word": guess, "outcome": outcome.value})

            if verbose:
                print(f"  Guess: {guess} -> {outcome.value}")

            if outcome is not GuessOutcome.CORRECT:
                break

        game_log.append(turn_entry)

    if state.winner is None:
        # Max turns reached — team with fewer remaining words wins
        red_rem = state.remaining(Team.RED.card_color)
        blue_rem = state.remaining(Team.BLUE.card_color)
        state.winner = Team.RED if red_rem <= blue_rem else Team.BLUE

    if verbose:
        print(f"\n{'='*60}")
        print(f"WINNER: {state.winner.value.upper()} team ({configs[state.winner].display_name})")
        print(f"Game ended on turn {state.turn_number}")
        print(f"{'='*60}\n")

    return GameResult(
        winner=state.winner,
        red_model=red_config.display_name,
        blue_model=blue_config.display_name,
        turns=state.turn_number,
        log=game_log,
    )
