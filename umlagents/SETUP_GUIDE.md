# UMLAgents Setup Guide for Your Laptop

## Prerequisites

1. **Python 3.10+** (recommended: 3.10-3.12)
2. **Git** (for cloning repository)
3. **DeepSeek API Key** (from [platform.deepseek.com](https://platform.deepseek.com/))

## Step 1: Clone and Setup

```powershell
# Clone the repository
git clone <repository-url>
cd umlagents

# Create and activate virtual environment (recommended)
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install with web UI support
pip install -e .[web]
```

**Alternative with Conda:**
```powershell
conda create -n umlagents python=3.10
conda activate umlagents
pip install -e .[web]
```

## Step 2: Configure API Key

### **IMPORTANT for Windows:** Set system environment variable
```powershell
# Set API key for current session (temporary)
$env:DEEPSEEK_API_KEY="sk-your-key-here"
$env:DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"

# OR set permanently (requires Admin):
[System.Environment]::SetEnvironmentVariable('DEEPSEEK_API_KEY', 'sk-your-key-here', 'Machine')
[System.Environment]::SetEnvironmentVariable('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1', 'Machine')

# Restart PowerShell after permanent change
```

### **Also create `.env` file** (backup):
```bash
# In project root, create .env file with:
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

## Step 3: Verify Installation

```powershell
# Test imports
python -c "import web.app; print('✅ Web app imports work')"

# Test API key loading
python -c "
import os
from dotenv import load_dotenv
load_dotenv('.env')
key = os.getenv('DEEPSEEK_API_KEY')
print(f'Key loaded: {key[:8] if key else None}')
"
```

## Step 4: Start Web Server

```powershell
# Start with auto-reload (development)
uvicorn web.app:app --host 0.0.0.0 --port 8080 --reload

# Or without reload (production)
uvicorn web.app:app --host 0.0.0.0 --port 8080
```

**Expected output:**
```
Loaded environment from .env
✅ DEEPSEEK_API_KEY loaded: sk-3725d...
Starting UMLAgents WebSocket UI on 0.0.0.0:8080
Database: umlagents.db
Debug mode: True
WebSocket endpoint: ws://0.0.0.0:8080/ws
API docs: http://0.0.0.0:8080/api/docs
Health check: http://0.0.0.0:8080/api/health
```

## Step 5: Open Browser

Open: **http://localhost:8080**

## 🎯 Quick Test Workflow

### **Option A: Upload Example YAML**
1. **Reset** (optional) → Dashboard → "Reset Everything"
2. **Upload** → Requirements tab → drag `examples/dice-game-example.yaml`
3. **Run Pipeline** → Pipeline Control → select "Dice Game" → Start Pipeline

### **Option B: Manual Path**
1. **Load YAML** → Requirements tab → enter `examples/dice-game-example.yaml` → Load
2. **Run Pipeline** → Pipeline Control → select project → Start Pipeline

## 🔧 Troubleshooting

### **"uvicorn not recognized" (Conda)**
```powershell
pip install uvicorn[standard]
```

### **API Key Not Loading (401 errors)**
```powershell
# Check if key is loaded in web server process
# Visit: http://localhost:8080/api/test-key

# Temporary fix: Set environment variable before starting server
$env:DEEPSEEK_API_KEY="sk-your-key-here"
uvicorn web.app:app --host 0.0.0.0 --port 8080 --reload
```

### **Database Locked/Corrupted**
```powershell
# Reset via API (requires server running)
curl -X POST http://localhost:8080/api/reset
# Or use web UI: Dashboard → "Reset Everything"
```

### **WebSocket Connection Failed**
- Check firewall allows port 8080
- Use `--host 0.0.0.0` for network access
- Clear browser cache if UI doesn't update

## 📊 Verify Everything Works

1. **API Key:** http://localhost:8080/api/test-key → "API key is loaded and valid"
2. **Health:** http://localhost:8080/api/health → "healthy"
3. **Projects:** http://localhost:8080/api/projects → list of projects
4. **WebSocket:** Open browser console → "WebSocket connected"
5. **Upload:** Drag YAML file → see progress in Recent Activity

## 🚀 Complete Web‑Only Features

✅ **Drag‑and‑drop YAML upload**  
✅ **Database reset from browser**  
✅ **Real‑time pipeline monitoring**  
✅ **API key validation**  
✅ **No terminal needed after server start**

## 📞 Need Help?

Check:
1. `README.md` – Detailed documentation
2. `CHANGES_SUMMARY.md` – What's new
3. Web UI → API Docs: http://localhost:8080/api/docs

**Your API key is the only external dependency.** Once set as system environment variable, everything works through the browser.