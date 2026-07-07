import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import customtkinter as ctk
from .theme import COLORS, FONTS, RADII

class BaseDialog(ctk.CTkToplevel):
    """Base custom modal dialog class."""
    def __init__(self, parent, title: str, width: int = 400, height: int = 300):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        
        # Set icon
        from ..core.utils import get_resource_path
        icon_path = get_resource_path("ZRar.ico")
        if Path(icon_path).exists():
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass
                
        # Center dialog
        self.update_idletasks()
        if parent.winfo_viewable():
            x = parent.winfo_x() + (parent.winfo_width() - width) // 2
            y = parent.winfo_y() + (parent.winfo_height() - height) // 2
        else:
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            x = (screen_width - width) // 2
            y = (screen_height - height) // 2
        self.geometry(f"+{x}+{y}")
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        self.focus_set()
        
        # Escape key exits
        self.bind("<Escape>", lambda e: self.on_cancel())
        
        # Result placeholder
        self.result = None
        
    def on_cancel(self):
        self.result = None
        self.destroy()


class CompressDialog(BaseDialog):
    """Dialog for setting compression parameters."""
    
    def __init__(self, parent, default_name: str, suggested_dir: Path, default_format: str = "zip", default_level: int = 5):
        super().__init__(parent, "خيارات ضغط الأرشيف", width=460, height=420)
        self.suggested_dir = suggested_dir
        self.configure(fg_color=COLORS["bg_primary"])
        
        # Container frame
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 1. Archive Name Input
        ctk.CTkLabel(main_frame, text="اسم الأرشيف:", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).grid(row=0, column=0, sticky="w", pady=5)
        self.name_entry = ctk.CTkEntry(main_frame, width=220, placeholder_text="اسم الملف")
        self.name_entry.insert(0, default_name)
        self.name_entry.grid(row=0, column=1, sticky="w", pady=5, padx=10)
        
        # 2. Format choice
        ctk.CTkLabel(main_frame, text="صيغة الأرشيف:", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).grid(row=1, column=0, sticky="w", pady=5)
        self.format_var = ctk.StringVar(value=default_format)
        self.format_combo = ctk.CTkComboBox(
            main_frame, 
            values=["zrar", "zip", "7z", "tar", "tar.gz"], 
            variable=self.format_var, 
            width=220,
            command=self._on_format_change
        )
        self.format_combo.grid(row=1, column=1, sticky="w", pady=5, padx=10)
        
        # 3. Compression level slider
        ctk.CTkLabel(main_frame, text="مستوى الضغط:", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).grid(row=2, column=0, sticky="w", pady=5)
        self.level_slider = ctk.CTkSlider(main_frame, from_=1, to=9, number_of_steps=8, width=220)
        self.level_slider.set(default_level)
        self.level_slider.grid(row=2, column=1, sticky="w", pady=5, padx=10)
        self.level_label = ctk.CTkLabel(main_frame, text="عادي (5)", font=FONTS["caption"], text_color=COLORS["text_secondary"])
        self.level_label.grid(row=2, column=1, sticky="e")
        self._update_slider_label(default_level)
        self.level_slider.configure(command=self._update_slider_label)
        
        # 4. Password Protection
        ctk.CTkLabel(main_frame, text="كلمة المرور (اختياري):", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).grid(row=3, column=0, sticky="w", pady=5)
        self.pass_entry = ctk.CTkEntry(main_frame, placeholder_text="تشفير الملفات بكلمة مرور", show="*", width=220)
        self.pass_entry.grid(row=3, column=1, sticky="w", pady=5, padx=10)
        
        # Show password toggle
        self.show_pass_var = tk.BooleanVar(value=False)
        self.show_pass_cb = ctk.CTkCheckBox(
            main_frame, 
            text="إظهار كلمة المرور", 
            variable=self.show_pass_var, 
            font=FONTS["caption"],
            command=self._toggle_password_visibility
        )
        self.show_pass_cb.grid(row=4, column=1, sticky="w", pady=2, padx=10)
        
        # 5. Volume Splitting
        ctk.CTkLabel(main_frame, text="تقسيم الأرشيف (7z فقط):", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).grid(row=5, column=0, sticky="w", pady=5)
        self.split_var = ctk.StringVar(value="بدون تقسيم")
        self.split_combo = ctk.CTkComboBox(
            main_frame, 
            values=["بدون تقسيم", "100 MB", "700 MB", "4 GB"], 
            variable=self.split_var, 
            width=220
        )
        self.split_combo.grid(row=5, column=1, sticky="w", pady=5, padx=10)
        if default_format != "7z":
            self.split_combo.configure(state="disabled")
            
        # Actions button
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(25, 0))
        
        self.cancel_btn = ctk.CTkButton(
            btn_frame, 
            text="إلغاء", 
            fg_color="transparent", 
            border_color=COLORS["border"], 
            border_width=1,
            text_color=COLORS["text_primary"],
            hover_color=COLORS["border"],
            width=100,
            command=self.on_cancel
        )
        self.cancel_btn.pack(side="left", padx=5)
        
        self.ok_btn = ctk.CTkButton(
            btn_frame, 
            text="بدء الضغط", 
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#FFFFFF",
            width=120,
            command=self.on_ok
        )
        self.ok_btn.pack(side="right", padx=5)
        
        # Focus on entry
        self.name_entry.focus()
        self.name_entry.select_range(0, tk.END)
        
    def _update_slider_label(self, value):
        val = int(value)
        labels = {
            1: "تخزين (1)", 2: "أسرع ما يمكن (2)", 3: "سريع (3)", 
            4: "خفيف (4)", 5: "عادي (5)", 6: "جيد (6)", 
            7: "مكثف (7)", 8: "أقصى ضغط (8)", 9: "خارق (9)"
        }
        self.level_label.configure(text=labels.get(val, f"{val}"))
        
    def _on_format_change(self, value):
        # Tar format doesn't support passwords
        if value in ["tar", "tar.gz"]:
            self.pass_entry.configure(state="disabled")
            self.pass_entry.delete(0, tk.END)
            self.pass_entry.configure(placeholder_text="غير مدعوم بصيغة Tar")
            self.show_pass_cb.configure(state="disabled")
        else:
            self.pass_entry.configure(state="normal")
            self.pass_entry.configure(placeholder_text="تشفير الملفات بكلمة مرور")
            self.show_pass_cb.configure(state="normal")
            
        # Split is only supported for 7z format
        if value == "7z":
            self.split_combo.configure(state="normal")
        else:
            self.split_combo.configure(state="disabled")
            self.split_var.set("بدون تقسيم")
            
    def _toggle_password_visibility(self):
        show_char = "" if self.show_pass_var.get() else "*"
        self.pass_entry.configure(show=show_char)

    def _parse_volume_size(self, val_str: str) -> int:
        """Parse volume size string (e.g., '100 MB', '4 GB') to bytes."""
        if not val_str or val_str == "بدون تقسيم":
            return 0
        
        val_str = val_str.lower().replace(" ", "").replace("b", "")
        try:
            if "g" in val_str:
                num = float(val_str.split("g")[0])
                return int(num * 1024 * 1024 * 1024)
            elif "m" in val_str:
                num = float(val_str.split("m")[0])
                return int(num * 1024 * 1024)
            elif "k" in val_str:
                num = float(val_str.split("k")[0])
                return int(num * 1024)
            else:
                return int(float(val_str) * 1024 * 1024)
        except Exception:
            return 0

    def on_ok(self):
        name = self.name_entry.get().strip()
        fmt = self.format_var.get()
        
        # Ensure file has correct extension
        ext = f".{fmt}" if fmt != "tar.gz" else ".tar.gz"
        if not name.endswith(ext):
            name += ext
            
        archive_path = self.suggested_dir / name
        password = self.pass_entry.get() if self.pass_entry.get().strip() else None
        
        # Parse volume size if 7z
        volume_size = self._parse_volume_size(self.split_var.get()) if fmt == "7z" else 0
        
        self.result = {
            'archive_path': archive_path,
            'format': fmt,
            'compression_level': int(self.level_slider.get()),
            'password': password,
            'volume_size': volume_size
        }
        self.destroy()


class ExtractDialog(BaseDialog):
    """Dialog for choosing extraction path and settings."""
    
    def __init__(self, parent, default_dir: Path, requires_password: bool = False):
        super().__init__(parent, "خيارات فك الضغط", width=460, height=260)
        self.default_dir = default_dir
        self.configure(fg_color=COLORS["bg_primary"])
        
        # Container frame
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 1. Output directory selection
        ctk.CTkLabel(main_frame, text="مجلد الاستخراج:", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).grid(row=0, column=0, sticky="w", pady=5)
        
        dir_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        dir_frame.grid(row=0, column=1, sticky="w", pady=5, padx=10)
        
        self.dir_entry = ctk.CTkEntry(dir_frame, width=170)
        self.dir_entry.insert(0, str(default_dir))
        self.dir_entry.pack(side="left")
        
        self.browse_btn = ctk.CTkButton(
            dir_frame, 
            text="...", 
            width=30, 
            height=26,
            fg_color="transparent",
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["text_primary"],
            hover_color=COLORS["border"],
            command=self._browse_directory
        )
        self.browse_btn.pack(side="left", padx=(5, 0))
        
        # 2. Password input if archive is encrypted
        self.pass_entry = None
        if requires_password:
            ctk.CTkLabel(main_frame, text="كلمة المرور المطلوبة:", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).grid(row=1, column=0, sticky="w", pady=5)
            self.pass_entry = ctk.CTkEntry(main_frame, placeholder_text="أدخل كلمة مرور فك الضغط", show="*", width=220)
            self.pass_entry.grid(row=1, column=1, sticky="w", pady=5, padx=10)
            
            # Focus on password entry instead
            self.pass_entry.focus()
            
        # Actions button
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(35, 0))
        
        self.cancel_btn = ctk.CTkButton(
            btn_frame, 
            text="إلغاء", 
            fg_color="transparent", 
            border_color=COLORS["border"], 
            border_width=1,
            text_color=COLORS["text_primary"],
            hover_color=COLORS["border"],
            width=100,
            command=self.on_cancel
        )
        self.cancel_btn.pack(side="left", padx=5)
        
        self.ok_btn = ctk.CTkButton(
            btn_frame, 
            text="بدء فك الضغط", 
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#FFFFFF",
            width=120,
            command=self.on_ok
        )
        self.ok_btn.pack(side="right", padx=5)
        
    def _browse_directory(self):
        chosen = filedialog.askdirectory(initialdir=self.dir_entry.get(), title="اختر مجلد فك الضغط")
        if chosen:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, chosen)
            
    def on_ok(self):
        dest = Path(self.dir_entry.get().strip())
        password = self.pass_entry.get() if self.pass_entry else None
        
        self.result = {
            'extract_dir': dest,
            'password': password
        }
        self.destroy()


class PasswordPromptDialog(BaseDialog):
    """Simple dialog to ask password for password-protected archives."""
    
    def __init__(self, parent, archive_name: str):
        super().__init__(parent, "الملف محمي بكلمة مرور", width=400, height=180)
        self.configure(fg_color=COLORS["bg_primary"])
        
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        label_text = f"الرجاء إدخال كلمة المرور لفك ضغط:\n{archive_name}"
        ctk.CTkLabel(
            main_frame, 
            text=label_text, 
            font=FONTS["body_bold"], 
            text_color=COLORS["text_primary"],
            justify="center"
        ).pack(fill="x", pady=(0, 10))
        
        self.pass_entry = ctk.CTkEntry(main_frame, placeholder_text="كلمة المرور", show="*", width=250)
        self.pass_entry.pack(pady=5)
        self.pass_entry.focus()
        
        # Bind Return/Enter key to confirm
        self.pass_entry.bind("<Return>", lambda e: self.on_ok())
        
        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(15, 0))
        
        self.cancel_btn = ctk.CTkButton(
            btn_frame, 
            text="إلغاء", 
            fg_color="transparent", 
            border_color=COLORS["border"], 
            border_width=1,
            text_color=COLORS["text_primary"],
            hover_color=COLORS["border"],
            width=80,
            command=self.on_cancel
        )
        self.cancel_btn.pack(side="left", padx=5)
        
        self.ok_btn = ctk.CTkButton(
            btn_frame, 
            text="موافق", 
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#FFFFFF",
            width=80,
            command=self.on_ok
        )
        self.ok_btn.pack(side="right", padx=5)

    def on_ok(self):
        password = self.pass_entry.get()
        if password.strip():
            self.result = password
            self.destroy()
        else:
            # Shake or warning
            self.pass_entry.configure(border_color=COLORS["error"])
            
    def on_cancel(self):
        self.result = None
        self.destroy()


class SettingsDialog(BaseDialog):
    """Dialog for system and archiving configurations."""
    
    def __init__(self, parent, current_settings: dict):
        super().__init__(parent, "إعدادات ZRar", width=460, height=450)
        self.configure(fg_color=COLORS["bg_primary"])
        self.current_settings = current_settings.copy()
        
        # Tabs
        self.tabview = ctk.CTkTabview(
            self, 
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_selected_hover_color=COLORS["accent_hover"],
            segmented_button_unselected_hover_color=COLORS["bg_tertiary"],
            corner_radius=RADII["card"]
        )
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(10, 60))
        
        tab_general = self.tabview.add("عام")
        tab_archive = self.tabview.add("الأرشفة")
        
        # --- GENERAL TAB ---
        # 1. Theme Setting
        ctk.CTkLabel(tab_general, text="المظهر (Theme):", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).grid(row=0, column=0, sticky="w", pady=10, padx=10)
        self.theme_var = ctk.StringVar(value=self.current_settings.get("theme", "System"))
        self.theme_combo = ctk.CTkComboBox(
            tab_general, 
            values=["System", "Dark", "Light"], 
            variable=self.theme_var, 
            width=180,
            command=self._on_theme_change
        )
        self.theme_combo.grid(row=0, column=1, sticky="w", pady=10, padx=10)
        
        # 2. Default extraction folder
        ctk.CTkLabel(tab_general, text="مجلد فك الضغط الافتراضي:", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).grid(row=1, column=0, sticky="nw", pady=10, padx=10)
        
        self.dest_mode_var = ctk.StringVar(value=self.current_settings.get("dest_mode", "same"))
        self.radio_same = ctk.CTkRadioButton(
            tab_general, 
            text="نفس مجلد الأرشيف", 
            variable=self.dest_mode_var, 
            value="same",
            command=self._toggle_custom_dir_state
        )
        self.radio_same.grid(row=1, column=1, sticky="w", pady=(10, 2), padx=10)
        
        self.radio_custom = ctk.CTkRadioButton(
            tab_general, 
            text="مجلد مخصص:", 
            variable=self.dest_mode_var, 
            value="custom",
            command=self._toggle_custom_dir_state
        )
        self.radio_custom.grid(row=2, column=1, sticky="w", pady=2, padx=10)
        
        custom_dir_frame = ctk.CTkFrame(tab_general, fg_color="transparent")
        custom_dir_frame.grid(row=3, column=1, sticky="ew", pady=(2, 10), padx=10)
        
        self.custom_dir_entry = ctk.CTkEntry(custom_dir_frame, width=130)
        self.custom_dir_entry.insert(0, self.current_settings.get("custom_extract_dir", ""))
        self.custom_dir_entry.pack(side="left")
        
        self.browse_btn = ctk.CTkButton(
            custom_dir_frame, 
            text="...", 
            width=30, 
            height=26,
            fg_color="transparent",
            border_color=COLORS["border"],
            border_width=1,
            text_color=COLORS["text_primary"],
            hover_color=COLORS["border"],
            command=self._browse_custom_dir
        )
        self.browse_btn.pack(side="left", padx=(5, 0))
        
        self._toggle_custom_dir_state()
        
        # 3. Windows Startup Checkbox
        from ..core.registry_helper import get_startup_state
        self.startup_var = ctk.BooleanVar(value=get_startup_state())
        self.startup_chk = ctk.CTkCheckBox(
            tab_general,
            text="التشغيل تلقائياً عند بدء تشغيل نظام ويندوز",
            variable=self.startup_var,
            font=FONTS["body"],
            text_color=COLORS["text_primary"]
        )
        self.startup_chk.grid(row=4, column=0, columnspan=2, sticky="w", pady=15, padx=10)
        
        # 4. Windows 11 Classic Context Menu Checkbox
        from ..core.registry_helper import get_classic_context_menu_state
        self.classic_menu_var = ctk.BooleanVar(value=get_classic_context_menu_state())
        self.classic_menu_chk = ctk.CTkCheckBox(
            tab_general,
            text="تمكين قائمة الزر الأيمن الكلاسيكية (لويندوز 11)",
            variable=self.classic_menu_var,
            font=FONTS["body"],
            text_color=COLORS["text_primary"]
        )
        self.classic_menu_chk.grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 10), padx=10)
        
        # --- ARCHIVE TAB ---
        # 1. Default Format
        ctk.CTkLabel(tab_archive, text="صيغة الأرشيف الافتراضية:", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).grid(row=0, column=0, sticky="w", pady=10, padx=10)
        self.fmt_var = ctk.StringVar(value=self.current_settings.get("default_format", "zip"))
        self.fmt_combo = ctk.CTkComboBox(tab_archive, values=["zip", "7z", "tar"], variable=self.fmt_var, width=180)
        self.fmt_combo.grid(row=0, column=1, sticky="w", pady=10, padx=10)
        
        # 2. Default Compression Level
        ctk.CTkLabel(tab_archive, text="مستوى الضغط الافتراضي:", font=FONTS["body_bold"], text_color=COLORS["text_primary"]).grid(row=1, column=0, sticky="w", pady=10, padx=10)
        self.comp_slider = ctk.CTkSlider(tab_archive, from_=1, to=9, number_of_steps=8, width=180)
        self.comp_slider.set(self.current_settings.get("default_level", 5))
        self.comp_slider.grid(row=1, column=1, sticky="w", pady=10, padx=10)
        
        
        # --- BOTTOM ACTION BUTTONS ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent", height=40)
        btn_frame.pack(side="bottom", fill="x", padx=20, pady=10)
        
        self.cancel_btn = ctk.CTkButton(
            btn_frame, 
            text="إلغاء", 
            fg_color="transparent", 
            border_color=COLORS["border"], 
            border_width=1,
            text_color=COLORS["text_primary"],
            hover_color=COLORS["border"],
            width=100,
            command=self.on_cancel
        )
        self.cancel_btn.pack(side="left", padx=5)
        
        self.ok_btn = ctk.CTkButton(
            btn_frame, 
            text="حفظ الإعدادات", 
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#FFFFFF",
            width=120,
            command=self.on_ok
        )
        self.ok_btn.pack(side="right", padx=5)
        
    def _on_theme_change(self, value):
        self.current_settings["theme"] = value
        
    def _toggle_custom_dir_state(self):
        mode = self.dest_mode_var.get()
        if mode == "same":
            self.custom_dir_entry.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
        else:
            self.custom_dir_entry.configure(state="normal")
            self.browse_btn.configure(state="normal")
            
    def _browse_custom_dir(self):
        chosen = filedialog.askdirectory(title="اختر مجلد الحفظ الافتراضي")
        if chosen:
            self.custom_dir_entry.configure(state="normal")
            self.custom_dir_entry.delete(0, tk.END)
            self.custom_dir_entry.insert(0, chosen)
            
    def on_ok(self):
        # Save Windows startup state
        from ..core.registry_helper import set_startup_state
        set_startup_state(self.startup_var.get())
        
        # Save Windows 11 Classic Context Menu state
        from ..core.registry_helper import set_classic_context_menu
        set_classic_context_menu(self.classic_menu_var.get())
        
        self.result = {
            'theme': self.theme_var.get(),
            'dest_mode': self.dest_mode_var.get(),
            'custom_extract_dir': self.custom_dir_entry.get().strip(),
            'default_format': self.fmt_var.get(),
            'default_level': int(self.comp_slider.get())
        }
        self.destroy()
