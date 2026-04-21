#!/usr/bin/env python3
"""Update project phase to ELABORATION."""
import sys
sys.path.insert(0, '.')

from umlagents.db.models import init_db, Project, Phase
from sqlalchemy.orm import Session

def update_phase(project_id=1, new_phase=Phase.ELABORATION):
    engine = init_db("umlagents.db")
    session = Session(engine)
    
    project = session.query(Project).filter_by(id=project_id).first()
    if not project:
        print(f"Project {project_id} not found")
        return
    
    old_phase = project.current_phase
    project.current_phase = new_phase
    session.commit()
    
    print(f"Updated project {project.name} phase: {old_phase.value} -> {new_phase.value}")
    
    session.close()

if __name__ == "__main__":
    update_phase()