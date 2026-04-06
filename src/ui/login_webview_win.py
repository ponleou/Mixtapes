"""
Windows login using pywebview (Edge WebView2 backend).
Equivalent to login_webview.py which uses WebKitGTK on Linux.
Runs in a separate thread since pywebview has its own event loop.
"""

import json
import threading
import webview


class WindowsLoginCapture:
    def __init__(self, on_success):
        self.on_success = on_success
        self.captured_headers = {}
        self.finished = False
        self._window = None

    def start(self):
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def _run(self):
        self._window = webview.create_window(
            "Login to YouTube Music",
            "https://accounts.google.com/ServiceLogin?ltmpl=music&service=youtube"
            "&uilel=3&passive=true"
            "&continue=https%3A%2F%2Fmusic.youtube.com%2Flibrary",
            width=700,
            height=600,
        )
        self._window.events.loaded += self._on_loaded
        webview.start(private_mode=False)

    def _on_loaded(self):
        if self.finished:
            return

        url = self._window.get_current_url() or ""

        # Once we land on music.youtube.com, extract cookies via JS
        if "music.youtube.com" in url and "accounts.google.com" not in url:
            cookies = self._window.evaluate_js("document.cookie")
            if cookies and ("SAPISID" in cookies or "__Secure-3PAPISID" in cookies):
                self.finished = True
                self.captured_headers = {
                    "Cookie": cookies,
                    "User-Agent": self._window.evaluate_js("navigator.userAgent"),
                }
                print(f"[WIN-LOGIN] Captured authenticated cookies from {url}")
                self._window.destroy()
                self.on_success(json.dumps(self.captured_headers))
