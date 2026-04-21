"""
Deployer Agent - Generates Docker and deployment configuration.

Responsibilities (Larman's Transition phase):
- Create containerization configuration (Dockerfile, docker‑compose.yml)
- Generate deployment manifests for cloud platforms
- Produce environment configuration and secrets management
- Create CI/CD pipeline definitions
"""
import os
import re
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseAgent
from ..db.models import (
    AgentRole, Project, ArtifactType, Artifact
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
You are tasked with creating production‑ready deployment configuration for the following Python application:

# Project: {project.name}
**Domain**: {project.domain}
**Description**: {project.description}

## Application Details
- **Python Version**: 3.12+ (assume latest stable)
- **Source Files**: {', '.join(source_files[:10])} ({len(source_files)} total)
- **Test Files**: {', '.join(test_files[:5])} ({len(test_files)} total)
- **Dependencies**: {', '.join(dependencies) if dependencies else 'None (standard library only)'}
- **Entry Point**: `main.py` (assumed)

## Deployment Requirements

Generate a complete deployment configuration that includes:

### 1. Containerization
- **Dockerfile** with multi‑stage build (development + production)
- **.dockerignore** file to exclude unnecessary files
- **docker‑compose.yml** for local development and testing

### 2. Cloud Deployment (choose one platform)
- **Kubernetes manifests** (Deployment, Service, ConfigMap, Secret)
- **AWS ECS/Fargate** task definition and service configuration
- **Azure Container Apps** deployment configuration

### 3. CI/CD Pipeline
- **GitHub Actions workflow** for testing and deployment
- **GitLab CI/CD pipeline** configuration

### 4. Environment Configuration
- **.env.example** template with required environment variables
- **Configuration management** for different environments (dev, staging, prod)

### 5. Monitoring & Observability
- **Health check** endpoints and configuration
- **Logging configuration** (structured JSON logs)
- **Metrics exposure** (Prometheus metrics if applicable)

## Output Format

Provide each file in a separate code block with the filename as a comment:

```dockerfile
# Dockerfile
... content ...
```

```yaml
# docker-compose.yml
... content ...
```

```yaml
# k8s/deployment.yaml
... content ...
```

## Important Guidelines

- Follow **security best practices** (non‑root user, minimal base images)
- Use **specific version tags** (not `latest`)
- Include **health checks** and **graceful shutdown**
- Configure **resource limits** for containers
- Provide **clear documentation** in comments
- Make the configuration **environment‑aware** (dev/staging/prod)
"""

        return prompt

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