# Quick Test - UMLAgents Web UI

Run this after setting up to verify everything works:

## 1. Start Server
```powershell
cd umlagents
$env:DEEPSEEK_API_KEY="sk-your-key-here"  # If not set permanently
uvicorn web.app:app --host 0.0.0.0 --port 8080 --reload
```

## 2. Open Browser Tests
Open these URLs in your browser:

### **Health Check**  
http://localhost:8080/api/health  
✅ Should show: `{"status":"healthy",...}`

### **API Key Test**  
http://localhost:8080/api/test-key  
✅ Should show: `"key_loaded": true` with your key preview

### **Web UI**  
http://localhost:8080  
✅ Should show UMLAgents dashboard with navigation tabs

## 3. Test Workflow

### **A. Reset Database (optional)**
1. Go to **Dashboard** tab
2. Click **"Reset Everything"** (red button)
3. Confirm warning dialog
4. Check **Recent Activity**: "Reset completed"

### **B. Upload YAML**
1. Go to **Requirements** tab  
2. **Drag & drop** `examples/dice-game-example.yaml` onto file upload area
3. Or click **Upload** after selecting file
4. Watch **Recent Activity**: "Uploaded: ...", "Loading YAML: ..."
5. Should end with: "YAML loaded: X actors, Y use cases"

### **C. Run Pipeline**
1. Go to **Pipeline Control** tab
2. Select **"Dice Game"** from dropdown
3. Click **"Start Pipeline"**
4. Watch **Live Logs** for agent progress
5. Should complete with: "Pipeline completed in Xms"

## 4. Expected Results

| Test | Expected |
|------|----------|
| **Server starts** | No errors, "Loaded environment from .env" |
| **API key loaded** | `✅ DEEPSEEK_API_KEY loaded: sk-...` |
| **Health endpoint** | HTTP 200 with "healthy" status |
| **Key test endpoint** | `"key_loaded": true` |
| **WebSocket connection** | Browser console: "WebSocket connected" |
| **YAML upload** | Progress messages, project appears in list |
| **Pipeline execution** | Agents run sequentially, completion message |

## 5. Common Issues & Fixes

### **Issue: 401 Unauthorized in pipeline**
**Fix:** API key not loaded in web server process
```powershell
# Stop server (Ctrl+C)
# Set environment variable
$env:DEEPSEEK_API_KEY="sk-your-key-here"
# Restart server
uvicorn web.app:app --host 0.0.0.0 --port 8080 --reload
```

### **Issue: "ModuleNotFoundError: No module named 'web.app'"**
**Fix:** Wrong working directory
```powershell
# Make sure you're in umlagents project root
cd umlagents
pwd  # Should show umlagents directory
```

### **Issue: Database locked/corrupted**
**Fix:** Reset via API or web UI
```powershell
# Via curl (server must be running)
curl -X POST http://localhost:8080/api/reset
# Or use web UI: Dashboard → "Reset Everything"
```

### **Issue: WebSocket not connecting**
**Fix:** Clear browser cache or check firewall
1. Open browser developer tools (F12)
2. Go to Console tab
3. Look for WebSocket connection errors
4. Try different browser or incognito mode

## 6. Success Indicators

✅ **Green "Connected" badge** in top-right of web UI  
✅ **Recent Activity** shows upload and pipeline events  
✅ **Pipeline progress bar** moves from 0% to 100%  
✅ **Live Logs** show agent execution  
✅ **Projects list** updates after YAML load  

## 7. Advanced Testing

### **Test CLI (optional)**
```powershell
# List projects
umlagents list

# Load YAML via CLI
umlagents load-yaml examples/dice-game-example.yaml

# Run pipeline via CLI
umlagents orchestrate 1 --agents BAAgent  # Use --agents flag
```

### **Test Multiple Projects**
1. Upload `examples/healthsync-example.yaml`
2. Check Projects tab → should show 2 projects
3. Run pipeline on HealthSync project

---

**All tests pass?** → UMLAgents is fully operational on your laptop! 🎉

**Any issues?** → Check error messages, ensure API key is set, and restart server with environment variable.