"""ELO rating system and persistent leaderboard for Codenames teams."""

import json
import math
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

DEFAULT_ELO = 1000.0
K_FACTOR = 32.0


@dataclass
class TeamRecord:
    """ELO record for a single team configuration."""

    name: str
    model: str
    elo: float = DEFAULT_ELO
    wins: int = 0
    losses: int = 0
    games: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """Return the expected score for player A against player B (0–1)."""
    return 1.0 / (1.0 + math.pow(10, (rating_b - rating_a) / 400.0))


def updated_elo(
    rating: float,
    score: float,
    expected: float,
    k: float = K_FACTOR,
) -> float:
    """Return the new ELO rating after one game."""
    return rating + k * (score - expected)


class Leaderboard:
    """
    JSON-backed ELO leaderboard.

    Teams are identified by their ``name`` field.  The leaderboard is loaded
    from *filepath* on construction and persisted after every :meth:`record`
    call.

    Example::

        lb = Leaderboard("leaderboard.json")
        lb.ensure_team("AlphaBot", model="gpt-4o")
        lb.ensure_team("BetaBot", model="claude-3-opus-20240229")
        lb.record(winner_name="AlphaBot", loser_name="BetaBot")
        lb.display()
    """

    def __init__(self, filepath: str = "leaderboard.json") -> None:
        self.filepath = filepath
        self.teams: Dict[str, TeamRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ensure_team(self, name: str, model: str = "") -> TeamRecord:
        """Return the team record, creating it with default ELO if absent."""
        if name not in self.teams:
            self.teams[name] = TeamRecord(name=name, model=model)
            self._save()
        return self.teams[name]

    def record(self, winner_name: str, loser_name: str) -> None:
        """
        Update ELO ratings after a game.

        Both teams must already exist (call :meth:`ensure_team` first).
        """
        winner = self.teams[winner_name]
        loser = self.teams[loser_name]

        exp_w = expected_score(winner.elo, loser.elo)
        exp_l = expected_score(loser.elo, winner.elo)

        winner.elo = updated_elo(winner.elo, score=1.0, expected=exp_w)
        loser.elo = updated_elo(loser.elo, score=0.0, expected=exp_l)

        winner.wins += 1
        winner.games += 1
        loser.losses += 1
        loser.games += 1

        self._save()

    def rankings(self) -> List[TeamRecord]:
        """Return all teams sorted by ELO descending."""
        return sorted(self.teams.values(), key=lambda t: t.elo, reverse=True)

    def display(self) -> None:
        """Print a formatted leaderboard to stdout."""
        print(
            f"\n{'Rank':<6}{'Name':<20}{'Model':<30}"
            f"{'ELO':>7}{'W':>6}{'L':>6}{'Games':>7}{'Win%':>8}"
        )
        print("-" * 90)
        for rank, team in enumerate(self.rankings(), start=1):
            print(
                f"{rank:<6}{team.name:<20}{team.model:<30}"
                f"{team.elo:>7.1f}{team.wins:>6}{team.losses:>6}"
                f"{team.games:>7}{team.win_rate:>7.1%}"
            )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not os.path.exists(self.filepath):
            return
        with open(self.filepath, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for entry in data:
            record = TeamRecord(**entry)
            self.teams[record.name] = record

    def _save(self) -> None:
        data = [asdict(t) for t in self.teams.values()]
        with open(self.filepath, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
