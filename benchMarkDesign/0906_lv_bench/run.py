from __future__ import annotations

import threading
import webbrowser
import socket

import uvicorn

from app import app


def choose_port(start: int = 8765, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free local port found between {start} and {start + attempts - 1}")


def open_view(url: str) -> None:
    webbrowser.open(url)


if __name__ == "__main__":
    selected_port = choose_port()
    view_url = f"http://127.0.0.1:{selected_port}/#view"
    print(f"Opening Benchmark View: {view_url}")
    threading.Timer(1.2, open_view, args=(view_url,)).start()
    uvicorn.run(app, host="127.0.0.1", port=selected_port, reload=False)
