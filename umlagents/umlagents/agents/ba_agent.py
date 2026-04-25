"""
Business Analyst (BA) Agent - Requirement elicitation and validation.
Aligned with Larman's OOA/OOD methodology.

Supports two modes:
1. YAML load: Load and validate existing YAML use case specification
2. Interactive: Ask Larman-style questions to build YAML specification
"""
import os
import sys
import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseAgent
from ..db.models import AgentRole, Project, Actor, UseCase, ArtifactType
from ..utils.validation import YAMLValidator, ValidationError


class BAAgent(BaseAgent):
    """
    Business Analyst agent for requirement elicitation and validation.
    
    Key responsibilities (Larman):
    - Identify actors and their goals
    - Define use cases with pre/post conditions
    - Capture extension scenarios
    - Validate completeness and consistency
    """
    
    def __init__(self, db_session: Optional[Session] = None, project_id: Optional[int] = None):
        system_prompt = """You are a senior business analyst following Craig Larman's 
        Object-Oriented Analysis and Design methodology. Your expertise includes:
        
        1. Identifying system actors and their goals
        2. Defining precise use cases with clear preconditions and postconditions
        3. Capturing main success scenarios and extension scenarios
        4. Applying GRASP principles for responsibility assignment
        5. Ensuring requirements are testable and traceable
        
        You think in terms of contracts (pre/post conditions) and always seek specificity."""
        
        super().__init__(
            name="BAAgent",
            system_prompt=system_prompt,
            agent_role=AgentRole.BA,
            db_session=db_session,
            project_id=project_id
        )
        
        # Larman-style question bank for interactive mode
        self.question_bank = [
            # Project context
            ("project_name", "What is the name of this project?", "text"),
            ("project_domain", "What domain does this project belong to? (e.g., Healthcare, Finance, Gaming)", "text"),
            ("project_description", "Describe the project in 1-2 sentences.", "text"),
            
            # Regulatory context
            ("regulatory_frameworks", "Are there any regulatory frameworks to consider? (e.g., GDPR, SOC2, HIPAA). Enter comma-separated or 'none'.", "list"),
            
            # Actor identification (Larman: "Who interacts with the system?")
            ("actors", "Who are the actors (users or external systems) that interact with the system? For each actor: 'name: description' (one per line)", "multiline"),
            
            # Use case elicitation (Larman: "What are the actors' goals?")
            ("use_cases", "What are the main things actors need to do with the system? List use case titles (one per line)", "multiline"),
        ]
        
        # State for interactive mode
        self.interactive_state = {}
        self.current_question_idx = 0
    
    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run BA agent. Supports two modes based on context:
        
        1. If context has 'yaml_path': load and validate YAML
        2. If context has 'interactive': True: run interactive questionnaire
        3. If context has 'prompt': use natural language prompt (dice-game-agents compatibility)
        4. If skip_existing=True and use cases exist: skip requirement elicitation
        
        Args:
            context: Dictionary with input parameters
            
        Returns:
            Updated context with requirements
        """
        mode = self._determine_mode(context)
        
        if mode == "yaml":
            return self._run_yaml_mode(context)
        elif mode == "interactive":
            return self._run_interactive_mode(context)
        elif mode == "prompt":
            return self._run_prompt_mode(context)
        elif mode == "skip":
            return self._run_skip_mode(context)
        else:
            raise ValueError(f"Unknown mode: {mode}")
    
    def _determine_mode(self, context: Dict[str, Any]) -> str:
        """Determine which mode to run based on context."""
        # Check if we should skip because requirements already exist
        if context.get("skip_existing", False) and self.project_id:
            # Check if use cases already exist for this project
            existing_use_cases = self.db.query(UseCase).filter(
                UseCase.project_id == self.project_id
            ).count()
            if existing_use_cases > 0:
                print(f"[{self.name}] Skipping BA - {existing_use_cases} use cases already exist")
                return "skip"
            else:
                # No use cases exist but skip_existing is True
                # This is an error condition - requirements should already be loaded
                raise ValueError(
                    f"No use cases found for project {self.project_id}. "
                    "Requirements must be loaded via YAML before running pipeline from web UI."
                )
        
        if "yaml_path" in context:
            return "yaml"
        elif context.get("interactive"):
            return "interactive"
        elif "prompt" in context:
            return "prompt"
        elif "project_description" in context:  # dice-game-agents pattern
            return "prompt"
        else:
            # Default to interactive if no other mode specified
            return "interactive"
    
    def _run_skip_mode(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Skip requirement elicitation because use cases already exist."""
        print(f"[{self.name}] Skipping requirement elicitation - use cases already exist")
        # Ensure project_id is in context
        if self.project_id:
            context['project_id'] = self.project_id
        return context

    def _run_yaml_mode(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load and validate YAML use case specification.
        
        Args:
            context: Must contain 'yaml_path' pointing to YAML file
            
        Returns:
            Context with validated requirements and project_id
        """
        yaml_path = context["yaml_path"]
        
        print(f"\n{'='*60}")
        print(f"[{self.name}] Loading YAML specification: {yaml_path}")
        print(f"{'='*60}")
        
        # Load and validate YAML using centralized validator
        try:
            yaml_data = YAMLValidator.validate_file(Path(yaml_path))
            print(f"[{self.name}] ✓ YAML validation passed")
        except ValidationError as e:
            print(f"[{self.name}] ❌ YAML validation failed: {e.message}")
            if e.field:
                print(f"       Field: {e.field}")
            raise
        
        # Create or load project in database
        project_id = self.create_or_load_project(
            name=yaml_data["project"]["name"],
            domain=yaml_data["project"]["domain"],
            description=yaml_data["project"]["description"],
            regulatory_frameworks=yaml_data["project"].get("regulatory_frameworks", [])
        )
        
        # Save actors to database
        actors = []
        for actor_data in yaml_data.get("actors", []):
            actor = Actor(
                project_id=project_id,
                name=actor_data["name"],
                description=actor_data["description"],
                role=actor_data.get("role", "EndUser")
            )
            self.db.add(actor)
            actors.append(actor)
        
        self.db.commit()
        
        # Save use cases to database
        use_cases = []
        for uc_data in yaml_data.get("use_cases", []):
            # Find actor ID
            actor_id = None
            if "actor" in uc_data:
                actor = next((a for a in actors if a.name == uc_data["actor"]), None)
                if actor:
                    actor_id = actor.id
            
            use_case = UseCase(
                project_id=project_id,
                actor_id=actor_id,
                uc_id=uc_data["id"],
                title=uc_data["title"],
                priority=uc_data.get("priority", 2),
                pre_conditions=uc_data.get("pre_conditions", []),
                success_scenario=uc_data.get("success_scenario", []),
                extension_scenarios=uc_data.get("extension_scenarios", []),
                post_conditions=uc_data.get("post_conditions", []),
                regulatory_requirements=uc_data.get("regulatory_requirements", []),
                uat_criteria=uc_data.get("uat_criteria", [])
            )
            self.db.add(use_case)
            use_cases.append(use_case)
        
        self.db.commit()
        
        # Save YAML as artifact
        yaml_content = yaml.dump(yaml_data, default_flow_style=False)
        self.save_artifact(
            filepath=f"output/{project_id}/requirements.yaml",
            content=yaml_content,
            artifact_type=ArtifactType.USE_CASE_YAML,
            metadata={
                "source": "yaml_file",
                "yaml_path": yaml_path,
                "use_case_count": len(use_cases),
                "actor_count": len(actors)
            }
        )
        
        # Log completion
        self._log_activity(
            activity="requirements_loaded_from_yaml",
            details={
                "yaml_path": yaml_path,
                "project_id": project_id,
                "actor_count": len(actors),
                "use_case_count": len(use_cases)
            }
        )
        
        print(f"\n[{self.name}] Successfully loaded:")
        print(f"  - Project: {yaml_data['project']['name']}")
        print(f"  - Actors: {len(actors)}")
        print(f"  - Use cases: {len(use_cases)}")
        print(f"  - Project ID: {project_id}")
        
        # Update context
        context["project_id"] = project_id
        context["requirements_yaml"] = yaml_data
        context["actors"] = [{"id": a.id, "name": a.name} for a in actors]
        context["use_cases"] = [{"id": uc.id, "uc_id": uc.uc_id, "title": uc.title} for uc in use_cases]
        
        return context
    
    def _get_input(self, prompt: str = "> ") -> str:
        """
        Get input from user with proper error handling.
        
        Args:
            prompt: Input prompt
            
        Returns:
            User input string
            
        Raises:
            RuntimeError: If EOF is encountered (Ctrl+D/Ctrl+Z)
        """
        try:
            return input(prompt).strip()
        except EOFError:
            raise RuntimeError(
                "\nEOF encountered. Interactive session cancelled.\n"
                "If running in a terminal, you may have pressed Ctrl+D (Unix) or Ctrl+Z (Windows).\n"
                "If running through an automation tool, interactive mode is not supported.\n"
                "Use YAML requirements file instead: umlagents load-yaml <file.yaml>"
            )
        except KeyboardInterrupt:
            raise RuntimeError("\nInteractive session cancelled by user.")
    
    def _run_interactive_mode(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interactive questionnaire to elicit requirements.
        
        Args:
            context: May contain partial information to pre-populate
            
        Returns:
            Context with elicited requirements
        """
        # Check if we have an interactive terminal
        if not sys.stdin.isatty():
            raise RuntimeError(
                "Interactive mode requires a terminal with stdin.\n"
                "Please run this command in a terminal (not through a wrapper or automation tool).\n"
                "Alternative: Use YAML requirements file instead: umlagents load-yaml <file.yaml>"
            )
        
        print(f"\n{'='*60}")
        print(f"[{self.name}] Starting interactive requirement elicitation")
        print(f"[{self.name}] Following Larman's OOA/OOD methodology")
        print(f"{'='*60}")
        
        # Initialize with any existing context
        self.interactive_state = context.copy()
        
        # Run through question bank
        for i, (key, question, qtype) in enumerate(self.question_bank):
            if key in self.interactive_state:
                continue  # Already answered in context
                
            print(f"\nQ{i+1}: {question}")
            
            if qtype == "text":
                answer = self._get_input("> ")  # Handles EOFError and KeyboardInterrupt
                while not answer:
                    print("Please provide an answer.")
                    answer = self._get_input("> ")
                self.interactive_state[key] = answer
                
            elif qtype == "list":
                answer = self._get_input("> ")
                if answer.lower() == "none":
                    self.interactive_state[key] = []
                else:
                    self.interactive_state[key] = [item.strip() for item in answer.split(",") if item.strip()]
                    
            elif qtype == "multiline":
                print("(Enter empty line when done)")
                lines = []
                while True:
                    line = self._get_input("> ")
                    if not line:
                        break
                    lines.append(line)
                self.interactive_state[key] = lines
        
        # Process collected information
        return self._process_interactive_answers(context)
    
    def _run_prompt_mode(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Natural language prompt mode (dice-game-agents compatibility).
        
        Args:
            context: Must contain 'prompt' or 'project_description'
            
        Returns:
            Context with generated requirements
        """
        prompt = context.get("prompt") or context.get("project_description", "")
        
        print(f"\n{'='*60}")
        print(f"[{self.name}] Generating requirements from natural language")
        print(f"{'='*60}")
        
        # Enhanced prompt for Larman-style analysis
        enhanced_prompt = f"""Analyze the following project description using Craig Larman's 
        Object-Oriented Analysis and Design methodology:

        {prompt}

        Please provide:

        1. **Actors**: Who interacts with the system? Include primary and secondary actors.
        2. **Use Cases**: For each actor's key goals, define use cases with:
           - Preconditions (what must be true before)
           - Main success scenario (numbered steps)
           - Extension scenarios (alternative/error flows)
           - Postconditions (what will be true after)
        3. **Domain Vocabulary**: Key terms and their definitions.
        4. **Initial Domain Model**: Key concepts and their relationships.

        Format your response clearly with markdown headers."""
        
        response = self.call_deepseek(enhanced_prompt)
        
        # Save requirements document
        self.save_artifact(
            filepath="output/requirements.md",
            content=response,
            artifact_type=ArtifactType.USE_CASE_YAML,  # Using this as closest match
            metadata={
                "source": "natural_language_prompt",
                "prompt_length": len(prompt)
            }
        )
        
        # Extract potential YAML structure (simplistic - will be enhanced)
        yaml_data = self._extract_yaml_from_response(response, prompt)
        
        # Update context
        context["requirements_markdown"] = response
        context["requirements_yaml"] = yaml_data
        
        # Log completion
        self._log_activity(
            activity="requirements_generated_from_prompt",
            details={
                "prompt_length": len(prompt),
                "response_length": len(response)
            }
        )
        
        return context
    
    def _validate_yaml_structure(self, yaml_data: Dict[str, Any]) -> None:
        """
        Validate YAML structure against UMLAgents schema.
        Uses the centralized YAMLValidator for consistent validation.
        """
        # Note: This method is kept for backward compatibility
        # The actual validation now happens in _run_yaml_mode
        pass
    
    def _process_interactive_answers(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Process interactive answers into structured requirements."""
        # This is a simplified implementation
        # In full version, would ask follow-up questions for each use case
        
        print(f"\n[{self.name}] Processing interactive answers...")
        
        # Create project in database
        project_id = self.create_or_load_project(
            name=self.interactive_state["project_name"],
            domain=self.interactive_state["project_domain"],
            description=self.interactive_state["project_description"],
            regulatory_frameworks=self.interactive_state.get("regulatory_frameworks", [])
        )
        
        # Create simple YAML structure
        yaml_data = {
            "project": {
                "name": self.interactive_state["project_name"],
                "domain": self.interactive_state["project_domain"],
                "description": self.interactive_state["project_description"],
                "regulatory_frameworks": self.interactive_state.get("regulatory_frameworks", [])
            },
            "actors": [],
            "use_cases": []
        }
        
        # Parse actors
        actor_lines = self.interactive_state.get("actors", [])
        for line in actor_lines:
            if ":" in line:
                name, desc = line.split(":", 1)
                yaml_data["actors"].append({
                    "name": name.strip(),
                    "description": desc.strip(),
                    "role": "EndUser"  # Default
                })
        
        # Parse use case titles
        uc_lines = self.interactive_state.get("use_cases", [])
        for i, title in enumerate(uc_lines):
            yaml_data["use_cases"].append({
                "id": f"UC{i+1}",
                "title": title,
                "actor": yaml_data["actors"][0]["name"] if yaml_data["actors"] else "System",
                "priority": 2,
                "pre_conditions": ["To be defined"],
                "success_scenario": ["To be defined"],
                "post_conditions": ["To be defined"],
                "uat_criteria": ["To be defined"]
            })
        
        # Save YAML
        yaml_content = yaml.dump(yaml_data, default_flow_style=False)
        self.save_artifact(
            filepath=f"output/{project_id}/requirements_interactive.yaml",
            content=yaml_content,
            artifact_type=ArtifactType.USE_CASE_YAML,
            metadata={
                "source": "interactive_questionnaire",
                "actor_count": len(yaml_data["actors"]),
                "use_case_count": len(yaml_data["use_cases"])
            }
        )
        
        # Update context
        context["project_id"] = project_id
        context["requirements_yaml"] = yaml_data
        context["interactive_answers"] = self.interactive_state
        
        print(f"\n[{self.name}] Interactive elicitation complete:")
        print(f"  - Generated {len(yaml_data['use_cases'])} use case(s)")
        print(f"  - Project ID: {project_id}")
        print(f"  - Next: Run detailed use case elaboration")
        
        return context
    
    def _extract_yaml_from_response(self, response: str, original_prompt: str) -> Dict[str, Any]:
        """Extract structured YAML from natural language response."""
        # Simplified extraction - in full version would use LLM to structure
        return {
            "project": {
                "name": "Generated from prompt",
                "domain": "To be determined",
                "description": original_prompt[:200] + "...",
                "regulatory_frameworks": []
            },
            "actors": [
                {
                    "name": "User",
                    "description": "Primary user of the system",
                    "role": "EndUser"
                }
            ],
            "use_cases": [
                {
                    "id": "UC1",
                    "title": "Initial use case",
                    "actor": "User",
                    "priority": 1,
                    "pre_conditions": ["System is available"],
                    "success_scenario": ["User interacts with system"],
                    "post_conditions": ["Task completed"],
                    "uat_criteria": ["User can complete the task"]
                }
            ]
        }