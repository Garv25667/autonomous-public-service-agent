import os
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.orchestrator import AgentOrchestrator
from agent.states import RunState
from agent.checkpoint import Checkpointer
from agent.eligibility import EligibilityEvaluator
from agent.tools.docs import DocumentProcessor

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="Public Service Automation Agent API", version="1.0.0")

# Active WebSocket connections: run_id -> list of WebSockets
connections: Dict[str, List[WebSocket]] = {}
checkpointer = Checkpointer()
evaluator = EligibilityEvaluator()
doc_processor = DocumentProcessor()


class ApprovalRequest(BaseModel):
    run_id: str
    approved: bool


class GateSolveRequest(BaseModel):
    run_id: str
    captcha: Optional[str] = None
    otp: Optional[str] = None


async def broadcast_to_run(run_id: str, message: Dict[str, Any]):
    """Broadcasts a message to all connected clients for a run."""
    ws_list = connections.get(run_id, [])
    for ws in list(ws_list):
        try:
            await ws.send_json(message)
        except Exception:
            ws_list.remove(ws)


@app.get("/api/profile")
def get_profile():
    profile_path = ROOT / "data" / "citizen.json"
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail="Citizen profile not found")
    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/profile")
def update_profile(data: Dict[str, Any]):
    profile_path = ROOT / "data" / "citizen.json"
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return {"status": "success", "message": "Profile updated successfully"}


@app.get("/api/eligibility")
def check_eligibility():
    profile_path = ROOT / "data" / "citizen.json"
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)
    result = evaluator.evaluate(profile)
    return result.model_dump()


@app.get("/api/runs")
def list_runs():
    return checkpointer.list_runs()


@app.get("/api/runs/{run_id}")
def get_run_details(run_id: str):
    state = checkpointer.load(run_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return state.model_dump()


@app.post("/api/run")
async def start_agent_run(background_tasks: BackgroundTasks, headless: bool = False, dry_run: bool = False):
    """Starts an autonomous agent run in the background."""
    profile_path = ROOT / "data" / "citizen.json"

    async def _run_agent():
        orchestrator = AgentOrchestrator(
            headless=headless,
            dry_run=dry_run,
            broadcast_callback=lambda event: broadcast_to_run("active", event)
        )
        try:
            await orchestrator.run(profile_path=profile_path)
        except Exception as e:
            await broadcast_to_run("active", {"event": "run_error", "data": {"error": str(e)}})

    background_tasks.add_task(_run_agent)
    return {"status": "started", "message": "Agent execution launched in background."}


@app.websocket("/ws/live/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    """Streams live step logs, screencast frames, and prompts to the browser UI."""
    await websocket.accept()
    if run_id not in connections:
        connections[run_id] = []
    connections[run_id].append(websocket)

    try:
        while True:
            # Keep socket alive and accept incoming messages from UI
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        connections[run_id].remove(websocket)


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serves the citizen dashboard single-page interface."""
    web_index = ROOT / "web" / "index.html"
    if not web_index.exists():
        return HTMLResponse("<h1>Web Dashboard Index not found.</h1>", status_code=404)
    with open(web_index, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
