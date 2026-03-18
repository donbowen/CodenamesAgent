"""
Add a new model to the Codenames leaderboard via adaptive matchmaking.

Phase 1  (12 games): Plays 1 round (2 games: red + blue) against each of
6 opponents spread evenly across the current ELO spectrum.

Phase 2  (4 games): After Phase 1 the new model has an estimated ELO.  It
then plays 1 round against each of the 2 existing models whose ELO is
closest to that estimate, tightening its placement.

Total: 16 games (vs. 144 for a full round-robin with 9 existing models).

Usage::

    python -m codenames.addnewmodel --name ClaudeSonnet46 --model claude-sonnet-4-6
    python -m codenames.addnewmodel --name MyBot --model gpt-4o --verbose
"""

import argparse
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .elo import Leaderboard, TeamRecord
from .inject_tables import inject_esttab_html
from .remove_tables import remove_esttab_html
from .tournament import (
    _LEADERBOARD_FILE,
    _append_games_json,
    _run_one,
    _validate_models,
)

# ---------------------------------------------------------------------------
# Opponent selection helpers
# ---------------------------------------------------------------------------


def _select_spread_opponents(ranked: list[TeamRecord], n: int = 6) -> list[TeamRecord]:
    """
    Select *n* opponents whose ELO ratings are spread evenly across the full
    spectrum of the ranked list.

    Uses evenly-spaced quantile indices so the new model gets calibration
    games against the best, worst, and middle-tier players.
    """
    total = len(ranked)
    if total <= n:
        return ranked[:]
    # Build n evenly spaced indices in [0, total-1]
    indices = [round(i * (total - 1) / (n - 1)) for i in range(n)]
    seen: set[int] = set()
    result: list[TeamRecord] = []
    for idx in indices:
        if idx not in seen:
            seen.add(idx)
            result.append(ranked[idx])
    return result


def _select_closest_opponents(
    ranked: list[TeamRecord], new_elo: float, n: int = 2
) -> list[TeamRecord]:
    """Return the *n* existing models with ELO closest to *new_elo*."""
    return sorted(ranked, key=lambda t: abs(t.elo - new_elo))[:n]


# ---------------------------------------------------------------------------
# Phase runner
# ---------------------------------------------------------------------------


def _run_phase(
    new_model: tuple[str, str],
    opponents: list[TeamRecord],
    lb: Leaderboard,
    lock: threading.Lock,
    verbose: bool,
    max_workers: int,
    phase_label: str,
) -> None:
    """
    Run one phase: the new model plays 1 round (red + blue) against every
    opponent in *opponents*.  Results are recorded to *lb* under *lock*.
    """
    schedule: list[tuple[tuple[str, str], tuple[str, str]]] = []
    for opp in opponents:
        opp_entry: tuple[str, str] = (opp.name, opp.model)
        schedule.append((new_model, opp_entry))  # new model plays red
        schedule.append((opp_entry, new_model))  # new model plays blue

    total = len(schedule)
    done = 0

    print(f"\n--- {phase_label}: {len(opponents)} opponent(s), {total} games ---\n")

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
                    "Game %s(red) vs %s(blue) failed: %s", red[0], blue[0], exc
                )
                with lock:
                    done += 1
                print(
                    f"  [{done}/{total}] {red[0]}(red) vs {blue[0]}(blue) → ERROR: {exc}"
                )
                continue

            result = data["result"]

            with lock:
                done += 1
                current_done = done

            prefix = f"  [{current_done}/{total}] {red[0]}(red) vs {blue[0]}(blue)"

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
                f"{prefix} → {result.winning_team_name} wins ({result.total_turns} turns)"
            )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def add_new_model(
    new_name: str,
    new_model_str: str,
    leaderboard_file: str = _LEADERBOARD_FILE,
    verbose: bool = False,
    max_workers: int = 4,
) -> None:
    """
    Add *new_name* / *new_model_str* to the leaderboard using a two-phase
    adaptive schedule.

    After this runs, add the model to the ``MODELS`` list in
    ``codenames/tournament.py`` so it participates in future round-robin
    tournaments.
    """
    new_model: tuple[str, str] = (new_name, new_model_str)

    if not _validate_models([new_model]):
        return

    print(f"\nAdding {new_name!r} ({new_model_str}) to the leaderboard.")

    lb = Leaderboard(leaderboard_file)
    lb.ensure_team(new_name, model=new_model_str)

    # Existing opponents sorted best→worst by ELO (new model excluded)
    ranked = [t for t in lb.rankings() if t.name != new_name]
    if len(ranked) < 2:
        raise ValueError(
            "Need at least 2 existing models in the leaderboard to calibrate against."
        )

    lock = threading.Lock()

    # ------------------------------------------------------------------
    # Phase 1 — spread across the ELO spectrum
    # ------------------------------------------------------------------
    n_phase1 = min(6, len(ranked))
    phase1_opponents = _select_spread_opponents(ranked, n=n_phase1)

    print(f"\nPhase 1 opponents (evenly spread across ELO spectrum):")
    for opp in phase1_opponents:
        print(f"  {opp.name:<22} ELO={opp.elo:.1f}")

    _run_phase(
        new_model=new_model,
        opponents=phase1_opponents,
        lb=lb,
        lock=lock,
        verbose=verbose,
        max_workers=max_workers,
        phase_label="Phase 1",
    )

    # ------------------------------------------------------------------
    # Phase 2 — 2 opponents closest to the new model's current ELO
    # ------------------------------------------------------------------
    # Re-load leaderboard so we see ELO updates from Phase 1
    lb2 = Leaderboard(leaderboard_file)
    new_elo_after_phase1 = lb2.teams[new_name].elo
    ranked2 = [t for t in lb2.rankings() if t.name != new_name]

    phase2_opponents = _select_closest_opponents(ranked2, new_elo=new_elo_after_phase1, n=2)

    print(f"\nELO after Phase 1: {new_elo_after_phase1:.1f}")
    print(f"Phase 2 opponents (closest ELO match):")
    for opp in phase2_opponents:
        diff = abs(opp.elo - new_elo_after_phase1)
        print(f"  {opp.name:<22} ELO={opp.elo:.1f}  Δ={diff:.1f}")

    _run_phase(
        new_model=new_model,
        opponents=phase2_opponents,
        lb=lb2,
        lock=lock,
        verbose=verbose,
        max_workers=max_workers,
        phase_label="Phase 2",
    )

    # ------------------------------------------------------------------
    # Final standings + README update
    # ------------------------------------------------------------------
    lb_final = Leaderboard(leaderboard_file)
    print()
    lb_final.display()

    readme = Path("README.md")
    html = Path("game_logs/leaderboard.html")
    lb_final.to_html(str(html))
    remove_esttab_html(readme)
    inject_esttab_html(readme, html)
    print("\nREADME.md leaderboard updated.")
    print(
        f"\nDone!  Remember to add {new_name!r} to MODELS in codenames/tournament.py "
        "so it participates in future round-robin tournaments."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="addnewmodel",
        description=(
            "Add a new model to the Codenames leaderboard via adaptive matchmaking. "
            "Phase 1: 6 spread opponents (12 games). "
            "Phase 2: 2 closest-ELO opponents (4 games)."
        ),
    )
    parser.add_argument(
        "--name",
        required=True,
        metavar="NAME",
        help="Short identifier for the new model (e.g. ClaudeSonnet46).",
    )
    parser.add_argument(
        "--model",
        required=True,
        metavar="MODEL",
        help="LiteLLM model string (e.g. claude-sonnet-4-6).",
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
    add_new_model(
        new_name=args.name,
        new_model_str=args.model,
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
