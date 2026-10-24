"""Where every document is kept: knowledge-base files, project-portfolio documents, tenders sent for analysis and generated
proposals. The database keeps only the full path of each file.

Settings page > System > "Document storage":
  * local        a folder on the machine running ZYNEX (UPLOAD_DIR from the env file). Also right when ZYNEX runs on the
                 file server itself.
  * file server  a folder on another server reached over SSH/SFTP, e.g. 10.10.10.19 : /home/xenovex/Tendo_Docs/ZYNEX.

Layout under either root:  kb/<owner type>/<owner>/...  ·  kb/project/<id>/<CATEGORY>/...  ·  tenders/...  ·  proposals/...

Reading follows the path, not the current choice: a path under the local uploads folder is read from this machine (so files
kept before a switch still open) and a path under the server folder is fetched from the file server.
"""
import asyncio
import logging
import mimetypes
import os
import posixpath
import re
import stat
import threading
import urllib.parse
import uuid
from typing import List, Optional, Tuple

from fastapi import HTTPException
from fastapi.responses import Response

from app.core.config import settings

logger = logging.getLogger(__name__)
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class StorageError(HTTPException):
    """A document could not be stored or read. An HTTPException so an endpoint answers with a clear message on its own."""

    def __init__(self, message: str, status: int = 503):
        super().__init__(status, message)
        self.message = message

    def __str__(self) -> str:
        return self.message


def on_server() -> bool:
    return settings.STORAGE_LOCATION == "file server"


def safe_name(name: str) -> str:
    return _SAFE.sub("_", os.path.basename(name or "file"))[-150:] or "file"


def _local_root() -> str:
    return os.path.realpath(settings.UPLOAD_DIR)


def _under(path: str, root: str, sep: str = os.sep) -> bool:
    return bool(root) and path.startswith(root.rstrip(sep) + sep)


# ── file server connection (one SFTP session, reused; paramiko is not thread safe, so one lock around every use) ─────────
_lock = threading.Lock()
_conn: Optional[Tuple[tuple, object, object, str]] = None       # (settings key, SSHClient, SFTPClient, absolute root)


def _key() -> tuple:
    return (settings.STORAGE_HOST, int(settings.STORAGE_PORT or 22), settings.STORAGE_USER, settings.STORAGE_PASSWORD,
            settings.STORAGE_KEY_FILE, settings.STORAGE_SERVER_DIR)


def _close() -> None:
    global _conn
    if _conn:
        try:
            _conn[1].close()
        except Exception:
            pass
    _conn = None


def _connect():
    """(sftp, absolute server root). Call with _lock held."""
    global _conn
    key = _key()
    if _conn and _conn[0] == key:
        transport = _conn[1].get_transport()
        if transport is not None and transport.is_active():
            return _conn[2], _conn[3]
    _close()
    host, port, user, password, key_file, folder = key
    if not host or not user:
        raise StorageError("Document storage is set to 'file server' but its address or user name is empty "
                           "(Settings > System > Document storage).")
    import paramiko
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    # trust the server the first time it is reached and remember its key; a changed key afterwards is refused
    known = os.path.join(_local_root(), ".file_server_known_hosts")
    if os.path.isfile(known):
        client.load_host_keys(known)
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, port=port, username=user, password=password or None, key_filename=key_file or None,
                       look_for_keys=not password and not key_file, allow_agent=not password, timeout=10,
                       banner_timeout=10, auth_timeout=15)
    except paramiko.BadHostKeyException:
        client.close()
        raise StorageError(f"The file server {host} answered with a different SSH key than before. If the server was "
                           f"reinstalled, delete {known} and try again.")
    except Exception as e:
        client.close()
        raise StorageError(f"Could not reach the file server {host}:{port} ({e}). Check that this computer is on the office "
                           f"network and the user name and password under Settings > System > Document storage.")
    try:
        os.makedirs(os.path.dirname(known), exist_ok=True)
        client.save_host_keys(known)
    except OSError:
        pass
    sftp = client.open_sftp()
    root = (folder or "Tendo_Docs/ZYNEX").rstrip("/")
    if not root.startswith("/"):                                  # relative = inside the user's home folder on the server
        root = posixpath.join(sftp.normalize("."), root)
    root = posixpath.normpath(root)
    _conn = (key, client, sftp, root)
    return sftp, root


def _server(op):
    """Run op(sftp, root) on the file server, reconnecting once if the kept session went stale."""
    with _lock:
        for attempt in (1, 2):
            sftp, root = _connect()
            try:
                return op(sftp, root)
            except (FileNotFoundError, StorageError):
                raise
            except (EOFError, OSError, Exception) as e:              # dropped session: reconnect once
                _close()
                if attempt == 2:
                    raise StorageError(f"File server error: {e}")


def _server_root() -> str:
    return _server(lambda sftp, root: root)


def _mkdirs(sftp, folder: str) -> None:
    parts, cur = folder.strip("/").split("/"), ""
    for p in parts:
        cur += "/" + p
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


# ── synchronous operations ─────────────────────────────────────────────────────────────────────────────────────────────
def _save_sync(folder: List[str], filename: str, data: bytes) -> str:
    name = f"{uuid.uuid4().hex[:12]}_{safe_name(filename)}"
    parts = [safe_name(p) for p in folder if p]
    if on_server():
        def op(sftp, root):
            target = posixpath.join(root, *parts)
            _mkdirs(sftp, target)
            path = posixpath.join(target, name)
            with sftp.open(path, "wb") as fh:
                fh.set_pipelined(True)
                fh.write(data)
            return path
        return _server(op)
    target = os.path.join(_local_root(), *parts)
    os.makedirs(target, exist_ok=True)
    path = os.path.join(target, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def _where(path: str) -> str:
    """'local' or 'server' for a stored path; raises when it is outside both document folders."""
    if not path:
        raise StorageError("No file is stored for this record.", 404)
    local = os.path.realpath(path)
    if _under(local, _local_root()) and os.path.isfile(local):
        return "local"
    if _under(local, _local_root()):
        raise StorageError("The stored file is missing.", 404)
    if path.startswith("/") and settings.STORAGE_HOST:
        if _under(posixpath.normpath(path), _server_root(), "/"):
            return "server"
        raise StorageError("This file is outside the document folders.", 404)
    raise StorageError("This file is kept on the file server. Connect to the office network and set "
                       "Settings > System > Document storage to reach it.", 404)


def _read_sync(path: str) -> bytes:
    if _where(path) == "local":
        with open(os.path.realpath(path), "rb") as fh:
            return fh.read()

    def op(sftp, root):
        try:
            with sftp.open(posixpath.normpath(path), "rb") as fh:
                fh.prefetch()
                return fh.read()
        except FileNotFoundError:
            raise StorageError("The stored file is missing on the file server.", 404)
    return _server(op)


def _delete_sync(path: str) -> None:
    try:
        where = _where(path)
    except StorageError:
        return                                                        # already gone or unreachable: nothing to remove
    if where == "local":
        try:
            os.remove(os.path.realpath(path))
        except OSError:
            pass
        return

    def op(sftp, root):
        try:
            sftp.remove(posixpath.normpath(path))
        except FileNotFoundError:
            pass
    try:
        _server(op)
    except StorageError as e:
        logger.warning("Could not delete %s on the file server: %s", path, e)


def _check_sync() -> dict:
    """Write, read back and remove a small file; used by the Settings page 'Test' button."""
    probe = b"zynex storage check"
    path = _save_sync([".check"], "probe.txt", probe)
    ok = _read_sync(path) == probe
    _delete_sync(path)
    return {"ok": ok, "location": settings.STORAGE_LOCATION, "folder": posixpath.dirname(posixpath.dirname(path))
            if on_server() else os.path.dirname(os.path.dirname(path))}


def _exists_sync(path: str) -> bool:
    try:
        if _where(path) == "local":
            return True

        def op(sftp, root):
            try:
                return stat.S_ISREG(sftp.stat(posixpath.normpath(path)).st_mode)
            except FileNotFoundError:
                return False
        return _server(op)
    except StorageError:
        return False


# ── async API used by the endpoints ────────────────────────────────────────────────────────────────────────────────────
async def save(folder: List[str], filename: str, data: bytes) -> str:
    """Store `data` under <root>/<folder...>/<random>_<filename> and return its full path (to keep in the database)."""
    return await asyncio.to_thread(_save_sync, folder, filename, data)


async def read(path: str) -> bytes:
    return await asyncio.to_thread(_read_sync, path)


async def delete(path: Optional[str]) -> None:
    if path:
        await asyncio.to_thread(_delete_sync, path)


async def exists(path: Optional[str]) -> bool:
    return bool(path) and await asyncio.to_thread(_exists_sync, path)


async def check() -> dict:
    return await asyncio.to_thread(_check_sync)


def response(data: bytes, name: str, mime: Optional[str] = None, inline: bool = True) -> Response:
    """The file as a download (or for viewing in the browser when inline); non-ASCII names are sent RFC 5987 encoded."""
    name = (name or "file").replace('"', "").replace("\n", " ").replace("\r", " ")
    ascii_name = name.encode("ascii", "replace").decode("ascii").replace("?", "_")
    disposition = f'{"inline" if inline else "attachment"}; filename="{ascii_name}"'
    if ascii_name != name:
        disposition += f"; filename*=UTF-8''{urllib.parse.quote(name)}"
    return Response(content=data, media_type=mime or mimetypes.guess_type(name)[0] or "application/octet-stream",
                    headers={"Content-Disposition": disposition})


def is_local(path: Optional[str]) -> bool:
    """True when the path is a file in the local uploads folder (used to move old files to the file server)."""
    if not path:
        return False
    local = os.path.realpath(path)
    return _under(local, _local_root()) and os.path.isfile(local)
