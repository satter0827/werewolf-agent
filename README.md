Below is a faithful, professional English translation suitable for a README, portfolio, or PyPI description.
The tone is neutral–positive and aligned with software engineering conventions.

---

# Werewolf LLM Engine — LLM-Driven Werewolf Game Core

---

## Overview

This project is a **Python-based, headless game engine designed to execute Werewolf games using large language models (LLMs)**.
It provides no UI/UX or communication layer and is intended to be used as a **library invoked from higher-level systems** such as CLI tools, web applications, bots, or experimental platforms.

The library implements the core logic of the Werewolf game, including phase management, role ability resolution, voting and execution, and win-condition evaluation.
Each player’s dialogue and decision-making are abstracted as LLM-driven agents.

Game rules, configurations, and prompts are fully injectable from external sources, enabling flexible use across **research, experimentation, agent comparison, and game design validation**.
The project aims to serve as a **general-purpose execution core for LLM-based Werewolf simulations**.

---

## Design Principles

* Do not fix UI or input/output mechanisms; optimize for embedded use
* Keep roles, rules, and LLMs loosely coupled to ensure extensibility
* Clearly define boundaries and interfaces, assuming control from higher-level layers
* Emphasize reproducibility through deterministic execution and random seed control

---

## Key Features

The engine focuses on orchestrating Werewolf game execution while integrating LLM-based agents for dialogue, voting, and ability usage.

* **Game Execution Engine**
  Manages phase transitions such as night, day, voting, execution, and win-condition evaluation, while consistently updating game state.

* **Role and Ability System**
  Defines roles such as werewolves, villagers, and seers in an extensible manner, with controllable ability resolution order and conflict handling.

* **LLM-Driven Agent Decisions**
  Player dialogue, voting, and ability usage are determined by LLM-based or rule-based agents.

* **Config-Driven Architecture**
  Role composition, win conditions, dialogue constraints, prompts, and random seeds can be specified externally.

* **Structured Event Output**
  Game events such as dialogue, votes, ability results, deaths, and victories are emitted in a structured format suitable for higher-level systems.

* **Reproducible Game Execution**
  Identical configurations and seeds guarantee identical execution, making the engine suitable for experimentation and validation.

---

## Scope

This project deliberately focuses on the **core logic of a Werewolf game engine**.
The following areas are explicitly out of scope:

* **User Interface Layer**
  Chat UIs, web interfaces, and voice input/output are excluded and expected to be implemented externally.

* **Persistence and Data Management**
  Storage formats and destinations for logs, conversations, and results are not prescribed.

* **LLM Credential Management**
  API keys and model configuration are expected to be managed outside the library.

* **Matching and Room Management**
  Multiplayer orchestration and session management are not included.

---

## Differentiation from Other Libraries

This library is specifically designed as an **LLM-driven Werewolf game core**.

* **Focus on Core Game Logic**
  UI and operational concerns are intentionally separated from the game engine.

* **LLM-First Architecture**
  Dialogue, reasoning, and voting are treated as first-class LLM agent behaviors.

* **Reproducibility and Evaluability**
  Deterministic execution supports experiments, comparisons, and research workflows.

* **Extensible Role and Rule Design**
  New roles and custom rules can be added with minimal friction.

* **Integration-Oriented API Design**
  Interfaces are designed for embedding into bots, web services, and analytical systems.

---

## Intended Use Cases

* **LLM Agent Research and Evaluation**
  Comparing reasoning and dialogue behaviors across models and prompts.

* **Integration into Bots and Game Services**
  Serving as the internal engine for Discord, Slack, or similar bots.

* **Game Design Validation**
  Running large-scale simulations to test role balance and rule changes.

* **Conversation and Reasoning Log Analysis**
  Collecting structured logs for analysis of LLM behavior.

---

## Supported Elements (Initial Scope)

* Phase management (night / day / voting / execution)
* Core roles (villager, werewolf, seer, etc.)
* LLM-based and rule-based agents
* Win-condition evaluation
* Structured event output

---

## Architecture Overview

* Game execution engine layer
* Role and ability definition layer
* LLM agent abstraction layer
* Runtime and orchestration layer

---

## Installation (Planned)

```bash
pip install werewolf-llm
```

---

## Quick Start (Conceptual)

```python
from werewolf_llm import GameEngine, GameConfig

config = GameConfig(
    players=5,
    roles={"villager": 2, "werewolf": 2, "seer": 1},
    seed=42,
)

engine = GameEngine(config)
events = engine.run()

for event in events:
    print(event)
```

The returned events are intended to be interpreted, displayed, or persisted by higher-level systems.

---

## Roadmap

* Refinement of APIs for role and rule extensions (plugin-style architecture)
* Enhanced reasoning logs and perspective-based logs (player vs. spectator views)
* Human-in-the-loop input injection for mixed human/agent games
* Experimental runners for large-scale execution and benchmarking
* **Preparation for API-based deployment (e.g., FastAPI)**
  While preserving the core library design, the engine will be extended to support API-based services.
* PyPI publication and expanded documentation, including design guidelines, extension guides, and examples

---

## License

MIT License
