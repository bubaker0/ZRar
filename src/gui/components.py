import tkinter as tk
from tkinter import ttk
from pathlib import Path
from typing import List, Callable, Optional, Dict
import customtkinter as ctk
from .theme import COLORS, FONTS, RADII
from ..core.utils import format_size, format_time, format_speed

class BreadcrumbBar(ctk.CTkFrame):
    """An interactive navigation bar showing clickable path segments."""
    
    def __init__(self, parent, on_navigate: Callable[[Path], None], **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.on_navigate = on_navigate
        self.current_path = Path()
        
    def set_path(self, path: Path):
        self.current_path = path
        
        # Clear existing breadcrumbs
        for child in self.winfo_children():
            child.destroy()
            
        # For Windows, handle drive letters separately
        parts = []
        if path.anchor:
            parts.append((Path(path.anchor), path.anchor.rstrip('\\/')))
            
        current = Path(path.anchor) if path.anchor else Path()
        for part in path.parts:
            # Skip the anchor as it's already handled
            if path.anchor and part == path.anchor or part in ['\\', '/']:
                continue
            current = current / part
            parts.append((current, part))
            
        # Draw buttons
        for i, (p, label) in enumerate(parts):
            is_active = (i == len(parts) - 1)
            
            # Premium chip styling
            bg = COLORS["accent"] if is_active else COLORS["bg_secondary"]
            txt_col = "#F8FAFC" if is_active else COLORS["text_primary"]
            border_w = 0 if is_active else 1
            hover_bg = COLORS["accent_hover"] if is_active else COLORS["bg_tertiary"]
            
            btn = ctk.CTkButton(
                self, 
                text=label, 
                width=0,
                height=28,
                fg_color=bg,
                text_color=txt_col,
                border_width=border_w,
                border_color=COLORS["border"],
                corner_radius=6,
                hover_color=hover_bg,
                font=FONTS["body_bold"] if is_active else FONTS["body"],
                command=lambda path_to_nav=p: self.on_navigate(path_to_nav)
            )
            btn.pack(side="left", padx=2)
            
            if i < len(parts) - 1:
                sep = ctk.CTkLabel(
                    self, 
                    text="›", 
                    font=FONTS["title"], 
                    text_color=COLORS["text_secondary"]
                )
                sep.pack(side="left", padx=1)


class TaskCard(ctk.CTkFrame):
    """A card showing the progress, speed, and status of an active task."""
    
    def __init__(self, parent, task_id: str, title: str, 
                 on_cancel: Callable[[str], None], 
                 on_pause: Callable[[str], None],
                 on_resume: Callable[[str], None],
                 **kwargs):
        super().__init__(parent, 
                         fg_color=COLORS["bg_secondary"], 
                         border_color=COLORS["border"],
                         border_width=1,
                         corner_radius=RADII["card"], 
                         **kwargs)
        self.task_id = task_id
        self.on_cancel = on_cancel
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.is_paused = False
        self.output_dir: Optional[Path] = None
        
        # Title & Buttons Frame
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.pack(fill="x", padx=12, pady=(10, 5))
        
        self.title_label = ctk.CTkLabel(
            self.header_frame, 
            text=title, 
            font=FONTS["subtitle"],
            text_color=COLORS["text_primary"],
            anchor="w"
        )
        self.title_label.pack(side="left", fill="x", expand=True)
        
        # Buttons Container
        self.action_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.action_frame.pack(side="right")
        
        # Open Folder Button 📁
        self.open_folder_btn = ctk.CTkButton(
            self.action_frame,
            text="📁",
            width=26,
            height=26,
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["accent"],
            font=("Segoe UI", 12),
            command=self._open_output_folder
        )
        # Hidden by default
        
        # Pause/Play Button ⏸ / ▶
        self.pause_btn = ctk.CTkButton(
            self.action_frame, 
            text="⏸", 
            width=26, 
            height=26,
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            font=("Segoe UI", 12),
            command=self._toggle_pause
        )
        self.pause_btn.pack(side="left", padx=1)
        
        # Cancel Button ✕
        self.cancel_btn = ctk.CTkButton(
            self.action_frame, 
            text="✕", 
            width=26, 
            height=26,
            fg_color="transparent",
            hover_color=COLORS["border"],
            text_color=COLORS["error"],
            font=FONTS["body_bold"],
            command=lambda: self.on_cancel(self.task_id)
        )
        self.cancel_btn.pack(side="left", padx=1)
        
        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(
            self, 
            progress_color=COLORS["accent"],
            height=8
        )
        self.progress_bar.pack(fill="x", padx=12, pady=5)
        self.progress_bar.set(0.0)
        
        # Details Layout (Speed, Time, File)
        self.details_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.details_frame.pack(fill="x", padx=12, pady=(5, 10))
        
        self.file_label = ctk.CTkLabel(
            self.details_frame, 
            text="", 
            font=FONTS["caption"],
            text_color=COLORS["text_secondary"],
            anchor="w"
        )
        self.file_label.pack(fill="x")
        
        self.status_frame = ctk.CTkFrame(self.details_frame, fg_color="transparent")
        self.status_frame.pack(fill="x", pady=(2, 0))
        
        self.speed_label = ctk.CTkLabel(
            self.status_frame, 
            text="", 
            font=FONTS["caption"],
            text_color=COLORS["accent"]
        )
        self.speed_label.pack(side="left")
        
        self.time_label = ctk.CTkLabel(
            self.status_frame, 
            text="", 
            font=FONTS["caption"],
            text_color=COLORS["text_secondary"]
        )
        self.time_label.pack(side="right")

    def _toggle_pause(self):
        if self.is_paused:
            self.on_resume(self.task_id)
        else:
            self.on_pause(self.task_id)

    def _open_output_folder(self):
        if self.output_dir and self.output_dir.exists():
            try:
                import os
                os.startfile(self.output_dir)
            except Exception:
                pass

    def update_task(self, task_data: dict):
        """Update progress bar and text labels from task state."""
        status = task_data['status']
        progress = task_data['progress_percent'] / 100.0
        self.progress_bar.set(progress)
        
        # Save output directory
        # For compress, output is parent of archive_path
        # For decompress, output is extract_dir (base_dir)
        # In dict, we can pass it or resolve it in main window. Let's make sure it is resolved.
        # Actually, let's pass a custom field or resolve it from UI side.
        
        # Clean current file path representation
        curr_file = task_data['current_file']
        if len(curr_file) > 40:
            curr_file = "..." + curr_file[-37:]
        self.file_label.configure(text=curr_file)
        
        if status == "processing":
            self.is_paused = False
            self.pause_btn.configure(text="⏸", text_color=COLORS["text_primary"])
            
            speed_str = format_speed(task_data['speed'])
            eta = task_data['remaining_time']
            eta_str = f"متبقي: {format_time(eta)}" if eta >= 0 else "تقدير الوقت..."
            
            self.speed_label.configure(text=speed_str, text_color=COLORS["accent"])
            self.time_label.configure(text=eta_str)
            self.progress_bar.configure(progress_color=COLORS["accent"])
            
        elif status == "paused":
            self.is_paused = True
            self.pause_btn.configure(text="▶", text_color=COLORS["success"])
            self.speed_label.configure(text="موقوف مؤقتاً", text_color=COLORS["warning"])
            self.time_label.configure(text="معلق")
            self.progress_bar.configure(progress_color=COLORS["warning"])
            
        elif status == "completed":
            self.speed_label.configure(text="اكتمل بنجاح!", text_color=COLORS["success"])
            self.time_label.configure(text="")
            self.progress_bar.configure(progress_color=COLORS["success"])
            self.pause_btn.destroy()
            self.cancel_btn.destroy()
            
            # Show folder open button
            self.open_folder_btn.pack(side="right")
            
        elif status == "failed":
            error_msg = task_data['error_message']
            self.file_label.configure(text=f"خطأ: {error_msg}", text_color=COLORS["error"])
            self.speed_label.configure(text="فشل العملية", text_color=COLORS["error"])
            self.time_label.configure(text="")
            self.progress_bar.configure(progress_color=COLORS["error"])
            self.pause_btn.destroy()
            self.cancel_btn.destroy()
            
        elif status == "cancelled":
            self.speed_label.configure(text="تم الإلغاء", text_color=COLORS["warning"])
            self.time_label.configure(text="")
            self.progress_bar.configure(progress_color=COLORS["warning"])
            self.pause_btn.destroy()
            self.cancel_btn.destroy()


class FileListView(ctk.CTkFrame):
    """Custom explorer treeview configured to fit CustomTkinter theme."""
    
    def __init__(self, parent, on_double_click: Callable[[Path], None], **kwargs):
        super().__init__(parent, fg_color=COLORS["bg_secondary"], **kwargs)
        self.on_double_click = on_double_click
        self.current_items: Dict[str, Path] = {} # maps tree item id to Path
        self.current_items_dict: Dict[str, dict] = {}
        
        # Configure treeview style
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Get theme mode (Dark or Light)
        # In custom tkinter, we can get current appearance mode
        self.update_style()
        
        # Treeview + Scrollbars
        self.tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.tree_frame.pack(fill="both", expand=True)
        
        self.tree = ttk.Treeview(
            self.tree_frame, 
            columns=("Size", "Type", "Modified"), 
            show="tree headings", 
            selectmode="extended"
        )
        self.tree.pack(side="left", fill="both", expand=True)
        
        self.scrollbar = ctk.CTkScrollbar(
            self.tree_frame, 
            orientation="vertical", 
            command=self.tree.yview
        )
        self.scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=self.scrollbar.set)
        
        # Define columns
        self.tree.heading("#0", text="الاسم", anchor="w", command=lambda: self._sort_column("#0", False))
        self.tree.heading("Size", text="الحجم", anchor="w", command=lambda: self._sort_column("Size", False))
        self.tree.heading("Type", text="النوع", anchor="w", command=lambda: self._sort_column("Type", False))
        self.tree.heading("Modified", text="تاريخ التعديل", anchor="w", command=lambda: self._sort_column("Modified", False))
        
        self.tree.column("#0", width=300, minwidth=150)
        self.tree.column("Size", width=80, minwidth=50)
        self.tree.column("Type", width=80, minwidth=50)
        self.tree.column("Modified", width=150, minwidth=100)
        
        # Events
        self.tree.bind("<Double-1>", self._double_click_handler)
        
    def update_style(self):
        """Apply theme colors to treeview."""
        mode = ctk.get_appearance_mode().lower()
        bg_col = COLORS["bg_secondary"][1] if mode == "dark" else COLORS["bg_secondary"][0]
        fg_col = COLORS["text_primary"][1] if mode == "dark" else COLORS["text_primary"][0]
        header_bg = COLORS["bg_tertiary"][1] if mode == "dark" else COLORS["bg_tertiary"][0]
        border_col = COLORS["border"][1] if mode == "dark" else COLORS["border"][0]
        accent_col = COLORS["accent"][1] if mode == "dark" else COLORS["accent"][0]
        
        self.style.configure(
            "Treeview",
            background=bg_col,
            fieldbackground=bg_col,
            foreground=fg_col,
            rowheight=32,
            font=FONTS["body"],
            borderwidth=0
        )
        
        self.style.configure(
            "Treeview.Heading",
            background=header_bg,
            foreground=fg_col,
            font=FONTS["body_bold"],
            borderwidth=1,
            bordercolor=border_col
        )
        
        self.style.map(
            "Treeview", 
            background=[('selected', accent_col)],
            foreground=[('selected', '#FFFFFF' if mode == 'dark' else '#000000')]
        )
        try:
            self.tree.configure(style="Treeview")
        except Exception:
            pass

    def populate(self, items: List[dict]):
        """
        Populate the treeview with item dictionaries containing:
        {'name': str, 'path': Path, 'size': int, 'is_dir': bool, 'type_str': str, 'modified_str': str}
        """
        # Clear items
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.current_items.clear()
        self.current_items_dict.clear()
        
        # Sort items: folders first, then files
        sorted_items = sorted(items, key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        for item in sorted_items:
            # Icon decoration based on extension (Rich Visuals)
            if item['is_dir']:
                icon = "📁"
                size_str = ""
            else:
                ext = item['path'].suffix.lower() if isinstance(item['path'], Path) else ""
                if ext in ['.zrar', '.zip', '.7z', '.rar', '.tar', '.gz', '.bz2', '.xz']:
                    icon = "📦" # Archive
                elif ext in ['.py', '.js', '.html', '.css', '.cpp', '.java', '.cs', '.go', '.ts', '.rs']:
                    icon = "💻" # Developer Code files
                elif ext in ['.txt', '.log', '.md', '.ini', '.cfg', '.json', '.xml', '.yaml', '.yml']:
                    icon = "📄" # Documents / Data
                elif ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.bmp']:
                    icon = "🖼️" # Images
                elif ext in ['.mp4', '.mkv', '.avi', '.mov', '.mp3', '.wav', '.flac', '.ogg']:
                    icon = "🎵" # Multimedia
                elif ext in ['.exe', '.msi', '.bat', '.sh', '.cmd', '.lnk']:
                    icon = "⚙️" # Executables / System scripts
                elif ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
                    icon = "📕" # PDF / Office documents
                else:
                    icon = "📄" # Default
                size_str = format_size(item['size'])
                
            display_name = f"  {icon}  {item['name']}"
            
            node_id = self.tree.insert(
                "", 
                "end", 
                text=display_name,
                values=(size_str, item['type_str'], item['modified_str'])
            )
            self.current_items[node_id] = item['path']
            self.current_items_dict[node_id] = item

    def get_selected_paths(self) -> List[Path]:
        """Returns the list of Paths selected in the list."""
        selected_ids = self.tree.selection()
        return [self.current_items[node_id] for node_id in selected_ids if node_id in self.current_items]

    def get_selected_item_metadata(self) -> Optional[dict]:
        """Returns the dictionary metadata of the first selected item."""
        selected_ids = self.tree.selection()
        if selected_ids and selected_ids[0] in self.current_items_dict:
            return self.current_items_dict[selected_ids[0]]
        return None

    def _double_click_handler(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id in self.current_items:
            self.on_double_click(self.current_items[item_id])

    def _sort_column(self, col: str, reverse: bool):
        """Sort Treeview columns dynamically on click."""
        # Get elements (value, item_id)
        items_list = []
        for k in self.tree.get_children(""):
            if col == "#0":
                val = self.tree.item(k, "text")
            else:
                val = self.tree.set(k, col)
            items_list.append((val, k))
            
        # Size sorting helper
        def parse_size_to_bytes(size_str: str) -> float:
            size_str = size_str.strip()
            if not size_str or size_str == "0 B":
                return -1.0
            try:
                num_part = "".join(c for c in size_str if c.isdigit() or c == '.')
                unit = "".join(c for c in size_str if c.isalpha())
                val = float(num_part)
                multiplier = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4, 'PB': 1024**5}
                return val * multiplier.get(unit.upper(), 1)
            except Exception:
                return 0.0

        if col == "Size":
            items_list.sort(key=lambda t: parse_size_to_bytes(t[0]), reverse=reverse)
        elif col == "#0":
            # Extract filename without icons for correct alphabetical sorting
            def extract_name(text: str) -> str:
                clean = text.strip()
                parts = clean.split(None, 1)
                if len(parts) > 1:
                    return parts[1].lower()
                return clean.lower()
            items_list.sort(key=lambda t: extract_name(t[0]), reverse=reverse)
        else:
            items_list.sort(key=lambda t: t[0].lower(), reverse=reverse)
            
        # Rearrange items
        for index, (val, k) in enumerate(items_list):
            self.tree.move(k, "", index)
            
        # Configure next sort direction
        self.tree.heading(col, command=lambda: self._sort_column(col, not reverse))
