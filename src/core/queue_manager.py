import time
import uuid
import multiprocessing
from pathlib import Path
from typing import List, Callable, Optional, Dict
from .archiver import get_archive_engine, ArchiveProgress
from .logger import get_logger

logger = get_logger()

class ArchiveTask:
    """Represents a compression or decompression task in the queue."""
    def __init__(self, 
                 task_type: str,  # 'compress' or 'decompress'
                 source_paths: List[Path], 
                 archive_path: Path, 
                 base_dir: Path,
                 password: Optional[str] = None,
                 compression_level: int = 5,
                 volume_size: int = 0):
        self.id = str(uuid.uuid4())
        self.task_type = task_type
        self.source_paths = source_paths
        self.archive_path = archive_path
        self.base_dir = base_dir
        self.password = password
        self.compression_level = compression_level
        self.volume_size = volume_size
        
        self.status = "pending"  # 'pending', 'processing', 'completed', 'failed', 'cancelled'
        self.current_file = ""
        self.progress_percent = 0.0
        self.processed_bytes = 0
        self.total_bytes = 0
        self.speed = 0.0
        self.remaining_time = -1.0
        self.error_message = ""
        self.cancel_requested = False

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'task_type': self.task_type,
            'archive_name': self.archive_path.name,
            'status': self.status,
            'current_file': self.current_file,
            'progress_percent': self.progress_percent,
            'processed_bytes': self.processed_bytes,
            'total_bytes': self.total_bytes,
            'speed': self.speed,
            'remaining_time': self.remaining_time,
            'error_message': self.error_message
        }


def _process_worker_entry(task_id: str, 
                          task_type: str, 
                          source_paths: List[Path], 
                          archive_path: Path, 
                          base_dir: Path, 
                          password: Optional[str], 
                          compression_level: int,
                          prog_queue: multiprocessing.Queue,
                          cancel_event: multiprocessing.Event,
                          volume_size: int = 0):
    """
    Isolated entry point for the worker process. 
    Runs on its own GIL, leaving the Tkinter UI process completely smooth.
    """
    # Re-initialize logger for the child process context
    from .logger import get_logger
    proc_logger = get_logger()
    proc_logger.info(f"بدأت عملية فرعية جديدة للمهمة: {task_id} ({task_type})")
    
    try:
        engine = get_archive_engine(archive_path)
        
        # Custom progress callback that serializes updates to the parent process queue
        def progress_cb(prog: ArchiveProgress):
            prog_queue.put({
                'task_id': task_id,
                'status': 'processing',
                'current_file': prog.current_file,
                'processed_bytes': prog.bytes_processed,
                'total_bytes': prog.total_bytes,
                'progress_percent': prog.percent,
                'speed': prog.speed,
                'remaining_time': prog.remaining_time,
                'error_message': ''
            })

        # Define cancel checker using event
        def cancel_check_fn():
            return cancel_event.is_set()

        import os
        if task_type == "compress":
            tmp_archive_path = archive_path.with_name(archive_path.name + ".tmp")
            success = engine.compress(
                files_to_compress=source_paths,
                archive_path=tmp_archive_path,
                base_dir=base_dir,
                password=password,
                compression_level=compression_level,
                progress_cb=progress_cb,
                cancel_check=cancel_check_fn,
                volume_size=volume_size
            )
            
            # Atomic transaction commit/rollback
            if success:
                try:
                    # Commit: rename tmp file(s) to final name
                    if volume_size > 0:
                        parent_dir = archive_path.parent
                        tmp_prefix = tmp_archive_path.name
                        for f_name in os.listdir(parent_dir):
                            if f_name.startswith(tmp_prefix):
                                tmp_file_path = parent_dir / f_name
                                final_file_name = f_name.replace(tmp_prefix, archive_path.name)
                                final_file_path = parent_dir / final_file_name
                                if final_file_path.exists():
                                    final_file_path.unlink()
                                os.rename(tmp_file_path, final_file_path)
                    else:
                        if archive_path.exists():
                            archive_path.unlink()
                        os.rename(tmp_archive_path, archive_path)
                    proc_logger.info("تم تأكيد ونشر معاملة الضغط الذري (Commit) بنجاح.")
                except Exception as tx_err:
                    proc_logger.error(f"فشل تأكيد معاملة الضغط الذري: {str(tx_err)}")
                    success = False
                    error_msg = f"فشل استبدال الملف النهائي: {str(tx_err)}"
            else:
                # Rollback: Clean up any partial files
                try:
                    if volume_size > 0:
                        parent_dir = archive_path.parent
                        tmp_prefix = tmp_archive_path.name
                        for f_name in os.listdir(parent_dir):
                            if f_name.startswith(tmp_prefix):
                                (parent_dir / f_name).unlink()
                    else:
                        if tmp_archive_path.exists():
                            tmp_archive_path.unlink()
                    proc_logger.info("تم التراجع عن معاملة الضغط (Rollback) وتطهير الملفات المؤقتة بنجاح.")
                except Exception as rb_err:
                    proc_logger.warning(f"فشل تنظيف الملفات المؤقتة أثناء التراجع: {str(rb_err)}")
        else:
            success = engine.decompress(
                archive_path=archive_path,
                extract_dir=base_dir, # destination is base_dir
                password=password,
                progress_cb=progress_cb,
                cancel_check=cancel_check_fn
            )

        if success:
            proc_logger.info(f"أنهت العملية الفرعية مهمتها بنجاح: {task_id}")
            prog_queue.put({
                'task_id': task_id,
                'status': 'completed',
                'progress_percent': 100.0,
                'error_message': ''
            })
        else:
            proc_logger.warning(f"العملية الفرعية أرجعت فشلاً أو تم إلغاؤها للمهمة: {task_id}")
            # If error_msg wasn't set, use generic cancelled msg
            err_text = locals().get('error_msg', 'تم إلغاء العملية أو فشلها.')
            prog_queue.put({
                'task_id': task_id,
                'status': 'cancelled' if not locals().get('error_msg') else 'failed',
                'error_message': err_text
            })
            
    except Exception as e:
        proc_logger.error(f"خطأ فادح غير متوقع بالعملية الفرعية للمهمة {task_id}: {str(e)}", exc_info=True)
        prog_queue.put({
            'task_id': task_id,
            'status': 'failed',
            'error_message': str(e)
        })


class QueueManager:
    """Manages thread-safe and process-isolated execution of archiving tasks."""
    
    def __init__(self, ui_update_cb: Callable[[ArchiveTask], None]):
        self.ui_update_cb = ui_update_cb
        
        # Tasks queue and map
        self.tasks: Dict[str, ArchiveTask] = {}
        self.pending_task_ids: List[str] = []
        
        # Active worker process tracking
        self.active_task: Optional[ArchiveTask] = None
        self.active_process: Optional[multiprocessing.Process] = None
        self.active_cancel_event: Optional[multiprocessing.Event] = None
        
        # Inter-process communication queue
        self.process_queue = multiprocessing.Queue()
        
    def add_compress_task(self, 
                          source_paths: List[Path], 
                          archive_path: Path, 
                          base_dir: Path,
                          password: Optional[str] = None,
                          compression_level: int = 5,
                          volume_size: int = 0) -> str:
        
        task = ArchiveTask(
            task_type="compress",
            source_paths=source_paths,
            archive_path=archive_path,
            base_dir=base_dir,
            password=password,
            compression_level=compression_level,
            volume_size=volume_size
        )
        self.tasks[task.id] = task
        self.pending_task_ids.append(task.id)
        logger.info(f"تمت إضافة مهمة ضغط جديدة للطابور: {task.id} الأرشيف: {archive_path.name}")
        self._check_queue()
        return task.id

    def add_decompress_task(self, 
                            archive_path: Path, 
                            extract_dir: Path, 
                            password: Optional[str] = None) -> str:
        
        task = ArchiveTask(
            task_type="decompress",
            source_paths=[archive_path],
            archive_path=archive_path,
            base_dir=extract_dir,
            password=password
        )
        self.tasks[task.id] = task
        self.pending_task_ids.append(task.id)
        logger.info(f"تمت إضافة مهمة فك ضغط جديدة للطابور: {task.id} الأرشيف: {archive_path.name}")
        self._check_queue()
        return task.id

    def cancel_task(self, task_id: str):
        """Cancel task. If running, terminate its child process immediately."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.cancel_requested = True
            logger.info(f"طلب إلغاء المهمة: {task_id}، الحالة الحالية: {task.status}")
            
            if task.status == "pending":
                task.status = "cancelled"
                self.pending_task_ids.remove(task.id)
                self.ui_update_cb(task)
                
            elif (task.status in ["processing", "paused"]) and self.active_task and self.active_task.id == task_id:
                if task.status == "paused":
                    self.resume_task(task_id)
                
                if self.active_cancel_event:
                    self.active_cancel_event.set()
                
                if self.active_process and self.active_process.is_alive():
                    logger.info(f"إنهاء العملية الفرعية للقرص صراحة للمهمة: {task_id}")
                    self.active_process.terminate()
                    self.active_process.join(timeout=1.0)
                
                task.status = "cancelled"
                self.ui_update_cb(task)
                
                # Reset worker
                self.active_task = None
                self.active_process = None
                self.active_cancel_event = None
                self._check_queue()

    def pause_task(self, task_id: str):
        """Pause running task process using psutil."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task.status == "processing" and self.active_task and self.active_task.id == task_id:
                if self.active_process and self.active_process.is_alive():
                    try:
                        import psutil
                        proc = psutil.Process(self.active_process.pid)
                        proc.suspend()
                        task.status = "paused"
                        self.ui_update_cb(task)
                        logger.info(f"تم تعليق العملية الفرعية للمهمة: {task_id}")
                    except Exception as e:
                        logger.error(f"فشل تعليق العملية الفرعية للمهمة: {e}")

    def resume_task(self, task_id: str):
        """Resume suspended task process using psutil."""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task.status == "paused" and self.active_task and self.active_task.id == task_id:
                if self.active_process and self.active_process.is_alive():
                    try:
                        import psutil
                        proc = psutil.Process(self.active_process.pid)
                        proc.resume()
                        task.status = "processing"
                        self.ui_update_cb(task)
                        logger.info(f"تم استئناف العملية الفرعية للمهمة: {task_id}")
                    except Exception as e:
                        logger.error(f"فشل استئناف العملية الفرعية للمهمة: {e}")

    def _check_queue(self):
        """Start the next pending task if no active process is running."""
        if self.active_task is None and self.pending_task_ids:
            next_id = self.pending_task_ids.pop(0)
            task = self.tasks[next_id]
            self.active_task = task
            task.status = "processing"
            self.ui_update_cb(task)
            
            logger.info(f"إطلاق العملية الفرعية للمهمة: {task.id} الصيغة: {task.archive_path.suffix}")
            
            # Start process isolation
            self.active_cancel_event = multiprocessing.Event()
            self.active_process = multiprocessing.Process(
                target=_process_worker_entry,
                args=(
                    task.id,
                    task.task_type,
                    task.source_paths,
                    task.archive_path,
                    task.base_dir,
                    task.password,
                    task.compression_level,
                    self.process_queue,
                    self.active_cancel_event,
                    task.volume_size
                )
            )
            self.active_process.start()

    def process_gui_events(self):
        """
        Polls the inter-process queue and monitors active child processes.
        Must be called periodically on the main thread loop.
        """
        # 1. Read all progress updates from child process
        while True:
            try:
                # Read from multiprocessing queue without blocking
                msg = self.process_queue.get_nowait()
                t_id = msg['task_id']
                
                if t_id in self.tasks:
                    task = self.tasks[t_id]
                    task.status = msg['status']
                    
                    if 'current_file' in msg:
                        task.current_file = msg['current_file']
                        task.processed_bytes = msg['processed_bytes']
                        task.total_bytes = msg['total_bytes']
                        task.progress_percent = msg['progress_percent']
                        # Apply Exponential Moving Average (EMA) for speed smoothing
                        raw_speed = msg['speed']
                        if not hasattr(task, 'smoothed_speed') or task.smoothed_speed is None:
                            task.smoothed_speed = raw_speed
                        else:
                            # 0.7 * current_speed + 0.3 * smoothed_speed
                            task.smoothed_speed = (0.7 * raw_speed) + (0.3 * task.smoothed_speed)
                        
                        task.speed = task.smoothed_speed
                        
                        # Recalculate remaining time using smoothed speed
                        remaining_bytes = task.total_bytes - task.processed_bytes
                        if remaining_bytes <= 0:
                            task.remaining_time = 0.0
                        elif task.speed > 0:
                            task.remaining_time = remaining_bytes / task.speed
                        else:
                            task.remaining_time = -1.0
                    
                    if 'error_message' in msg:
                        task.error_message = msg['error_message']
                        
                    self.ui_update_cb(task)
            except Exception:
                # Queue empty
                break
                
        # 2. Check process status
        if self.active_process is not None:
            if not self.active_process.is_alive():
                # Process exited
                exit_code = self.active_process.exitcode
                task = self.active_task
                
                # Join process to avoid zombie state
                self.active_process.join()
                
                logger.info(f"انتهت العملية الفرعية للمهمة {task.id if task else 'Unknown'} برمز خروج: {exit_code}")
                
                # Check if task didn't update to finished state
                if task and task.status == "processing":
                    if exit_code == 0:
                        task.status = "completed"
                        task.progress_percent = 100.0
                    elif exit_code < 0: # Terminated
                        task.status = "cancelled"
                    else:
                        task.status = "failed"
                        task.error_message = f"انتهت العملية بشكل غير متوقع برمز: {exit_code}"
                    self.ui_update_cb(task)
                    
                # Reset active tracking
                self.active_task = None
                self.active_process = None
                
                # Trigger next queue item
                self._check_queue()

    def shutdown(self):
        """Force terminate any active background child processes on exit."""
        if self.active_task and self.active_task.status == "paused":
            try:
                self.resume_task(self.active_task.id)
            except Exception:
                pass
                
        if self.active_cancel_event:
            self.active_cancel_event.set()
            
        if self.active_process and self.active_process.is_alive():
            logger.info("إنهاء العملية الفرعية النشطة كجزء من إغلاق البرنامج.")
            try:
                self.active_process.terminate()
                self.active_process.join(timeout=1.0)
            except Exception:
                pass
