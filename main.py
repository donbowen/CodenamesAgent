"""
CodenamesAgent – command-line interface.

Usage examples
--------------
Play a game between two OpenAI-powered teams::

    python main.py play \\
        --red-name  "RedBot"  --red-model  "gpt-4o" \\
        --blue-name "BlueBot" --blue-model "gpt-4o-mini"

Play with a fixed random seed (reproducible board)::

    python main.py play --seed 42 --verbose \\
        --red-name "RedBot" --red-model "gpt-4o" \\
        --blue-name "BlueBot" --blue-model "gpt-4o-mini"

Show the current leaderboard::

    python main.py leaderboard

Environment variables for API keys are read by litellm automatically, e.g.::

    OPENAI_API_KEY=sk-...
    ANTHROPIC_API_KEY=sk-ant-...
"""

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from codenames.elo import Leaderboard
from codenames.runner import GameRunner, Team

_LEADERBOARD_FILE = "game_logs/leaderboard.json"


def _make_game_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


class _Tee:
    """Mirror a stream to one or more open file objects simultaneously."""

    def __init__(self, original, *files):
        self._orig = original
        self._files = files

    def write(self, data):
        self._orig.write(data)
        for f in self._files:
            f.write(data)

    def flush(self):
        self._orig.flush()
        for f in self._files:
            f.flush()


def _refresh_readme(leaderboard_file: str) -> None:
    """Regenerate game_logs/leaderboard.html and inject it into README.md."""
    from codenames.inject_tables import inject_esttab_html
    from codenames.remove_tables import remove_esttab_html

    readme = Path("README.md")
    html = Path("game_logs/leaderboard.html")
    Leaderboard(leaderboard_file).to_html(str(html))
    remove_esttab_html(readme)
    inject_esttab_html(readme, html)


def cmd_play(args: argparse.Namespace) -> None:
    red_team = Team(name=args.red_name, model=args.red_model, prompt_log=args.prompt_log)
    blue_team = Team(name=args.blue_name, model=args.blue_model, prompt_log=args.prompt_log)

    runner = GameRunner(
        red_team=red_team,
        blue_team=blue_team,
        seed=args.seed,
        verbose=args.verbose,
    )

    print(
        f"\nStarting game: {args.red_name} (red, {args.red_model}) "
        f"vs {args.blue_name} (blue, {args.blue_model})"
    )
    result = runner.run()

    print(
        f"\n{'=' * 60}\n"
        f"Winner: {result.winning_team_name} ({result.winner.value.upper()})\n"
        f"Turns played: {result.total_turns}\n"
        f"{'=' * 60}"
    )

    # Update leaderboard
    lb = Leaderboard(args.leaderboard_file)
    lb.ensure_team(args.red_name, model=args.red_model)
    lb.ensure_team(args.blue_name, model=args.blue_model)
    lb.record(
        winner_name=result.winning_team_name,
        loser_name=result.losing_team_name,
    )
    print(f"\nLeaderboard updated ({args.leaderboard_file}).")
    _refresh_readme(args.leaderboard_file)

    # Append per-game record to games.json
    games_path = Path("game_logs/games.json")
    games = json.loads(games_path.read_text(encoding="utf-8")) if games_path.exists() else []
    games.append({
        "game_id": args.game_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "red_name": args.red_name,
        "red_model": args.red_model,
        "blue_name": args.blue_name,
        "blue_model": args.blue_model,
        "winner_name": result.winning_team_name,
        "winner_color": result.winner.value,
        "total_turns": result.total_turns,
    })
    games_path.write_text(json.dumps(games, indent=2), encoding="utf-8")
    print(f"Game record saved (game_logs/games.json, id={args.game_id}).")


def cmd_leaderboard(args: argparse.Namespace) -> None:
    lb = Leaderboard(args.leaderboard_file)
    if not lb.teams:
        print("No teams in the leaderboard yet. Play some games first!")
    else:
        lb.display()
        _refresh_readme(args.leaderboard_file)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codenames",
        description="Run LLM agent Codenames games with ELO tracking.",
    )
    parser.add_argument(
        "--leaderboard-file",
        default=_LEADERBOARD_FILE,
        metavar="FILE",
        help=f"Path to the JSON leaderboard file (default: {_LEADERBOARD_FILE}).",
    )

    subs = parser.add_subparsers(dest="command", required=True)

    # play -----------------------------------------------------------
    play_parser = subs.add_parser("play", help="Play a game between two teams.")
    play_parser.add_argument("--red-name", required=True, help="Red team name.")
    play_parser.add_argument(
        "--red-model", required=True, help="Red team LLM model (litellm string)."
    )
    play_parser.add_argument("--blue-name", required=True, help="Blue team name.")
    play_parser.add_argument(
        "--blue-model", required=True, help="Blue team LLM model (litellm string)."
    )
    play_parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducible boards."
    )
    play_parser.add_argument(
        "--verbose", action="store_true", help="Print play-by-play commentary."
    )
    play_parser.set_defaults(func=cmd_play)

    # leaderboard ----------------------------------------------------
    lb_parser = subs.add_parser("leaderboard", help="Display the ELO leaderboard.")
    lb_parser.set_defaults(func=cmd_leaderboard)

    return parser


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    f_log = f_prompts = None
    if args.command == "play":
        game_id = _make_game_id()
        args.game_id = game_id
        Path("game_logs/full_records").mkdir(parents=True, exist_ok=True)
        log_path = Path(f"game_logs/full_records/{game_id}.txt")
        prompts_path = log_path.with_stem(log_path.stem + "_prompts")
        f_log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
        f_prompts = open(prompts_path, "w", encoding="utf-8")  # noqa: SIM115
        sys.stdout = _Tee(sys.stdout, f_log, f_prompts)  # type: ignore[assignment]
        sys.stderr = _Tee(sys.stderr, f_log, f_prompts)  # type: ignore[assignment]
        args.prompt_log = f_prompts
    else:
        args.prompt_log = None

    try:
        args.func(args)
    finally:
        if f_log:
            sys.stdout = sys.stdout._orig  # type: ignore[union-attr]
            sys.stderr = sys.stderr._orig  # type: ignore[union-attr]
            f_log.close()
            f_prompts.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    main()
