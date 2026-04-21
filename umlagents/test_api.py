#!/usr/bin/env python3
"""
Test DeepSeek API key.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from umlagents.agents.base import BaseAgent
from umlagents.db.models import init_db, get_session, AgentRole

# Test API key
api_key = os.getenv("DEEPSEEK_API_KEY")
print(f"API Key configured: {'Yes' if api_key and api_key != 'your_deepseek_api_key_here' else 'No'}")
if api_key:
    print(f"Key starts with: {api_key[:10]}...")

# Create a base agent
engine = init_db("test_api.db")
session = get_session(engine)
agent = BaseAgent(
    name="TestAgent",
    system_prompt="You are a test assistant.",
    agent_role=AgentRole.BA,
    db_session=session
)

# Test simple API call
print("\nTesting API call...")
try:
    response = agent.call_deepseek("Hello, please respond with 'API test successful'", temperature=0.1, max_tokens=50)
    print(f"✅ API call successful!")
    print(f"Response: {response}")
except Exception as e:
    print(f"❌ API call failed: {e}")
    import traceback
    traceback.print_exc()

session.close()