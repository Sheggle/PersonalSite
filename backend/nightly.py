"""Nightly Agent — Proposal API with JSON file storage."""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from backend.push import send_silent_push

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROPOSALS_FILE = DATA_DIR / "nightly_proposals.json"

PP_API_KEY = os.environ.get("PP_API_KEY", "pp-dev-key-change-me")


# --- Auth ---


def verify_api_key(x_pp_key: str = Header(...)):
    if x_pp_key != PP_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# --- Models ---


class Change(BaseModel):
    file_path: str
    diff: str


class ProposalCreate(BaseModel):
    project: str
    title: str
    changes: list[Change]
    rationale: str
    source: str = "nightly"
    command: str | None = None


class ProposalUpdate(BaseModel):
    status: str | None = None
    feedback: str | None = None
    changes: list[Change] | None = None
    title: str | None = None
    rationale: str | None = None


class Proposal(BaseModel):
    id: str
    project: str
    title: str
    changes: list[Change]
    rationale: str
    source: str
    command: str | None = None
    status: str
    created_at: str
    decided_at: str | None
    run_id: str
    feedback: str | None = None


class BatchCreate(BaseModel):
    run_id: str | None = None
    proposals: list[ProposalCreate]


class RunSummary(BaseModel):
    run_id: str
    created_at: str
    project: str
    total: int
    pending: int
    accepted: int
    rejected: int
    revision_requested: int = 0
    completed: int = 0


# --- Storage ---


def _read_proposals() -> list[dict]:
    if not PROPOSALS_FILE.exists():
        return []
    proposals = json.loads(PROPOSALS_FILE.read_text())
    for p in proposals:
        if "changes" not in p and "file_path" in p:
            p["changes"] = [{"file_path": p.pop("file_path"), "diff": p.pop("diff", "")}]
    return proposals


def _write_proposals(proposals: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROPOSALS_FILE.write_text(json.dumps(proposals, indent=2))


# --- Endpoints ---


@router.get("/proposals", response_model=list[Proposal])
def list_proposals(
    status: str | None = Query(None),
    run_id: str | None = Query(None),
    project: str | None = Query(None),
    _key: str = Depends(verify_api_key),
):
    proposals = _read_proposals()
    if status:
        proposals = [p for p in proposals if p.get("status") == status]
    if run_id:
        proposals = [p for p in proposals if p.get("run_id") == run_id]
    if project:
        proposals = [p for p in proposals if p.get("project") == project]
    proposals.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    return proposals


@router.get("/proposals/{proposal_id}", response_model=Proposal)
def get_proposal(proposal_id: str, _key: str = Depends(verify_api_key)):
    proposals = _read_proposals()
    for p in proposals:
        if p["id"] == proposal_id:
            return p
    raise HTTPException(status_code=404, detail="Proposal not found")


@router.post("/proposals", response_model=Proposal, status_code=201)
def create_proposal(body: ProposalCreate, _key: str = Depends(verify_api_key)):
    proposals = _read_proposals()
    now = datetime.now(timezone.utc).isoformat()
    proposal = {
        "id": uuid.uuid4().hex[:12],
        **body.model_dump(),
        "status": "pending",
        "created_at": now,
        "decided_at": None,
        "run_id": f"run-{uuid.uuid4().hex[:8]}",
    }
    proposals.append(proposal)
    _write_proposals(proposals)
    return proposal


@router.post("/proposals/batch", response_model=list[Proposal], status_code=201)
async def create_proposals_batch(body: BatchCreate, _key: str = Depends(verify_api_key)):
    proposals = _read_proposals()
    now = datetime.now(timezone.utc).isoformat()
    run_id = body.run_id or f"run-{uuid.uuid4().hex[:8]}"

    created = []
    for item in body.proposals:
        proposal = {
            "id": uuid.uuid4().hex[:12],
            **item.model_dump(),
            "status": "pending",
            "created_at": now,
            "decided_at": None,
            "run_id": run_id,
        }
        proposals.append(proposal)
        created.append(proposal)

    _write_proposals(proposals)
    asyncio.ensure_future(send_silent_push("nightly-update"))
    return created


VALID_TRANSITIONS = {
    "pending": {"accepted", "rejected", "revision_requested"},
    "revision_requested": {"accepted", "rejected", "revision_requested", "pending"},
    "accepted": {"completed"},
}


@router.patch("/proposals/{proposal_id}", response_model=Proposal)
async def update_proposal(proposal_id: str, body: ProposalUpdate, _key: str = Depends(verify_api_key)):
    proposals = _read_proposals()
    for p in proposals:
        if p["id"] == proposal_id:
            if body.status is not None:
                allowed = VALID_TRANSITIONS.get(p["status"], set())
                if body.status not in allowed:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot transition from '{p['status']}' to '{body.status}'",
                    )
                if body.status == "revision_requested" and not body.feedback:
                    raise HTTPException(status_code=400, detail="Feedback is required when requesting revision")
                p["status"] = body.status
                p["decided_at"] = datetime.now(timezone.utc).isoformat()
            if body.feedback is not None:
                p["feedback"] = body.feedback
            if body.changes is not None:
                p["changes"] = [c.model_dump() for c in body.changes]
            if body.title is not None:
                p["title"] = body.title
            if body.rationale is not None:
                p["rationale"] = body.rationale
            _write_proposals(proposals)
            if body.status == "revision_requested":
                asyncio.ensure_future(send_silent_push("nightly-update"))
            return p
    raise HTTPException(status_code=404, detail="Proposal not found")


@router.patch("/runs/{run_id}", response_model=list[Proposal])
async def update_run(run_id: str, body: ProposalUpdate, _key: str = Depends(verify_api_key)):
    """Batch accept/reject/revise all actionable proposals in a run."""
    if body.status is None:
        raise HTTPException(status_code=400, detail="Status is required for batch updates")

    if body.status == "revision_requested" and not body.feedback:
        raise HTTPException(status_code=400, detail="Feedback is required when requesting revision")

    proposals = _read_proposals()
    now = datetime.now(timezone.utc).isoformat()
    updated = []
    for p in proposals:
        if p["run_id"] != run_id:
            continue
        allowed = VALID_TRANSITIONS.get(p["status"], set())
        if body.status in allowed:
            p["status"] = body.status
            p["decided_at"] = now
            if body.feedback is not None:
                p["feedback"] = body.feedback
            updated.append(p)

    if not updated:
        raise HTTPException(status_code=404, detail="No actionable proposals found for this run")

    _write_proposals(proposals)
    if body.status == "revision_requested":
        asyncio.ensure_future(send_silent_push("nightly-update"))
    return updated


@router.get("/runs", response_model=list[RunSummary])
def list_runs(_key: str = Depends(verify_api_key)):
    proposals = _read_proposals()
    runs: dict[str, dict] = {}
    for p in proposals:
        rid = p["run_id"]
        if rid not in runs:
            runs[rid] = {
                "run_id": rid,
                "created_at": p["created_at"],
                "project": p["project"],
                "total": 0,
                "pending": 0,
                "accepted": 0,
                "rejected": 0,
                "revision_requested": 0,
                "completed": 0,
            }
        runs[rid]["total"] += 1
        runs[rid][p["status"]] += 1
    result = sorted(runs.values(), key=lambda r: r["created_at"], reverse=True)
    return result
