#!/usr/bin/env python3
"""Test orchestrator with Architect and Design agents (skip existing)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from umlagents.db.models import init_db, Project, Phase
from umlagents.agents.orchestrator_agent import OrchestratorAgent
from umlagents.agents.architect_agent import ArchitectAgent
from umlagents.agents.design_agent import DesignAgent
from sqlalchemy.orm import Session

def test_orchestrator_elaboration():
    db_path = "umlagents.db"
    engine = init_db(db_path)
    session = Session(engine)
    
    project = session.query(Project).filter_by(id=1).first()
    if not project:
        print("❌ Project not found")
        return
    
    print(f"Testing Orchestrator with project: {project.name}")
    print(f"Current phase: {project.current_phase.value}")
    
    # Create orchestrator
    orchestrator = OrchestratorAgent(db_session=session, project_id=project.id)
    
    # Run pipeline with Architect and Design agents, skip existing
    context = {
        'project_id': project.id,
        'agents_to_run': [ArchitectAgent, DesignAgent],
        'skip_existing': True,
        'halt_on_error': True
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
    
    for agent_exec in result['agents_executed']:
        print(f"  - {agent_exec['agent']}: {agent_exec['status']} ({agent_exec['time_ms']}ms)")
    
    session.close()
    return result['success']

if __name__ == "__main__":
    success = test_orchestrator_elaboration()
    sys.exit(0 if success else 1)