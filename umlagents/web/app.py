#!/usr/bin/env python3
"""
UMLAgents WebSocket UI - FastAPI application for real‑time pipeline monitoring.

Features:
- WebSocket broadcasts for pipeline events
- Real‑time PlantUML diagram rendering
- Interactive requirement elicitation
- Audit trail exploration
- Pipeline control (start/pause/restart)
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import UMLAgents core
try:
    from umlagents.db.models import init_db, get_session, Project, Phase, Artifact, AuditLog, AgentRole
    from umlagents.agents.orchestrator_agent import OrchestratorAgent
    from umlagents.agents.ba_agent import BAAgent
    from umlagents.utils.events import event_bus, Event
    UMLAGENTS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: UMLAgents import error - {e}")
    print("Running in demo mode without database access.")
    UMLAGENTS_AVAILABLE = False

# ============================================================================
# Configuration
# ============================================================================

DB_PATH = os.getenv("UMLAGENTS_DB_PATH", "umlagents.db")
PORT = int(os.getenv("UMLAGENTS_WEB_PORT", "8080"))
HOST = os.getenv("UMLAGENTS_WEB_HOST", "0.0.0.0")
DEBUG = os.getenv("UMLAGENTS_DEBUG", "false").lower() == "true"

# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="UMLAgents WebSocket UI",
    description="Real‑time monitoring and interaction for UMLAgents pipeline",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (for frontend)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# ============================================================================
# WebSocket Manager
# ============================================================================

class WebSocketManager:
    """Manages WebSocket connections and broadcasting."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.pipeline_tasks: Dict[str, asyncio.Task] = {}
        
        # Subscribe to UMLAgents event bus for real‑time monitoring
        if UMLAGENTS_AVAILABLE:
            try:
                event_bus.subscribe(self._handle_event)
                logging.info("WebSocketManager subscribed to UMLAgents event bus")
            except Exception as e:
                logging.error(f"Failed to subscribe to event bus: {e}")
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logging.info(f"WebSocket connected: {len(self.active_connections)} active")
    
    def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logging.info(f"WebSocket disconnected: {len(self.active_connections)} active")
    
    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast a message to all connected clients."""
        message_json = json.dumps(message)
        for connection in self.active_connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logging.error(f"Failed to send to WebSocket: {e}")
                self.disconnect(connection)
    
    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """Send a message to a specific WebSocket client."""
        await websocket.send_text(json.dumps(message))
    
    def _handle_event(self, event):
        """
        Handle events from UMLAgents event bus.
        Broadcasts event data to all connected WebSocket clients.
        """
        # Convert event to WebSocket message format
        message = {
            "type": "event",
            "event_type": event.type.value,
            "data": event.data,
            "timestamp": event.timestamp
        }
        
        # Schedule broadcast (can't await in sync callback)
        asyncio.create_task(self.broadcast(message))

# Singleton WebSocket manager
ws_manager = WebSocketManager()

# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Main WebSocket endpoint for real‑time communication."""
    await ws_manager.connect(websocket)
    try:
        # Send initial state
        await ws_manager.send_personal_message({
            "type": "connected",
            "timestamp": datetime.now().isoformat(),
            "message": "Connected to UMLAgents WebSocket UI"
        }, websocket)
        
        # Keep connection alive and listen for messages
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await handle_websocket_message(message, websocket)
            except json.JSONDecodeError:
                await ws_manager.send_personal_message({
                    "type": "error",
                    "message": "Invalid JSON message"
                }, websocket)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)

async def handle_websocket_message(message: Dict[str, Any], websocket: WebSocket):
    """Handle incoming WebSocket messages."""
    msg_type = message.get("type")
    
    if msg_type == "pipeline_start":
        await handle_pipeline_start(message, websocket)
    elif msg_type == "ba_interactive":
        await handle_ba_interactive(message, websocket)
    elif msg_type == "load_yaml":
        await handle_load_yaml(message, websocket)
    elif msg_type == "get_project_status":
        await handle_get_project_status(message, websocket)
    elif msg_type == "get_artifact":
        await handle_get_artifact(message, websocket)
    else:
        await ws_manager.send_personal_message({
            "type": "error",
            "message": f"Unknown message type: {msg_type}"
        }, websocket)

async def handle_pipeline_start(message: Dict[str, Any], websocket: WebSocket):
    """Start a pipeline execution."""
    project_id = message.get("project_id", 1)
    agents = message.get("agents", [])
    
    await ws_manager.broadcast({
        "type": "pipeline_started",
        "project_id": project_id,
        "timestamp": datetime.now().isoformat(),
        "message": f"Starting pipeline for project {project_id}"
    })
    
    # Run pipeline in background task
    task = asyncio.create_task(run_pipeline_background(project_id, agents))
    ws_manager.pipeline_tasks[f"pipeline_{project_id}"] = task

async def handle_ba_interactive(message: Dict[str, Any], websocket: WebSocket):
    """Start interactive BA requirement elicitation."""
    project_name = message.get("project_name", "New Project")
    domain = message.get("domain", "General")
    
    await ws_manager.broadcast({
        "type": "ba_interactive_started",
        "project_name": project_name,
        "domain": domain,
        "timestamp": datetime.now().isoformat()
    })
    
    # Create background task for interactive BA
    task = asyncio.create_task(run_ba_interactive_background(project_name, domain, websocket))
    ws_manager.pipeline_tasks[f"ba_{project_name}"] = task

async def handle_load_yaml(message: Dict[str, Any], websocket: WebSocket):
    """Load YAML file into database."""
    yaml_path = message.get("yaml_path")
    if not yaml_path:
        await ws_manager.send_personal_message({
            "type": "error",
            "message": "yaml_path required"
        }, websocket)
        return
    
    await ws_manager.broadcast({
        "type": "yaml_load_started",
        "yaml_path": yaml_path,
        "timestamp": datetime.now().isoformat()
    })
    
    # TODO: Implement YAML loading with progress updates

async def handle_get_project_status(message: Dict[str, Any], websocket: WebSocket):
    """Get current status of a project."""
    project_id = message.get("project_id", 1)
    
    try:
        # Get project from database
        engine = init_db(DB_PATH)
        session = get_session(engine)
        project = session.query(Project).filter(Project.id == project_id).first()
        
        if project:
            # Get recent audit logs
            audit_logs = session.query(AuditLog).filter(
                AuditLog.project_id == project_id
            ).order_by(AuditLog.timestamp.desc()).limit(20).all()
            
            # Get artifacts
            artifacts = session.query(Artifact).filter(
                Artifact.project_id == project_id
            ).all()
            
            response = {
                "type": "project_status",
                "project_id": project.id,
                "project_name": project.name,
                "current_phase": project.current_phase.value if project.current_phase else "unknown",
                "created_at": project.created_at.isoformat() if project.created_at else None,
                "audit_logs": [
                    {
                        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                        "agent_role": log.agent_role.value if log.agent_role else None,
                        "activity": log.activity,
                        "details": log.details
                    }
                    for log in audit_logs
                ],
                "artifacts": [
                    {
                        "id": art.id,
                        "name": art.name,
                        "artifact_type": art.artifact_type.value if art.artifact_type else None,
                        "file_path": art.file_path,
                        "created_at": art.created_at.isoformat() if art.created_at else None
                    }
                    for art in artifacts
                ]
            }
        else:
            response = {
                "type": "error",
                "message": f"Project {project_id} not found"
            }
        
        await ws_manager.send_personal_message(response, websocket)
        session.close()
        
    except Exception as e:
        await ws_manager.send_personal_message({
            "type": "error",
            "message": f"Error getting project status: {str(e)}"
        }, websocket)

async def handle_get_artifact(message: Dict[str, Any], websocket: WebSocket):
    """Get artifact content."""
    artifact_id = message.get("artifact_id")
    if not artifact_id:
        await ws_manager.send_personal_message({
            "type": "error",
            "message": "artifact_id required"
        }, websocket)
        return
    
    try:
        engine = init_db(DB_PATH)
        session = get_session(engine)
        artifact = session.query(Artifact).filter(Artifact.id == artifact_id).first()
        
        if artifact and artifact.file_path and Path(artifact.file_path).exists():
            content = Path(artifact.file_path).read_text(encoding='utf-8', errors='ignore')
            response = {
                "type": "artifact_content",
                "artifact_id": artifact.id,
                "name": artifact.name,
                "artifact_type": artifact.artifact_type.value if artifact.artifact_type else None,
                "content": content,
                "file_path": artifact.file_path
            }
        else:
            response = {
                "type": "error",
                "message": f"Artifact {artifact_id} not found or file missing"
            }
        
        await ws_manager.send_personal_message(response, websocket)
        session.close()
        
    except Exception as e:
        await ws_manager.send_personal_message({
            "type": "error",
            "message": f"Error getting artifact: {str(e)}"
        }, websocket)

# ============================================================================
# Background Tasks
# ============================================================================

async def run_pipeline_background(project_id: int, agents: List[str]):
    """Run pipeline in background with WebSocket progress updates."""
    try:
        engine = init_db(DB_PATH)
        session = get_session(engine)
        
        await ws_manager.broadcast({
            "type": "pipeline_progress",
            "stage": "initializing",
            "project_id": project_id,
            "message": "Initializing orchestrator...",
            "timestamp": datetime.now().isoformat()
        })
        
        # Create orchestrator
        orchestrator = OrchestratorAgent(db_session=session, project_id=project_id)
        
        # Build context
        context = {
            'project_id': project_id,
            'skip_existing': False,
            'agents_to_run': agents if agents else None
        }
        
        await ws_manager.broadcast({
            "type": "pipeline_progress",
            "stage": "starting",
            "project_id": project_id,
            "message": "Starting pipeline execution...",
            "timestamp": datetime.now().isoformat()
        })
        
        # Run pipeline (this is synchronous, consider running in thread pool)
        # For now, we'll simulate progress
        result = orchestrator.run(context)
        
        await ws_manager.broadcast({
            "type": "pipeline_completed",
            "project_id": project_id,
            "result": {
                "success": result.get('success', False),
                "agents_executed": result.get('agents_executed', []),
                "total_time_ms": result.get('total_time_ms', 0),
                "artifacts_generated": len(result.get('artifacts_generated', []))
            },
            "message": f"Pipeline completed in {result.get('total_time_ms', 0)}ms",
            "timestamp": datetime.now().isoformat()
        })
        
        session.close()
        
    except Exception as e:
        await ws_manager.broadcast({
            "type": "pipeline_error",
            "project_id": project_id,
            "message": f"Pipeline failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })

async def run_ba_interactive_background(project_name: str, domain: str, websocket: WebSocket):
    """Run interactive BA requirement elicitation."""
    try:
        engine = init_db(DB_PATH)
        session = get_session(engine)
        
        ba_agent = BAAgent(db_session=session)
        
        # Interactive mode - we'll send questions via WebSocket
        questions = [
            "What is the primary goal of this application?",
            "Who are the main users/actors?",
            "What are the key use cases or scenarios?",
            "Are there any regulatory or compliance requirements?",
            "What are the success criteria for this project?"
        ]
        
        answers = {}
        
        for i, question in enumerate(questions):
            await ws_manager.send_personal_message({
                "type": "ba_question",
                "question": question,
                "question_number": i + 1,
                "total_questions": len(questions),
                "timestamp": datetime.now().isoformat()
            }, websocket)
            
            # Wait for answer (simplified - in real app would wait for WebSocket response)
            await asyncio.sleep(1)  # Placeholder
            answers[question] = "Sample answer"  # Would come from WebSocket
        
        # Create project from answers
        project_data = {
            'name': project_name,
            'domain': domain,
            'description': f"Project created via interactive BA on {datetime.now().isoformat()}",
            'answers': answers
        }
        
        # TODO: Actually create project in database
        
        await ws_manager.send_personal_message({
            "type": "ba_completed",
            "project_name": project_name,
            "project_data": project_data,
            "timestamp": datetime.now().isoformat(),
            "message": "Interactive requirement elicitation completed"
        }, websocket)
        
        session.close()
        
    except Exception as e:
        await ws_manager.send_personal_message({
            "type": "ba_error",
            "message": f"Interactive BA failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }, websocket)

# ============================================================================
# REST API Endpoints
# ============================================================================

class ProjectCreate(BaseModel):
    name: str
    domain: str
    description: Optional[str] = None

@app.get("/")
async def root():
    """Serve the main UI page."""
    html_path = Path(__file__).parent / "templates" / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    else:
        return HTMLResponse("""
        <html>
            <head><title>UMLAgents WebSocket UI</title></head>
            <body>
                <h1>UMLAgents WebSocket UI</h1>
                <p>Frontend not yet built. Use WebSocket at /ws</p>
                <p>API docs: <a href="/api/docs">/api/docs</a></p>
            </body>
        </html>
        """)

@app.get("/api/projects")
async def get_projects():
    """Get list of all projects."""
    try:
        engine = init_db(DB_PATH)
        session = get_session(engine)
        projects = session.query(Project).all()
        result = [
            {
                "id": p.id,
                "name": p.name,
                "domain": p.domain,
                "current_phase": p.current_phase.value if p.current_phase else None,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None
            }
            for p in projects
        ]
        session.close()
        return {"projects": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}")
async def get_project(project_id: int):
    """Get detailed project information."""
    try:
        engine = init_db(DB_PATH)
        session = get_session(engine)
        project = session.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
        
        # Get associated data
        actors = [{"id": a.id, "name": a.name, "role": a.role} for a in project.actors]
        use_cases = [{"id": uc.id, "title": uc.title, "uc_id": uc.uc_id} for uc in project.use_cases]
        artifacts = [
            {
                "id": a.id,
                "name": a.name,
                "artifact_type": a.artifact_type.value if a.artifact_type else None,
                "file_path": a.file_path,
                "created_at": a.created_at.isoformat() if a.created_at else None
            }
            for a in project.artifacts
        ]
        
        result = {
            "id": project.id,
            "name": project.name,
            "domain": project.domain,
            "description": project.description,
            "current_phase": project.current_phase.value if project.current_phase else None,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
            "actors": actors,
            "use_cases": use_cases,
            "artifacts": artifacts
        }
        session.close()
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects")
async def create_project(project: ProjectCreate):
    """Create a new project."""
    try:
        engine = init_db(DB_PATH)
        session = get_session(engine)
        
        new_project = Project(
            name=project.name,
            domain=project.domain,
            description=project.description,
            current_phase=Phase.INCEPTION
        )
        session.add(new_project)
        session.commit()
        session.refresh(new_project)
        
        result = {
            "id": new_project.id,
            "name": new_project.name,
            "domain": new_project.domain,
            "current_phase": new_project.current_phase.value,
            "created_at": new_project.created_at.isoformat() if new_project.created_at else None
        }
        session.close()
        
        # Broadcast via WebSocket
        await ws_manager.broadcast({
            "type": "project_created",
            "project": result,
            "timestamp": datetime.now().isoformat()
        })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/artifacts/{artifact_id}/content")
async def get_artifact_content(artifact_id: int):
    """Get the content of an artifact."""
    try:
        engine = init_db(DB_PATH)
        session = get_session(engine)
        artifact = session.query(Artifact).filter(Artifact.id == artifact_id).first()
        
        if not artifact:
            raise HTTPException(status_code=404, detail=f"Artifact {artifact_id} not found")
        
        if not artifact.file_path or not Path(artifact.file_path).exists():
            raise HTTPException(status_code=404, detail=f"Artifact file not found: {artifact.file_path}")
        
        content = Path(artifact.file_path).read_text(encoding='utf-8', errors='ignore')
        
        result = {
            "id": artifact.id,
            "name": artifact.name,
            "artifact_type": artifact.artifact_type.value if artifact.artifact_type else None,
            "content": content,
            "file_path": artifact.file_path,
            "created_at": artifact.created_at.isoformat() if artifact.created_at else None
        }
        session.close()
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "websocket_connections": len(ws_manager.active_connections),
        "active_pipelines": len(ws_manager.pipeline_tasks)
    }

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print(f"Starting UMLAgents WebSocket UI on {HOST}:{PORT}")
    print(f"Database: {DB_PATH}")
    print(f"Debug mode: {DEBUG}")
    print(f"WebSocket endpoint: ws://{HOST}:{PORT}/ws")
    print(f"API docs: http://{HOST}:{PORT}/api/docs")
    print(f"Health check: http://{HOST}:{PORT}/api/health")
    
    uvicorn.run(
        "app:app",
        host=HOST,
        port=PORT,
        log_level="debug" if DEBUG else "info",
        reload=DEBUG,
    )