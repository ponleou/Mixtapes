from gi.repository import Gtk, Adw, GObject, GLib, Gdk, Gio, Pango
import threading
from api.client import MusicClient


class LibraryPage(Adw.Bin):
    def __init__(self, player, open_playlist_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player
        self.client = MusicClient()
        self.open_playlist_callback = open_playlist_callback
        self._is_loading = False

        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Tab switcher: Library / Uploads
        self.lib_stack = Gtk.Stack()
        self.lib_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)

        # Single scrolled window for the whole page
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        clamp = Adw.Clamp()

        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self.content_box.set_margin_top(12)
        self.content_box.set_margin_bottom(24)
        self.content_box.set_margin_start(12)
        self.content_box.set_margin_end(12)

        # Tab row inside the content (same constraints as albums/artists)
        tab_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tab_row.set_margin_bottom(8)

        # Compact toggle buttons instead of StackSwitcher
        self._lib_tab_btn = Gtk.ToggleButton(label="Library")
        self._lib_tab_btn.set_active(True)
        self._upl_tab_btn = Gtk.ToggleButton(label="Uploads")
        self._upl_tab_btn.set_group(self._lib_tab_btn)

        self._lib_tab_btn.connect("toggled", lambda b: (
            self.lib_stack.set_visible_child_name("library") if b.get_active() else None
        ))
        self._upl_tab_btn.connect("toggled", lambda b: (
            self.lib_stack.set_visible_child_name("uploads") if b.get_active() else None
        ))

        tab_row.append(self._lib_tab_btn)
        tab_row.append(self._upl_tab_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        tab_row.append(spacer)

        # Upload action buttons (only visible on uploads tab)
        self.uploads_actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.uploads_actions_box.set_visible(False)

        self.all_songs_btn = Gtk.Button(icon_name="audio-x-generic-symbolic")
        self.all_songs_btn.add_css_class("flat")
        self.all_songs_btn.add_css_class("circular")
        self.all_songs_btn.set_valign(Gtk.Align.CENTER)
        self.all_songs_btn.set_tooltip_text("All Uploaded Songs")
        self.all_songs_btn.connect("clicked", lambda b: self.uploads_page._open_all_songs())
        self.uploads_actions_box.append(self.all_songs_btn)

        self.upload_btn = Gtk.Button(icon_name="document-send-symbolic")
        self.upload_btn.add_css_class("flat")
        self.upload_btn.add_css_class("circular")
        self.upload_btn.set_valign(Gtk.Align.CENTER)
        self.upload_btn.set_tooltip_text("Upload Songs")
        self.upload_btn.connect("clicked", self._on_upload_clicked)
        self.uploads_actions_box.append(self.upload_btn)

        tab_row.append(self.uploads_actions_box)
        self.content_box.append(tab_row)

        # The lib_stack goes below the tab row
        self.lib_stack.set_vexpand(True)
        self.content_box.append(self.lib_stack)

        # Library tab content (playlists, albums, artists)
        self.lib_content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)

        # Loading overlay
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.add_named(self.lib_content_box, "root")

        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        spinner = Adw.Spinner()
        spinner.set_size_request(32, 32)
        loading_box.append(spinner)
        loading_label = Gtk.Label(label="Refreshing Library...")
        loading_label.add_css_class("caption")
        loading_box.append(loading_label)
        self.stack.add_named(loading_box, "loading")

        self.lib_stack.add_titled(self.stack, "library", "Library")

        # 1. Playlists Section (inside lib_content_box, not content_box)
        playlists_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        playlists_header_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=12
        )
        playlists_header_box.set_size_request(
            -1, 34
        )

        playlists_label = Gtk.Label(label="Playlists")
        playlists_label.add_css_class("heading")
        playlists_label.set_halign(Gtk.Align.START)
        playlists_label.set_valign(Gtk.Align.CENTER)
        playlists_label.set_hexpand(True)
        playlists_header_box.append(playlists_label)

        self.new_playlist_btn = Gtk.Button(icon_name="list-add-symbolic")
        self.new_playlist_btn.add_css_class("flat")
        self.new_playlist_btn.add_css_class("circular")
        self.new_playlist_btn.set_valign(Gtk.Align.CENTER)
        self.new_playlist_btn.set_tooltip_text("New Playlist")
        self.new_playlist_btn.connect("clicked", self.on_new_playlist_clicked)
        playlists_header_box.append(self.new_playlist_btn)

        playlists_section.append(playlists_header_box)

        self.playlists_list = Gtk.ListBox()
        self.playlists_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.playlists_list.add_css_class("boxed-list")
        self.playlists_list.connect("row-activated", self.on_playlist_activated)
        playlists_section.append(self.playlists_list)

        self.lib_content_box.append(playlists_section)

        # 2. Albums Section
        albums_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        albums_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        albums_header_box.set_size_request(-1, 34)

        albums_label = Gtk.Label(label="Albums")
        albums_label.add_css_class("heading")
        albums_label.set_halign(Gtk.Align.START)
        albums_label.set_valign(Gtk.Align.CENTER)
        albums_header_box.append(albums_label)

        albums_section.append(albums_header_box)

        self.albums_list = Gtk.ListBox()
        self.albums_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.albums_list.add_css_class("boxed-list")
        self.albums_list.connect("row-activated", self.on_album_activated)
        albums_section.append(self.albums_list)

        self.lib_content_box.append(albums_section)

        # 3. Artists Section
        artists_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        artists_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        artists_header_box.set_size_request(-1, 34)

        artists_label = Gtk.Label(label="Artists")
        artists_label.add_css_class("heading")
        artists_label.set_halign(Gtk.Align.START)
        artists_label.set_valign(Gtk.Align.CENTER)
        artists_header_box.append(artists_label)

        artists_section.append(artists_header_box)

        self.artists_list = Gtk.ListBox()
        self.artists_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.artists_list.add_css_class("boxed-list")
        self.artists_list.connect("row-activated", self.on_artist_activated)
        artists_section.append(self.artists_list)

        self.lib_content_box.append(artists_section)

        # ── Tab 2: Uploads ──
        self.uploads_page = UploadsPage(self.player, self.client, self.open_playlist_callback)
        self.uploads_page._library_page = self  # Reference for upload queue UI
        self.lib_stack.add_titled(self.uploads_page, "uploads", "Uploads")
        self._uploads_loaded = True  # Will be loaded on startup
        self.lib_stack.connect("notify::visible-child-name", self._on_tab_changed)

        clamp.set_child(self.content_box)
        scrolled.set_child(clamp)
        self.main_box.append(scrolled)
        self.set_child(self.main_box)

        # Load Library + Uploads
        self.load_library()
        self.uploads_page.load()

        # Connect Player
        self.loading_row_spinner = None
        self.player.connect("state-changed", self.on_player_state_changed)

    def set_compact_mode(self, compact):
        self._compact = compact
        if compact:
            self.add_css_class("compact")
            self.content_box.set_spacing(16)
        else:
            self.remove_css_class("compact")
            self.content_box.set_spacing(24)

        # Propagate compact to all song row images (library + uploads)
        self._propagate_compact(self.content_box, compact)
        if hasattr(self, 'uploads_page'):
            self.uploads_page.set_compact_mode(compact)

    def _propagate_compact(self, widget, compact):
        if hasattr(widget, 'set_compact') and hasattr(widget, 'target_size'):
            widget.set_compact(compact)
        child = widget.get_first_child() if hasattr(widget, 'get_first_child') else None
        while child:
            self._propagate_compact(child, compact)
            child = child.get_next_sibling()

    def clear(self):
        """Clears all playlists from the UI."""
        print("Clearing LibraryPage playlists...")
        while row := self.playlists_list.get_row_at_index(0):
            self.playlists_list.remove(row)

    def load_library(self):
        if self._is_loading:
            return
        self._is_loading = True
        thread = threading.Thread(target=self._fetch_library)
        thread.daemon = True
        thread.start()

    def _fetch_library(self):
        try:
            # Only show loading UI if we have no data at all
            if self.playlists_list.get_row_at_index(0) is None:
                GLib.idle_add(self.stack.set_visible_child_name, "loading")

            playlists = self.client.get_library_playlists()
            albums = self.client.get_library_albums()
            artists = self.client.get_library_subscriptions()

            GObject.idle_add(self.update_playlists, playlists if playlists else [])
            GObject.idle_add(self.update_albums, albums if albums else [])
            GObject.idle_add(self.update_artists, artists if artists else [])
            GLib.idle_add(self.stack.set_visible_child_name, "root")
        finally:
            self._is_loading = False

    def update_playlists(self, playlists):
        # Sort: 2-letter IDs first (Automatic Playlists like LM, SE, etc.)
        def sort_key(p):
            pid = p.get("playlistId", "")
            return 0 if len(pid) == 2 else 1

        playlists.sort(key=sort_key)

        # 1. Map existing rows by playlist_id
        existing_rows = {}
        row = self.playlists_list.get_row_at_index(0)
        # ... (mapping logic remains same, but we can't easily skip lines in replacement without copying)
        # Let's just copy the mapping part briefly or assume it exists if I don't change it?
        # No, I must provide contiguous block.

        while row:
            if hasattr(row, "playlist_id"):
                existing_rows[row.playlist_id] = row
            row = row.get_next_sibling()

        processed_ids = set()

        for i, p in enumerate(playlists):
            p_id = p.get("playlistId")
            title = p.get("title", "Unknown")
            count = p.get("count")
            if not count:
                count = p.get("itemCount", "")

            thumbnails = p.get("thumbnails", [])
            thumb_url = thumbnails[-1]["url"] if thumbnails else None

            processed_ids.add(p_id)

            # Subtitle Logic
            subtitle = ""
            if len(p_id) == 2:
                subtitle = "Automatic Playlist"
                if count:
                    c_str = str(count)
                    if "songs" not in c_str:
                        c_str += " songs"
                    subtitle += f" • {c_str}"
            elif count:
                subtitle = f"{count} songs" if "songs" not in str(count) else str(count)

            row = existing_rows.get(p_id)

            if row:
                # Update existing
                box = row.get_child()
                if row.playlist_title != title:
                    row.playlist_title = title
                    box._title_label.set_label(title)

                box._subtitle_label.set_label(subtitle)
                row.playlist_count = count  # store raw count
                row.is_owned = self.client.is_own_playlist(p, playlist_id=p_id)

                # Image
                if hasattr(row, "cover_img"):
                    if row.cover_img.url != thumb_url:
                        row.cover_img.load_url(thumb_url)

                # Reordering
                current_idx = row.get_index()
                if current_idx != i:
                    self.playlists_list.remove(row)
                    self.playlists_list.insert(row, i)

            else:
                # Create New
                row = Gtk.ListBoxRow()
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                box.add_css_class("song-row")
                row.set_child(box)

                from ui.utils import AsyncPicture

                img = AsyncPicture(
                    url=thumb_url,
                    target_size=56,
                    crop_to_square=True,
                    player=self.player,
                )
                img.add_css_class("song-img")
                root = self.get_root()
                img.set_compact(getattr(root, '_is_compact', False) if root else False)
                if not thumb_url:
                    img.set_from_icon_name("media-playlist-audio-symbolic")

                box.append(img)
                row.cover_img = img

                vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                vbox.set_valign(Gtk.Align.CENTER)
                vbox.set_hexpand(True)

                title_label = Gtk.Label(label=title)
                title_label.set_halign(Gtk.Align.START)
                title_label.set_ellipsize(Pango.EllipsizeMode.END)
                title_label.set_lines(1)
                box._title_label = title_label

                subtitle_label = Gtk.Label(label=subtitle)
                subtitle_label.set_halign(Gtk.Align.START)
                subtitle_label.set_ellipsize(Pango.EllipsizeMode.END)
                subtitle_label.set_lines(1)
                subtitle_label.add_css_class("dim-label")
                subtitle_label.add_css_class("caption")
                box._subtitle_label = subtitle_label

                vbox.append(title_label)
                vbox.append(subtitle_label)
                box.append(vbox)

                row.playlist_id = p_id
                row.playlist_title = title
                row.playlist_count = count
                row.is_owned = self.client.is_own_playlist(p, playlist_id=p_id)
                row.set_activatable(True)

                # Context Menu
                gesture = Gtk.GestureClick()
                gesture.set_button(3)
                gesture.connect("released", self.on_row_right_click, row)
                row.add_controller(gesture)

                # Long Press for touch
                lp = Gtk.GestureLongPress()
                lp.connect(
                    "pressed",
                    lambda g, x, y, r=row: self.on_row_right_click(g, 1, x, y, r),
                )
                row.add_controller(lp)

                self.playlists_list.insert(row, i)

        # Identify and remove stale rows (those in existing_rows but not in processed_ids).
        # Moved widgets are kept safe by processed_ids check.
        for p_id, row in existing_rows.items():
            if p_id not in processed_ids:
                self.playlists_list.remove(row)

    def update_albums(self, albums):
        # Map existing rows
        existing_rows = {}
        row = self.albums_list.get_row_at_index(0)
        while row:
            if hasattr(row, "album_id"):
                existing_rows[row.album_id] = row
            row = row.get_next_sibling()

        processed_ids = set()

        for i, album in enumerate(albums):
            browse_id = album.get("browseId", "")
            title = album.get("title", "Unknown")
            artists = album.get("artists", [])
            artist_str = ", ".join(a.get("name", "") for a in artists if isinstance(a, dict))
            year = album.get("year", "")
            album_type = album.get("type", "Album")

            subtitle_parts = []
            if artist_str:
                subtitle_parts.append(artist_str)
            if album_type:
                subtitle_parts.append(album_type)
            if year:
                subtitle_parts.append(str(year))
            subtitle = " • ".join(subtitle_parts)

            thumbnails = album.get("thumbnails", [])
            thumb_url = thumbnails[-1]["url"] if thumbnails else None

            processed_ids.add(browse_id)

            row = existing_rows.get(browse_id)

            if row:
                box = row.get_child()
                box._title_label.set_label(title)
                box._subtitle_label.set_label(subtitle)
                if hasattr(row, "cover_img") and row.cover_img.url != thumb_url:
                    row.cover_img.load_url(thumb_url)
                current_idx = row.get_index()
                if current_idx != i:
                    self.albums_list.remove(row)
                    self.albums_list.insert(row, i)
            else:
                row = Gtk.ListBoxRow()
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                box.add_css_class("song-row")
                row.set_child(box)

                from ui.utils import AsyncPicture

                img = AsyncPicture(
                    url=thumb_url,
                    target_size=56,
                    crop_to_square=True,
                    player=self.player,
                )
                img.add_css_class("song-img")
                root = self.get_root()
                img.set_compact(getattr(root, '_is_compact', False) if root else False)
                if not thumb_url:
                    img.set_from_icon_name("media-optical-symbolic")

                box.append(img)
                row.cover_img = img

                vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                vbox.set_valign(Gtk.Align.CENTER)
                vbox.set_hexpand(True)

                title_label = Gtk.Label(label=title)
                title_label.set_halign(Gtk.Align.START)
                title_label.set_ellipsize(Pango.EllipsizeMode.END)
                title_label.set_lines(1)
                box._title_label = title_label

                subtitle_label = Gtk.Label(label=subtitle)
                subtitle_label.set_halign(Gtk.Align.START)
                subtitle_label.set_ellipsize(Pango.EllipsizeMode.END)
                subtitle_label.set_lines(1)
                subtitle_label.add_css_class("dim-label")
                subtitle_label.add_css_class("caption")
                subtitle_label.set_visible(bool(subtitle))
                box._subtitle_label = subtitle_label

                vbox.append(title_label)
                vbox.append(subtitle_label)
                box.append(vbox)

                row.album_id = browse_id
                row.album_data = album
                row.set_activatable(True)

                # Context Menu
                gesture = Gtk.GestureClick()
                gesture.set_button(3)
                gesture.connect("released", self.on_album_right_click, row)
                row.add_controller(gesture)

                lp = Gtk.GestureLongPress()
                lp.connect(
                    "pressed",
                    lambda g, x, y, r=row: self.on_album_right_click(g, 1, x, y, r),
                )
                row.add_controller(lp)

                self.albums_list.insert(row, i)

        for aid, row in existing_rows.items():
            if aid not in processed_ids:
                self.albums_list.remove(row)

    def on_album_activated(self, listbox, row):
        if hasattr(row, "album_id"):
            album = getattr(row, "album_data", {})
            initial_data = {
                "title": album.get("title", ""),
                "thumb": album.get("thumbnails", [{}])[-1].get("url") if album.get("thumbnails") else None,
            }
            self.open_playlist_callback(row.album_id, initial_data)

    def on_album_right_click(self, gesture, n_press, x, y, row):
        if not hasattr(row, "album_id"):
            return

        browse_id = row.album_id
        album = getattr(row, "album_data", {})
        audio_pid = album.get("audioPlaylistId", "")

        group = Gio.SimpleActionGroup()
        row.insert_action_group("row", group)

        menu = Gio.Menu()

        # Copy Link
        if audio_pid:
            link = f"https://music.youtube.com/playlist?list={audio_pid}"
        else:
            link = f"https://music.youtube.com/browse/{browse_id}"

        action_copy = Gio.SimpleAction.new("copy_link", None)
        action_copy.connect("activate", lambda a, p, u=link: (
            Gdk.Display.get_default().get_clipboard().set(u)
        ))
        group.add_action(action_copy)
        menu.append("Copy Link", "row.copy_link")

        # Remove from Library
        action_unsave = Gio.SimpleAction.new("unsave", None)
        def _unsave(a, p, pid=audio_pid or browse_id):
            def _thread():
                success = self.client.rate_playlist(pid, "INDIFFERENT")
                if success:
                    GLib.idle_add(self.load_library)
            threading.Thread(target=_thread, daemon=True).start()
        action_unsave.connect("activate", _unsave)
        group.add_action(action_unsave)
        menu.append("Remove from Library", "row.unsave")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(row)
        popover.set_has_arrow(False)
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        popover.popup()

    def _on_upload_clicked(self, btn):
        # Call uploads page but pass our root window since uploads tab might not be visible
        self.uploads_page._do_open_file_picker(self.get_root())

    def _on_tab_changed(self, stack, param):
        is_uploads = stack.get_visible_child_name() == "uploads"
        self.uploads_actions_box.set_visible(is_uploads)
        if is_uploads:
            # Refresh uploads every time the tab is revealed
            self.uploads_page.load()

    def on_row_right_click(self, gesture, n_press, x, y, row):
        if not hasattr(row, "playlist_id"):
            return

        pid = row.playlist_id
        # Determine URL
        url = f"https://music.youtube.com/playlist?list={pid}"

        group = Gio.SimpleActionGroup()
        row.insert_action_group("row", group)

        def copy_link_action(action, param):
            try:
                clipboard = Gdk.Display.get_default().get_clipboard()
                clipboard.set(url)
                root = self.get_root()
                if root and hasattr(root, "add_toast"):
                    root.add_toast("Link copied")
            except Exception:
                pass

        action_copy = Gio.SimpleAction.new("copy_link", None)
        action_copy.connect("activate", copy_link_action)
        group.add_action(action_copy)

        menu = Gio.Menu()
        menu.append("Copy Link", "row.copy_link")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(row)
        popover.set_has_arrow(False)

        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)

        is_owned = getattr(row, "is_owned", False)
        if is_owned:
            menu.append("Delete Playlist", "row.delete_playlist")

            def delete_action(action, param):
                self._confirm_delete_playlist(row)

            action_delete = Gio.SimpleAction.new("delete_playlist", None)
            action_delete.connect("activate", delete_action)
            group.add_action(action_delete)
        else:
            # Non-owned playlists can be removed from library
            menu.append("Remove from Library", "row.unsave")

            def unsave_action(action, param):
                def _thread():
                    success = self.client.rate_playlist(pid, "INDIFFERENT")
                    if success:
                        GLib.idle_add(self.load_library)
                threading.Thread(target=_thread, daemon=True).start()

            action_unsave = Gio.SimpleAction.new("unsave", None)
            action_unsave.connect("activate", unsave_action)
            group.add_action(action_unsave)

        popover.popup()

    def _confirm_delete_playlist(self, row):
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading="Delete Playlist?",
            body=f'Are you sure you want to delete "{row.playlist_title}"?\nThis action cannot be undone.',
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(dg, response_id):
            if response_id == "delete":
                self._delete_playlist_confirmed(row)
            dg.destroy()

        dialog.connect("response", on_response)
        dialog.present()

    def _delete_playlist_confirmed(self, row):
        def thread_func():
            success = self.client.delete_playlist(row.playlist_id)
            if success:
                print(f"Playlist {row.playlist_id} deleted successfully.")
                GLib.idle_add(self.load_library)
            else:
                print(f"Failed to delete playlist {row.playlist_id}")

        threading.Thread(target=thread_func, daemon=True).start()

    def on_new_playlist_clicked(self, btn):
        dialog = Adw.Dialog()
        dialog.set_title("New Playlist")
        dialog.set_content_width(500)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        dialog.set_child(main_box)

        header = Adw.HeaderBar()
        header.add_css_class("flat")
        main_box.append(header)

        create_btn = Gtk.Button(label="Create")
        create_btn.add_css_class("suggested-action")
        header.pack_start(create_btn)

        page = Adw.PreferencesPage()
        main_box.append(page)

        group = Adw.PreferencesGroup(title="Playlist Details")
        group.set_margin_start(12)
        group.set_margin_end(12)
        group.set_margin_top(12)
        group.set_margin_bottom(12)
        page.add(group)

        # Title
        title_row = Adw.EntryRow(title="Title")
        title_row.set_activates_default(True)
        group.add(title_row)

        # Description
        desc_row = Adw.EntryRow(title="Description")
        group.add(desc_row)

        # Privacy
        privacy_row = Adw.ComboRow(title="Visibility")
        privacy_options = ["Public", "Private", "Unlisted"]
        privacy_model = Gtk.StringList.new(privacy_options)
        privacy_row.set_model(privacy_model)
        privacy_row.set_selected(1)  # Private by default
        group.add(privacy_row)

        def on_create_clicked(button):
            title = title_row.get_text().strip()
            if not title:
                return

            description = desc_row.get_text().strip()
            privacy_idx = privacy_row.get_selected()
            privacy_status = ["PUBLIC", "PRIVATE", "UNLISTED"][privacy_idx]

            self._create_playlist_confirmed(title, description, privacy_status)
            dialog.close()

        create_btn.connect("clicked", on_create_clicked)
        dialog.present(self.get_root())
        title_row.grab_focus()

    def _create_playlist_confirmed(self, title, description, privacy_status):
        def thread_func():
            print(f"Creating playlist: {title}")
            playlist_id = self.client.create_playlist(
                title, description=description, privacy_status=privacy_status
            )

            if playlist_id:
                print(f"Playlist created successfully: {playlist_id}")
                # 1. Refresh library in background
                GLib.idle_add(self.load_library)

                # 2. Navigate to the new playlist immediately
                GLib.idle_add(
                    self.open_playlist_callback,
                    playlist_id,
                    {"title": title, "author": "You"},
                )
            else:
                print("Failed to create playlist.")

        threading.Thread(target=thread_func, daemon=True).start()

    def update_artists(self, artists):
        # 1. Map existing rows by browse_id
        existing_rows = {}
        row = self.artists_list.get_row_at_index(0)
        while row:
            if hasattr(row, "artist_id"):
                existing_rows[row.artist_id] = row
            row = row.get_next_sibling()

        processed_ids = set()

        for i, a in enumerate(artists):
            a_id = a.get("browseId")
            name = a.get("artist", "Unknown")
            subscribers = a.get("subscribers", "")
            if subscribers and "subscribers" not in subscribers.lower():
                subscribers = f"{subscribers} subscribers"

            thumbnails = a.get("thumbnails", [])
            thumb_url = thumbnails[-1]["url"] if thumbnails else None

            processed_ids.add(a_id)

            row = existing_rows.get(a_id)

            if row:
                # Update existing
                box = row.get_child()
                if row.artist_name != name:
                    row.artist_name = name
                    box._title_label.set_label(name)

                box._subtitle_label.set_label(subscribers)

                # Image
                if hasattr(row, "cover_img"):
                    if row.cover_img.url != thumb_url:
                        row.cover_img.load_url(thumb_url)

                # Reordering
                current_idx = row.get_index()
                if current_idx != i:
                    self.artists_list.remove(row)
                    self.artists_list.insert(row, i)

            else:
                # Create New
                row = Gtk.ListBoxRow()
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
                box.add_css_class("song-row")
                row.set_child(box)

                from ui.utils import AsyncPicture

                img = AsyncPicture(
                    url=thumb_url,
                    target_size=56,
                    crop_to_square=True,
                    player=self.player,
                )
                img.add_css_class("song-img")
                root = self.get_root()
                img.set_compact(getattr(root, '_is_compact', False) if root else False)
                if not thumb_url:
                    img.set_from_icon_name("avatar-default-symbolic")

                box.append(img)
                row.cover_img = img

                vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                vbox.set_valign(Gtk.Align.CENTER)
                vbox.set_hexpand(True)

                title_label = Gtk.Label(label=name)
                title_label.set_halign(Gtk.Align.START)
                title_label.set_ellipsize(Pango.EllipsizeMode.END)
                title_label.set_lines(1)
                box._title_label = title_label

                subtitle_label = Gtk.Label(label=subscribers)
                subtitle_label.set_halign(Gtk.Align.START)
                subtitle_label.set_ellipsize(Pango.EllipsizeMode.END)
                subtitle_label.set_lines(1)
                subtitle_label.add_css_class("dim-label")
                subtitle_label.add_css_class("caption")
                box._subtitle_label = subtitle_label

                vbox.append(title_label)
                vbox.append(subtitle_label)
                box.append(vbox)

                row.artist_id = a_id
                row.artist_name = name
                row.set_activatable(True)

                self.artists_list.insert(row, i)

        # Remove stale
        for a_id, row in existing_rows.items():
            if a_id not in processed_ids:
                self.artists_list.remove(row)

    def on_artist_activated(self, box, row):
        if hasattr(row, "artist_id"):
            # The MainWindow has open_artist, but here we only have open_playlist_callback.
            # However, open_playlist_callback in MainWindow.init_pages is bound to self.open_playlist.
            # We might need a separate callback for artists or use the root window.
            root = self.get_root()
            if hasattr(root, "open_artist"):
                root.open_artist(row.artist_id, row.artist_name)

    def on_playlist_activated(self, box, row):
        if hasattr(row, "playlist_id"):
            initial_data = {
                "title": getattr(row, "playlist_title", None),
                "thumb": row.cover_img.url if hasattr(row, "cover_img") else None,
            }
            self.open_playlist_callback(row.playlist_id, initial_data)

    def on_player_state_changed(self, player, state):
        pass  # Not used currently for playlist list


class UploadsPage(Gtk.Box):
    """Sub-page showing uploaded albums from the user's YouTube Music library."""

    def __init__(self, player, client, open_playlist_callback):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.player = player
        self.client = client
        self.open_playlist_callback = open_playlist_callback

        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self.append(self._stack)

        # Loading page
        loading_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        loading_box.set_valign(Gtk.Align.CENTER)
        loading_box.set_halign(Gtk.Align.CENTER)
        loading_box.set_vexpand(True)
        loading_box.set_hexpand(True)
        loading_spinner = Adw.Spinner()
        loading_spinner.set_size_request(32, 32)
        loading_box.append(loading_spinner)
        loading_label = Gtk.Label(label="Loading uploads...")
        loading_label.add_css_class("caption")
        loading_label.add_css_class("dim-label")
        loading_box.append(loading_label)
        self._stack.add_named(loading_box, "loading")

        # Content page
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)

        # Albums section
        albums_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        albums_label = Gtk.Label(label="Albums")
        albums_label.add_css_class("heading")
        albums_label.set_halign(Gtk.Align.START)
        albums_section.append(albums_label)

        self.albums_list = Gtk.ListBox()
        self.albums_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.albums_list.add_css_class("boxed-list")
        self.albums_list.connect("row-activated", self._on_album_activated)
        albums_section.append(self.albums_list)
        self.content_box.append(albums_section)

        # Artists section
        artists_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        artists_label = Gtk.Label(label="Artists")
        artists_label.add_css_class("heading")
        artists_label.set_halign(Gtk.Align.START)
        artists_section.append(artists_label)

        self.artists_list = Gtk.ListBox()
        self.artists_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.artists_list.add_css_class("boxed-list")
        self.artists_list.connect("row-activated", self._on_artist_activated)
        artists_section.append(self.artists_list)
        self.content_box.append(artists_section)

        self.empty_label = Gtk.Label(label="No uploaded music")
        self.empty_label.add_css_class("dim-label")
        self.empty_label.set_visible(False)
        self.content_box.append(self.empty_label)

        self._stack.add_named(self.content_box, "content")
        self._stack.set_visible_child_name("loading")


    def set_compact_mode(self, compact):
        if compact:
            self.add_css_class("compact")
            self.content_box.set_spacing(16)
        else:
            self.remove_css_class("compact")
            self.content_box.set_spacing(24)
        self._propagate_compact(self.content_box, compact)

    def _propagate_compact(self, widget, compact):
        if hasattr(widget, 'set_compact') and hasattr(widget, 'target_size'):
            widget.set_compact(compact)
        child = widget.get_first_child() if hasattr(widget, 'get_first_child') else None
        while child:
            self._propagate_compact(child, compact)
            child = child.get_next_sibling()

    def load(self):
        # Only show loading screen if we have no content yet (first load)
        has_content = self.albums_list.get_row_at_index(0) is not None or self.artists_list.get_row_at_index(0) is not None
        if not has_content:
            self._stack.set_visible_child_name("loading")
        self.empty_label.set_visible(False)
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        albums = self.client.get_library_upload_albums(limit=100)
        artists = self.client.get_library_upload_artists(limit=100)
        GLib.idle_add(self._display, albums or [], artists or [])

    def _display(self, albums, artists):
        self._stack.set_visible_child_name("content")

        # Clear existing
        while row := self.albums_list.get_row_at_index(0):
            self.albums_list.remove(row)
        while row := self.artists_list.get_row_at_index(0):
            self.artists_list.remove(row)

        if not albums and not artists:
            self.empty_label.set_visible(True)
            return

        self.empty_label.set_visible(False)
        self._display_artists(artists)
        self._display_albums(albums)

    def _display_artists(self, artists):
        from ui.utils import AsyncPicture

        for artist in artists:
            name = artist.get("artist", artist.get("name", "Unknown"))
            song_count = artist.get("songs")
            subtitle = f"{song_count} songs" if song_count else ""

            thumbnails = artist.get("thumbnails", [])
            thumb_url = thumbnails[-1]["url"] if thumbnails else None

            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.add_css_class("song-row")
            row.set_child(box)

            img = AsyncPicture(
                url=thumb_url, target_size=56, crop_to_square=True, player=self.player,
            )
            img.add_css_class("song-img")
            root = self.get_root()
            img.set_compact(getattr(root, '_is_compact', False) if root else False)
            if not thumb_url:
                img.set_from_icon_name("avatar-default-symbolic")
            box.append(img)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.set_valign(Gtk.Align.CENTER)
            vbox.set_hexpand(True)

            title_label = Gtk.Label(label=name)
            title_label.set_halign(Gtk.Align.START)
            title_label.set_ellipsize(Pango.EllipsizeMode.END)
            title_label.set_lines(1)
            vbox.append(title_label)

            if subtitle:
                sub_label = Gtk.Label(label=subtitle)
                sub_label.set_halign(Gtk.Align.START)
                sub_label.add_css_class("dim-label")
                sub_label.add_css_class("caption")
                vbox.append(sub_label)

            box.append(vbox)

            row.artist_data = artist
            row.set_activatable(True)
            self.artists_list.append(row)

    def _display_albums(self, albums):
        from ui.utils import AsyncPicture

        for album in albums:
            title = album.get("title", "Unknown")
            artists = album.get("artists", [])
            artist_str = ", ".join(a.get("name", "") for a in artists if isinstance(a, dict))
            if not artist_str:
                artist_str = album.get("artist", "")
            year = album.get("year", "")

            subtitle_parts = []
            if artist_str:
                subtitle_parts.append(artist_str)
            if year:
                subtitle_parts.append(str(year))
            subtitle = " • ".join(subtitle_parts)

            thumbnails = album.get("thumbnails", [])
            thumb_url = thumbnails[-1]["url"] if thumbnails else None

            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.add_css_class("song-row")
            row.set_child(box)

            img = AsyncPicture(
                url=thumb_url,
                target_size=56,
                crop_to_square=True,
                player=self.player,
            )
            img.add_css_class("song-img")
            root = self.get_root()
            img.set_compact(getattr(root, '_is_compact', False) if root else False)
            if not thumb_url:
                img.set_from_icon_name("media-optical-symbolic")

            box.append(img)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            vbox.set_valign(Gtk.Align.CENTER)
            vbox.set_hexpand(True)

            title_label = Gtk.Label(label=title)
            title_label.set_halign(Gtk.Align.START)
            title_label.set_ellipsize(Pango.EllipsizeMode.END)
            title_label.set_lines(1)

            subtitle_label = Gtk.Label(label=subtitle)
            subtitle_label.set_halign(Gtk.Align.START)
            subtitle_label.set_ellipsize(Pango.EllipsizeMode.END)
            subtitle_label.set_lines(1)
            subtitle_label.add_css_class("dim-label")
            subtitle_label.add_css_class("caption")
            subtitle_label.set_visible(bool(subtitle))

            vbox.append(title_label)
            vbox.append(subtitle_label)
            box.append(vbox)

            row.album_data = album
            row.set_activatable(True)

            # Context menu
            gesture = Gtk.GestureClick()
            gesture.set_button(3)
            gesture.connect("released", self._on_album_right_click, row)
            row.add_controller(gesture)

            lp = Gtk.GestureLongPress()
            lp.connect("pressed", lambda g, x, y, r=row: self._on_album_right_click(g, 1, x, y, r))
            row.add_controller(lp)

            self.albums_list.append(row)

    def _on_artist_activated(self, listbox, row):
        if not hasattr(row, "artist_data"):
            return
        artist = row.artist_data
        browse_id = artist.get("browseId")
        name = artist.get("artist", artist.get("name", "Unknown"))
        if not browse_id:
            return

        nav = self._find_nav()
        if not nav:
            return

        from ui.pages.playlist import PlaylistPage
        page = PlaylistPage(self.player)
        page.playlist_id = f"UPLOAD_ARTIST_{browse_id}"
        page.is_fully_loaded = True
        page.is_fully_fetched = True

        root = self.get_root()
        if root and getattr(root, '_is_compact', False):
            page.set_compact_mode(True)

        nav_page = Adw.NavigationPage(child=page, title=name)
        nav.push(nav_page)
        page.stack.set_visible_child_name("loading")

        def _fetch():
            songs = self.client.get_library_upload_artist(browse_id)
            GLib.idle_add(self._populate_songs_page, page, songs or [], name, "Uploaded Artist")

        threading.Thread(target=_fetch, daemon=True).start()

    def _populate_songs_page(self, page, songs, title="Uploaded Songs", meta1="Uploads"):
        tracks = []
        for s in songs:
            t = dict(s)
            if "thumbnail" in t and "thumbnails" not in t:
                t["thumbnails"] = t["thumbnail"]
            tracks.append(t)

        page.original_tracks = tracks
        page.current_tracks = tracks

        total_seconds = sum(t.get("duration_seconds", 0) for t in tracks)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        duration_str = f"{hours} hr {minutes} min" if hours > 0 else f"{minutes} min"

        page.update_ui(
            title=title,
            description="",
            meta1=meta1,
            meta2=f"{len(tracks)} songs • {duration_str}",
            thumbnails=tracks[0].get("thumbnails", []) if tracks else [],
            tracks=tracks,
        )

        # Apply current compact mode
        root = page.get_root()
        if root and getattr(root, '_is_compact', False):
            page.set_compact_mode(True)

    def _find_nav(self):
        """Walk up the widget tree to find the NavigationView."""
        widget = self
        while widget:
            parent = widget.get_parent()
            if isinstance(parent, Adw.NavigationView):
                return parent
            widget = parent
        return None

    def _open_all_songs(self):
        """Open a pseudo-playlist page immediately, load data in background."""
        nav = self._find_nav()
        if not nav:
            return

        from ui.pages.playlist import PlaylistPage
        page = PlaylistPage(self.player)
        page.playlist_id = "UPLOADS"
        page.is_fully_loaded = True
        page.is_fully_fetched = True

        # Apply compact mode before pushing
        root = self.get_root()
        if root and getattr(root, '_is_compact', False):
            page.set_compact_mode(True)

        nav_page = Adw.NavigationPage(child=page, title="Uploaded Songs")
        nav.push(nav_page)
        page.stack.set_visible_child_name("loading")

        def _fetch():
            songs = self.client.get_library_upload_songs(limit=None)
            GLib.idle_add(self._populate_songs_page, page, songs or [])

        threading.Thread(target=_fetch, daemon=True).start()

    def _on_album_activated(self, listbox, row):
        if not hasattr(row, "album_data"):
            return
        album = row.album_data
        browse_id = album.get("browseId")
        if browse_id:
            initial_data = {
                "title": album.get("title", ""),
                "thumb": album.get("thumbnails", [{}])[-1].get("url") if album.get("thumbnails") else None,
            }
            self.open_playlist_callback(browse_id, initial_data)

    def _on_album_right_click(self, gesture, n_press, x, y, row):
        if not hasattr(row, "album_data"):
            return

        album = row.album_data
        entity_id = album.get("entityId") or album.get("browseId")

        group = Gio.SimpleActionGroup()
        row.insert_action_group("upl", group)

        menu = Gio.Menu()
        action_section = Gio.Menu()

        # Delete upload
        if entity_id:
            title = album.get("title", "this album")
            action_section.append("Delete Album", "upl.delete")
            a_del = Gio.SimpleAction.new("delete", None)
            a_del.connect("activate", lambda a, p, eid=entity_id, t=title: self._confirm_delete_upload(eid, t))
            group.add_action(a_del)

        if action_section.get_n_items() > 0:
            menu.append_section(None, action_section)

        if menu.get_n_items() > 0:
            popover = Gtk.PopoverMenu.new_from_model(menu)
            popover.set_parent(row)
            popover.set_has_arrow(False)
            rect = Gdk.Rectangle()
            rect.x = int(x)
            rect.y = int(y)
            rect.width = 1
            rect.height = 1
            popover.set_pointing_to(rect)
            popover.popup()

    def _confirm_delete_upload(self, entity_id, title):
        dialog = Adw.MessageDialog(
            transient_for=self.get_root(),
            heading="Delete Upload?",
            body=f'Are you sure you want to delete "{title}"?\nThis cannot be undone.',
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(dg, response_id):
            if response_id == "delete":
                def _thread():
                    success = self.client.delete_upload_entity(entity_id)
                    if success:
                        GLib.idle_add(self._show_toast, f"Deleted {title}")
                        GLib.idle_add(self.load)
                    else:
                        GLib.idle_add(self._show_toast, "Failed to delete")
                threading.Thread(target=_thread, daemon=True).start()
            dg.destroy()

        dialog.connect("response", on_response)
        dialog.present()

    def _show_toast(self, message):
        root = self.get_root()
        if root and hasattr(root, "add_toast"):
            root.add_toast(message)

    def _on_upload_clicked(self, btn):
        self._do_open_file_picker(self.get_root())

    def _do_open_file_picker(self, parent_window=None):
        dialog = Gtk.FileDialog()
        dialog.set_title("Upload Songs")

        filter_audio = Gtk.FileFilter()
        filter_audio.set_name("Audio Files")
        for ext in ["mp3", "m4a", "wma", "flac", "ogg"]:
            filter_audio.add_pattern(f"*.{ext}")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_audio)
        dialog.set_filters(filters)
        dialog.set_default_filter(filter_audio)

        win = parent_window or self.get_root()
        dialog.open_multiple(win, None, self._on_files_chosen)

    def _on_files_chosen(self, dialog, result):
        try:
            files = dialog.open_multiple_finish(result)
            if files:
                paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
                if paths:
                    self._start_upload_queue(paths)
        except GLib.Error:
            pass

    def _get_window(self):
        root = self.get_root()
        if not root:
            lp = getattr(self, '_library_page', None)
            root = lp.get_root() if lp else None
        return root

    def _start_upload_queue(self, filepaths):
        import os

        win = self._get_window()
        if not win or not hasattr(win, '_upload_queue_box'):
            return
        queue_box = win._upload_queue_box

        # Show the progress button
        GLib.idle_add(win._upload_progress_btn.set_visible, True)

        self._upload_total = getattr(self, '_upload_total', 0) + len(filepaths)
        self._upload_done_count = getattr(self, '_upload_done_count', 0)

        for filepath in filepaths:
            filename = os.path.basename(filepath)
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            info_box.set_hexpand(True)
            info_box.set_margin_top(4)
            info_box.set_margin_bottom(4)

            name_label = Gtk.Label(label=filename)
            name_label.set_halign(Gtk.Align.START)
            name_label.set_ellipsize(Pango.EllipsizeMode.END)
            name_label.add_css_class("caption")
            info_box.append(name_label)

            status_label = Gtk.Label(label="Queued")
            status_label.set_halign(Gtk.Align.START)
            status_label.add_css_class("caption")
            status_label.add_css_class("dim-label")
            info_box.append(status_label)

            row.append(info_box)
            row._filepath = filepath
            row._filename = filename
            row._status_label = status_label
            row._done = False

            queue_box.append(row)

        if not getattr(self, '_uploading', False):
            threading.Thread(target=self._process_upload_queue, daemon=True).start()

    def _process_upload_queue(self):
        self._uploading = True
        has_success = False

        import time
        while True:
            child_holder = [None]
            def _find():
                w = self._get_window()
                if not w or not hasattr(w, '_upload_queue_box'):
                    return
                c = w._upload_queue_box.get_first_child()
                while c:
                    if not getattr(c, '_done', False):
                        child_holder[0] = c
                        return
                    c = c.get_next_sibling()
            GLib.idle_add(_find)
            time.sleep(0.2)

            child = child_holder[0]
            if child is None:
                break

            GLib.idle_add(child._status_label.set_label, "Uploading...")

            result = self.client.upload_song(child._filepath)
            result_str = str(result) if result else ""

            success = result and ("SUCCEEDED" in result_str.upper() or "200" in result_str)
            if success:
                has_success = True
                GLib.idle_add(child._status_label.set_label, "Done")
            else:
                GLib.idle_add(child._status_label.set_label, "Failed")

            child._done = True
            self._upload_done_count = getattr(self, '_upload_done_count', 0) + 1

            # Update pie chart on the window
            def _update_pie():
                w = self._get_window()
                if w and hasattr(w, '_upload_progress_fraction'):
                    total = getattr(self, '_upload_total', 1)
                    done = getattr(self, '_upload_done_count', 0)
                    w._upload_progress_fraction = done / max(total, 1)
                    w._pie_area.queue_draw()
            GLib.idle_add(_update_pie)

        self._uploading = False

        if has_success:
            GLib.idle_add(self._show_toast, "Uploads complete")
            GLib.timeout_add(5000, self._delayed_refresh)

        GLib.timeout_add(8000, self._clear_upload_queue)

    def _clear_upload_queue(self):
        win = self._get_window()
        if not win or not hasattr(win, '_upload_queue_box'):
            return False
        child = win._upload_queue_box.get_first_child()
        while child:
            next_c = child.get_next_sibling()
            if getattr(child, '_done', False):
                win._upload_queue_box.remove(child)
            child = next_c
        if not win._upload_queue_box.get_first_child():
            win._upload_progress_btn.set_visible(False)
            win._upload_progress_fraction = 0.0
            win._pie_area.queue_draw()
            self._upload_total = 0
            self._upload_done_count = 0
        return False

    def _delayed_refresh(self):
        self.load()
        root = self.get_root()
        if root and hasattr(root, "library_page"):
            root.library_page.load_library()
        return False
