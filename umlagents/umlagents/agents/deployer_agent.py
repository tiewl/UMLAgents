"""
Deployer Agent - Generates Docker and deployment configuration.

Responsibilities (Larman's Transition phase):
- Create containerization configuration (Dockerfile, docker‑compose.yml)
- Generate deployment manifests for cloud platforms
- Produce environment configuration and secrets management
- Create CI/CD pipeline definitions
- Generate project README.md with structure and deployment guide
"""
import os
import re
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseAgent
from ..db.models import (
    AgentRole, Project, UseCase, Actor, ArtifactType, Artifact
)


class DeployerAgent(BaseAgent):
    """
    Deployer agent for deployment configuration generation.

    Key responsibilities:
    1. Generate Dockerfile for containerization
    2. Create docker‑compose.yml for local development
    3. Produce cloud deployment manifests (Kubernetes, AWS, etc.)
    4. Generate environment configuration templates
    5. Save deployment artifacts with content hashing
    """

    def __init__(self, db_session: Optional[Session] = None, project_id: Optional[int] = None):
        system_prompt = """You are a senior DevOps engineer specializing in containerization
        and cloud deployment. Your expertise includes:

        1. Creating production‑ready Docker configurations for Python applications
        2. Writing Kubernetes manifests and Helm charts
        3. Setting up CI/CD pipelines (GitHub Actions, GitLab CI)
        4. Configuring environment variables and secrets management
        5. Following infrastructure‑as‑code and security best practices

        You think in terms of reproducibility, scalability, and operational excellence.
        """

        super().__init__(
            name="DeployerAgent",
            system_prompt=system_prompt,
            agent_role=AgentRole.DEPLOYER,
            db_session=db_session,
            project_id=project_id
        )
        if not os.getenv("UMLAGENTS_DEPLOYERAGENT_MODEL"):
            self._model = os.getenv("UMLAGENTS_DEFAULT_MODEL", "claude-haiku-4-5-20251001")

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate deployment configuration for project.

        Args:
            context: Must contain 'project_id' (int)

        Returns:
            Dict with generated deployment files and artifact records
        """
        project_id = context.get('project_id', self.project_id)
        if not project_id:
            raise ValueError("project_id required in context or agent initialization")

        # Load project data
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # Skip if deployment artifacts already exist and skip_existing is True
        if context.get('skip_existing', False):
            existing_deployment = self.db.query(Artifact).filter(
                Artifact.project_id == project_id,
                Artifact.artifact_type.in_([ArtifactType.DOCKERFILE, ArtifactType.DEPLOYMENT_CONFIG])
            ).count()
            if existing_deployment > 0:
                print(f"[DeployerAgent] Skipping - {existing_deployment} deployment artifacts already exist")
                # Return existing artifacts
                existing_artifacts = self.db.query(Artifact).filter(
                    Artifact.project_id == project_id,
                    Artifact.artifact_type.in_([ArtifactType.DOCKERFILE, ArtifactType.DEPLOYMENT_CONFIG])
                ).all()
                return {
                    'project_id': project_id,
                    'project_name': project.name,
                    'generated_deployment': [
                        {
                            'id': art.id,
                            'name': art.name,
                            'artifact_type': art.artifact_type.value,
                            'file_path': art.file_path
                        }
                        for art in existing_artifacts
                    ]
                }

        # Gather source code artifacts to understand dependencies
        source_artifacts = self.db.query(Artifact).filter(
            Artifact.project_id == project_id,
            Artifact.artifact_type == ArtifactType.SOURCE_CODE
        ).all()
        
        # Extract dependencies from requirements.txt if exists
        dependencies = self._extract_dependencies(source_artifacts)
        
        # Gather test artifacts to understand testing requirements
        test_artifacts = self.db.query(Artifact).filter(
            Artifact.project_id == project_id,
            Artifact.artifact_type == ArtifactType.UNIT_TESTS
        ).all()

        print(f"[DeployerAgent] Generating deployment config for project: {project.name}")
        print(f"[DeployerAgent] Source files: {len(source_artifacts)}, Tests: {len(test_artifacts)}")
        print(f"[DeployerAgent] Dependencies: {', '.join(dependencies) if dependencies else 'None'}")

        # Build comprehensive prompt
        prompt = self._build_deployment_prompt(project, dependencies, source_artifacts, test_artifacts)

        # Call DeepSeek API
        response = self.call_deepseek(prompt)

        # Extract deployment files from response
        deployment_files = self._extract_deployment_files(response)

        # Save files and create artifacts
        generated_artifacts = []
        output_dir = f"output/project_{project_id}/deployment"
        os.makedirs(output_dir, exist_ok=True)

        for filename, content in deployment_files.items():
            filepath = os.path.join(output_dir, filename)
            
            # Determine artifact type based on filename
            if "Dockerfile" in filename:
                artifact_type = ArtifactType.DOCKERFILE
            elif "docker-compose" in filename:
                artifact_type = ArtifactType.DEPLOYMENT_CONFIG
            elif "k8s" in filename or "kubernetes" in filename:
                artifact_type = ArtifactType.DEPLOYMENT_CONFIG
            elif "cloud" in filename or "aws" in filename or "azure" in filename:
                artifact_type = ArtifactType.DEPLOYMENT_CONFIG
            elif "github" in filename or "gitlab" in filename or "ci" in filename or "cd" in filename:
                artifact_type = ArtifactType.DEPLOYMENT_CONFIG
            elif "env" in filename or "config" in filename:
                artifact_type = ArtifactType.DEPLOYMENT_CONFIG
            else:
                artifact_type = ArtifactType.DEPLOYMENT_CONFIG
            
            artifact = self.save_artifact(
                filepath=filepath,
                content=content,
                artifact_type=artifact_type,
                metadata={
                    "filename": filename,
                    "project_name": project.name,
                    "dependencies": dependencies
                }
            )
            
            if artifact:
                generated_artifacts.append({
                    'id': artifact.id,
                    'name': artifact.name,
                    'artifact_type': artifact.artifact_type.value,
                    'file_path': artifact.file_path
                })

        # Generate README.md at the project root output folder
        readme_content = self._generate_readme(project, source_artifacts, test_artifacts, deployment_files)
        readme_path = f"output/project_{project_id}/README.md"
        readme_artifact = self.save_artifact(
            filepath=readme_path,
            content=readme_content,
            artifact_type=ArtifactType.DEPLOYMENT_CONFIG,
            metadata={"filename": "README.md", "project_name": project.name},
        )
        if readme_artifact:
            generated_artifacts.append({
                'id': readme_artifact.id,
                'name': readme_artifact.name,
                'artifact_type': readme_artifact.artifact_type.value,
                'file_path': readme_artifact.file_path,
            })

        # Log completion
        self.log_activity(
            action="generate_deployment",
            details={
                "num_source_files": len(source_artifacts),
                "num_test_files": len(test_artifacts),
                "num_deployment_files": len(deployment_files),
                "project_id": project_id
            }
        )

        return {
            'project_id': project_id,
            'project_name': project.name,
            'generated_deployment': generated_artifacts,
            'deployment_files': list(deployment_files.keys())
        }

    def _extract_dependencies(self, source_artifacts: List[Artifact]) -> List[str]:
        """Extract Python dependencies from source artifacts."""
        dependencies = []
        
        # Look for requirements.txt
        for artifact in source_artifacts:
            if artifact.name == "requirements.txt" and artifact.file_path and os.path.exists(artifact.file_path):
                try:
                    with open(artifact.file_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                dependencies.append(line)
                except Exception as e:
                    print(f"[DeployerAgent] Error reading requirements.txt: {e}")
        
        # If no requirements.txt found, infer from Python files
        if not dependencies:
            # Simple inference: assume standard library only for dice game
            dependencies = ["No external dependencies detected (using Python standard library)"]
        
        return dependencies

    def _build_deployment_prompt(
        self,
        project: Project,
        dependencies: List[str],
        source_artifacts: List[Artifact],
        test_artifacts: List[Artifact]
    ) -> str:
        """Build comprehensive prompt for deployment generation."""
        
        # List source files
        source_files = [a.name for a in source_artifacts if a.name.endswith('.py')]
        test_files = [a.name for a in test_artifacts if a.name.endswith('.py')]
        
        prompt = f"""
Generate Docker deployment configuration for this FastAPI web application.

# Project: {project.name}
**Domain**: {project.domain}
**Description**: {project.description}

## Application files
- Source: {', '.join(source_files[:10])}
- Dependencies: {', '.join(dependencies) if dependencies else 'fastapi, uvicorn, sqlalchemy, pydantic, psycopg2-binary'}

## STRICT RULES

1. The app is a **FastAPI web service** started with:
   `uvicorn main:app --host 0.0.0.0 --port 8080`

2. **Dockerfile** requirements:
   - Base image: `python:3.12-slim`
   - Build context is the project root (parent of `deployment/`), so COPY paths are:
     `COPY code/ /app/` and `COPY tests/ /app/tests/`
   - Install from `code/requirements.txt`
   - EXPOSE 8080
   - CMD runs uvicorn on main:app

3. **docker-compose.yml** requirements:
   - `context: ..` and `dockerfile: deployment/Dockerfile`
   - `app` service: maps port 8080:8080, sets `DATABASE_URL` pointing to the `db` service
   - `db` service: postgres:16-alpine, with health check — NO profiles
   - `app` depends_on db with `condition: service_healthy`
   - Plain `docker compose up --build` must work with zero extra flags

4. Generate ONLY: `Dockerfile` and `docker-compose.yml` — nothing else.

## Output format

```dockerfile
# Dockerfile
...
```

```yaml
# docker-compose.yml
...
```
"""

        return prompt

    def _generate_readme(
        self,
        project: Project,
        source_artifacts: List[Artifact],
        test_artifacts: List[Artifact],
        deployment_files: Dict[str, str],
    ) -> str:
        """Generate a README.md from project data — no LLM call needed."""
        actors = self.db.query(Actor).filter(Actor.project_id == project.id).all()
        use_cases = self.db.query(UseCase).filter(UseCase.project_id == project.id).order_by(UseCase.priority).all()

        source_names = [a.name for a in source_artifacts]
        test_names = [a.name for a in test_artifacts]
        deploy_names = list(deployment_files.keys())
        has_docker = any("Dockerfile" in n for n in deploy_names)
        has_compose = any("docker-compose" in n for n in deploy_names)

        uc_lines = "\n".join(
            f"| {uc.uc_id} | {uc.title} | {uc.actor.name if uc.actor else 'System'} |"
            for uc in use_cases
        ) or "| — | No use cases found | — |"

        actor_lines = "\n".join(
            f"- **{a.name}** ({a.role}): {a.description}"
            for a in actors
        ) or "- No actors found"

        reg = ", ".join(project.regulatory_frameworks or []) or "None"

        frameworks_note = ""
        if project.regulatory_frameworks:
            frameworks_note = (
                "\n> **Compliance note:** This project is subject to "
                + reg
                + " requirements. Ensure all environment variables and secrets are managed securely.\n"
            )

        is_web_app = any(n in source_names for n in ("main.py", "database.py", "models.py"))
        source_tree = "\n".join(f"    {n}" for n in source_names) or "    (none)"
        test_tree   = "\n".join(f"    {n}" for n in test_names)   or "    (none)"
        deploy_tree = "\n".join(f"    {n}" for n in deploy_names) or "    (none)"

        app_name_slug = project.name.lower().replace(' ', '-')

        docker_section = ""
        if has_docker and has_compose:
            docker_section = f"""
## Deploying the Web App

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

### Start with Docker Compose

```bash
# From the deployment/ folder
cd deployment

# Build and start all services (first run downloads images — takes ~1 min)
docker compose up --build

# Run in the background
docker compose up --build -d

# View logs
docker compose logs -f

# Stop all services
docker compose down

# Stop AND wipe the database (clean slate)
docker compose down -v
```

### What opens after `docker compose up --build`

| URL | Description |
|-----|-------------|
| `http://localhost:8080/` | **Web UI** — Bootstrap 5 app, use this to test all features |
| `http://localhost:8080/docs` | **Swagger UI** — interactive API explorer |
| `http://localhost:8080/health` | Health check JSON |

### Testing the app

1. Open `http://localhost:8080/` in your browser.
2. Use the left sidebar to navigate between use cases.
3. Fill in the forms and click Submit — each form calls the matching API endpoint.
4. The "API Response" panel at the bottom of each card shows the raw JSON returned.
5. Use the "Load" buttons on list sections to fetch existing records.

### Build image only (no Compose)

```bash
docker build -f deployment/Dockerfile -t {app_name_slug} .
docker run --rm -p 8080:8080 {app_name_slug}
```
"""
        elif has_docker:
            docker_section = f"""
## Docker Deployment

```bash
docker build -f deployment/Dockerfile -t {app_name_slug} .
docker run --rm -p 8080:8080 {app_name_slug}
```
"""

        return f"""# {project.name}

**Domain:** {project.domain}
**Generated:** {datetime.now().strftime('%Y-%m-%d')}
**Regulatory frameworks:** {reg}
{frameworks_note}
## Overview

{project.description}

## Actors

{actor_lines}

## Use Cases

| ID | Title | Primary Actor |
|----|-------|---------------|
{uc_lines}

## Project Structure

```
project_{project.id}/
|
+-- code/               # Generated Python source code
{source_tree}
|
+-- tests/              # Automated test suite
{test_tree}
|
+-- deployment/         # Docker and deployment configuration
{deploy_tree}
|
+-- diagrams/           # UML diagrams (PlantUML)
    domain_diagram.puml     Use-case overview
    class_diagram.puml      Class relationships
    uc*_sequence.puml       Per-use-case sequence diagrams
|
+-- requirements.yaml   # Source-of-truth requirements (Larman format)
+-- README.md           # This file
```

## Running Locally (without Docker)

### Prerequisites
- Python 3.11+
- pip

### Quick start

```bash
cd code
pip install -r requirements.txt
{"uvicorn main:app --reload --port 8080" if is_web_app else "python main.py"}
```
{"Open **http://localhost:8080/** for the web UI, or **http://localhost:8080/docs** for Swagger." if is_web_app else ""}

### Run tests

```bash
cd tests
pip install pytest
pytest -v
```
{docker_section}
## Traceability

Every class and method in `code/` references the use case it implements.
Every test in `tests/` references the use case it validates.
The full traceability matrix is captured in `tests/uat_checklist.md`.

## Generated by UMLAgents

This project was generated using the [UMLAgents](https://github.com/tiewl/UMLAgents) pipeline,
following Craig Larman's OOA/OOD methodology (ISBN 9780137488803).
"""

    def _extract_deployment_files(self, text: str) -> Dict[str, str]:
        """
        Extract deployment configuration files from the response.
        
        Handles Dockerfile, YAML, and other configuration formats.
        """
        files = {}
        
        # Pattern for Dockerfile
        docker_pattern = r"```dockerfile\s*\n#?\s*(Dockerfile)\s*\n(.*?)```"
        docker_matches = re.findall(docker_pattern, text, re.DOTALL)
        
        for filename, content in docker_matches:
            files[filename] = content.strip() + "\n"
        
        # Pattern for YAML files (docker-compose, Kubernetes)
        yaml_pattern = r"```ya?ml\s*\n#?\s*(\S+\.ya?ml)\s*\n(.*?)```"
        yaml_matches = re.findall(yaml_pattern, text, re.DOTALL)
        
        for filename, content in yaml_matches:
            files[filename] = content.strip() + "\n"
        
        # Pattern for shell scripts, env files, etc.
        generic_pattern = r"```(?:bash|sh|text|plaintext)?\s*\n#?\s*(\S+\.\w+)\s*\n(.*?)```"
        generic_matches = re.findall(generic_pattern, text, re.DOTALL)
        
        for filename, content in generic_matches:
            files[filename] = content.strip() + "\n"
        
        # Fallback: extract any code blocks
        if not files:
            # Try to find blocks with filenames in comments
            pattern = r"```\s*\n#\s*(\S+)\s*\n(.*?)```"
            matches = re.findall(pattern, text, re.DOTALL)
            for filename, content in matches:
                files[filename] = content.strip() + "\n"
            
            # Last resort: create generic files
            if not files:
                # Look for Dockerfile content
                if "FROM python" in text:
                    docker_start = text.find("FROM python")
                    docker_end = text.find("\n```", docker_start)
                    if docker_end == -1:
                        docker_end = len(text)
                    docker_content = text[docker_start:docker_end].strip()
                    files["Dockerfile"] = docker_content + "\n"
                
                # Look for docker-compose content
                if "version:" in text.lower():
                    compose_start = text.lower().find("version:")
                    compose_end = text.find("\n```", compose_start)
                    if compose_end == -1:
                        compose_end = len(text)
                    compose_content = text[compose_start:compose_end].strip()
                    files["docker-compose.yml"] = compose_content + "\n"
        
        return files