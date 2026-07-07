"""
Theme configurations for ZRar.
Defines colors, fonts, and style options for CustomTkinter widgets to ensure a premium UI.
"""

# Color Palette (Light Mode, Dark Mode)
COLORS = {
    "bg_primary": ("#F3F4F6", "#0F172A"),       # Light gray / Dark Slate Navy
    "bg_secondary": ("#FFFFFF", "#1E293B"),     # Pure White / Lighter Navy Card
    "bg_tertiary": ("#E5E7EB", "#0F172A"),      # Medium gray / Deep Navy
    
    "accent": ("#0284C7", "#38BDF8"),            # Sky Blue / Vibrant Neon Cyan
    "accent_hover": ("#0369A1", "#0EA5E9"),      # Darker Blue / Medium Cyan
    
    "text_primary": ("#1E293B", "#F8FAFC"),      # Slate Navy / Ice White
    "text_secondary": ("#64748B", "#94A3B8"),    # Muted Gray-Blue
    
    "border": ("#E2E8F0", "#334155"),            # Slate Border
    "border_focus": ("#38BDF8", "#38BDF8"),      # Light border on focus
    
    "success": ("#10B981", "#34D399"),           # Emerald Green
    "error": ("#EF4444", "#F87171"),             # Rose Red
    "warning": ("#F59E0B", "#FBBF24"),           # Warm Amber
}

# Typography
FONTS = {
    "title": ("Outfit", 18, "bold"),
    "subtitle": ("Outfit", 14, "bold"),
    "body_bold": ("Segoe UI", 12, "bold"),
    "body": ("Segoe UI", 12),
    "caption": ("Segoe UI", 10),
    "code": ("Consolas", 10),
}

# Corner Radii
RADII = {
    "card": 12,
    "button": 8,
    "input": 6,
}
