# CodenamesBench

A framework for running LLM-powered agents in a full game of
[Codenames](https://en.wikipedia.org/wiki/Codenames_(board_game)) with an
ELO leaderboard.

## Leaderboard

<!-- ESTTAB:START:game_logs/leaderboard.html -->

<table>
<thead><tr><th>Rank</th><th>Name</th><th>Model</th><th>ELO</th><th>W</th><th>L</th><th>Games</th><th>Win%</th></tr></thead>
<tbody>
<tr><td>1</td><td>GPT5Mini</td><td>gpt-5-mini</td><td>1173.1</td><td>29</td><td>5</td><td>34</td><td>85.3%</td></tr>
<tr><td>2</td><td>ClaudeSonnet45</td><td>claude-sonnet-4-5-20250929</td><td>1117.9</td><td>17</td><td>7</td><td>24</td><td>70.8%</td></tr>
<tr><td>3</td><td>ClaudeOpus46</td><td>claude-opus-4-6</td><td>1073.1</td><td>11</td><td>5</td><td>16</td><td>68.8%</td></tr>
<tr><td>4</td><td>ClaudeSonnet46</td><td>claude-sonnet-4-6</td><td>1037.0</td><td>10</td><td>6</td><td>16</td><td>62.5%</td></tr>
<tr><td>5</td><td>GPT5Nano</td><td>gpt-5-nano</td><td>1019.3</td><td>18</td><td>16</td><td>34</td><td>52.9%</td></tr>
<tr><td>6</td><td>GPT54</td><td>gpt-5.4</td><td>1010.3</td><td>18</td><td>18</td><td>36</td><td>50.0%</td></tr>
<tr><td>7</td><td>GPT51</td><td>gpt-5.1</td><td>972.2</td><td>15</td><td>19</td><td>34</td><td>44.1%</td></tr>
<tr><td>8</td><td>GPT41Mini</td><td>gpt-4.1-mini</td><td>960.8</td><td>13</td><td>17</td><td>30</td><td>43.3%</td></tr>
<tr><td>9</td><td>GPT41</td><td>gpt-4.1</td><td>939.6</td><td>13</td><td>17</td><td>30</td><td>43.3%</td></tr>
<tr><td>10</td><td>ClaudeSonnet4</td><td>claude-sonnet-4-20250514</td><td>922.7</td><td>7</td><td>15</td><td>22</td><td>31.8%</td></tr>
<tr><td>11</td><td>GPT4oMini</td><td>gpt-4o-mini</td><td>774.0</td><td>3</td><td>29</td><td>32</td><td>9.4%</td></tr>
</tbody>
</table>

<!-- ESTTAB:END:game_logs/leaderboard.html -->

## Building and updating the leaderboard.

1. Initialize the leaderboard. The models are set in `codenames/tournament.py`, and should come from https://models.litellm.ai/ 
  ```bash
  conda activate codenames
  python -m codenames.tournament --rounds 1
  ```

2. Add a new model to the leaderboard. It plays 16 adaptive games: 12 against 6 opponents spread across the ELO spectrum (Phase 1), then 4 more against the 2 closest-rated opponents once its initial ELO is known (Phase 2). Then add the model to `MODELS` in `codenames/tournament.py` for future round-robin tournaments.
  ```bash
  conda activate codenames
  python -m codenames.addnewmodel --name ClaudeSonnet46 --model claude-sonnet-4-6
  ```

---

## Overview of Repo and Usage

* **Two-agent teams** – Each team consists of a *Spymaster* (gives clues) and a
  *Field Operative/Guesser* (guesses words), both powered by the same LLM model.
* **Any LLM** – Uses [litellm](https://github.com/BerriAI/litellm) under the
  hood, so you can plug in OpenAI, Anthropic, Ollama, or any other provider.
* **ELO ranking** – Results are persisted to a JSON leaderboard and ratings
  update automatically after every game.

---

### Quick start - playing a single game 

```bash
# 1a. Install dependencies (preferred)
conda env create -f environment.yml 
conda activate codenames

# 1b. Or
pip install -r requirements.txt

# 2a. Set your API key(s) per provider
export OPENAI_API_KEY=sk-...  # mac/linux
$env:OPENAI_API_KEY="sk-..."  # windows 
.env file can be used.

# 2b. 
# Create .env file with OPENAI_API_KEY, etc.

# 3. Play a game
python main.py play \
    --red-name  "gpt-4o-mini-Std-Prompt"  --red-model  "gpt-4o-mini" `
    --blue-name "gpt-5-mini-2025-08-07-Std-Prompt" --blue-model "gpt-5-mini-2025-08-07" `
    --verbose 

# 3.b Powershell
python main.py play `
    --red-name  "gpt-4o-mini-Std-Prompt"  --red-model  "gpt-4o-mini" `
    --blue-name "gpt-5-mini-2025-08-07-Std-Prompt" --blue-model "gpt-5-mini-2025-08-07" `
    --verbose 

# 4. View the leaderboard
python main.py leaderboard
```

---

### Project structure

```
codenames/
├── words.py          # 400-word list for board generation
├── game.py           # Pure-Python game engine (board, turns, win conditions)
├── agents.py         # LLM Spymaster & Guesser agents (via litellm)
├── runner.py         # Team class + GameRunner orchestrator
├── elo.py            # ELO rating system + JSON-backed leaderboard
├── tournament.py     # Round-robin benchmark runner (parallel games)
├── inject_tables.py  # Injects HTML tables into README between ESTTAB markers
└── remove_tables.py  # Removes injected HTML tables from README

main.py               # CLI: play a single game or view the leaderboard
tests/                # pytest test suite

game_logs/
├── leaderboard.json        # ELO ratings (updated after every game)
├── leaderboard.html        # HTML leaderboard (injected into README)
├── games.json              # Per-game records (appended after every game)
└── full_records/
    ├── {game_id}.txt        # Play-by-play log
    └── {game_id}_prompts.txt  # Full LLM prompt/response log
```

---

### Game rules (brief)

* 25 word cards are laid out in a 5×5 grid.
* Red gets **9** cards (if going first), Blue gets **8**; 7 are neutral; 1 is the
  **assassin**.
* Each turn the Spymaster gives a one-word clue + a number.  The Field Operative
  then guesses up to *(number + 1)* words.
* Hitting the assassin loses the game immediately.
* First team to reveal all their cards wins.

---

### Customising prompts

Pass custom system prompts when building a `Team`:

```python
from codenames.runner import Team

team = Team(
    name="MyBot",
    model="claude-3-5-sonnet-20241022",
    spymaster_prompt="You are an expert Codenames Spymaster ...",
    guesser_prompt="You are an expert Field Operative ...",
)
```

---

### ELO leaderboard

Results are stored in `leaderboard.json` (gitignored).  Use
`Leaderboard` directly for programmatic access:

```python
from codenames.elo import Leaderboard

lb = Leaderboard("leaderboard.json")
lb.display()
```

---

### Running tests

```bash
pytest
```
