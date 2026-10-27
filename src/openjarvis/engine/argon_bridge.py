"""Persistent warm bridge to Google Antigravity CLI (`agy`) for Gemini 4 Argon (Maestro).

Keeps a warm `agy --input-format stream-json --output-format stream-json` process
running in the background so requests to `gemini-4-argon*` stream tokens in real
time without paying CLI cold-start overhead on every turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

logger = logging.getLogger(__name__)

ARGON_MODELS = [
    "gemini-4-argon-low",
    "gemini-4-argon-medium",
    "gemini-4-argon-high",
    "gemini-4-argon",
]


def find_agy_binary() -> Optional[str]:
    """Locate `agy.exe` on Windows or PATH."""
    found = shutil.which("agy")
    if found:
        return found
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidate = Path(local_app_data) / "agy" / "bin" / "agy.exe"
        if candidate.is_file():
            return str(candidate)
    home_candidate = Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe"
    if home_candidate.is_file():
        return str(home_candidate)
    return None


def is_argon_model(model: str) -> bool:
    """Return True if *model* is a Gemini 4 Argon / Antigravity Maestro model."""
    m = model.lower().strip()
    return m.startswith("gemini-4-argon") or m.startswith("argon")


def normalize_argon_model(model: str) -> str:
    """Map generic `gemini-4-argon` or `argon` to `gemini-4-argon-low` for fast interactive voice."""
    m = model.lower().strip()
    if m in ("gemini-4-argon", "argon", "argon-maestro"):
        return "gemini-4-argon-low"
    if m in ("gemini-4-argon-low", "gemini-4-argon-medium", "gemini-4-argon-high"):
        return m
    return "gemini-4-argon-low"


class WarmArgonSession:
    """Manages a persistent `agy` stream-json subprocess for instant Argon Maestro turns."""

    def __init__(self, model: str = "gemini-4-argon-low") -> None:
        self._model = normalize_argon_model(model)
        self._proc: Optional[subprocess.Popen[str]] = None
        self._lock = threading.Lock()
        self._conversation_id: Optional[str] = None

    def _ensure_proc(self, model: str) -> subprocess.Popen[str]:
        target_model = normalize_argon_model(model)
        if (
            self._proc is not None
            and self._proc.poll() is None
            and self._model == target_model
        ):
            return self._proc

        self.close()
        agy_bin = find_agy_binary()
        if not agy_bin:
            raise RuntimeError("Antigravity CLI (agy.exe) not found on this machine.")

        self._model = target_model
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"

        # Hide console window on Windows
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        self._proc = subprocess.Popen(
            [
                agy_bin,
                "--model",
                self._model,
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--dangerously-skip-permissions",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            creationflags=creationflags,
        )

        # Read the initial {"event": "init", ...} line
        if self._proc.stdout is not None:
            init_line = self._proc.stdout.readline()
            if init_line:
                try:
                    data = json.loads(init_line)
                    self._conversation_id = data.get("conversation_id")
                    logger.info(
                        "Warm Argon Maestro session initialized (model=%s, conv=%s)",
                        self._model,
                        self._conversation_id,
                    )
                except Exception:
                    pass
        return self._proc

    def stream_turn_sync(self, prompt: str, model: str = "gemini-4-argon-low") -> Iterator[str]:
        """Send a user prompt to the warm Argon subprocess and yield text deltas."""
        with self._lock:
            proc = self._ensure_proc(model)
            assert proc.stdin is not None
            assert proc.stdout is not None

            payload = json.dumps(
                {"event": "user", "message": {"content": prompt}},
                ensure_ascii=False,
            )
            try:
                proc.stdin.write(payload + "\n")
                proc.stdin.flush()
            except BrokenPipeError:
                self.close()
                proc = self._ensure_proc(model)
                assert proc.stdin is not None
                assert proc.stdout is not None
                proc.stdin.write(payload + "\n")
                proc.stdin.flush()

            emitted_any = False
            while True:
                line = proc.stdout.readline()
                if not line:
                    # Process exited unexpectedly
                    self.close()
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = evt.get("event")
                if etype == "step_update":
                    su = evt.get("step_update", {})
                    if su.get("step_type") == "agent_response":
                        delta = su.get("text_delta", "")
                        if delta:
                            emitted_any = True
                            yield delta
                elif etype == "result":
                    res = evt.get("result", {})
                    if not emitted_any and res.get("response"):
                        yield res["response"]
                    break

    def close(self) -> None:
        if self._proc is not None:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None


_GLOBAL_SESSION: Optional[WarmArgonSession] = None
_GLOBAL_LOCK = threading.Lock()


def get_warm_argon_session(model: str = "gemini-4-argon-low") -> WarmArgonSession:
    global _GLOBAL_SESSION
    with _GLOBAL_LOCK:
        if _GLOBAL_SESSION is None:
            _GLOBAL_SESSION = WarmArgonSession(model=model)
        return _GLOBAL_SESSION


def prewarm_argon_async(model: str = "gemini-4-argon-low") -> None:
    """Pre-warm the Argon CLI process in a daemon thread so the first voice turn is fast."""
    def _warmup() -> None:
        try:
            sess = get_warm_argon_session(model)
            with sess._lock:
                sess._ensure_proc(model)
        except Exception as exc:
            logger.debug("Argon prewarm skipped: %s", exc)

    t = threading.Thread(target=_warmup, name="argon-prewarm", daemon=True)
    t.start()


def format_prompt_for_argon(messages: Sequence[Any]) -> str:
    """Extract the user prompt (with concise J.A.R.V.I.S. voice persona reminder on first turn)."""
    user_text = ""
    for m in reversed(messages):
        role = getattr(m, "role", None)
        role_str = role.value if hasattr(role, "value") else str(role)
        content = getattr(m, "content", "") or ""
        if role_str == "user" and content:
            user_text = content
            break
    if not user_text:
        return "Olá J.A.R.V.I.S."
    return (
        "[Modo Voz J.A.R.V.I.S. Ativo — Responda em Português (PT-BR) como J.A.R.V.I.S. / Maestro "
        "para o Senhor Caio de forma direta, natural para leitura em voz alta e objetiva]\n\n"
        f"{user_text}"
    )


async def stream_argon(
    model: str,
    messages: Sequence[Any],
) -> AsyncIterator[str]:
    """Async generator yielding real-time tokens from the warm Argon Maestro session."""
    prompt = format_prompt_for_argon(messages)
    sess = get_warm_argon_session(model)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

    def _worker() -> None:
        try:
            for chunk in sess.stream_turn_sync(prompt, model=model):
                loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:
            loop.call_soon_threadsafe(
                queue.put_nowait, f"\n[Erro Argon Maestro: {exc}]"
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=_worker, name="argon-stream-turn", daemon=True).start()
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item
