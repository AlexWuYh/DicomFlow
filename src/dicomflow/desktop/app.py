"""Launch DicomFlow as a fully offline desktop tool (local loopback + WebView)."""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_http(url: str, timeout: float = 30.0) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:  # noqa: S310
                if 200 <= getattr(resp, "status", 200) < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.15)
    return False


def _default_app_data_dir() -> Path:
    """User-writable data root for offline app (Windows LOCALAPPDATA preferred)."""
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if local:
        return Path(local) / "DicomFlow"
    return Path.home() / ".dicomflow" / "app-data"


def run_offline_app(*, port: int | None = None, data_dir: Path | None = None) -> int:
    """
    Start localhost API+UI and open a native window.

    Completely offline by design: binds 127.0.0.1 only; disables access token
    and Turnstile via Settings.offline_app.
    """
    # Must be set before Settings() / get_settings() are first used
    os.environ["DICOMFLOW_OFFLINE_APP"] = "true"
    os.environ["DICOMFLOW_HOST"] = "127.0.0.1"
    os.environ["DICOMFLOW_ACCESS_TOKEN"] = ""
    os.environ["DICOMFLOW_CAPTCHA_ENABLED"] = "false"
    os.environ.pop("TURNSTILE_SECRET", None)
    os.environ.pop("DICOMFLOW_TURNSTILE_SECRET_KEY", None)
    os.environ.pop("DICOMFLOW_TURNSTILE_SITE_KEY", None)

    app_data = (data_dir or _default_app_data_dir()).resolve()
    app_data.mkdir(parents=True, exist_ok=True)
    os.environ["DICOMFLOW_DATA_DIR"] = str(app_data)

    from dicomflow.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    if not settings.offline_app:
        logger.error("offline_app flag not applied; refusing to start desktop shell")
        return 2

    bind_port = port or _free_port()
    os.environ["DICOMFLOW_PORT"] = str(bind_port)
    get_settings.cache_clear()

    try:
        import webview
    except ImportError:
        print(
            "缺少桌面壳依赖。请安装：\n"
            "  pip install -e \".[app]\"\n"
            "Windows 还需系统 WebView2 运行时（Win10/11 通常已预装）。"
        )
        return 1

    import uvicorn

    from dicomflow.api.app import create_app

    app = create_app()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=bind_port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="dicomflow-uvicorn", daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{bind_port}/"
    health = f"http://127.0.0.1:{bind_port}/health"
    if not _wait_http(health):
        print("本地服务启动超时，请检查端口占用或日志。")
        server.should_exit = True
        return 1

    print(f"DicomFlow 离线 App 已启动（仅本机）: {url}")
    print(f"数据目录: {app_data}")

    window = webview.create_window(
        "DicomFlow",
        url,
        width=1100,
        height=800,
        min_size=(800, 600),
    )
    webview.start()
    # Window closed
    server.should_exit = True
    thread.join(timeout=5.0)
    return 0
