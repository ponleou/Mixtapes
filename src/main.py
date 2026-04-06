import sys
import os

# On Windows, configure fontconfig to find bundled Adwaita Sans
# MUST happen before GTK/fontconfig initializes
if sys.platform == "win32":
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for _candidate in [
        os.path.join(_base, "share", "fonts"),
        os.path.join(_base, "runtime", "share", "fonts", "adwaita-sans"),
    ]:
        if os.path.isdir(_candidate):
            import tempfile
            _fc = tempfile.NamedTemporaryFile(
                mode="w", suffix=".conf", delete=False, prefix="mixtapes_fc_"
            )
            _fc.write(
                '<?xml version="1.0"?>\n'
                '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
                "<fontconfig>\n"
                f'  <dir>{_candidate.replace(chr(92), "/")}</dir>\n'
                "</fontconfig>\n"
            )
            _fc.close()
            os.environ["FONTCONFIG_FILE"] = _fc.name
            break

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

        # On Windows, apply Adwaita Sans font via CSS
        if sys.platform == "win32":
            font_css = Gtk.CssProvider()
            font_css.load_from_string("* { font-family: 'Adwaita Sans', 'Inter', sans-serif; }")
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                font_css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
            )

        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
        win.present()


def main():
    app = MusicApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
