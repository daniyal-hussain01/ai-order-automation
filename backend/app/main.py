"""
AI-Powered Order Data Entry Automation
Backend API - FastAPI service that handles OCR, AI parsing, review, and Bravo sync.
"""
import io
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.bravo_client import BravoClient
from app.config import settings
from app.database import Database
from app.ocr_engine import OCREngine
from app.parser import OrderParser
from app.schemas import (
    ApprovalResponse,
    ExtractResponse,
    HealthResponse,
    OrderUpdate,
    SalesOrder,
    UploadResponse,
)

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("api")

# ---------- App lifecycle ----------
db = Database(settings.DATABASE_URL)
ocr = OCREngine()
parser = OrderParser(use_llm=settings.USE_LLM, llm_api_key=settings.LLM_API_KEY)
bravo = BravoClient(base_url=settings.BRAVO_API_URL, api_key=settings.BRAVO_API_KEY)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting up — initializing database")
    db.init()
    yield
    log.info("Shutting down")


app = FastAPI(
    title="AI Order Automation API",
    description="OCR + AI-driven sales order capture, review, and Bravo ERP sync.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Health ----------
@app.get("/api/v1/health", response_model=HealthResponse, tags=["system"])
async def health():
    return HealthResponse(
        status="ok",
        version=app.version,
        ocr_available=ocr.available(),
        bravo_mode="live" if bravo.is_live() else "mock",
    )


# ---------- Upload ----------
@app.post("/api/v1/upload", response_model=UploadResponse, tags=["pipeline"])
async def upload_order(file: UploadFile = File(...)):
    """Upload an order document (image or PDF), run OCR, and stage it."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Empty filename")

    allowed = {"image/png", "image/jpeg", "image/jpg", "application/pdf", "image/webp", "image/tiff"}
    if file.content_type not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type {file.content_type}. Allowed: {sorted(allowed)}",
        )

    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    t0 = time.time()
    try:
        ocr_result = ocr.run(contents, mime_type=file.content_type)
    except Exception as exc:
        log.exception("OCR failure")
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc
    elapsed_ms = int((time.time() - t0) * 1000)

    order_id = str(uuid.uuid4())
    db.save_raw(order_id, file.filename, ocr_result.text, ocr_result.confidence)
    log.info("upload ok id=%s file=%s ocr_conf=%.2f ms=%d",
             order_id, file.filename, ocr_result.confidence, elapsed_ms)

    return UploadResponse(
        order_id=order_id,
        filename=file.filename,
        ocr_text=ocr_result.text,
        ocr_confidence=ocr_result.confidence,
        processing_ms=elapsed_ms,
    )


# ---------- Extract ----------
@app.post("/api/v1/extract/{order_id}", response_model=ExtractResponse, tags=["pipeline"])
async def extract_order(order_id: str):
    """Run AI parser on the OCR text to produce a structured SalesOrder draft."""
    raw = db.get_raw(order_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Order not found")

    t0 = time.time()
    parsed = parser.parse(raw["ocr_text"])
    elapsed_ms = int((time.time() - t0) * 1000)

    db.save_draft(order_id, parsed.dict())
    log.info("extract ok id=%s items=%d conf=%.2f ms=%d",
             order_id, len(parsed.items), parsed.confidence, elapsed_ms)

    return ExtractResponse(
        order_id=order_id,
        order=parsed,
        parser_method=parser.last_method,
        processing_ms=elapsed_ms,
    )


# ---------- Review CRUD ----------
@app.get("/api/v1/orders", response_model=List[dict], tags=["review"])
async def list_orders(status_filter: Optional[str] = None):
    return db.list_orders(status_filter)


@app.get("/api/v1/orders/{order_id}", tags=["review"])
async def get_order(order_id: str):
    rec = db.get_full(order_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Order not found")
    return rec


@app.put("/api/v1/orders/{order_id}", tags=["review"])
async def update_order(order_id: str, payload: OrderUpdate):
    if not db.get_raw(order_id):
        raise HTTPException(status_code=404, detail="Order not found")
    db.save_draft(order_id, payload.order.dict())
    return {"order_id": order_id, "updated": True}


# ---------- Approve & push to Bravo ----------
@app.post("/api/v1/orders/{order_id}/approve",
          response_model=ApprovalResponse, tags=["review"])
async def approve_order(order_id: str):
    rec = db.get_full(order_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Order not found")
    if not rec.get("draft"):
        raise HTTPException(status_code=400, detail="Order has no draft to approve")

    order = SalesOrder(**rec["draft"])
    try:
        result = await bravo.create_sales_order(order)
    except Exception as exc:
        log.exception("Bravo push failed")
        db.set_status(order_id, "failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"Bravo error: {exc}") from exc

    db.set_status(order_id, "approved", external_id=result.get("external_id"))
    log.info("approve ok id=%s external=%s", order_id, result.get("external_id"))
    return ApprovalResponse(
        order_id=order_id,
        status="approved",
        external_id=result.get("external_id"),
        bravo_mode="live" if bravo.is_live() else "mock",
    )


@app.post("/api/v1/orders/{order_id}/reject", tags=["review"])
async def reject_order(order_id: str):
    if not db.get_raw(order_id):
        raise HTTPException(status_code=404, detail="Order not found")
    db.set_status(order_id, "rejected")
    return {"order_id": order_id, "status": "rejected"}


# ---------- Errors ----------
@app.exception_handler(Exception)
async def fallback_handler(request, exc):
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "internal_server_error"},
    )


# ---------- Static (frontend) ----------
# In docker-compose nginx serves /, but we expose the UI at /ui for local dev too.
try:
    app.mount("/ui", StaticFiles(directory="/app/static", html=True), name="ui")
except Exception:
    log.info("Static UI mount skipped (frontend not bundled in this image)")
