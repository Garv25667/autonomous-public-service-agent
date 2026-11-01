import os
import io
import json
import base64
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.unified_runner import UnifiedRunner
from agent.tools.entity_extractor import EntityExtractor
from agent.service_catalog import ServiceCatalog
from agent.states import RunState
from agent.checkpoint import Checkpointer
from agent.eligibility import EligibilityEvaluator
from agent.tools.docs import DocumentProcessor
from agent.llm.conversation_agent import GeminiConversationAgent

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="Autonomous Public Service & Bureaucracy Execution Agent API", version="2.0.0")

# Active WebSocket connections: run_id -> list of WebSockets
connections: Dict[str, List[WebSocket]] = {}
checkpointer = Checkpointer()
evaluator = EligibilityEvaluator()
doc_processor = DocumentProcessor()
catalog = ServiceCatalog()
entity_extractor = EntityExtractor()
conv_agent = GeminiConversationAgent()
main_loop: Optional[asyncio.AbstractEventLoop] = None
executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

# Global runner instance
async def _broadcast_handler(msg: Dict[str, Any]):
    global main_loop
    if main_loop and main_loop.is_running():
        asyncio.run_coroutine_threadsafe(broadcast_to_run("active", msg), main_loop)
    else:
        await broadcast_to_run("active", msg)

runner = UnifiedRunner(broadcast_callback=_broadcast_handler)


@app.on_event("startup")
def on_startup():
    global main_loop
    try:
        main_loop = asyncio.get_running_loop()
    except Exception:
        pass


class ApprovalRequest(BaseModel):
    run_id: str
    approved: bool


class GateSolveRequest(BaseModel):
    run_id: Optional[str] = "active"
    captcha: Optional[str] = None
    otp: Optional[str] = None
    action: Optional[str] = "continue"


class DocumentUploadRequest(BaseModel):
    filename: Optional[str] = "document.pdf"
    content_base64: Optional[str] = None
    text_content: Optional[str] = None


class ChatMessageRequest(BaseModel):
    message: str


class RunDispatchRequest(BaseModel):
    service: str = "scholarship"  # 'scholarship', 'parivahan_dl', 'nsp', 'universal'
    target_url: Optional[str] = None
    headless: bool = False
    dry_run: bool = False


async def broadcast_to_run(run_id: str, message: Dict[str, Any]):
    """Broadcasts a message to all connected clients for a run."""
    ws_list = connections.get(run_id, [])
    for ws in list(ws_list):
        try:
            await ws.send_json(message)
        except Exception:
            if ws in ws_list:
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
    return {"status": "success", "message": "Profile updated successfully", "profile": data}


@app.get("/api/services")
def list_available_services():
    """Lists all public service catalog offerings."""
    return catalog.list_services()


@app.get("/api/eligibility")
def check_eligibility(service_id: str = "scholarship"):
    profile_path = ROOT / "data" / "citizen.json"
    profile = {}
    if profile_path.exists():
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)
    try:
        result = catalog.evaluate_service(service_id, profile)
        return result.model_dump()
    except Exception as e:
        return {
            "service_id": service_id,
            "service_name": service_id.replace("_", " ").title(),
            "authority": "Public Authority",
            "portal_url": "",
            "eligible": False,
            "reasons": [str(e)],
            "friendly_explanation": f"Evaluation notice: {str(e)}",
            "required_documents": [],
            "actionable_checklist": []
        }


@app.post("/api/upload-doc")
def upload_and_parse_document(req: DocumentUploadRequest):
    """
    Ingests ANY uploaded PDF, image, or text file, extracts citizen entities,
    and updates data/citizen.json.
    """
    if req.content_base64:
        extracted = entity_extractor.extract_from_base64(req.content_base64, filename=req.filename)
    elif req.text_content:
        extracted = entity_extractor.extract_from_text(req.text_content)
    else:
        raise HTTPException(status_code=400, detail="Either content_base64 or text_content must be provided.")

    updated_profile = entity_extractor.update_citizen_profile(extracted)
    return {
        "status": "success",
        "extracted_entities": extracted,
        "updated_profile": updated_profile,
        "message": f"Successfully parsed {len(extracted)} citizen attributes from document."
    }


@app.post("/api/chat")
def chat_with_agent(req: ChatMessageRequest):
    """
    Conversational agent interface powered by Gemini with local confidential tool execution.
    Extracts entities from user text, identifies intent (e.g. DL renewal, scholarship, custom URL),
    and suggests next actions.
    """
    msg = req.message.strip()
    extracted = entity_extractor.extract_from_text(msg)

    # If any citizen entities found in the chat message, update profile locally
    if extracted:
        entity_extractor.update_citizen_profile(extracted)

    # Converse via Gemini with local tool execution
    result = conv_agent.chat(msg)

    # If silent mode resume signaled
    if result.get("resume_gate"):
        runner.resolve_gate({"action": "continue"})

    return {
        "reply": result["reply"],
        "extracted_entities": extracted,
        "service_recommendation": result.get("service_recommendation"),
        "target_url": result.get("target_url"),
        "auto_trigger": result.get("auto_trigger", False),
        "powered_by": result.get("powered_by", "gemini")
    }


def _run_worker(chosen_service: str, target_url: Optional[str], is_headless: bool, is_dry: bool, base_url: str):
    """Runs Playwright inside a dedicated ProactorEventLoop worker on Windows."""
    loop = asyncio.ProactorEventLoop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            runner.execute(
                service=chosen_service,
                target_url=target_url,
                headless=is_headless,
                dry_run=is_dry,
                base_url=base_url
            )
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        err_msg = str(e).strip() or f"{type(e).__name__}: Execution stopped unexpectedly"
        if main_loop and main_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                broadcast_to_run("active", {"event": "run_error", "data": {"error": err_msg}}),
                main_loop
            )
    finally:
        try:
            loop.close()
        except Exception:
            pass


@app.post("/api/run")
async def start_unified_run(
    request: Request,
    payload: Optional[RunDispatchRequest] = None,
    service: Optional[str] = None,
    headless: bool = False,
    dry_run: bool = False
):
    """Starts autonomous execution in a dedicated Windows Proactor background worker."""
    chosen_service = payload.service if payload else (service or "scholarship")
    target_url = payload.target_url if payload else None
    is_headless = payload.headless if payload else headless
    is_dry = payload.dry_run if payload else dry_run
    base_url = str(request.base_url)

    # Route to specialized co-pilots based on target URL and service
    if target_url and "sarathi.parivahan" in target_url:
        chosen_service = "parivahan_dl"
    elif target_url and chosen_service in ["scholarship", "mock_sandbox"]:
        chosen_service = "universal"

    # Launch in dedicated worker thread with Proactor loop (prevents NotImplementedError on Windows)
    executor.submit(_run_worker, chosen_service, target_url, is_headless, is_dry, base_url)

    return {
        "status": "started",
        "service": chosen_service,
        "message": f"Autonomous execution for service '{chosen_service}' initiated in background."
    }


@app.post("/api/gate-solve")
def solve_human_gate(req: GateSolveRequest):
    """Delivers citizen human gate solution (CAPTCHA, OTP, Approval) to the active runner."""
    runner.resolve_gate(req.model_dump())
    return {"status": "success", "message": "Gate response delivered to agent runner."}


@app.get("/api/runs")
def list_runs():
    return checkpointer.list_runs()


@app.get("/api/runs/{run_id}")
def get_run_details(run_id: str):
    state = checkpointer.load(run_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return state.model_dump()


@app.websocket("/ws/live/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    """Streams live step logs, screencast frames, and prompts to the browser UI."""
    await websocket.accept()
    if run_id not in connections:
        connections[run_id] = []
    connections[run_id].append(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            # If UI sends a gate solve or command over websocket
            try:
                parsed = json.loads(data)
                if parsed.get("type") == "gate_solve":
                    runner.resolve_gate(parsed.get("data", {}))
            except Exception:
                pass
    except WebSocketDisconnect:
        if websocket in connections.get(run_id, []):
            connections[run_id].remove(websocket)


@app.get("/scholarship-form", response_class=HTMLResponse)
@app.get("/scholarship-form.html", response_class=HTMLResponse)
def serve_scholarship_form():
    """Serves the standalone live scholarship application form."""
    candidates = [
        ROOT / "docs" / "scholarship-form.html",
        ROOT / "web" / "live_scholarship_form.html",
        ROOT / "web" / "scholarship-form.html"
    ]
    for form_path in candidates:
        if form_path.exists():
            with open(form_path, "r", encoding="utf-8") as f:
                return f.read()
    return HTMLResponse("<h1>Scholarship Form not found.</h1>", status_code=404)


@app.get("/parivahan-form", response_class=HTMLResponse)
@app.get("/parivahan-form.html", response_class=HTMLResponse)
def serve_parivahan_form():
    """Serves the standalone live MoRTH Parivahan Sarathi DL renewal form."""
    candidates = [
        ROOT / "docs" / "parivahan-form.html",
        ROOT / "web" / "live_parivahan_form.html",
        ROOT / "web" / "parivahan-form.html"
    ]
    for form_path in candidates:
        if form_path.exists():
            with open(form_path, "r", encoding="utf-8") as f:
                return f.read()
    return HTMLResponse("<h1>Parivahan Form not found.</h1>", status_code=404)


@app.get("/presentation", response_class=HTMLResponse)
@app.get("/presentation.html", response_class=HTMLResponse)
def serve_presentation():
    """Serves the 7-Slide Pitch Deck Presentation."""
    candidates = [
        ROOT / "docs" / "presentation.html",
        ROOT / "web" / "presentation.html"
    ]
    for deck_path in candidates:
        if deck_path.exists():
            with open(deck_path, "r", encoding="utf-8") as f:
                return f.read()
    return HTMLResponse("<h1>Presentation not found.</h1>", status_code=404)


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serves the Unified Agent Web Dashboard."""
    web_index = ROOT / "web" / "index.html"
    if not web_index.exists():
        return HTMLResponse("<h1>Web Dashboard Index not found.</h1>", status_code=404)
    with open(web_index, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8001, reload=True)
