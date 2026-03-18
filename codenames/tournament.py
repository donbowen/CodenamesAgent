"""
Codenames LLM Benchmark — round-robin tournament with ELO tracking.

Runs every model pair twice per round (color-swapped) in parallel, then
updates the shared leaderboard and game log under a lock.

Usage::

    python -m codenames.tournament                        # 2 rounds, default models
    python -m codenames.tournament --rounds 5             # more rounds for tighter ELO
    python -m codenames.tournament --verbose              # print play-by-play per game
    python -m codenames.tournament --leaderboard-file game_logs/leaderboard.json

Environment variables for API keys are read by litellm automatically::

    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...
"""

import argparse
import json
import logging
import os 
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .elo import Leaderboard
from .inject_tables import inject_esttab_html
from .remove_tables import remove_esttab_html
from .runner import GameRunner, Team

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODELS: list[tuple[str, str]] = [
    # --- Frontier / best quality ---
    ("GPT54", "gpt-5.4"),
    # ('ClaudeOpus46', 'claude-opus-4-6'),
    # ('ClaudeSonnet46','claude-sonnet-4-6'),

    # --- Strong general-purpose ---
# ("GPT52", "gpt-5.2"),
    ("GPT51", "gpt-5.1"),
# ("GPT5", "gpt-5"),
    ("GPT5Mini", "gpt-5-mini"),
    ("GPT5Nano", "gpt-5-nano"),
    ('ClaudeSonnet45','claude-sonnet-4-5-20250929'),
# ('Gemini31FlashLite','gemini/gemini-3.1-flash-lite-preview'),

    # --- Non-reasoning / fast high-quality ---
# ('Gemini25FlashLite','gemini/gemini-2.5-flash-lite'),
# ('Gemini25Flash','gemini/gemini-2.5-flash'),
    ('ClaudeSonnet4','claude-sonnet-4-20250514'),
    ("GPT41", "gpt-4.1"),
    ("GPT41Mini", "gpt-4.1-mini"),
# ("GPT41Nano", "gpt-4.1-nano"),

    # --- Legacy but still widely used ---
    # ("GPT4o", "gpt-4o"),
    ("GPT4oMini", "gpt-4o-mini"),
]
_LEADERBOARD_FILE = "game_logs/leaderboard.json"
_DEFAULT_ROUNDS = 2

os.makedirs(_LEADERBOARD_FILE.rsplit("/", 1)[0], exist_ok=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_models(models: list[tuple[str, str]]) -> bool:
    """
    Check that every model has its required API keys set.

    Prints a warning for each invalid model. Returns True if all pass,
    False if any fail (caller should abort).
    """
    import litellm

    invalid = []
    for name, model in models:
        # Check the model string is resolvable (known provider + model)
        try:
            litellm.get_llm_provider(model)
        except Exception as exc:  # noqa: BLE001
            invalid.append((name, model, str(exc)))
            continue

        # Check required API keys are present
        check = litellm.validate_environment(model)
        if not check.get("keys_in_environment", False):
            missing = ", ".join(check.get("missing_keys", ["unknown"]))
            invalid.append((name, model, f"missing API keys: {missing}"))

    if invalid:
        print("ERROR: the following models cannot run:")
        for name, model, reason in invalid:
            print(f"  {name!r} ({model}) — {reason}")
        return False
    return True


def _make_game_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _matchups(
    models: list[tuple[str, str]], rounds: int
) -> list[tuple[tuple[str, str], tuple[str, str]]]:
    """Return the full schedule: every pair twice (color-swapped) per round."""
    pairs = [
        (models[i], models[j])
        for i in range(len(models))
        for j in range(i + 1, len(models))
    ]
    schedule = []
    for _ in range(rounds):
        for red, blue in pairs:
            schedule.append((red, blue))   # red plays red
            schedule.append((blue, red))   # color-swapped
    return schedule


_MAX_PAIR_GAMES = 4


def _played_counts() -> dict[frozenset, int]:
    """Return a counter of games already played per unordered pair of names."""
    games_path = Path("game_logs/games.json")
    if not games_path.exists():
        return {}
    counts: dict[frozenset, int] = {}
    for g in json.loads(games_path.read_text(encoding="utf-8")):
        key = frozenset({g["red_name"], g["blue_name"]})
        counts[key] = counts.get(key, 0) + 1
    return counts


def _filter_played(
    schedule: list[tuple[tuple[str, str], tuple[str, str]]],
) -> list[tuple[tuple[str, str], tuple[str, str]]]:
    """Remove matchups where the pair has already reached _MAX_PAIR_GAMES."""
    counts = _played_counts()
    filtered = []
    skipped: dict[frozenset, int] = {}
    for red, blue in schedule:
        key = frozenset({red[0], blue[0]})
        played = counts.get(key, 0)
        if played >= _MAX_PAIR_GAMES:
            skipped[key] = played
        else:
            counts[key] = played + 1  # reserve this slot
            filtered.append((red, blue))
    if skipped:
        print("Skipping already-saturated pairs (≥ 4 games played):")
        for key, n in skipped.items():
            a, b = sorted(key)
            print(f"  {a} vs {b}: {n} games")
        print()
    return filtered


def _append_games_json(entry: dict) -> None:
    games_path = Path("game_logs/games.json")
    games = json.loads(games_path.read_text(encoding="utf-8")) if games_path.exists() else []
    games.append(entry)
    games_path.write_text(json.dumps(games, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Per-game worker (runs in a thread)
# ---------------------------------------------------------------------------

def _run_one(
    red: tuple[str, str],
    blue: tuple[str, str],
    verbose: bool,
) -> dict:
    """Play one game and return a result dict. No shared mutable state used here."""
    game_id = _make_game_id()
    Path("game_logs/full_records").mkdir(parents=True, exist_ok=True)
    log_path = Path(f"game_logs/full_records/{game_id}.txt")
    prompts_path = log_path.with_stem(log_path.stem + "_prompts")

    with open(log_path, "w", encoding="utf-8") as f_log, \
         open(prompts_path, "w", encoding="utf-8") as f_prompts:

        red_team = Team(name=red[0], model=red[1], prompt_log=f_prompts)
        blue_team = Team(name=blue[0], model=blue[1], prompt_log=f_prompts)

        runner = GameRunner(
            red_team=red_team,
            blue_team=blue_team,
            verbose=verbose,
        )
        result = runner.run()

        if verbose:
            summary = (
                f"  → {result.winning_team_name} wins "
                f"({result.total_turns} turns)"
            )
            f_log.write(summary + "\n")

    return {
        "game_id": game_id,
        "red": red,
        "blue": blue,
        "result": result,
    }


# ---------------------------------------------------------------------------
# Tournament entry point
# ---------------------------------------------------------------------------

def run_tournament(
    models: list[tuple[str, str]],
    rounds: int,
    leaderboard_file: str,
    verbose: bool,
    max_workers: int = 4,
) -> None:
    if len(models) < 2:
        raise ValueError("Need at least 2 models to run a tournament.")

    if not _validate_models(models):
        return

    schedule = _matchups(models, rounds)
    schedule = _filter_played(schedule)
    total = len(schedule)
    done = 0
    lock = threading.Lock()

    lb = Leaderboard(leaderboard_file)
    for name, model in models:
        lb.ensure_team(name, model=model)

    print(
        f"\nBenchmark: {len(models)} models, {rounds} round(s), "
        f"{total} games total ({max_workers} workers).\n"
    )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_run_one, red, blue, verbose): (red, blue)
            for red, blue in schedule
        }

        for future in as_completed(futures):
            red, blue = futures[future]
            try:
                data = future.result()
            except Exception as exc:  # noqa: BLE001
                logging.error(
                    "Game %s(red) vs %s(blue) failed: %s",
                    red[0], blue[0], exc,
                )
                with lock:
                    done += 1
                print(f"[{done}/{total}] {red[0]}(red) vs {blue[0]}(blue) → ERROR: {exc}")
                continue

            result = data["result"]

            with lock:
                done += 1
                current_done = done

            prefix = f"[{current_done}/{total}] {red[0]}(red) vs {blue[0]}(blue)"

            if result.error_turns > 0:
                print(
                    f"{prefix} → INVALID ({result.error_turns} error turn(s)) — not counted"
                )
                continue

            entry = {
                "game_id": data["game_id"],
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "red_name": red[0],
                "red_model": red[1],
                "blue_name": blue[0],
                "blue_model": blue[1],
                "winner_name": result.winning_team_name,
                "winner_color": result.winner.value,
                "total_turns": result.total_turns,
            }

            with lock:
                lb.record(
                    winner_name=result.winning_team_name,
                    loser_name=result.losing_team_name,
                )
                _append_games_json(entry)

            print(
                f"{prefix} → {result.winning_team_name} wins "
                f"({result.total_turns} turns)"
            )

    print()
    lb.display()

    readme = Path("README.md")
    html = Path("game_logs/leaderboard.html")
    lb.to_html(str(html))
    remove_esttab_html(readme)
    inject_esttab_html(readme, html)
    print("\nREADME.md leaderboard updated.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tournament",
        description="Run a round-robin LLM Codenames benchmark with ELO tracking.",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=_DEFAULT_ROUNDS,
        metavar="N",
        help=f"Number of round-robin rounds (default: {_DEFAULT_ROUNDS}). "
             "Each round plays every pair twice (color-swapped).",
    )
    parser.add_argument(
        "--leaderboard-file",
        default=_LEADERBOARD_FILE,
        metavar="FILE",
        help=f"Path to the JSON leaderboard file (default: {_LEADERBOARD_FILE}).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print play-by-play commentary inside each game log.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        metavar="N",
        help="Max parallel games (default: 4). Lower to reduce API rate-limit errors.",
    )
    return parser


def main(argv=None) -> None:
    args = _build_parser().parse_args(argv)
    run_tournament(
        models=MODELS,
        rounds=args.rounds,
        leaderboard_file=args.leaderboard_file,
        verbose=args.verbose,
        max_workers=args.max_workers,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    main()
