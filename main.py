"""CLI entry point for running Codenames games and tournaments."""

from __future__ import annotations

import argparse
import logging
import sys

from codenames.elo import Leaderboard
from codenames.game import Team
from codenames.llm import LLMConfig
from codenames.runner import play_game


def run_match(
    model_a: str,
    model_b: str,
    rounds: int = 2,
    leaderboard_path: str = "leaderboard.json",
    verbose: bool = True,
) -> None:
    """Run a match (multiple rounds) between two models, updating ELO."""
    config_a = LLMConfig(model=model_a)
    config_b = LLMConfig(model=model_b)
    leaderboard = Leaderboard.load(leaderboard_path)

    for i in range(rounds):
        # Alternate who plays red/blue each round
        if i % 2 == 0:
            red, blue = config_a, config_b
        else:
            red, blue = config_b, config_a

        print(f"\n{'#'*60}")
        print(f"ROUND {i + 1}/{rounds}")
        print(f"{'#'*60}")

        result = play_game(red, blue, seed=i, verbose=verbose)

        # Map winner back to model
        winner_config = red if result.winner is Team.RED else blue
        loser_config = blue if result.winner is Team.RED else red
        leaderboard.record_match(winner_config.model, loser_config.model)

    leaderboard.save(leaderboard_path)
    print(f"\n{'='*60}")
    print("LEADERBOARD")
    print(f"{'='*60}")
    print(leaderboard.display())


def run_tournament(
    models: list[str],
    rounds_per_match: int = 2,
    leaderboard_path: str = "leaderboard.json",
    verbose: bool = True,
) -> None:
    """Round-robin tournament between all models."""
    leaderboard = Leaderboard.load(leaderboard_path)

    matchups = []
    for i, a in enumerate(models):
        for b in models[i + 1 :]:
            matchups.append((a, b))

    total = len(matchups) * rounds_per_match
    print(f"Tournament: {len(models)} models, {len(matchups)} matchups, {total} games total\n")

    for a, b in matchups:
        run_match(a, b, rounds=rounds_per_match, leaderboard_path=leaderboard_path, verbose=verbose)

    leaderboard = Leaderboard.load(leaderboard_path)
    print(f"\n{'='*60}")
    print("FINAL LEADERBOARD")
    print(f"{'='*60}")
    print(leaderboard.display())


def main() -> None:
    parser = argparse.ArgumentParser(description="Codenames LLM Agent Arena")
    sub = parser.add_subparsers(dest="command")

    # Single match
    match_p = sub.add_parser("match", help="Run a match between two models")
    match_p.add_argument("model_a", help="First model (e.g. anthropic/claude-sonnet-4-20250514)")
    match_p.add_argument("model_b", help="Second model (e.g. openai/gpt-4o)")
    match_p.add_argument("-r", "--rounds", type=int, default=2, help="Rounds per match (default: 2)")
    match_p.add_argument("-l", "--leaderboard", default="leaderboard.json", help="Leaderboard file path")
    match_p.add_argument("-q", "--quiet", action="store_true", help="Suppress verbose output")

    # Tournament
    tourn_p = sub.add_parser("tournament", help="Round-robin tournament")
    tourn_p.add_argument("models", nargs="+", help="Models to compete")
    tourn_p.add_argument("-r", "--rounds", type=int, default=2, help="Rounds per matchup (default: 2)")
    tourn_p.add_argument("-l", "--leaderboard", default="leaderboard.json", help="Leaderboard file path")
    tourn_p.add_argument("-q", "--quiet", action="store_true", help="Suppress verbose output")

    # Leaderboard
    lb_p = sub.add_parser("leaderboard", help="Show current leaderboard")
    lb_p.add_argument("-l", "--leaderboard", default="leaderboard.json", help="Leaderboard file path")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if getattr(args, "quiet", False) else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.command == "match":
        run_match(args.model_a, args.model_b, args.rounds, args.leaderboard, not args.quiet)
    elif args.command == "tournament":
        run_tournament(args.models, args.rounds, args.leaderboard, not args.quiet)
    elif args.command == "leaderboard":
        lb = Leaderboard.load(args.leaderboard)
        print(lb.display())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
