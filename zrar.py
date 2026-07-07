import sys
import argparse
from pathlib import Path
from tkinter import messagebox

# Adjust path to import src modules if needed
sys.path.insert(0, str(Path(__file__).parent))

from src.gui.main_window import MainWindow
from src.core.archiver import get_archive_engine
from src.gui.theme import COLORS

def run_gui(initial_path: Path = None):
    app = MainWindow(initial_path=initial_path)
    app.mainloop()

def handle_cli_args():
    parser = argparse.ArgumentParser(description="ZRar - بديل WinRAR الحديث والمجاني")
    parser.add_argument("path", nargs="?", help="المسار لفتحه في متصفح الملفات عند بدء التشغيل")
    parser.add_argument("-c", "--compress", nargs="+", help="ضغط الملفات المحددة مباشرة")
    parser.add_argument("-x", "--extract", help="فك ضغط الأرشيف المحدد مباشرة")
    parser.add_argument("--here", action="store_true", help="فك ضغط الأرشيف في المجلد الحالي مباشرة")
    parser.add_argument("--to-folder", action="store_true", help="فك ضغط الأرشيف في مجلد باسم الملف مباشرة")
    
    args = parser.parse_args()
    
    if args.compress:
        # User requested compression via CLI (e.g. context menu)
        source_paths = [Path(p).resolve() for p in args.compress if Path(p).exists()]
        if not source_paths:
            print("خطأ: لم يتم العثور على الملفات المحددة للضغط.")
            sys.exit(1)
            
        # Open GUI in quick mode and trigger compress dialog
        base_dir = source_paths[0].parent
        app = MainWindow(initial_path=base_dir, quick_mode=True)
        app.after(500, lambda: app._action_compress(target_paths=source_paths))
        app.mainloop()
        
    elif args.extract:
        # User requested extraction via CLI
        archive_path = Path(args.extract).resolve()
        if not archive_path.exists():
            print(f"خطأ: الأرشيف غير موجود: {archive_path}")
            sys.exit(1)
            
        # Open GUI in quick mode and trigger extract
        app = MainWindow(initial_path=archive_path.parent, quick_mode=True)
        
        if args.here:
            extract_dir = archive_path.parent
            app.after(500, lambda: app._action_extract_direct(archive_path, extract_dir))
        elif args.to_folder:
            extract_dir = archive_path.parent / archive_path.stem
            app.after(500, lambda: app._action_extract_direct(archive_path, extract_dir))
        else:
            app.after(500, lambda: app._action_extract(target_archive_path=archive_path))
        app.mainloop()
        
    else:
        # Run GUI normally
        initial_dir = Path(args.path).resolve() if args.path else None
        run_gui(initial_dir)

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    handle_cli_args()
