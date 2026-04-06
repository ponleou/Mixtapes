"""
Standalone YouTube Music login helper for Windows.
Uses Edge WebView2 via pywebview to capture auth cookies,
then writes them to a JSON file for Mixtapes to import.

Usage:
  login_helper.exe [--output PATH]

Writes captured headers JSON to:
  --output PATH   (default: %LOCALAPPDATA%/Mixtapes/login_headers.json)
"""

import json
import os
import sys
import time
import threading
import webview


OUTPUT_PATH = None


def get_default_output():
    appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    d = os.path.join(appdata, "Mixtapes")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "login_headers.json")


class LoginCapture:
    def __init__(self, window):
        self.window = window
        self.finished = False
        self._poll_thread = None

    def on_loaded(self):
        """Start polling cookies once we land on music.youtube.com."""
        if self.finished:
            return

        url = self.window.get_current_url() or ""

        if "music.youtube.com" in url and "accounts.google.com" not in url:
            # Start a polling thread to check cookies via get_cookies()
            if not self._poll_thread:
                self._poll_thread = threading.Thread(target=self._poll_cookies, daemon=True)
                self._poll_thread.start()

    def _poll_cookies(self):
        """Poll for auth cookies using pywebview's get_cookies() which sees HttpOnly cookies."""
        for _ in range(30):  # Try for 30 seconds
            if self.finished:
                return

            try:
                cookies = self.window.get_cookies()
                cookie_strs = []
                has_sapisid = False

                for cookie in cookies:
                    name = cookie.get("name", "") if isinstance(cookie, dict) else getattr(cookie, "name", "")
                    value = cookie.get("value", "") if isinstance(cookie, dict) else getattr(cookie, "value", "")

                    if name and value:
                        cookie_strs.append(f"{name}={value}")
                        if name in ("SAPISID", "__Secure-3PAPISID"):
                            has_sapisid = True

                if has_sapisid and cookie_strs:
                    self.finished = True
                    ua = self.window.evaluate_js("navigator.userAgent") or ""

                    headers = {
                        "Cookie": "; ".join(cookie_strs),
                        "User-Agent": ua,
                    }

                    output = OUTPUT_PATH or get_default_output()
                    with open(output, "w") as f:
                        json.dump(headers, f)

                    print(f"Login successful! Headers saved to: {output}")
                    self.window.destroy()
                    return

            except Exception as e:
                print(f"Cookie poll error: {e}")

            time.sleep(1)

        print("Timed out waiting for auth cookies.")


def main():
    global OUTPUT_PATH

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--output" and i + 1 < len(args):
            OUTPUT_PATH = args[i + 1]

    window = webview.create_window(
        "Mixtapes - Login to YouTube Music",
        "https://accounts.google.com/ServiceLogin?ltmpl=music&service=youtube"
        "&uilel=3&passive=true"
        "&continue=https%3A%2F%2Fmusic.youtube.com%2Flibrary",
        width=700,
        height=600,
    )

    capture = LoginCapture(window)
    window.events.loaded += capture.on_loaded
    webview.start(private_mode=False)

    output = OUTPUT_PATH or get_default_output()
    if not os.path.exists(output):
        print("Login was cancelled or failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
