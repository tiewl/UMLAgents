"""
Developer Agent - Generates Python source code from design.

Responsibilities (Larman's Construction phase):
- Translate design decisions and pattern applications into executable code
- Implement use case scenarios as methods and functions
- Create class hierarchies based on applied patterns
- Ensure code follows Python best practices and type hints
- Generate runnable application with entry point
"""
import os
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseAgent, InsufficientCreditsError
from ._extract import _extract_files_from_response, _strip_fences
from ..db.models import (
    AgentRole, Project, Actor, UseCase, DesignDecision,
    PatternApplication, PatternCategory, ArtifactType, Artifact
)


class DeveloperAgent(BaseAgent):
    """
    Developer agent for code generation.

    Key responsibilities:
    1. Generate Python classes based on actors and use cases
    2. Implement pattern applications (Factory, Strategy, Observer, etc.)
    3. Create executable application with main entry point
    4. Follow Python best practices (type hints, docstrings, error handling)
    5. Save source code artifacts with content hashing
    """

    def __init__(self, db_session: Optional[Session] = None, project_id: Optional[int] = None):
        system_prompt = """You are a senior Python developer building production-quality
        FastAPI web applications following Craig Larman's OOA/OOD methodology.

        Every project you generate is a deployable REST API, not a CLI demo:
        - FastAPI app with one endpoint per use case
        - SQLAlchemy ORM models backed by SQLite (dev) or PostgreSQL (prod)
        - Pydantic schemas for all request/response bodies
        - Auto-generated Swagger UI at /docs
        - Each endpoint docstring references its use case ID for traceability

        You write type-hinted, clean, production-ready Python code.
        """

        super().__init__(
            name="DeveloperAgent",
            system_prompt=system_prompt,
            agent_role=AgentRole.DEVELOPER,
            db_session=db_session,
            project_id=project_id
        )

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate Python source code from project design.

        Args:
            context: Must contain 'project_id' (int)

        Returns:
            Dict with generated code files and artifact records
        """
        project_id = context.get('project_id', self.project_id)
        if not project_id:
            raise ValueError("project_id required in context or agent initialization")

        # Load project data
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # Skip if source code artifacts already exist and skip_existing is True
        if context.get('skip_existing', False):
            existing_code = self.db.query(Artifact).filter(
                Artifact.project_id == project_id,
                Artifact.artifact_type == ArtifactType.SOURCE_CODE
            ).count()
            if existing_code > 0:
                print(f"[DeveloperAgent] Skipping - {existing_code} source code artifacts already exist")
                # Return existing artifacts
                existing_artifacts = self.db.query(Artifact).filter(
                    Artifact.project_id == project_id,
                    Artifact.artifact_type.in_([ArtifactType.SOURCE_CODE, ArtifactType.UNIT_TESTS])
                ).all()
                return {
                    'project_id': project_id,
                    'project_name': project.name,
                    'generated_files': [
                        {
                            'id': art.id,
                            'name': art.name,
                            'artifact_type': art.artifact_type.value,
                            'file_path': art.file_path
                        }
                        for art in existing_artifacts
                    ]
                }

        # Gather design context
        use_cases = self.db.query(UseCase).filter(UseCase.project_id == project_id).all()
        actors = self.db.query(Actor).filter(Actor.project_id == project_id).all()
        design_decisions = self.db.query(DesignDecision).filter(
            DesignDecision.project_id == project_id
        ).all()
        pattern_applications = self.db.query(PatternApplication).filter(
            PatternApplication.project_id == project_id
        ).all()

        print(f"[DeveloperAgent] Generating code for project: {project.name}")
        print(f"[DeveloperAgent] Use cases: {len(use_cases)}, Actors: {len(actors)}")

        output_dir = f"output/project_{project_id}/code"
        os.makedirs(output_dir, exist_ok=True)

        # Build shared context block reused across all calls
        shared_ctx = self._build_shared_context(
            project, actors, use_cases, design_decisions, pattern_applications
        )

        generated_artifacts = []
        generated_code: Dict[str, str] = {}  # accumulates code for later calls

        # ── Each file gets its own focused API call ───────────────────────────
        steps = [
            ("database.py",     self._prompt_database),
            ("models.py",       self._prompt_models),
            ("schemas.py",      self._prompt_schemas),
            ("use_cases.py",    self._prompt_use_cases),
            ("main.py",         self._prompt_main),
            ("requirements.txt",self._prompt_requirements),
        ]

        for filename, prompt_fn in steps:
            print(f"[DeveloperAgent] Generating {filename}...")
            try:
                prompt = prompt_fn(shared_ctx, generated_code)
                limit = 16384 if filename in ("main.py", "use_cases.py") else 8192
                content = None
                for attempt in range(1, 3):
                    response = self.call_deepseek(prompt, temperature=0.3, max_tokens=limit)
                    extracted = self._extract_code_files(response)
                    candidate = (
                        extracted.get(filename)
                        or next(iter(extracted.values()), None)
                        or _strip_fences(response)
                    )
                    if filename.endswith(".py"):
                        try:
                            compile(candidate, filename, "exec")
                            content = candidate
                            break
                        except SyntaxError as se:
                            print(f"[DeveloperAgent] {filename} attempt {attempt} has syntax error ({se}), retrying...")
                            prompt = (
                                f"The previous response for `{filename}` was truncated and has a SyntaxError: {se}\n"
                                f"Here is what was generated so far (truncated):\n```python\n{candidate[-800:]}\n```\n\n"
                                f"Please regenerate the COMPLETE `{filename}` from scratch. "
                                f"Keep it concise — avoid long docstrings or comments.\n\n"
                                + prompt_fn(shared_ctx, generated_code)
                            )
                    else:
                        content = candidate
                        break
                if content is None:
                    content = candidate  # use last attempt even if broken
                    print(f"[DeveloperAgent] Warning: {filename} still has syntax errors after retries")
                generated_code[filename] = content
            except InsufficientCreditsError:
                raise
            except Exception as e:
                print(f"[DeveloperAgent] Warning: failed to generate {filename}: {e}")
                continue

            # Save to disk
            filepath = os.path.join(output_dir, filename)
            artifact_type = ArtifactType.SOURCE_CODE
            artifact = self.save_artifact(
                filepath=filepath,
                content=content,
                artifact_type=artifact_type,
                metadata={"filename": filename, "project_name": project.name}
            )
            if artifact:
                generated_artifacts.append({
                    'id': artifact.id,
                    'name': artifact.name,
                    'artifact_type': artifact.artifact_type.value,
                    'file_path': artifact.file_path
                })

        self.log_activity(
            action="generate_source_code",
            details={
                "num_use_cases": len(use_cases),
                "num_generated_files": len(generated_artifacts),
                "project_id": project_id
            }
        )

        return {
            'project_id': project_id,
            'project_name': project.name,
            'generated_files': generated_artifacts,
            'code_files': list(generated_code.keys())
        }

    def _build_shared_context(
        self,
        project: Project,
        actors: List[Actor],
        use_cases: List[UseCase],
        design_decisions: List[DesignDecision],
        pattern_applications: List[PatternApplication],
    ) -> str:
        """Build the project context block shared by all per-file prompts."""
        actors_text = "\n".join(f"- {a.name}: {a.description}" for a in actors)

        uc_lines = []
        for uc in use_cases:
            uc_lines.append(f"UC{uc.uc_id}: {uc.title} (actor: {uc.actor.name if uc.actor else 'System'})")
            if uc.success_scenario:
                for i, step in enumerate(uc.success_scenario, 1):
                    uc_lines.append(f"  {i}. {step}")
        use_cases_text = "\n".join(uc_lines)

        patterns_text = "\n".join(
            f"- {pa.pattern_name} ({pa.pattern_category.value}): {pa.description}"
            for pa in pattern_applications
        )

        # Load diagram artifacts
        diagrams_text = ""
        diagram_artifacts = self.db.query(Artifact).filter(
            Artifact.project_id == project.id,
            Artifact.artifact_type.in_([
                ArtifactType.DOMAIN_DIAGRAM,
                ArtifactType.CLASS_DIAGRAM,
                ArtifactType.SEQUENCE_DIAGRAM,
            ])
        ).all()
        for art in diagram_artifacts:
            if art.file_path:
                try:
                    content = Path(art.file_path).read_text(encoding="utf-8", errors="ignore")
                    diagrams_text += f"\n### {art.name}\n```\n{content}\n```\n"
                except Exception:
                    pass

        return (
            f"Project: {project.name}\n"
            f"Domain: {project.domain}\n"
            f"Description: {project.description}\n\n"
            f"## Actors\n{actors_text}\n\n"
            f"## Use Cases\n{use_cases_text}\n\n"
            f"## Applied Patterns\n{patterns_text}\n"
            f"{diagrams_text}"
        )

    def _prompt_database(self, ctx: str, _prev: Dict[str, str]) -> str:
        return (
            f"{ctx}\n\n"
            "Generate ONLY `database.py` — SQLAlchemy database setup.\n\n"
            "Requirements:\n"
            "- Read DATABASE_URL from env (default: `sqlite:///./app.db`)\n"
            "- Works with both SQLite (dev) and PostgreSQL (prod/Docker)\n"
            "- Export: `engine`, `SessionLocal`, `Base`, `get_db` (FastAPI dependency)\n"
            "- `get_db` must be a generator function usable with `Depends(get_db)`\n\n"
            "Reply with a single fenced code block:\n"
            "```python\n# database.py\n...code...\n```"
        )

    def _prompt_models(self, ctx: str, prev: Dict[str, str]) -> str:
        db_code = prev.get("database.py", "")
        return (
            f"{ctx}\n\n"
            "## database.py\n```python\n" + db_code + "\n```\n\n"
            "Generate ONLY `models.py` — SQLAlchemy ORM models.\n\n"
            "Requirements:\n"
            "- Import Base from database.py\n"
            "- Create one ORM model per key domain entity from the use cases above\n"
            "- Every model needs: `id` (Integer primary key), `created_at` (DateTime), relevant fields\n"
            "- Use appropriate column types (String, Integer, Boolean, DateTime, Enum, ForeignKey)\n"
            "- Add `__tablename__` to every model\n"
            "- Add relationships where entities are related\n"
            "- Each class docstring must reference which use cases use it (e.g. `# UC1, UC2`)\n\n"
            "Reply with a single fenced code block:\n"
            "```python\n# models.py\n...code...\n```"
        )

    def _prompt_schemas(self, ctx: str, prev: Dict[str, str]) -> str:
        models_code = prev.get("models.py", "")
        return (
            f"{ctx}\n\n"
            "## models.py\n```python\n" + models_code + "\n```\n\n"
            "Generate ONLY `schemas.py` — Pydantic v2 request/response schemas.\n\n"
            "Requirements:\n"
            "- One `*Create` schema (request body) and one `*Response` schema (response) per ORM model\n"
            "- Response schemas must include `id` and `created_at`\n"
            "- Use `model_config = ConfigDict(from_attributes=True)` on response schemas\n"
            "- Add Field descriptions that reference the use case (e.g. `Field(..., description='UC1: ...')`)\n\n"
            "Reply with a single fenced code block:\n"
            "```python\n# schemas.py\n...code...\n```"
        )

    def _prompt_use_cases(self, ctx: str, prev: Dict[str, str]) -> str:
        models_code = prev.get("models.py", "")
        schemas_code = prev.get("schemas.py", "")
        return (
            f"{ctx}\n\n"
            "## models.py\n```python\n" + models_code + "\n```\n\n"
            "## schemas.py\n```python\n" + schemas_code + "\n```\n\n"
            "Generate ONLY `use_cases.py` — business logic service layer.\n\n"
            "Requirements:\n"
            "- One function per use case (e.g. `def schedule_appointment(db: Session, data: AppointmentCreate)`)\n"
            "- Each function takes a SQLAlchemy Session + a Pydantic schema as input\n"
            "- Implement the main success scenario steps as inline comments (e.g. `# Step 3: validate slot`)\n"
            "- Return ORM model instances\n"
            "- Raise `HTTPException` (imported from fastapi) for error/extension scenarios\n"
            "- Each function docstring references its use case ID (e.g. `Implements UC1`)\n\n"
            "Reply with a single fenced code block:\n"
            "```python\n# use_cases.py\n...code...\n```"
        )

    def _prompt_main(self, ctx: str, prev: Dict[str, str]) -> str:
        uc_code = prev.get("use_cases.py", "")
        schemas_code = prev.get("schemas.py", "")
        return (
            f"{ctx}\n\n"
            "## use_cases.py\n```python\n" + uc_code + "\n```\n\n"
            "## schemas.py\n```python\n" + schemas_code + "\n```\n\n"
            "Generate ONLY `main.py` — the FastAPI application.\n\n"
            "Requirements:\n"
            "- Create `app = FastAPI(title=..., description=..., version='1.0.0')`\n"
            "- Call `models.Base.metadata.create_all(bind=engine)` on startup\n"
            "- One router/endpoint per use case from the context above\n"
            "- Use correct HTTP methods: POST to create, GET to retrieve, DELETE to cancel/remove\n"
            "- Each endpoint must: use `Depends(get_db)`, call the matching use_cases function, "
            "include a docstring with the use case ID and title (e.g. `UC1: Schedule Appointment`)\n"
            "- Add a `GET /health` endpoint returning `{'status': 'ok'}`\n"
            "- App runs with: `uvicorn main:app --host 0.0.0.0 --port 8080` when executed directly\n\n"
            "Reply with a single fenced code block:\n"
            "```python\n# main.py\n...code...\n```"
        )

    def _prompt_requirements(self, ctx: str, prev: Dict[str, str]) -> str:
        return (
            "Generate `requirements.txt` for a FastAPI application that uses:\n"
            "- FastAPI + uvicorn (ASGI server)\n"
            "- SQLAlchemy (ORM)\n"
            "- Pydantic v2\n"
            "- python-dotenv (env config)\n"
            "- psycopg2-binary (PostgreSQL driver, for Docker)\n\n"
            "Pin to specific stable versions. Reply with a single fenced block:\n"
            "```text\n# requirements.txt\n...packages...\n```"
        )

    def _extract_code_files(self, text: str) -> Dict[str, str]:
        """Extract named code/text blocks from an LLM response."""
        return _extract_files_from_response(text)