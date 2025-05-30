"""File management operations for Zenfolio downloads."""

import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from config.settings import Settings
from logs.logger import get_logger

logger = get_logger(__name__)


class FileManager:
    """Manages file operations for downloads."""
    
    def __init__(self, settings: Settings):
        """Initialize file manager.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
    
    def move_file(self, source: Path, destination: Path) -> bool:
        """Move a file from source to destination.
        
        Args:
            source: Source file path
            destination: Destination file path
            
        Returns:
            True if file was moved successfully
        """
        try:
            # Ensure destination directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # Move the file
            shutil.move(str(source), str(destination))
            logger.debug(f"Moved file: {source} -> {destination}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to move file {source} to {destination}: {e}")
            return False
    
    def copy_file(self, source: Path, destination: Path, preserve_metadata: bool = True) -> bool:
        """Copy a file from source to destination.
        
        Args:
            source: Source file path
            destination: Destination file path
            preserve_metadata: Whether to preserve file metadata
            
        Returns:
            True if file was copied successfully
        """
        try:
            # Ensure destination directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy the file
            if preserve_metadata:
                shutil.copy2(str(source), str(destination))
            else:
                shutil.copy(str(source), str(destination))
            
            logger.debug(f"Copied file: {source} -> {destination}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to copy file {source} to {destination}: {e}")
            return False
    
    def delete_file(self, file_path: Path) -> bool:
        """Delete a file.
        
        Args:
            file_path: Path to file to delete
            
        Returns:
            True if file was deleted successfully
        """
        try:
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Deleted file: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return False
    
    def get_file_info(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Get comprehensive information about a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Dictionary with file information or None if file doesn't exist
        """
        try:
            if not file_path.exists():
                return None
            
            stat = file_path.stat()
            
            return {
                'path': str(file_path),
                'name': file_path.name,
                'size': stat.st_size,
                'created': datetime.fromtimestamp(stat.st_ctime),
                'modified': datetime.fromtimestamp(stat.st_mtime),
                'accessed': datetime.fromtimestamp(stat.st_atime),
                'is_file': file_path.is_file(),
                'is_directory': file_path.is_dir(),
                'permissions': oct(stat.st_mode)[-3:],
                'extension': file_path.suffix.lower()
            }
            
        except Exception as e:
            logger.error(f"Failed to get file info for {file_path}: {e}")
            return None
    
    def set_file_timestamp(self, file_path: Path, timestamp: datetime) -> bool:
        """Set file modification and access timestamps.
        
        Args:
            file_path: Path to file
            timestamp: Timestamp to set
            
        Returns:
            True if timestamp was set successfully
        """
        try:
            unix_timestamp = timestamp.timestamp()
            os.utime(file_path, (unix_timestamp, unix_timestamp))
            logger.debug(f"Set timestamp for {file_path}: {timestamp}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set timestamp for {file_path}: {e}")
            return False
    
    def create_backup(self, file_path: Path, backup_suffix: str = ".bak") -> Optional[Path]:
        """Create a backup copy of a file.
        
        Args:
            file_path: Path to file to backup
            backup_suffix: Suffix to add to backup filename
            
        Returns:
            Path to backup file or None if backup failed
        """
        try:
            if not file_path.exists():
                logger.warning(f"Cannot backup non-existent file: {file_path}")
                return None
            
            backup_path = file_path.with_suffix(file_path.suffix + backup_suffix)
            
            # If backup already exists, add a number
            counter = 1
            while backup_path.exists():
                backup_path = file_path.with_suffix(f"{file_path.suffix}{backup_suffix}.{counter}")
                counter += 1
            
            if self.copy_file(file_path, backup_path):
                logger.debug(f"Created backup: {backup_path}")
                return backup_path
            else:
                return None
                
        except Exception as e:
            logger.error(f"Failed to create backup of {file_path}: {e}")
            return None
    
    def restore_backup(self, backup_path: Path, original_path: Optional[Path] = None) -> bool:
        """Restore a file from backup.
        
        Args:
            backup_path: Path to backup file
            original_path: Path to restore to (if different from backup location)
            
        Returns:
            True if file was restored successfully
        """
        try:
            if not backup_path.exists():
                logger.error(f"Backup file not found: {backup_path}")
                return False
            
            # Determine restore path
            if original_path is None:
                # Remove backup suffix to get original path
                original_path = backup_path
                for suffix in ['.bak', '.backup']:
                    if backup_path.name.endswith(suffix):
                        original_path = backup_path.with_name(
                            backup_path.name[:-len(suffix)]
                        )
                        break
            
            if self.copy_file(backup_path, original_path):
                logger.debug(f"Restored from backup: {backup_path} -> {original_path}")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Failed to restore backup {backup_path}: {e}")
            return False
    
    def verify_file_integrity(self, file_path: Path, expected_size: Optional[int] = None) -> bool:
        """Verify basic file integrity.
        
        Args:
            file_path: Path to file to verify
            expected_size: Expected file size in bytes
            
        Returns:
            True if file appears intact
        """
        try:
            if not file_path.exists():
                logger.warning(f"File does not exist: {file_path}")
                return False
            
            if not file_path.is_file():
                logger.warning(f"Path is not a file: {file_path}")
                return False
            
            # Check file size
            actual_size = file_path.stat().st_size
            if expected_size is not None and actual_size != expected_size:
                logger.warning(
                    f"File size mismatch for {file_path}: "
                    f"expected {expected_size}, got {actual_size}"
                )
                return False
            
            # Try to read the file to check for corruption
            try:
                with open(file_path, 'rb') as f:
                    # Read first and last chunks
                    f.read(1024)
                    if actual_size > 1024:
                        f.seek(-1024, 2)
                        f.read(1024)
            except Exception as e:
                logger.warning(f"File appears corrupted: {file_path} - {e}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to verify file integrity for {file_path}: {e}")
            return False
    
    def cleanup_temp_files(self, directory: Path, pattern: str = "*.tmp") -> int:
        """Clean up temporary files in a directory.
        
        Args:
            directory: Directory to clean
            pattern: File pattern to match (glob pattern)
            
        Returns:
            Number of files cleaned up
        """
        cleaned_count = 0
        
        try:
            for temp_file in directory.glob(pattern):
                if temp_file.is_file():
                    try:
                        temp_file.unlink()
                        cleaned_count += 1
                        logger.debug(f"Cleaned up temp file: {temp_file}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up {temp_file}: {e}")
            
            if cleaned_count > 0:
                logger.debug(f"Cleaned up {cleaned_count} temporary files")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error during temp file cleanup in {directory}: {e}")
            return cleaned_count
    
    def get_available_space(self, path: Path) -> Optional[int]:
        """Get available disk space for a path.
        
        Args:
            path: Path to check (file or directory)
            
        Returns:
            Available space in bytes or None if cannot determine
        """
        try:
            if path.is_file():
                path = path.parent
            
            stat = shutil.disk_usage(path)
            return stat.free
            
        except Exception as e:
            logger.warning(f"Cannot determine available space for {path}: {e}")
            return None
    
    def ensure_sufficient_space(self, path: Path, required_bytes: int, buffer_percent: float = 10.0) -> bool:
        """Ensure sufficient disk space is available.
        
        Args:
            path: Path to check
            required_bytes: Required space in bytes
            buffer_percent: Additional buffer percentage
            
        Returns:
            True if sufficient space is available
        """
        available = self.get_available_space(path)
        if available is None:
            # Cannot determine space, assume it's available
            return True
        
        required_with_buffer = required_bytes * (1 + buffer_percent / 100)
        
        if available < required_with_buffer:
            logger.warning(
                f"Insufficient disk space: {available:,} bytes available, "
                f"{required_with_buffer:,} bytes required (including {buffer_percent}% buffer)"
            )
            return False
        
        return True