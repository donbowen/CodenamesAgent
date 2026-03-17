"""LLM-powered Spymaster and Guesser agents for Codenames."""

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# Default prompts --------------------------------------------------------

SPYMASTER_SYSTEM_PROMPT = """\
You are a Spymaster in a game of Codenames. You have full knowledge of the \
board: which words belong to your team, the opponent, are neutral, or are the \
deadly assassin.

Your task: give ONE word as a clue and a NUMBER indicating how many of your \
team's words relate to it.

Rules:
- The clue must be a single English word (no proper nouns that match board \
words, no phrases).
- The clue CANNOT be any word currently on the board (exact match, \
case-insensitive).
- The number must be at least 1.
- Avoid clues that could guide your team toward the ASSASSIN — guessing it \
loses the game instantly.
- Avoid clues that point to opponent words.

Respond with ONLY valid JSON:
{"clue": "WORD", "number": N, "reasoning": "brief explanation"}
"""

GUESSER_SYSTEM_PROMPT = """\
You are a Field Operative in a game of Codenames. Your Spymaster has given \
you a clue (a word + number). Guess which unrevealed words on the board best \
match the clue.

Rules:
- You may guess up to (clue_number + 1) times per turn.
- Only unrevealed words are valid guesses.
- Correct guess (your team's card): turn continues.
- Neutral card: turn ends immediately.
- Opponent card: turn ends, opponent benefits.
- ASSASSIN card: your team LOSES instantly — be very careful!
- Respond "PASS" to end your turn without guessing.

Respond with ONLY valid JSON:
{"guess": "WORD_OR_PASS", "reasoning": "brief explanation"}
"""


# Base agent -------------------------------------------------------------

class BaseAgent(ABC):
    """Common LLM call logic shared by Spymaster and Guesser."""

    def __init__(
        self,
        model: str,
        system_prompt: str,
        max_retries: int = 3,
        temperature: float = 0.7,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.max_retries = max_retries
        self.temperature = temperature

    def _call_llm(self, user_message: str) -> str:
        """Call the LLM and return the raw text response."""
        try:
            import litellm  # imported lazily so tests can mock it easily
        except ImportError as exc:
            raise ImportError(
                "litellm is required to run LLM agents. "
                "Install it with: pip install litellm"
            ) from exc

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]
        response = litellm.completion(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        return response.choices[0].message.content.strip()

    def _parse_json(self, text: str) -> dict:
        """Extract the first JSON object found in *text*."""
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"No JSON object found in response: {text!r}")
        return json.loads(text[start:end])

    @abstractmethod
    def _build_prompt(self, *args, **kwargs) -> str:
        """Build the user-facing prompt for the LLM."""


# Spymaster agent --------------------------------------------------------

class SpymasterAgent(BaseAgent):
    """LLM agent that acts as the Codenames Spymaster."""

    def __init__(
        self,
        model: str,
        system_prompt: str = SPYMASTER_SYSTEM_PROMPT,
        max_retries: int = 3,
        temperature: float = 0.7,
    ) -> None:
        super().__init__(model, system_prompt, max_retries, temperature)

    def _build_prompt(self, game_view: dict) -> str:  # type: ignore[override]
        team = game_view["current_team"]
        own_color = team
        lines = [
            f"You are the {team.upper()} Spymaster.",
            f"Red remaining: {game_view['red_remaining']}  |  "
            f"Blue remaining: {game_view['blue_remaining']}",
            "",
            "Board (all colors visible to you):",
        ]
        for card in game_view["cards"]:
            status = "[revealed]" if card["revealed"] else ""
            lines.append(
                f"  {card['word']:<20} {card['color'].upper():<10} {status}"
            )
        if game_view["clue_history"]:
            lines.append("\nPrevious clues this game:")
            for cl in game_view["clue_history"]:
                lines.append(
                    f"  [{cl['team'].upper()}] {cl['word']} {cl['number']}"
                )
        lines.append(
            f"\nGive a clue that helps your team ({own_color.upper()}) "
            "identify their unrevealed words."
        )
        return "\n".join(lines)

    def give_clue(self, game_view: dict) -> tuple[str, int]:
        """
        Ask the LLM for a clue.

        Returns ``(clue_word, number)``.
        Raises ``RuntimeError`` if a valid response cannot be obtained after
        ``max_retries`` attempts.
        """
        prompt = self._build_prompt(game_view)
        board_words_upper = {c["word"].upper() for c in game_view["cards"]}
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                raw = self._call_llm(prompt)
                data = self._parse_json(raw)
                clue_word = str(data["clue"]).strip().upper()
                number = int(data["number"])

                if clue_word in board_words_upper:
                    raise ValueError(
                        f"Clue '{clue_word}' is a word on the board."
                    )
                if number < 1:
                    raise ValueError("Clue number must be >= 1.")

                logger.debug(
                    "Spymaster clue (attempt %d): %s %d — %s",
                    attempt,
                    clue_word,
                    number,
                    data.get("reasoning", ""),
                )
                return clue_word, number

            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Spymaster attempt %d/%d failed: %s",
                    attempt,
                    self.max_retries,
                    exc,
                )
                last_error = exc

        raise RuntimeError(
            f"SpymasterAgent failed after {self.max_retries} attempts. "
            f"Last error: {last_error}"
        )


# Guesser agent ----------------------------------------------------------

class GuesserAgent(BaseAgent):
    """LLM agent that acts as the Codenames Field Operative (guesser)."""

    def __init__(
        self,
        model: str,
        system_prompt: str = GUESSER_SYSTEM_PROMPT,
        max_retries: int = 3,
        temperature: float = 0.7,
    ) -> None:
        super().__init__(model, system_prompt, max_retries, temperature)

    def _build_prompt(self, game_view: dict) -> str:  # type: ignore[override]
        team = game_view["current_team"]
        clue = game_view["current_clue"]
        lines = [
            f"You are the {team.upper()} Field Operative.",
            f"Clue: '{clue['word']}' — {clue['number']} word(s).",
            f"Guesses used this turn: {game_view['guesses_this_turn']} / "
            f"{game_view['max_guesses']}.",
            f"Red remaining: {game_view['red_remaining']}  |  "
            f"Blue remaining: {game_view['blue_remaining']}",
            "",
            "Board (unrevealed words have UNKNOWN color):",
        ]
        for card in game_view["cards"]:
            if not card["revealed"]:
                lines.append(f"  {card['word']}")
        if game_view["guess_history"]:
            lines.append("\nThis game's guesses so far:")
            for g in game_view["guess_history"][-10:]:  # last 10 only
                lines.append(
                    f"  [{g['team'].upper()}] {g['word']} → {g['result']}"
                )
        if game_view["clue_history"]:
            lines.append("\nAll clues this game:")
            for cl in game_view["clue_history"]:
                lines.append(
                    f"  [{cl['team'].upper()}] {cl['word']} {cl['number']}"
                )
        lines.append(
            "\nGuess one of the unrevealed words above, or respond PASS."
        )
        return "\n".join(lines)

    def make_guess(self, game_view: dict) -> str:
        """
        Ask the LLM for a guess.

        Returns the guessed word (uppercased) or ``"PASS"``.
        Raises ``RuntimeError`` if a valid response cannot be obtained.
        """
        prompt = self._build_prompt(game_view)
        unrevealed_upper = {
            c["word"].upper()
            for c in game_view["cards"]
            if not c["revealed"]
        }
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                raw = self._call_llm(prompt)
                data = self._parse_json(raw)
                guess = str(data["guess"]).strip().upper()

                if guess == "PASS":
                    logger.debug(
                        "Guesser PASS (attempt %d) — %s",
                        attempt,
                        data.get("reasoning", ""),
                    )
                    return "PASS"

                if guess not in unrevealed_upper:
                    raise ValueError(
                        f"'{guess}' is not an unrevealed word on the board."
                    )

                logger.debug(
                    "Guesser guess (attempt %d): %s — %s",
                    attempt,
                    guess,
                    data.get("reasoning", ""),
                )
                return guess

            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Guesser attempt %d/%d failed: %s",
                    attempt,
                    self.max_retries,
                    exc,
                )
                last_error = exc

        raise RuntimeError(
            f"GuesserAgent failed after {self.max_retries} attempts. "
            f"Last error: {last_error}"
        )
