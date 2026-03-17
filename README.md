# CodenamesAgent

LLM agents play Codenames against each other, rated by ELO.

Each team is two agents (Spymaster + Guesser) spawned from the same model. Uses [litellm](https://docs.litellm.ai/) for multi-provider LLM support (Anthropic, OpenAI, Google, etc.).

## Setup

```bash
pip install -r requirements.txt
```

Set API keys as environment variables (or via GitHub Secrets for CI):

```bash
export ANTHROPIC_API_KEY=sk-...
export OPENAI_API_KEY=sk-...
```

## Usage

**Run a match between two models:**

```bash
python main.py match anthropic/claude-sonnet-4-20250514 openai/gpt-4o
```

**Run a round-robin tournament:**

```bash
python main.py tournament anthropic/claude-sonnet-4-20250514 openai/gpt-4o google/gemini-2.0-flash
```

**View the leaderboard:**

```bash
python main.py leaderboard
```

## Options

- `-r, --rounds` — Rounds per matchup (default: 2, teams alternate red/blue)
- `-q, --quiet` — Suppress verbose game output
- `-l, --leaderboard` — Path to leaderboard JSON file

## Architecture

```
codenames/
  game.py     — Board setup, card colors, rules, state machine
  agents.py   — LLM Spymaster and Guesser prompts + parsing
  llm.py      — LLM provider abstraction (litellm)
  elo.py      — ELO rating system and leaderboard persistence
  runner.py   — Game loop: alternates clue/guess turns until a winner
  words.py    — Default 400-word list
main.py       — CLI entry point (match / tournament / leaderboard)
```
