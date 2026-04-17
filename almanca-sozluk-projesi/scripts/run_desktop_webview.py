#!/usr/bin/env python
"""
Almanca–Türkçe Sözlük — Masaüstü Uygulaması (pywebview)
HTTP sunucusunu arka planda başlatır, pywebview penceresiyle açar.
Tarayıcı gerekmez; URL bar görünmez; native masaüstü penceresidir.
"""

from __future__ import annotations

import sys
import threading
import time
import socket
from pathlib import Path

# Proje kökü
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
APP_TITLE = "Almanca–Türkçe Sözlük"
MIN_WIDTH  = 1100
MIN_HEIGHT = 680
ICON_PATH  = PROJECT_ROOT / "frontend" / "favicon.ico"  # varsa


def find_free_port(start: int = DEFAULT_PORT) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if s.connect_ex((HOST, port)) != 0:
                return port
    raise RuntimeError("Boş port bulunamadı.")


def is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((HOST, port)) == 0


def start_server(port: int) -> None:
    """run_frontend.py'deki HTTP sunucusunu ayrı thread'de başlat."""
    # Sunucuyu import edip direkt çalıştır (webbrowser.open çağrısını devre dışı bırak)
    import importlib, types, http.server
    from functools import partial

    # run_frontend modülünü yükle
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_frontend",
        PROJECT_ROOT / "scripts" / "run_frontend.py"
    )
    mod = importlib.util.load_from_spec(spec) if hasattr(importlib.util, 'load_from_spec') else None

    # Alternatif: doğrudan sunucu nesnesini kur
    # run_frontend'deki DictionaryRequestHandler ve ThreadingHTTPServer'ı al
    spec2 = importlib.util.spec_from_file_location("run_frontend", PROJECT_ROOT / "scripts" / "run_frontend.py")
    rf = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(rf)

    handler = partial(rf.DictionaryRequestHandler, directory=str(PROJECT_ROOT))
    server = rf.ThreadingHTTPServer((HOST, port), handler)
    # Daemon thread: pencere kapanınca sunucu da durur
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()


def main() -> None:
    import webview

    # Eğer sunucu zaten çalışıyorsa (başka bir örnek), aynı portu kullan
    if is_port_open(DEFAULT_PORT):
        port = DEFAULT_PORT
    else:
        port = find_free_port(DEFAULT_PORT)
        start_server(port)
        # Sunucunun ayağa kalkmasını bekle (max 5 sn)
        for _ in range(50):
            if is_port_open(port):
                break
            time.sleep(0.1)

    url = f"http://{HOST}:{port}/frontend/index.html"

    # pywebview penceresi
    icon = str(ICON_PATH) if ICON_PATH.exists() else None
    window = webview.create_window(
        title=APP_TITLE,
        url=url,
        width=MIN_WIDTH,
        height=MIN_HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        # Frameless=False: başlık çubuğu, büyütme/küçültme düğmeleri normal
        frameless=False,
        easy_drag=False,
        text_select=True,
    )

    webview.start(
        debug=False,         # True yaparsanız DevTools açılır
        private_mode=False,  # localStorage çalışsın (tema vs. kalıcı olsun)
    )


if __name__ == "__main__":
    main()
