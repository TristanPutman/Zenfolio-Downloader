"""Checkpoint management for resumable downloads."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from datetime import datetime
from api.models import DownloadInfo, DownloadProgress
from config.settings import Settings
from logs.logger import get_logger, log_checkpoint_save, log_checkpoint_load

logger = get_logger(__name__)


class CheckpointData:
    """Container for checkpoint data."""
    
    def __init__(self):
        self.completed_files: Set[str] = set()
        self.failed_files: Set[str] = set()
        self.skipped_files: Set[str] = set()
        self.gallery_progress: Dict[str, Dict[str, Any]] = {}
        self.total_progress: Dict[str, Any] = {}
        self.session_start_time: Optional[datetime] = None
        self.last_updated: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert checkpoint data to dictionary for serialization."""
        return {
            'completed_files': list(self.completed_files),
            'failed_files': list(self.failed_files),
            'skipped_files': list(self.skipped_files),
            'gallery_progress': self.gallery_progress,
            'total_progress': self.total_progress,
            'session_start_time': self.session_start_time.isoformat() if self.session_start_time else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'version': '1.0'
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CheckpointData':
        """Create checkpoint data from dictionary."""
        checkpoint = cls()
        checkpoint.completed_files = set(data.get('completed_files', []))
        checkpoint.failed_files = set(data.get('failed_files', []))
        checkpoint.skipped_files = set(data.get('skipped_files', []))
        checkpoint.gallery_progress = data.get('gallery_progress', {})
        checkpoint.total_progress = data.get('total_progress', {})
        
        # Parse timestamps
        if data.get('session_start_time'):
            checkpoint.session_start_time = datetime.fromisoformat(data['session_start_time'])
        if data.get('last_updated'):
            checkpoint.last_updated = datetime.fromisoformat(data['last_updated'])
        
        return checkpoint


class CheckpointManager:
    """Manages download checkpoints for resume functionality."""
    
    def __init__(self, settings: Settings, checkpoint_file: Optional[str] = None):
        """Initialize checkpoint manager.
        
        Args:
            settings: Application settings
            checkpoint_file: Optional custom checkpoint file path
        """
        self.settings = settings
        self.checkpoint_file = Path(checkpoint_file or ".zenfolio_checkpoint.json")
        self.checkpoint_data = CheckpointData()
        self._auto_save_enabled = True
        self._save_interval = 30  # Save every 30 seconds
        self._last_save_time: Optional[datetime] = None
    
    def load_checkpoint(self) -> bool:
        """Load checkpoint from file.
        
        Returns:
            True if checkpoint was loaded successfully
        """
        if not self.checkpoint_file.exists():
            logger.debug("No checkpoint file found")
            return False
        
        try:
            with open(self.checkpoint_file, 'r') as f:
                data = json.load(f)
            
            self.checkpoint_data = CheckpointData.from_dict(data)
            log_checkpoint_load(str(self.checkpoint_file))
            
            # Log resume information
            completed_count = len(self.checkpoint_data.completed_files)
            failed_count = len(self.checkpoint_data.failed_files)
            skipped_count = len(self.checkpoint_data.skipped_files)
            
            # Use print instead of logger to avoid module path in output
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"{timestamp} | Resuming from checkpoint: {completed_count} completed, {failed_count} failed, {skipped_count} previously downloaded")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return False
    
    def save_checkpoint(self, force: bool = False) -> bool:
        """Save checkpoint to file.
        
        Args:
            force: Force save even if auto-save interval hasn't elapsed
            
        Returns:
            True if checkpoint was saved successfully
        """
        # Check if we should save based on interval
        if not force and self._last_save_time:
            elapsed = (datetime.now() - self._last_save_time).total_seconds()
            if elapsed < self._save_interval:
                return True
        
        try:
            # Update timestamp
            self.checkpoint_data.last_updated = datetime.now()
            
            # Ensure checkpoint directory exists
            self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Write checkpoint data
            with open(self.checkpoint_file, 'w') as f:
                json.dump(self.checkpoint_data.to_dict(), f, indent=2)
            
            # Set restrictive permissions
            self.checkpoint_file.chmod(0o600)
            
            self._last_save_time = datetime.now()
            log_checkpoint_save(str(self.checkpoint_file))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False
    
    def clear_checkpoint(self) -> bool:
        """Clear checkpoint file and data.
        
        Returns:
            True if checkpoint was cleared successfully
        """
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
            
            self.checkpoint_data = CheckpointData()
            logger.debug("Checkpoint cleared")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear checkpoint: {e}")
            return False
    
    def mark_file_completed(self, file_path: str) -> None:
        """Mark a file as completed.
        
        Args:
            file_path: Path of completed file
        """
        self.checkpoint_data.completed_files.add(file_path)
        self.checkpoint_data.failed_files.discard(file_path)
        
        if self._auto_save_enabled:
            self.save_checkpoint()
    
    def mark_file_failed(self, file_path: str) -> None:
        """Mark a file as failed.
        
        Args:
            file_path: Path of failed file
        """
        self.checkpoint_data.failed_files.add(file_path)
        self.checkpoint_data.completed_files.discard(file_path)
        
        if self._auto_save_enabled:
            self.save_checkpoint()
    
    def mark_file_skipped(self, file_path: str) -> None:
        """Mark a file as skipped.
        
        Args:
            file_path: Path of skipped file
        """
        self.checkpoint_data.skipped_files.add(file_path)
        
        if self._auto_save_enabled:
            self.save_checkpoint()
    
    def is_file_completed(self, file_path: str) -> bool:
        """Check if a file has been completed.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file is marked as completed
        """
        return file_path in self.checkpoint_data.completed_files
    
    def is_file_failed(self, file_path: str) -> bool:
        """Check if a file has failed.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file is marked as failed
        """
        return file_path in self.checkpoint_data.failed_files
    
    def is_file_skipped(self, file_path: str) -> bool:
        """Check if a file was skipped.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file is marked as skipped
        """
        return file_path in self.checkpoint_data.skipped_files
    
    def should_download_file(self, file_path: str) -> bool:
        """Determine if a file should be downloaded based on checkpoint.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file should be downloaded
        """
        return not (
            self.is_file_completed(file_path) or 
            self.is_file_skipped(file_path)
        )
    
    def update_gallery_progress(self, gallery_name: str, progress_data: Dict[str, Any]) -> None:
        """Update progress for a specific gallery.
        
        Args:
            gallery_name: Name of the gallery
            progress_data: Progress information
        """
        self.checkpoint_data.gallery_progress[gallery_name] = {
            **progress_data,
            'last_updated': datetime.now().isoformat()
        }
        
        if self._auto_save_enabled:
            self.save_checkpoint()
    
    def update_total_progress(self, progress: DownloadProgress) -> None:
        """Update total download progress.
        
        Args:
            progress: Overall download progress
        """
        self.checkpoint_data.total_progress = {
            'total_files': progress.total_files,
            'completed_files': progress.completed_files,
            'failed_files': progress.failed_files,
            'skipped_files': progress.skipped_files,
            'total_bytes': progress.total_bytes,
            'downloaded_bytes': progress.downloaded_bytes,
            'completion_percentage': progress.completion_percentage,
            'last_updated': datetime.now().isoformat()
        }
        
        if self._auto_save_enabled:
            self.save_checkpoint()
    
    def get_resume_info(self) -> Dict[str, Any]:
        """Get information about what can be resumed.
        
        Returns:
            Dictionary with resume information
        """
        return {
            'has_checkpoint': len(self.checkpoint_data.completed_files) > 0,
            'completed_files': len(self.checkpoint_data.completed_files),
            'failed_files': len(self.checkpoint_data.failed_files),
            'skipped_files': len(self.checkpoint_data.skipped_files),
            'galleries_in_progress': len(self.checkpoint_data.gallery_progress),
            'session_start_time': (
                self.checkpoint_data.session_start_time.isoformat() 
                if self.checkpoint_data.session_start_time else None
            ),
            'last_updated': (
                self.checkpoint_data.last_updated.isoformat() 
                if self.checkpoint_data.last_updated else None
            )
        }
    
    def filter_downloads_for_resume(self, downloads: List[DownloadInfo]) -> List[DownloadInfo]:
        """Filter download list to only include files that need to be downloaded.
        
        Args:
            downloads: List of all downloads
            
        Returns:
            Filtered list of downloads that need to be processed
        """
        filtered = []
        
        for download in downloads:
            if self.should_download_file(download.local_path):
                filtered.append(download)
            else:
                logger.debug(f"Skipping already processed file: {download.local_path}")
        
        logger.debug(
            f"Resume filter: {len(filtered)} files to download "
            f"out of {len(downloads)} total files"
        )
        
        return filtered
    
    def start_session(self) -> None:
        """Mark the start of a new download session."""
        if not self.checkpoint_data.session_start_time:
            self.checkpoint_data.session_start_time = datetime.now()
            self.save_checkpoint(force=True)
    
    def set_auto_save(self, enabled: bool) -> None:
        """Enable or disable automatic checkpoint saving.
        
        Args:
            enabled: Whether to enable auto-save
        """
        self._auto_save_enabled = enabled
        logger.debug(f"Auto-save {'enabled' if enabled else 'disabled'}")