import sys
import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio, Gdk
from ui.window import MainWindow
import logger

logger.setup_logging()


class MusicApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.pocoguy.Muse", flags=Gio.ApplicationFlags.FLAGS_NONE
        )

        # Load GResource
        try:
            resource_path = os.path.join(os.path.dirname(__file__), "muse.gresource")
            resource = Gio.Resource.load(resource_path)
            resource._register()
            
            # Add icon resource path
            Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_resource_path("/com/pocoguy/muse/icons")
        except Exception as e:
            print(f"Failed to load GResource: {e}")

    def do_activate(self):
        # Load CSS
        css_provider = Gtk.CssProvider()
        css_path = os.path.join(os.path.dirname(__file__), "ui", "style.css")
        css_provider.load_from_path(css_path)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # On Windows, override the font to Adwaita Sans (shipped with the bundle)
        if sys.platform == "win32":
            self._load_windows_font()

        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
        win.present()

    def _load_windows_font(self):
        # Register bundled Adwaita Sans with Windows so fontconfig/GTK can find it
        import ctypes
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        fonts_dir = os.path.join(base, "share", "fonts")
        if os.path.isdir(fonts_dir):
            gdi32 = ctypes.windll.gdi32
            for f in os.listdir(fonts_dir):
                if f.endswith((".otf", ".ttf")):
                    path = os.path.join(fonts_dir, f)
                    gdi32.AddFontResourceExW(path, 0x10, 0)  # FR_PRIVATE

        font_css = Gtk.CssProvider()
        font_css.load_from_string("* { font-family: 'Adwaita Sans', 'Inter', sans-serif; }")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            font_css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
        )


def main():
    app = MusicApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
