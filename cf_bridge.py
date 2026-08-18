"""
CF Bridge — HTTP server that replaces FlareSolverr on localhost:8191.

Shops call POST localhost:8191/v1 with same payload as FlareSolverr.
This bridge receives the request and routes it to cf_solver (persistent patchright).

WHY: Zero changes needed in 10 shop scrapers. They still POST to localhost:8191.
But instead of Docker FlareSolverr (440 PIDs, 189% CPU), they hit our lightweight solver.

USAGE:
    # Start as part of SLOW process (or standalone):
    from cf_bridge import start_bridge
    await start_bridge()  # Starts HTTP server on :8191
    
    # Shops continue unchanged:
    # POST http://localhost:8191/v1 {"cmd": "request.get", "url": "...", "maxTimeout": 30000}
    # Response: {"status": "ok", "solution": {"response": "<html>..."}}

REQUIREMENTS:
    - Stop FlareSolverr Docker first: docker stop flaresolverr
    - cf_solver.py must be importable
    - aiohttp must be installed
"""
import asyncio
import json
import logging
from aiohttp import web

logger = logging.getLogger("monitor")

_server = None
_runner = None


async def _handle_request(request):
    """Handle FlareSolverr-compatible POST requests."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON"}, status=400)

    cmd = body.get("cmd", "")

    if cmd == "request.get":
        url = body.get("url", "")
        max_timeout = body.get("maxTimeout", 30000)
        session_name = body.get("session", None)

        if not url:
            return web.json_response({"status": "error", "message": "No URL"}, status=400)

        from cf_solver import solve_fs_compat
        result = await solve_fs_compat(url, max_timeout=max_timeout, session=session_name)
        return web.json_response(result)

    elif cmd == "sessions.create":
        # Compatibility — sessions not needed, just return OK
        return web.json_response({"status": "ok", "message": "Session concept not needed"})

    elif cmd == "sessions.destroy":
        # Compatibility — no-op
        return web.json_response({"status": "ok"})

    elif cmd == "sessions.list":
        return web.json_response({"status": "ok", "sessions": []})

    else:
        return web.json_response({"status": "error", "message": f"Unknown cmd: {cmd}"}, status=400)


async def _health(request):
    """Health check endpoint."""
    return web.json_response({"status": "ok", "version": "cf_bridge/1.0"})


async def start_bridge(host="127.0.0.1", port=8191):
    """
    Start HTTP server on localhost:8191 (same as FlareSolverr).
    Must stop FlareSolverr Docker first!
    """
    global _server, _runner

    app = web.Application()
    app.router.add_post("/v1", _handle_request)
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)

    _runner = web.AppRunner(app)
    await _runner.setup()
    _server = web.TCPSite(_runner, host, port)
    await _server.start()
    logger.info(f"[CF_BRIDGE] Listening on {host}:{port} (FlareSolverr replacement)")


async def stop_bridge():
    """Stop the bridge server."""
    global _runner
    if _runner:
        await _runner.cleanup()
        _runner = None
    logger.info("[CF_BRIDGE] Stopped")
