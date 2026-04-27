"""Tester Agent - Generates pytest unit and integration tests."""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseAgent, InsufficientCreditsError
from ._extract import _extract_files_from_response, _strip_fences
from ..db.models import (
    AgentRole, Project, Actor, UseCase, DesignDecision,
    PatternApplication, ArtifactType, Artifact
)

_SYS_PATH_HEADER = """\
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "code"))
"""


class TesterAgent(BaseAgent):

    def __init__(self, db_session: Optional[Session] = None, project_id: Optional[int] = None):
        system_prompt = """You are a senior QA engineer and Python testing specialist.
        Write comprehensive pytest suites: unit tests, integration tests, edge cases.
        Use fixtures, parametrize, and mocks appropriately.
        """
        super().__init__(
            name="TesterAgent",
            system_prompt=system_prompt,
            agent_role=AgentRole.TESTER,
            db_session=db_session,
            project_id=project_id,
        )
        if not os.getenv("UMLAGENTS_TESTERAGENT_MODEL"):
            self._model = os.getenv("UMLAGENTS_DEFAULT_MODEL", "claude-haiku-4-5-20251001")

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        project_id = context.get('project_id', self.project_id)
        if not project_id:
            raise ValueError("project_id required in context or agent initialization")

        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        if context.get('skip_existing', False):
            existing = self.db.query(Artifact).filter(
                Artifact.project_id == project_id,
                Artifact.artifact_type.in_([
                    ArtifactType.UNIT_TESTS, ArtifactType.INTEGRATION_TESTS, ArtifactType.UAT_CHECKLIST
                ])
            ).count()
            if existing > 0:
                print(f"[TesterAgent] Skipping - {existing} test artifacts already exist")
                arts = self.db.query(Artifact).filter(
                    Artifact.project_id == project_id,
                    Artifact.artifact_type.in_([
                        ArtifactType.UNIT_TESTS, ArtifactType.INTEGRATION_TESTS, ArtifactType.UAT_CHECKLIST
                    ])
                ).all()
                return {
                    'project_id': project_id,
                    'project_name': project.name,
                    'generated_tests': [
                        {'id': a.id, 'name': a.name, 'artifact_type': a.artifact_type.value, 'file_path': a.file_path}
                        for a in arts
                    ],
                }

        # Load source code
        source_artifacts = self.db.query(Artifact).filter(
            Artifact.project_id == project_id,
            Artifact.artifact_type == ArtifactType.SOURCE_CODE,
        ).all()
        source_code: Dict[str, str] = {}
        for art in source_artifacts:
            if art.file_path and os.path.exists(art.file_path):
                source_code[art.name] = Path(art.file_path).read_text(encoding="utf-8")

        use_cases = self.db.query(UseCase).filter(UseCase.project_id == project_id).all()

        print(f"[TesterAgent] Generating tests for project: {project.name}")
        print(f"[TesterAgent] Source files: {len(source_code)}, Use cases: {len(use_cases)}")

        output_dir = f"output/project_{project_id}/tests"
        os.makedirs(output_dir, exist_ok=True)

        shared_ctx = self._build_shared_context(project, source_code, use_cases)
        generated_code: Dict[str, str] = {}
        generated_artifacts = []

        steps = [
            ("conftest.py",        self._prompt_conftest),
            ("test_domain.py",     self._prompt_test_domain),
            ("test_use_cases.py",  self._prompt_test_use_cases),
            ("uat_checklist.md",   self._prompt_uat_checklist),
        ]

        for filename, prompt_fn in steps:
            print(f"[TesterAgent] Generating {filename}...")
            try:
                prompt = prompt_fn(shared_ctx, generated_code)
                response = self.call_deepseek(prompt, temperature=0.3, max_tokens=4096)
                extracted = _extract_files_from_response(response)
                content = (
                    extracted.get(filename)
                    or next(iter(extracted.values()), None)
                    or _strip_fences(response)
                )
                # Inject sys.path header into conftest so tests can find domain.py
                if filename == "conftest.py" and "sys.path.insert" not in content:
                    content = _SYS_PATH_HEADER + "\n" + content
                generated_code[filename] = content
            except InsufficientCreditsError:
                raise
            except Exception as e:
                print(f"[TesterAgent] Warning: failed to generate {filename}: {e}")
                continue

            filepath = os.path.join(output_dir, filename)
            if "test_" in filename or filename == "conftest.py":
                artifact_type = ArtifactType.UNIT_TESTS
            elif "uat" in filename or "checklist" in filename:
                artifact_type = ArtifactType.UAT_CHECKLIST
            else:
                artifact_type = ArtifactType.UNIT_TESTS

            artifact = self.save_artifact(
                filepath=filepath,
                content=content,
                artifact_type=artifact_type,
                metadata={"filename": filename, "project_name": project.name},
            )
            if artifact:
                generated_artifacts.append({
                    'id': artifact.id,
                    'name': artifact.name,
                    'artifact_type': artifact.artifact_type.value,
                    'file_path': artifact.file_path,
                })

        self.log_activity(
            action="generate_tests",
            details={
                "num_source_files": len(source_code),
                "num_use_cases": len(use_cases),
                "num_generated_files": len(generated_artifacts),
                "project_id": project_id,
            },
        )

        return {
            'project_id': project_id,
            'project_name': project.name,
            'generated_tests': generated_artifacts,
            'test_files': list(generated_code.keys()),
        }

    # ------------------------------------------------------------------
    # Context builder
    # ------------------------------------------------------------------

    def _build_shared_context(
        self,
        project: Project,
        source_code: Dict[str, str],
        use_cases: List[UseCase],
    ) -> str:
        source_text = "".join(
            f"\n### {name}\n```python\n{code}\n```\n"
            for name, code in source_code.items()
        )
        uc_text = "\n".join(
            f"UC{uc.uc_id}: {uc.title} (actor: {uc.actor.name if uc.actor else 'System'})"
            for uc in use_cases
        )
        return (
            f"Project: {project.name}\n"
            f"Domain: {project.domain}\n\n"
            f"## Use Cases\n{uc_text}\n\n"
            f"## Source Code\n{source_text}"
        )

    # ------------------------------------------------------------------
    # Per-file prompts
    # ------------------------------------------------------------------

    def _prompt_conftest(self, ctx: str, _prev: Dict[str, str]) -> str:
        return (
            f"{ctx}\n\n"
            "Generate ONLY `conftest.py` with shared pytest fixtures.\n"
            "Do NOT add sys.path manipulation — that will be added automatically.\n"
            "Import domain classes directly (e.g. `from domain import Player`).\n\n"
            "Reply with a single fenced block:\n"
            "```python\n# conftest.py\n...code...\n```"
        )

    def _prompt_test_domain(self, ctx: str, prev: Dict[str, str]) -> str:
        conftest = prev.get("conftest.py", "")
        return (
            f"{ctx}\n\n"
            "## conftest.py (already generated)\n"
            f"```python\n{conftest}\n```\n\n"
            "Generate ONLY `test_domain.py` — unit tests for every domain class.\n"
            "Use fixtures from conftest.py. Cover normal cases, edge cases, and error paths.\n\n"
            "Reply with a single fenced block:\n"
            "```python\n# test_domain.py\n...code...\n```"
        )

    def _prompt_test_use_cases(self, ctx: str, prev: Dict[str, str]) -> str:
        conftest = prev.get("conftest.py", "")
        test_domain = prev.get("test_domain.py", "")
        return (
            f"{ctx}\n\n"
            "## conftest.py\n```python\n" + conftest + "\n```\n"
            "## test_domain.py (for reference)\n```python\n" + test_domain[:800] + "\n```\n\n"
            "Generate ONLY `test_use_cases.py` — integration tests for each use case "
            "(UC1 join game, UC2 roll dice, UC3 declare winner).\n"
            "Import UseCaseController from use_cases.\n\n"
            "Reply with a single fenced block:\n"
            "```python\n# test_use_cases.py\n...code...\n```"
        )

    def _prompt_uat_checklist(self, ctx: str, prev: Dict[str, str]) -> str:
        return (
            f"Project: {ctx.splitlines()[0]}\n\n"
            "Write `uat_checklist.md` — a User Acceptance Testing checklist with one section "
            "per use case, each with 3-5 acceptance criteria as checkboxes.\n\n"
            "Reply with a single fenced block:\n"
            "```markdown\n# uat_checklist.md\n...content...\n```"
        )
