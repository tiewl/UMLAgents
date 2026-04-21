"""
Tester Agent - Generates unit and integration tests.

Responsibilities (Larman's Construction phase):
- Create comprehensive test suites for generated code
- Ensure test coverage of use cases and edge cases
- Generate both unit tests (pytest) and integration tests
- Create UAT checklists for business validation
"""
import os
import re
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseAgent
from ..db.models import (
    AgentRole, Project, Actor, UseCase, DesignDecision, 
    PatternApplication, ArtifactType, Artifact
)


class TesterAgent(BaseAgent):
    """
    Tester agent for test generation.

    Key responsibilities:
    1. Generate unit tests for generated source code
    2. Create integration tests for use case scenarios
    3. Produce UAT checklists based on success criteria
    4. Ensure test coverage of applied patterns
    5. Save test artifacts with content hashing
    """

    def __init__(self, db_session: Optional[Session] = None, project_id: Optional[int] = None):
        system_prompt = """You are a senior QA engineer and Python testing specialist.
        Your expertise includes:

        1. Writing comprehensive pytest test suites for Python applications
        2. Testing GRASP and GoF pattern implementations
        3. Creating integration tests for use case scenarios
        4. Generating UAT checklists with clear acceptance criteria
        5. Ensuring high code coverage and edge‑case testing

        You think in terms of testability, reliability, and validation against requirements.
        """

        super().__init__(
            name="TesterAgent",
            system_prompt=system_prompt,
            agent_role=AgentRole.TESTER,
            db_session=db_session,
            project_id=project_id
        )

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate tests for project code.

        Args:
            context: Must contain 'project_id' (int)

        Returns:
            Dict with generated test files and artifact records
        """
        project_id = context.get('project_id', self.project_id)
        if not project_id:
            raise ValueError("project_id required in context or agent initialization")

        # Load project data
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # Skip if test artifacts already exist and skip_existing is True
        if context.get('skip_existing', False):
            existing_tests = self.db.query(Artifact).filter(
                Artifact.project_id == project_id,
                Artifact.artifact_type.in_([ArtifactType.UNIT_TESTS, ArtifactType.INTEGRATION_TESTS, ArtifactType.UAT_CHECKLIST])
            ).count()
            if existing_tests > 0:
                print(f"[TesterAgent] Skipping - {existing_tests} test artifacts already exist")
                # Return existing artifacts
                existing_artifacts = self.db.query(Artifact).filter(
                    Artifact.project_id == project_id,
                    Artifact.artifact_type.in_([ArtifactType.UNIT_TESTS, ArtifactType.INTEGRATION_TESTS, ArtifactType.UAT_CHECKLIST])
                ).all()
                return {
                    'project_id': project_id,
                    'project_name': project.name,
                    'generated_tests': [
                        {
                            'id': art.id,
                            'name': art.name,
                            'artifact_type': art.artifact_type.value,
                            'file_path': art.file_path
                        }
                        for art in existing_artifacts
                    ]
                }

        # Gather source code artifacts to test
        source_artifacts = self.db.query(Artifact).filter(
            Artifact.project_id == project_id,
            Artifact.artifact_type == ArtifactType.SOURCE_CODE
        ).all()
        
        # Read source code files
        source_code = {}
        for artifact in source_artifacts:
            if artifact.file_path and os.path.exists(artifact.file_path):
                with open(artifact.file_path, 'r', encoding='utf-8') as f:
                    source_code[artifact.name] = f.read()
        
        # If no source code found, generate tests based on design context
        if not source_code:
            print("[TesterAgent] No source code artifacts found, generating tests from design context")
            return self._generate_tests_from_design(project_id, context)
        
        # Gather design context for test scenarios
        use_cases = self.db.query(UseCase).filter(UseCase.project_id == project_id).all()
        
        print(f"[TesterAgent] Generating tests for project: {project.name}")
        print(f"[TesterAgent] Source files: {len(source_code)}, Use cases: {len(use_cases)}")

        # Build comprehensive prompt
        prompt = self._build_test_prompt(project, source_code, use_cases)

        # Call DeepSeek API
        response = self.call_deepseek(prompt)

        # Extract test files from response
        test_files = self._extract_code_files(response)

        # Save files and create artifacts
        generated_artifacts = []
        output_dir = f"output/project_{project_id}/tests"
        os.makedirs(output_dir, exist_ok=True)

        for filename, content in test_files.items():
            filepath = os.path.join(output_dir, filename)
            
            # Determine artifact type based on filename
            if filename.startswith("test_") or "test" in filename.lower():
                artifact_type = ArtifactType.UNIT_TESTS
            elif "integration" in filename.lower():
                artifact_type = ArtifactType.INTEGRATION_TESTS
            elif "uat" in filename.lower() or "checklist" in filename.lower():
                artifact_type = ArtifactType.UAT_CHECKLIST
            else:
                artifact_type = ArtifactType.UNIT_TESTS
            
            artifact = self.save_artifact(
                filepath=filepath,
                content=content,
                artifact_type=artifact_type,
                metadata={
                    "filename": filename,
                    "project_name": project.name,
                    "source_files_count": len(source_code)
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
            action="generate_tests",
            details={
                "num_source_files": len(source_code),
                "num_use_cases": len(use_cases),
                "num_generated_tests": len(test_files),
                "project_id": project_id
            }
        )

        return {
            'project_id': project_id,
            'project_name': project.name,
            'generated_tests': generated_artifacts,
            'test_files': list(test_files.keys())
        }

    def _generate_tests_from_design(self, project_id: int, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate tests based on design context when no source code exists."""
        project = self.db.query(Project).filter(Project.id == project_id).first()
        use_cases = self.db.query(UseCase).filter(UseCase.project_id == project_id).all()
        actors = self.db.query(Actor).filter(Actor.project_id == project_id).all()
        
        prompt = f"""
Generate comprehensive pytest unit tests for a Python application based on the following design:

# Project: {project.name}
**Domain**: {project.domain}

## Actors
{', '.join([a.name for a in actors])}

## Use Cases
{chr(10).join([f'- UC{uc.uc_id}: {uc.title}' for uc in use_cases])}

## Test Requirements

Create pytest test files that:

1. **Test each use case scenario** (success, extension, error cases)
2. **Mock dependencies** where appropriate
3. **Include fixtures** for common test setup
4. **Use parametrized tests** for boundary conditions
5. **Follow pytest best practices** (descriptive test names, proper assertions)

## Output Format

Provide each test file in a separate code block with the filename as a comment:

```python
# test_filename.py
... test code ...
```

## Required Files

Please generate:

1. **test_domain.py** – Tests for domain classes
2. **test_use_cases.py** – Tests for use case implementations
3. **conftest.py** – Shared pytest fixtures
4. **README.md** – Test execution instructions
"""

        response = self.call_deepseek(prompt)
        test_files = self._extract_code_files(response)
        
        # Save artifacts (similar to main run method)
        generated_artifacts = []
        output_dir = f"output/project_{project_id}/tests"
        os.makedirs(output_dir, exist_ok=True)
        
        for filename, content in test_files.items():
            filepath = os.path.join(output_dir, filename)
            artifact_type = ArtifactType.UNIT_TESTS if filename.startswith("test_") else ArtifactType.UNIT_TESTS
            
            artifact = self.save_artifact(
                filepath=filepath,
                content=content,
                artifact_type=artifact_type,
                metadata={"filename": filename, "generated_from": "design_context"}
            )
            
            if artifact:
                generated_artifacts.append({
                    'id': artifact.id,
                    'name': artifact.name,
                    'artifact_type': artifact.artifact_type.value,
                    'file_path': artifact.file_path
                })
        
        return {
            'project_id': project_id,
            'project_name': project.name,
            'generated_tests': generated_artifacts,
            'test_files': list(test_files.keys())
        }

    def _build_test_prompt(
        self,
        project: Project,
        source_code: Dict[str, str],
        use_cases: List[UseCase]
    ) -> str:
        """Build comprehensive prompt for test generation."""
        
        # Format source code summary
        source_text = ""
        for filename, code in source_code.items():
            source_text += f"\n### {filename}\n```python\n{code[:500]}...\n```\n"
        
        # Format use cases for test scenarios
        use_cases_text = "\n".join([
            f"- **UC{uc.uc_id}: {uc.title}**\n"
            f"  Actor: {uc.actor.name if uc.actor else 'System'}\n"
            f"  Success scenario:\n" + "\n".join(f"    {i+1}. {step}" for i, step in enumerate(uc.success_scenario))
            for uc in use_cases
        ])
        
        prompt = f"""
You are tasked with creating comprehensive tests for the following Python application:

# Project: {project.name}
**Domain**: {project.domain}
**Description**: {project.description}

## Source Code Files
{source_text}

## Use Cases to Test
{use_cases_text}

# Test Generation Requirements

Generate a complete pytest test suite that:

1. **Unit tests** for each class and method in the source code
2. **Integration tests** for each use case scenario
3. **Edge case tests** for boundary conditions and error handling
4. **Mocking** of external dependencies where needed
5. **Fixtures** for common test setup (in conftest.py)
6. **UAT checklist** with acceptance criteria for each use case

# Output Format

Provide each file in a separate code block with the filename as a comment:

```python
# filename.py
... test code ...
```

# Required Files

Please generate at least these files:

1. **conftest.py** – Shared pytest fixtures
2. **test_domain.py** – Unit tests for domain classes
3. **test_use_cases.py** – Integration tests for use case implementations
4. **test_edge_cases.py** – Edge case and error condition tests
5. **uat_checklist.md** – User Acceptance Testing checklist

# Important

- Use **pytest** (not unittest)
- Include **descriptive test names** that explain what is being tested
- Use **parametrized tests** for multiple input scenarios
- Include **docstrings** for each test function
- The tests should be **runnable** with `pytest` command
"""

        return prompt

    def _extract_code_files(self, text: str) -> Dict[str, str]:
        """
        Extract named code blocks from the response.
        
        Handles Python code blocks and markdown blocks for UAT checklists.
        """
        files = {}
        
        # Pattern for Python code blocks
        python_pattern = r"```python\s*\n#\s*(\w+\.py)\s*\n(.*?)```"
        python_matches = re.findall(python_pattern, text, re.DOTALL)
        
        for filename, code in python_matches:
            files[filename] = f"# {filename}\n{code.strip()}\n"
        
        # Pattern for markdown blocks (UAT checklists)
        markdown_pattern = r"```markdown\s*\n#?\s*(\w+\.md)\s*\n(.*?)```"
        markdown_matches = re.findall(markdown_pattern, text, re.DOTALL)
        
        for filename, content in markdown_matches:
            files[filename] = f"# {filename}\n{content.strip()}\n"
        
        # Fallback: extract any code blocks
        if not files:
            # Try generic code blocks
            pattern = r"```(?:python|markdown)?\s*\n(.*?)```"
            matches = re.findall(pattern, text, re.DOTALL)
            for i, content in enumerate(matches):
                # Try to detect filename from first line
                first_line = content.strip().split("\n")[0]
                if first_line.startswith("#") and ("." in first_line):
                    filename = first_line.replace("#", "").strip()
                    files[filename] = content.strip() + "\n"
                else:
                    # Assign generic names
                    if "test" in content.lower():
                        files[f"test_module_{i}.py"] = content.strip() + "\n"
                    elif "uat" in content.lower() or "checklist" in content.lower():
                        files[f"uat_checklist_{i}.md"] = content.strip() + "\n"
                    else:
                        files[f"module_{i}.py"] = content.strip() + "\n"
        
        return files