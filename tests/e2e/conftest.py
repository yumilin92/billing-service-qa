"""
Fixtures for the end-to-end (E2E) tests.

E2E is the TOP of the pyramid: a real browser (driven by Playwright) clicks a
real UI, which calls the real running server, which uses a real database.
It is the most realistic — and the slowest — kind of test, so we keep just a
couple of them for the critical happy path and the key business error.

`live_server` below starts the actual app in a background process on a random
free port, with its OWN temporary database, waits until it answers /health,
hands the URL to the tests, and shuts it down afterwards.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest


def _free_port() -> int:
    """Ask the OS for a free TCP port so parallel runs don't collide."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_until_up(url: str, timeout: float = 30.0) -> None:
    """Poll `url` until it returns HTTP 200 or we give up."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.3)
    raise RuntimeError(f"server at {url} did not start in {timeout}s")


@pytest.fixture(scope="session")
def live_server():
    # A throwaway database file just for this E2E session.
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    env = {**os.environ, "BILLING_DB_URL": f"sqlite:///{db_path}"}

    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--port", str(port), "--log-level", "warning"],
        env=env,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_up(f"{base_url}/health")
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        os.remove(db_path)
