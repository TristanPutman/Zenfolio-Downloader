"""Directory management for Zenfolio downloads."""

import os
import re
from pathlib import Path
from typing import Optional
from config.settings import Settings
from logs.logger import get_logger

logger = get_logger(__name__)


class DirectoryManager:
    """Manages directory operations for downloads."""
    
    def __init__(self, settings: Settings):
        """Initialize directory manager.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        
        # Characters that are invalid in filenames on various systems
        self.invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
        self.reserved_names = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }
    
    def sanitize_filename(self, filename: str, replacement: str = "_") -> str:
        """Sanitize a filename to be safe for the filesystem.
        
        Args:
            filename: Original filename
            replacement: Character to replace invalid characters with
            
        Returns:
            Sanitized filename
        """
        if not filename:
            return "unnamed"
        
        # Replace invalid characters
        sanitized = re.sub(self.invalid_chars, replacement, filename)
        
        # Remove leading/trailing dots and spaces
        sanitized = sanitized.strip('. ')
        
        # Handle reserved names
        name_part = sanitized.split('.')[0].upper()
        if name_part in self.reserved_names:
            sanitized = f"{replacement}{sanitized}"
        
        # Ensure filename isn't too long (255 chars is typical limit)
        if len(sanitized) > 255:
            name, ext = os.path.splitext(sanitized)
            max_name_length = 255 - len(ext)
            sanitized = name[:max_name_length] + ext
        
        # Ensure we have a valid filename
        if not sanitized or sanitized in ['.', '..']:
            sanitized = "unnamed"
        
        logger.debug(f"Sanitized filename: '{filename}' -> '{sanitized}'")
        return sanitized
    
    def ensure_directory(self, directory_path: Path) -> bool:
        """Ensure a directory exists, creating it if necessary.
        
        Args:
            directory_path: Path to directory
            
        Returns:
            True if directory exists or was created successfully
        """
        try:
            directory_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Directory ensured: {directory_path}")
            return True
            
        except PermissionError:
            logger.error(f"Permission denied creating directory: {directory_path}")
            return False
        except OSError as e:
            logger.error(f"Failed to create directory {directory_path}: {e}")
            return False
    
    def get_safe_path(self, base_path: Path, relative_path: str) -> Path:
        """Get a safe path by sanitizing components.
        
        Args:
            base_path: Base directory path
            relative_path: Relative path to sanitize
            
        Returns:
            Safe combined path
        """
        # Split the relative path into components
        components = relative_path.split('/')
        
        # Sanitize each component
        safe_components = [self.sanitize_filename(comp) for comp in components if comp]
        
        # Build the safe path
        safe_path = base_path
        for component in safe_components:
            safe_path = safe_path / component
        
        return safe_path
    
    def create_gallery_directory(self, base_path: Path, gallery_name: str) -> Path:
        """Create a directory for a gallery.
        
        Args:
            base_path: Base output directory
            gallery_name: Name of the gallery
            
        Returns:
            Path to created gallery directory
        """
        safe_gallery_name = self.sanitize_filename(gallery_name)
        gallery_path = base_path / safe_gallery_name
        
        if self.ensure_directory(gallery_path):
            logger.debug(f"Created gallery directory: {gallery_path}")
            return gallery_path
        else:
            raise OSError(f"Failed to create gallery directory: {gallery_path}")
    
    def get_unique_filename(self, file_path: Path) -> Path:
        """Get a unique filename if the original already exists.
        
        Args:
            file_path: Original file path
            
        Returns:
            Unique file path
        """
        if not file_path.exists():
            return file_path
        
        base_path = file_path.parent
        stem = file_path.stem
        suffix = file_path.suffix
        
        counter = 1
        while True:
            new_name = f"{stem}_{counter:03d}{suffix}"
            new_path = base_path / new_name
            
            if not new_path.exists():
                logger.debug(f"Generated unique filename: {new_path}")
                return new_path
            
            counter += 1
            
            # Prevent infinite loop
            if counter > 9999:
                raise ValueError(f"Cannot generate unique filename for: {file_path}")
    
    def check_disk_space(self, directory: Path, required_bytes: int) -> bool:
        """Check if there's enough disk space for a download.
        
        Args:
            directory: Directory to check
            required_bytes: Required space in bytes
            
        Returns:
            True if enough space is available
        """
        try:
            stat = os.statvfs(directory)
            available_bytes = stat.f_bavail * stat.f_frsize
            
            # Add 10% buffer
            required_with_buffer = required_bytes * 1.1
            
            if available_bytes < required_with_buffer:
                logger.warning(
                    f"Insufficient disk space: {available_bytes:,} bytes available, "
                    f"{required_with_buffer:,} bytes required"
                )
                return False
            
            return True
            
        except (OSError, AttributeError):
            # If we can't check disk space, assume it's available
            logger.warning("Unable to check disk space")
            return True
    
    def cleanup_empty_directories(self, base_path: Path) -> int:
        """Remove empty directories recursively.
        
        Args:
            base_path: Base path to start cleanup from
            
        Returns:
            Number of directories removed
        """
        removed_count = 0
        
        try:
            # Walk the directory tree bottom-up
            for root, dirs, files in os.walk(base_path, topdown=False):
                root_path = Path(root)
                
                # Skip if this is the base path
                if root_path == base_path:
                    continue
                
                # Check if directory is empty
                try:
                    if not any(root_path.iterdir()):
                        root_path.rmdir()
                        removed_count += 1
                        logger.debug(f"Removed empty directory: {root_path}")
                except OSError:
                    # Directory not empty or permission error
                    pass
            
            if removed_count > 0:
                logger.debug(f"Cleaned up {removed_count} empty directories")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error during directory cleanup: {e}")
            return removed_count
    
    def get_directory_size(self, directory: Path) -> int:
        """Get total size of a directory and its contents.
        
        Args:
            directory: Directory to measure
            
        Returns:
            Total size in bytes
        """
        total_size = 0
        
        try:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_path = Path(root) / file
                    try:
                        total_size += file_path.stat().st_size
                    except (OSError, FileNotFoundError):
                        # File might have been deleted or is inaccessible
                        pass
            
            return total_size
            
        except Exception as e:
            logger.error(f"Error calculating directory size for {directory}: {e}")
            return 0
    
    def create_directory_structure(self, base_path: Path, structure: dict) -> bool:
        """Create a directory structure from a nested dictionary.
        
        Args:
            base_path: Base path to create structure under
            structure: Dictionary representing directory structure
            
        Returns:
            True if structure was created successfully
        """
        try:
            for name, content in structure.items():
                safe_name = self.sanitize_filename(name)
                current_path = base_path / safe_name
                
                if isinstance(content, dict):
                    # This is a directory
                    if self.ensure_directory(current_path):
                        # Recursively create subdirectories
                        if not self.create_directory_structure(current_path, content):
                            return False
                    else:
                        return False
                # If content is not a dict, we assume it's a file placeholder
                # and don't create anything (files will be created during download)
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating directory structure: {e}")
            return False
    
    def validate_path_length(self, file_path: Path) -> bool:
        """Validate that a file path isn't too long for the filesystem.
        
        Args:
            file_path: File path to validate
            
        Returns:
            True if path length is acceptable
        """
        # Most filesystems have a 260 character limit for full paths
        max_path_length = 260
        
        path_str = str(file_path.resolve())
        if len(path_str) > max_path_length:
            logger.warning(f"Path too long ({len(path_str)} chars): {path_str}")
            return False
        
        return True
    
    def get_relative_path(self, file_path: Path, base_path: Path) -> Path:
        """Get relative path from base path to file path.
        
        Args:
            file_path: Target file path
            base_path: Base directory path
            
        Returns:
            Relative path
        """
        try:
            return file_path.relative_to(base_path)
        except ValueError:
            # Paths are not related, return the file path as-is
            return file_path