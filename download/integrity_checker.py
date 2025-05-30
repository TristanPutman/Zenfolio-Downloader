"""File integrity verification for downloaded files."""

import hashlib
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from api.models import Photo, DownloadInfo
from config.settings import Settings
from logs.logger import get_logger

logger = get_logger(__name__)


class IntegrityChecker:
    """Handles file integrity verification and metadata validation."""
    
    def __init__(self, settings: Settings):
        """Initialize integrity checker.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.chunk_size = settings.chunk_size
    
    def calculate_file_hash(self, file_path: str, algorithm: str = "sha256") -> str:
        """Calculate hash of a file.
        
        Args:
            file_path: Path to file
            algorithm: Hash algorithm to use
            
        Returns:
            Hex digest of file hash
            
        Raises:
            FileNotFoundError: If file doesn't exist
            IOError: If file cannot be read
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        hash_obj = hashlib.new(algorithm)
        
        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(self.chunk_size):
                    hash_obj.update(chunk)
            
            file_hash = hash_obj.hexdigest()
            logger.debug(f"Calculated {algorithm} hash for {file_path}: {file_hash}")
            return file_hash
            
        except IOError as e:
            logger.error(f"Failed to read file for hashing {file_path}: {e}")
            raise
    
    def verify_file_size(self, file_path: str, expected_size: Optional[int] = None) -> bool:
        """Verify file size matches expected size.
        
        Args:
            file_path: Path to file
            expected_size: Expected file size in bytes
            
        Returns:
            True if size matches or no expected size provided
        """
        if not os.path.exists(file_path):
            logger.warning(f"Cannot verify size - file not found: {file_path}")
            return False
        
        if expected_size is None:
            return True
        
        actual_size = os.path.getsize(file_path)
        
        if actual_size != expected_size:
            logger.debug(
                f"Size mismatch for {file_path}: "
                f"expected {expected_size:,} bytes, got {actual_size:,} bytes"
            )
            return False
        
        logger.debug(f"Size verified for {file_path}: {actual_size:,} bytes")
        return True
    
    def verify_download_integrity(self, download_info: DownloadInfo) -> Dict[str, Any]:
        """Verify integrity of a downloaded file.
        
        Args:
            download_info: Information about the downloaded file
            
        Returns:
            Dictionary with verification results
        """
        file_path = download_info.local_path
        results = {
            'file_path': file_path,
            'exists': False,
            'size_valid': False,
            'hash_calculated': None,
            'timestamp': datetime.now().isoformat(),
            'errors': []
        }
        
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                results['errors'].append("File does not exist")
                return results
            
            results['exists'] = True
            
            # Verify file size
            if download_info.expected_size:
                actual_size = os.path.getsize(file_path)
                size_ratio = actual_size / download_info.expected_size if download_info.expected_size and download_info.expected_size > 0 else 0
                
                # Be more lenient with size mismatches - Zenfolio often provides different sized versions
                if actual_size == download_info.expected_size:
                    results['size_valid'] = True
                elif size_ratio >= 0.8 and size_ratio <= 1.2:  # Within 20% tolerance
                    results['size_valid'] = True
                    logger.debug(f"Size within tolerance for {file_path}: {actual_size} vs {download_info.expected_size}")
                elif hasattr(download_info, 'photo') and hasattr(download_info.photo, 'is_video') and download_info.photo.is_video and size_ratio < 0.1:
                    # For videos, accept preview versions (Zenfolio API limitation)
                    results['size_valid'] = True
                    logger.debug(f"Accepting video preview for {file_path}: {actual_size} vs {download_info.expected_size}")
                else:
                    # Only log as debug, don't treat as error unless size is drastically different
                    if size_ratio < 0.1 or size_ratio > 10:
                        results['errors'].append("File size mismatch")
                        logger.debug(f"Significant size mismatch for {file_path}: {actual_size} vs {download_info.expected_size}")
                    else:
                        # Accept moderate size differences
                        results['size_valid'] = True
                        logger.debug(f"Accepting size difference for {file_path}: {actual_size} vs {download_info.expected_size}")
            else:
                results['size_valid'] = True
            
            # Calculate file hash for integrity
            if self.settings.verify_integrity:
                try:
                    results['hash_calculated'] = self.calculate_file_hash(file_path)
                except Exception as e:
                    results['errors'].append(f"Hash calculation failed: {e}")
            
            # Check if file is readable and not corrupted
            try:
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    results['errors'].append("File is empty")
                else:
                    with open(file_path, 'rb') as f:
                        # Try to read first chunk
                        chunk_size = min(1024, file_size)
                        first_chunk = f.read(chunk_size)
                        if len(first_chunk) != chunk_size:
                            results['errors'].append("File read incomplete")
                        
                        # Try to read last chunk if file is large enough
                        if file_size > 1024:
                            try:
                                f.seek(-1024, 2)
                                last_chunk = f.read(1024)
                                if len(last_chunk) != 1024:
                                    results['errors'].append("File end read incomplete")
                            except (OSError, IOError) as seek_error:
                                # Some filesystems don't support seeking from end
                                logger.debug(f"Cannot seek to end of file {file_path}: {seek_error}")
            except (OSError, IOError, PermissionError) as e:
                # Handle filesystem-specific errors more gracefully
                if "Invalid argument" in str(e):
                    logger.debug(f"Filesystem error reading {file_path}: {e}")
                    # Don't treat filesystem errors as corruption
                else:
                    results['errors'].append(f"File appears corrupted: {e}")
            except Exception as e:
                results['errors'].append(f"File appears corrupted: {e}")
            
        except Exception as e:
            results['errors'].append(f"Verification failed: {e}")
            logger.debug(f"Integrity verification failed for {file_path}: {e}")
        
        return results
    
    def is_file_complete(self, download_info: DownloadInfo) -> bool:
        """Check if a file download appears complete.
        
        Args:
            download_info: Information about the download
            
        Returns:
            True if file appears complete
        """
        verification = self.verify_download_integrity(download_info)
        
        # File is complete if it exists, has correct size, and no errors
        return (
            verification['exists'] and 
            verification['size_valid'] and 
            len(verification['errors']) == 0
        )
    
    def should_redownload(self, download_info: DownloadInfo, force_overwrite: bool = False) -> bool:
        """Determine if a file should be re-downloaded.
        
        Args:
            download_info: Information about the download
            force_overwrite: Whether to force overwrite existing files
            
        Returns:
            True if file should be downloaded
        """
        file_path = download_info.local_path
        
        # Always download if file doesn't exist
        if not os.path.exists(file_path):
            return True
        
        # Force overwrite if requested
        if force_overwrite:
            logger.debug(f"Force overwrite enabled for {file_path}")
            return True
        
        # Check if existing file is complete and valid
        if not self.is_file_complete(download_info):
            logger.debug(f"Existing file incomplete, will re-download: {file_path}")
            return True
        
        # File exists and appears complete
        logger.debug(f"File already exists and appears complete: {file_path}")
        return False
    
    def cleanup_partial_download(self, file_path: str) -> bool:
        """Clean up a partial or corrupted download.
        
        Args:
            file_path: Path to file to clean up
            
        Returns:
            True if cleanup successful
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Cleaned up partial download: {file_path}")
                return True
            return True
            
        except Exception as e:
            logger.error(f"Failed to cleanup partial download {file_path}: {e}")
            return False
    
    def preserve_file_timestamp(self, file_path: str, photo: Photo) -> bool:
        """Preserve original file timestamp from photo metadata.
        
        Args:
            file_path: Path to downloaded file
            photo: Photo object with timestamp information
            
        Returns:
            True if timestamp was preserved
        """
        if not self.settings.preserve_timestamps:
            return True
        
        try:
            # Check if file exists before trying to set timestamp
            if not os.path.exists(file_path):
                logger.debug(f"File does not exist for timestamp preservation: {file_path}")
                return False
            
            # Use taken_on timestamp if available, otherwise uploaded_on
            timestamp = photo.taken_on or photo.uploaded_on
            
            if timestamp:
                # Convert to Unix timestamp
                unix_timestamp = timestamp.timestamp()
                
                # Set both access and modification times
                os.utime(file_path, (unix_timestamp, unix_timestamp))
                
                logger.debug(f"Preserved timestamp for {file_path}: {timestamp}")
                return True
            else:
                logger.debug(f"No timestamp available for {file_path}")
                return True
                
        except FileNotFoundError:
            logger.debug(f"File not found when preserving timestamp: {file_path}")
            return False
        except OSError as e:
            # Handle filesystem-specific errors more gracefully
            logger.debug(f"Filesystem error preserving timestamp for {file_path}: {e}")
            return False
        except Exception as e:
            logger.debug(f"Failed to preserve timestamp for {file_path}: {e}")
            return False
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get comprehensive file information.
        
        Args:
            file_path: Path to file
            
        Returns:
            Dictionary with file information
        """
        info = {
            'path': file_path,
            'exists': False,
            'size': 0,
            'modified_time': None,
            'hash_sha256': None,
            'readable': False
        }
        
        try:
            if os.path.exists(file_path):
                info['exists'] = True
                stat = os.stat(file_path)
                info['size'] = stat.st_size
                info['modified_time'] = datetime.fromtimestamp(stat.st_mtime).isoformat()
                
                # Check if file is readable
                try:
                    with open(file_path, 'rb') as f:
                        f.read(1)
                    info['readable'] = True
                except:
                    info['readable'] = False
                
                # Calculate hash if file is small enough or if explicitly requested
                if info['size'] < 100 * 1024 * 1024 or self.settings.verify_integrity:  # 100MB limit
                    try:
                        info['hash_sha256'] = self.calculate_file_hash(file_path)
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"Failed to get file info for {file_path}: {e}")
        
        return info