# CodenamesAgent

A framework for running LLM-powered agents in a full game of
[Codenames](https://en.wikipedia.org/wiki/Codenames_(board_game)) with an
ELO leaderboard.

---

## Overview

* **Two-agent teams** – Each team consists of a *Spymaster* (gives clues) and a
  *Field Operative/Guesser* (guesses words), both powered by the same LLM model.
* **Any LLM** – Uses [litellm](https://github.com/BerriAI/litellm) under the
  hood, so you can plug in OpenAI, Anthropic, Ollama, or any other provider.
* **ELO ranking** – Results are persisted to a JSON leaderboard and ratings
  update automatically after every game.

---

## Quick start

```bash
# 1a. Install dependencies (preferred)
conda env create -f environment.yml 
conda activate codenames

# 1b. Or
pip install -r requirements.txt

# 2a. Set your API key (example for OpenAI)
export OPENAI_API_KEY=sk-...  # mac/linux
$env:OPENAI_API_KEY="sk-..."  # windows 

# 2b. 
# Create .env file with OPENAI_API_KEY, etc.

# 3. Play a game
python main.py play \
    --red-name  "RedBot"  --red-model  "gpt-4o" \
    --blue-name "BlueBot" --blue-model "gpt-4o-mini" \
    --verbose --log-file

# 3.b Powershell
python main.py play `
    --red-name  "RedBot"  --red-model  "gpt-4o-mini" `
    --blue-name "BlueBot" --blue-model "gpt-4o-mini" `
    --verbose --log-file

# 4. View the leaderboard
python main.py leaderboard
```

---

## Project structure

```
codenames/
├── words.py     # 400-word list for board generation
├── game.py      # Pure-Python game engine (board, turns, win conditions)
├── agents.py    # LLM Spymaster & Guesser agents (via litellm)
├── runner.py    # Team class + GameRunner orchestrator
└── elo.py       # ELO rating system + JSON-backed leaderboard

main.py          # CLI entry point
tests/           # pytest test suite
```

---

## Game rules (brief)

* 25 word cards are laid out in a 5×5 grid.
* Red gets **9** cards (if going first), Blue gets **8**; 7 are neutral; 1 is the
  **assassin**.
* Each turn the Spymaster gives a one-word clue + a number.  The Field Operative
  then guesses up to *(number + 1)* words.
* Hitting the assassin loses the game immediately.
* First team to reveal all their cards wins.

---

## Customising prompts

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

## ELO leaderboard

Results are stored in `leaderboard.json` (gitignored).  Use
`Leaderboard` directly for programmatic access:

```python
from codenames.elo import Leaderboard

lb = Leaderboard("leaderboard.json")
lb.display()
```

---

## Running tests

```bash
pytest
```
