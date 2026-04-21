#!/usr/bin/env python3
"""
Test Week 3 agents: Developer, Tester, Deployer
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

from umlagents.db.models import init_db, Project, Phase
from sqlalchemy.orm import Session

def test_developer():
    """Test DeveloperAgent"""
    print("=== Testing DeveloperAgent ===")
    from umlagents.agents.developer_agent import DeveloperAgent
    
    engine = init_db('umlagents.db')
    session = Session(engine)
    
    try:
        project = session.query(Project).filter_by(id=1).first()
        if not project:
            print("❌ Project 1 not found")
            return False
        
        agent = DeveloperAgent(db_session=session, project_id=project.id)
        context = {'project_id': project.id, 'skip_existing': False}
        
        result = agent.run(context)
        print(f"✅ Generated {len(result.get('generated_files', []))} source files")
        print(f"   Files: {result.get('code_files', [])}")
        
        # Check artifacts in DB
        from umlagents.db.models import Artifact, ArtifactType
        artifacts = session.query(Artifact).filter(
            Artifact.project_id == project.id,
            Artifact.artifact_type == ArtifactType.SOURCE_CODE
        ).all()
        print(f"   Source code artifacts: {len(artifacts)}")
        
        for art in artifacts:
            print(f"     - {art.name}: {art.file_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ DeveloperAgent error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

def test_tester():
    """Test TesterAgent"""
    print("\n=== Testing TesterAgent ===")
    from umlagents.agents.tester_agent import TesterAgent
    
    engine = init_db('umlagents.db')
    session = Session(engine)
    
    try:
        project = session.query(Project).filter_by(id=1).first()
        if not project:
            print("❌ Project 1 not found")
            return False
        
        agent = TesterAgent(db_session=session, project_id=project.id)
        context = {'project_id': project.id, 'skip_existing': False}
        
        result = agent.run(context)
        print(f"✅ Generated {len(result.get('generated_tests', []))} test files")
        print(f"   Files: {result.get('test_files', [])}")
        
        # Check artifacts in DB
        from umlagents.db.models import Artifact, ArtifactType
        artifacts = session.query(Artifact).filter(
            Artifact.project_id == project.id,
            Artifact.artifact_type.in_([ArtifactType.UNIT_TESTS, ArtifactType.INTEGRATION_TESTS, ArtifactType.UAT_CHECKLIST])
        ).all()
        print(f"   Test artifacts: {len(artifacts)}")
        
        for art in artifacts:
            print(f"     - {art.name}: {art.file_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ TesterAgent error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

def test_deployer():
    """Test DeployerAgent"""
    print("\n=== Testing DeployerAgent ===")
    from umlagents.agents.deployer_agent import DeployerAgent
    
    engine = init_db('umlagents.db')
    session = Session(engine)
    
    try:
        project = session.query(Project).filter_by(id=1).first()
        if not project:
            print("❌ Project 1 not found")
            return False
        
        agent = DeployerAgent(db_session=session, project_id=project.id)
        context = {'project_id': project.id, 'skip_existing': False}
        
        result = agent.run(context)
        print(f"✅ Generated {len(result.get('generated_deployment', []))} deployment files")
        print(f"   Files: {result.get('deployment_files', [])}")
        
        # Check artifacts in DB
        from umlagents.db.models import Artifact, ArtifactType
        artifacts = session.query(Artifact).filter(
            Artifact.project_id == project.id,
            Artifact.artifact_type.in_([ArtifactType.DOCKERFILE, ArtifactType.DEPLOYMENT_CONFIG])
        ).all()
        print(f"   Deployment artifacts: {len(artifacts)}")
        
        for art in artifacts:
            print(f"     - {art.name}: {art.file_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ DeployerAgent error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

def test_orchestrator():
    """Test orchestrator with Week 3 agents"""
    print("\n=== Testing Orchestrator with CONSTRUCTION phase ===")
    from umlagents.agents.orchestrator_agent import OrchestratorAgent
    
    engine = init_db('umlagents.db')
    session = Session(engine)
    
    try:
        project = session.query(Project).filter_by(id=1).first()
        if not project:
            print("❌ Project 1 not found")
            return False
        
        # Set phase to CONSTRUCTION (should already be)
        if project.current_phase != Phase.CONSTRUCTION:
            project.current_phase = Phase.CONSTRUCTION
            session.commit()
        
        orchestrator = OrchestratorAgent(db_session=session, project_id=project.id)
        context = {
            'project_id': project.id,
            'skip_existing': False,
            'start_phase': Phase.CONSTRUCTION
        }
        
        result = orchestrator.run(context)
        print(f"✅ Orchestrator completed: {result['success']}")
        print(f"   Agents executed: {[ae['agent'] for ae in result['agents_executed']]}")
        print(f"   Final phase: {result.get('final_phase', 'unknown')}")
        print(f"   Total time: {result['total_time_ms']}ms")
        
        return result['success']
        
    except Exception as e:
        print(f"❌ Orchestrator error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

if __name__ == "__main__":
    print("UMLAgents Week 3 Testing")
    print("========================")
    
    # Test individual agents
    dev_ok = test_developer()
    test_ok = test_tester()
    dep_ok = test_deployer()
    
    # Only test orchestrator if individual agents succeeded
    if dev_ok and test_ok and dep_ok:
        orch_ok = test_orchestrator()
    else:
        print("\nSkipping orchestrator test due to individual agent failures")
        orch_ok = False
    
    # Summary
    print("\n=== Summary ===")
    print(f"DeveloperAgent: {'✅' if dev_ok else '❌'}")
    print(f"TesterAgent: {'✅' if test_ok else '❌'}")
    print(f"DeployerAgent: {'✅' if dep_ok else '❌'}")
    print(f"Orchestrator: {'✅' if orch_ok else '❌'}")
    
    sys.exit(0 if all([dev_ok, test_ok, dep_ok, orch_ok]) else 1)