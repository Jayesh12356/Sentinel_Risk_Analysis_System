"""SENTINEL entry-point — FastAPI + uvicorn."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import uvicorn


def create_app():
    """Create and configure the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from sentinel.api.routes import router

    app = FastAPI(title="SENTINEL", version="0.1.0")

    # ── CORS middleware — allow Next.js UI on localhost:3000 ──────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Include API routes ───────────────────────────────────────────
    app.include_router(router)

    return app


def main() -> None:
    """CLI entry-point: parse args, configure event loop, start server."""
    parser = argparse.ArgumentParser(description="SENTINEL server")
    parser.add_argument(
        "--demo-mode",
        action="store_true",
        help="Run in demo mode (mock external APIs)",
    )
    args = parser.parse_args()

    if args.demo_mode:
        os.environ["DEMO_MODE"] = "true"

    # Clear any cached settings so they pick up the new env var
    from sentinel.config import get_settings
    get_settings.cache_clear()

    # Windows requires the selector event-loop policy for uvicorn
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    uvicorn.run(
        "sentinel.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


# Module-level app — created lazily when uvicorn imports this module
app = create_app()

if __name__ == "__main__":
    main()
