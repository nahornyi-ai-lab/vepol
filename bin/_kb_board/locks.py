"""Import-safe advisory lock abstraction for kb-board."""
from __future__ import annotations

import importlib
import os
import pathlib
import time
from contextlib import contextmanager
from dataclasses import dataclass
from types import ModuleType
from typing import Mapping


@dataclass
class LockBackend:
    name: str
    supported: bool
    error_code: str | None = None


class LockError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _module_or_none(name: str, modules: Mapping[str, ModuleType | None] | None) -> ModuleType | None:
    if modules is not None:
        return modules.get(name)
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        return None


def select_backend(os_name: str | None = None, modules: Mapping[str, ModuleType | None] | None = None) -> LockBackend:
    name = os_name if os_name is not None else os.name
    if name == "posix":
        return LockBackend("posix-fcntl", True) if _module_or_none("fcntl", modules) else LockBackend("unsupported", False, "ELOCK_UNSUPPORTED")
    if name == "nt":
        return LockBackend("windows-msvcrt", True) if _module_or_none("msvcrt", modules) else LockBackend("unsupported", False, "ELOCK_UNSUPPORTED")
    return LockBackend("unsupported", False, "ELOCK_UNSUPPORTED")


@contextmanager
def acquire_file_lock(path: str | pathlib.Path, timeout_s: float = 30.0):
    backend = select_backend()
    if not backend.supported:
        raise LockError(backend.error_code or "ELOCK_UNSUPPORTED", "no supported file-lock backend on this platform")
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fh = open(p, "a+")
    try:
        if backend.name == "posix-fcntl":
            fcntl = importlib.import_module("fcntl")
            deadline = time.monotonic() + timeout_s
            while True:
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise LockError("ELOCK", f"lock not acquired within {timeout_s}s")
                    time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
            return
        raise LockError("ELOCK_UNSUPPORTED", f"backend {backend.name} is not implemented in this runtime")
    finally:
        fh.close()
