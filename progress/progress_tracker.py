"""Progress tracking for Zenfolio downloads."""

import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from logs.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ProgressInfo:
    """Information about download progress."""
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    total_bytes: int = 0
    downloaded_bytes: int = 0
    current_file: Optional[str] = None
    start_time: Optional[datetime] = None
    
    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.completed_files / self.total_files) * 100
    
    @property
    def bytes_percentage(self) -> float:
        """Calculate bytes completion percentage."""
        if self.total_bytes == 0:
            return 0.0
        return (self.downloaded_bytes / self.total_bytes) * 100
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        if not self.start_time:
            return 0.0
        duration = (datetime.now() - self.start_time).total_seconds()
        # Ensure duration is never negative
        return max(0.0, duration)
    
    @property
    def download_speed_mbps(self) -> float:
        """Calculate download speed in MB/s."""
        elapsed = self.elapsed_time
        if elapsed == 0:
            return 0.0
        return (self.downloaded_bytes / (1024 * 1024)) / elapsed


class ProgressTracker:
    """Tracks download progress with real-time updates."""
    
    def __init__(self):
        """Initialize progress tracker."""
        self.progress = ProgressInfo()
        self.gallery_progress: Dict[str, ProgressInfo] = {}
        self.is_active = False
        
    def start_session(self, total_files: int = 0, total_bytes: int = 0) -> None:
        """Start a new progress tracking session.
        
        Args:
            total_files: Total number of files to download
            total_bytes: Total bytes to download
        """
        self.progress = ProgressInfo(
            total_files=total_files,
            total_bytes=total_bytes,
            start_time=datetime.now()
        )
        self.gallery_progress.clear()
        self.is_active = True
        
        logger.debug(f"Progress tracking started: {total_files} files, {total_bytes:,} bytes")
    
    def end_session(self) -> None:
        """End the current progress tracking session."""
        self.is_active = False
        elapsed = self.progress.elapsed_time
        
        logger.debug(
            f"Progress tracking ended: {self.progress.completed_files}/{self.progress.total_files} files "
            f"completed in {elapsed:.2f}s"
        )
    
    def start_gallery(self, gallery_name: str, total_files: int, total_bytes: int) -> None:
        """Start tracking progress for a specific gallery.
        
        Args:
            gallery_name: Name of the gallery
            total_files: Total files in the gallery
            total_bytes: Total bytes in the gallery
        """
        self.gallery_progress[gallery_name] = ProgressInfo(
            total_files=total_files,
            total_bytes=total_bytes,
            start_time=datetime.now()
        )
        
        logger.debug(f"Started tracking gallery: {gallery_name} ({total_files} files)")
    
    def end_gallery(self, gallery_name: str) -> None:
        """End tracking for a specific gallery.
        
        Args:
            gallery_name: Name of the gallery
        """
        if gallery_name in self.gallery_progress:
            gallery_info = self.gallery_progress[gallery_name]
            elapsed = gallery_info.elapsed_time
            
            logger.debug(
                f"Finished tracking gallery: {gallery_name} "
                f"({gallery_info.completed_files}/{gallery_info.total_files} files in {elapsed:.2f}s)"
            )
    
    def update_file_progress(self, gallery_name: str, file_path: str, bytes_downloaded: int) -> None:
        """Update progress for a file being downloaded.
        
        Args:
            gallery_name: Name of the gallery
            file_path: Path of the file being downloaded
            bytes_downloaded: Number of bytes downloaded for this file
        """
        self.progress.current_file = file_path
        self.progress.downloaded_bytes += bytes_downloaded
        
        if gallery_name in self.gallery_progress:
            self.gallery_progress[gallery_name].current_file = file_path
            self.gallery_progress[gallery_name].downloaded_bytes += bytes_downloaded
    
    def mark_file_completed(self, gallery_name: str, file_size: int) -> None:
        """Mark a file as completed.
        
        Args:
            gallery_name: Name of the gallery
            file_size: Size of the completed file
        """
        self.progress.completed_files += 1
        
        if gallery_name in self.gallery_progress:
            self.gallery_progress[gallery_name].completed_files += 1
    
    def mark_file_failed(self, gallery_name: str) -> None:
        """Mark a file as failed.
        
        Args:
            gallery_name: Name of the gallery
        """
        self.progress.failed_files += 1
        
        if gallery_name in self.gallery_progress:
            self.gallery_progress[gallery_name].failed_files += 1
    
    def mark_file_skipped(self, gallery_name: str, file_size: int) -> None:
        """Mark a file as skipped.
        
        Args:
            gallery_name: Name of the gallery
            file_size: Size of the skipped file
        """
        self.progress.skipped_files += 1
        
        if gallery_name in self.gallery_progress:
            self.gallery_progress[gallery_name].skipped_files += 1
    
    def get_overall_progress(self) -> ProgressInfo:
        """Get overall progress information.
        
        Returns:
            Overall progress information
        """
        return self.progress
    
    def get_gallery_progress(self, gallery_name: str) -> Optional[ProgressInfo]:
        """Get progress information for a specific gallery.
        
        Args:
            gallery_name: Name of the gallery
            
        Returns:
            Gallery progress information or None if not found
        """
        return self.gallery_progress.get(gallery_name)
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """Get a summary of all progress information.
        
        Returns:
            Dictionary containing progress summary
        """
        return {
            'overall': {
                'total_files': self.progress.total_files,
                'completed_files': self.progress.completed_files,
                'failed_files': self.progress.failed_files,
                'skipped_files': self.progress.skipped_files,
                'completion_percentage': self.progress.completion_percentage,
                'bytes_percentage': self.progress.bytes_percentage,
                'download_speed_mbps': self.progress.download_speed_mbps,
                'elapsed_time': self.progress.elapsed_time,
                'current_file': self.progress.current_file
            },
            'galleries': {
                name: {
                    'total_files': info.total_files,
                    'completed_files': info.completed_files,
                    'failed_files': info.failed_files,
                    'skipped_files': info.skipped_files,
                    'completion_percentage': info.completion_percentage,
                    'bytes_percentage': info.bytes_percentage,
                    'download_speed_mbps': info.download_speed_mbps,
                    'elapsed_time': info.elapsed_time
                }
                for name, info in self.gallery_progress.items()
            },
            'is_active': self.is_active
        }
    
    def estimate_time_remaining(self) -> Optional[float]:
        """Estimate time remaining based on current progress.
        
        Returns:
            Estimated time remaining in seconds, or None if cannot estimate
        """
        if not self.is_active or self.progress.completed_files == 0:
            return None
        
        elapsed = self.progress.elapsed_time
        if elapsed == 0:
            return None
        
        files_per_second = self.progress.completed_files / elapsed
        remaining_files = self.progress.total_files - self.progress.completed_files
        
        if files_per_second == 0:
            return None
        
        return remaining_files / files_per_second
    
    def format_progress_string(self) -> str:
        """Format progress as a human-readable string.
        
        Returns:
            Formatted progress string
        """
        if not self.is_active:
            return "Progress tracking not active"
        
        completed = self.progress.completed_files
        total = self.progress.total_files
        percentage = self.progress.completion_percentage
        speed = self.progress.download_speed_mbps
        
        progress_str = f"{completed}/{total} files ({percentage:.1f}%)"
        
        if speed > 0:
            progress_str += f" at {speed:.2f} MB/s"
        
        time_remaining = self.estimate_time_remaining()
        if time_remaining:
            if time_remaining < 60:
                progress_str += f" - {time_remaining:.0f}s remaining"
            elif time_remaining < 3600:
                progress_str += f" - {time_remaining/60:.1f}m remaining"
            else:
                progress_str += f" - {time_remaining/3600:.1f}h remaining"
        
        return progress_str