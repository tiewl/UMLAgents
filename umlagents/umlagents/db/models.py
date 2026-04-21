"""
SQLAlchemy models for UMLAgents audit trail.
Captures full traceability from requirements → design → code → tests → deployment.
Aligned with Larman's OOA/OOD methodology and pattern tracking.
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, DateTime, 
    ForeignKey, Boolean, JSON, Float, Enum
)
from sqlalchemy.orm import declarative_base, relationship, Session
from sqlalchemy.sql import func
import enum

Base = declarative_base()

# ============================================================================
# Enums for type safety
# ============================================================================

class Phase(enum.Enum):
    """Unified Process phases (Larman)"""
    INCEPTION = "inception"
    ELABORATION = "elaboration"
    CONSTRUCTION = "construction"
    TRANSITION = "transition"

class AgentRole(enum.Enum):
    """Specialized agent roles in the pipeline"""
    BA = "business_analyst"
    ARCHITECT = "architect"
    DESIGN = "designer"
    DEVELOPER = "developer"
    TESTER = "tester"
    DEPLOYER = "deployer"
    ORCHESTRATOR = "orchestrator"

class PatternCategory(enum.Enum):
    """GRASP and GoF pattern categories"""
    GRASP_CREATOR = "grasp_creator"
    GRASP_EXPERT = "grasp_expert"
    GRASP_CONTROLLER = "grasp_controller"
    GRASP_PURE_FABRICATION = "grasp_pure_fabrication"
    GRASP_INDIRECTION = "grasp_indirection"
    GOF_CREATIONAL = "gof_creational"
    GOF_STRUCTURAL = "gof_structural"
    GOF_BEHAVIORAL = "gof_behavioral"
    ARCHITECTURAL = "architectural"

class ArtifactType(enum.Enum):
    """Generated artifact types"""
    USE_CASE_YAML = "use_case_yaml"
    DOMAIN_DIAGRAM = "domain_diagram"
    SEQUENCE_DIAGRAM = "sequence_diagram"
    CLASS_DIAGRAM = "class_diagram"
    SOURCE_CODE = "source_code"
    UNIT_TESTS = "unit_tests"
    INTEGRATION_TESTS = "integration_tests"
    UAT_CHECKLIST = "uat_checklist"
    DOCKERFILE = "dockerfile"
    DEPLOYMENT_CONFIG = "deployment_config"
    AUDIT_REPORT = "audit_report"

# ============================================================================
# Core domain models
# ============================================================================

class Project(Base):
    """Root project entity"""
    __tablename__ = "projects"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    domain = Column(String(100))  # e.g., "Healthcare", "Finance", "Gaming"
    description = Column(Text)
    regulatory_frameworks = Column(JSON)  # List of strings: ["GDPR", "SOC2", "HIPAA"]
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    current_phase = Column(Enum(Phase), default=Phase.INCEPTION)
    
    # Relationships
    actors = relationship("Actor", back_populates="project", cascade="all, delete-orphan")
    use_cases = relationship("UseCase", back_populates="project", cascade="all, delete-orphan")
    design_decisions = relationship("DesignDecision", back_populates="project", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="project", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="project", cascade="all, delete-orphan")

class Actor(Base):
    """System actors (Larman: who interacts with the system)"""
    __tablename__ = "actors"
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    role = Column(String(50))  # e.g., "EndUser", "Admin", "System", "ExternalService"
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    project = relationship("Project", back_populates="actors")
    use_cases = relationship("UseCase", back_populates="actor")

class UseCase(Base):
    """Use cases (Larman's primary requirements artifact)"""
    __tablename__ = "use_cases"
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    actor_id = Column(Integer, ForeignKey("actors.id", ondelete="CASCADE"))
    uc_id = Column(String(20), nullable=False)  # e.g., "UC1", "AUTH-001"
    title = Column(String(200), nullable=False)
    priority = Column(Integer, default=2)  # 1=must have, 2=should have, 3=could have
    pre_conditions = Column(JSON)  # List of strings
    success_scenario = Column(JSON)  # List of strings (numbered steps)
    extension_scenarios = Column(JSON)  # List of dicts: {"condition": str, "steps": List[str]}
    post_conditions = Column(JSON)  # List of strings
    regulatory_requirements = Column(JSON)  # List of strings
    uat_criteria = Column(JSON)  # List of strings
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    project = relationship("Project", back_populates="use_cases")
    actor = relationship("Actor", back_populates="use_cases")
    design_decisions = relationship("DesignDecision", back_populates="use_case")
    pattern_applications = relationship("PatternApplication", back_populates="use_case")

class DesignDecision(Base):
    """Design decisions with rationale (Larman: coupling, cohesion, pattern choices)"""
    __tablename__ = "design_decisions"
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    use_case_id = Column(Integer, ForeignKey("use_cases.id", ondelete="CASCADE"))
    title = Column(String(200), nullable=False)
    description = Column(Text)
    rationale = Column(Text)  # Why this decision was made
    alternatives_considered = Column(JSON)  # List of alternative designs considered
    impact_assessment = Column(Text)  # Impact on maintainability, performance, etc.
    created_by_agent = Column(Enum(AgentRole))
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    project = relationship("Project", back_populates="design_decisions")
    use_case = relationship("UseCase", back_populates="design_decisions")
    pattern_applications = relationship("PatternApplication", back_populates="design_decision")

class PatternApplication(Base):
    """Application of GRASP/GoF patterns with rationale"""
    __tablename__ = "pattern_applications"
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    use_case_id = Column(Integer, ForeignKey("use_cases.id", ondelete="CASCADE"))
    design_decision_id = Column(Integer, ForeignKey("design_decisions.id", ondelete="CASCADE"))
    pattern_name = Column(String(100), nullable=False)  # e.g., "Expert", "Factory", "Observer"
    pattern_category = Column(Enum(PatternCategory))
    description = Column(Text)  # How pattern is applied
    rationale = Column(Text)  # Why this pattern was chosen
    created_by_agent = Column(Enum(AgentRole))
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    project = relationship("Project")
    use_case = relationship("UseCase", back_populates="pattern_applications")
    design_decision = relationship("DesignDecision", back_populates="pattern_applications")

class Artifact(Base):
    """Generated artifacts (diagrams, code, tests, configs)"""
    __tablename__ = "artifacts"
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(Enum(ArtifactType), nullable=False)
    name = Column(String(200), nullable=False)
    file_path = Column(String(500))  # Relative path to file
    content_hash = Column(String(64))  # SHA-256 for change detection
    generated_by_agent = Column(Enum(AgentRole))
    generation_time_ms = Column(Integer)  # How long generation took
    artifact_metadata = Column(JSON)  # Additional structured metadata
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    project = relationship("Project", back_populates="artifacts")

class AuditLog(Base):
    """Complete audit trail of agent activities"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    agent_role = Column(Enum(AgentRole))
    activity = Column(String(200), nullable=False)  # e.g., "elicited_requirement", "applied_pattern"
    details = Column(JSON)  # Structured details of the activity
    timestamp = Column(DateTime, default=func.now())
    
    # Relationships
    project = relationship("Project", back_populates="audit_logs")

# ============================================================================
# Database initialization
# ============================================================================

def init_db(db_path: str = "umlagents.db"):
    """Initialize database with schema"""
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return engine

def get_session(engine):
    """Get a database session"""
    return Session(engine)