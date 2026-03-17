"""ELO rating system for ranking Codenames teams."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_RATING = 1500
K_FACTOR = 32


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def update_ratings(
    rating_a: float, rating_b: float, score_a: float
) -> tuple[float, float]:
    """Return updated (rating_a, rating_b) after a match.

    score_a: 1.0 for win, 0.0 for loss, 0.5 for draw.
    """
    ea = expected_score(rating_a, rating_b)
    eb = 1.0 - ea
    score_b = 1.0 - score_a
    new_a = rating_a + K_FACTOR * (score_a - ea)
    new_b = rating_b + K_FACTOR * (score_b - eb)
    return round(new_a, 1), round(new_b, 1)


@dataclass
class TeamRecord:
    model: str
    rating: float = DEFAULT_RATING
    wins: int = 0
    losses: int = 0
    games: int = 0

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0


@dataclass
class Leaderboard:
    teams: dict[str, TeamRecord] = field(default_factory=dict)

    def get_or_create(self, model: str) -> TeamRecord:
        if model not in self.teams:
            self.teams[model] = TeamRecord(model=model)
        return self.teams[model]

    def record_match(self, winner_model: str, loser_model: str) -> None:
        winner = self.get_or_create(winner_model)
        loser = self.get_or_create(loser_model)

        winner.rating, loser.rating = update_ratings(winner.rating, loser.rating, 1.0)
        winner.wins += 1
        winner.games += 1
        loser.losses += 1
        loser.games += 1

    def rankings(self) -> list[TeamRecord]:
        return sorted(self.teams.values(), key=lambda t: t.rating, reverse=True)

    def save(self, path: str | Path = "leaderboard.json") -> None:
        data = {
            name: {
                "model": rec.model,
                "rating": rec.rating,
                "wins": rec.wins,
                "losses": rec.losses,
                "games": rec.games,
            }
            for name, rec in self.teams.items()
        }
        Path(path).write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: str | Path = "leaderboard.json") -> Leaderboard:
        p = Path(path)
        if not p.exists():
            return cls()
        data = json.loads(p.read_text())
        teams = {
            name: TeamRecord(**rec) for name, rec in data.items()
        }
        return cls(teams=teams)

    def display(self) -> str:
        lines = [f"{'Rank':<5} {'Model':<40} {'Rating':<8} {'W':<5} {'L':<5} {'Games':<6} {'Win%':<6}"]
        lines.append("-" * 80)
        for i, rec in enumerate(self.rankings(), 1):
            lines.append(
                f"{i:<5} {rec.model:<40} {rec.rating:<8.1f} {rec.wins:<5} "
                f"{rec.losses:<5} {rec.games:<6} {rec.win_rate:<6.1%}"
            )
        return "\n".join(lines)
