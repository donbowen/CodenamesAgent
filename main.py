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
import logging
import sys
from pathlib import Path

from codenames.elo import Leaderboard
from codenames.runner import GameRunner, Team


class _Tee:
    """Write to both an original stream and a log file simultaneously."""

    def __init__(self, original, file_path: str):
        self._orig = original
        self._file = open(file_path, "w", encoding="utf-8")  # noqa: SIM115

    def write(self, data):
        self._orig.write(data)
        self._file.write(data)

    def flush(self):
        self._orig.flush()
        self._file.flush()

    def close(self):
        self._file.close()


def cmd_play(args: argparse.Namespace) -> None:
    red_team = Team(name=args.red_name, model=args.red_model)
    blue_team = Team(name=args.blue_name, model=args.blue_model)

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


def cmd_leaderboard(args: argparse.Namespace) -> None:
    lb = Leaderboard(args.leaderboard_file)
    if not lb.teams:
        print("No teams in the leaderboard yet. Play some games first!")
    else:
        lb.display()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codenames",
        description="Run LLM agent Codenames games with ELO tracking.",
    )
    parser.add_argument(
        "--leaderboard-file",
        default="leaderboard.json",
        metavar="FILE",
        help="Path to the JSON leaderboard file (default: leaderboard.json).",
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
    play_parser.add_argument(
        "--log-file",
        metavar="FILE",
        default=None,
        help="Write all output (play-by-play + warnings) to FILE.",
    )
    play_parser.set_defaults(func=cmd_play)

    # leaderboard ----------------------------------------------------
    lb_parser = subs.add_parser("leaderboard", help="Display the ELO leaderboard.")
    lb_parser.set_defaults(func=cmd_leaderboard)

    return parser


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    tee_out = tee_err = None
    log_file = getattr(args, "log_file", None)
    if log_file:
        tee_out = _Tee(sys.stdout, log_file)
        tee_err = _Tee(sys.stderr, log_file)
        sys.stdout = tee_out  # type: ignore[assignment]
        sys.stderr = tee_err  # type: ignore[assignment]

    try:
        args.func(args)
    finally:
        if tee_out:
            sys.stdout = tee_out._orig
            sys.stderr = tee_err._orig
            tee_out.close()
            tee_err.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    main()
