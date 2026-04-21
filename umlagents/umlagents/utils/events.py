"""
Event system for UMLAgents to enable real‑time monitoring.
Provides publish‑subscribe pattern for agent activities, artifact generation, and pipeline events.
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Callable, List, Optional
import threading
from enum import Enum


class EventType(Enum):
    """Types of events that can be emitted."""
    AGENT_ACTIVITY = "agent_activity"
    ARTIFACT_GENERATED = "artifact_generated"
    API_CALL_START = "api_call_start"
    API_CALL_SUCCESS = "api_call_success"
    API_CALL_FAILED = "api_call_failed"
    PROJECT_CREATED = "project_created"
    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_COMPLETED = "pipeline_completed"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"


class Event:
    """An event with type, data, and timestamp."""
    
    def __init__(self, event_type: EventType, data: Dict[str, Any]):
        self.type = event_type
        self.data = data
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        return {
            "type": self.type.value,
            "data": self.data,
            "timestamp": self.timestamp
        }
    
    def to_json(self) -> str:
        """Serialize event to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class EventBus:
    """
    Simple event bus for publish‑subscribe pattern.
    Supports both synchronous and asynchronous listeners.
    """
    
    def __init__(self):
        self._listeners: List[Callable[[Event], None]] = []
        self._async_listeners: List[Callable[[Event], Any]] = []
        self._lock = threading.Lock()
    
    def subscribe(self, callback: Callable[[Event], None]) -> None:
        """Subscribe a synchronous callback to events."""
        with self._lock:
            self._listeners.append(callback)
    
    def subscribe_async(self, callback: Callable[[Event], Any]) -> None:
        """Subscribe an asynchronous callback to events."""
        with self._lock:
            self._async_listeners.append(callback)
    
    def unsubscribe(self, callback: Callable[[Event], None]) -> None:
        """Unsubscribe a synchronous callback."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)
    
    def unsubscribe_async(self, callback: Callable[[Event], Any]) -> None:
        """Unsubscribe an asynchronous callback."""
        with self._lock:
            if callback in self._async_listeners:
                self._async_listeners.remove(callback)
    
    def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers.
        Synchronous callbacks are called immediately.
        Asynchronous callbacks are scheduled as tasks.
        """
        # Call synchronous listeners
        for listener in self._listeners[:]:  # copy in case of modification
            try:
                listener(event)
            except Exception as e:
                print(f"Error in event listener: {e}")
        
        # Schedule async listeners
        if self._async_listeners:
            for listener in self._async_listeners[:]:
                try:
                    # Create task if we're in an event loop, otherwise run directly
                    asyncio.create_task(listener(event))
                except RuntimeError:
                    # No event loop in this thread, run in background thread
                    threading.Thread(
                        target=self._run_async_listener,
                        args=(listener, event),
                        daemon=True
                    ).start()
                except Exception as e:
                    print(f"Error scheduling async event listener: {e}")
    
    def _run_async_listener(self, listener: Callable[[Event], Any], event: Event) -> None:
        """Run async listener in a new event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(listener(event))
        except Exception as e:
            print(f"Error in async event listener: {e}")
        finally:
            loop.close()


# Global event bus instance
event_bus = EventBus()


# Convenience functions for common events
def publish_agent_activity(
    agent_name: str,
    activity: str,
    project_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """Publish an agent activity event."""
    event_data = {
        "agent": agent_name,
        "activity": activity,
    }
    if project_id is not None:
        event_data["project_id"] = project_id
    if details:
        event_data["details"] = details
    
    event = Event(EventType.AGENT_ACTIVITY, event_data)
    event_bus.publish(event)


def publish_artifact_generated(
    agent_name: str,
    artifact_type: str,
    filepath: str,
    project_id: Optional[int] = None,
    content_hash: Optional[str] = None,
    content_length: Optional[int] = None
) -> None:
    """Publish an artifact generated event."""
    event_data = {
        "agent": agent_name,
        "artifact_type": artifact_type,
        "filepath": filepath,
    }
    if project_id is not None:
        event_data["project_id"] = project_id
    if content_hash:
        event_data["content_hash"] = content_hash
    if content_length is not None:
        event_data["content_length"] = content_length
    
    event = Event(EventType.ARTIFACT_GENERATED, event_data)
    event_bus.publish(event)


def publish_api_call(
    agent_name: str,
    status: str,  # "start", "success", "failed"
    endpoint: Optional[str] = None,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None,
    project_id: Optional[int] = None
) -> None:
    """Publish an API call event."""
    if status == "start":
        event_type = EventType.API_CALL_START
    elif status == "success":
        event_type = EventType.API_CALL_SUCCESS
    else:
        event_type = EventType.API_CALL_FAILED
    
    event_data = {
        "agent": agent_name,
        "status": status,
    }
    if endpoint:
        event_data["endpoint"] = endpoint
    if duration_ms is not None:
        event_data["duration_ms"] = duration_ms
    if error:
        event_data["error"] = error
    if project_id is not None:
        event_data["project_id"] = project_id
    
    event = Event(event_type, event_data)
    event_bus.publish(event)


def publish_pipeline_event(
    pipeline_id: str,
    event_type: str,  # "started", "completed"
    project_id: Optional[int] = None,
    agents: Optional[List[str]] = None,
    error: Optional[str] = None
) -> None:
    """Publish a pipeline event."""
    if event_type == "started":
        event_type_enum = EventType.PIPELINE_STARTED
    else:
        event_type_enum = EventType.PIPELINE_COMPLETED
    
    event_data = {
        "pipeline_id": pipeline_id,
        "status": event_type,
    }
    if project_id is not None:
        event_data["project_id"] = project_id
    if agents:
        event_data["agents"] = agents
    if error:
        event_data["error"] = error
    
    event = Event(event_type_enum, event_data)
    event_bus.publish(event)


def publish_agent_status(
    agent_name: str,
    status: str,  # "started", "completed"
    project_id: Optional[int] = None,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None
) -> None:
    """Publish an agent status event."""
    if status == "started":
        event_type = EventType.AGENT_STARTED
    else:
        event_type = EventType.AGENT_COMPLETED
    
    event_data = {
        "agent": agent_name,
        "status": status,
    }
    if project_id is not None:
        event_data["project_id"] = project_id
    if duration_ms is not None:
        event_data["duration_ms"] = duration_ms
    if error:
        event_data["error"] = error
    
    event = Event(event_type, event_data)
    event_bus.publish(event)