"""
Design Agent - Applies GRASP/GoF patterns to use cases.

Responsibilities (Larman):
- Analyze use cases for design problems
- Apply appropriate GRASP patterns (Creator, Expert, Controller, etc.)
- Apply GoF patterns where appropriate (Factory, Strategy, Observer, etc.)
- Document design decisions with rationale
- Ensure high cohesion and low coupling
"""
import os
import json
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseAgent
from ..db.models import (
    AgentRole, Project, Actor, UseCase, DesignDecision, 
    PatternApplication, PatternCategory, ArtifactType, Artifact
)


class DesignAgent(BaseAgent):
    """
    Design agent for pattern application and design decisions.

    Key responsibilities:
    1. Analyze use cases for design problems
    2. Apply GRASP patterns (Creator, Expert, Controller, Pure Fabrication, Indirection)
    3. Apply GoF patterns (Creational, Structural, Behavioral)
    4. Document design decisions with alternatives considered
    5. Create initial class diagrams based on pattern applications
    """

    def __init__(self, db_session: Optional[Session] = None, project_id: Optional[int] = None):
        system_prompt = """You are a senior software designer following Craig Larman's
        Object-Oriented Analysis and Design methodology. Your expertise includes:

        1. GRASP pattern application (Creator, Expert, Controller, Pure Fabrication, Indirection)
        2. GoF pattern selection and application (Factory, Strategy, Observer, etc.)
        3. Design decision documentation with rationale
        4. Evaluating coupling, cohesion, and maintainability
        5. Creating design artifacts that support implementation

        You think critically about trade-offs and always document your reasoning.
        When applying patterns, explain:
        - Why this pattern solves the specific design problem
        - What alternatives were considered
        - How it impacts maintainability and flexibility
        """

        super().__init__(
            name="DesignAgent",
            system_prompt=system_prompt,
            agent_role=AgentRole.DESIGN,
            db_session=db_session,
            project_id=project_id
        )
        print(f"[DesignAgent] Initialized for project {project_id}")

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run design agent. Analyzes use cases and applies patterns.

        Args:
            context: Must contain 'project_id' (int)

        Returns:
            Dict with design decisions, pattern applications, and generated artifacts
        """
        project_id = context.get('project_id', self.project_id)
        if not project_id:
            raise ValueError("project_id required in context or agent initialization")

        # Load project data
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # Skip if pattern applications already exist and skip_existing is True
        if context.get('skip_existing', False):
            existing_patterns = self.db.query(PatternApplication).filter(
                PatternApplication.project_id == project_id
            ).count()
            if existing_patterns > 0:
                print(f"[DesignAgent] Skipping - {existing_patterns} pattern applications already exist")
                # Return existing data
                existing_design_decisions = self.db.query(DesignDecision).filter(
                    DesignDecision.project_id == project_id
                ).all()
                existing_artifacts = self.db.query(Artifact).filter(
                    Artifact.project_id == project_id,
                    Artifact.artifact_type == ArtifactType.CLASS_DIAGRAM
                ).all()
                
                return {
                    'project_id': project_id,
                    'project_name': project.name,
                    'design_decisions': [
                        {
                            'id': dd.id,
                            'title': dd.title,
                            'use_case_id': dd.use_case_id,
                            'use_case_title': dd.use_case.title if dd.use_case else ''
                        }
                        for dd in existing_design_decisions
                    ],
                    'pattern_applications': [
                        {
                            'id': pa.id,
                            'pattern_name': pa.pattern_name,
                            'pattern_category': pa.pattern_category.value,
                            'use_case_id': pa.use_case_id
                        }
                        for pa in self.db.query(PatternApplication).filter(
                            PatternApplication.project_id == project_id
                        ).all()
                    ],
                    'generated_artifacts': [
                        {
                            'id': art.id,
                            'name': art.name,
                            'artifact_type': art.artifact_type.value,
                            'file_path': art.file_path
                        }
                        for art in existing_artifacts
                    ]
                }

        use_cases = self.db.query(UseCase).filter(UseCase.project_id == project_id).all()
        print(f"[DesignAgent] Analyzing project: {project.name} (ID: {project_id}) with {len(use_cases)} use cases")
        if not use_cases:
            self.log_warning(f"No use cases found for project {project_id}")
            return {
                'project_id': project_id,
                'design_decisions': [],
                'pattern_applications': [],
                'generated_artifacts': []
            }

        results = {
            'project_id': project_id,
            'project_name': project.name,
            'design_decisions': [],
            'pattern_applications': [],
            'generated_artifacts': []
        }

        # Analyze each use case and apply patterns
        for use_case in use_cases:
            uc_analysis = self.analyze_use_case(use_case)
            
            # Create design decision for this use case
            design_decision = self.create_design_decision(
                project_id=project_id,
                use_case_id=use_case.id,
                analysis=uc_analysis
            )
            
            if design_decision:
                results['design_decisions'].append({
                    'id': design_decision.id,
                    'title': design_decision.title,
                    'use_case_id': use_case.id,
                    'use_case_title': use_case.title
                })
                
                # Apply patterns based on analysis
                pattern_applications = self.apply_patterns(
                    project_id=project_id,
                    use_case_id=use_case.id,
                    design_decision_id=design_decision.id,
                    analysis=uc_analysis
                )
                
                results['pattern_applications'].extend([
                    {
                        'id': pa.id,
                        'pattern_name': pa.pattern_name,
                        'pattern_category': pa.pattern_category.value,
                        'use_case_id': use_case.id
                    }
                    for pa in pattern_applications
                ])

        # Generate initial class diagram based on pattern applications
        if results['pattern_applications']:
            class_diagram_artifact = self.generate_class_diagram(project_id)
            if class_diagram_artifact:
                results['generated_artifacts'].append({
                    'id': class_diagram_artifact.id,
                    'name': class_diagram_artifact.name,
                    'artifact_type': class_diagram_artifact.artifact_type.value,
                    'file_path': class_diagram_artifact.file_path
                })

        # Create audit log
        self.log_activity(
            action="apply_design_patterns",
            details={
                "num_use_cases": len(use_cases),
                "num_design_decisions": len(results['design_decisions']),
                "num_pattern_applications": len(results['pattern_applications']),
                "num_artifacts": len(results['generated_artifacts'])
            }
        )

        return results

    def analyze_use_case(self, use_case: UseCase) -> Dict[str, Any]:
        """
        Analyze a use case for design problems and pattern opportunities.
        
        Uses AI to identify:
        - Object creation needs (Creator pattern)
        - Information expert candidates (Expert pattern)
        - Controller candidates for system events
        - Pure fabrication opportunities
        - Indirection needs for coupling reduction
        - GoF pattern opportunities
        """
        # Prepare use case data for AI analysis
        uc_data = {
            'title': use_case.title,
            'id': use_case.uc_id,
            'actor': use_case.actor.name if use_case.actor else 'Unknown',
            'priority': use_case.priority,
            'success_scenario': use_case.success_scenario,
            'extension_scenarios': use_case.extension_scenarios,
            'pre_conditions': use_case.pre_conditions,
            'post_conditions': use_case.post_conditions
        }
        print(f"[DesignAgent] Analyzing use case {uc_data['id']}: {uc_data['title']}")

        prompt = f"""Analyze this use case for design pattern opportunities:

Use Case {uc_data['id']}: {uc_data['title']}
Actor: {uc_data['actor']}
Priority: {uc_data['priority']}
Success Scenario: {json.dumps(uc_data['success_scenario'], indent=2)}
{'- Extension Scenarios: ' + json.dumps(uc_data['extension_scenarios'], indent=2) if uc_data['extension_scenarios'] else ''}
Pre-conditions: {json.dumps(uc_data['pre_conditions'], indent=2) if uc_data['pre_conditions'] else 'None'}
Post-conditions: {json.dumps(uc_data['post_conditions'], indent=2) if uc_data['post_conditions'] else 'None'}

Please analyze this use case and identify:
1. GRASP pattern opportunities (Creator, Expert, Controller, Pure Fabrication, Indirection)
2. GoF pattern opportunities (Factory, Strategy, Observer, etc.)
3. Design problems that need to be solved
4. Coupling and cohesion considerations

Return your analysis as a JSON object with this structure:
{{
  "design_problems": ["problem1", "problem2", ...],
  "grasp_patterns": [
    {{"pattern": "Creator", "rationale": "explanation", "applied_to": "description"}},
    {{"pattern": "Expert", "rationale": "explanation", "applied_to": "description"}}
  ],
  "gof_patterns": [
    {{"pattern": "Factory", "rationale": "explanation", "applied_to": "description"}}
  ],
  "coupling_concerns": ["concern1", "concern2"],
  "cohesion_opportunities": ["opportunity1", "opportunity2"]
}}
"""

        try:
            response = self.call_deepseek(prompt, temperature=0.3)
            # Parse JSON from response
            # AI response might have extra text, so find JSON block
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                # Fallback analysis
                analysis = {
                    "design_problems": ["Need to analyze object responsibilities"],
                    "grasp_patterns": [],
                    "gof_patterns": [],
                    "coupling_concerns": [],
                    "cohesion_opportunities": []
                }
            
            return analysis
            
        except Exception as e:
            self.log_warning(f"Error analyzing use case {use_case.uc_id}: {e}")
            return {
                "design_problems": ["Analysis failed"],
                "grasp_patterns": [],
                "gof_patterns": [],
                "coupling_concerns": [],
                "cohesion_opportunities": []
            }

    def create_design_decision(
        self, 
        project_id: int, 
        use_case_id: int, 
        analysis: Dict[str, Any]
    ) -> Optional[DesignDecision]:
        """
        Create a design decision record based on use case analysis.
        """
        try:
            # Create rationale from analysis
            rationale_parts = []
            if analysis.get('design_problems'):
                rationale_parts.append(f"Design problems identified: {', '.join(analysis['design_problems'])}")
            if analysis.get('coupling_concerns'):
                rationale_parts.append(f"Coupling concerns: {', '.join(analysis['coupling_concerns'])}")
            if analysis.get('cohesion_opportunities'):
                rationale_parts.append(f"Cohesion opportunities: {', '.join(analysis['cohesion_opportunities'])}")
            
            rationale = "\n".join(rationale_parts) if rationale_parts else "Standard design analysis performed."
            
            design_decision = DesignDecision(
                project_id=project_id,
                use_case_id=use_case_id,
                title=f"Design for Use Case {use_case_id}",
                description="Design decisions based on pattern analysis",
                rationale=rationale,
                alternatives_considered=["Alternative designs considered during pattern selection"],
                impact_assessment="Pattern applications improve maintainability and flexibility",
                created_by_agent=AgentRole.DESIGN
            )
            
            self.db.add(design_decision)
            self.db.commit()
            
            self.log_info(f"Created design decision {design_decision.id} for use case {use_case_id}")
            return design_decision
            
        except Exception as e:
            self.log_warning(f"Error creating design decision: {e}")
            self.db.rollback()
            return None

    def apply_patterns(
        self, 
        project_id: int, 
        use_case_id: int, 
        design_decision_id: int,
        analysis: Dict[str, Any]
    ) -> List[PatternApplication]:
        """
        Apply patterns based on analysis and create PatternApplication records.
        """
        pattern_applications = []
        
        # Apply GRASP patterns
        for grasp_pattern in analysis.get('grasp_patterns', []):
            pattern_app = self._create_pattern_application(
                project_id=project_id,
                use_case_id=use_case_id,
                design_decision_id=design_decision_id,
                pattern_name=grasp_pattern.get('pattern'),
                pattern_category=self._map_grasp_category(grasp_pattern.get('pattern')),
                description=grasp_pattern.get('applied_to', ''),
                rationale=grasp_pattern.get('rationale', '')
            )
            if pattern_app:
                pattern_applications.append(pattern_app)
        
        # Apply GoF patterns
        for gof_pattern in analysis.get('gof_patterns', []):
            pattern_app = self._create_pattern_application(
                project_id=project_id,
                use_case_id=use_case_id,
                design_decision_id=design_decision_id,
                pattern_name=gof_pattern.get('pattern'),
                pattern_category=self._map_gof_category(gof_pattern.get('pattern')),
                description=gof_pattern.get('applied_to', ''),
                rationale=gof_pattern.get('rationale', '')
            )
            if pattern_app:
                pattern_applications.append(pattern_app)
        
        return pattern_applications

    def _create_pattern_application(
        self,
        project_id: int,
        use_case_id: int,
        design_decision_id: int,
        pattern_name: str,
        pattern_category: PatternCategory,
        description: str,
        rationale: str
    ) -> Optional[PatternApplication]:
        """
        Create a PatternApplication record.
        """
        try:
            pattern_app = PatternApplication(
                project_id=project_id,
                use_case_id=use_case_id,
                design_decision_id=design_decision_id,
                pattern_name=pattern_name,
                pattern_category=pattern_category,
                description=description,
                rationale=rationale,
                created_by_agent=AgentRole.DESIGN
            )
            
            self.db.add(pattern_app)
            self.db.commit()
            
            self.log_info(f"Applied pattern {pattern_name} to use case {use_case_id}")
            return pattern_app
            
        except Exception as e:
            self.log_warning(f"Error creating pattern application for {pattern_name}: {e}")
            self.db.rollback()
            return None

    def _map_grasp_category(self, pattern_name: str) -> PatternCategory:
        """Map GRASP pattern name to PatternCategory enum."""
        pattern_name_lower = pattern_name.lower()
        if 'creator' in pattern_name_lower:
            return PatternCategory.GRASP_CREATOR
        elif 'expert' in pattern_name_lower:
            return PatternCategory.GRASP_EXPERT
        elif 'controller' in pattern_name_lower:
            return PatternCategory.GRASP_CONTROLLER
        elif 'pure fabrication' in pattern_name_lower or 'pure-fabrication' in pattern_name_lower:
            return PatternCategory.GRASP_PURE_FABRICATION
        elif 'indirection' in pattern_name_lower:
            return PatternCategory.GRASP_INDIRECTION
        else:
            return PatternCategory.GRASP_EXPERT  # Default

    def _map_gof_category(self, pattern_name: str) -> PatternCategory:
        """Map GoF pattern name to PatternCategory enum."""
        pattern_name_lower = pattern_name.lower()
        
        # Creational patterns
        creational = ['factory', 'abstract factory', 'builder', 'prototype', 'singleton']
        if any(p in pattern_name_lower for p in creational):
            return PatternCategory.GOF_CREATIONAL
        
        # Structural patterns
        structural = ['adapter', 'bridge', 'composite', 'decorator', 'facade', 'flyweight', 'proxy']
        if any(p in pattern_name_lower for p in structural):
            return PatternCategory.GOF_STRUCTURAL
        
        # Behavioral patterns
        behavioral = ['chain of responsibility', 'command', 'interpreter', 'iterator', 
                     'mediator', 'memento', 'observer', 'state', 'strategy', 
                     'template method', 'visitor']
        if any(p in pattern_name_lower for p in behavioral):
            return PatternCategory.GOF_BEHAVIORAL
        
        return PatternCategory.GOF_BEHAVIORAL  # Default

    def generate_class_diagram(self, project_id: int) -> Optional[Artifact]:
        """
        Generate initial class diagram based on applied patterns.
        This creates a simple PlantUML class diagram showing:
        - Classes inferred from use cases
        - Relationships based on applied patterns
        - Pattern annotations
        """
        try:
            # Get all pattern applications for this project
            patterns = self.db.query(PatternApplication).filter(
                PatternApplication.project_id == project_id
            ).all()
            
            if not patterns:
                self.log_info("No patterns applied, skipping class diagram generation")
                return None
            
            # Get use cases for context
            use_cases = self.db.query(UseCase).filter(UseCase.project_id == project_id).all()
            
            # Create directory for artifacts
            output_dir = f"output/project_{project_id}"
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate PlantUML class diagram
            plantuml_content = self._generate_plantuml_class_diagram(use_cases, patterns)
            
            file_path = os.path.join(output_dir, "class_diagram.puml")
            with open(file_path, 'w') as f:
                f.write(plantuml_content)
            
            # Ensure agent has project context
            self.project_id = project_id
            
            # Create artifact record
            artifact = self.save_artifact(
                filepath=file_path,
                content=plantuml_content,
                artifact_type=ArtifactType.CLASS_DIAGRAM,
                metadata={
                    "name": "Class Diagram (Pattern-Based)",
                    "patterns_count": len(patterns),
                    "use_cases_count": len(use_cases)
                }
            )
            
            self.log_info(f"Generated class diagram at {file_path}")
            return artifact
            
        except Exception as e:
            self.log_warning(f"Error generating class diagram: {e}")
            return None

    def _generate_plantuml_class_diagram(
        self, 
        use_cases: List[UseCase], 
        patterns: List[PatternApplication]
    ) -> str:
        """
        Generate PlantUML content for a class diagram based on use cases and patterns.
        """
        # Simple heuristic: create classes based on use case actors and patterns
        classes = set()
        relationships = []
        
        # Add classes for actors
        for uc in use_cases:
            if uc.actor:
                classes.add(uc.actor.name)
        
        # Add classes inferred from patterns
        for pattern in patterns:
            # Extract potential class names from pattern descriptions
            desc = pattern.description.lower()
            if "controller" in desc or pattern.pattern_name.lower() == "controller":
                classes.add("SystemController")
            if "factory" in desc or "creator" in desc:
                classes.add("ObjectFactory")
            if "expert" in desc:
                # Try to infer expert class from use case
                uc = next((uc for uc in use_cases if uc.id == pattern.use_case_id), None)
                if uc and uc.actor:
                    classes.add(f"{uc.actor.name}Expert")
        
        # Create PlantUML content
        lines = [
            "@startuml",
            "title Class Diagram (Pattern-Based)",
            "skinparam classAttributeIconSize 0",
            "",
        ]
        
        # Add classes
        for class_name in sorted(classes):
            lines.append(f"class {class_name} {{")
            lines.append(f"  // Responsibilities based on patterns")
            lines.append("}")
            lines.append("")
        
        # Add simple relationships (just associations for now)
        if len(classes) > 1:
            class_list = sorted(classes)
            for i in range(len(class_list) - 1):
                lines.append(f"{class_list[i]} --> {class_list[i+1]} : uses")
        
        lines.append("")
        lines.append("note top of SystemController")
        lines.append("Controller pattern applied")
        lines.append("end note")
        lines.append("")
        lines.append("@enduml")
        
        return "\n".join(lines)