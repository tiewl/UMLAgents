def command_architect(args):
    """Generate UML diagrams for a project."""
    from pathlib import Path
    from umlagents.db.models import init_db, Project, Actor, UseCase
    from umlagents.agents.architect_agent import ArchitectAgent
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