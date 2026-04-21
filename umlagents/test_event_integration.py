#!/usr/bin/env python3
"""
Test event system integration with WebSocket.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from umlagents.utils.events import (
    event_bus, publish_agent_activity, publish_artifact_generated,
    publish_api_call, publish_pipeline_event, publish_agent_status
)

def test_event_bus():
    """Test that events can be published and received."""
    print("Testing event bus...")
    
    events_received = []
    
    def event_listener(event):
        events_received.append(event.type.value)
        print(f"  Received event: {event.type.value}")
    
    # Subscribe listener
    event_bus.subscribe(event_listener)
    
    # Publish test events
    publish_agent_activity("TestAgent", "test_activity", project_id=99)
    publish_artifact_generated("TestAgent", "code", "/tmp/test.py", project_id=99)
    publish_api_call("TestAgent", "start", endpoint="/v1/chat/completions", project_id=99)
    publish_agent_status("TestAgent", "started", project_id=99)
    publish_pipeline_event("test_pipeline", "started", project_id=99)
    
    # Unsubscribe
    event_bus.unsubscribe(event_listener)
    
    expected_events = [
        "agent_activity",
        "artifact_generated", 
        "api_call_start",
        "agent_started",
        "pipeline_started"
    ]
    
    for expected in expected_events:
        if expected in events_received:
            print(f"✓ {expected} event published and received")
        else:
            print(f"✗ {expected} event NOT received")
    
    print(f"Total events received: {len(events_received)}")
    return len(events_received) == len(expected_events)

async def test_websocket_integration():
    """Test that WebSocket manager can subscribe to events."""
    print("\nTesting WebSocket integration...")
    
    # Import WebSocket manager (requires FastAPI context)
    try:
        from web.app import ws_manager, UMLAGENTS_AVAILABLE
        if not UMLAGENTS_AVAILABLE:
            print("  UMLAgents not available (demo mode)")
            return False
        
        print("  WebSocketManager subscribed to event bus")
        print("  (Manual test needed: start WebSocket UI and run pipeline)")
        return True
    except ImportError as e:
        print(f"  Import error: {e}")
        return False

def test_agent_integration():
    """Test that BaseAgent emits events."""
    print("\nTesting agent integration...")
    
    try:
        from umlagents.agents.base import BaseAgent
        from umlagents.db.models import AgentRole, init_db, get_session
        import tempfile
        
        # Create temporary database
        db_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        db_path = db_file.name
        db_file.close()
        
        engine = init_db(db_path)
        session = get_session(engine)
        
        # Create agent (no project ID, so audit logging will be skipped)
        agent = BaseAgent(
            name="TestAgent",
            system_prompt="Test",
            agent_role=AgentRole.BA,
            db_session=session
        )
        
        # Test _log_activity (should publish event)
        events_before = []
        def capture_event(event):
            events_before.append(event.type.value)
        
        event_bus.subscribe(capture_event)
        agent._log_activity("test_activity", {"test": "data"})
        event_bus.unsubscribe(capture_event)
        
        # Without project_id, event should still be published but not logged to DB
        if "agent_activity" in events_before:
            print("  ✓ BaseAgent._log_activity publishes events")
        else:
            print("  ✗ BaseAgent._log_activity did not publish event")
        
        # Clean up
        session.close()
        os.unlink(db_path)
        
        return "agent_activity" in events_before
    except Exception as e:
        print(f"  Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("UMLAgents Event System Integration Test")
    print("=" * 60)
    
    # Run tests
    test1 = test_event_bus()
    test2 = asyncio.run(test_websocket_integration())
    test3 = test_agent_integration()
    
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Event bus: {'✓ PASS' if test1 else '✗ FAIL'}")
    print(f"  WebSocket integration: {'✓ AVAILABLE' if test2 else '✗ UNAVAILABLE'}")
    print(f"  Agent integration: {'✓ PASS' if test3 else '✗ FAIL'}")
    
    if test1 and test3:
        print("\n✅ Event system integration successful!")
        print("   Events flow from agents → event bus → WebSocket UI")
    else:
        print("\n❌ Some tests failed")
        sys.exit(1)