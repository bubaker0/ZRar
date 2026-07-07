import os
import time
from pathlib import Path
from typing import Tuple, List, Dict, Any

def format_size(size_bytes: int) -> str:
    """Format a size in bytes into a human-readable string (e.g. 1.25 MB)."""
    if size_bytes < 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def format_speed(bytes_per_sec: float) -> str:
    """Format compression/decompression speed (e.g. 4.5 MB/s)."""
    return f"{format_size(int(bytes_per_sec))}/s"

def format_time(seconds: float) -> str:
    """Format seconds into a human-readable duration (MM:SS or HH:MM:SS)."""
    if seconds is None or seconds < 0:
        return "--:--"
    
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

def scan_directory(path: Path) -> Tuple[int, int, List[Path]]:
    """
    Scan a directory to find the total number of files and total size.
    Returns: (total_files, total_size_bytes, file_list)
    """
    total_files = 0
    total_size = 0
    file_list: List[Path] = []
    
    if path.is_file():
        return 1, path.stat().st_size, [path]
        
    try:
        for root, _, files in os.walk(path):
            for file in files:
                file_path = Path(root) / file
                try:
                    total_size += file_path.stat().st_size
                    total_files += 1
                    file_list.append(file_path)
                except (OSError, PermissionError):
                    # Skip files that we can't access
                    continue
    except OSError:
        pass
        
    return total_files, total_size, file_list

def estimate_remaining_time(processed_bytes: int, total_bytes: int, elapsed_time: float) -> float:
    """Estimate remaining time in seconds based on processing speed."""
    if processed_bytes <= 0 or elapsed_time <= 0:
        return -1.0
    
    speed = processed_bytes / elapsed_time
    remaining_bytes = total_bytes - processed_bytes
    
    if remaining_bytes <= 0:
        return 0.0
        
    return remaining_bytes / speed


def show_system_notification(title: str, message: str):
    """Show a native Windows OS toast notification using lightweight PowerShell scripting."""
    import sys
    import subprocess
    if sys.platform == 'win32':
        ps_cmd = (
            "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms'); "
            "$notification = New-Object System.Windows.Forms.NotifyIcon; "
            "$notification.Icon = [System.Drawing.SystemIcons]::Information; "
            f"$notification.BalloonTipTitle = '{title}'; "
            f"$notification.BalloonTipText = '{message}'; "
            "$notification.Visible = $True; "
            "$notification.ShowBalloonTip(5000);"
        )
        try:
            subprocess.Popen(["powershell", "-Command", ps_cmd], 
                             creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass

def get_resource_path(relative_path: str) -> str:
    """Get absolute path to resource, works for dev and for PyInstaller."""
    import sys
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), relative_path)

def is_archive_file(path: Path) -> bool:
    """Helper to check if a file is a supported archive type, including split 7z archives."""
    if not path.is_file():
        return False
    import re
    name_lower = path.name.lower()
    if re.search(r'\.7z\.\d+$', name_lower):
        return True
    suffix = path.suffix.lower()
    return suffix in ['.zrar', '.zip', '.7z', '.tar', '.gz', '.bz2', '.xz', '.rar']
