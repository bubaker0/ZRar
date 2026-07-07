import sys
import winreg
from pathlib import Path

def set_startup_state(enabled: bool) -> bool:
    """Enable or disable ZRar launching at Windows startup."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    # Determine the correct execution command
    if getattr(sys, 'frozen', False):
        app_path = sys.executable
    else:
        script_path = Path(__file__).parent.parent.parent / "zrar.py"
        app_path = f'"{sys.executable}" "{script_path.resolve()}"'
        
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, "ZRar", 0, winreg.REG_SZ, app_path)
        else:
            try:
                winreg.DeleteValue(key, "ZRar")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False

def get_startup_state() -> bool:
    """Check if ZRar is currently set to start automatically with Windows."""
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, "ZRar")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False

def generate_reg_file(output_path: Path) -> Path:
    """
    Generate a Windows Registry (.reg) file to integrate ZRar as a cascading context menu
    and associate .zrar files to open automatically in ZRar with the custom icon.
    """
    script_path = Path(__file__).parent.parent.parent / "zrar.py"
    script_path = script_path.resolve()
    
    icon_path = Path(__file__).parent.parent.parent / "ZRar.ico"
    icon_path = icon_path.resolve()
    
    # Python executable path (use pythonw.exe to prevent CMD window popups)
    python_exe = sys.executable
    if python_exe.lower().endswith("python.exe"):
        python_exe = python_exe[:-10] + "pythonw.exe"
    
    # We must escape backslashes in .reg files
    esc_python = str(python_exe).replace('\\', '\\\\')
    esc_script = str(script_path).replace('\\', '\\\\')
    esc_icon = str(icon_path).replace('\\', '\\\\')
    
    reg_content = f"""Windows Registry Editor Version 5.00

; --- CASCADING CONTEXT MENU FOR FILES ---

[HKEY_CLASSES_ROOT\\*\\shell\\ZRar]
"MUIVerb"="ZRar"
"SubCommands"=""
"Icon"="{esc_icon}"

[HKEY_CLASSES_ROOT\\*\\shell\\ZRar\\shell]

[HKEY_CLASSES_ROOT\\*\\shell\\ZRar\\shell\\Compress]
"MUIVerb"="الضغط بـ ZRar..."
"Icon"="{esc_icon}"

[HKEY_CLASSES_ROOT\\*\\shell\\ZRar\\shell\\Compress\\command]
@="\\"{esc_python}\\" \\"{esc_script}\\" -c \\"%1\\""

[HKEY_CLASSES_ROOT\\*\\shell\\ZRar\\shell\\Extract]
"MUIVerb"="فك الضغط بـ ZRar..."
"Icon"="{esc_icon}"

[HKEY_CLASSES_ROOT\\*\\shell\\ZRar\\shell\\Extract\\command]
@="\\"{esc_python}\\" \\"{esc_script}\\" -x \\"%1\\""

[HKEY_CLASSES_ROOT\\*\\shell\\ZRar\\shell\\ExtractHere]
"MUIVerb"="فك الضغط هنا"
"Icon"="{esc_icon}"

[HKEY_CLASSES_ROOT\\*\\shell\\ZRar\\shell\\ExtractHere\\command]
@="\\"{esc_python}\\" \\"{esc_script}\\" -x \\"%1\\" --here"

[HKEY_CLASSES_ROOT\\*\\shell\\ZRar\\shell\\ExtractToDir]
"MUIVerb"="فك الضغط إلى مجلد باسم الملف"
"Icon"="{esc_icon}"

[HKEY_CLASSES_ROOT\\*\\shell\\ZRar\\shell\\ExtractToDir\\command]
@="\\"{esc_python}\\" \\"{esc_script}\\" -x \\"%1\\" --to-folder"


; --- CASCADING CONTEXT MENU FOR DIRECTORIES ---

[HKEY_CLASSES_ROOT\\Directory\\shell\\ZRar]
"MUIVerb"="ZRar"
"SubCommands"=""
"Icon"="{esc_icon}"

[HKEY_CLASSES_ROOT\\Directory\\shell\\ZRar\\shell]

[HKEY_CLASSES_ROOT\\Directory\\shell\\ZRar\\shell\\Compress]
"MUIVerb"="الضغط بـ ZRar..."
"Icon"="{esc_icon}"

[HKEY_CLASSES_ROOT\\Directory\\shell\\ZRar\\shell\\Compress\\command]
@="\\"{esc_python}\\" \\"{esc_script}\\" -c \\"%1\\""


; --- FILE ASSOCIATION FOR .ZRAR FILES ---

[HKEY_CLASSES_ROOT\\.zrar]
@="ZRar.Archive"

[HKEY_CLASSES_ROOT\\ZRar.Archive]
@="أرشيف ZRar"
"FriendlyTypeName"="أرشيف ZRar"

[HKEY_CLASSES_ROOT\\ZRar.Archive\\DefaultIcon]
@="{esc_icon}"

[HKEY_CLASSES_ROOT\\ZRar.Archive\\shell]

[HKEY_CLASSES_ROOT\\ZRar.Archive\\shell\\open]
"MUIVerb"="فتح الأرشيف بـ ZRar"

[HKEY_CLASSES_ROOT\\ZRar.Archive\\shell\\open\\command]
@="\\"{esc_python}\\" \\"{esc_script}\\" \\"%1\\""
"""
    
    with open(output_path, "w", encoding="utf-16") as f:
        f.write(reg_content)
        
    return output_path

def set_classic_context_menu(enabled: bool) -> bool:
    """Restore classic Windows 10 context menu as default in Windows 11."""
    key_path = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32"
    try:
        if enabled:
            # Create key and set default value to empty string to override Windows 11 modern menu
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "")
            winreg.CloseKey(key)
        else:
            # Delete keys recursively to restore default Win11 menu behavior
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
            except FileNotFoundError:
                pass
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}")
            except FileNotFoundError:
                pass
        
        # Restart explorer.exe asynchronously to apply changes immediately without logging off
        import os
        os.system("taskkill /f /im explorer.exe & start explorer.exe")
        return True
    except Exception:
        return False

def get_classic_context_menu_state() -> bool:
    """Check if classic context menu bypass is currently enabled."""
    key_path = r"Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False

if __name__ == "__main__":
    out = Path(__file__).parent.parent.parent / "integrate_zrar.reg"
    generate_reg_file(out)
    print(f"تم إنشاء ملف تسجيل ويندوز بنجاح في:\n{out}")
