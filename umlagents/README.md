# UMLAgents

**Automated OOA/OOD pipeline using role‑playing AI agents**

UMLAgents transforms structured use case descriptions into fully implemented applications with regulatory‑grade audit trails. Each agent simulates a distinct software engineering role, collaborating to bridge the gap between structured design and rapid prototyping.

## Vision

> "From conversation to compliant code"

Enable non‑technical creators to test ideas without hiring developers, through guided AI‑assisted requirement elicitation that produces production‑ready applications with full regulatory traceability.

## Core Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Creator                           │
│  (Conversation with AI Requirement Consultant)       │
└─────────────────────────┬───────────────────────────┘
                          │ YAML use cases
                          ▼
┌─────────────────────────────────────────────────────┐
│                 UMLAgents Pipeline                   │
│                                                     │
│  BA Agent → Architect → Design → Dev → Test         │
│  (validates)  (diagrams)  (patterns) (code) (tests) │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │           SQLite Audit Trail                │    │
│  │  (requirements→design→code→tests trace)     │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────┬───────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    PlantUML diagrams  Production code  UAT checklist
    (.puml)           (Python/TS)       (.md)
```

## Quick Start (Week 1 MVP)

UMLAgents now has a working BA Agent with SQLite audit trail and CLI.

### 1. Setup Environment

```bash
# Navigate to project
cd /home/picoclaw/.openclaw/workspace/umlagents

# Activate virtual environment
source venv/bin/activate

# Configure DeepSeek API key (required for full pipeline)
# Edit .env file with your key from https://platform.deepseek.com/
# For YAML-only testing, any non-dummy value works
```

### 2. CLI Commands

```bash
# Validate YAML file against schema
python cli.py validate examples/dice-game-example.yaml

# Load YAML into database with audit trail
python cli.py load-yaml examples/dice-game-example.yaml

# List projects in database
python cli.py list

# Export project from database to YAML
python cli.py export 1 --output exported.yaml

# Interactive requirement elicitation (Larman-style questions)
python cli.py interactive --project-name "My Project" --domain "Finance"
```

### 3. Test Suite

```bash
# Run Week 1 tests
python test_week1.py
```

## Agent Roles

| Agent | Responsibility | Output |
|-------|----------------|--------|
| **BA Agent** | Interactive requirement elicitation, validates use cases, extracts domain vocabulary | YAML use case specification |
| **Architect Agent** | Produces domain & sequence diagrams (PlantUML) | `.puml` files |
| **Design Agent** | Generates class diagrams with GoF patterns (low coupling/high cohesion) | Class diagrams, design decisions |
| **Dev Agent** | Writes production‑ready code (Python/TypeScript) | Application source code |
| **Test Agent** | Creates integration & UAT scripts | Test suites, UAT checklist |

## YAML Schema

See `schema/umlagents-schema-v0.1.yaml` for the structured input format.

## Design Principles

1. **CLI‑first** – Enables ecosystem growth (Miro, Jira, GitHub, VS Code integrations)
2. **Pi‑compatible** – SQLite audit trail, single‑container deployment (ARM64 friendly)
3. **Regulatory‑by‑design** – Full traceability matrix (requirements→design→code→tests)
4. **Specialized agents** – 5 distinct roles collaborating > monolithic AI
5. **Interactive elicitation** – Conversation‑first, not UML‑expertise‑required

## Current Status

**Week 1 COMPLETE** ✅
- [x] **YAML schema** (`schema/umlagents-schema-v0.1.yaml`) – Larman‑aligned use case format
- [x] **SQLite audit trail** (`umlagents/db/models.py`) – Full traceability with GRASP/GoF pattern tracking
- [x] **Base agent** (`umlagents/agents/base.py`) – DeepSeek API + audit logging (dice‑game‑agents compatible)
- [x] **BA Agent** (`umlagents/agents/ba_agent.py`) – YAML load + interactive modes, Larman‑style questioning
- [x] **CLI interface** (`cli.py`) – Validate, load‑yaml, interactive, export, list commands
- [x] **Test suite** (`test_week1.py`) – All tests passing
- [x] **Example** (`examples/dice-game-example.yaml`) – Dice game specification

**Week 2‑3 (Next)**
- [ ] **Architect Agent** – PlantUML diagram generation from use cases
- [ ] **Design Agent** – GRASP/GoF pattern application with rationale
- [ ] **Orchestrator** – Agent pipeline with SQLite audit integration
- [ ] **Integration** – Compatibility layer for dice‑game‑agents

**Hybrid Approach (Option C)** – Supports both YAML schema and natural language prompt modes

## License

Open source / research (TBD)