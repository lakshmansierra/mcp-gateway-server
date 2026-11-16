"""Admin/user backend for the MCP gateway (FastAPI + SAP HANA).

Run either way:
    python backend/main.py                                   (or `python main.py` inside backend/)
    uvicorn backend.main:app --port 8000 --reload            (from the project root)
API docs: http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root, so `backend.*` imports work when run as a file

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from hdbcli import dbapi

from backend.config import get_settings
from backend.db import get_db
from backend.routes import admin, servers, user

app = FastAPI(title="MCP Gateway Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,  # the React frontend (vite dev server by default)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router)
app.include_router(user.router)
app.include_router(servers.router)


@app.get("/api/health", tags=["health"])
def health(conn: dbapi.Connection = Depends(get_db)) -> dict[str, str]:
    """Checks that HANA is reachable."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM DUMMY")
        cur.fetchone()
    finally:
        cur.close()
    return {"status": "ok", "database": "connected"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
