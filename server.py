import os
import threading
import json
import datetime
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, abort
from whoosh.index import create_in, open_dir, exists_in
from whoosh.fields import Schema, TEXT, ID, STORED, NGRAMWORDS
from whoosh.qparser import MultifieldParser
import fitz
from docx import Document
import logging
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

# --- LOGGING ---
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# --- KONFIGURACIJA ---
#INDEX_DIR = "index_db"
INDEX_DIR = os.path.join(Path.home(), ".local_search")
CONFIG_FILE = "config.json"
app = Flask(__name__, template_folder='.')
app.config['TEMPLATES_AUTO_RELOAD'] = True

config_lock = threading.Lock()
indexing_in_progress = threading.Event()

observer_lock = threading.Lock()
current_observer = None


def get_default_home():
    return str(Path.home())


def load_config():
    default = {
        "watch_path": get_default_home(),
        "app_name": "Local Search",
        "ignored_dirs": [],
        "index_content_types": []
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                return {**default, **loaded}
        except Exception as e:
            log.warning(f"Ne mogu ucitati config: {e}, koristim defaulte.")
    return default


config = load_config()

TEXT_EXTS  = ('.txt', '.py', '.js', '.html', '.css', '.sh', '.csv', '.json',
              '.md', '.log', '.conf', '.yaml', '.yml', '.ini', '.bat')
IMG_EXTS   = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp')
VIDEO_EXTS = ('.mp4', '.webm', '.ogg', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v')

CONTENT_TYPE_GROUPS = {
    "pdf":  {"label": "PDF dokumenti",      "exts": [".pdf"]},
    "docx": {"label": "Word dokumenti",     "exts": [".docx", ".doc"]},
    "text": {"label": "Tekstualni fajlovi", "exts": list(TEXT_EXTS)},
}


def should_index_content(ext: str) -> bool:
    with config_lock:
        enabled = config.get("index_content_types", [])
    for group_key, group in CONTENT_TYPE_GROUPS.items():
        if group_key in enabled and ext in group["exts"]:
            return True
    return False


def is_safe_path(path: str) -> bool:
    with config_lock:
        watch = config["watch_path"]
    try:
        requested = Path(path).resolve()
        base = Path(watch).resolve()
        return requested.is_relative_to(base)
    except Exception:
        return False


class SearchEngine:
    def __init__(self):
        self.schema = Schema(
            path=ID(stored=True, unique=True),
            filename=TEXT(stored=True),
            filename_ng=NGRAMWORDS(stored=False, minsize=2),
            folders=TEXT(stored=False),
            folders_ng=NGRAMWORDS(stored=False, minsize=2),
            extension=TEXT(stored=True),
            content=TEXT(stored=True),
            mtime=STORED,
            size=STORED
        )
        if not os.path.exists(INDEX_DIR):
            os.makedirs(INDEX_DIR)

        lock_path = Path(INDEX_DIR) / "write.lock"
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception as e:
                log.warning(f"Ne mogu obrisati write.lock: {e}")

        if exists_in(INDEX_DIR):
            self.ix = open_dir(INDEX_DIR)
        else:
            self.ix = create_in(INDEX_DIR, self.schema)

    def extract_content(self, file_path):
        ext = Path(file_path).suffix.lower()
        if not should_index_content(ext):
            return ""
        try:
            if ext in TEXT_EXTS:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read(100000)
            elif ext == ".pdf":
                text = ""
                with fitz.open(file_path) as doc:
                    for page in doc:
                        text += page.get_text()
                        if len(text) > 100000:
                            break
                return text
            elif ext in (".docx", ".doc"):
                doc = Document(file_path)
                return "\n".join([p.text for p in doc.paragraphs])[:100000]
        except Exception as e:
            log.debug(f"Ne mogu ekstraktati sadrzaj iz {file_path}: {e}")
        return ""

    def index_file(self, full_path):
        file = Path(full_path).name
        try:
            stat = os.stat(full_path)
            content = self.extract_content(full_path)
            writer = self.ix.writer()
            folder_parts = " ".join(Path(full_path).parent.parts)
            writer.update_document(
                path=full_path,
                filename=file,
                filename_ng=file,
                folders=folder_parts,
                folders_ng=folder_parts,
                extension=Path(file).suffix.lower(),
                content=content,
                mtime=stat.st_mtime,
                size=stat.st_size
            )
            writer.commit()
            log.info(f"[WATCHDOG] Indeksirano: {full_path}")
        except Exception as e:
            log.warning(f"[WATCHDOG] Ne mogu indeksirati {full_path}: {e}")

    def delete_file(self, full_path):
        try:
            writer = self.ix.writer()
            writer.delete_by_term('path', full_path)
            writer.commit()
            log.info(f"[WATCHDOG] Obrisano iz indexa: {full_path}")
        except Exception as e:
            log.warning(f"[WATCHDOG] Ne mogu obrisati iz indexa {full_path}: {e}")

    def search(self, query_str):
        self.ix = self.ix.refresh()
        results = []
        with self.ix.searcher() as searcher:
            parser = MultifieldParser(["filename_ng", "folders_ng", "filename", "folders", "extension", "content"], self.ix.schema)
            try:
                query = parser.parse(query_str)
            except Exception as e:
                log.warning(f"Greska parsiranja upita: {e}")
                return []
            hits = searcher.search(query, limit=100)
            for hit in hits:
                p = hit['path']
                ext = Path(p).suffix.lower()
                s_bytes = hit.get('size', 0)
                if s_bytes > 1024 * 1024:
                    s_str = f"{s_bytes / (1024 * 1024):.1f} MB"
                elif s_bytes > 1024:
                    s_str = f"{s_bytes / 1024:.1f} KB"
                else:
                    s_str = f"{s_bytes} B"

                if ext in IMG_EXTS:
                    ftype = "image"
                elif ext == ".pdf":
                    ftype = "pdf"
                elif ext in VIDEO_EXTS:
                    ftype = "video"
                else:
                    ftype = "text"

                results.append({
                    "name": hit['filename'],
                    "path": p,
                    "size": s_str,
                    "date": datetime.datetime.fromtimestamp(
                        hit.get('mtime', 0)).strftime('%d.%m.%Y. %H:%M'),
                    "ext": ext.replace('.', '').upper() or "FILE",
                    "type": ftype,
                    "snippet": hit['content'][:1000] if hit.get('content') else ""
                })
        return results


engine = SearchEngine()


class GladiatorHandler(FileSystemEventHandler):

    def _is_ignored(self, path: str) -> bool:
        parts = Path(path).parts
        with config_lock:
            ignored = [d.lower() for d in config.get("ignored_dirs", [])]
        return any(p.startswith('.') or p.lower() in ignored for p in parts)

    def on_created(self, event):
        if event.is_directory or self._is_ignored(event.src_path):
            return
        threading.Timer(1.0, engine.index_file, args=[event.src_path]).start()

    def on_modified(self, event):
        if event.is_directory or self._is_ignored(event.src_path):
            return
        threading.Timer(1.0, engine.index_file, args=[event.src_path]).start()

    def on_deleted(self, event):
        if event.is_directory or self._is_ignored(event.src_path):
            return
        engine.delete_file(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        if not self._is_ignored(event.src_path):
            engine.delete_file(event.src_path)
        if not self._is_ignored(event.dest_path):
            threading.Timer(1.0, engine.index_file, args=[event.dest_path]).start()


def _set_observer(obs):
    global current_observer
    with observer_lock:
        current_observer = obs


def start_watchdog(path_to_watch: str):
    """Pokrece PollingObserver u zasebnom threadu — ne blokira i ne ovisi o inotify limitima."""
    global current_observer
    log.info(f"[WATCHDOG] Pokrecam za: {path_to_watch}")

    with observer_lock:
        if current_observer is not None:
            try:
                current_observer.stop()
                current_observer.join(timeout=5)
            except Exception as e:
                log.warning(f"Greska pri zaustavljanju starog observera: {e}")
            current_observer = None

    def _start():
        try:
            handler = GladiatorHandler()
            obs = Observer()
            obs.schedule(handler, path_to_watch, recursive=True)
            obs.daemon = True
            obs.start()
            _set_observer(obs)
            log.info(f"[WATCHDOG] Aktivan na: {path_to_watch}")
            obs.join()
        except Exception as e:
            log.warning(f"[WATCHDOG] GRESKA ({type(e).__name__}): {e}")
            _set_observer(None)

    threading.Thread(target=_start, daemon=True).start()


def run_indexing(path_to_watch, force_reindex=False):
    """
    Inkrementalno indeksiranje.
    force_reindex=True: ignorira mtime i re-indeksira sve fajlove (za promjenu content tipova).
    """
    if indexing_in_progress.is_set():
        log.warning("Indeksiranje vec u tijeku, preskacam.")
        return

    indexing_in_progress.set()
    log.info(f"Skeniranje zapoceto: {path_to_watch} (force={force_reindex})")

    with config_lock:
        ignored = [d.lower() for d in config.get("ignored_dirs", [])]

    try:
        with engine.ix.searcher() as s:
            indexed = {r['path']: r['mtime'] for r in s.all_stored_fields()}
    except Exception as e:
        log.warning(f"Ne mogu ucitati postojeci index: {e}")
        indexed = {}

    log.info(f"U indexu vec: {len(indexed)} datoteka")

    writer = engine.ix.writer(limitmb=1024)
    added = 0
    skipped = 0
    seen_paths = set()

    try:
        for root, dirs, files in os.walk(path_to_watch):
            dirs[:] = [d for d in dirs
                       if not d.startswith('.') and d.lower() not in ignored]

            for file in files:
                full_path = os.path.join(root, file)
                seen_paths.add(full_path)
                try:
                    stat = os.stat(full_path)
                    # Preskoči samo ako nije force i mtime je isti
                    if not force_reindex and full_path in indexed and indexed[full_path] == stat.st_mtime:
                        skipped += 1
                        continue
                    content = engine.extract_content(full_path)
                    folder_parts = " ".join(Path(full_path).parent.parts)
                    writer.update_document(
                        path=full_path,
                        filename=file,
                        filename_ng=file,
                        folders=folder_parts,
                        folders_ng=folder_parts,
                        extension=Path(file).suffix.lower(),
                        content=content,
                        mtime=stat.st_mtime,
                        size=stat.st_size
                    )
                    added += 1
                    if added % 20 == 0:
                        writer.commit()
                        writer = engine.ix.writer()
                        log.info(f"[BAZA] Novo: {added}, preskoceno: {skipped}...")
                except Exception as e:
                    log.debug(f"Preskacam {full_path}: {e}")
                    continue

        deleted = 0
        for path in indexed:
            if path not in seen_paths:
                writer.delete_by_term('path', path)
                deleted += 1

        writer.commit()
        log.info(f"GOTOVO! Novo: {added}, preskoceno: {skipped}, obrisano: {deleted}")

    except Exception as e:
        log.error(f"Greska pri indeksiranju: {e}")
        try:
            writer.cancel()
        except Exception:
            pass
    finally:
        indexing_in_progress.clear()


@app.route("/")
def index():
    q = request.args.get("q", "")
    res = engine.search(q) if q else []
    with engine.ix.searcher() as s:
        count = s.doc_count()
    with config_lock:
        cfg = dict(config)
    return render_template("index.html", query=q, results=res, doc_count=count, config=cfg)


@app.route("/media")
def get_media():
    p = request.args.get("path")
    if not p:
        abort(400)
    if not is_safe_path(p):
        log.warning(f"Odbijen pristup izvan watch_path: {p}")
        abort(403)
    if not os.path.isfile(p):
        abort(404)
    return send_file(p)


@app.route("/list_folders")
def list_folders():
    with config_lock:
        p = config["watch_path"]
        ignored = list(config["ignored_dirs"])
        index_content_types = list(config.get("index_content_types", []))
    try:
        items = os.listdir(p)
        folders = sorted([i for i in items
                          if os.path.isdir(os.path.join(p, i)) and not i.startswith('.')])
        return jsonify(
            folders=folders,
            ignored=ignored,
            index_content_types=index_content_types,
            content_type_groups={k: v["label"] for k, v in CONTENT_TYPE_GROUPS.items()}
        )
    except Exception as e:
        log.error(f"Ne mogu listati mape: {e}")
        return jsonify(folders=[], ignored=[], index_content_types=[], content_type_groups={})


@app.route("/update_settings", methods=['POST'])
def update_settings():
    global config
    data = request.json
    if not data:
        abort(400)

    new_name          = str(data.get("name", "Gladiator")).strip() or "Gladiator"
    new_ignored       = [str(d) for d in data.get("ignored", []) if isinstance(d, str)]
    new_content_types = [str(t) for t in data.get("index_content_types", [])
                         if str(t) in CONTENT_TYPE_GROUPS]

    with config_lock:
        config["app_name"]            = new_name
        config["ignored_dirs"]        = new_ignored
        config["index_content_types"] = new_content_types
        cfg_snapshot = dict(config)

    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg_snapshot, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Ne mogu spremiti config: {e}")
        return jsonify(success=False, error=str(e)), 500

    # Normalno inkrementalno indeksiranje (samo nova/izmijenjena imena)
    threading.Thread(
        target=run_indexing,
        args=(cfg_snapshot["watch_path"],),
        daemon=True
    ).start()
    threading.Thread(
        target=start_watchdog,
        args=(cfg_snapshot["watch_path"],),
        daemon=True
    ).start()

    return jsonify(success=True)


@app.route("/reindex_content", methods=['POST'])
def reindex_content():
    """
    Pokrece force re-indeksiranje sadrzaja — ignorira mtime i prolazi kroz sve fajlove.
    Koristi se kad korisnik promijeni koje tipove zeli indeksirati.
    """
    with config_lock:
        watch = config["watch_path"]

    threading.Thread(
        target=run_indexing,
        args=(watch,),
        kwargs={"force_reindex": True},
        daemon=True
    ).start()

    return jsonify(success=True)


@app.route("/indexing_status")
def indexing_status():
    return jsonify(running=indexing_in_progress.is_set())


@app.route("/open")
def open_file():
    p = request.args.get("path")
    if not p:
        abort(400)
    if not is_safe_path(p):
        log.warning(f"Odbijen pokusaj otvaranja izvan watch_path: {p}")
        abort(403)
    if not os.path.exists(p):
        abort(404)
    try:
        subprocess.run(["xdg-open", p], check=False)
    except Exception as e:
        log.error(f"Ne mogu otvoriti datoteku {p}: {e}")
        return jsonify(success=False, error=str(e)), 500
    return jsonify(success=True)


if __name__ == "__main__":
    watch = config["watch_path"]
    threading.Thread(target=run_indexing, args=(watch,), daemon=True).start()
    threading.Thread(target=start_watchdog, args=(watch,), daemon=True).start()
    log.info("Gladiator (Linux) trci na http://127.0.0.1:5000")
    app.run(port=5000, debug=False, use_reloader=False)
