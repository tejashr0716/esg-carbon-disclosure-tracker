import uuid
import time
import logging
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, Request, Response, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from src.config import settings
from src.database import db
from src.epa_client import epa_client
from src.carbon_engine import carbon_engine
from src.models import (
    Facility,
    ParentCompanyFootprint,
    GreenwashingAuditRequest,
    GreenwashingAuditResult,
    SyncResponse,
    HealthResponse
)

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger("carbon_tracker")


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        corr_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = corr_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = corr_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_sync_db()
    count = await db.get_total_facilities_count()
    if count == 0:
        logger.info("Initializing facility index from EPA Envirofacts...")
        try:
            await epa_client.sync_to_database(state="TX", limit=25)
        except Exception as e:
            logger.warning("Initial EPA sync deferred: %s", e)
    logger.info("ESG Carbon Disclosure Tracker initialized.")
    yield


app = FastAPI(
    title="ESG Carbon Disclosure Tracker",
    description="Automated Greenwashing Detection & Corporate Footprint Surveillance against US EPA Greenhouse Gas Reporting Program (GHGRP).",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(RequestCorrelationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health():
    try:
        f_count = await db.get_total_facilities_count()
        p_count = await db.get_unique_parents_count()
        return HealthResponse(
            status="HEALTHY",
            database_status="CONNECTED",
            total_facilities_indexed=f_count,
            unique_parent_companies=p_count
        )
    except Exception as e:
        return HealthResponse(
            status="DEGRADED",
            database_status=f"ERROR: {str(e)}",
            total_facilities_indexed=0,
            unique_parent_companies=0
        )


@app.post("/api/emissions/sync", response_model=SyncResponse)
async def trigger_sync(state: Optional[str] = Query(default="TX"), limit: int = Query(default=30, ge=1, le=200)):
    start_t = time.perf_counter()
    count = await epa_client.sync_to_database(state=state, limit=limit)
    duration = time.perf_counter() - start_t
    return SyncResponse(
        status="SUCCESS",
        records_ingested=count,
        duration_seconds=round(duration, 3)
    )


@app.get("/api/facilities", response_model=List[Facility])
async def list_facilities(
    state: Optional[str] = None,
    parent: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500)
):
    rows = await db.search_facilities(state=state, parent=parent, limit=limit)
    return [Facility(**r) for r in rows]


@app.get("/api/corporate/{parent_company}/footprint", response_model=ParentCompanyFootprint)
async def get_corporate_footprint(parent_company: str):
    footprint = await carbon_engine.get_corporate_footprint(parent_company)
    if not footprint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No EPA physical facilities found for corporate entity '{parent_company}'."
        )
    return footprint


@app.post("/api/audit/greenwashing-check", response_model=GreenwashingAuditResult)
async def audit_greenwashing_claim(payload: GreenwashingAuditRequest):
    return await carbon_engine.audit_greenwashing(payload)


@app.get("/api/audit/history")
async def get_audit_history(limit: int = Query(default=20, ge=1, le=100)):
    return await db.get_recent_audits(limit=limit)
