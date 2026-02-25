"""Peronsal Persistent — Todo API with JSON file storage."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TODOS_FILE = DATA_DIR / "pp_todos.json"

# API key from environment variable, fallback for dev
PP_API_KEY = os.environ.get("PP_API_KEY", "pp-dev-key-change-me")


# --- Auth ---


def verify_api_key(x_pp_key: str = Header(...)):
    if x_pp_key != PP_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


# --- Models ---


class TodoCreate(BaseModel):
    title: str
    priority: int = 0  # higher = more important


class TodoUpdate(BaseModel):
    title: str | None = None
    priority: int | None = None
    completed: bool | None = None


class Todo(BaseModel):
    id: str
    title: str
    priority: int = 0
    completed: bool = False
    created_at: str
    completed_at: str | None = None


# --- Storage ---


def _read_todos() -> list[dict]:
    if not TODOS_FILE.exists():
        return []
    return json.loads(TODOS_FILE.read_text())


def _write_todos(todos: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TODOS_FILE.write_text(json.dumps(todos, indent=2))


# --- Endpoints ---


@router.get("/todos", response_model=list[Todo])
def list_todos(active_only: bool = False, _key: str = Depends(verify_api_key)):
    todos = _read_todos()
    if active_only:
        todos = [t for t in todos if not t.get("completed", False)]
    # Sort: incomplete first, then by priority desc, then by created_at
    todos.sort(key=lambda t: (t.get("completed", False), -t.get("priority", 0), t.get("created_at", "")))
    return todos


@router.post("/todos", response_model=Todo, status_code=201)
def create_todo(body: TodoCreate, _key: str = Depends(verify_api_key)):
    todos = _read_todos()
    todo = {
        "id": uuid.uuid4().hex[:12],
        "title": body.title,
        "priority": body.priority,
        "completed": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    todos.append(todo)
    _write_todos(todos)
    return todo


@router.patch("/todos/{todo_id}", response_model=Todo)
def update_todo(todo_id: str, body: TodoUpdate, _key: str = Depends(verify_api_key)):
    todos = _read_todos()
    for todo in todos:
        if todo["id"] == todo_id:
            if body.title is not None:
                todo["title"] = body.title
            if body.priority is not None:
                todo["priority"] = body.priority
            if body.completed is not None:
                todo["completed"] = body.completed
                if body.completed:
                    todo["completed_at"] = datetime.now(timezone.utc).isoformat()
                else:
                    todo["completed_at"] = None
            _write_todos(todos)
            return todo
    raise HTTPException(status_code=404, detail="Todo not found")


@router.delete("/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: str, _key: str = Depends(verify_api_key)):
    todos = _read_todos()
    original_len = len(todos)
    todos = [t for t in todos if t["id"] != todo_id]
    if len(todos) == original_len:
        raise HTTPException(status_code=404, detail="Todo not found")
    _write_todos(todos)
