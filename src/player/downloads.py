"""
Download manager for offline playback.

Downloads songs with full ID3 metadata and cover art, stores them in
~/Music/YouTube Music/Artist/Album/NN - Title.ext

Never overwrites existing files. Tracks downloads in SQLite.
Stores videoId and other YTM identifiers in metadata custom tags.
"""

import os
import re
import json
import sqlite3
import threading
import time
import requests
from gi.repository import GLib, GObject

# Format config
FORMATS = {
    "opus": {"ext": "opus", "ydl_format": "bestaudio/best", "ffmpeg_codec": "libopus"},
    "mp3": {"ext": "mp3", "ydl_format": "bestaudio/best", "ffmpeg_codec": "libmp3lame"},
    "m4a": {"ext": "m4a", "ydl_format": "bestaudio/best", "ffmpeg_codec": "aac"},
    "flac": {"ext": "flac", "ydl_format": "bestaudio/best", "ffmpeg_codec": "flac"},
    "ogg": {"ext": "ogg", "ydl_format": "bestaudio/best", "ffmpeg_codec": "libvorbis"},
}

DEFAULT_FORMAT = "opus"


def _sanitize_filename(name):
    """Remove characters that are invalid in filenames."""
    if not name:
        return "Unknown"
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = name.strip(". ")
    return name or "Unknown"


def _get_prefs():
    path = os.path.join(GLib.get_user_data_dir(), "muse", "prefs.json")
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_prefs(prefs):
    path = os.path.join(GLib.get_user_data_dir(), "muse", "prefs.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(prefs, f)


def get_preferred_format():
    return _get_prefs().get("download_format", DEFAULT_FORMAT)


def set_preferred_format(fmt):
    if fmt in FORMATS:
        prefs = _get_prefs()
        prefs["download_format"] = fmt
        _save_prefs(prefs)


def get_music_dir():
    """Get the download directory: ~/Music/YouTube Music/"""
    music = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC)
    if not music:
        music = os.path.expanduser("~/Music")
    return os.path.join(music, "YouTube Music")


_download_db_instance = None


def get_download_db():
    """Get the shared DownloadDB singleton."""
    global _download_db_instance
    if _download_db_instance is None:
        _download_db_instance = DownloadDB()
    return _download_db_instance


class DownloadDB:
    """SQLite database for tracking downloads."""

    def __init__(self):
        db_dir = os.path.join(get_music_dir(), ".mixtapes")
        os.makedirs(db_dir, exist_ok=True)
        self._db_path = os.path.join(db_dir, "library.db")
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        """Create a DB connection, ensuring the parent directory exists."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        return sqlite3.connect(self._db_path)

    def _init_db(self):
        with self._lock:
            conn = self._connect()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    video_id TEXT PRIMARY KEY,
                    title TEXT,
                    artist TEXT,
                    album TEXT,
                    album_id TEXT,
                    track_number INTEGER,
                    duration_seconds INTEGER,
                    file_path TEXT,
                    cover_path TEXT,
                    thumbnail_url TEXT,
                    downloaded_at TEXT,
                    file_size INTEGER,
                    format TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS library_cache (
                    playlist_id TEXT PRIMARY KEY,
                    title TEXT,
                    author TEXT,
                    track_count INTEGER,
                    last_synced TEXT,
                    tracks_json TEXT
                )
            """)
            conn.commit()
            conn.close()

    def is_downloaded(self, video_id):
        if not video_id:
            return False
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT file_path FROM downloads WHERE video_id = ?", (video_id,)
            ).fetchone()
            conn.close()
            if row and row[0]:
                return os.path.exists(row[0])
            return False

    def get_local_path(self, video_id):
        if not video_id:
            return None
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT file_path FROM downloads WHERE video_id = ?", (video_id,)
            ).fetchone()
            conn.close()
            if row and row[0] and os.path.exists(row[0]):
                return row[0]
            return None

    def add_download(self, video_id, title, artist, album, album_id,
                     track_number, duration_seconds, file_path, cover_path,
                     thumbnail_url, file_size, fmt):
        with self._lock:
            conn = self._connect()
            conn.execute("""
                INSERT OR REPLACE INTO downloads
                (video_id, title, artist, album, album_id, track_number,
                 duration_seconds, file_path, cover_path, thumbnail_url,
                 downloaded_at, file_size, format)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (video_id, title, artist, album, album_id, track_number,
                  duration_seconds, file_path, cover_path, thumbnail_url,
                  time.strftime("%Y-%m-%dT%H:%M:%S"), file_size, fmt))
            conn.commit()
            conn.close()

    def get_all_downloads(self):
        with self._lock:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM downloads ORDER BY downloaded_at DESC").fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def remove_download(self, video_id):
        with self._lock:
            conn = self._connect()
            conn.execute("DELETE FROM downloads WHERE video_id = ?", (video_id,))
            conn.commit()
            conn.close()

    # ── Library cache ────────────────────────────────────────────────────────

    def cache_playlist(self, playlist_id, title, author, track_count, tracks):
        """Cache a playlist's track listing for offline browsing."""
        with self._lock:
            conn = self._connect()
            conn.execute("""
                INSERT OR REPLACE INTO library_cache
                (playlist_id, title, author, track_count, last_synced, tracks_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                playlist_id, title, author, track_count,
                time.strftime("%Y-%m-%dT%H:%M:%S"),
                json.dumps(tracks, ensure_ascii=False) if tracks else "[]",
            ))
            conn.commit()
            conn.close()

    def get_cached_playlist(self, playlist_id):
        """Get cached playlist data. Returns dict or None."""
        with self._lock:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM library_cache WHERE playlist_id = ?", (playlist_id,)
            ).fetchone()
            conn.close()
            if row:
                result = dict(row)
                try:
                    result["tracks"] = json.loads(result.get("tracks_json", "[]"))
                except (json.JSONDecodeError, TypeError):
                    result["tracks"] = []
                return result
            return None

    def get_all_cached_playlists(self):
        """Get all cached playlists for offline library browsing."""
        with self._lock:
            conn = self._connect()
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT playlist_id, title, author, track_count, last_synced FROM library_cache ORDER BY title"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def cache_library_playlists(self, playlists):
        """Cache the list of library playlists (not their tracks)."""
        with self._lock:
            conn = self._connect()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS library_playlists_cache (
                    id INTEGER PRIMARY KEY,
                    data_json TEXT,
                    last_synced TEXT
                )
            """)
            conn.execute("DELETE FROM library_playlists_cache")
            conn.execute("""
                INSERT INTO library_playlists_cache (id, data_json, last_synced)
                VALUES (1, ?, ?)
            """, (
                json.dumps(playlists, ensure_ascii=False),
                time.strftime("%Y-%m-%dT%H:%M:%S"),
            ))
            conn.commit()
            conn.close()

    def get_cached_library_playlists(self):
        """Get cached library playlists list for offline browsing."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT data_json FROM library_playlists_cache WHERE id = 1"
                ).fetchone()
                conn.close()
                if row:
                    return json.loads(row[0])
            except Exception:
                conn.close()
            return None

    def cache_library_albums(self, albums):
        """Cache the list of library albums."""
        with self._lock:
            conn = self._connect()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS library_albums_cache (
                    id INTEGER PRIMARY KEY,
                    data_json TEXT,
                    last_synced TEXT
                )
            """)
            conn.execute("DELETE FROM library_albums_cache")
            conn.execute("""
                INSERT INTO library_albums_cache (id, data_json, last_synced)
                VALUES (1, ?, ?)
            """, (
                json.dumps(albums, ensure_ascii=False),
                time.strftime("%Y-%m-%dT%H:%M:%S"),
            ))
            conn.commit()
            conn.close()

    def get_cached_library_albums(self):
        """Get cached library albums list for offline browsing."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT data_json FROM library_albums_cache WHERE id = 1"
                ).fetchone()
                conn.close()
                if row:
                    return json.loads(row[0])
            except Exception:
                conn.close()
            return None

    def cache_library_artists(self, artists):
        """Cache the list of library subscriptions."""
        with self._lock:
            conn = self._connect()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS library_artists_cache (
                    id INTEGER PRIMARY KEY,
                    data_json TEXT,
                    last_synced TEXT
                )
            """)
            conn.execute("DELETE FROM library_artists_cache")
            conn.execute("""
                INSERT INTO library_artists_cache (id, data_json, last_synced)
                VALUES (1, ?, ?)
            """, (
                json.dumps(artists, ensure_ascii=False),
                time.strftime("%Y-%m-%dT%H:%M:%S"),
            ))
            conn.commit()
            conn.close()

    def get_cached_library_artists(self):
        """Get cached library artists for offline browsing."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT data_json FROM library_artists_cache WHERE id = 1"
                ).fetchone()
                conn.close()
                if row:
                    return json.loads(row[0])
            except Exception:
                conn.close()
            return None


class DownloadManager(GObject.Object):
    """Manages song downloads with metadata tagging."""

    __gsignals__ = {
        "progress": (GObject.SignalFlags.RUN_FIRST, None, (int, int, str)),  # done, total, current_title
        "complete": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "item-done": (GObject.SignalFlags.RUN_FIRST, None, (str, bool, str)),  # video_id, success, message
        "item-progress": (GObject.SignalFlags.RUN_FIRST, None, (str, float)),  # video_id, fraction 0.0-1.0
        "item-queued": (GObject.SignalFlags.RUN_FIRST, None, (str,)),  # video_id
    }

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.db = DownloadDB()
        self._queue = []
        self._lock = threading.Lock()
        self._downloading = False
        self._total = 0
        self._done = 0
        self._pending_playlists = []  # [{id, title, tracks, thumb_url}]

    def is_downloaded(self, video_id):
        return self.db.is_downloaded(video_id)

    def is_queued(self, video_id):
        """Check if a video is currently in the download queue."""
        with self._lock:
            return any(q["videoId"] == video_id for q in self._queue)

    def get_local_path(self, video_id):
        return self.db.get_local_path(video_id)

    def queue_track(self, track, album_title=None, album_id=None, track_number=None):
        """Add a track to the download queue."""
        vid = track.get("videoId")
        if not vid:
            return
        # Skip if already downloaded
        if self.db.is_downloaded(vid):
            return

        # Get album from the track itself, not the playlist name
        track_album = ""
        track_album_id = ""
        if isinstance(track.get("album"), dict):
            track_album = track["album"].get("name", "")
            track_album_id = track["album"].get("id", "")
        elif isinstance(track.get("album"), str):
            track_album = track["album"]

        item = {
            "videoId": vid,
            "title": track.get("title", "Unknown"),
            "artists": track.get("artists", []),
            "album": track_album,  # Real album, not playlist name
            "album_id": track_album_id or album_id or "",
            "playlist_title": album_title or "",  # Keep playlist name separately for m3u8
            "track_number": track_number,
            "duration_seconds": track.get("duration_seconds", 0),
            "thumbnails": track.get("thumbnails", []),
            "thumbnail_url": track.get("thumbnails", [{}])[-1].get("url", "") if track.get("thumbnails") else track.get("thumb", ""),
        }

        with self._lock:
            # Avoid duplicates in queue
            if not any(q["videoId"] == vid for q in self._queue):
                self._queue.append(item)
                self._total += 1
                GLib.idle_add(self.emit, "item-queued", vid)

    def queue_tracks(self, tracks, album_title=None, album_id=None):
        """Queue multiple tracks (album/playlist)."""
        for i, t in enumerate(tracks):
            self.queue_track(t, album_title, album_id, track_number=i + 1)

    def start(self):
        """Start processing the download queue."""
        if self._downloading:
            return
        if not self._queue:
            return
        self._downloading = True
        self._done = 0
        self._total = len(self._queue)
        threading.Thread(target=self._process_queue, daemon=True).start()

    def _make_cookie_file(self):
        """Create a temporary Netscape cookie file from ytmusicapi auth. Returns path or None."""
        import tempfile
        if not self.client.is_authenticated() or not self.client.api:
            return None
        cookie_str = self.client.api.headers.get("Cookie", "")
        if not cookie_str:
            return None
        cookie_fd, cookie_file = tempfile.mkstemp(suffix=".txt")
        now = int(time.time()) + 3600 * 24 * 365
        with os.fdopen(cookie_fd, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for part in cookie_str.split(";"):
                if "=" in part:
                    pair = part.strip().split("=", 1)
                    if len(pair) == 2:
                        f.write(f".youtube.com\tTRUE\t/\tTRUE\t{now}\t{pair[0]}\t{pair[1]}\n")
        return cookie_file

    def _download_one(self, item, fmt_key, fmt, music_dir):
        """Download and tag a single track. Called from worker threads."""
        from yt_dlp import YoutubeDL
        from ui.utils import get_high_res_url
        import shutil
        import tempfile

        vid = item["videoId"]
        title = item["title"]
        artist_list = item.get("artists", [])
        artist_str = ", ".join(a.get("name", "") for a in artist_list if isinstance(a, dict))
        if not artist_str:
            artist_str = "Unknown Artist"
        album = item.get("album", "") or ""
        track_num = None
        thumb_url = item.get("thumbnail_url", "")
        if thumb_url:
            thumb_url = get_high_res_url(thumb_url) or thumb_url

        album_artist = ""
        release_year = ""
        track_total = 0

        # Fetch real metadata from YTM if album or other info is missing
        if not album or not thumb_url or not artist_str or artist_str == "Unknown Artist":
            try:
                wp = self.client.get_watch_playlist(video_id=vid)
                if wp and wp.get("tracks"):
                    wt = wp["tracks"][0]
                    if not album:
                        wt_album = wt.get("album")
                        if isinstance(wt_album, dict):
                            album = wt_album.get("name", "")
                            if not item.get("album_id") and wt_album.get("id"):
                                item["album_id"] = wt_album["id"]
                        elif isinstance(wt_album, str):
                            album = wt_album
                    if not artist_str or artist_str == "Unknown Artist":
                        wt_artists = wt.get("artists", [])
                        if wt_artists:
                            artist_str = ", ".join(
                                a.get("name", "") for a in wt_artists if isinstance(a, dict)
                            ) or artist_str
                    if not title or title == "Unknown":
                        title = wt.get("title", title)
                    if not thumb_url:
                        wt_thumbs = wt.get("thumbnail")
                        if isinstance(wt_thumbs, list) and wt_thumbs:
                            thumb_url = get_high_res_url(wt_thumbs[-1].get("url", "")) or wt_thumbs[-1].get("url", "")
                        elif isinstance(wt_thumbs, dict):
                            wt_thumb_list = wt_thumbs.get("thumbnails", [])
                            if wt_thumb_list:
                                thumb_url = get_high_res_url(wt_thumb_list[-1]["url"]) or wt_thumb_list[-1]["url"]
            except Exception:
                pass

        # Fetch album-level metadata
        album_id = item.get("album_id", "")
        if album_id and album_id.startswith("MPRE"):
            try:
                album_data = self.client.get_album(album_id)
                if album_data:
                    ab_artists = album_data.get("artists", [])
                    if ab_artists:
                        album_artist = ", ".join(
                            a.get("name", "") for a in ab_artists if isinstance(a, dict)
                        )
                    release_year = album_data.get("year", "") or ""
                    track_total = album_data.get("trackCount", 0) or 0
                    ab_tracks = album_data.get("tracks", [])
                    for idx, at in enumerate(ab_tracks):
                        if at.get("videoId") == vid:
                            track_num = idx + 1
                            break
                    if track_num is None and ab_tracks:
                        for idx, at in enumerate(ab_tracks):
                            if at.get("title", "").lower() == title.lower():
                                track_num = idx + 1
                                break
                    if not album:
                        album = album_data.get("title", "")
                    if not thumb_url:
                        ab_thumbs = album_data.get("thumbnails", [])
                        if ab_thumbs:
                            thumb_url = get_high_res_url(ab_thumbs[-1]["url"]) or ab_thumbs[-1]["url"]
            except Exception:
                pass

        # File path: ~/Music/YouTube Music/Artist/Title.ext
        artist_dir = _sanitize_filename(artist_str.split(",")[0].strip())
        song_name = _sanitize_filename(title)
        filename = f"{song_name}.{fmt['ext']}"
        dir_path = os.path.join(music_dir, artist_dir)
        file_path = os.path.join(dir_path, filename)

        # Never overwrite
        if os.path.exists(file_path):
            self.db.add_download(
                vid, title, artist_str, album, item.get("album_id", ""),
                track_num, item.get("duration_seconds", 0),
                file_path, None, thumb_url,
                os.path.getsize(file_path), fmt_key,
            )
            return vid, True, "Already exists", title

        os.makedirs(dir_path, exist_ok=True)

        tmp_dir = tempfile.mkdtemp()
        tmp_file = os.path.join(tmp_dir, f"download.{fmt['ext']}")

        def _ydl_progress_hook(d, _vid=vid):
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    frac = min(downloaded / total, 1.0)
                    GLib.idle_add(self.emit, "item-progress", _vid, frac)

        ydl_opts = {
            "format": fmt["ydl_format"],
            "outtmpl": tmp_file.rsplit(".", 1)[0] + ".%(ext)s",
            "quiet": True,
            "no_warnings": True,
            "js_runtimes": {"node": {}},
            "progress_hooks": [_ydl_progress_hook],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": fmt_key if fmt_key != "m4a" else "aac",
                "preferredquality": "0",
            }],
        }
        if self._shared_cookie_file:
            ydl_opts["cookiefile"] = self._shared_cookie_file
        if self.client.is_authenticated() and self.client.api:
            ua = self.client.api.headers.get("User-Agent")
            if ua:
                ydl_opts["user_agent"] = ua

        url = f"https://music.youtube.com/watch?v={vid}"
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded file
        actual_file = None
        for f in os.listdir(tmp_dir):
            if f.startswith("download"):
                actual_file = os.path.join(tmp_dir, f)
                break

        if not actual_file or not os.path.exists(actual_file):
            raise Exception("Download produced no output file")

        actual_ext = actual_file.rsplit(".", 1)[-1]
        if actual_ext != fmt["ext"]:
            filename = f"{song_name}.{actual_ext}"
            file_path = os.path.join(dir_path, filename)

        # Download cover art for embedding (try fallbacks for video thumbnails)
        # YouTube returns a tiny 120x90 placeholder JPEG (~1KB) for missing qualities
        # instead of a real 404, so we check size > 5000 to skip those
        cover_data = None
        if thumb_url:
            from ui.utils import get_ytimg_fallbacks
            urls_to_try = [thumb_url] + get_ytimg_fallbacks(thumb_url)
            for try_url in urls_to_try:
                try:
                    resp = requests.get(try_url, timeout=15)
                    if resp.status_code == 200 and len(resp.content) > 5000:
                        cover_data = resp.content
                        break
                except Exception:
                    continue

        # Tag metadata
        self._tag_file(actual_file, actual_ext, title, artist_str, album,
                       track_num, track_total, vid, item.get("album_id", ""),
                       cover_data, item.get("duration_seconds", 0),
                       album_artist=album_artist, release_year=release_year)

        # Move to final location
        if not os.path.exists(file_path):
            shutil.move(actual_file, file_path)
        else:
            os.remove(actual_file)

        shutil.rmtree(tmp_dir, ignore_errors=True)

        # Register in DB
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        self.db.add_download(
            vid, title, artist_str, album, item.get("album_id", ""),
            track_num, item.get("duration_seconds", 0),
            file_path, None, thumb_url, file_size, actual_ext,
        )

        return vid, True, "Downloaded", title

    def _process_queue(self):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        # Pre-import yt-dlp on the main thread to avoid concurrent plugin registration
        import yt_dlp  # noqa: F401

        fmt_key = get_preferred_format()
        fmt = FORMATS.get(fmt_key, FORMATS[DEFAULT_FORMAT])
        music_dir = get_music_dir()
        max_workers = 3

        self._shared_cookie_file = self._make_cookie_file()

        # Take all items from queue upfront
        with self._lock:
            items = list(self._queue)
            self._queue.clear()

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for item in items:
                fut = pool.submit(self._download_one, item, fmt_key, fmt, music_dir)
                futures[fut] = item

            for fut in as_completed(futures):
                item = futures[fut]
                vid = item["videoId"]
                try:
                    vid, success, msg, title = fut.result()
                    self._done += 1
                    GLib.idle_add(self.emit, "progress", self._done, self._total, title)
                    GLib.idle_add(self.emit, "item-done", vid, success, msg)
                    if success:
                        self._update_playlists_for(vid)
                except Exception as e:
                    self._done += 1
                    GLib.idle_add(self.emit, "progress", self._done, self._total, item.get("title", ""))
                    GLib.idle_add(self.emit, "item-done", vid, False, str(e)[:60])
                    print(f"[DOWNLOAD] Error downloading {item.get('title')}: {e}")

        self._downloading = False
        self._total = 0
        self._done = 0
        self._pending_playlists = []
        # Clean up shared cookie file
        if self._shared_cookie_file and os.path.exists(self._shared_cookie_file):
            try:
                os.remove(self._shared_cookie_file)
            except OSError:
                pass
            self._shared_cookie_file = None
        GLib.idle_add(self.emit, "complete")

    def _tag_file(self, filepath, ext, title, artist, album, track_num,
                  track_total, video_id, album_id, cover_data_or_path,
                  duration_seconds, album_artist="", release_year=""):
        """Write ID3/Vorbis/MP4 metadata including YTM identifiers.
        cover_data_or_path can be bytes (raw image data) or a file path string."""
        try:
            import mutagen
            from mutagen.oggopus import OggOpus
            from mutagen.oggvorbis import OggVorbis
            from mutagen.flac import FLAC, Picture
            from mutagen.mp3 import MP3
            from mutagen.mp4 import MP4
            from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TRCK, APIC, COMM, TXXX, TDRC

            cover_data = None
            if isinstance(cover_data_or_path, bytes):
                cover_data = cover_data_or_path
            elif isinstance(cover_data_or_path, str) and os.path.exists(cover_data_or_path):
                with open(cover_data_or_path, "rb") as f:
                    cover_data = f.read()

            # Custom comment with YTM identifiers
            ytm_comment = json.dumps({
                "videoId": video_id,
                "albumId": album_id,
                "source": "YouTube Music (Mixtapes)",
            })

            # Track number string: "3/12" or "3"
            trck_str = ""
            if track_num:
                trck_str = str(track_num)
                if track_total:
                    trck_str = f"{track_num}/{track_total}"

            if ext == "mp3":
                audio = MP3(filepath, ID3=ID3)
                try:
                    audio.add_tags()
                except mutagen.id3.error:
                    pass
                audio.tags.add(TIT2(encoding=3, text=title))
                audio.tags.add(TPE1(encoding=3, text=artist))
                audio.tags.add(TALB(encoding=3, text=album))
                if album_artist:
                    audio.tags.add(TPE2(encoding=3, text=album_artist))
                if trck_str:
                    audio.tags.add(TRCK(encoding=3, text=trck_str))
                if release_year:
                    audio.tags.add(TDRC(encoding=3, text=release_year))
                audio.tags.add(COMM(encoding=3, lang="eng", desc="ytm_metadata", text=ytm_comment))
                audio.tags.add(TXXX(encoding=3, desc="YTMUSIC_VIDEO_ID", text=video_id))
                if cover_data:
                    audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_data))
                audio.save()

            elif ext == "m4a" or ext == "aac":
                audio = MP4(filepath)
                audio["\xa9nam"] = title
                audio["\xa9ART"] = artist
                audio["\xa9alb"] = album
                if album_artist:
                    audio["aART"] = [album_artist]
                if track_num:
                    audio["trkn"] = [(track_num, track_total or 0)]
                if release_year:
                    audio["\xa9day"] = [release_year]
                audio["\xa9cmt"] = ytm_comment
                if cover_data:
                    from mutagen.mp4 import MP4Cover
                    audio["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]
                audio.save()

            elif ext in ("opus", "ogg"):
                if ext == "opus":
                    audio = OggOpus(filepath)
                else:
                    audio = OggVorbis(filepath)
                audio["title"] = title
                audio["artist"] = artist
                audio["album"] = album
                if album_artist:
                    audio["albumartist"] = album_artist
                if track_num:
                    audio["tracknumber"] = str(track_num)
                if track_total:
                    audio["tracktotal"] = str(track_total)
                if release_year:
                    audio["date"] = release_year
                audio["comment"] = ytm_comment
                audio["ytmusic_video_id"] = video_id
                if cover_data:
                    import base64
                    pic = Picture()
                    pic.data = cover_data
                    pic.type = 3
                    pic.mime = "image/jpeg"
                    pic.desc = "Cover"
                    audio["metadata_block_picture"] = base64.b64encode(pic.write()).decode("ascii")
                audio.save()

            elif ext == "flac":
                audio = FLAC(filepath)
                audio["title"] = title
                audio["artist"] = artist
                audio["album"] = album
                if album_artist:
                    audio["albumartist"] = album_artist
                if track_num:
                    audio["tracknumber"] = str(track_num)
                if track_total:
                    audio["tracktotal"] = str(track_total)
                if release_year:
                    audio["date"] = release_year
                audio["comment"] = ytm_comment
                audio["ytmusic_video_id"] = video_id
                if cover_data:
                    pic = Picture()
                    pic.data = cover_data
                    pic.type = 3
                    pic.mime = "image/jpeg"
                    pic.desc = "Cover"
                    audio.add_picture(pic)
                audio.save()

        except Exception as e:
            print(f"[DOWNLOAD] Tagging error for {filepath}: {e}")

    def register_playlist(self, playlist_id, title, tracks, thumb_url=None):
        """Register a playlist for incremental m3u8 generation."""
        self._pending_playlists.append({
            "id": playlist_id or "",
            "title": title,
            "tracks": tracks,
            "thumb_url": thumb_url,
        })
        # Download playlist cover immediately
        if thumb_url:
            music_dir = get_music_dir()
            playlists_dir = os.path.join(music_dir, "playlists")
            os.makedirs(playlists_dir, exist_ok=True)
            safe_name = _sanitize_filename(title)
            cover_path = os.path.join(playlists_dir, f"{safe_name}.jpg")
            if not os.path.exists(cover_path):
                try:
                    from ui.utils import get_high_res_url
                    url = get_high_res_url(thumb_url) or thumb_url
                    resp = requests.get(url, timeout=15)
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        with open(cover_path, "wb") as f:
                            f.write(resp.content)
                except Exception:
                    pass

    def _update_playlists_for(self, video_id):
        """Regenerate m3u8 for any pending playlist containing this video."""
        music_dir = get_music_dir()
        playlists_dir = os.path.join(music_dir, "playlists")
        os.makedirs(playlists_dir, exist_ok=True)

        for pl in self._pending_playlists:
            # Check if this video is in the playlist
            if not any(t.get("videoId") == video_id for t in pl.get("tracks", [])):
                continue
            safe_name = _sanitize_filename(pl["title"])
            m3u_path = os.path.join(playlists_dir, f"{safe_name}.m3u8")
            try:
                with open(m3u_path, "w", encoding="utf-8") as f:
                    f.write("#EXTM3U\n")
                    f.write(f"#PLAYLIST:{pl['title']}\n")
                    for t in pl["tracks"]:
                        vid = t.get("videoId")
                        if not vid:
                            continue
                        local = self.db.get_local_path(vid)
                        if local and os.path.exists(local):
                            rel_path = os.path.relpath(local, playlists_dir)
                            dur = t.get("duration_seconds", 0)
                            song_title = t.get("title", "Unknown")
                            artists = t.get("artists", [])
                            artist = ", ".join(
                                a.get("name", "") for a in artists if isinstance(a, dict)
                            ) if artists else ""
                            f.write(f"#EXTINF:{dur},{artist} - {song_title}\n")
                            f.write(f"{rel_path}\n")
            except Exception as e:
                print(f"[DOWNLOAD] Error updating playlist {pl['title']}: {e}")

    @staticmethod
    def extract_cover_from_file(filepath):
        """Extract embedded cover art from an audio file. Returns bytes or None."""
        if not filepath or not os.path.exists(filepath):
            return None
        try:
            ext = filepath.rsplit(".", 1)[-1].lower()

            if ext == "mp3":
                from mutagen.mp3 import MP3
                from mutagen.id3 import ID3
                audio = MP3(filepath, ID3=ID3)
                for tag in audio.tags.values():
                    if hasattr(tag, 'data') and hasattr(tag, 'mime') and 'image' in str(getattr(tag, 'mime', '')):
                        return tag.data

            elif ext in ("m4a", "aac"):
                from mutagen.mp4 import MP4
                audio = MP4(filepath)
                covrs = audio.get("covr", [])
                if covrs:
                    return bytes(covrs[0])

            elif ext in ("opus", "ogg"):
                import base64
                from mutagen.oggopus import OggOpus
                from mutagen.oggvorbis import OggVorbis
                from mutagen.flac import Picture
                try:
                    audio = OggOpus(filepath) if ext == "opus" else OggVorbis(filepath)
                except Exception:
                    return None
                pics = audio.get("metadata_block_picture", [])
                if pics:
                    pic = Picture(base64.b64decode(pics[0]))
                    return pic.data

            elif ext == "flac":
                from mutagen.flac import FLAC
                audio = FLAC(filepath)
                if audio.pictures:
                    return audio.pictures[0].data

        except Exception as e:
            print(f"[DOWNLOAD] Cover extraction error for {filepath}: {e}")
        return None
