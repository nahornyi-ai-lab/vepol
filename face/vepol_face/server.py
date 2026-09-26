"""Launcher. Prints the one URL the user needs, with the token embedded."""
from __future__ import annotations

import argparse
import pathlib
import socket
import subprocess
import sys
import threading
import webbrowser

import uvicorn

from .app import create_app
from .config import Config, ExternalBindRefused


def port_in_use(host: str, port: int) -> str | None:
    """Return a description of whoever holds the port, or None if it is free.

    Checks the wildcard bind too: a service on 0.0.0.0:<port> also answers on
    loopback, so a plain bind test on 127.0.0.1 can succeed and still collide.
    """
    for probe_host in (host, "0.0.0.0"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((probe_host, port))
            except OSError:
                return _describe_holder(port)
    return None


def _describe_holder(port: int) -> str:
    try:
        out = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip().splitlines()
        if len(out) > 1:
            parts = out[1].split()
            return f"{parts[0]} (pid {parts[1]})"
    except (OSError, subprocess.SubprocessError):
        pass
    return "another process"


def banner_lines(host: str, port: int, token: str, tty: bool) -> list[str]:
    """Startup banner. The tokenized URL is shown only on an interactive TTY.

    With stdout redirected (`nohup ./run.sh > log &`) an unconditional print
    would persist the token to disk, and the token must stay in memory only. Redirected launches still work — the browser is
    opened directly with the token in memory — they just never log it.
    """
    lines = ["", "  Vepol Face is up.", ""]
    if tty:
        lines += [f"  Open:  http://{host}:{port}/?token={token}", ""]
    else:
        lines += [
            f"  Open:  http://{host}:{port}/  (token withheld: stdout is not a terminal,",
            "         so printing it here would persist it to a log file.",
            "         Launch from an interactive terminal to see the tokenized URL,",
            "         or use the browser window this launcher opens.)", "",
        ]
    lines += [
        "  The token lives in memory only and changes on every restart.",
        "  Stop with Ctrl-C.", "",
    ]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vepol-face")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8781)
    parser.add_argument("--hub", default=None)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)

    try:
        cfg = Config(host=args.host, port=args.port)
    except ExternalBindRefused as exc:
        print(f"vepol-face: {exc}", file=sys.stderr)
        print("Vepol Face binds 127.0.0.1 only.", file=sys.stderr)
        return 2

    busy = port_in_use(cfg.host, cfg.port)
    if busy:
        print(
            f"vepol-face: port {cfg.port} is already in use by {busy}.\n"
            f"Another service owns it — Vepol Face will not fight for the port.\n"
            f"Retry with:  ./run.sh --port {cfg.port + 1}",
            file=sys.stderr,
        )
        return 3

    hub = pathlib.Path(args.hub).expanduser() if args.hub else None
    app = create_app(hub=hub, config=cfg)
    url = f"http://{cfg.host}:{cfg.port}/?token={app.state.auth.token}"

    for line in banner_lines(cfg.host, cfg.port, app.state.auth.token,
                             tty=sys.stdout.isatty()):
        print(line, flush=True)

    if not args.no_open:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
