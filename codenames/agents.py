"""LLM-powered Codenames agents: Spymaster and Guesser.

Each team is two agents spawned from the same model and prompt config.
"""

from __future__ import annotations

import json
import logging
import re

from codenames.game import CardColor, Clue, GameState, Team
from codenames.llm import LLMConfig, chat

log = logging.getLogger(__name__)

SPYMASTER_SYSTEM = """\
You are a Codenames Spymaster. You must give a one-word clue and a number.

RULES:
- Your clue must be a SINGLE word (no spaces, hyphens, or compound words).
- The number indicates how many of your team's words relate to the clue.
- You must NOT use any word (or part of a word) that is on the board.
- Avoid clues that could lead your team to the assassin word.
- Try to connect multiple words with one clue for efficiency.

Respond with ONLY valid JSON: {"word": "<clue>", "count": <number>}
"""

GUESSER_SYSTEM = """\
You are a Codenames Guesser. Your spymaster has given you a clue.

RULES:
- Pick words from the board that match the spymaster's clue.
- You may guess up to (count + 1) words, but you can stop early.
- If you're unsure, it's better to stop than risk hitting the assassin.
- Consider previously revealed cards and past clues for context.

Respond with ONLY valid JSON: {"guesses": ["WORD1", "WORD2", ...]}
Order your guesses from most confident to least confident.
"""


def _format_board_grid(board_data: list[dict]) -> str:
    """Format the board as a 5x5 grid for readability."""
    lines = []
    for row in range(5):
        cells = []
        for col in range(5):
            card = board_data[row * 5 + col]
            word = card["word"]
            if card["revealed"]:
                cells.append(f"[{word} ({card['color']})]")
            else:
                if card["color"] != "unknown":
                    cells.append(f"{word} ({card['color']})")
                else:
                    cells.append(word)
        lines.append(" | ".join(cells))
    return "\n".join(lines)


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response, tolerating markdown fences."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    return json.loads(text)


def get_spymaster_clue(
    config: LLMConfig,
    state: GameState,
    team: Team,
) -> Clue:
    """Ask the spymaster LLM for a clue."""
    board_info = _format_board_grid(state.board_for_spymaster())
    our_words = state.words_by_color(team.card_color)
    opponent_words = state.words_by_color(team.opponent.card_color)
    assassin_words = state.words_by_color(CardColor.ASSASSIN)

    user_msg = (
        f"You are the {team.value.upper()} team spymaster.\n\n"
        f"Board:\n{board_info}\n\n"
        f"Your words (unrevealed): {our_words}\n"
        f"Opponent words (unrevealed): {opponent_words}\n"
        f"Assassin: {assassin_words}\n"
        f"Your remaining: {len(our_words)} | Opponent remaining: {len(opponent_words)}\n"
    )
    if state.clue_history:
        user_msg += f"\nClue history: {json.dumps(state.clue_history)}\n"

    user_msg += "\nGive your clue as JSON: {\"word\": \"<clue>\", \"count\": <number>}"

    messages = [
        {"role": "system", "content": SPYMASTER_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    for attempt in range(3):
        raw = chat(config, messages)
        try:
            data = _parse_json(raw)
            word = str(data["word"]).strip().upper()
            count = int(data["count"])
            if count < 0:
                raise ValueError("count must be non-negative")
            log.info(f"Spymaster ({team.value}) clue: {word} {count}")
            return Clue(word=word, count=count)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            log.warning(f"Spymaster parse error (attempt {attempt + 1}): {e} — raw: {raw}")
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {"role": "user", "content": f"Invalid response. Reply with ONLY JSON: {{\"word\": \"<clue>\", \"count\": <number>}}"}
            )

    # Fallback: single-word clue for one word
    fallback_word = state.words_by_color(team.card_color)[0] if state.words_by_color(team.card_color) else "PASS"
    log.error(f"Spymaster fallback clue for {team.value}")
    return Clue(word="HINT", count=1)


def get_guesser_guesses(
    config: LLMConfig,
    state: GameState,
    team: Team,
    clue: Clue,
) -> list[str]:
    """Ask the guesser LLM for guesses given a clue."""
    board_info = _format_board_grid(state.board_for_guesser())
    unrevealed = state.unrevealed_words

    user_msg = (
        f"You are the {team.value.upper()} team guesser.\n\n"
        f"Board:\n{board_info}\n\n"
        f"Unrevealed words: {unrevealed}\n"
        f"Spymaster's clue: \"{clue.word}\" for {clue.count}\n"
        f"You may guess up to {clue.count + 1} words (but can stop early if unsure).\n"
    )
    if state.clue_history:
        user_msg += f"\nClue history: {json.dumps(state.clue_history)}\n"

    user_msg += "\nRespond with JSON: {\"guesses\": [\"WORD1\", \"WORD2\", ...]}"

    messages = [
        {"role": "system", "content": GUESSER_SYSTEM},
        {"role": "user", "content": user_msg},
    ]

    for attempt in range(3):
        raw = chat(config, messages)
        try:
            data = _parse_json(raw)
            guesses = [str(g).strip().upper() for g in data["guesses"]]
            # Filter to valid unrevealed words
            valid = [g for g in guesses if g in unrevealed]
            if not valid:
                raise ValueError("No valid guesses found in response")
            log.info(f"Guesser ({team.value}) guesses: {valid}")
            return valid
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            log.warning(f"Guesser parse error (attempt {attempt + 1}): {e} — raw: {raw}")
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {"role": "user", "content": f"Invalid response. Pick from these words ONLY: {unrevealed}\nRespond with JSON: {{\"guesses\": [\"WORD1\"]}}"}
            )

    # Fallback: pick first unrevealed word
    log.error(f"Guesser fallback for {team.value}")
    return [unrevealed[0]] if unrevealed else []
