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

# Install with web UI support (optional)
pip install -e .[web]

# Or install directly (when published)
pip install umlagents
```

**Using Conda?** Create a new environment first:
```bash
conda create -n umlagents python=3.10
conda activate umlagents
pip install -e .
# For web UI support:
pip install -e .[web]
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
# If you encounter "'NoneType' object is not iterable", use:
# umlagents orchestrate 1 --agents BAAgent

# Generate UML diagrams only
umlagents architect 1 --diagram-types "domain,sequence"

# ==== Easiest: end-to-end ====
# Run pipeline + install deps + start the app in one command:
umlagents run 2 --port 8080

# Just start an existing generated app (skip pipeline):
umlagents run 1 --skip-pipeline --port 8000

# Start WebSocket UI (monitoring)
uvicorn web.app:app --host 0.0.0.0 --port 8080
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

## Running Generated Applications

After running the pipeline, generated artifacts appear in `output/project_X/`. Each project produces a runnable application with source code, tests, and deployment configs.

### Dice Game (Project 1)

```bash
# Ensure the pipeline has been run
umlagents orchestrate 1

# The generated app lives at:
ls output/project_1/code/
#   main.py       # FastAPI web service
#   domain.py     # Core domain classes
#   requirements.txt

# Install dependencies and run
cd output/project_1/code
pip install -r requirements.txt
uvicorn main:app --port 8080
```

**Verify it's running:**
```bash
curl http://localhost:8080/health
curl http://localhost:8080/metrics
curl -X POST http://localhost:8080/players -H 'Content-Type: application/json' -d '{"name":"Alice"}'
curl -X POST http://localhost:8080/sessions -H 'Content-Type: application/json' -d '{"session_id":"game1","max_players":4}'
```

#### Known Fix (Agent Coordination Bug)
If `uvicorn main:app` fails with `ImportError: cannot import name 'GameRound' from 'domain'`, the generated code has a class mismatch between `main.py` and `domain.py`. Add this class to `domain.py` right before `class GameSystem:`:

```python
class GameRound:
    """Represents a single round within a game session."""
    def __init__(self, round_number: int):
        self.round_number = round_number
        self.rolls: list = []
        self.is_tie: bool = False
    
    def add_roll(self, roll_result) -> None:
        self.rolls.append(roll_result)
    
    def determine_winner(self):
        if not self.rolls:
            return None
        max_val = max(r.value for r in self.rolls)
        winners = [r.player for r in self.rolls if r.value == max_val]
        self.is_tie = len(winners) > 1
        return max(winners, key=lambda p: p.name) if self.is_tie else winners[0]
```

Also fix `roll_value` → `value` in the `HighestRollStrategy.determine_winner()` method if it exists. This is a known agent coordination gap — agents generate code independently and may reference classes from sibling files imperfectly.

### Healthcare Appointment System (Project 2)

```bash
# Run the full pipeline
umlagents orchestrate 2 --agents ArchitectAgent,DesignAgent,DeveloperAgent,TesterAgent,DeployerAgent

# Find generated artifacts
ls output/project_2/code/          # Source code (may vary)
ls output/project_2/tests/         # Test suite
ls output/project_2/deployment/    # Docker, k8s configs

# Run tests
cd output/project_2
python -m pytest tests/ -v

# Build and run with Docker
cd output/project_2/deployment
docker compose up
```

### Key Endpoints
| Project | App URL | Description |
|---------|---------|-------------|
| Dice Game | `http://localhost:8080` | Dice rolling game REST API |
| HealthSync | `http://localhost:8080` | Healthcare appointment system (after Docker) |
| Monitoring UI | `http://localhost:8081` | WebSocket pipeline monitor (`uvicorn web.app:app --port 8081`) |

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

UMLAgents includes a real‑time monitoring interface. **Note:** The web UI requires optional dependencies.

### Installation

Option A: Install with web extras:
```bash
# Install UMLAgents with web dependencies
pip install -e .[web]
```

Option B: Install dependencies separately:
```bash
# Install UMLAgents first
pip install -e .

# Then install web dependencies
pip install "uvicorn[standard]" fastapi websockets python-multipart
```

### Starting the Server

```bash
# Start the WebSocket server
uvicorn web.app:app --host 0.0.0.0 --port 8080 --reload
```

If using Conda, ensure you're in the correct environment:
```bash
# Activate your conda environment first
conda activate umlagents

# Then install dependencies and run
pip install "uvicorn[standard]" fastapi websockets python-multipart
uvicorn web.app:app --host 0.0.0.0 --port 8080 --reload
```

Access the UI at `http://localhost:8080` for:
- Real‑time pipeline event monitoring
- YAML requirement upload and validation
- Artifact preview and download
- Audit trail exploration

**Note:** Interactive requirement elicitation is CLI‑only (`umlagents interactive`)

## Troubleshooting

### "uvicorn is not recognized" (Windows/Conda)
If you get `The term 'uvicorn' is not recognized`, you need to:
1. Activate your Conda environment: `conda activate umlagents`
2. Install UMLAgents with web extras: `pip install -e .[web]`
   Or install separately:
   ```bash
   pip install -e .
   pip install "uvicorn[standard]" fastapi websockets python-multipart
   ```

### Orchestrator Error: "'NoneType' object is not iterable"
If `umlagents orchestrate 1` fails with this error, you may have an older version of the CLI. The fix is in `umlagents/cli.py` around line 690-710.

**Workaround:** Use the `--agents` flag to specify which agents to run:
```bash
umlagents orchestrate 1 --agents BAAgent
```

**Permanent fix:** Update your `cli.py` file. Look for:
```python
# Prepare context
context = {
    'project_id': project.id,
    'start_phase': Phase[args.start_phase.upper()] if args.start_phase else None,
    'agents_to_run': args.agents.split(',') if args.agents else None,
    'halt_on_error': not args.continue_on_error
}
```

Replace with:
```python
# Prepare context
context = {
    'project_id': project.id,
    'halt_on_error': not args.continue_on_error
}
if args.start_phase:
    context['start_phase'] = Phase[args.start_phase.upper()]
if args.agents:
    context['agents_to_run'] = args.agents.split(',')
```

### Import Errors
If Python can't find `umlagents` modules, make sure you installed in development mode:
```bash
pip install -e .
```

### Web UI Import Errors
If you get `ModuleNotFoundError: No module named 'umlagents.web'`, note that the web module is at the project root, not inside the `umlagents` package. Use `web.app` instead of `umlagents.web.app`:
```bash
# Correct import for testing
python -c "import uvicorn; import fastapi; import web.app; print('✅ All imports work!')"

# Correct uvicorn command
uvicorn web.app:app --host 0.0.0.0 --port 8080 --reload
```

### Interactive mode fails or questions loop quickly (CLI)
If `umlagents interactive` shows questions quickly without waiting for answers, or fails with an error about stdin:

**Cause:** Interactive mode requires a real terminal with standard input. It won't work when run through automation tools, wrappers, or non‑interactive shells.

**Solutions:**
1. **Run in a proper terminal:** Use Windows Command Prompt, PowerShell, Git Bash, or your system's terminal (not through OpenClaw TUI or other wrappers).
2. **Use YAML files instead:** Create a requirements YAML file and load it:
   ```bash
   umlagents load-yaml examples/dice-game-example.yaml
   ```
3. **Use command‑line arguments:** Pre‑populate some answers:
   ```bash
   umlagents interactive --project-name "My Project" --domain "Finance"
   ```

### Interactive BA questions loop quickly (web UI)
If you click "Start Interactive Session" in the web UI and questions appear quickly without waiting for answers, this is because interactive requirement elicitation is not implemented in the web UI.

**Solution:** Use the CLI for interactive requirement elicitation:
```bash
umlagents interactive
```

Or upload a YAML requirements file via the web UI's upload feature.

The web UI is designed for **monitoring pipeline execution**, not interactive requirement elicitation.

## License

MIT License - see [LICENSE](LICENSE) file.

## Acknowledgments

- Based on Craig Larman's Object‑Oriented Analysis and Design methodology
- Inspired by modern AI‑assisted development workflows
- Built with SQLAlchemy, FastAPI, and DeepSeek AI