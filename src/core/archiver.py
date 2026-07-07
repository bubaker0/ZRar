import os
import time
import subprocess
import tempfile
from pathlib import Path
from typing import List, Callable, Optional, Union
import pyzipper
import py7zr
import tarfile
from .logger import get_logger
from .utils import get_resource_path

logger = get_logger()

class ArchiveProgress:
    """Class to hold progress information for callback functions."""
    def __init__(self, current_file: str, bytes_processed: int, total_bytes: int, elapsed_time: float):
        self.current_file = current_file
        self.bytes_processed = bytes_processed
        self.total_bytes = total_bytes
        self.elapsed_time = elapsed_time
        
    @property
    def speed(self) -> float:
        """Speed in bytes per second."""
        if self.elapsed_time <= 0:
            return 0.0
        return self.bytes_processed / self.elapsed_time

    @property
    def percent(self) -> float:
        """Percentage of completion (0 to 100)."""
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, (self.bytes_processed / self.total_bytes) * 100.0)

    @property
    def remaining_time(self) -> float:
        """Estimated remaining time in seconds."""
        if self.speed <= 0:
            return -1.0
        remaining_bytes = self.total_bytes - self.bytes_processed
        return max(0.0, remaining_bytes / self.speed)


# Progress callback type
ProgressCallback = Callable[[ArchiveProgress], None]


class BaseArchiveEngine:
    """Abstract Base Class for all compression/decompression engines."""
    
    def compress(self, 
                 files_to_compress: List[Path], 
                 archive_path: Path, 
                 base_dir: Path,
                 password: Optional[str] = None, 
                 compression_level: int = 5,  # Scale from 1 (Store) to 9 (Ultra)
                 progress_cb: Optional[ProgressCallback] = None,
                 cancel_check: Optional[Callable[[], bool]] = None,
                 volume_size: int = 0) -> bool:
        raise NotImplementedError
        
    def decompress(self, 
                   archive_path: Path, 
                   extract_dir: Path, 
                   password: Optional[str] = None,
                   progress_cb: Optional[ProgressCallback] = None,
                   cancel_check: Optional[Callable[[], bool]] = None) -> bool:
        raise NotImplementedError
        
    def list_files(self, archive_path: Path, password: Optional[str] = None) -> List[dict]:
        """List metadata of files in the archive."""
        raise NotImplementedError


class ZipEngine(BaseArchiveEngine):
    """ZIP engine using pyzipper for modern AES-256 and legacy ZipCrypto support."""
    
    def compress(self, 
                 files_to_compress: List[Path], 
                 archive_path: Path, 
                 base_dir: Path,
                 password: Optional[str] = None, 
                 compression_level: int = 5,
                 progress_cb: Optional[ProgressCallback] = None,
                 cancel_check: Optional[Callable[[], bool]] = None,
                 volume_size: int = 0) -> bool:
        
        # Map compression levels (1-9) to ZIP compression levels
        # 1-2: Store or fastest, 3-7: Deflated, 8-9: Bzip2/LZMA (using Deflated for zip compatibility)
        comp_type = pyzipper.ZIP_STORED if compression_level == 1 else pyzipper.ZIP_DEFLATED
        
        # Calculate total size
        total_bytes = 0
        all_files: List[tuple] = [] # (absolute_path, relative_path_in_zip)
        
        for p in files_to_compress:
            if p.is_file():
                try:
                    rel_path = p.relative_to(base_dir).as_posix()
                except ValueError:
                    rel_path = p.name
                try:
                    total_bytes += p.stat().st_size
                    all_files.append((p, rel_path))
                except Exception as ex:
                    logger.warning(f"تعذر قراءة خصائص الملف {p}: {str(ex)}")
            elif p.is_dir():
                for root, _, filenames in os.walk(p):
                    for fname in filenames:
                        file_path = Path(root) / fname
                        try:
                            rel_path = file_path.relative_to(base_dir).as_posix()
                        except ValueError:
                            rel_path = file_path.name
                        try:
                            total_bytes += file_path.stat().st_size
                            all_files.append((file_path, rel_path))
                        except Exception as ex:
                            logger.warning(f"تعذر الوصول للملف {file_path} أثناء المسح: {str(ex)}")
                            continue
                            
        logger.info(f"بدء عملية ضغط ZIP للأرشيف '{archive_path.name}'. إجمالي الملفات: {len(all_files)}، الحجم الكلي: {total_bytes} بايت.")
        start_time = time.time()
        bytes_processed = 0
        chunk_size = 8 * 1024 * 1024  # 8MB Chunks (Buffer Size Scaling)
        last_update_time = 0.0
        
        # Compressed file extensions that don't benefit from compression
        COMPRESSED_EXTENSIONS = {
            '.zip', '.7z', '.rar', '.zrar', '.tar', '.gz', '.bz2', '.xz',
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
            '.mp3', '.wav', '.ogg', '.m4a', '.flac',
            '.png', '.jpg', '.jpeg', '.gif', '.webp',
            '.pdf', '.docx', '.xlsx', '.pptx', '.apk', '.jar', '.war'
        }
        
        # Create Zip File
        try:
            if password:
                # Use AES encryption (AES-256)
                zf = pyzipper.AESZipFile(archive_path, 'w', compression=comp_type, encryption=pyzipper.WZ_AES)
                zf.setpassword(password.encode('utf-8'))
            else:
                zf = pyzipper.AESZipFile(archive_path, 'w', compression=comp_type)
                
            with zf:
                for src_path, rel_path in all_files:
                    if cancel_check and cancel_check():
                        logger.info("تم إلغاء عملية ضغط ZIP من قبل المستخدم.")
                        return False
                        
                    zip_info = pyzipper.ZipInfo(rel_path)
                    
                    # Smart Store Mode: Skip compression for pre-compressed formats
                    if src_path.suffix.lower() in COMPRESSED_EXTENSIONS:
                        zip_info.compress_type = pyzipper.ZIP_STORED
                    else:
                        zip_info.compress_type = comp_type
                    # Preserve modification time
                    try:
                        stat = src_path.stat()
                        mtime = time.localtime(stat.st_mtime)
                        zip_info.date_time = (mtime.tm_year, mtime.tm_mon, mtime.tm_mday, mtime.tm_hour, mtime.tm_min, mtime.tm_sec)
                    except Exception:
                        pass
                    
                    with zf.open(zip_info, mode='w') as dest_stream:
                        with open(src_path, 'rb') as src_stream:
                            while True:
                                if cancel_check and cancel_check():
                                    logger.info("تم إلغاء عملية ضغط ZIP من قبل المستخدم.")
                                    return False
                                chunk = src_stream.read(chunk_size)
                                if not chunk:
                                    break
                                dest_stream.write(chunk)
                                bytes_processed += len(chunk)
                                
                                if progress_cb:
                                    current_time = time.time()
                                    if current_time - last_update_time >= 0.25:
                                        progress_cb(ArchiveProgress(
                                            current_file=rel_path,
                                            bytes_processed=bytes_processed,
                                            total_bytes=total_bytes,
                                            elapsed_time=current_time - start_time
                                        ))
                                        last_update_time = current_time
                                        
            # Send final update for accuracy
            if progress_cb:
                progress_cb(ArchiveProgress(
                    current_file="اكتمل الضغط بنجاح",
                    bytes_processed=total_bytes,
                    total_bytes=total_bytes,
                    elapsed_time=time.time() - start_time
                ))
            logger.info(f"تم اكتمال ضغط الأرشيف '{archive_path.name}' بنجاح في {time.time() - start_time:.2f} ثانية.")
            return True
        except Exception as e:
            logger.error(f"خطأ فادح أثناء ضغط ZIP للأرشيف '{archive_path.name}': {str(e)}", exc_info=True)
            if archive_path.exists():
                try:
                    archive_path.unlink()
                except OSError as oe:
                    logger.warning(f"فشل حذف الأرشيف التالف '{archive_path.name}': {str(oe)}")
            raise e

    def decompress(self, 
                   archive_path: Path, 
                   extract_dir: Path, 
                   password: Optional[str] = None,
                   progress_cb: Optional[ProgressCallback] = None,
                   cancel_check: Optional[Callable[[], bool]] = None) -> bool:
        
        start_time = time.time()
        chunk_size = 1024 * 1024  # 1MB Chunks
        last_update_time = 0.0
        
        try:
            zf = pyzipper.AESZipFile(archive_path, 'r')
            if password:
                zf.setpassword(password.encode('utf-8'))
                
            with zf:
                # Calculate total size of files to decompress
                infolist = zf.infolist()
                total_bytes = sum(info.file_size for info in infolist)
                bytes_processed = 0
                
                for info in infolist:
                    if cancel_check and cancel_check():
                        return False
                        
                    # Skip directories (pyzipper creates directories automatically on file extraction)
                    if info.filename.endswith('/'):
                        continue
                        
                    dest_file_path = extract_dir / info.filename
                    # Ensure parent directories exist
                    dest_file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    with zf.open(info, mode='r') as src_stream:
                        with open(dest_file_path, 'wb') as dest_stream:
                            while True:
                                if cancel_check and cancel_check():
                                    return False
                                chunk = src_stream.read(chunk_size)
                                if not chunk:
                                    break
                                dest_stream.write(chunk)
                                bytes_processed += len(chunk)
                                
                                if progress_cb:
                                    current_time = time.time()
                                    if current_time - last_update_time >= 0.25:
                                        progress_cb(ArchiveProgress(
                                            current_file=info.filename,
                                            bytes_processed=bytes_processed,
                                            total_bytes=total_bytes,
                                            elapsed_time=current_time - start_time
                                        ))
                                        last_update_time = current_time
                                        
            # Send final update for accuracy
            if progress_cb:
                progress_cb(ArchiveProgress(
                    current_file="اكتمل فك الضغط بنجاح",
                    bytes_processed=total_bytes,
                    total_bytes=total_bytes,
                    elapsed_time=time.time() - start_time
                ))
            return True
        except Exception as e:
            raise e

    def list_files(self, archive_path: Path, password: Optional[str] = None) -> List[dict]:
        file_list = []
        try:
            zf = pyzipper.AESZipFile(archive_path, 'r')
            if password:
                zf.setpassword(password.encode('utf-8'))
            with zf:
                for info in zf.infolist():
                    file_list.append({
                        'filename': info.filename,
                        'file_size': info.file_size,
                        'compress_size': info.compress_size,
                        'is_dir': info.filename.endswith('/'),
                        'date_time': f"{info.date_time[0]:04d}-{info.date_time[1]:02d}-{info.date_time[2]:02d} {info.date_time[3]:02d}:{info.date_time[4]:02d}:{info.date_time[5]:02d}"
                    })
        except Exception as e:
            raise e
        return file_list
class SevenZipEngine(BaseArchiveEngine):
    """7z Engine using native 7z.exe with py7zr fallback."""
    
    def compress(self, 
                 files_to_compress: List[Path], 
                 archive_path: Path, 
                 base_dir: Path,
                 password: Optional[str] = None, 
                 compression_level: int = 5,
                 progress_cb: Optional[ProgressCallback] = None,
                 cancel_check: Optional[Callable[[], bool]] = None,
                 volume_size: int = 0) -> bool:
        
        # Calculate total size
        total_bytes = 0
        all_files: List[tuple] = []
        
        for p in files_to_compress:
            if p.is_file():
                try:
                    rel_path = p.relative_to(base_dir).as_posix()
                except ValueError:
                    rel_path = p.name
                total_bytes += p.stat().st_size
                all_files.append((p, rel_path))
            elif p.is_dir():
                for root, _, filenames in os.walk(p):
                    for fname in filenames:
                        file_path = Path(root) / fname
                        try:
                            rel_path = file_path.relative_to(base_dir).as_posix()
                        except ValueError:
                            rel_path = file_path.name
                        try:
                            total_bytes += file_path.stat().st_size
                            all_files.append((file_path, rel_path))
                        except Exception:
                            continue
                            
        start_time = time.time()
        last_update_time = 0.0
        
        # Detect if native 7-zip executable is available in bin folder
        try:
            exe_path = get_resource_path(os.path.join("bin", "7z.exe"))
            has_native = os.path.exists(exe_path)
        except Exception:
            has_native = False
            
        if has_native:
            # Map compression levels
            if compression_level == 1:
                mx_level = 0
            elif compression_level <= 3:
                mx_level = 1
            elif compression_level <= 5:
                mx_level = 3
            elif compression_level <= 7:
                mx_level = 4
            else:
                mx_level = 5
                
            # Create temporary listfile to avoid Windows command line length limit (8191 chars)
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as f:
                for src_path, rel_path in all_files:
                    f.write(rel_path + "\n")
                listfile_path = f.name
                
            cmd = [
                exe_path,
                "a",
                "-t7z",
                f"-mx={mx_level}",
                "-mmt=on",
                "-bsp1",
                "-bso0",
                "-y"
            ]
            if password:
                cmd.append(f"-p{password}")
                cmd.append("-mhe=on")
            if volume_size > 0:
                cmd.append(f"-v{volume_size}b")
                
            cmd.append(str(archive_path))
            cmd.append(f"@{listfile_path}")
            
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(base_dir),
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                import re
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    if cancel_check and cancel_check():
                        process.terminate()
                        process.wait()
                        return False
                        
                    line_clean = line.strip().replace('\b', '').replace('\r', '')
                    match = re.search(r'(\d+)%', line_clean)
                    if match and progress_cb:
                        percent = int(match.group(1))
                        current_time = time.time()
                        if current_time - last_update_time >= 0.25:
                            progress_cb(ArchiveProgress(
                                current_file="جاري الضغط بواسطة محرك 7-Zip السريع...",
                                bytes_processed=int(total_bytes * (percent / 100.0)),
                                total_bytes=total_bytes,
                                elapsed_time=current_time - start_time
                            ))
                            last_update_time = current_time
            finally:
                try:
                    os.unlink(listfile_path)
                except OSError:
                    pass
                    
            if progress_cb:
                progress_cb(ArchiveProgress(
                    current_file="اكتمل الضغط بنجاح",
                    bytes_processed=total_bytes,
                    total_bytes=total_bytes,
                    elapsed_time=time.time() - start_time
                ))
            return (process.returncode == 0)
            
        else:
            # Fallback to pure-Python py7zr implementation
            if compression_level == 1:
                filters = [{"id": py7zr.FILTER_COPY}]
            else:
                if compression_level <= 3:
                    preset = 1
                elif compression_level <= 5:
                    preset = 3
                elif compression_level <= 7:
                    preset = 4
                else:
                    preset = 5
                filters = [{"id": py7zr.FILTER_LZMA2, "preset": preset}]
                
            import contextlib
            if volume_size > 0:
                import multivolumefile
                mv_ctx = multivolumefile.open(str(archive_path), 'wb', volume=volume_size)
            else:
                mv_ctx = contextlib.nullcontext(archive_path)
                
            try:
                with mv_ctx as target_file:
                    with py7zr.SevenZipFile(target_file, 'w', password=password, filters=filters) as sz:
                        for src_path, rel_path in all_files:
                            if cancel_check and cancel_check():
                                return False
                            sz.write(src_path, rel_path)
                            bytes_processed += src_path.stat().st_size
                            if progress_cb:
                                current_time = time.time()
                                if current_time - last_update_time >= 0.25:
                                    progress_cb(ArchiveProgress(
                                        current_file=rel_path,
                                        bytes_processed=bytes_processed,
                                        total_bytes=total_bytes,
                                        elapsed_time=current_time - start_time
                                    ))
                                    last_update_time = current_time
                if progress_cb:
                    progress_cb(ArchiveProgress(
                        current_file="اكتمل الضغط بنجاح",
                        bytes_processed=total_bytes,
                        total_bytes=total_bytes,
                        elapsed_time=time.time() - start_time
                    ))
                return True
            except Exception as e:
                if archive_path.exists():
                    try:
                        archive_path.unlink()
                    except OSError:
                        pass
                raise e

    def decompress(self, 
                   archive_path: Path, 
                   extract_dir: Path, 
                   password: Optional[str] = None,
                   progress_cb: Optional[ProgressCallback] = None,
                   cancel_check: Optional[Callable[[], bool]] = None) -> bool:
        
        start_time = time.time()
        last_update_time = 0.0
        
        try:
            exe_path = get_resource_path(os.path.join("bin", "7z.exe"))
            has_native = os.path.exists(exe_path)
        except Exception:
            has_native = False
            
        if has_native:
            import re
            base_path = archive_path
            match = re.search(r'\.7z\.\d+$', str(archive_path).lower())
            if match:
                base_path = Path(str(archive_path)[:match.start() + 3])
                
            cmd = [
                exe_path,
                "x",
                str(base_path),
                f"-o{extract_dir}",
                "-y",
                "-bsp1",
                "-bso0"
            ]
            if password:
                cmd.append(f"-p{password}")
                
            try:
                # Find total uncompressed size for status tracking
                archive_info = self.list_files(archive_path, password)
                total_bytes = sum(f['file_size'] for f in archive_info if not f['is_dir'])
            except Exception:
                total_bytes = 0
                
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            import re
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if cancel_check and cancel_check():
                    process.terminate()
                    process.wait()
                    return False
                    
                line_clean = line.strip().replace('\b', '').replace('\r', '')
                match_percent = re.search(r'(\d+)%', line_clean)
                if match_percent and progress_cb:
                    percent = int(match_percent.group(1))
                    current_time = time.time()
                    if current_time - last_update_time >= 0.25:
                        progress_cb(ArchiveProgress(
                            current_file="جاري فك الضغط بواسطة محرك 7-Zip السريع...",
                            bytes_processed=int(total_bytes * (percent / 100.0)),
                            total_bytes=total_bytes,
                            elapsed_time=current_time - start_time
                        ))
                        last_update_time = current_time
                        
            if progress_cb:
                progress_cb(ArchiveProgress(
                    current_file="اكتمل فك الضغط بنجاح",
                    bytes_processed=total_bytes,
                    total_bytes=total_bytes,
                    elapsed_time=time.time() - start_time
                ))
            return (process.returncode == 0)
            
        else:
            # Fallback to py7zr
            import re
            import contextlib
            base_path = archive_path
            is_split = False
            
            match = re.search(r'\.7z\.\d+$', str(archive_path).lower())
            if match:
                base_path = Path(str(archive_path)[:match.start() + 3])
                is_split = True
                
            if is_split:
                import multivolumefile
                mv_ctx = multivolumefile.open(str(base_path), 'rb')
            else:
                mv_ctx = contextlib.nullcontext(archive_path)
                
            try:
                with mv_ctx as target_file:
                    with py7zr.SevenZipFile(target_file, 'r', password=password) as sz:
                        archive_info = sz.list()
                        total_bytes = 0
                        for f in archive_info:
                            if not f.is_directory:
                                total_bytes += f.uncompressed
                                
                        bytes_processed = 0
                        files_to_extract = [f.filename for f in archive_info if not f.is_directory]
                        
                        for filename in files_to_extract:
                            if cancel_check and cancel_check():
                                return False
                            sz.extract(targets=[filename], path=extract_dir)
                            for info in archive_info:
                                if info.filename == filename:
                                    bytes_processed += info.uncompressed
                                    break
                            if progress_cb:
                                current_time = time.time()
                                if current_time - last_update_time >= 0.25:
                                    progress_cb(ArchiveProgress(
                                        current_file=filename,
                                        bytes_processed=bytes_processed,
                                        total_bytes=total_bytes,
                                        elapsed_time=current_time - start_time
                                    ))
                                    last_update_time = current_time
                if progress_cb:
                    progress_cb(ArchiveProgress(
                        current_file="اكتمل فك الضغط بنجاح",
                        bytes_processed=total_bytes,
                        total_bytes=total_bytes,
                        elapsed_time=time.time() - start_time
                    ))
                return True
            except Exception as e:
                raise e

    def list_files(self, archive_path: Path, password: Optional[str] = None) -> List[dict]:
        try:
            exe_path = get_resource_path(os.path.join("bin", "7z.exe"))
            has_native = os.path.exists(exe_path)
        except Exception:
            has_native = False
            
        if has_native:
            file_list = []
            import re
            base_path = archive_path
            match = re.search(r'\.7z\.\d+$', str(archive_path).lower())
            if match:
                base_path = Path(str(archive_path)[:match.start() + 3])
                
            cmd = [exe_path, "l", "-slt", str(base_path)]
            if password:
                cmd.append(f"-p{password}")
                
            try:
                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                lines = result.stdout.splitlines()
                current_entry = {}
                in_files_section = False
                for line in lines:
                    line = line.strip()
                    if line.startswith('----------'):
                        in_files_section = True
                        current_entry = {}
                        continue
                    if not in_files_section:
                        continue
                    if not line:
                        if current_entry and 'filename' in current_entry:
                            current_entry.setdefault('is_dir', False)
                            current_entry.setdefault('file_size', 0)
                            current_entry.setdefault('compress_size', 0)
                            current_entry.setdefault('date_time', 'Unknown')
                            file_list.append(current_entry)
                            current_entry = {}
                        continue
                    if '=' in line:
                        key, val = line.split('=', 1)
                        key = key.strip().lower()
                        val = val.strip()
                        
                        if key == 'path':
                            current_entry['filename'] = val
                        elif key == 'size':
                            current_entry['file_size'] = int(val) if val.isdigit() else 0
                        elif key == 'packed size':
                            current_entry['compress_size'] = int(val) if val.isdigit() else 0
                        elif key == 'folder':
                            current_entry['is_dir'] = (val == '+')
                        elif key == 'modified':
                            current_entry['date_time'] = val
                            
                if current_entry and 'filename' in current_entry:
                    current_entry.setdefault('is_dir', False)
                    current_entry.setdefault('file_size', 0)
                    current_entry.setdefault('compress_size', 0)
                    current_entry.setdefault('date_time', 'Unknown')
                    file_list.append(current_entry)
            except Exception as e:
                logger.error(f"Error listing files with native 7z: {str(e)}")
                raise e
            return file_list
            
        else:
            # Fallback to py7zr
            file_list = []
            import re
            import contextlib
            base_path = archive_path
            is_split = False
            
            match = re.search(r'\.7z\.\d+$', str(archive_path).lower())
            if match:
                base_path = Path(str(archive_path)[:match.start() + 3])
                is_split = True
                
            if is_split:
                import multivolumefile
                mv_ctx = multivolumefile.open(str(base_path), 'rb')
            else:
                mv_ctx = contextlib.nullcontext(archive_path)
                
            try:
                with mv_ctx as target_file:
                    with py7zr.SevenZipFile(target_file, 'r', password=password) as sz:
                        for info in sz.list():
                            dt = info.creationtime if info.creationtime else info.modified
                            dt_str = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "Unknown"
                            file_list.append({
                                'filename': info.filename,
                                'file_size': info.uncompressed,
                                'compress_size': info.compressed if info.compressed else 0,
                                'is_dir': info.is_directory,
                                'date_time': dt_str
                            })
            except Exception as e:
                raise e
            return file_list


class ZrarEngine(SevenZipEngine):
    """
    Custom ZRar engine that creates standard 7z archives under the hood,
    but appends a secure signature and JSON metadata wrapper at the end of the file
    for branding, app integration, and validation.
    """
    
    def compress(self, 
                 files_to_compress: List[Path], 
                 archive_path: Path, 
                 base_dir: Path,
                 password: Optional[str] = None, 
                 compression_level: int = 5,
                 progress_cb: Optional[ProgressCallback] = None,
                 cancel_check: Optional[Callable[[], bool]] = None,
                 volume_size: int = 0) -> bool:
                 
        # 1. Compress using SevenZipEngine
        success = super().compress(
            files_to_compress=files_to_compress,
            archive_path=archive_path,
            base_dir=base_dir,
            password=password,
            compression_level=compression_level,
            progress_cb=progress_cb,
            cancel_check=cancel_check,
            volume_size=volume_size
        )
        
        if success and volume_size == 0 and archive_path.exists():
            try:
                import json
                # 2. Append custom ZRar metadata signature at the end
                metadata = {
                    "app_name": "ZRar",
                    "version": "1.0.0",
                    "created_at": time.time(),
                    "original_format": "7z",
                    "comment": "تم الضغط بواسطة بديل WinRAR المجاني - ZRar"
                }
                meta_bytes = json.dumps(metadata, ensure_ascii=False).encode('utf-8')
                meta_len = len(meta_bytes)
                
                with open(archive_path, 'ab') as f:
                    f.write(meta_bytes)
                    f.write(meta_len.to_bytes(4, byteorder='big'))
                    f.write(b"ZRAR")
                logger.info(f"تمت إضافة بصمة ZRar الخاصة بنجاح للأرشيف: {archive_path.name}")
            except Exception as e:
                logger.warning(f"تعذر كتابة بصمة ZRar التعريفية للأرشيف: {str(e)}")
                
        return success

    @staticmethod
    def read_zrar_metadata(archive_path: Path) -> Optional[dict]:
        """Reads and parses the custom ZRar metadata from the end of the file."""
        if not archive_path.exists():
            return None
            
        try:
            file_size = archive_path.stat().st_size
            if file_size < 12:  # Min size: payload + 4 bytes len + 4 bytes signature
                return None
                
            with open(archive_path, 'rb') as f:
                # Seek to signature
                f.seek(file_size - 4)
                sig = f.read(4)
                if sig != b"ZRAR":
                    return None
                    
                # Read length
                f.seek(file_size - 8)
                len_bytes = f.read(4)
                meta_len = int.from_bytes(len_bytes, byteorder='big')
                
                if meta_len <= 0 or meta_len > file_size - 8:
                    return None
                    
                # Read JSON payload
                f.seek(file_size - 8 - meta_len)
                meta_bytes = f.read(meta_len)
                import json
                return json.loads(meta_bytes.decode('utf-8'))
        except Exception as e:
            logger.warning(f"فشل قراءة بصمة ZRar التعريفية من {archive_path.name}: {str(e)}")
            return None


class TarEngine(BaseArchiveEngine):
    """Tar Engine using native tarfile library, supporting gz, bz2, and xz."""
    
    def _get_mode(self, archive_path: Path, mode_prefix: str) -> str:
        suffix = archive_path.suffix.lower()
        if suffix == '.gz' or archive_path.name.endswith('.tar.gz'):
            return f"{mode_prefix}:gz"
        elif suffix == '.bz2' or archive_path.name.endswith('.tar.bz2'):
            return f"{mode_prefix}:bz2"
        elif suffix == '.xz' or archive_path.name.endswith('.tar.xz'):
            return f"{mode_prefix}:xz"
        return mode_prefix

    def compress(self, 
                 files_to_compress: List[Path], 
                 archive_path: Path, 
                 base_dir: Path,
                 password: Optional[str] = None, 
                 compression_level: int = 5,
                 progress_cb: Optional[ProgressCallback] = None,
                 cancel_check: Optional[Callable[[], bool]] = None,
                 volume_size: int = 0) -> bool:
        
        if password:
            raise ValueError("TAR archives do not support native password encryption.")
            
        mode = self._get_mode(archive_path, 'w')
        
        # Calculate total size
        total_bytes = 0
        all_files: List[tuple] = []
        
        for p in files_to_compress:
            if p.is_file():
                try:
                    rel_path = p.relative_to(base_dir).as_posix()
                except ValueError:
                    rel_path = p.name
                total_bytes += p.stat().st_size
                all_files.append((p, rel_path))
            elif p.is_dir():
                for root, _, filenames in os.walk(p):
                    for fname in filenames:
                        file_path = Path(root) / fname
                        try:
                            rel_path = file_path.relative_to(base_dir).as_posix()
                        except ValueError:
                            rel_path = file_path.name
                        try:
                            total_bytes += file_path.stat().st_size
                            all_files.append((file_path, rel_path))
                        except Exception:
                            continue
                            
        start_time = time.time()
        bytes_processed = 0
        last_update_time = 0.0
        
        try:
            with tarfile.open(archive_path, mode) as tar:
                for src_path, rel_path in all_files:
                    if cancel_check and cancel_check():
                        return False
                        
                    # Create a tarinfo object
                    tarinfo = tar.gettarinfo(name=str(src_path), arcname=rel_path)
                    
                    with open(src_path, 'rb') as f:
                        tar.addfile(tarinfo, fileobj=f)
                        
                    bytes_processed += src_path.stat().st_size
                    if progress_cb:
                        current_time = time.time()
                        if current_time - last_update_time >= 0.25:
                            progress_cb(ArchiveProgress(
                                current_file=rel_path,
                                bytes_processed=bytes_processed,
                                total_bytes=total_bytes,
                                elapsed_time=current_time - start_time
                            ))
                            last_update_time = current_time
            # Final update
            if progress_cb:
                progress_cb(ArchiveProgress(
                    current_file="اكتمل الضغط بنجاح",
                    bytes_processed=total_bytes,
                    total_bytes=total_bytes,
                    elapsed_time=time.time() - start_time
                ))
            return True
        except Exception as e:
            if archive_path.exists():
                try:
                    archive_path.unlink()
                except OSError:
                    pass
            raise e

    def decompress(self, 
                   archive_path: Path, 
                   extract_dir: Path, 
                   password: Optional[str] = None,
                   progress_cb: Optional[ProgressCallback] = None,
                   cancel_check: Optional[Callable[[], bool]] = None) -> bool:
        
        if password:
            raise ValueError("TAR archives do not support password protection.")
            
        mode = self._get_mode(archive_path, 'r')
        start_time = time.time()
        last_update_time = 0.0
        
        try:
            with tarfile.open(archive_path, mode) as tar:
                # Find total uncompressed size
                members = tar.getmembers()
                total_bytes = sum(m.size for m in members if m.isfile())
                bytes_processed = 0
                
                for member in members:
                    if cancel_check and cancel_check():
                        return False
                        
                    tar.extract(member, path=extract_dir)
                    
                    if member.isfile():
                        bytes_processed += member.size
                        
                    if progress_cb:
                        current_time = time.time()
                        if current_time - last_update_time >= 0.25:
                            progress_cb(ArchiveProgress(
                                current_file=member.name,
                                bytes_processed=bytes_processed,
                                total_bytes=total_bytes,
                                elapsed_time=current_time - start_time
                            ))
                            last_update_time = current_time
            # Final update
            if progress_cb:
                progress_cb(ArchiveProgress(
                    current_file="اكتمل فك الضغط بنجاح",
                    bytes_processed=total_bytes,
                    total_bytes=total_bytes,
                    elapsed_time=time.time() - start_time
                ))
            return True
        except Exception as e:
            raise e

    def list_files(self, archive_path: Path, password: Optional[str] = None) -> List[dict]:
        file_list = []
        mode = self._get_mode(archive_path, 'r')
        try:
            with tarfile.open(archive_path, mode) as tar:
                for member in tar.getmembers():
                    # Format time
                    mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(member.mtime))
                    file_list.append({
                        'filename': member.name,
                        'file_size': member.size,
                        'compress_size': member.size, # Tar has overall block compression, can't measure individual compressed sizes easily
                        'is_dir': member.isdir(),
                        'date_time': mtime_str
                    })
        except Exception as e:
            raise e
        return file_list


class RarEngine(BaseArchiveEngine):
    """RAR Engine that uses system unrar tool via subprocess (extract only)."""
    
    def _find_unrar(self) -> Optional[str]:
        """Look for unrar.exe in common locations."""
        # 1. Check in PATH
        from shutil import which
        path_unrar = which("unrar")
        if path_unrar:
            return path_unrar
            
        # 2. Check WinRAR standard directories
        paths_to_check = [
            r"C:\Program Files\WinRAR\UnRAR.exe",
            r"C:\Program Files (x86)\WinRAR\UnRAR.exe",
            r"C:\Program Files\WinRAR\WinRAR.exe", # WinRAR CLI also supports unrar arguments
            r"C:\Program Files (x86)\WinRAR\WinRAR.exe",
        ]
        for p in paths_to_check:
            if Path(p).exists():
                return p
        return None

    def compress(self, 
                 files_to_compress: List[Path], 
                 archive_path: Path, 
                 base_dir: Path,
                 password: Optional[str] = None, 
                 compression_level: int = 5,
                 progress_cb: Optional[ProgressCallback] = None,
                 cancel_check: Optional[Callable[[], bool]] = None) -> bool:
        raise NotImplementedError("Creating RAR archives is not supported (RAR compression is proprietary). Please use ZIP or 7Z.")

    def decompress(self, 
                   archive_path: Path, 
                   extract_dir: Path, 
                   password: Optional[str] = None,
                   progress_cb: Optional[ProgressCallback] = None,
                   cancel_check: Optional[Callable[[], bool]] = None) -> bool:
        
        unrar_exe = self._find_unrar()
        if not unrar_exe:
            raise FileNotFoundError("أداة فك ضغط RAR غير متوفرة. يرجى تثبيت WinRAR أو أداة UnRAR الرسمية.")
            
        start_time = time.time()
        
        # Command arguments:
        # x : Extract with full paths
        # -y : Assume Yes on all queries
        # -p{password} : Password
        cmd = [unrar_exe, "x", "-y"]
        if password:
            cmd.append(f"-p{password}")
        else:
            cmd.append("-p-") # Do not prompt for password
            
        cmd.extend([str(archive_path), str(extract_dir) + os.sep])
        
        try:
            # Run the command. Use CREATE_NO_WINDOW on Windows to prevent CMD flicker.
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0 # SW_HIDE
            
            # Start process
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Since unrar output is printed line by line, we can parse progress if it output percentages.
            # In unrar, it outputs progress on stdout as '...  10%' etc.
            # We will read line-by-line or char-by-char and look for percentages.
            total_bytes = 100 # We will just use percentage as progress scale (0 to 100)
            bytes_processed = 0
            
            while True:
                if cancel_check and cancel_check():
                    process.terminate()
                    return False
                    
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                    
                # Try to parse percentage like '...  45%' or '45%'
                if '%' in line:
                    parts = line.split('%')
                    for part in parts:
                        subparts = part.strip().split()
                        if subparts:
                            val = subparts[-1]
                            if val.isdigit():
                                bytes_processed = int(val)
                                if progress_cb:
                                    progress_cb(ArchiveProgress(
                                        current_file="Extracting archives...",
                                        bytes_processed=bytes_processed,
                                        total_bytes=total_bytes,
                                        elapsed_time=time.time() - start_time
                                    ))
                                    
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                if "password" in stderr.lower() or "password" in stdout.lower() or process.returncode == 3:
                    raise ValueError("كلمة مرور خاطئة للأرشيف أو الملف محمي بكلمة مرور.")
                raise RuntimeError(f"فشلت عملية فك الضغط. تفاصيل الخطأ: {stderr or stdout}")
                
            return True
        except Exception as e:
            raise e

    def list_files(self, archive_path: Path, password: Optional[str] = None) -> List[dict]:
        unrar_exe = self._find_unrar()
        if not unrar_exe:
            raise FileNotFoundError("أداة فك ضغط RAR غير متوفرة. يرجى تثبيت WinRAR أو أداة UnRAR الرسمية.")
            
        # Command to list files:
        # vt: View Technical information (outputs JSON-like or tabular list details)
        cmd = [unrar_exe, "vt"]
        if password:
            cmd.append(f"-p{password}")
        else:
            cmd.append("-p-")
        cmd.append(str(archive_path))
        
        file_list = []
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode != 0:
                raise ValueError("فشلت قراءة ملف RAR. قد يكون الملف محمياً بكلمة مرور أو تالفاً.")
                
            # Parse technical list output
            # Output format contains blocks like:
            # Name: path/to/file
            # Type: File
            # Size: 12345
            # Packed size: 5432
            # Mtime: 2026-07-06 21:00:00
            lines = result.stdout.splitlines()
            current_entry = {}
            
            for line in lines:
                line = line.strip()
                if not line:
                    if current_entry and 'filename' in current_entry:
                        file_list.append(current_entry)
                        current_entry = {}
                    continue
                
                if ':' in line:
                    key, val = line.split(':', 1)
                    key = key.strip().lower()
                    val = val.strip()
                    
                    if key == 'name':
                        current_entry['filename'] = val
                    elif key == 'type':
                        current_entry['is_dir'] = (val.lower() == 'directory')
                    elif key == 'size':
                        current_entry['file_size'] = int(val) if val.isdigit() else 0
                    elif key == 'packed size':
                        current_entry['compress_size'] = int(val) if val.isdigit() else 0
                    elif key == 'mtime':
                        current_entry['date_time'] = val
                        
            if current_entry and 'filename' in current_entry:
                file_list.append(current_entry)
                
        except Exception as e:
            raise e
            
        return file_list


class ArchiveEngineRegistry:
    """Central registry for mapping archive file extensions to compression engines."""
    _engines = {}
    
    @classmethod
    def register(cls, extensions: List[str], engine_class: type):
        """Register an engine class for a list of extensions."""
        for ext in extensions:
            cls._engines[ext.lower()] = engine_class

    @classmethod
    def get_engine_for_path(cls, archive_path: Path) -> BaseArchiveEngine:
        """Find and return the correct engine instance for a given archive file path."""
        import re
        name_lower = archive_path.name.lower()
        
        # 1. Handle split 7z archives (e.g. .7z.001)
        if re.search(r'\.7z\.\d+$', name_lower):
            return SevenZipEngine()
            
        # 2. Match compound extensions first (e.g. .tar.gz)
        for ext, engine_class in cls._engines.items():
            if ext.count('.') > 1 and name_lower.endswith(ext):
                return engine_class()
                
        # 3. Match single extension
        suffix = archive_path.suffix.lower()
        if suffix in cls._engines:
            return cls._engines[suffix]()
            
        raise ValueError(f"صيغة غير مدعومة: {suffix}")

# Register default engines
ArchiveEngineRegistry.register(['.zrar'], ZrarEngine)
ArchiveEngineRegistry.register(['.zip'], ZipEngine)
ArchiveEngineRegistry.register(['.7z'], SevenZipEngine)
ArchiveEngineRegistry.register(['.tar', '.gz', '.bz2', '.xz', '.tar.gz', '.tar.bz2', '.tar.xz'], TarEngine)
ArchiveEngineRegistry.register(['.rar'], RarEngine)


def get_archive_engine(archive_path: Path) -> BaseArchiveEngine:
    """Backward-compatible helper function that delegates to ArchiveEngineRegistry."""
    return ArchiveEngineRegistry.get_engine_for_path(archive_path)
