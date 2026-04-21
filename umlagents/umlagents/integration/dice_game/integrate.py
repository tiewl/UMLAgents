#!/usr/bin/env python3
"""
Integration module for dice‑game‑agents repository.
Runs the dice‑game‑agents SDLC pipeline and imports its outputs
into the UMLAgents database for comparison and audit trail.
"""
import os
import sys
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
sys.path.insert(0, '/home/picoclaw/.openclaw/workspace/dice-game-agents-ref')

from umlagents.db.models import (
    init_db, get_session, Project, Phase, AgentRole, ArtifactType,
    Artifact, AuditLog, Actor, UseCase, DesignDecision, PatternApplication
)

# ============================================================================
# Configuration
# ============================================================================

DICE_GAME_AGENTS_PATH = Path('/home/picoclaw/.openclaw/workspace/dice-game-agents-ref')
UMLAGENTS_DB_PATH = 'umlagents.db'

# ============================================================================
# Core Integration Functions
# ============================================================================

def check_dependencies() -> bool:
    """Check if dice‑game‑agents dependencies are satisfied."""
    try:
        from agents.base_agent import BaseAgent
        return True
    except ImportError as e:
        print(f"Import error: {e}")
        print("Make sure dice‑game‑agents repository is available at:")
        print(f"  {DICE_GAME_AGENTS_PATH}")
        return False

def check_api_key() -> bool:
    """Check if DEEPSEEK_API_KEY is set."""
    if 'DEEPSEEK_API_KEY' not in os.environ:
        print("ERROR: DEEPSEEK_API_KEY environment variable not set.")
        print("The dice‑game‑agents pipeline requires a DeepSeek API key.")
        print("Set it with:")
        print("  export DEEPSEEK_API_KEY='your_key_here'")
        return False
    return True

def run_dice_game_pipeline(output_dir: Path) -> Dict[str, Any]:
    """
    Run the dice‑game‑agents SDLC pipeline.
    Returns a dictionary with paths to generated artifacts.
    """
    print(f"Running dice‑game‑agents pipeline into {output_dir}")
    
    # Change to dice‑game‑agents directory
    original_cwd = os.getcwd()
    os.chdir(DICE_GAME_AGENTS_PATH)
    
    try:
        # Import the orchestrator
        sys.path.insert(0, str(DICE_GAME_AGENTS_PATH))
        from orchestrator import run_pipeline
        
        # Monkey‑patch the output directory
        import orchestrator as orig_module
        original_create_dirs = orig_module.create_output_dirs
        
        def patched_create_dirs():
            """Create directories in our custom output location."""
            dirs = [
                output_dir / "uml",
                output_dir / "code",
                output_dir / "deployment",
            ]
            for d in dirs:
                d.mkdir(parents=True, exist_ok=True)
                print(f"  [OK] {d}/")
        
        orig_module.create_output_dirs = patched_create_dirs
        
        # Also patch file saving in agents
        from agents.base_agent import BaseAgent
        original_save = BaseAgent.save_file
        
        def patched_save(self, filename: str, content: str):
            """Save files to our custom output directory."""
            path = output_dir / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
            print(f"  -> Saved: {path}")
        
        BaseAgent.save_file = patched_save
        
        # Run the pipeline
        run_pipeline()
        
        # Restore original functions
        orig_module.create_output_dirs = original_create_dirs
        BaseAgent.save_file = original_save
        
    except Exception as e:
        print(f"Pipeline execution failed: {e}")
        raise
    finally:
        os.chdir(original_cwd)
    
    # Collect generated artifacts
    artifacts = {}
    for category in ["uml", "code", "deployment"]:
        cat_dir = output_dir / category
        if cat_dir.exists():
            artifacts[category] = []
            for file_path in cat_dir.rglob("*"):
                if file_path.is_file():
                    artifacts[category].append(str(file_path.relative_to(output_dir)))
    
    return artifacts

def import_to_umlagents(output_dir: Path, project_id: int = None) -> int:
    """
    Import dice‑game‑agents outputs into UMLAgents database.
    Returns the project ID.
    """
    engine = init_db(UMLAGENTS_DB_PATH)
    session = get_session(engine)
    
    # Create a new project or use existing
    if project_id:
        project = session.query(Project).filter(Project.id == project_id).first()
        if not project:
            print(f"Project {project_id} not found, creating new project")
            project = create_new_project(session)
    else:
        project = create_new_project(session)
    
    # Import artifacts
    import_artifacts(session, project, output_dir)
    
    # Create audit logs
    log_import(session, project)
    
    session.commit()
    session.close()
    
    print(f"Imported dice‑game‑agents outputs into project {project.id}: {project.name}")
    return project.id

def create_new_project(session) -> Project:
    """Create a new project for dice‑game‑agents integration."""
    project = Project(
        name="Dice Game (dice‑game‑agents pipeline)",
        domain="Gaming",
        description="Generated by dice‑game‑agents SDLC pipeline via integration module",
        current_phase=Phase.TRANSITION  # Pipeline completes all phases
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project

def import_artifacts(session, project: Project, output_dir: Path):
    """Import generated files as artifacts."""
    artifact_type_map = {
        '.puml': ArtifactType.DOMAIN_DIAGRAM,
        '.md': ArtifactType.USE_CASE_YAML,  # Actually use case docs
        '.py': ArtifactType.SOURCE_CODE,
        '.txt': ArtifactType.UNIT_TESTS,    # Test files
        'Dockerfile': ArtifactType.DOCKERFILE,
        'docker-compose': ArtifactType.DEPLOYMENT_CONFIG,
        'deployment': ArtifactType.DEPLOYMENT_CONFIG,
    }
    
    for file_path in output_dir.rglob("*"):
        if not file_path.is_file():
            continue
        
        # Determine artifact type
        artifact_type = ArtifactType.DEPLOYMENT_CONFIG  # default
        for suffix, atype in artifact_type_map.items():
            if suffix in file_path.name or suffix in str(file_path):
                artifact_type = atype
                break
        
        # Read content
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            content_hash = hash(content)  # Simple hash for demo
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}")
            continue
        
        # Create artifact record
        artifact = Artifact(
            project_id=project.id,
            artifact_type=artifact_type,
            name=file_path.name,
            file_path=str(file_path.relative_to(output_dir)),
            content_hash=str(content_hash),
            generated_by_agent=AgentRole.DEVELOPER,  # Approximate mapping
            generation_time_ms=0,
            artifact_metadata={
                "source": "dice‑game‑agents",
                "original_path": str(file_path),
                "imported_at": datetime.now().isoformat()
            }
        )
        session.add(artifact)
        print(f"  Imported: {file_path.name} ({artifact_type.value})")

def log_import(session, project: Project):
    """Create audit log entries for the import."""
    log = AuditLog(
        project_id=project.id,
        agent_role=AgentRole.ORCHESTRATOR,
        activity="dice_game_agents_integration",
        details={
            "action": "import_pipeline_outputs",
            "timestamp": datetime.now().isoformat(),
            "pipeline_version": "1.0",
            "artifacts_count": session.query(Artifact).filter(Artifact.project_id == project.id).count()
        }
    )
    session.add(log)

def compare_projects(project_id_uml: int, project_id_dice: int):
    """Compare artifacts between UMLAgents and dice‑game‑agents projects."""
    engine = init_db(UMLAGENTS_DB_PATH)
    session = get_session(engine)
    
    uml_artifacts = session.query(Artifact).filter(Artifact.project_id == project_id_uml).all()
    dice_artifacts = session.query(Artifact).filter(Artifact.project_id == project_id_dice).all()
    
    print("\n" + "="*60)
    print("COMPARISON: UMLAgents vs dice‑game‑agents")
    print("="*60)
    print(f"UMLAgents project {project_id_uml}: {len(uml_artifacts)} artifacts")
    print(f"dice‑game‑agents project {project_id_dice}: {len(dice_artifacts)} artifacts")
    
    # Group by type
    uml_by_type = {}
    dice_by_type = {}
    
    for a in uml_artifacts:
        ut = a.artifact_type.value
        uml_by_type[ut] = uml_by_type.get(ut, 0) + 1
    
    for a in dice_artifacts:
        dt = a.artifact_type.value
        dice_by_type[dt] = dice_by_type.get(dt, 0) + 1
    
    print("\nArtifact type breakdown:")
    print(f"{'Type':<25} {'UMLAgents':<12} {'dice‑game‑agents':<12}")
    print("-" * 50)
    all_types = set(list(uml_by_type.keys()) + list(dice_by_type.keys()))
    for t in sorted(all_types):
        print(f"{t:<25} {uml_by_type.get(t, 0):<12} {dice_by_type.get(t, 0):<12}")
    
    session.close()

# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    """Main integration workflow."""
    print("="*60)
    print("UMLAgents – dice‑game‑agents Integration")
    print("="*60)
    
    # Check prerequisites
    if not check_dependencies():
        sys.exit(1)
    
    if not check_api_key():
        print("\nNote: Without API key, pipeline will fail.")
        print("Continue anyway? (y/N)")
        if input().strip().lower() != 'y':
            sys.exit(0)
    
    # Create temporary output directory
    with tempfile.TemporaryDirectory(prefix="dice_game_agents_") as tmpdir:
        output_dir = Path(tmpdir)
        print(f"Using temporary directory: {output_dir}")
        
        try:
            # Run pipeline
            artifacts = run_dice_game_pipeline(output_dir)
            print(f"Pipeline completed. Generated {sum(len(v) for v in artifacts.values())} artifacts.")
            
            # Import into UMLAgents
            project_id = import_to_umlagents(output_dir)
            
            # Compare with existing UMLAgents dice game project (ID 1)
            compare_projects(1, project_id)
            
            print("\n✅ Integration complete!")
            print(f"   dice‑game‑agents outputs imported as project {project_id}")
            print(f"   Temporary files cleaned up.")
            
        except Exception as e:
            print(f"\n❌ Integration failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    main()