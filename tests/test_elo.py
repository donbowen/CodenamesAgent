"""Unit tests for the ELO system and Leaderboard."""

import json
import os
import tempfile

import pytest

from codenames.elo import (
    DEFAULT_ELO,
    K_FACTOR,
    Leaderboard,
    TeamRecord,
    expected_score,
    updated_elo,
)


# ---------------------------------------------------------------------------
# ELO math
# ---------------------------------------------------------------------------

class TestEloMath:
    def test_expected_score_equal_ratings(self):
        score = expected_score(1000, 1000)
        assert abs(score - 0.5) < 1e-9

    def test_expected_score_higher_rating_wins_more(self):
        assert expected_score(1200, 1000) > 0.5
        assert expected_score(1000, 1200) < 0.5

    def test_expected_scores_sum_to_one(self):
        e1 = expected_score(1300, 900)
        e2 = expected_score(900, 1300)
        assert abs(e1 + e2 - 1.0) < 1e-9

    def test_updated_elo_win(self):
        new = updated_elo(rating=1000, score=1.0, expected=0.5, k=32)
        assert new == pytest.approx(1016.0)

    def test_updated_elo_loss(self):
        new = updated_elo(rating=1000, score=0.0, expected=0.5, k=32)
        assert new == pytest.approx(984.0)

    def test_updated_elo_draw(self):
        new = updated_elo(rating=1000, score=0.5, expected=0.5, k=32)
        assert new == pytest.approx(1000.0)

    def test_elo_sum_conserved_after_game(self):
        """Total ELO in the system must be conserved after a match."""
        ra, rb = 1000.0, 1000.0
        ea = expected_score(ra, rb)
        eb = expected_score(rb, ra)
        new_a = updated_elo(ra, 1.0, ea)
        new_b = updated_elo(rb, 0.0, eb)
        assert abs((new_a + new_b) - (ra + rb)) < 1e-6


# ---------------------------------------------------------------------------
# TeamRecord
# ---------------------------------------------------------------------------

class TestTeamRecord:
    def test_default_elo(self):
        t = TeamRecord(name="Bot", model="gpt-4o")
        assert t.elo == DEFAULT_ELO

    def test_win_rate_zero_games(self):
        t = TeamRecord(name="Bot", model="gpt-4o")
        assert t.win_rate == 0.0

    def test_win_rate(self):
        t = TeamRecord(name="Bot", model="gpt-4o", wins=3, games=4)
        assert t.win_rate == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

@pytest.fixture
def lb_file(tmp_path):
    return str(tmp_path / "test_leaderboard.json")


class TestLeaderboard:
    def test_ensure_team_creates_entry(self, lb_file):
        lb = Leaderboard(lb_file)
        t = lb.ensure_team("Alpha", model="gpt-4o")
        assert t.name == "Alpha"
        assert t.elo == DEFAULT_ELO

    def test_ensure_team_idempotent(self, lb_file):
        lb = Leaderboard(lb_file)
        lb.ensure_team("Alpha", model="gpt-4o")
        lb.ensure_team("Alpha", model="gpt-4o")
        assert len(lb.teams) == 1

    def test_record_updates_elo(self, lb_file):
        lb = Leaderboard(lb_file)
        lb.ensure_team("Alpha", model="gpt-4o")
        lb.ensure_team("Beta", model="gpt-4o-mini")
        lb.record("Alpha", "Beta")
        assert lb.teams["Alpha"].elo > DEFAULT_ELO
        assert lb.teams["Beta"].elo < DEFAULT_ELO

    def test_record_updates_win_loss_counts(self, lb_file):
        lb = Leaderboard(lb_file)
        lb.ensure_team("Alpha", model="gpt-4o")
        lb.ensure_team("Beta", model="gpt-4o-mini")
        lb.record("Alpha", "Beta")
        assert lb.teams["Alpha"].wins == 1
        assert lb.teams["Alpha"].losses == 0
        assert lb.teams["Beta"].wins == 0
        assert lb.teams["Beta"].losses == 1

    def test_record_increments_games(self, lb_file):
        lb = Leaderboard(lb_file)
        lb.ensure_team("Alpha", model="gpt-4o")
        lb.ensure_team("Beta", model="gpt-4o-mini")
        lb.record("Alpha", "Beta")
        assert lb.teams["Alpha"].games == 1
        assert lb.teams["Beta"].games == 1

    def test_persistence_across_instances(self, lb_file):
        lb1 = Leaderboard(lb_file)
        lb1.ensure_team("Alpha", model="gpt-4o")
        lb1.ensure_team("Beta", model="gpt-4o-mini")
        lb1.record("Alpha", "Beta")
        alpha_elo = lb1.teams["Alpha"].elo

        lb2 = Leaderboard(lb_file)
        assert "Alpha" in lb2.teams
        assert lb2.teams["Alpha"].elo == pytest.approx(alpha_elo)

    def test_rankings_sorted_by_elo(self, lb_file):
        lb = Leaderboard(lb_file)
        lb.ensure_team("Alpha", model="gpt-4o")
        lb.ensure_team("Beta", model="gpt-4o-mini")
        lb.record("Alpha", "Beta")
        lb.record("Alpha", "Beta")
        ranked = lb.rankings()
        assert ranked[0].name == "Alpha"

    def test_missing_file_starts_empty(self, lb_file):
        lb = Leaderboard(lb_file)
        assert lb.teams == {}

    def test_json_file_structure(self, lb_file):
        lb = Leaderboard(lb_file)
        lb.ensure_team("Alpha", model="gpt-4o")
        with open(lb_file) as fh:
            data = json.load(fh)
        assert isinstance(data, list)
        assert data[0]["name"] == "Alpha"
        assert "elo" in data[0]
