#!/usr/bin/env python3
"""
Migration script for UMLAgents schema updates.
Adds metadata column to artifacts table if missing.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, JSON, Enum, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import enum

# Import our models to ensure enums are loaded
from umlagents.db.models import Base, Artifact, AgentRole

def check_and_migrate(db_path="umlagents.db"):
    """Check schema and add missing columns."""
    engine = create_engine(f"sqlite:///{db_path}")
    
    # Create inspector
    insp = inspect(engine)
    
    # Check if metadata column exists in artifacts table
    columns = insp.get_columns("artifacts")
    column_names = [col['name'] for col in columns]
    
    print(f"Existing columns in artifacts: {column_names}")
    
    if 'metadata' not in column_names:
        print("Adding metadata column to artifacts table...")
        with engine.connect() as conn:
            # SQLite doesn't support adding JSON column directly, use TEXT
            conn.execute(text("ALTER TABLE artifacts ADD COLUMN metadata TEXT"))
            conn.commit()
        print("✅ Added metadata column")
    else:
        print("✅ metadata column already exists")
    
    # Verify AgentRole enum values (Python-side only)
    print(f"AgentRole enum values: {[role.value for role in AgentRole]}")
    
    if 'orchestrator' not in [role.value for role in AgentRole]:
        print("⚠️  ORCHESTRATOR role not in enum (Python code needs update)")
    else:
        print("✅ ORCHESTRATOR role present in enum")
    
    # Check Phase enum column in projects
    columns = insp.get_columns("projects")
    project_cols = [col['name'] for col in columns]
    print(f"Project columns: {project_cols}")
    
    if 'current_phase' not in project_cols:
        print("⚠️  current_phase column missing from projects table")
    else:
        print("✅ current_phase column exists")
    
    print("\nSchema migration complete.")

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "umlagents.db"
    check_and_migrate(db_path)