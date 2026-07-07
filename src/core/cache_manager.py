import os
import sqlite3
from pathlib import Path
from typing import List, Optional

class CacheManager:
    """
    Manages indexing cache using an isolated SQLite database.
    Stores directory listings for archive files to make opening them instant.
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.db_dir = Path.home() / ".zrar"
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.db_dir / "zrar_cache.db"
        self._init_db()
        
    def _init_db(self):
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Create archives table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS archives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE,
                    mtime REAL,
                    size INTEGER
                )
            """)
            
            # Create entries table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    archive_id INTEGER,
                    filename TEXT,
                    file_size INTEGER,
                    compress_size INTEGER,
                    is_dir INTEGER,
                    date_time TEXT,
                    FOREIGN KEY (archive_id) REFERENCES archives (id) ON DELETE CASCADE
                )
            """)
            
            # Add database index
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_archive ON entries (archive_id)")
            
            conn.commit()
            conn.close()
        except Exception as e:
            from .logger import get_logger
            get_logger().error(f"Failed to initialize SQLite cache database: {e}")

    def get_cached_entries(self, archive_path: Path) -> Optional[List[dict]]:
        """Fetch cached list entries if file path, modification time, and size match."""
        try:
            archive_path = Path(archive_path).resolve()
            if not archive_path.exists():
                return None
                
            stat = archive_path.stat()
            mtime = stat.st_mtime
            size = stat.st_size
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id FROM archives WHERE file_path = ? AND mtime = ? AND size = ?",
                (str(archive_path), mtime, size)
            )
            row = cursor.fetchone()
            
            if not row:
                conn.close()
                return None
                
            archive_id = row[0]
            
            cursor.execute(
                "SELECT filename, file_size, compress_size, is_dir, date_time FROM entries WHERE archive_id = ?",
                (archive_id,)
            )
            rows = cursor.fetchall()
            
            entries = []
            for r in rows:
                entries.append({
                    'filename': r[0],
                    'file_size': r[1],
                    'compress_size': r[2],
                    'is_dir': bool(r[3]),
                    'date_time': r[4]
                })
                
            conn.close()
            return entries
        except Exception as e:
            from .logger import get_logger
            get_logger().error(f"Error fetching cache for {archive_path.name}: {e}")
            return None

    def save_entries_to_cache(self, archive_path: Path, entries: List[dict]):
        """Starts a background thread to write entries to the database cache."""
        import threading
        t = threading.Thread(
            target=self._save_entries_worker, 
            args=(archive_path, entries), 
            daemon=True
        )
        t.start()
        
    def _save_entries_worker(self, archive_path: Path, entries: List[dict]):
        try:
            archive_path = Path(archive_path).resolve()
            if not archive_path.exists():
                return
                
            stat = archive_path.stat()
            mtime = stat.st_mtime
            size = stat.st_size
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Explicitly enable foreign key cascade deletes in SQLite
            cursor.execute("PRAGMA foreign_keys = ON")
            
            # Delete any stale record
            cursor.execute("DELETE FROM archives WHERE file_path = ?", (str(archive_path),))
            
            # Insert archive metadata
            cursor.execute(
                "INSERT INTO archives (file_path, mtime, size) VALUES (?, ?, ?)",
                (str(archive_path), mtime, size)
            )
            archive_id = cursor.lastrowid
            
            # Bulk insert entries for speed
            insert_data = [
                (archive_id, e['filename'], e['file_size'], e['compress_size'], 1 if e['is_dir'] else 0, e['date_time'])
                for e in entries
            ]
            
            cursor.executemany(
                "INSERT INTO entries (archive_id, filename, file_size, compress_size, is_dir, date_time) VALUES (?, ?, ?, ?, ?, ?)",
                insert_data
            )
            
            conn.commit()
            conn.close()
            
            from .logger import get_logger
            get_logger().info(f"Successfully cached {len(entries)} file index entries for {archive_path.name}")
        except Exception as e:
            from .logger import get_logger
            get_logger().error(f"Failed to write entries cache for {archive_path.name}: {e}")
