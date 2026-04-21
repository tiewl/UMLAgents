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
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseAgent
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
        system_prompt = """You are a senior Python developer following Craig Larman's
        Object-Oriented Analysis and Design methodology. Your expertise includes:

        1. Translating UML designs and pattern applications into clean Python code
        2. Implementing GRASP patterns (Creator, Expert, Controller, etc.) in code
        3. Implementing GoF patterns (Factory, Strategy, Observer, etc.) in Python
        4. Writing type‑hinted, well‑documented, and testable code
        5. Creating runnable applications with proper entry points

        You think in terms of maintainability, readability, and adherence to the design.
        When generating code, you explain key decisions in comments.
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
        print(f"[DeveloperAgent] Design decisions: {len(design_decisions)}")
        print(f"[DeveloperAgent] Applied patterns: {len(pattern_applications)}")

        # Build comprehensive prompt
        prompt = self._build_generation_prompt(
            project, actors, use_cases, design_decisions, pattern_applications
        )

        # Call DeepSeek API
        response = self.call_deepseek(prompt)

        # Extract code files from response
        code_files = self._extract_code_files(response)

        # Save files and create artifacts
        generated_artifacts = []
        output_dir = f"output/project_{project_id}/code"
        os.makedirs(output_dir, exist_ok=True)

        for filename, content in code_files.items():
            filepath = os.path.join(output_dir, filename)
            
            # Determine artifact type based on filename
            if filename.startswith("test_"):
                artifact_type = ArtifactType.UNIT_TESTS
            else:
                artifact_type = ArtifactType.SOURCE_CODE
            
            artifact = self.save_artifact(
                filepath=filepath,
                content=content,
                artifact_type=artifact_type,
                metadata={
                    "filename": filename,
                    "project_name": project.name,
                    "use_cases_count": len(use_cases)
                }
            )
            
            if artifact:
                generated_artifacts.append({
                    'id': artifact.id,
                    'name': artifact.name,
                    'artifact_type': artifact.artifact_type.value,
                    'file_path': artifact.file_path
                })

        # Log completion
        self.log_activity(
            action="generate_source_code",
            details={
                "num_use_cases": len(use_cases),
                "num_patterns": len(pattern_applications),
                "num_generated_files": len(code_files),
                "project_id": project_id
            }
        )

        return {
            'project_id': project_id,
            'project_name': project.name,
            'generated_files': generated_artifacts,
            'code_files': list(code_files.keys())
        }

    def _build_generation_prompt(
        self,
        project: Project,
        actors: List[Actor],
        use_cases: List[UseCase],
        design_decisions: List[DesignDecision],
        pattern_applications: List[PatternApplication]
    ) -> str:
        """Build comprehensive prompt for code generation."""
        
        # Format actors
        actors_text = "\n".join([
            f"- {a.name}: {a.description} (role: {a.role})"
            for a in actors
        ])
        
        # Format use cases
        use_cases_text = ""
        for uc in use_cases:
            use_cases_text += f"\n### UC{uc.uc_id}: {uc.title}\n"
            use_cases_text += f"**Actor**: {uc.actor.name if uc.actor else 'System'}\n"
            use_cases_text += f"**Priority**: {uc.priority}/3\n"
            if uc.pre_conditions:
                use_cases_text += f"**Pre‑conditions**:\n" + "\n".join(f"  - {c}" for c in uc.pre_conditions) + "\n"
            if uc.success_scenario:
                use_cases_text += f"**Success scenario**:\n" + "\n".join(f"  {i+1}. {step}" for i, step in enumerate(uc.success_scenario)) + "\n"
            if uc.extension_scenarios:
                use_cases_text += f"**Extension scenarios**:\n" + "\n".join(f"  - {e}" for e in uc.extension_scenarios) + "\n"
            if uc.post_conditions:
                use_cases_text += f"**Post‑conditions**:\n" + "\n".join(f"  - {c}" for c in uc.post_conditions) + "\n"
        
        # Format design decisions
        decisions_text = ""
        if design_decisions:
            decisions_text = "\n## Design Decisions\n"
            for dd in design_decisions:
                decisions_text += f"\n### Decision for UC{dd.use_case.uc_id if dd.use_case else '?'}: {dd.title}\n"
                decisions_text += f"**Rationale**: {dd.rationale}\n"
                decisions_text += f"**Alternatives considered**: {dd.alternatives_considered}\n"
        
        # Format applied patterns
        patterns_text = ""
        if pattern_applications:
            patterns_text = "\n## Applied Design Patterns\n"
            for pa in pattern_applications:
                patterns_text += f"- **{pa.pattern_name}** ({pa.pattern_category.value}): {pa.description}\n"
        
        prompt = f"""
You are tasked with implementing a Python application for the following project:

# Project: {project.name}
**Domain**: {project.domain}
**Description**: {project.description}

## Actors
{actors_text}

## Use Cases
{use_cases_text}
{decisions_text}
{patterns_text}

# Implementation Requirements

Generate a complete, runnable Python application that:

1. **Implements all use cases** as methods/functions
2. **Embodies the applied design patterns** in the code structure
3. **Follows Python best practices**:
   - Type hints for all functions and methods
   - Comprehensive docstrings (Google style)
   - PEP 8 formatting
   - Proper error handling and validation
4. **Creates a modular structure** with separate files for:
   - Domain classes (based on actors and use cases)
   - Main application logic
   - Entry point (main.py)
5. **Includes a command‑line interface** for interacting with the system

# Output Format

Provide each file in a separate code block with the filename as a comment on the first line:

```python
# filename.py
# Brief description
... code ...
```

# Required Files

Please generate at least these files:

1. **domain.py** – Core domain classes (Actor‑based)
2. **use_cases.py** – Use case implementations
3. **main.py** – Entry point with CLI
4. **requirements.txt** – Python dependencies (if any)

You may add additional files as needed (e.g., `services.py`, `exceptions.py`).

# Important

- The code must be **runnable** (python main.py should start the application)
- Include example usage in `main.py`
- Use the applied patterns appropriately (e.g., Factory pattern for object creation)
- Keep the code clean, testable, and well‑documented
"""

        return prompt

    def _extract_code_files(self, text: str) -> Dict[str, str]:
        """
        Extract named Python code blocks from the response.
        
        Looks for patterns like:
        ```python
        # filename.py
        ...code...
        ```
        """
        files = {}
        
        # Pattern: ```python followed by # filename.py
        pattern = r"```python\s*\n#\s*(\w+\.py)\s*\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        
        for filename, code in matches:
            files[filename] = f"# {filename}\n{code.strip()}\n"
        
        # Fallback: extract any python blocks and infer filenames
        if not files:
            pattern = r"```python\s*\n(.*?)```"
            matches = re.findall(pattern, text, re.DOTALL)
            for i, code in enumerate(matches):
                # Try to detect filename from first comment line
                first_line = code.strip().split("\n")[0]
                if first_line.startswith("#") and ".py" in first_line:
                    filename = first_line.replace("#", "").strip()
                    files[filename] = code.strip() + "\n"
                else:
                    # Assign generic names
                    if "test" in code.lower():
                        files[f"test_module_{i}.py"] = code.strip() + "\n"
                    else:
                        files[f"module_{i}.py"] = code.strip() + "\n"
        
        return files