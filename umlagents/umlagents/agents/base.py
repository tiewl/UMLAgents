"""
Enhanced base agent with SQLite audit logging and Anthropic API integration.
Compatible with dice-game-agents pattern but adds Larman methodology alignment.
"""
import os
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from ..utils.events import (
    publish_agent_activity,
    publish_artifact_generated,
    publish_api_call,
    publish_agent_status
)

from ..db.models import (
    Base, Project, Actor, UseCase, DesignDecision, PatternApplication, 
    Artifact, AuditLog, AgentRole, ArtifactType, init_db, get_session
)


class BaseAgent:
    """
    Base agent with DeepSeek API integration and SQLite audit logging.
    
    Extends the dice-game-agents pattern with:
    - SQLite audit trail for regulatory compliance
    - Pattern application tracking (GRASP/GoF)
    - Larman methodology alignment
    - Artifact versioning with content hashing
    """
    
    def __init__(
        self, 
        name: str, 
        system_prompt: str,
        agent_role: AgentRole,
        db_session: Optional[Session] = None,
        project_id: Optional[int] = None
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.agent_role = agent_role
        self.project_id = project_id
        
        # Anthropic API configuration
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        # Allow per-agent model override via env, e.g. UMLAGENTS_TESTERAGENT_MODEL=claude-haiku-4-5-20251001
        env_key = f"UMLAGENTS_{name.upper()}_MODEL"
        self._model = os.getenv(env_key) or os.getenv("UMLAGENTS_DEFAULT_MODEL", "claude-sonnet-4-6")

        if not self.api_key or self.api_key.startswith("your_"):
            print(f"[WARNING] ANTHROPIC_API_KEY not set. AI features will be disabled.")
            self.api_key = None
        
        # Database session
        if db_session:
            self.db = db_session
            self.owns_db = False
        else:
            engine = init_db("umlagents.db")
            self.db = get_session(engine)
            self.owns_db = True
    
    def call_deepseek(
        self,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Call Anthropic Claude API (drop-in replacement for the DeepSeek caller)."""
        import anthropic

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured. Cannot call AI API.")

        self._log_activity(
            activity="api_call_start",
            details={
                "prompt_length": len(user_prompt),
                "temperature": temperature,
                "max_tokens": max_tokens,
                "metadata": metadata or {},
            },
        )

        print(f"[{self.name}] Calling Anthropic {self._model} ...")

        try:
            start_time = datetime.now()
            client = anthropic.Anthropic(api_key=self.api_key, timeout=180.0)
            message = client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=temperature,
            )
            content = message.content[0].text
            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)

            print(f"[{self.name}] Response received ({len(content)} chars, {elapsed_ms}ms)")

            self._log_activity(
                activity="api_call_success",
                details={
                    "response_length": len(content),
                    "elapsed_ms": elapsed_ms,
                    "model": self._model,
                    "usage": {
                        "input_tokens": message.usage.input_tokens,
                        "output_tokens": message.usage.output_tokens,
                    },
                },
            )
            return content

        except Exception as e:
            self._log_activity(
                activity="api_call_failed",
                details={"error": str(e), "error_type": type(e).__name__},
            )
            # Re-raise credit errors as a distinct type so the orchestrator can halt
            if "credit balance is too low" in str(e).lower() or "billing" in str(e).lower():
                raise InsufficientCreditsError(str(e)) from e
            raise


    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute agent's task. Must be overridden by subclasses.
        
        Args:
            context: Dictionary containing outputs from previous agents.
            
        Returns:
            Dictionary with this agent's outputs added.
        """
        raise NotImplementedError("Subclasses must implement the run() method.")
    
    def save_artifact(
        self, 
        filepath: str, 
        content: str, 
        artifact_type: ArtifactType,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Artifact]:
        """
        Save artifact to file and record in database with content hash.
        
        Args:
            filepath: Path to save the file
            content: File content
            artifact_type: Type of artifact
            metadata: Additional metadata
            
        Returns:
            Artifact object if saved with project context, else None
        """
        import os
        
        # Create directories if needed
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Save to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Calculate content hash
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        artifact = None
        
        # Record in database if we have a project
        if self.project_id:
            artifact = Artifact(
                project_id=self.project_id,
                artifact_type=artifact_type,
                name=os.path.basename(filepath),
                file_path=filepath,
                content_hash=content_hash,
                generated_by_agent=self.agent_role,
                generation_time_ms=0,  # Would need timing instrumentation
                artifact_metadata=metadata or {}
            )
            self.db.add(artifact)
            self.db.commit()
        
        # Log activity
        self._log_activity(
            activity="artifact_generated",
            details={
                "filepath": filepath,
                "artifact_type": artifact_type.value,
                "content_length": len(content),
                "content_hash": content_hash,
                "metadata": metadata or {}
            }
        )
        
        print(f"  -> Saved: {filepath} (hash: {content_hash[:8]}...)")
        return artifact
    
    def _log_activity(self, activity: str, details: Dict[str, Any]) -> None:
        """
        Log activity to audit trail and publish event.
        
        Args:
            activity: Activity description
            details: Structured details
        """
        # Publish event regardless of project context (for monitoring)
        try:
            if activity in ["api_call_start", "api_call_success", "api_call_failed"]:
                status = activity.replace("api_call_", "")
                publish_api_call(
                    agent_name=self.name,
                    status=status,
                    endpoint=details.get("endpoint", "/v1/chat/completions"),
                    duration_ms=details.get("elapsed_ms"),
                    error=details.get("error"),
                    project_id=self.project_id
                )
            elif activity == "artifact_generated":
                publish_artifact_generated(
                    agent_name=self.name,
                    artifact_type=details.get("artifact_type", "unknown"),
                    filepath=details.get("filepath", ""),
                    project_id=self.project_id,
                    content_hash=details.get("content_hash"),
                    content_length=details.get("content_length")
                )
            elif activity == "project_created":
                # Project creation already handled in create_or_load_project
                pass
            
            # Always publish general agent activity
            publish_agent_activity(
                agent_name=self.name,
                activity=activity,
                project_id=self.project_id,
                details=details
            )
        except Exception as e:
            # Don't let event publishing break the agent
            print(f"[{self.name}] Warning: Failed to publish event: {e}")
        
        # Original audit logging (requires project context)
        if not self.project_id:
            return  # Can't log to audit trail without project context
            
        audit_log = AuditLog(
            project_id=self.project_id,
            agent_role=self.agent_role,
            activity=activity,
            details=details,
            timestamp=datetime.now()
        )
        
        self.db.add(audit_log)
        self.db.commit()
    
    def log_activity(self, action: str, details: Dict[str, Any]) -> None:
        """
        Public wrapper for _log_activity.
        """
        self._log_activity(action, details)
    
    def log_info(self, message: str) -> None:
        """
        Log informational message.
        """
        print(f"[{self.name}] INFO: {message}")
    
    def log_warning(self, message: str) -> None:
        """
        Log warning message.
        """
        print(f"[{self.name}] WARNING: {message}")

    def create_or_load_project(
        self, 
        name: str, 
        domain: str, 
        description: str,
        regulatory_frameworks: Optional[list] = None
    ) -> int:
        """
        Create a new project or load existing one by name.
        
        Args:
            name: Project name
            domain: Project domain (e.g., "Healthcare", "Finance")
            description: Project description
            regulatory_frameworks: List of regulatory frameworks
            
        Returns:
            Project ID
        """
        # Check if project exists
        project = self.db.query(Project).filter_by(name=name).first()
        
        if project:
            print(f"[{self.name}] Loaded existing project: {name} (ID: {project.id})")
            self.project_id = project.id
            return project.id
        
        # Create new project
        project = Project(
            name=name,
            domain=domain,
            description=description,
            regulatory_frameworks=regulatory_frameworks or []
        )
        
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        
        self.project_id = project.id
        
        print(f"[{self.name}] Created new project: {name} (ID: {project.id})")
        
        # Log project creation
        self._log_activity(
            activity="project_created",
            details={
                "name": name,
                "domain": domain,
                "regulatory_frameworks": regulatory_frameworks or []
            }
        )
        
        return project.id
    
    def close(self):
        """Close database session if we own it."""
        if self.owns_db and self.db:
            self.db.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class InsufficientCreditsError(RuntimeError):
    """Raised when the Anthropic API key has no remaining credits."""