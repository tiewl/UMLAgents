"""
Enhanced base agent with SQLite audit logging and DeepSeek API integration.
Compatible with dice-game-agents pattern but adds Larman methodology alignment.
"""
import os
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

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
        
        # DeepSeek API configuration (compatible with dice-game-agents)
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        
        if not self.api_key or self.api_key == "your_deepseek_api_key_here":
            raise ValueError(
                "DEEPSEEK_API_KEY not set. Please set DEEPSEEK_API_KEY environment variable."
            )
        
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
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Send prompt to DeepSeek API with audit logging.
        
        Args:
            user_prompt: The user prompt
            temperature: Creativity control (0.0-1.0)
            max_tokens: Maximum response length
            metadata: Additional metadata for audit log
            
        Returns:
            API response text
        """
        import requests
        
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        # Log API call start
        self._log_activity(
            activity="api_call_start",
            details={
                "prompt_length": len(user_prompt),
                "temperature": temperature,
                "max_tokens": max_tokens,
                "metadata": metadata or {}
            }
        )
        
        print(f"\n{'='*60}")
        print(f"[{self.name}] Sending request to DeepSeek API...")
        print(f"{'='*60}")
        
        try:
            start_time = datetime.now()
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            end_time = datetime.now()
            
            elapsed_ms = int((end_time - start_time).total_seconds() * 1000)
            
            print(f"[{self.name}] Response received ({len(content)} chars, {elapsed_ms}ms)")
            
            # Log API call success
            self._log_activity(
                activity="api_call_success",
                details={
                    "response_length": len(content),
                    "elapsed_ms": elapsed_ms,
                    "model": data.get("model", "unknown"),
                    "usage": data.get("usage", {})
                }
            )
            
            return content
            
        except Exception as e:
            # Log API call failure
            self._log_activity(
                activity="api_call_failed",
                details={
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
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
    ) -> None:
        """
        Save artifact to file and record in database with content hash.
        
        Args:
            filepath: Path to save the file
            content: File content
            artifact_type: Type of artifact
            metadata: Additional metadata
        """
        import os
        
        # Create directories if needed
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        # Save to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Calculate content hash
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
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
                metadata=metadata or {}
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
    
    def _log_activity(self, activity: str, details: Dict[str, Any]) -> None:
        """
        Log activity to audit trail.
        
        Args:
            activity: Activity description
            details: Structured details
        """
        if not self.project_id:
            return  # Can't log without project context
            
        audit_log = AuditLog(
            project_id=self.project_id,
            agent_role=self.agent_role,
            activity=activity,
            details=details,
            timestamp=datetime.now()
        )
        
        self.db.add(audit_log)
        self.db.commit()
    
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