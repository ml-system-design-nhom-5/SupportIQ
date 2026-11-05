import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Any, Dict
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from apps.demo.store import DemoStore
from apps.demo.service import DemoService, DemoRunRequest, DemoFeedbackRequest

STATIC_DIR = Path(__file__).parent / "static"

def create_app(
    db_path: Optional[str] = None,
    runner: Optional[PipelineRunner] = None,
    intent_client: Optional[Any] = None,
    health_metadata: Optional[Dict[str, Any]] = None,
) -> FastAPI:
    demo_store = DemoStore(db_path=db_path)
    if runner is None:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        p_store = PersistentStore(db_path=db_path)
        runner = PipelineRunner(intent_client=intent_client, store=p_store)

    service = DemoService(runner=runner, store=demo_store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        for client in (runner.intent_client, runner.llm_client):
            close = getattr(client, "close", None)
            if callable(close):
                close()

    app = FastAPI(title="SupportIQ Local Copilot Demo", docs_url=None, redoc_url=None, lifespan=lifespan)

    # Middleware to ensure session_id cookie and block cross-origin mutations
    @app.middleware("http")
    async def session_cookie_middleware(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("origin")
            if origin:
                host = request.headers.get("host")
                origin_netloc = origin.split("://")[-1].rstrip("/")
                if host and origin_netloc != host:
                    return Response(content='{"detail":"Cross-origin mutation forbidden"}', status_code=403, media_type="application/json")

        session_id = request.cookies.get("demo_session_id")
        created_new = False
        if not session_id:
            session_id = str(uuid.uuid4())
            created_new = True
        request.state.session_id = session_id

        response = await call_next(request)
        if created_new:
            response.set_cookie(
                key="demo_session_id",
                value=session_id,
                httponly=True,
                samesite="lax",
                secure=False,
            )
        return response

    @app.get("/api/demo/health")
    def health():
        data = {
            "status": "ok",
            "model_version": getattr(runner.policy, "version", "unknown"),
            "draft_kind": "llm" if getattr(getattr(runner, "llm_client", None), "configured", False) else None,
            "llm_provider": "google_ai_studio",
            "llm_model": getattr(getattr(runner, "llm_client", None), "model", None),
            "llm_configured": getattr(getattr(runner, "llm_client", None), "configured", False),
            "local_mode": True,
        }
        if health_metadata:
            data.update(health_metadata)
        return data

    @app.get("/api/demo/profiles")
    def get_profiles():
        return service.get_profiles()

    @app.post("/api/demo/runs")
    def submit_run(req: DemoRunRequest, request: Request):
        session_id = request.state.session_id
        try:
            return service.submit_run(req, session_id=session_id)
        except KeyError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/demo/runs/{run_id}/feedback")
    def record_feedback(run_id: str, req: DemoFeedbackRequest, request: Request):
        session_id = request.state.session_id
        try:
            return service.record_feedback(run_id=run_id, req=req, session_id=session_id)
        except KeyError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @app.get("/api/demo/history")
    def get_history(request: Request):
        session_id = request.state.session_id
        return demo_store.get_history(session_id=session_id, limit=10)

    # Serve static frontend
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return HTMLResponse("<h1>SupportIQ Demo Backend Running</h1>")

    return app

# Module-level placeholder for uvicorn factory or lazy init
app = None
