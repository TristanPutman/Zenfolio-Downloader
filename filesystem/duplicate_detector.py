"""Duplicate detection for downloaded files."""

import os
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from config.settings import Settings
from logs.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FileInfo:
    """Information about a file for duplicate detection."""
    path: Path
    size: int
    hash_sha256: Optional[str] = None
    modified_time: float = 0.0
    
    def __post_init__(self):
        """Calculate hash and modified time if not provided."""
        if self.path.exists():
            stat = self.path.stat()
            self.size = stat.st_size
            self.modified_time = stat.st_mtime


@dataclass
class DuplicateGroup:
    """Group of duplicate files."""
    files: List[FileInfo]
    total_size: int
    
    @property
    def duplicate_count(self) -> int:
        """Number of duplicate files (excluding the original)."""
        return len(self.files) - 1
    
    @property
    def wasted_space(self) -> int:
        """Bytes wasted by duplicates."""
        return self.total_size * self.duplicate_count


class DuplicateDetector:
    """Detects and manages duplicate files."""
    
    def __init__(self, settings: Settings):
        """Initialize duplicate detector.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.chunk_size = settings.chunk_size
        
        # Cache for file hashes to avoid recalculation
        self._hash_cache: Dict[str, str] = {}
    
    def find_duplicates_by_size(self, directory: Path) -> List[DuplicateGroup]:
        """Find potential duplicates by file size.
        
        Args:
            directory: Directory to scan
            
        Returns:
            List of duplicate groups
        """
        size_groups: Dict[int, List[FileInfo]] = {}
        
        # Group files by size
        for file_path in self._scan_files(directory):
            try:
                file_info = FileInfo(path=file_path, size=0)
                
                if file_info.size > 0:  # Skip empty files
                    if file_info.size not in size_groups:
                        size_groups[file_info.size] = []
                    size_groups[file_info.size].append(file_info)
                    
            except (OSError, FileNotFoundError):
                logger.warning(f"Cannot access file: {file_path}")
                continue
        
        # Find groups with multiple files (potential duplicates)
        duplicate_groups = []
        for size, files in size_groups.items():
            if len(files) > 1:
                duplicate_groups.append(DuplicateGroup(
                    files=files,
                    total_size=size
                ))
        
        logger.info(f"Found {len(duplicate_groups)} potential duplicate groups by size")
        return duplicate_groups
    
    def find_duplicates_by_hash(self, directory: Path) -> List[DuplicateGroup]:
        """Find exact duplicates by file hash.
        
        Args:
            directory: Directory to scan
            
        Returns:
            List of duplicate groups
        """
        hash_groups: Dict[str, List[FileInfo]] = {}
        
        # First, group by size to reduce hash calculations
        size_groups = self.find_duplicates_by_size(directory)
        
        for size_group in size_groups:
            # Calculate hashes for files of the same size
            for file_info in size_group.files:
                try:
                    file_hash = self._calculate_file_hash(file_info.path)
                    file_info.hash_sha256 = file_hash
                    
                    if file_hash not in hash_groups:
                        hash_groups[file_hash] = []
                    hash_groups[file_hash].append(file_info)
                    
                except Exception as e:
                    logger.warning(f"Failed to hash file {file_info.path}: {e}")
                    continue
        
        # Find groups with multiple files (exact duplicates)
        duplicate_groups = []
        for file_hash, files in hash_groups.items():
            if len(files) > 1:
                duplicate_groups.append(DuplicateGroup(
                    files=files,
                    total_size=files[0].size
                ))
        
        logger.info(f"Found {len(duplicate_groups)} exact duplicate groups by hash")
        return duplicate_groups
    
    def is_duplicate(self, file_path: Path, reference_directory: Path) -> bool:
        """Check if a file is a duplicate of any file in the reference directory.
        
        Args:
            file_path: File to check
            reference_directory: Directory to check against
            
        Returns:
            True if file is a duplicate
        """
        if not file_path.exists():
            return False
        
        try:
            file_size = file_path.stat().st_size
            file_hash = self._calculate_file_hash(file_path)
            
            # Check all files in reference directory
            for ref_file in self._scan_files(reference_directory):
                if ref_file == file_path:
                    continue  # Skip self
                
                try:
                    if ref_file.stat().st_size == file_size:
                        ref_hash = self._calculate_file_hash(ref_file)
                        if ref_hash == file_hash:
                            logger.debug(f"Duplicate found: {file_path} matches {ref_file}")
                            return True
                            
                except (OSError, FileNotFoundError):
                    continue
            
            return False
            
        except Exception as e:
            logger.warning(f"Error checking duplicate for {file_path}: {e}")
            return False
    
    def find_duplicate_of_file(self, file_path: Path, search_directory: Path) -> Optional[Path]:
        """Find the duplicate of a specific file in a directory.
        
        Args:
            file_path: File to find duplicate of
            search_directory: Directory to search in
            
        Returns:
            Path to duplicate file or None if not found
        """
        if not file_path.exists():
            return None
        
        try:
            file_size = file_path.stat().st_size
            file_hash = self._calculate_file_hash(file_path)
            
            for candidate_file in self._scan_files(search_directory):
                if candidate_file == file_path:
                    continue
                
                try:
                    if candidate_file.stat().st_size == file_size:
                        candidate_hash = self._calculate_file_hash(candidate_file)
                        if candidate_hash == file_hash:
                            return candidate_file
                            
                except (OSError, FileNotFoundError):
                    continue
            
            return None
            
        except Exception as e:
            logger.warning(f"Error finding duplicate of {file_path}: {e}")
            return None
    
    def get_duplicate_statistics(self, directory: Path) -> Dict[str, any]:
        """Get statistics about duplicates in a directory.
        
        Args:
            directory: Directory to analyze
            
        Returns:
            Dictionary with duplicate statistics
        """
        duplicate_groups = self.find_duplicates_by_hash(directory)
        
        total_duplicates = sum(group.duplicate_count for group in duplicate_groups)
        total_wasted_space = sum(group.wasted_space for group in duplicate_groups)
        total_files = len(list(self._scan_files(directory)))
        
        return {
            'total_files': total_files,
            'duplicate_groups': len(duplicate_groups),
            'total_duplicates': total_duplicates,
            'wasted_space_bytes': total_wasted_space,
            'wasted_space_mb': total_wasted_space / (1024 * 1024),
            'duplicate_percentage': (total_duplicates / total_files * 100) if total_files > 0 else 0
        }
    
    def remove_duplicates(self, directory: Path, keep_newest: bool = True) -> Dict[str, any]:
        """Remove duplicate files from a directory.
        
        Args:
            directory: Directory to clean
            keep_newest: Whether to keep the newest file in each duplicate group
            
        Returns:
            Dictionary with removal results
        """
        duplicate_groups = self.find_duplicates_by_hash(directory)
        
        removed_files = []
        removed_bytes = 0
        errors = []
        
        for group in duplicate_groups:
            try:
                # Sort files by modification time
                sorted_files = sorted(group.files, key=lambda f: f.modified_time)
                
                # Determine which files to remove
                if keep_newest:
                    files_to_remove = sorted_files[:-1]  # Remove all but the newest
                else:
                    files_to_remove = sorted_files[1:]   # Remove all but the oldest
                
                # Remove the duplicate files
                for file_info in files_to_remove:
                    try:
                        file_info.path.unlink()
                        removed_files.append(str(file_info.path))
                        removed_bytes += file_info.size
                        logger.info(f"Removed duplicate: {file_info.path}")
                        
                    except OSError as e:
                        error_msg = f"Failed to remove {file_info.path}: {e}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                        
            except Exception as e:
                error_msg = f"Error processing duplicate group: {e}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return {
            'removed_files': len(removed_files),
            'removed_bytes': removed_bytes,
            'removed_mb': removed_bytes / (1024 * 1024),
            'errors': errors,
            'file_list': removed_files
        }
    
    def _scan_files(self, directory: Path) -> List[Path]:
        """Recursively scan directory for files.
        
        Args:
            directory: Directory to scan
            
        Returns:
            List of file paths
        """
        files = []
        
        try:
            for root, dirs, filenames in os.walk(directory):
                for filename in filenames:
                    file_path = Path(root) / filename
                    if file_path.is_file():
                        files.append(file_path)
                        
        except Exception as e:
            logger.error(f"Error scanning directory {directory}: {e}")
        
        return files
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file with caching.
        
        Args:
            file_path: Path to file
            
        Returns:
            SHA-256 hash as hex string
        """
        # Create cache key from path and modification time
        try:
            stat = file_path.stat()
            cache_key = f"{file_path}:{stat.st_size}:{stat.st_mtime}"
            
            # Check cache first
            if cache_key in self._hash_cache:
                return self._hash_cache[cache_key]
            
            # Calculate hash
            hash_obj = hashlib.sha256()
            with open(file_path, 'rb') as f:
                while chunk := f.read(self.chunk_size):
                    hash_obj.update(chunk)
            
            file_hash = hash_obj.hexdigest()
            
            # Cache the result
            self._hash_cache[cache_key] = file_hash
            
            return file_hash
            
        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            raise
    
    def clear_cache(self) -> None:
        """Clear the hash cache."""
        self._hash_cache.clear()
        logger.debug("Hash cache cleared")
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            'cached_hashes': len(self._hash_cache),
            'cache_memory_estimate': len(str(self._hash_cache))  # Rough estimate
        }