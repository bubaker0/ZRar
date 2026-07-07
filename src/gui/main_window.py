import time
import os
import sys
import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
from typing import List, Optional, Dict, Any, Union

import customtkinter as ctk

from .theme import COLORS, FONTS, RADII
from .components import BreadcrumbBar, TaskCard, FileListView
from .dialogs import CompressDialog, ExtractDialog, PasswordPromptDialog, SettingsDialog
from ..core.queue_manager import QueueManager, ArchiveTask
from ..core.archiver import get_archive_engine
from ..core.utils import format_size, format_speed, is_archive_file

class MainWindow(ctk.CTk):
    """The primary dashboard and file archiver UI for ZRar."""
    
    def __init__(self, initial_path: Optional[Path] = None, quick_mode: bool = False):
        super().__init__()
        
        self.quick_mode = quick_mode
        # Window setup
        self.title("ZRar - بديل WinRAR الحديث والمجاني")
        self.geometry("960x640")
        if not self.quick_mode:
            self.minsize(800, 500)
        
        # Set window icon
        from ..core.utils import get_resource_path
        icon_path = get_resource_path("ZRar.ico")
        if Path(icon_path).exists():
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass
                
        # Default settings
        self.settings = {
            'theme': 'System',
            'dest_mode': 'same',
            'custom_extract_dir': str(Path.home() / "Documents"),
            'default_format': 'zrar',
            'default_level': 5
        }
        
        # Use System appearance by default
        ctk.set_appearance_mode(self.settings['theme'])
        
        # Layout color
        self.configure(fg_color=COLORS["bg_primary"])
        
        # State variables
        self.current_directory = initial_path or Path.home()
        if not self.current_directory.exists():
            self.current_directory = Path.cwd()
            
        self.is_viewing_archive = False
        self.active_archive_path = Path()
        self.archive_inner_dir = "" # E.g. "folder/subfolder/" (ends with / or empty)
        self.archive_cached_files: List[dict] = []
        self.archive_password: Optional[str] = None
        self.local_cached_items: List[dict] = []
        self._search_after_id = None
        
        # Navigation History (for Back/Forward)
        self.history: List[tuple] = [] # List of (is_archive, path, inner_dir)
        self.history_index = -1
        
        # Queue Manager initialization
        self.queue_manager = QueueManager(ui_update_cb=self._handle_task_notification)
        
        # Assemble UI components
        self._build_ui()
        
        # Load initial directory
        self.navigate_to(self.current_directory)
        
        # Start queue polling
        self._poll_queue_events()
        
        # Protocol handler
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        if self.quick_mode:
            self.withdraw()
        
    def _build_ui(self):
        # 1. Main Grid Layout
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # --- TOP HEADER & TOOLBAR ---
        self.top_frame = ctk.CTkFrame(self, height=80, corner_radius=0, fg_color=COLORS["bg_secondary"], border_width=1, border_color=COLORS["border"])
        self.top_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.top_frame.pack_propagate(False)
        
        # Logo text
        self.logo_label = ctk.CTkLabel(
            self.top_frame, 
            text="⚡ ZRar", 
            font=("Outfit", 22, "bold"), 
            text_color=COLORS["accent"]
        )
        self.logo_label.pack(side="right", padx=15, pady=10)
        
        # Settings Button (Gear icon)
        self.settings_btn = ctk.CTkButton(
            self.top_frame,
            text="⚙️",
            width=34,
            height=34,
            font=("Segoe UI", 16),
            fg_color=COLORS["bg_secondary"],
            hover_color=COLORS["bg_tertiary"],
            text_color=COLORS["text_primary"],
            command=self._action_settings
        )
        self.settings_btn.pack(side="right", padx=(0, 10), pady=10)
        
        # Preview Toggle Button (Eye icon)
        self.preview_toggle_btn = ctk.CTkButton(
            self.top_frame,
            text="👁️",
            width=34,
            height=34,
            font=("Segoe UI", 16),
            fg_color=COLORS["bg_tertiary"],
            hover_color=COLORS["bg_tertiary"],
            text_color=COLORS["text_primary"],
            command=self._action_toggle_preview
        )
        self.preview_toggle_btn.pack(side="right", padx=5, pady=10)
        
        # Toolbar buttons
        self.toolbar_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.toolbar_frame.pack(side="left", fill="y", padx=10, pady=10)
        
        btn_opts = [
            ("➕ ضغط ملف", self._action_compress, COLORS["accent"]),
            ("🔓 فك الضغط", self._action_extract, COLORS["success"]),
            ("🧹 حذف", self._action_delete, COLORS["error"]),
            ("🔄 تحديث", self._action_refresh, COLORS["text_secondary"]),
            ("⚡ سرعة المعالج", self._action_benchmark, COLORS["warning"]),
        ]
        
        for text, command, color in btn_opts:
            btn = ctk.CTkButton(
                self.toolbar_frame,
                text=text,
                command=command,
                width=90,
                height=34,
                font=FONTS["body_bold"],
                fg_color="transparent",
                border_width=1,
                border_color=COLORS["border"],
                corner_radius=RADII["button"],
                text_color=COLORS["text_primary"],
                hover_color=COLORS["border"]
            )
            # Accent buttons can be highlighted
            if text in ["➕ ضغط ملف", "🔓 فك الضغط"]:
                btn.configure(
                    fg_color=color, 
                    text_color="#FFFFFF",
                    border_width=0, 
                    corner_radius=RADII["button"],
                    hover_color=COLORS["accent_hover"] if text == "➕ ضغط ملف" else "#059669"
                )
            btn.pack(side="left", padx=5)
            
        # --- LEFT SIDEBAR (Navigation shortcuts & task list) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=COLORS["bg_secondary"], border_width=1, border_color=COLORS["border"])
        self.sidebar_frame.grid(row=1, column=0, sticky="ns")
        self.sidebar_frame.pack_propagate(False)
        
        # Shortcuts Title
        ctk.CTkLabel(
            self.sidebar_frame, 
            text="الوصول السريع", 
            font=FONTS["subtitle"], 
            text_color=COLORS["text_secondary"], 
            anchor="e"
        ).pack(fill="x", padx=15, pady=(15, 5))
        
        # Shortcut Locations
        shortcuts = [
            ("🏠 المجلد الرئيسي", Path.home()),
            ("🖥️ سطح المكتب", Path.home() / "Desktop"),
            ("📂 المستندات", Path.home() / "Documents"),
            ("📥 التنزيلات", Path.home() / "Downloads"),
        ]
        
        for name, path in shortcuts:
            if path.exists():
                btn = ctk.CTkButton(
                    self.sidebar_frame,
                    text=name,
                    font=FONTS["body"],
                    fg_color=COLORS["bg_secondary"],
                    text_color=COLORS["text_primary"],
                    hover_color=COLORS["bg_tertiary"],
                    anchor="e",
                    height=30,
                    command=lambda p=path: self._nav_from_sidebar(p)
                )
                btn.pack(fill="x", padx=10, pady=2)
                
        # Tasks Panel Title
        self.tasks_title = ctk.CTkLabel(
            self.sidebar_frame, 
            text="مهام الخلفية ⚪ (0)", 
            font=FONTS["subtitle"], 
            text_color=COLORS["text_secondary"], 
            anchor="e"
        )
        self.tasks_title.pack(fill="x", padx=15, pady=(25, 5))
        
        # Scrollable Task Container
        self.task_scroll = ctk.CTkScrollableFrame(
            self.sidebar_frame, 
            fg_color="transparent", 
            height=200
        )
        self.task_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        self.task_cards: Dict[str, TaskCard] = {}
        
        # --- MIDDLE MAIN CONTENT AREA ---
        self.main_content = ctk.CTkFrame(self, fg_color="transparent")
        self.main_content.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        
        # Navigation controls (Bar + Breadcrumbs)
        self.nav_controls = ctk.CTkFrame(self.main_content, fg_color="transparent", height=40)
        self.nav_controls.pack(fill="x", pady=(0, 5))
        
        # Back Button ⬅
        self.back_btn = ctk.CTkButton(
            self.nav_controls,
            text="⬅",
            width=30,
            height=30,
            font=FONTS["body_bold"],
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            command=self._action_history_back
        )
        self.back_btn.pack(side="left", padx=2)
        self.back_btn.configure(state="disabled")
        
        # Up Button ⬆
        self.up_btn = ctk.CTkButton(
            self.nav_controls,
            text="⬆",
            width=30,
            height=30,
            font=FONTS["body_bold"],
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            command=self._action_up
        )
        self.up_btn.pack(side="left", padx=2)
        
        # Breadcrumbs
        self.breadcrumbs = BreadcrumbBar(self.nav_controls, on_navigate=self.navigate_to)
        self.breadcrumbs.pack(side="left", fill="x", expand=True, padx=10)
        
        # Search Entry 🔍
        self.search_entry = ctk.CTkEntry(
            self.nav_controls, 
            placeholder_text="🔍 ابحث في الملفات...", 
            width=180,
            font=FONTS["body"]
        )
        self.search_entry.pack(side="right", padx=5)
        self.search_entry.bind("<KeyRelease>", self._on_search_key_release)
        
        # Explorer & Preview Container
        self.explorer_container = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.explorer_container.pack(fill="both", expand=True)
        
        # File Explorer list
        self.file_explorer = FileListView(self.explorer_container, on_double_click=self._handle_double_click)
        self.file_explorer.pack(side="left", fill="both", expand=True)
        
        # Collapsible Preview Pane (Right side)
        self.preview_pane = ctk.CTkFrame(
            self.explorer_container, 
            width=260, 
            border_width=1, 
            border_color=COLORS["border"], 
            fg_color=COLORS["bg_secondary"],
            corner_radius=RADII["card"]
        )
        self.preview_pane.pack(side="right", fill="both", padx=(10, 0))
        self.preview_pane.pack_propagate(False)
        
        # Build Preview Pane internal layout
        self._build_preview_pane()
        
        # Bind treeview selection update to trigger preview rendering
        self.file_explorer.tree.bind("<<TreeviewSelect>>", lambda e: self.after(50, self._update_preview))
        
        # --- BOTTOM STATUS BAR ---
        self.status_bar = ctk.CTkFrame(self, height=26, corner_radius=0, fg_color=COLORS["bg_secondary"], border_width=1, border_color=COLORS["border"])
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.status_lbl = ctk.CTkLabel(
            self.status_bar, 
            text="جاهز", 
            font=FONTS["caption"], 
            text_color=COLORS["text_secondary"]
        )
        self.status_lbl.pack(side="right", padx=15)
        
        if self.quick_mode:
            self.top_frame.grid_forget()
            self.sidebar_frame.grid_forget()
            self.main_content.grid_forget()
            self.status_bar.grid_forget()
            
            self.quick_frame = ctk.CTkFrame(self, fg_color="transparent")
            self.quick_frame.pack(fill="both", expand=True, padx=10, pady=10)
            
            self.geometry("480x180")
            self.resizable(False, False)
            self.title("معالجة الملفات - ZRar")

    def _poll_queue_events(self):
        """Periodically polls the QueueManager to process background thread events safely."""
        self.queue_manager.process_gui_events()
        self.after(50, self._poll_queue_events)
        
    def _on_close(self):
        """Override close button click to hide to tray instead of quitting."""
        self.hide_to_tray()
        
    def hide_to_tray(self):
        """Hide window and run tray icon in background thread."""
        self.withdraw()
        
        if not hasattr(self, "tray_icon") or not self.tray_icon:
            import threading
            import pystray
            from ..core.utils import get_resource_path
            icon_img = Image.open(get_resource_path("ZRar.ico"))
            
            menu = pystray.Menu(
                pystray.MenuItem("فتح ZRar", self.show_from_tray),
                pystray.MenuItem("الإعدادات", self._action_settings),
                pystray.MenuItem("إنهاء ZRar", self.exit_application)
            )
            
            self.tray_icon = pystray.Icon("ZRar", icon_img, "ZRar", menu)
            
            # Start tray loop in a background thread
            t = threading.Thread(target=self.tray_icon.run, daemon=True)
            t.start()

    def show_from_tray(self):
        """Restore window from tray."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def exit_application(self):
        """Exit application fully from tray."""
        if hasattr(self, "tray_icon") and self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self._on_close_final()

    def _on_close_final(self):
        """Clean shutdown and destroy."""
        self.queue_manager.shutdown()
        self.destroy()
        import os
        os._exit(0)

    def _update_history_buttons(self):
        if self.history_index > 0:
            self.back_btn.configure(state="normal")
        else:
            self.back_btn.configure(state="disabled")

    def navigate_to(self, path: Union[Path, str], inner_dir: str = "", push_history: bool = True):
        """Navigate explorer to path (local folder or within archive)."""
        # Close search/filters if any
        if isinstance(path, str):
            path = Path(path)
            
        old_state = (self.is_viewing_archive, self.current_directory, self.archive_inner_dir)
        
        # Check if the navigation target is a local archive file
        if is_archive_file(path):
            # Start viewing inside this archive
            self.is_viewing_archive = True
            self.active_archive_path = path
            self.archive_inner_dir = inner_dir
            # Fetch files
            success = self._load_archive_contents(path)
            if not success:
                # Failed to open archive (maybe password or error). Reset.
                self.is_viewing_archive = old_state[0]
                self.current_directory = old_state[1]
                self.archive_inner_dir = old_state[2]
                return
        else:
            # Viewing a regular local directory
            self.is_viewing_archive = False
            self.current_directory = path
            self.archive_inner_dir = ""
            self.archive_password = None
            self._load_local_directory(path)
            
        # Update History
        if push_history:
            # Slice history if we were in the middle of it
            self.history = self.history[:self.history_index + 1]
            self.history.append((self.is_viewing_archive, 
                                 self.active_archive_path if self.is_viewing_archive else self.current_directory, 
                                 self.archive_inner_dir))
            self.history_index = len(self.history) - 1
            
        self._update_history_buttons()
        self._update_status_info()

    def _nav_from_sidebar(self, path: Path):
        self.navigate_to(path)
        
    def _load_local_directory(self, path: Path):
        """Scan and display filesystem folder contents."""
        self.breadcrumbs.set_path(path)
        
        try:
            items = []
            for p in path.iterdir():
                try:
                    stat = p.stat()
                    # Arabic descriptions
                    if p.is_dir():
                        type_str = "مجلد ملفات"
                    else:
                        ext = p.suffix.lower()
                        type_str = f"ملف {ext.upper()}" if ext else "ملف"
                        
                    modified_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
                    items.append({
                        'name': p.name,
                        'path': p,
                        'size': stat.st_size if p.is_file() else 0,
                        'is_dir': p.is_dir(),
                        'type_str': type_str,
                        'modified_str': modified_str
                    })
                except (PermissionError, FileNotFoundError):
                    continue
                    
            self.local_cached_items = items
            self._apply_search_filter()
        except Exception as e:
            messagebox.showerror("خطأ في قراءة المجلد", f"تعذر قراءة محتويات المجلد:\n{e}")
            # Try to navigate up
            if path.parent != path:
                self.navigate_to(path.parent)

    def _load_archive_contents(self, archive_path: Path) -> bool:
        """Read files list from the archive to populate the browser."""
        try:
            from ..core.cache_manager import CacheManager
            cache = CacheManager.get_instance()
            
            # Try reading from SQLite cache first
            cached_entries = cache.get_cached_entries(archive_path)
            if cached_entries is not None:
                self.archive_cached_files = cached_entries
                self._render_archive_view()
                return True
                
            engine = get_archive_engine(archive_path)
            
            # Try loading file list
            try:
                self.archive_cached_files = engine.list_files(archive_path, self.archive_password)
                cache.save_entries_to_cache(archive_path, self.archive_cached_files)
            except (ValueError, RuntimeError) as e:
                # If error might be password, prompt user
                if "كلمة مرور" in str(e) or "password" in str(e).lower() or "decrypt" in str(e).lower():
                    # Prompt for password
                    prompt = PasswordPromptDialog(self, archive_path.name)
                    self.wait_window(prompt)
                    
                    if prompt.result is not None:
                        self.archive_password = prompt.result
                        # Try again
                        self.archive_cached_files = engine.list_files(archive_path, self.archive_password)
                        cache.save_entries_to_cache(archive_path, self.archive_cached_files)
                    else:
                        # Cancelled password prompt
                        return False
                else:
                    raise e
                    
            self._render_archive_view()
            return True
        except Exception as e:
            messagebox.showerror("خطأ في قراءة الأرشيف", f"تعذر فتح ملف الأرشيف:\n{e}")
            return False

    def _render_archive_view(self):
        """Filter and display contents of the current virtual folder inside the archive."""
        # Breadcrumbs inside archive
        virt_path = self.active_archive_path / self.archive_inner_dir
        self.breadcrumbs.set_path(virt_path)
        
        query = self.search_entry.get().strip().lower()
        items = []
        
        if query:
            # Global search inside archive
            for entry in self.archive_cached_files:
                fn = entry['filename'].replace('\\', '/')
                # Extract basename
                name = fn.split('/')[-1] if not fn.endswith('/') else fn.split('/')[-2]
                if query in name.lower():
                    items.append({
                        'name': name,
                        'path': self.active_archive_path / fn,
                        'size': entry['file_size'],
                        'is_dir': entry['is_dir'],
                        'type_str': "مجلد أرشيف" if entry['is_dir'] else "ملف أرشيف",
                        'modified_str': entry.get('date_time', 'Unknown')
                    })
            self.file_explorer.populate(items)
            self.status_lbl.configure(text=f"🔍 نتائج البحث: تم العثور على {len(items)} من أصل {len(self.archive_cached_files)} عنصر")
            return
            
        seen_folders = set()
        
        # Normalize inner dir prefix (ensure trailing slash if not root)
        prefix = self.archive_inner_dir
        if prefix and not prefix.endswith('/'):
            prefix += '/'
            
        for entry in self.archive_cached_files:
            fn = entry['filename']
            # Normalise zip separator
            fn = fn.replace('\\', '/')
            
            if fn == prefix:
                continue # Skip self
                
            if not prefix or fn.startswith(prefix):
                # Extract the relative path portion after prefix
                rel = fn[len(prefix):]
                parts = rel.split('/')
                
                # If parts count is 1 (or 2 and the second is empty), it is a direct child
                if len(parts) == 1 or (len(parts) == 2 and parts[1] == ''):
                    name = parts[0]
                    is_dir = entry['is_dir'] or (len(parts) > 1 and parts[1] == '')
                    
                    items.append({
                        'name': name,
                        'path': self.active_archive_path / (prefix + name + ('/' if is_dir else '')),
                        'size': entry['file_size'],
                        'is_dir': is_dir,
                        'type_str': "مجلد أرشيف" if is_dir else "ملف أرشيف",
                        'modified_str': entry.get('date_time', 'Unknown')
                    })
                elif len(parts) > 1:
                    # Indirect child -> represents a subdirectory we must display
                    subfolder_name = parts[0]
                    if subfolder_name not in seen_folders:
                        seen_folders.add(subfolder_name)
                        items.append({
                            'name': subfolder_name,
                            'path': self.active_archive_path / (prefix + subfolder_name + '/'),
                            'size': 0,
                            'is_dir': True,
                            'type_str': "مجلد أرشيف",
                            'modified_str': entry.get('date_time', 'Unknown')
                        })
                        
        self.file_explorer.populate(items)

    def _handle_double_click(self, clicked_path: Path):
        """Handles double clicking files/folders in the explorer."""
        if self.is_viewing_archive:
            # We are double clicking inside the archive
            # Find the virtual relative path
            # clicked_path is: archive_path / inner_relative_path
            rel_parts = clicked_path.parts[len(self.active_archive_path.parts):]
            inner_str = "/".join(rel_parts)
            
            # Check if this virtual path is a folder
            # Virtual folder paths in our render end with '/'
            is_folder = False
            for entry in self.archive_cached_files:
                fn = entry['filename'].replace('\\', '/')
                if fn == inner_str or fn == (inner_str + '/'):
                    is_folder = entry['is_dir'] or fn.endswith('/')
                    break
            # Fallback if folder was dynamically aggregated
            if not is_folder and clicked_path.name in [item['name'] for item in self.file_explorer.current_items_dict.values() if item['is_dir']]:
                is_folder = True # Treat as folder
                
            if inner_str.endswith('/') or is_folder:
                # Navigate inside the archive folder
                # Clean path ending
                if inner_str and not inner_str.endswith('/'):
                    inner_str += '/'
                self.navigate_to(self.active_archive_path, inner_dir=inner_str)
            else:
                # Double clicked a file inside archive -> prompt to extract it
                msg = f"هل تريد استخراج ملف '{clicked_path.name}' من الأرشيف؟"
                if messagebox.askyesno("استخراج ملف فردي", msg):
                    # Prompt location
                    dest = filedialog.askdirectory(title="اختر مجلد الاستخراج")
                    if dest:
                        # Add sub extraction task
                        # In this version, we will extract the whole archive or extract targets
                        # Let's extract this specific file target
                        # To keep it simple, we extract to dest and the queue manager will manage it
                        # Let's run a full decompress task but only targeting this file? Or decompress the whole thing.
                        # For simplicity, extract the whole archive to the selected directory
                        self.queue_manager.add_decompress_task(
                            self.active_archive_path, 
                            Path(dest), 
                            self.archive_password
                        )
        else:
            # Normal file explorer
            if clicked_path.is_dir():
                self.navigate_to(clicked_path)
            else:
                # If it's an archive, we open it
                if is_archive_file(clicked_path):
                    self.navigate_to(clicked_path)
                else:
                    # Open normal file with OS default
                    try:
                        os.startfile(clicked_path)
                    except Exception as e:
                        messagebox.showinfo("فتح الملف", f"لا يوجد برنامج افتراضي لفتح هذا الملف:\n{clicked_path.name}")

    def _action_up(self):
        """Navigate to parent folder/context."""
        if self.is_viewing_archive:
            if self.archive_inner_dir:
                # Go up inside archive folders
                parts = self.archive_inner_dir.rstrip('/').split('/')
                if len(parts) > 1:
                    parent_inner = "/".join(parts[:-1]) + "/"
                else:
                    parent_inner = ""
                self.navigate_to(self.active_archive_path, inner_dir=parent_inner)
            else:
                # We are at the root of the archive. Exit archive and go to its folder!
                self.navigate_to(self.active_archive_path.parent)
        else:
            if self.current_directory.parent != self.current_directory:
                self.navigate_to(self.current_directory.parent)

    def _action_history_back(self):
        if self.history_index > 0:
            self.history_index -= 1
            is_arch, path, inner = self.history[self.history_index]
            
            self.is_viewing_archive = is_arch
            if is_arch:
                self.active_archive_path = path
                self.archive_inner_dir = inner
                self._load_archive_contents(path)
            else:
                self.current_directory = path
                self.archive_inner_dir = ""
                self._load_local_directory(path)
                
            self._update_history_buttons()
            self._update_status_info()

    def _action_refresh(self):
        if self.is_viewing_archive:
            self._load_archive_contents(self.active_archive_path)
        else:
            self._load_local_directory(self.current_directory)

    def _action_settings(self):
        """Open settings dialog to configure ZRar."""
        dialog = SettingsDialog(self, self.settings)
        self.wait_window(dialog)
        
        if dialog.result:
            self.settings.update(dialog.result)
            ctk.set_appearance_mode(self.settings['theme'])
            self.file_explorer.update_style()
            self._action_refresh()

    def _action_compress(self, target_paths: List[Path] = None):
        """Open compression dialog to compress selected explorer items or target paths."""
        if self.is_viewing_archive:
            messagebox.showwarning("تنبيه", "لا يمكن إضافة ملفات لأرشيف أثناء تصفحه حالياً. يرجى الضغط من متصفح الملفات العادي.")
            return
            
        selected_paths = target_paths if target_paths else self.file_explorer.get_selected_paths()
        if not selected_paths:
            messagebox.showinfo("تنبيه", "يرجى اختيار ملف أو مجلد واحد على الأقل لضغطه.")
            return
            
        # Determine default archive name
        default_name = selected_paths[0].stem
        if len(selected_paths) > 1:
            default_name += "_Group"
            
        base_dir = selected_paths[0].parent if target_paths else self.current_directory
        
        dialog = CompressDialog(
            self, 
            default_name, 
            base_dir,
            default_format=self.settings['default_format'],
            default_level=self.settings['default_level']
        )
        self.wait_window(dialog)
        
        if dialog.result:
            if self.quick_mode:
                self.deiconify()
            opts = dialog.result
            self.queue_manager.add_compress_task(
                source_paths=selected_paths,
                archive_path=opts['archive_path'],
                base_dir=base_dir,
                password=opts['password'],
                compression_level=opts['compression_level'],
                volume_size=opts.get('volume_size', 0)
            )
        else:
            if self.quick_mode:
                self.destroy()

    def _action_extract(self, target_archive_path: Path = None):
        """Open extraction dialog to decompress selected archives, current archive, or target archive."""
        archive_path = target_archive_path
        requires_password = False
        
        if not archive_path:
            if self.is_viewing_archive:
                archive_path = self.active_archive_path
                requires_password = (self.archive_password is not None)
            else:
                selected = self.file_explorer.get_selected_paths()
                if not selected:
                    messagebox.showinfo("تنبيه", "يرجى تحديد ملف أرشيف (ZRAR, ZIP, 7Z, TAR, RAR) لفك ضغطه.")
                    return
                # Find first archive
                for p in selected:
                    if is_archive_file(p):
                        archive_path = p
                        break
                if not archive_path:
                    messagebox.showinfo("تنبيه", "الملفات المحددة ليست ملفات أرشيف مدعومة.")
                    return
                    
        # Propose extraction directory (respecting custom settings directory)
        if self.settings['dest_mode'] == 'custom' and self.settings['custom_extract_dir']:
            default_extract_dir = Path(self.settings['custom_extract_dir']) / archive_path.stem
        else:
            default_extract_dir = archive_path.parent / archive_path.stem
        
        dialog = ExtractDialog(self, default_extract_dir, requires_password=requires_password)
        # If password already loaded, insert it automatically
        if requires_password and self.archive_password:
            dialog.pass_entry.insert(0, self.archive_password)
            
        self.wait_window(dialog)
        
        if dialog.result:
            if self.quick_mode:
                self.deiconify()
            opts = dialog.result
            self.queue_manager.add_decompress_task(
                archive_path=archive_path,
                extract_dir=opts['extract_dir'],
                password=opts['password'] or self.archive_password
            )
        else:
            if self.quick_mode:
                self.destroy()

    def _action_extract_direct(self, archive_path: Path, extract_dir: Path):
        """Immediately adds decompression task in background without opening options dialog."""
        if self.quick_mode:
            self.deiconify()
        self.queue_manager.add_decompress_task(
            archive_path=archive_path,
            extract_dir=extract_dir,
            password=self.archive_password
        )

    def _action_delete(self):
        """Delete selected files from local filesystem."""
        if self.is_viewing_archive:
            messagebox.showwarning("تنبيه", "تعديل محتويات الأرشيف (حذف ملفات من داخله) غير مدعوم في النسخة الحالية.")
            return
            
        selected = self.file_explorer.get_selected_paths()
        if not selected:
            messagebox.showinfo("تنبيه", "يرجى اختيار ملف أو مجلد لحذفه.")
            return
            
        confirm = messagebox.askyesno(
            "تأكيد الحذف", 
            f"هل أنت متأكد من رغبتك في حذف {len(selected)} عنصر بشكل نهائي؟"
        )
        if confirm:
            for p in selected:
                try:
                    if p.is_file():
                        p.unlink()
                    elif p.is_dir():
                        # Simple recursive deletion
                        import shutil
                        shutil.rmtree(p)
                except Exception as e:
                    messagebox.showerror("خطأ أثناء الحذف", f"تعذر حذف العنصر:\n{p.name}\nالسبب: {e}")
            self._action_refresh()

    def _action_benchmark(self):
        """Run CPU and memory compression speed benchmark."""
        # Create a benchmark top level dialog
        bench_win = ctk.CTkToplevel(self)
        bench_win.title("ZRar Speed Benchmark - اختبار الأداء")
        bench_win.geometry("450x260")
        bench_win.resizable(False, False)
        bench_win.transient(self)
        bench_win.grab_set()
        bench_win.configure(fg_color=COLORS["bg_primary"])
        
        # Center window
        bench_win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 450) // 2
        y = self.winfo_y() + (self.winfo_height() - 260) // 2
        bench_win.geometry(f"+{x}+{y}")
        
        main_frame = ctk.CTkFrame(bench_win, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        ctk.CTkLabel(
            main_frame, 
            text="سرعة ضغط المعالج والذاكرة", 
            font=FONTS["title"], 
            text_color=COLORS["accent"]
        ).pack(pady=(0, 10))
        
        # Labels
        progress_lbl = ctk.CTkLabel(main_frame, text="جاري تجهيز اختبار الأداء...", font=FONTS["body"])
        progress_lbl.pack(pady=5)
        
        speed_lbl = ctk.CTkLabel(main_frame, text="السرعة الحالية: -- MB/s", font=FONTS["subtitle"], text_color=COLORS["text_primary"])
        speed_lbl.pack(pady=5)
        
        progress_bar = ctk.CTkProgressBar(main_frame, progress_color=COLORS["accent"], height=10)
        progress_bar.pack(fill="x", pady=10)
        progress_bar.set(0.0)
        
        # Flag to track if cancelled
        is_cancelled = False
        
        def cancel_bench():
            nonlocal is_cancelled
            is_cancelled = True
            bench_win.destroy()
            
        cancel_btn = ctk.CTkButton(
            main_frame, 
            text="إغلاق", 
            fg_color=COLORS["error"], 
            text_color="#FFFFFF",
            command=cancel_bench
        )
        cancel_btn.pack(pady=10)
        
        # Run test in background thread to avoid freezing
        def run_bench():
            import io
            import random
            import zlib
            
            # Generate 20MB of text data
            progress_lbl.configure(text="جاري توليد بيانات اختبار عشوائية (25 ميجابايت)...")
            progress_bar.set(0.1)
            bench_win.update()
            
            if is_cancelled: return
            
            # Generate chunks
            chunk_data = b"ZRar Speed Benchmark Data - " * 10000 # 280KB per chunk
            num_chunks = 90
            total_bytes = len(chunk_data) * num_chunks
            
            progress_lbl.configure(text="جاري تشغيل محاكاة خوارزمية ضغط Deflate...")
            progress_bar.set(0.2)
            bench_win.update()
            
            start_time = time.time()
            compressed_bytes = 0
            
            for i in range(num_chunks):
                if is_cancelled: return
                
                # Compress chunk
                zlib.compress(chunk_data, level=6)
                compressed_bytes += len(chunk_data)
                
                # Update progress
                elapsed = time.time() - start_time
                if elapsed > 0:
                    speed = compressed_bytes / elapsed
                    speed_mb = speed / (1024 * 1024)
                    
                    # Update label safely
                    speed_lbl.configure(text=f"السرعة المتوسطة: {speed_mb:.2f} MB/s")
                    
                pct = 0.2 + (0.8 * ((i + 1) / num_chunks))
                progress_bar.set(pct)
                bench_win.update()
                
            elapsed_total = time.time() - start_time
            final_speed = total_bytes / elapsed_total / (1024 * 1024)
            
            progress_lbl.configure(text="اكتمل الاختبار بنجاح!")
            speed_lbl.configure(text=f"السرعة النهائية للمُعالج: {final_speed:.2f} MB/s", text_color=COLORS["success"])
            progress_bar.set(1.0)
            
        self.after(500, run_bench)

    def _handle_task_notification(self, task: ArchiveTask):
        """Reacts to events pushed by background threads (Task progress/status)."""
        task_id = task.id
        
        # Check if task card exists
        if task_id not in self.task_cards:
            # Create a card
            title = "ضغط الملفات..." if task.task_type == "compress" else "فك ضغط الملفات..."
            parent_container = self.quick_frame if self.quick_mode else self.task_scroll
            card = TaskCard(
                parent_container, 
                task_id=task_id, 
                title=title, 
                on_cancel=self.queue_manager.cancel_task,
                on_pause=self.queue_manager.pause_task,
                on_resume=self.queue_manager.resume_task
            )
            card.pack(fill="both", expand=True, padx=5, pady=5)
            self.task_cards[task_id] = card
            
        # Update details
        card = self.task_cards[task_id]
        card.output_dir = task.archive_path.parent if task.task_type == "compress" else task.base_dir
        card.update_task(task.to_dict())
        
        # Manage active task count label
        active_count = sum(1 for t in self.queue_manager.tasks.values() if t.status in ["pending", "processing"])
        status_indicator = "🟢" if active_count > 0 else "⚪"
        self.tasks_title.configure(text=f"مهام الخلفية {status_indicator} ({active_count})")
        
        # When a task changes state to complete or fail
        if task.status in ["completed", "failed", "cancelled"]:
            # Refresh directory explorer in case task affected current folder
            self._action_refresh()
            
            # Send native OS notification
            from ..core.utils import show_system_notification
            task_type_str = "الضغط" if task.task_type == "compress" else "فك الضغط"
            archive_name = task.archive_path.name
            
            if task.status == "completed":
                show_system_notification(
                    "ZRar - اكتملت العملية", 
                    f"تم الانتهاء من {task_type_str} الملفات إلى '{archive_name}' بنجاح!"
                )
                self.after(4000, lambda t_id=task_id: self._remove_task_card(t_id))
            elif task.status == "failed":
                show_system_notification(
                    "ZRar - فشلت العملية", 
                    f"حدث خطأ أثناء {task_type_str} الأرشيف '{archive_name}': {task.error_message}"
                )
                
            if self.quick_mode:
                self.after(2000, self.destroy)

    def _remove_task_card(self, task_id: str):
        if task_id in self.task_cards:
            card = self.task_cards.pop(task_id)
            card.destroy()
            active_count = sum(1 for t in self.queue_manager.tasks.values() if t.status in ["pending", "processing"])
            status_indicator = "🟢" if active_count > 0 else "⚪"
            self.tasks_title.configure(text=f"مهام الخلفية {status_indicator} ({active_count})")

    def _update_status_info(self):
        """Update items count and size in the status bar."""
        if self.is_viewing_archive:
            # Inside archive
            num_items = len(self.file_explorer.tree.get_children())
            
            # Check for native zrar signature
            try:
                from ..core.archiver import ZrarEngine
                metadata = ZrarEngine.read_zrar_metadata(self.active_archive_path)
            except Exception:
                metadata = None
                
            if metadata:
                self.status_lbl.configure(
                    text=f"📂 أرشيف ZRar أصلي | {metadata.get('comment', 'تم الضغط بـ ZRar')} | {num_items} عنصر"
                )
            else:
                self.status_lbl.configure(
                    text=f"أرشيف: {self.active_archive_path.name} | {num_items} عنصر في هذا المجلد"
                )
        else:
            # Normal directory
            try:
                num_items = len(list(self.current_directory.iterdir()))
                self.status_lbl.configure(text=f"المجلد الحالي: {self.current_directory.name} | {num_items} عنصر")
            except Exception:
                self.status_lbl.configure(text="جاهز")
                
    def _on_search_key_release(self, event):
        """Debounced search entry handler to prevent UI lags on massive directories."""
        if self._search_after_id:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                pass
        self._search_after_id = self.after(150, self._apply_search_filter)

    def _apply_search_filter(self):
        """Filters the display view based on the current search query."""
        query = self.search_entry.get().strip().lower()
        
        if self.is_viewing_archive:
            self._render_archive_view()
        else:
            if not query:
                self.file_explorer.populate(self.local_cached_items)
                self._update_status_info()
            else:
                filtered_items = [item for item in self.local_cached_items if query in item['name'].lower()]
                self.file_explorer.populate(filtered_items)
                self.status_lbl.configure(
                    text=f"🔍 نتائج البحث: تم العثور على {len(filtered_items)} من أصل {len(self.local_cached_items)} عنصر"
                )

    def _build_preview_pane(self):
        """Constructs the interior components of the side preview panel."""
        self.preview_header = ctk.CTkFrame(self.preview_pane, fg_color="transparent")
        self.preview_header.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(
            self.preview_header, 
            text="معاينة الملف", 
            font=FONTS["subtitle"], 
            text_color=COLORS["accent"],
            anchor="w"
        ).pack(side="left")
        
        self.preview_close_btn = ctk.CTkButton(
            self.preview_header,
            text="✕",
            width=22,
            height=22,
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["error"],
            font=FONTS["body_bold"],
            command=self._action_toggle_preview
        )
        self.preview_close_btn.pack(side="right")
        
        # Scrollable container
        self.preview_scroll = ctk.CTkScrollableFrame(self.preview_pane, fg_color="transparent")
        self.preview_scroll.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Image preview
        self.preview_img_lbl = ctk.CTkLabel(self.preview_scroll, text="")
        self.preview_img_lbl.pack(pady=10)
        
        # Text preview
        self.preview_text = ctk.CTkTextbox(
            self.preview_scroll, 
            height=180, 
            font=FONTS["caption"],
            fg_color=COLORS["bg_primary"],
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=RADII["button"]
        )
        self.preview_text.pack(fill="x", pady=10)
        self.preview_text.configure(state="disabled")
        
        # Metadata
        self.meta_title = ctk.CTkLabel(self.preview_scroll, text="معلومات الملف", font=FONTS["body_bold"], text_color=COLORS["text_primary"], anchor="w")
        self.meta_title.pack(fill="x", pady=(10, 5))
        
        self.meta_labels = {}
        fields = [("الاسم", "name"), ("الحجم", "size"), ("النوع", "type"), ("تاريخ التعديل", "modified")]
        for label_text, key in fields:
            frame = ctk.CTkFrame(self.preview_scroll, fg_color="transparent")
            frame.pack(fill="x", pady=2)
            
            ctk.CTkLabel(frame, text=f"{label_text}:", font=("Segoe UI", 10, "bold"), text_color=COLORS["text_secondary"], anchor="w", width=80).pack(side="left")
            val_lbl = ctk.CTkLabel(frame, text="--", font=FONTS["caption"], text_color=COLORS["text_primary"], anchor="w")
            val_lbl.pack(side="left", fill="x", expand=True)
            self.meta_labels[key] = val_lbl
            
        self._clear_preview()

    def _action_toggle_preview(self):
        """Collapses or expands the right-side preview panel."""
        if self.preview_pane.winfo_manager():
            self.preview_pane.pack_forget()
            self.preview_toggle_btn.configure(fg_color=COLORS["bg_secondary"])
        else:
            self.preview_pane.pack(side="right", fill="both", padx=(10, 0))
            self.preview_toggle_btn.configure(fg_color=COLORS["bg_tertiary"])
            self._update_preview()

    def _clear_preview(self):
        """Resets the preview pane components to default empty state."""
        self.preview_img_lbl.configure(image=None, text="يرجى تحديد ملف لمعاينته")
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.configure(state="disabled")
        for lbl in self.meta_labels.values():
            lbl.configure(text="--")

    def _update_preview(self):
        """Queries the first selected item in explorer and renders its contents."""
        if not self.preview_pane.winfo_manager():
            return
            
        meta = self.file_explorer.get_selected_item_metadata()
        if not meta:
            self._clear_preview()
            return
            
        # Update metadata labels
        self.meta_labels["name"].configure(text=meta["name"])
        self.meta_labels["size"].configure(text=format_size(meta["size"]) if not meta["is_dir"] else "--")
        self.meta_labels["type"].configure(text=meta["type_str"])
        self.meta_labels["modified"].configure(text=meta["modified_str"])
        
        path = meta["path"]
        
        # Reset preview fields
        self.preview_img_lbl.configure(image=None, text="")
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.configure(state="disabled")
        
        if meta["is_dir"]:
            self.preview_img_lbl.configure(text="مجلد ملفات")
            return
            
        ext = path.suffix.lower() if isinstance(path, Path) else Path(path).suffix.lower()
        
        if self.is_viewing_archive:
            # File inside archive. Extract asynchronously in a background thread to prevent lag.
            import tempfile
            temp_dir = Path(tempfile.gettempdir()) / "zrar_preview"
            temp_file = temp_dir / Path(path).name
            
            # Start background thread
            import threading
            t = threading.Thread(
                target=self._async_extract_preview, 
                args=(self.active_archive_path, str(Path(path).relative_to(self.active_archive_path).as_posix()), temp_file), 
                daemon=True
            )
            t.start()
        else:
            # Local file on drive
            if path.exists():
                self._render_preview_file(path)

    def _async_extract_preview(self, archive_path: Path, inner_file: str, dest_temp: Path):
        """Target run method for background extraction of single file for preview."""
        try:
            import pyzipper
            import py7zr
            
            dest_temp.parent.mkdir(parents=True, exist_ok=True)
            if dest_temp.exists():
                try:
                    dest_temp.unlink()
                except Exception:
                    pass
                    
            ext = archive_path.suffix.lower()
            if ext == '.zip':
                zf = pyzipper.AESZipFile(archive_path, 'r')
                if self.archive_password:
                    zf.setpassword(self.archive_password.encode('utf-8'))
                with zf:
                    with zf.open(inner_file, 'r') as src, open(dest_temp, 'wb') as dst:
                        dst.write(src.read(15 * 1024)) # Read up to 15KB
            elif ext in ['.7z', '.zrar']:
                with py7zr.SevenZipFile(archive_path, 'r', password=self.archive_password) as sz:
                    sz.extract(targets=[inner_file], path=dest_temp.parent)
                    extracted = dest_temp.parent / inner_file
                    if extracted.exists() and extracted != dest_temp:
                        if dest_temp.exists():
                            dest_temp.unlink()
                        extracted.rename(dest_temp)
                        
            if dest_temp.exists():
                self.after(0, lambda: self._render_preview_file(dest_temp))
        except Exception as e:
            from ..core.logger import get_logger
            get_logger().error(f"Failed to extract preview async for {inner_file}: {e}")

    def _render_preview_file(self, file_path: Path):
        """Renders text or image previews in the GUI. Safely called from main thread."""
        ext = file_path.suffix.lower()
        
        # 1. Text Preview
        text_exts = ['.txt', '.py', '.json', '.xml', '.html', '.css', '.md', '.log', '.ini', '.cfg', '.yaml', '.yml', '.reg']
        if ext in text_exts:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(1024) # Read first 1KB
                self.preview_text.configure(state="normal")
                self.preview_text.insert("1.0", content)
                if len(content) >= 1024:
                    self.preview_text.insert(tk.END, "\n... [تم اقتطاع بقية الملف للسرعة]")
                self.preview_text.configure(state="disabled")
            except Exception:
                self.preview_text.configure(state="normal")
                self.preview_text.insert("1.0", "[تعذر قراءة محتوى الملف النصي]")
                self.preview_text.configure(state="disabled")
                
        # 2. Image Preview
        elif ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.ico']:
            try:
                from PIL import Image
                img = Image.open(file_path)
                w, h = img.size
                ratio = h / w
                
                # Fit inside 220x150
                new_w = 220
                new_h = int(220 * ratio)
                if new_h > 150:
                    new_h = 150
                    new_w = int(150 / ratio)
                    
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(new_w, new_h))
                self.preview_img_lbl.configure(image=ctk_img, text="")
                self.preview_img_lbl.image = ctk_img
            except Exception:
                self.preview_img_lbl.configure(image=None, text="تعذر تحميل مصغر الصورة")
        else:
            self.preview_img_lbl.configure(image=None, text="لا تتوفر معاينة مرئية لهذا النوع")
