#!/usr/bin/env python3
"""
UMLAgents CLI - Command-line interface for the UMLAgents pipeline.
"""
import os
import sys
import argparse
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
# Try to find .env relative to the project root
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    # Fall back to default location
    load_dotenv()

def check_api_key():
    """Check if DeepSeek API key is configured."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key or api_key == "your_deepseek_api_key_here":
        print("❌ DEEPSEEK_API_KEY not configured.")
        print()
        print("Please configure your DeepSeek API key:")
        print("1. Get your API key from https://platform.deepseek.com/")
        print("2. Edit the .env file:")
        print("   DEEPSEEK_API_KEY=your_actual_api_key_here")
        print()
        print("Or set the environment variable:")
        print("   export DEEPSEEK_API_KEY=your_actual_api_key_here")
        print()
        return False
    return True


def validate_and_setup_db(args, require_db_exists=True):
    """
    Common validation and database setup for agent commands.
    
    Args:
        args: CLI arguments
        require_db_exists: If True, database file must exist
        
    Returns:
        tuple: (project_id, db_path, session) or (None, None, None) on error
    """
    from pathlib import Path
    from umlagents.db.models import init_db, Project
    from umlagents.utils.validation import CLIArgumentValidator, ValidationError
    from sqlalchemy.orm import Session
    
    try:
        # Validate project ID if present
        project_id = None
        if hasattr(args, 'project_id') and args.project_id is not None:
            project_id = CLIArgumentValidator.validate_project_id(args.project_id)
        
        # Validate database path
        db_path = CLIArgumentValidator.validate_db_path(args.db or "umlagents.db")
        
        # Check if database file exists (for query operations)
        if require_db_exists and not db_path.exists():
            print(f"❌ Database not found: {db_path}")
            print(f"   Run 'load-yaml' or 'interactive' first to create a project.")
            return None, None, None
        
        # Initialize database and create session
        engine = init_db(db_path)
        session = Session(engine)
        
        # Verify project exists if project_id was provided
        if project_id is not None:
            project = session.query(Project).filter_by(id=project_id).first()
            if not project:
                print(f"❌ Project with ID {project_id} not found")
                session.close()
                return None, None, None
        
        return project_id, db_path, session
        
    except ValidationError as e:
        print(f"❌ Validation error: {e.message}")
        if e.field:
            print(f"   Field: {e.field}")
        return None, None, None
    except Exception as e:
        print(f"❌ Error setting up database: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None

def command_load_yaml(args):
    """Load YAML use case specification into database."""
    from umlagents.db.models import init_db
    from umlagents.agents.ba_agent import BAAgent
    from umlagents.utils.validation import YAMLValidator, ValidationError
    from sqlalchemy.orm import Session
    
    if not check_api_key():
        return 1
    
    yaml_path = Path(args.yaml_file)
    if not yaml_path.exists():
        print(f"❌ YAML file not found: {yaml_path}")
        return 1
    
    print(f"📁 Loading YAML: {yaml_path}")
    
    # Validate YAML structure before touching database
    try:
        print("🔍 Validating YAML structure...")
        yaml_data = YAMLValidator.validate_file(yaml_path)
        print("✅ YAML validation passed")
    except ValidationError as e:
        print(f"❌ YAML validation failed: {e.message}")
        if e.field:
            print(f"   Field: {e.field}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected validation error: {e}")
        return 1
    
    # Initialize database
    db_path = args.db or "umlagents.db"
    engine = init_db(db_path)
    session = Session(engine)
    
    try:
        # Create BA agent
        agent = BAAgent(db_session=session)
        
        # Run in YAML mode
        context = {"yaml_path": str(yaml_path)}
        result = agent.run(context)
        
        print()
        print("✅ Successfully loaded YAML specification")
        print(f"   Project ID: {result.get('project_id')}")
        print(f"   Actors: {len(result.get('actors', []))}")
        print(f"   Use Cases: {len(result.get('use_cases', []))}")
        print(f"   Database: {db_path}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error loading YAML: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()

def command_interactive(args):
    """Interactive requirement elicitation."""
    from umlagents.db.models import init_db
    from umlagents.agents.ba_agent import BAAgent
    from sqlalchemy.orm import Session
    
    if not check_api_key():
        return 1
    
    print("💬 Starting interactive requirement elicitation")
    print("   (Following Larman's OOA/OOD methodology)")
    print()
    
    # Initialize database
    db_path = args.db or "umlagents.db"
    engine = init_db(db_path)
    session = Session(engine)
    
    try:
        # Create BA agent
        agent = BAAgent(db_session=session)
        
        # Run in interactive mode
        context = {"interactive": True}
        
        # Pre-populate with command-line arguments if provided
        if args.project_name:
            context["project_name"] = args.project_name
        if args.domain:
            context["project_domain"] = args.domain
        
        result = agent.run(context)
        
        print()
        print("✅ Interactive elicitation complete")
        print(f"   Project ID: {result.get('project_id')}")
        print(f"   Generated: output/{result.get('project_id')}/requirements_interactive.yaml")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error in interactive mode: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()

def command_validate(args):
    """Validate YAML file against UMLAgents schema."""
    from umlagents.utils.validation import YAMLValidator, format_validation_errors, format_validation_warnings
    
    yaml_path = Path(args.yaml_file)
    if not yaml_path.exists():
        print(f"❌ YAML file not found: {yaml_path}")
        return 1
    
    print(f"🔍 Validating YAML: {yaml_path}")
    
    try:
        # Generate comprehensive validation report
        report = YAMLValidator.generate_validation_report(yaml_path)
        
        if report['valid']:
            print(f"✅ YAML validation passed")
            
            summary = report.get('data_summary', {})
            print(f"   Project: {summary.get('project', 'Unknown')}")
            print(f"   Domain: {summary.get('domain', 'Unknown')}")
            print(f"   Actors: {summary.get('actor_count', 0)}")
            print(f"   Use Cases: {summary.get('use_case_count', 0)}")
            
            if report['warnings']:
                print()
                print(format_validation_warnings(report['warnings']))
        else:
            print(f"❌ YAML validation failed")
            print()
            print(format_validation_errors(report['errors']))
            return 1
        
        return 0
        
    except Exception as e:
        print(f"❌ Validation error: {e}")
        import traceback
        traceback.print_exc()
        return 1
        print(f"   Actors: {actor_count}")
        print(f"   Use Cases: {use_case_count}")
        
        # Check for optional regulatory frameworks
        if "regulatory_frameworks" in yaml_data["project"]:
            frameworks = yaml_data["project"]["regulatory_frameworks"]
            if frameworks:
                print(f"   Regulatory frameworks: {', '.join(frameworks)}")
        
        return 0
        
    except yaml.YAMLError as e:
        print(f"❌ YAML parsing error: {e}")
        return 1
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return 1

def command_export(args):
    """Export project from database to YAML."""
    from umlagents.db.models import init_db, Project, Actor, UseCase
    from sqlalchemy.orm import Session
    
    db_path = args.db or "umlagents.db"
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return 1
    
    engine = init_db(db_path)
    session = Session(engine)
    
    try:
        # Get project
        project = session.query(Project).filter_by(id=args.project_id).first()
        if not project:
            print(f"❌ Project with ID {args.project_id} not found")
            return 1
        
        # Get actors
        actors = session.query(Actor).filter_by(project_id=project.id).all()
        
        # Get use cases
        use_cases = session.query(UseCase).filter_by(project_id=project.id).all()
        
        # Build YAML structure
        yaml_data = {
            "project": {
                "name": project.name,
                "domain": project.domain,
                "description": project.description,
                "regulatory_frameworks": project.regulatory_frameworks or []
            },
            "actors": [],
            "use_cases": []
        }
        
        # Add actors
        for actor in actors:
            yaml_data["actors"].append({
                "name": actor.name,
                "description": actor.description,
                "role": actor.role or "EndUser"
            })
        
        # Add use cases
        for uc in use_cases:
            # Find actor name
            actor_name = None
            if uc.actor_id:
                actor = session.query(Actor).filter_by(id=uc.actor_id).first()
                if actor:
                    actor_name = actor.name
            
            yaml_data["use_cases"].append({
                "id": uc.uc_id,
                "title": uc.title,
                "actor": actor_name or "System",
                "priority": uc.priority,
                "pre_conditions": uc.pre_conditions or [],
                "success_scenario": uc.success_scenario or [],
                "extension_scenarios": uc.extension_scenarios or [],
                "post_conditions": uc.post_conditions or [],
                "regulatory_requirements": uc.regulatory_requirements or [],
                "uat_criteria": uc.uat_criteria or []
            })
        
        # Write to file
        output_path = args.output or f"project_{project.id}_export.yaml"
        with open(output_path, 'w') as f:
            yaml.dump(yaml_data, f, default_flow_style=False)
        
        print(f"✅ Exported project to: {output_path}")
        print(f"   Project: {project.name}")
        print(f"   Actors: {len(actors)}")
        print(f"   Use Cases: {len(use_cases)}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Export error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()

def command_list(args):
    """List projects in database."""
    from umlagents.db.models import init_db, Project, Actor, UseCase
    from sqlalchemy.orm import Session
    
    db_path = args.db or "umlagents.db"
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return 1
    
    engine = init_db(db_path)
    session = Session(engine)
    
    try:
        projects = session.query(Project).all()
        
        if not projects:
            print("No projects found in database.")
            return 0
        
        print(f"Projects in {db_path}:")
        print()
        
        for project in projects:
            # Count actors and use cases
            actor_count = session.query(Actor).filter_by(project_id=project.id).count()
            use_case_count = session.query(UseCase).filter_by(project_id=project.id).count()
            
            print(f"  ID: {project.id}")
            print(f"  Name: {project.name}")
            print(f"  Domain: {project.domain}")
            print(f"  Created: {project.created_at}")
            print(f"  Actors: {actor_count}, Use Cases: {use_case_count}")
            print()
        
        return 0
        
    except Exception as e:
        print(f"❌ List error: {e}")
        return 1
    finally:
        session.close()

def command_architect(args):
    """Generate UML diagrams for a project."""
    from umlagents.db.models import Project
    from umlagents.agents.architect_agent import ArchitectAgent
    
    # Validate inputs and setup database
    project_id, db_path, session = validate_and_setup_db(args, require_db_exists=True)
    if project_id is None:
        return 1
    
    try:
        # Get project (already validated to exist)
        project = session.query(Project).filter_by(id=project_id).first()
        
        # Create architect agent
        agent = ArchitectAgent(db_session=session, project_id=project.id)
        
        # Run diagram generation
        diagram_types = args.diagram_types.split(',') if args.diagram_types else ['domain', 'sequence']
        context = {
            'project_id': project.id,
            'diagram_types': diagram_types
        }
        
        result = agent.run(context)
        
        print(f"✅ Generated {len(result['generated_artifacts'])} UML diagrams")
        print(f"   Project: {project.name}")
        
        for artifact in result['generated_artifacts']:
            print(f"   • {artifact['type']}: {artifact['filename']}")
            if artifact.get('plantuml_code'):
                # Show first few lines of PlantUML code
                lines = artifact['plantuml_code'].split('\n')[:3]
                for line in lines:
                    print(f"      {line}")
                if len(artifact['plantuml_code'].split('\n')) > 3:
                    print(f"      ...")
        
        return 0
        
    except Exception as e:
        print(f"❌ Architect error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()

def command_design(args):
    """Apply design patterns to a project."""
    from pathlib import Path
    from umlagents.db.models import init_db, Project
    from umlagents.agents.design_agent import DesignAgent
    from sqlalchemy.orm import Session
    
    if not check_api_key():
        return 1
    
    db_path = args.db or "umlagents.db"
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return 1
    
    engine = init_db(db_path)
    session = Session(engine)
    
    try:
        # Get project
        project = session.query(Project).filter_by(id=args.project_id).first()
        if not project:
            print(f"❌ Project with ID {args.project_id} not found")
            return 1
        
        # Create design agent
        agent = DesignAgent(db_session=session, project_id=project.id)
        
        # Run pattern application
        context = {
            'project_id': project.id
        }
        
        result = agent.run(context)
        
        print(f"✅ Applied {len(result['pattern_applications'])} design patterns")
        print(f"   Project: {project.name}")
        print(f"   Design Decisions: {len(result['design_decisions'])}")
        print(f"   Pattern Applications: {len(result['pattern_applications'])}")
        print(f"   Generated Artifacts: {len(result['generated_artifacts'])}")
        
        if result['pattern_applications']:
            print("\n   Applied Patterns:")
            for pa in result['pattern_applications']:
                print(f"     • {pa['pattern_name']} ({pa['pattern_category']})")
        
        if result['generated_artifacts']:
            print("\n   Generated Artifacts:")
            for artifact in result['generated_artifacts']:
                print(f"     • {artifact['name']}: {artifact['file_path']}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Design error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()

def command_developer(args):
    """Generate source code for a project."""
    from pathlib import Path
    from umlagents.db.models import init_db, Project
    from umlagents.agents.developer_agent import DeveloperAgent
    from sqlalchemy.orm import Session
    
    if not check_api_key():
        return 1
    
    db_path = args.db or "umlagents.db"
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return 1
    
    engine = init_db(db_path)
    session = Session(engine)
    
    try:
        # Get project
        project = session.query(Project).filter_by(id=args.project_id).first()
        if not project:
            print(f"❌ Project with ID {args.project_id} not found")
            return 1
        
        # Create developer agent
        agent = DeveloperAgent(db_session=session, project_id=project.id)
        
        # Run code generation
        context = {
            'project_id': project.id,
            'skip_existing': args.skip_existing if hasattr(args, 'skip_existing') else False
        }
        
        result = agent.run(context)
        
        print(f"✅ Generated {len(result['generated_files'])} source code files")
        print(f"   Project: {project.name}")
        print(f"   Generated Files: {', '.join(result['code_files']) if result.get('code_files') else 'None'}")
        
        if result.get('generated_files'):
            print("\n   Generated Artifacts:")
            for artifact in result['generated_files']:
                print(f"     • {artifact['name']}: {artifact['file_path']}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Developer error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()

def command_tester(args):
    """Generate tests for a project."""
    from pathlib import Path
    from umlagents.db.models import init_db, Project
    from umlagents.agents.tester_agent import TesterAgent
    from sqlalchemy.orm import Session
    
    if not check_api_key():
        return 1
    
    db_path = args.db or "umlagents.db"
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return 1
    
    engine = init_db(db_path)
    session = Session(engine)
    
    try:
        # Get project
        project = session.query(Project).filter_by(id=args.project_id).first()
        if not project:
            print(f"❌ Project with ID {args.project_id} not found")
            return 1
        
        # Create tester agent
        agent = TesterAgent(db_session=session, project_id=project.id)
        
        # Run test generation
        context = {
            'project_id': project.id,
            'skip_existing': args.skip_existing if hasattr(args, 'skip_existing') else False
        }
        
        result = agent.run(context)
        
        print(f"✅ Generated {len(result['generated_tests'])} test files")
        print(f"   Project: {project.name}")
        print(f"   Generated Tests: {', '.join(result['test_files']) if result.get('test_files') else 'None'}")
        
        if result.get('generated_tests'):
            print("\n   Generated Test Artifacts:")
            for artifact in result['generated_tests']:
                print(f"     • {artifact['name']}: {artifact['file_path']}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Tester error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()

def command_deployer(args):
    """Generate deployment configuration for a project."""
    from pathlib import Path
    from umlagents.db.models import init_db, Project
    from umlagents.agents.deployer_agent import DeployerAgent
    from sqlalchemy.orm import Session
    
    if not check_api_key():
        return 1
    
    db_path = args.db or "umlagents.db"
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return 1
    
    engine = init_db(db_path)
    session = Session(engine)
    
    try:
        # Get project
        project = session.query(Project).filter_by(id=args.project_id).first()
        if not project:
            print(f"❌ Project with ID {args.project_id} not found")
            return 1
        
        # Create deployer agent
        agent = DeployerAgent(db_session=session, project_id=project.id)
        
        # Run deployment generation
        context = {
            'project_id': project.id,
            'skip_existing': args.skip_existing if hasattr(args, 'skip_existing') else False
        }
        
        result = agent.run(context)
        
        print(f"✅ Generated {len(result['generated_deployment'])} deployment files")
        print(f"   Project: {project.name}")
        print(f"   Generated Files: {', '.join(result['deployment_files']) if result.get('deployment_files') else 'None'}")
        
        if result.get('generated_deployment'):
            print("\n   Generated Deployment Artifacts:")
            for artifact in result['generated_deployment']:
                print(f"     • {artifact['name']}: {artifact['file_path']}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Deployer error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()

def command_orchestrate(args):
    """Run the full UMLAgents pipeline for a project."""
    from pathlib import Path
    from umlagents.db.models import init_db, Project, Phase
    from umlagents.agents.orchestrator_agent import OrchestratorAgent
    from sqlalchemy.orm import Session
    
    if not check_api_key():
        return 1
    
    db_path = args.db or "umlagents.db"
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return 1
    
    engine = init_db(db_path)
    session = Session(engine)
    
    try:
        # Get project
        project = session.query(Project).filter_by(id=args.project_id).first()
        if not project:
            print(f"❌ Project with ID {args.project_id} not found")
            return 1
        
        # Create orchestrator agent
        agent = OrchestratorAgent(db_session=session, project_id=project.id)
        
        # Prepare context
        context = {
            'project_id': project.id,
            'halt_on_error': not args.continue_on_error
        }
        if args.start_phase:
            context['start_phase'] = Phase[args.start_phase.upper()]
        if args.agents:
            context['agents_to_run'] = args.agents.split(',')
        
        # Run pipeline
        result = agent.run(context)
        
        print(f"✅ Pipeline executed successfully")
        print(f"   Project: {project.name}")
        print(f"   Agents executed: {len(result['agents_executed'])}")
        print(f"   Total time: {result['total_time_ms']}ms")
        print(f"   Success: {result['success']}")
        
        if result['errors']:
            print(f"\n   Errors ({len(result['errors'])}):")
            for error in result['errors']:
                print(f"     • {error}")
        
        return 0 if result['success'] else 1
        
    except Exception as e:
        print(f"❌ Orchestrator error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        session.close()

def command_integrate_dice_game(args):
    """Run dice‑game‑agents pipeline and import outputs into UMLAgents database."""
    try:
        from umlagents.integration.dice_game.integrate import main as integrate_main
    except ImportError as e:
        print(f"❌ Integration module not found: {e}")
        print("Make sure dice‑game‑agents repository is available at:")
        print("  /home/picoclaw/.openclaw/workspace/dice-game-agents-ref")
        return 1
    
    try:
        # Run integration
        integrate_main()
        return 0
    except Exception as e:
        print(f"❌ Integration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="UMLAgents CLI - Automated OOA/OOD pipeline using role‑playing AI agents",
        epilog="Example: python cli.py load-yaml examples/dice-game-example.yaml"
    )
    parser.add_argument(
        "--db", 
        help="Database file path (default: umlagents.db)",
        default="umlagents.db"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # load-yaml command
    parser_load = subparsers.add_parser("load-yaml", help="Load YAML use case specification")
    parser_load.add_argument("yaml_file", help="Path to YAML file")
    
    # interactive command
    parser_interactive = subparsers.add_parser("interactive", help="Interactive requirement elicitation")
    parser_interactive.add_argument("--project-name", help="Project name (optional)")
    parser_interactive.add_argument("--domain", help="Project domain (optional)")
    
    # validate command
    parser_validate = subparsers.add_parser("validate", help="Validate YAML file")
    parser_validate.add_argument("yaml_file", help="Path to YAML file")
    
    # export command
    parser_export = subparsers.add_parser("export", help="Export project from database to YAML")
    parser_export.add_argument("project_id", type=int, help="Project ID to export")
    parser_export.add_argument("--output", help="Output file path")
    
    # list command
    subparsers.add_parser("list", help="List projects in database")
    # architect command
    parser_arch = subparsers.add_parser("architect", help="Generate UML diagrams")
    parser_arch.add_argument("project_id", type=int, help="Project ID")
    parser_arch.add_argument("--diagram-types", help="Comma-separated diagram types (domain,sequence)")
    
    # design command
    parser_design = subparsers.add_parser("design", help="Apply design patterns")
    parser_design.add_argument("project_id", type=int, help="Project ID")
    
    # developer command
    parser_developer = subparsers.add_parser("developer", help="Generate source code")
    parser_developer.add_argument("project_id", type=int, help="Project ID")
    parser_developer.add_argument("--skip-existing", action="store_true", help="Skip if source code already exists")

    # tester command
    parser_tester = subparsers.add_parser("tester", help="Generate tests")
    parser_tester.add_argument("project_id", type=int, help="Project ID")
    parser_tester.add_argument("--skip-existing", action="store_true", help="Skip if tests already exist")

    # deployer command
    parser_deployer = subparsers.add_parser("deployer", help="Generate deployment config")
    parser_deployer.add_argument("project_id", type=int, help="Project ID")
    parser_deployer.add_argument("--skip-existing", action="store_true", help="Skip if deployment config already exists")

    # integrate-dice-game command
    parser_integrate = subparsers.add_parser("integrate-dice-game", help="Integrate with dice‑game‑agents repository")

    # orchestrate command
    parser_orchestrate = subparsers.add_parser("orchestrate", help="Run full pipeline")
    parser_orchestrate.add_argument("project_id", type=int, help="Project ID")
    parser_orchestrate.add_argument("--start-phase", help="Start phase (INCEPTION, ELABORATION, CONSTRUCTION, TRANSITION)")
    parser_orchestrate.add_argument("--agents", help="Comma-separated list of agents to run (overrides phase)")
    parser_orchestrate.add_argument("--continue-on-error", action="store_true", help="Continue pipeline even if an agent fails")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute command
    commands = {
        "load-yaml": command_load_yaml,
        "interactive": command_interactive,
        "validate": command_validate,
        "export": command_export,
        "list": command_list,
        "architect": command_architect,
        "design": command_design,
        "developer": command_developer,
        "tester": command_tester,
        "deployer": command_deployer,
        "integrate-dice-game": command_integrate_dice_game,
        "orchestrate": command_orchestrate
    }
    
    return commands[args.command](args)

if __name__ == "__main__":
    sys.exit(main())