"""
Architect Agent - Generates UML diagrams from validated use cases.

Responsibilities (Larman):
- Create domain models (actors, use cases, relationships)
- Generate sequence diagrams for each use case
- Ensure architectural integrity and traceability
"""
import os
import re
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseAgent
from ..db.models import AgentRole, Project, Actor, UseCase, ArtifactType, Artifact


class ArchitectAgent(BaseAgent):
    """
    Architect agent for UML diagram generation.

    Key responsibilities:
    1. Generate PlantUML domain diagrams (actors + use cases)
    2. Generate PlantUML sequence diagrams for each use case
    3. Maintain traceability between requirements and architecture
    4. Apply architectural patterns (layered, hexagonal, etc.)
    """

    def __init__(self, db_session: Optional[Session] = None, project_id: Optional[int] = None):
        system_prompt = """You are a senior software architect following Craig Larman's
        Object-Oriented Analysis and Design methodology. Your expertise includes:

        1. Creating clear, communicative UML diagrams
        2. Designing domain models that capture the problem space
        3. Generating sequence diagrams that illustrate system behavior
        4. Applying architectural patterns (layered, ports & adapters, etc.)
        5. Ensuring traceability between requirements and architecture

        You think in terms of clarity and communication, not just correctness."""

        super().__init__(
            name="ArchitectAgent",
            system_prompt=system_prompt,
            agent_role=AgentRole.ARCHITECT,
            db_session=db_session,
            project_id=project_id
        )

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run architect agent. Generates UML diagrams for the project.

        Args:
            context: Must contain 'project_id' (int) and optional 'diagram_types' (list)

        Returns:
            Dict with generated diagram paths and metadata
        """
        project_id = context.get('project_id', self.project_id)
        if not project_id:
            raise ValueError("project_id required in context or agent initialization")

        diagram_types = context.get('diagram_types', ['domain', 'sequence'])

        # Load project data
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        actors = self.db.query(Actor).filter(Actor.project_id == project_id).all()
        use_cases = self.db.query(UseCase).filter(UseCase.project_id == project_id).all()

        results = {
            'project_id': project_id,
            'project_name': project.name,
            'generated_artifacts': []
        }

        # Generate diagrams
        for diagram_type in diagram_types:
            if diagram_type == 'domain':
                artifact = self.generate_domain_diagram(project, actors, use_cases)
                results['generated_artifacts'].append(artifact)
            elif diagram_type == 'sequence':
                sequence_artifacts = self.generate_sequence_diagrams(project, actors, use_cases)
                results['generated_artifacts'].extend(sequence_artifacts)
            else:
                self.log_warning(f"Unknown diagram type: {diagram_type}")

        # Create audit log
        self.log_activity(
            action="generate_diagrams",
            details={
                "diagram_types": diagram_types,
                "num_artifacts": len(results['generated_artifacts'])
            }
        )

        return results

    def generate_domain_diagram(self, project: Project, actors: List[Actor], use_cases: List[UseCase]) -> Dict[str, Any]:
        """
        Generate PlantUML domain diagram (use case diagram).

        Shows actors, use cases, and their relationships.
        """
        # PlantUML header
        plantuml = [
            "@startuml",
            "title Use Case Diagram: " + project.name,
            "left to right direction",
            ""
        ]

        # Add actors
        for actor in actors:
            plantuml.append(f'actor "{actor.name}" as {self._safe_id(actor.name)}')
            if actor.description:
                plantuml.append(f'note right of {self._safe_id(actor.name)}\n{actor.description}\nend note')

        plantuml.append("")

        # Add use cases as (system) rectangle
        plantuml.append('rectangle "System" {')
        for uc in use_cases:
            uc_id = self._safe_id(f"UC{uc.id}")
            plantuml.append(f'  usecase "{uc.title}" as {uc_id}')
            # Add note with ID and priority
            note_lines = []
            note_lines.append(f"ID: {uc.uc_id}")
            note_lines.append(f"Priority: {uc.priority}")
            if uc.pre_conditions and isinstance(uc.pre_conditions, list) and uc.pre_conditions:
                note_lines.append(f"Pre: {', '.join(uc.pre_conditions[:2])}")
            plantuml.append(f'  note right of {uc_id}')
            plantuml.extend([f'    {line}' for line in note_lines])
            plantuml.append('  end note')
        plantuml.append("}")
        plantuml.append("")

        # Connect actors to use cases
        for uc in use_cases:
            actor_name = uc.actor if isinstance(uc.actor, str) else uc.actor.name if uc.actor else "Unknown"
            actor_id = self._safe_id(actor_name)
            uc_id = self._safe_id(f"UC{uc.id}")
            plantuml.append(f'{actor_id} --> {uc_id}')

        plantuml.append("@enduml")

        # Create artifact
        content = '\n'.join(plantuml)
        filepath = self._get_output_path(project.id, "domain_diagram.puml")
        artifact = self.save_artifact(
            filepath=filepath,
            content=content,
            artifact_type=ArtifactType.DOMAIN_DIAGRAM,
            metadata={
                "actors_count": len(actors),
                "use_cases_count": len(use_cases),
                "project_name": project.name
            }
        )

        return {
            "type": "domain_diagram",
            "artifact_id": artifact.id,
            "filename": artifact.name,
            "filepath": artifact.file_path,
            "content_hash": artifact.content_hash,
            "plantuml_code": content  # For immediate preview
        }

    def generate_sequence_diagrams(self, project: Project, actors: List[Actor], use_cases: List[UseCase]) -> List[Dict[str, Any]]:
        """
        Generate sequence diagrams for each use case.

        Each diagram shows the interaction between actor and system
        based on the success scenario steps.
        """
        artifacts = []

        for uc in use_cases:
            # Get actor name
            actor_name = uc.actor if isinstance(uc.actor, str) else uc.actor.name if uc.actor else "Unknown"

            plantuml = [
                "@startuml",
                f"title Sequence Diagram: {uc.title} (UC{uc.id})",
                ""
            ]

            # Participants
            plantuml.append(f'actor "{actor_name}" as Actor')
            plantuml.append(f'participant "System" as System')
            plantuml.append("")

            # Success scenario steps
            steps = uc.success_scenario if isinstance(uc.success_scenario, list) else []

            for i, step in enumerate(steps, 1):
                plantuml.append(f'Actor -> System: {step}')
                if i < len(steps):
                    plantuml.append(f'System --> Actor: OK')

            plantuml.append("@enduml")

            content = '\n'.join(plantuml)
            filepath = self._get_output_path(project.id, f"uc{uc.id}_sequence.puml")
            artifact = self.save_artifact(
                filepath=filepath,
                content=content,
                artifact_type=ArtifactType.SEQUENCE_DIAGRAM,
                metadata={
                    "use_case_id": uc.id,
                    "use_case_name": uc.title,
                    "actor": actor_name,
                    "steps_count": len(steps)
                }
            )

            artifacts.append({
                "type": "sequence_diagram",
                "artifact_id": artifact.id,
                "filename": artifact.name,
                "filepath": artifact.file_path,
                "content_hash": artifact.content_hash,
                "plantuml_code": content
            })

        return artifacts

    def _get_output_path(self, project_id: int, filename: str) -> str:
        """
        Generate output file path for artifacts.
        
        Args:
            project_id: Project ID
            filename: Base filename
            
        Returns:
            Full path: output/project_{project_id}/{filename}
        """
        import os
        output_dir = f"output/project_{project_id}"
        os.makedirs(output_dir, exist_ok=True)
        return os.path.join(output_dir, filename)

    def _safe_id(self, text: str) -> str:
        """Convert text to PlantUML-safe identifier."""
        # Remove special characters, replace spaces with underscore
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', text)
        # Ensure starts with letter
        if safe and safe[0].isdigit():
            safe = 'ID_' + safe
        return safe

    def render_diagram(self, plantuml_code: str, output_format: str = "png") -> Optional[str]:
        """
        Render PlantUML code to image (requires PlantUML installation).

        Args:
            plantuml_code: PlantUML source code
            output_format: png, svg, pdf, etc.

        Returns:
            Path to generated image, or None if rendering fails
        """
        try:
            import plantuml
            # Local PlantUML server (requires Java)
            # For simplicity, we'll just return the PlantUML code
            # In production, would call plantuml.PlantUML()
            self.log_info(f"PlantUML rendering not yet implemented. Would generate {output_format}.")
            return None
        except ImportError:
            self.log_warning("plantuml package not installed. Install with: pip install plantuml")
            return None