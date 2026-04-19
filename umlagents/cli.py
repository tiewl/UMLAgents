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
load_dotenv()

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

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

def command_load_yaml(args):
    """Load YAML use case specification into database."""
    from umlagents.db.models import init_db
    from umlagents.agents.ba_agent import BAAgent
    from sqlalchemy.orm import Session
    
    if not check_api_key():
        return 1
    
    yaml_path = Path(args.yaml_file)
    if not yaml_path.exists():
        print(f"❌ YAML file not found: {yaml_path}")
        return 1
    
    print(f"📁 Loading YAML: {yaml_path}")
    
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
    """Validate YAML file against schema."""
    yaml_path = Path(args.yaml_file)
    if not yaml_path.exists():
        print(f"❌ YAML file not found: {yaml_path}")
        return 1
    
    try:
        with open(yaml_path, 'r') as f:
            yaml_data = yaml.safe_load(f)
        
        # Basic validation
        required_fields = ["project"]
        for field in required_fields:
            if field not in yaml_data:
                print(f"❌ Missing required field: {field}")
                return 1
        
        project_fields = ["name", "domain", "description"]
        for field in project_fields:
            if field not in yaml_data["project"]:
                print(f"❌ Missing project field: {field}")
                return 1
        
        # Count actors and use cases
        actor_count = len(yaml_data.get("actors", []))
        use_case_count = len(yaml_data.get("use_cases", []))
        
        print(f"✅ YAML validation passed")
        print(f"   Project: {yaml_data['project']['name']}")
        print(f"   Domain: {yaml_data['project']['domain']}")
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
        "list": command_list
    }
    
    return commands[args.command](args)

if __name__ == "__main__":
    sys.exit(main())