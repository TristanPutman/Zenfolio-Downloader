"""Statistics tracking for download operations."""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from api.models import DownloadProgress
from logs.logger import get_logger

logger = get_logger(__name__)


@dataclass
class GalleryStats:
    """Statistics for a single gallery."""
    name: str
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    total_bytes: int = 0
    downloaded_bytes: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> float:
        """Get duration in seconds."""
        if not self.start_time:
            return 0.0
        end = self.end_time or datetime.now()
        duration = (end - self.start_time).total_seconds()
        # Ensure duration is never negative
        return max(0.0, duration)
    
    @property
    def completion_percentage(self) -> float:
        """Get completion percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.completed_files / self.total_files) * 100
    
    @property
    def download_speed_mbps(self) -> float:
        """Get download speed in MB/s."""
        duration = self.duration_seconds
        if duration == 0:
            return 0.0
        return (self.downloaded_bytes / (1024 * 1024)) / duration


@dataclass
class OverallStats:
    """Overall download statistics."""
    total_galleries: int = 0
    completed_galleries: int = 0
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    total_bytes: int = 0
    downloaded_bytes: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    gallery_stats: Dict[str, GalleryStats] = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> float:
        """Get total duration in seconds."""
        if not self.start_time:
            return 0.0
        end = self.end_time or datetime.now()
        duration = (end - self.start_time).total_seconds()
        # Ensure duration is never negative
        return max(0.0, duration)
    
    @property
    def completion_percentage(self) -> float:
        """Get overall completion percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.completed_files / self.total_files) * 100
    
    @property
    def download_speed_mbps(self) -> float:
        """Get overall download speed in MB/s."""
        duration = self.duration_seconds
        if duration == 0:
            return 0.0
        return (self.downloaded_bytes / (1024 * 1024)) / duration


class StatisticsTracker:
    """Tracks comprehensive download statistics."""
    
    def __init__(self):
        """Initialize statistics tracker."""
        self.overall_stats = OverallStats()
        self.current_gallery: Optional[str] = None
        self._last_update_time = time.time()
    
    def start_session(self) -> None:
        """Start a new download session."""
        self.overall_stats.start_time = datetime.now()
        logger.debug("Statistics tracking started")
    
    def end_session(self) -> None:
        """End the current download session."""
        self.overall_stats.end_time = datetime.now()
        if self.current_gallery:
            self.end_gallery(self.current_gallery)
        logger.debug("Statistics tracking ended")
    
    def start_gallery(self, gallery_name: str, total_files: int, total_bytes: int = 0) -> None:
        """Start tracking a new gallery.
        
        Args:
            gallery_name: Name of the gallery
            total_files: Total number of files in gallery
            total_bytes: Total bytes to download (if known)
        """
        if self.current_gallery:
            self.end_gallery(self.current_gallery)
        
        self.current_gallery = gallery_name
        self.overall_stats.gallery_stats[gallery_name] = GalleryStats(
            name=gallery_name,
            total_files=total_files,
            total_bytes=total_bytes,
            start_time=datetime.now()
        )
        
        # Update overall stats
        self.overall_stats.total_galleries += 1
        self.overall_stats.total_files += total_files
        self.overall_stats.total_bytes += total_bytes
        
        logger.debug(f"Started tracking gallery: {gallery_name} ({total_files} files)")
    
    def end_gallery(self, gallery_name: str) -> None:
        """End tracking for a gallery.
        
        Args:
            gallery_name: Name of the gallery
        """
        if gallery_name in self.overall_stats.gallery_stats:
            gallery_stats = self.overall_stats.gallery_stats[gallery_name]
            gallery_stats.end_time = datetime.now()
            
            # Mark gallery as completed
            self.overall_stats.completed_galleries += 1
            
            logger.debug(
                f"Completed gallery: {gallery_name} - "
                f"{gallery_stats.completed_files}/{gallery_stats.total_files} files "
                f"in {gallery_stats.duration_seconds:.2f}s"
            )
        
        if self.current_gallery == gallery_name:
            self.current_gallery = None
    
    def record_file_completed(self, gallery_name: str, file_size: int = 0) -> None:
        """Record a completed file download.
        
        Args:
            gallery_name: Name of the gallery
            file_size: Size of downloaded file in bytes
        """
        # Update gallery stats
        if gallery_name in self.overall_stats.gallery_stats:
            gallery_stats = self.overall_stats.gallery_stats[gallery_name]
            gallery_stats.completed_files += 1
            gallery_stats.downloaded_bytes += file_size
        
        # Update overall stats
        self.overall_stats.completed_files += 1
        self.overall_stats.downloaded_bytes += file_size
    
    def record_file_failed(self, gallery_name: str) -> None:
        """Record a failed file download.
        
        Args:
            gallery_name: Name of the gallery
        """
        # Update gallery stats
        if gallery_name in self.overall_stats.gallery_stats:
            gallery_stats = self.overall_stats.gallery_stats[gallery_name]
            gallery_stats.failed_files += 1
        
        # Update overall stats
        self.overall_stats.failed_files += 1
    
    def record_file_skipped(self, gallery_name: str, file_size: int = 0) -> None:
        """Record a skipped file.
        
        Args:
            gallery_name: Name of the gallery
            file_size: Size of skipped file in bytes
        """
        # Update gallery stats
        if gallery_name in self.overall_stats.gallery_stats:
            gallery_stats = self.overall_stats.gallery_stats[gallery_name]
            gallery_stats.skipped_files += 1
            # Don't count skipped files in downloaded_bytes since they weren't downloaded this session

        # Update overall stats
        self.overall_stats.skipped_files += 1
        # Don't count skipped files in downloaded_bytes since they weren't downloaded this session
    
    def get_current_progress(self) -> DownloadProgress:
        """Get current download progress.
        
        Returns:
            Current download progress
        """
        return DownloadProgress(
            total_files=self.overall_stats.total_files,
            completed_files=self.overall_stats.completed_files,
            failed_files=self.overall_stats.failed_files,
            skipped_files=self.overall_stats.skipped_files,
            total_bytes=self.overall_stats.total_bytes,
            downloaded_bytes=self.overall_stats.downloaded_bytes,
            current_file=None,  # Would be set by download manager
            start_time=self.overall_stats.start_time
        )
    
    def get_gallery_stats(self, gallery_name: str) -> Optional[GalleryStats]:
        """Get statistics for a specific gallery.
        
        Args:
            gallery_name: Name of the gallery
            
        Returns:
            Gallery statistics or None if not found
        """
        return self.overall_stats.gallery_stats.get(gallery_name)
    
    def get_summary_report(self) -> Dict[str, Any]:
        """Get a comprehensive summary report.
        
        Returns:
            Dictionary with summary statistics
        """
        duration = self.overall_stats.duration_seconds
        
        return {
            'session': {
                'start_time': self.overall_stats.start_time.isoformat() if self.overall_stats.start_time else None,
                'end_time': self.overall_stats.end_time.isoformat() if self.overall_stats.end_time else None,
                'duration_seconds': duration,
                'duration_formatted': self._format_duration(duration)
            },
            'galleries': {
                'total': self.overall_stats.total_galleries,
                'completed': self.overall_stats.completed_galleries,
                'in_progress': len([g for g in self.overall_stats.gallery_stats.values() if not g.end_time])
            },
            'files': {
                'total': self.overall_stats.total_files,
                'completed': self.overall_stats.completed_files,
                'failed': self.overall_stats.failed_files,
                'previously_downloaded': self.overall_stats.skipped_files,
                'completion_percentage': self.overall_stats.completion_percentage
            },
            'data': {
                'total_bytes': self.overall_stats.total_bytes,
                'downloaded_bytes': self.overall_stats.downloaded_bytes,
                'total_mb': self.overall_stats.total_bytes / (1024 * 1024),
                'downloaded_mb': self.overall_stats.downloaded_bytes / (1024 * 1024),
                'download_speed_mbps': self.overall_stats.download_speed_mbps
            },
            'performance': {
                'average_speed_mbps': self.overall_stats.download_speed_mbps,
                'files_per_second': self.overall_stats.completed_files / duration if duration > 0 else 0,
                'estimated_time_remaining': self._estimate_time_remaining()
            }
        }
    
    def get_gallery_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all galleries.
        
        Returns:
            List of gallery summaries
        """
        summaries = []
        
        for gallery_stats in self.overall_stats.gallery_stats.values():
            summaries.append({
                'name': gallery_stats.name,
                'total_files': gallery_stats.total_files,
                'completed_files': gallery_stats.completed_files,
                'failed_files': gallery_stats.failed_files,
                'skipped_files': gallery_stats.skipped_files,
                'total_mb': gallery_stats.total_bytes / (1024 * 1024),
                'downloaded_mb': gallery_stats.downloaded_bytes / (1024 * 1024),
                'duration_seconds': gallery_stats.duration_seconds,
                'completion_percentage': gallery_stats.completion_percentage,
                'download_speed_mbps': gallery_stats.download_speed_mbps,
                'status': 'completed' if gallery_stats.end_time else 'in_progress'
            })
        
        return summaries
    
    def get_final_summary(self) -> Dict[str, Any]:
        """Get final summary for completed session.
        
        Returns:
            Final summary statistics
        """
        if not self.overall_stats.end_time:
            self.end_session()
        
        summary = self.get_summary_report()
        summary['gallery_details'] = self.get_gallery_summary()
        
        return summary
    
    def get_human_readable_summary(self) -> str:
        """Get a human-readable summary of the download session.
        
        Returns:
            Formatted string with key statistics
        """
        if not self.overall_stats.end_time:
            self.end_session()
        
        duration = self.overall_stats.duration_seconds
        duration_formatted = self._format_duration(duration)
        
        # Format file sizes in MB/GB
        downloaded_mb = self.overall_stats.downloaded_bytes / (1024 * 1024)
        
        # Calculate the expected size of files that needed to be downloaded
        # (excluding files that were already present)
        files_to_download = self.overall_stats.completed_files + self.overall_stats.failed_files
        if files_to_download > 0 and self.overall_stats.total_files > 0:
            # Estimate expected download size based on files that actually needed downloading
            expected_download_mb = (self.overall_stats.total_bytes / (1024 * 1024)) * (files_to_download / self.overall_stats.total_files)
        else:
            expected_download_mb = self.overall_stats.total_bytes / (1024 * 1024)
        
        if downloaded_mb >= 1024:
            downloaded_size = f"{downloaded_mb / 1024:.1f} GB"
        else:
            downloaded_size = f"{downloaded_mb:.1f} MB"
            
        if expected_download_mb >= 1024:
            expected_size = f"{expected_download_mb / 1024:.1f} GB"
        else:
            expected_size = f"{expected_download_mb:.1f} MB"
        
        # Create summary lines
        lines = [
            f"📊 Download Session Summary",
            f"   Galleries:     {self.overall_stats.completed_galleries:,} completed of {self.overall_stats.total_galleries:,} total",
            f"   Files:         {self.overall_stats.completed_files:,} downloaded, {self.overall_stats.skipped_files:,} previously downloaded, {self.overall_stats.failed_files:,} failed",
            f"   Total Files:   {self.overall_stats.total_files:,}",
            f"   Data Size:     {downloaded_size} downloaded (expected ~{expected_size})",
            f"   Duration:      {duration_formatted}",
            f"   Speed:         {self.overall_stats.download_speed_mbps:.1f} MB/s average"
        ]
        
        return "\n".join(lines)
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted duration string
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"
    
    def _estimate_time_remaining(self) -> Optional[str]:
        """Estimate time remaining for download.
        
        Returns:
            Formatted time remaining or None if cannot estimate
        """
        if self.overall_stats.completed_files == 0:
            return None
        
        remaining_files = self.overall_stats.total_files - self.overall_stats.completed_files
        if remaining_files <= 0:
            return "0s"
        
        duration = self.overall_stats.duration_seconds
        if duration <= 0:
            return None
        
        files_per_second = self.overall_stats.completed_files / duration
        if files_per_second <= 0:
            return None
        
        estimated_seconds = remaining_files / files_per_second
        return self._format_duration(estimated_seconds)