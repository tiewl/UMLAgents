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
│  BA Agent → Architect → Design → Dev → Test → Deploy│
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
    PlantUML diagrams  Production code  Deployment config
    (.puml)           (Python)          (Docker, k8s)
```

## Features

- **6 Role‑Playing Agents**: BA, Architect, Design, Developer, Tester, Deployer
- **Larman Methodology**: INCEPTION → ELABORATION → CONSTRUCTION → TRANSITION
- **SQLite Audit Trail**: Complete traceability from requirements to deployment
- **YAML Specification**: Structured use case definitions
- **Interactive Elicitation**: AI‑guided requirement gathering
- **WebSocket UI**: Real‑time pipeline monitoring and control
- **Production‑Ready**: Validation, error handling, structured logging

## Quick Start

### Installation

```bash
# Install from source (development)
git clone <repository>
cd umlagents
pip install -e .

# Or install directly (when published)
pip install umlagents
```

### Configuration

1. Get a DeepSeek API key from [platform.deepseek.com](https://platform.deepseek.com/)
2. Create `.env` file:
   ```bash
   DEEPSEEK_API_KEY=your_key_here
   DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
   ```

### Basic Usage

```bash
# Validate a YAML specification
umlagents validate examples/dice-game-example.yaml

# Load YAML into database
umlagents load-yaml examples/dice-game-example.yaml

# List projects
umlagents list

# Run full pipeline on project ID 1
umlagents orchestrate 1

# Generate UML diagrams only
umlagents architect 1 --diagram-types "domain,sequence"

# Start WebSocket UI (monitoring)
uvicorn umlagents.web.app:app --host 0.0.0.0 --port 8080
```

## Examples

### Dice Game (Gaming Domain)
- **Location**: `examples/dice-game-example.yaml`
- **Description**: Simple dice‑rolling game for 2‑4 players
- **Actors**: Player, GameSystem
- **Use Cases**: Join Game, Roll Dice, Declare Winner

### Healthcare Appointment System (Healthcare Domain)
- **Location**: `examples/healthcare-appointment.yaml`
- **Description**: HIPAA‑compliant appointment scheduling for medical clinics
- **Actors**: Patient, Receptionist, Doctor, BillingSystem, EMRSystem
- **Use Cases**: Schedule Appointment, Cancel Appointment, View Doctor Schedule, Generate Billing Invoice, Sync with EMR

## Project Structure

```
umlagents/
├── umlagents/              # Core package
│   ├── agents/             # 6 role‑playing agents
│   ├── db/                 # SQLite models and audit trail
│   ├── utils/              # Validation, logging utilities
│   └── web/                # WebSocket UI (FastAPI)
├── examples/               # YAML specifications
├── schema/                 # YAML schema definition
├── output/                 # Generated artifacts by project ID
├── cli.py                  # Command‑line interface
├── pyproject.toml          # Package configuration
└── README.md               # This file
```

## Development

### Running Tests
```bash
# Run validation tests
python test_validation.py

# Run CLI tests
python test_cli_validation.py
```

### Adding New Features
1. Follow existing agent patterns in `umlagents/agents/`
2. Update database models in `umlagents/db/models.py`
3. Add CLI command in `cli.py`
4. Update documentation

## WebSocket UI

UMLAgents includes a real‑time monitoring interface:

```bash
# Start the WebSocket server
uvicorn umlagents.web.app:app --host 0.0.0.0 --port 8080 --reload
```

Access the UI at `http://localhost:8080` for:
- Real‑time pipeline event monitoring
- Interactive requirement elicitation
- Artifact preview and download
- Audit trail exploration

## License

MIT License - see [LICENSE](LICENSE) file.

## Acknowledgments

- Based on Craig Larman's Object‑Oriented Analysis and Design methodology
- Inspired by modern AI‑assisted development workflows
- Built with SQLAlchemy, FastAPI, and DeepSeek AI