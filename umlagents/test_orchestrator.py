#!/usr/bin/env python3
"""
Test the OrchestratorAgent with BA and Architect agents only.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from umlagents.db.models import init_db, Project, Phase, AgentRole
from umlagents.agents.orchestrator_agent import OrchestratorAgent
from umlagents.agents.ba_agent import BAAgent
from umlagents.agents.architect_agent import ArchitectAgent
from sqlalchemy.orm import Session

def test_orchestrator():
    db_path = "umlagents.db"
    engine = init_db(db_path)
    session = Session(engine)
    
    # Get project (should be ID 1)
    project = session.query(Project).filter_by(id=1).first()
    if not project:
        print("❌ Project not found")
        return
    
    print(f"Testing Orchestrator with project: {project.name}")
    print(f"Current phase: {project.current_phase.value}")
    
    # Create orchestrator
    orchestrator = OrchestratorAgent(db_session=session, project_id=project.id)
    
    # Run pipeline with just BA and Architect agents
    context = {
        'project_id': project.id,
        'agents_to_run': [BAAgent, ArchitectAgent],
        'halt_on_error': True,
        'skip_existing': True  # Skip if artifacts already exist
    }
    
    print("\n[Test] Starting pipeline...")
    result = orchestrator.run(context)
    
    print(f"\n[Test] Pipeline completed:")
    print(f"  Success: {result['success']}")
    print(f"  Agents executed: {len(result['agents_executed'])}")
    print(f"  Total time: {result['total_time_ms']}ms")
    print(f"  Final phase: {project.current_phase.value}")
    
    if result['errors']:
        print(f"  Errors: {result['errors']}")
    
    # Print agent details
    for agent_exec in result['agents_executed']:
        print(f"  - {agent_exec['agent']}: {agent_exec['status']} ({agent_exec['time_ms']}ms)")
    
    session.close()
    return result['success']

if __name__ == "__main__":
    success = test_orchestrator()
    sys.exit(0 if success else 1)