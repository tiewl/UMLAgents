#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/picoclaw/.openclaw/workspace/umlagents')
from umlagents.db.models import init_db, get_session, Project, Phase, Artifact, AgentRole, ArtifactType

engine = init_db('umlagents.db')
session = get_session(engine)

projects = session.query(Project).all()
print(f"Found {len(projects)} projects:")
for p in projects:
    print(f"  ID {p.id}: {p.name} ({p.domain}) - Phase: {p.current_phase.value if p.current_phase else 'unknown'}")
    artifacts = session.query(Artifact).filter(Artifact.project_id == p.id).all()
    print(f"    Artifacts: {len(artifacts)}")
    for a in artifacts[:3]:
        print(f"      - {a.artifact_type.value}: {a.name}")
    if len(artifacts) > 3:
        print(f"      ... and {len(artifacts)-3} more")
    print()

session.close()