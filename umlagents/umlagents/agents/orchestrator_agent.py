"""
Orchestrator Agent - Coordinates the UMLAgents pipeline.

Responsibilities:
- Manage agent execution sequence (BA → Architect → Design → Developer → Tester → Deployer)
- Update project phase (Larman: Inception → Elaboration → Construction → Transition)
- Pass context between agents (project_id, artifacts, decisions)
- Handle errors and rollback if needed
- Maintain comprehensive audit trail
"""
import time
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseAgent, InsufficientCreditsError
from .ba_agent import BAAgent
from .architect_agent import ArchitectAgent
from .design_agent import DesignAgent
from ..db.models import AgentRole, Project, Phase, AuditLog
from ..utils.events import publish_agent_status, publish_pipeline_event


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator agent for coordinating the UMLAgents pipeline.

    Key responsibilities:
    1. Sequence agent execution according to methodology
    2. Update project phase based on progress
    3. Pass context and artifacts between agents
    4. Provide rollback and error recovery
    5. Generate comprehensive pipeline reports
    """

    def __init__(self, db_session: Optional[Session] = None, project_id: Optional[int] = None):
        system_prompt = """You are a project orchestrator following Craig Larman's
        Object-Oriented Analysis and Design methodology. Your expertise includes:

        1. Sequencing SDLC activities (Inception → Elaboration → Construction → Transition)
        2. Coordinating specialized AI agents (BA, Architect, Design, etc.)
        3. Managing project state and phase transitions
        4. Ensuring traceability and audit compliance
        5. Handling errors and providing fallback strategies

        You think in terms of project management, risk mitigation, and quality assurance.
        """

        super().__init__(
            name="OrchestratorAgent",
            system_prompt=system_prompt,
            agent_role=AgentRole.ORCHESTRATOR,
            db_session=db_session,
            project_id=project_id
        )

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the full UMLAgents pipeline or resume from current phase.

        Args:
            context: May contain:
                - 'project_id' (required if not set in agent)
                - 'start_phase' (optional, default: current project phase)
                - 'agents_to_run' (optional list of agent roles to run)
                - 'skip_existing' (optional bool, default: True)

        Returns:
            Dict with pipeline results, including:
                - 'project_id'
                - 'phases_completed'
                - 'agents_executed'
                - 'artifacts_generated'
                - 'total_time_ms'
                - 'success' (bool)
        """
        project_id = context.get('project_id', self.project_id)
        if not project_id:
            raise ValueError("project_id required in context or agent initialization")

        # Load project
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        # Determine start phase
        start_phase = context.get('start_phase', project.current_phase)
        # Convert string phase to Phase enum
        if isinstance(start_phase, str):
            start_phase = Phase[start_phase.upper()]
        # Get agents to run, defaulting to phase-based agents if None/empty or not provided
        agents_to_run = context.get('agents_to_run')
        if agents_to_run is None or agents_to_run == []:
            agents_to_run = self._get_agents_for_phase(start_phase)
        skip_existing = context.get('skip_existing', True)
        
        # If agents_to_run contains strings, map to classes
        if agents_to_run and isinstance(agents_to_run[0], str):
            from .ba_agent import BAAgent
            from .architect_agent import ArchitectAgent
            from .design_agent import DesignAgent
            from .developer_agent import DeveloperAgent
            from .tester_agent import TesterAgent
            from .deployer_agent import DeployerAgent
            from .frontend_agent import FrontendAgent
            agent_map = {
                "BAAgent": BAAgent,
                "ArchitectAgent": ArchitectAgent,
                "DesignAgent": DesignAgent,
                "DeveloperAgent": DeveloperAgent,
                "TesterAgent": TesterAgent,
                "DeployerAgent": DeployerAgent,
                "FrontendAgent": FrontendAgent,
            }
            agents_to_run = [agent_map[name] for name in agents_to_run if name in agent_map]

        print(f"[Orchestrator] Starting pipeline for project: {project.name}")
        print(f"[Orchestrator] Current phase: {project.current_phase.value}")
        if agents_to_run:
            print(f"[Orchestrator] Agents to run: {[agent.__name__ for agent in agents_to_run]}")
        else:
            print(f"[Orchestrator] Agents to run: [] (none specified, will use phase defaults)")

        results = {
            'project_id': project_id,
            'project_name': project.name,
            'start_phase': start_phase.value if start_phase else "unknown",
            'agents_executed': [],
            'phases_completed': [],
            'artifacts_generated': [],
            'errors': [],
            'total_time_ms': 0
        }

        total_start = time.time()
        pipeline_id = f"pipeline_{project_id}_{int(total_start)}"
        publish_pipeline_event(
            pipeline_id=pipeline_id,
            event_type="started",
            project_id=project_id,
            agents=[agent_class.__name__ for agent_class in agents_to_run]
        )
        results['pipeline_id'] = pipeline_id

        # Execute agents in sequence
        for agent_class in agents_to_run:
            agent_name = agent_class.__name__
            print(f"\n[Orchestrator] Executing {agent_name}...")
            
            agent_start = time.time()
            
            try:
                # Create agent instance
                agent = agent_class(db_session=self.db, project_id=project_id)
                
                # Publish agent started event
                publish_agent_status(
                    agent_name=agent_name,
                    status="started",
                    project_id=project_id
                )
                
                # Run agent with current context
                agent_context = {
                    'project_id': project_id,
                    'skip_existing': skip_existing,
                    **context.get('agent_contexts', {}).get(agent_name, {})
                }
                
                agent_result = agent.run(agent_context)
                
                # Update project phase if needed
                new_phase = self._determine_next_phase(project.current_phase, agent_name)
                if new_phase != project.current_phase:
                    project.current_phase = new_phase
                    self.db.commit()
                    print(f"[Orchestrator] Updated project phase to: {new_phase.value}")
                    results['phases_completed'].append(new_phase.value)
                
                # Record agent execution
                elapsed_ms = int((time.time() - agent_start) * 1000)
                # Publish agent completed event
                publish_agent_status(
                    agent_name=agent_name,
                    status="completed",
                    project_id=project_id,
                    duration_ms=elapsed_ms
                )
                results['agents_executed'].append({
                    'agent': agent_name,
                    'status': 'success',
                    'time_ms': elapsed_ms,
                    'result': agent_result
                })
                
                # Collect generated artifacts
                if 'generated_artifacts' in agent_result:
                    results['artifacts_generated'].extend(agent_result['generated_artifacts'])
                
                print(f"[Orchestrator] {agent_name} completed in {elapsed_ms}ms")
                
            except InsufficientCreditsError as e:
                elapsed_ms = int((time.time() - agent_start) * 1000)
                error_msg = f"Anthropic credit balance too low — top up at console.anthropic.com/settings/billing"
                print(f"[Orchestrator] CREDIT ERROR: {error_msg}")
                publish_agent_status(agent_name=agent_name, status="completed", project_id=project_id, duration_ms=elapsed_ms, error=error_msg)
                results['agents_executed'].append({'agent': agent_name, 'status': 'error', 'time_ms': elapsed_ms, 'error': error_msg})
                results['errors'].append(error_msg)
                break  # always halt on credit errors

            except Exception as e:
                elapsed_ms = int((time.time() - agent_start) * 1000)
                error_msg = f"{agent_name} failed: {str(e)}"
                print(f"[Orchestrator] FAILED: {error_msg}")
                
                # Publish agent completed with error event
                publish_agent_status(
                    agent_name=agent_name,
                    status="completed",
                    project_id=project_id,
                    duration_ms=elapsed_ms,
                    error=error_msg
                )
                
                results['agents_executed'].append({
                    'agent': agent_name,
                    'status': 'error',
                    'time_ms': elapsed_ms,
                    'error': error_msg
                })
                results['errors'].append(error_msg)
                
                # Determine if we should continue or halt
                if context.get('halt_on_error', True):
                    print("[Orchestrator] Pipeline halted due to error")
                    break
        
        total_elapsed_ms = int((time.time() - total_start) * 1000)
        results['total_time_ms'] = total_elapsed_ms
        results['success'] = len(results['errors']) == 0
        
        # Log pipeline completion
        self.log_activity(
            action="pipeline_execution",
            details={
                "project_id": project_id,
                "agents_executed": [ae['agent'] for ae in results['agents_executed']],
                "success_count": len([ae for ae in results['agents_executed'] if ae['status'] == 'success']),
                "error_count": len(results['errors']),
                "total_time_ms": total_elapsed_ms,
                "final_phase": project.current_phase.value
            }
        )
        
        # Publish pipeline completed event
        publish_pipeline_event(
            pipeline_id=results.get('pipeline_id', f"pipeline_{project_id}"),
            event_type="completed",
            project_id=project_id,
            agents=[ae['agent'] for ae in results['agents_executed']],
            error=None if results['success'] else f"{len(results['errors'])} errors"
        )
        
        print(f"\n[Orchestrator] Pipeline completed in {total_elapsed_ms}ms")
        print(f"[Orchestrator] Success: {results['success']}")
        print(f"[Orchestrator] Agents executed: {len(results['agents_executed'])}")
        print(f"[Orchestrator] Artifacts generated: {len(results['artifacts_generated'])}")
        
        return results

    def _get_agents_for_phase(self, phase: Phase) -> List:
        """
        Get list of agent classes to run for a given phase.
        
        Phase mapping (Larman):
        - INCEPTION: BAAgent (requirements)
        - ELABORATION: ArchitectAgent, DesignAgent (architecture & design)
        - CONSTRUCTION: DeveloperAgent, TesterAgent (implementation & testing)
        - TRANSITION: DeployerAgent (deployment)
        """
        from .ba_agent import BAAgent
        from .architect_agent import ArchitectAgent
        from .design_agent import DesignAgent
        from .developer_agent import DeveloperAgent
        from .tester_agent import TesterAgent
        from .deployer_agent import DeployerAgent
        from .frontend_agent import FrontendAgent

        phase_agents = {
            Phase.INCEPTION: [BAAgent],
            Phase.ELABORATION: [ArchitectAgent, DesignAgent],
            Phase.CONSTRUCTION: [DeveloperAgent, TesterAgent, FrontendAgent],
            Phase.TRANSITION: [DeployerAgent]
        }
        
        return phase_agents.get(phase, [])

    def _determine_next_phase(self, current_phase: Phase, completed_agent: str) -> Phase:
        """
        Determine next project phase based on completed agent.
        Simple progression: INCEPTION → ELABORATION → CONSTRUCTION → TRANSITION
        """
        phase_order = [Phase.INCEPTION, Phase.ELABORATION, Phase.CONSTRUCTION, Phase.TRANSITION]
        
        # If we just completed BA Agent, move to ELABORATION
        if completed_agent == "BAAgent" and current_phase == Phase.INCEPTION:
            return Phase.ELABORATION
        
        # If we just completed Design Agent, move to CONSTRUCTION
        if completed_agent == "DesignAgent" and current_phase == Phase.ELABORATION:
            return Phase.CONSTRUCTION
        
        # If we just completed Tester Agent, move to TRANSITION
        if completed_agent == "TesterAgent" and current_phase == Phase.CONSTRUCTION:
            return Phase.TRANSITION
        
        # Default: stay in current phase
        return current_phase

    def get_pipeline_status(self, project_id: int) -> Dict[str, Any]:
        """
        Get current pipeline status for a project.
        
        Returns:
            Dict with project info, phase, completed agents, pending agents, etc.
        """
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        # Get audit logs for this project
        audit_logs = self.db.query(AuditLog).filter(
            AuditLog.project_id == project_id
        ).order_by(AuditLog.timestamp).all()
        
        # Extract agent executions from audit logs
        agent_activities = []
        for log in audit_logs:
            if log.activity in ['pipeline_execution', 'agent_execution']:
                agent_activities.append({
                    'agent_role': log.agent_role.value if log.agent_role else None,
                    'activity': log.activity,
                    'timestamp': log.timestamp,
                    'details': log.details
                })
        
        # Determine next agents to run
        next_agents = self._get_agents_for_phase(project.current_phase)
        
        return {
            'project_id': project_id,
            'project_name': project.name,
            'current_phase': project.current_phase.value,
            'next_agents': [agent.__name__ for agent in next_agents],
            'agent_activities': agent_activities,
            'audit_log_count': len(audit_logs)
        }

    def rollback_to_phase(self, project_id: int, target_phase: Phase) -> Dict[str, Any]:
        """
        Rollback project to a previous phase (for error recovery).
        This is a simplified implementation - in production would need to handle
        artifact cleanup, database state, etc.
        """
        project = self.db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project {project_id} not found")
        
        print(f"[Orchestrator] Rolling back project {project.name} to phase: {target_phase.value}")
        
        # Update project phase
        project.current_phase = target_phase
        self.db.commit()
        
        # Log rollback
        self.log_activity(
            action="phase_rollback",
            details={
                "from_phase": project.current_phase.value,
                "to_phase": target_phase.value,
                "timestamp": time.time()
            }
        )
        
        return {
            'project_id': project_id,
            'previous_phase': project.current_phase.value,
            'new_phase': target_phase.value,
            'rollback_time': time.time()
        }