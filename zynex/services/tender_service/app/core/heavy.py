"""Run a CPU-heavy function in a separate, killable process.

Why: the analysis stages that read and check a big document (PDF extraction, structure, chunking, quote checking) are
plain CPU work. In a thread they share the web server's interpreter lock, so one very large or oddly formatted
document can make the whole app stop answering (seen with a 329-page tender). In a child process the web server
keeps running whatever the document does, and a stage that runs past its time limit is killed instead of hanging.
Small documents still run in a thread: starting a process costs a couple of seconds.
"""
import asyncio
import multiprocessing
import pickle
import traceback
from typing import Any, Callable

from app.core.config import settings


class StageTimeout(Exception):
    pass


class StageCrashed(Exception):
    pass


def _child(conn, func: Callable, args: tuple, kwargs: dict, saved_settings: dict) -> None:
    try:
        settings.load_snapshot(saved_settings)      # the worker must apply the same Settings-page values as the server
        conn.send(("ok", func(*args, **kwargs)))
    except BaseException as e:                                  # noqa: BLE001 - reported to the parent, which re-raises
        try:
            pickle.dumps(e)
            conn.send(("raise", e))
        except Exception:
            conn.send(("fail", f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}"))
    finally:
        conn.close()


async def run_stage(func: Callable, *args: Any, heavy: bool = False, name: str = "stage", **kwargs: Any) -> Any:
    """Call func(*args, **kwargs). `heavy=True` (and isolation enabled) runs it in a child process with a time limit."""
    if not (heavy and settings.ISOLATE_HEAVY_STAGES):
        return await asyncio.to_thread(func, *args, **kwargs)
    limit = float(settings.STAGE_TIMEOUT_S)
    ctx = multiprocessing.get_context("spawn")
    recv_end, send_end = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(send_end, func, args, kwargs, settings.snapshot()), daemon=True)
    proc.start()
    send_end.close()

    def wait() -> tuple:
        if not recv_end.poll(limit):
            return ("timeout",)
        try:
            return recv_end.recv()
        except EOFError:
            return ("crashed",)

    try:
        msg = await asyncio.get_running_loop().run_in_executor(None, wait)
    finally:
        if proc.is_alive():
            proc.kill()
        proc.join(timeout=5)
        recv_end.close()
    kind = msg[0]
    if kind == "ok":
        return msg[1]
    if kind == "raise":
        raise msg[1]
    if kind == "timeout":
        raise StageTimeout(f"The {name} step took longer than {int(limit)} s and was stopped. The document may be too large or damaged.")
    raise StageCrashed(f"The {name} step failed: {msg[1] if len(msg) > 1 else 'the worker process stopped unexpectedly'}")
