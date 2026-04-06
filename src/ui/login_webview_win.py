"""
Windows login helper.
Opens the system browser for YouTube Music login since WebKitGTK is unavailable.
"""

import webbrowser


def open_ytmusic_login():
    """Opens YouTube Music in the system browser for the user to log in."""
    webbrowser.open(
        "https://accounts.google.com/ServiceLogin?ltmpl=music&service=youtube"
        "&uilel=3&passive=true"
        "&continue=https%3A%2F%2Fmusic.youtube.com%2Flibrary"
    )
