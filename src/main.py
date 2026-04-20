import sys
import os

# On Windows, set AppUserModelID so the taskbar shows our icon, not Python's
if sys.platform == "win32":
    try:
        import ctypes
        _SetAppID = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        _SetAppID.argtypes = [ctypes.c_wchar_p]
        _SetAppID.restype = ctypes.HRESULT
        _SetAppID("com.pocoguy.Muse")
    except Exception:
        pass

# On Windows, install bundled font per-user so fontconfig can find it
if sys.platform == "win32":
    _base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _fonts_dir = os.path.join(_base, "fonts")
    if os.path.isdir(_fonts_dir):
        # Copy to Windows per-user fonts dir (fontconfig scans this)
        _win_fonts = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")
        if _win_fonts and os.path.isdir(os.path.dirname(_win_fonts)):
            os.makedirs(_win_fonts, exist_ok=True)
            for _f in os.listdir(_fonts_dir):
                if _f.endswith((".ttf", ".otf")):
                    _src = os.path.join(_fonts_dir, _f)
                    _dst = os.path.join(_win_fonts, _f)
                    if not os.path.exists(_dst):
                        try:
                            import shutil
                            shutil.copy2(_src, _dst)
                            print(f"Installed font: {_f}")
                        except Exception as _e:
                            print(f"Could not install font {_f}: {_e}")

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

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._apply_desktop_theme_preferences()

        # Prepend project icons to theme search path (for running from source)
        # Must be first so it takes priority over system-installed Flatpak icons
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assets_icons = os.path.join(project_root, "assets", "icons")
        if os.path.isdir(assets_icons):
            theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            theme.set_search_path([assets_icons] + theme.get_search_path())

        Gtk.Window.set_default_icon_name("com.pocoguy.Muse")

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

        # On Windows, use Adwaita Sans if installed
        if sys.platform == "win32":
            font_css = Gtk.CssProvider()
            font_css.load_from_string(
                "* { font-family: 'Adwaita Sans Text', 'Adwaita Sans', 'Segoe UI', sans-serif; }"
            )
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                font_css,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1,
            )

        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
        win.present()

    def _apply_desktop_theme_preferences(self):
        """Apply desktop GTK/libadwaita theme preferences on Linux."""
        if sys.platform != "linux":
            return

        settings = Gtk.Settings.get_default()
        if not settings:
            return

        theme_name = None
        icon_theme_name = None
        color_scheme = None

        # GTK_THEME should win when set explicitly by the user.
        gtk_theme_env = os.environ.get("GTK_THEME", "").strip()
        if gtk_theme_env:
            theme_name = gtk_theme_env.split(":", 1)[0].strip()

        try:
            interface_settings = Gio.Settings.new("org.gnome.desktop.interface")
            if not theme_name:
                theme_name = interface_settings.get_string("gtk-theme").strip() or None
            icon_theme_name = interface_settings.get_string("icon-theme").strip() or None
            color_scheme = interface_settings.get_string("color-scheme").strip() or None
        except Exception as e:
            print(f"Could not read desktop interface settings: {e}")

        if theme_name:
            try:
                settings.set_property("gtk-theme-name", theme_name)
                print(f"Using GTK theme: {theme_name}")
            except Exception as e:
                print(f"Could not apply GTK theme '{theme_name}': {e}")

        if icon_theme_name:
            try:
                settings.set_property("gtk-icon-theme-name", icon_theme_name)
            except Exception as e:
                print(f"Could not apply icon theme '{icon_theme_name}': {e}")

        style_manager = Adw.StyleManager.get_default()
        if color_scheme == "prefer-dark":
            style_manager.set_color_scheme(Adw.ColorScheme.PREFER_DARK)
            settings.set_property("gtk-application-prefer-dark-theme", True)
        elif color_scheme == "prefer-light":
            style_manager.set_color_scheme(Adw.ColorScheme.PREFER_LIGHT)
            settings.set_property("gtk-application-prefer-dark-theme", False)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)


def main():
    app = MusicApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
