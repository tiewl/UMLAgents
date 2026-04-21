#!/usr/bin/env python3
"""Test the new web endpoints."""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from web.app import app

client = TestClient(app)

print("=== Testing new UMLAgents web endpoints ===\n")

# Test 1: Health check
print("1. Testing /api/health")
response = client.get("/api/health")
print(f"   Status: {response.status_code}")
print(f"   Response: {response.json()}")
print()

# Test 2: Test API key endpoint
print("2. Testing /api/test-key")
response = client.get("/api/test-key")
data = response.json()
print(f"   Status: {response.status_code}")
print(f"   Success: {data.get('success')}")
print(f"   Key loaded: {data.get('key_loaded')}")
print(f"   Key preview: {data.get('key_preview')}")
print(f"   Message: {data.get('message')}")
print()

# Test 3: Upload endpoint (without file)
print("3. Testing /api/upload-yaml (POST without file)")
response = client.post("/api/upload-yaml")
print(f"   Status: {response.status_code}")
print(f"   Expected: 422 (validation error)")
print()

# Test 4: Reset endpoint (GET instead of POST - should fail)
print("4. Testing /api/reset (GET instead of POST)")
response = client.get("/api/reset")
print(f"   Status: {response.status_code}")
print(f"   Expected: 405 (method not allowed)")
print()

# Test 5: Projects list
print("5. Testing /api/projects")
response = client.get("/api/projects")
print(f"   Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"   Projects count: {len(data.get('projects', []))}")
else:
    print(f"   Error: {response.text[:100]}")

print("\n=== All tests completed ===")