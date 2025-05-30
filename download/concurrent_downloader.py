"""Concurrent file downloader with progress tracking."""

import asyncio
import aiohttp
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime

from config.settings import Settings
from api.zenfolio_client import ZenfolioClient
from api.models import DownloadInfo
from api.exceptions import NetworkError, RateLimitError
from progress.statistics import StatisticsTracker
from progress.console_progress import console_progress
from download.retry_manager import DownloadRetryManager
from download.integrity_checker import IntegrityChecker
from logs.logger import (
    get_logger, log_download_start, log_download_complete,
    log_download_error, log_download_skip
)

logger = get_logger(__name__)


class DownloadTask:
    """Represents a single download task."""
    
    def __init__(self, download_info: DownloadInfo, gallery_name: str):
        self.download_info = download_info
        self.gallery_name = gallery_name
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.bytes_downloaded = 0
        self.success = False
        self.error: Optional[Exception] = None
    
    @property
    def duration_seconds(self) -> float:
        """Get download duration in seconds."""
        if not self.start_time:
            return 0.0
        end = self.end_time or datetime.now()
        duration = (end - self.start_time).total_seconds()
        # Ensure duration is never negative
        return max(0.0, duration)
    
    @property
    def download_speed_mbps(self) -> float:
        """Get download speed in MB/s."""
        duration = self.duration_seconds
        if duration == 0 or self.bytes_downloaded == 0:
            return 0.0
        return (self.bytes_downloaded / (1024 * 1024)) / duration


class ConcurrentDownloader:
    """Manages concurrent file downloads with rate limiting and error handling."""
    
    def __init__(self, settings: Settings, client: ZenfolioClient):
        """Initialize concurrent downloader.
        
        Args:
            settings: Application settings
            client: Zenfolio API client
        """
        self.settings = settings
        self.client = client
        self.retry_manager = DownloadRetryManager(settings)
        self.integrity_checker = IntegrityChecker(settings)
        
        # Concurrency control
        self.semaphore = asyncio.Semaphore(settings.concurrent_downloads)
        self.is_running = True
        
        # Progress tracking
        self.active_downloads: Dict[str, DownloadTask] = {}
        self.completed_downloads: List[DownloadTask] = []
    
    async def download_files(
        self,
        downloads: List[DownloadInfo],
        gallery_name: str,
        statistics_tracker: StatisticsTracker
    ) -> List[Dict[str, Any]]:
        """Download multiple files concurrently.
        
        Args:
            downloads: List of files to download
            gallery_name: Name of the gallery being processed
            statistics_tracker: Statistics tracker
            
        Returns:
            List of download results
        """
        if not downloads:
            return []
        
        logger.debug(f"Starting concurrent download of {len(downloads)} files")
        
        # Initialize progress tracking
        completed_count = 0
        completed_lock = asyncio.Lock()
        
        async def track_completion():
            """Helper to update progress when a file completes."""
            nonlocal completed_count
            async with completed_lock:
                completed_count += 1
                # Get current gallery stats to calculate total completed (including existing files)
                gallery_stats = statistics_tracker.overall_stats.gallery_stats.get(gallery_name)
                if gallery_stats:
                    total_completed = gallery_stats.completed_files
                    console_progress.update_progress(total_completed)
        
        # Create download tasks
        tasks = []
        for download_info in downloads:
            if not self.is_running:
                break
            
            task = asyncio.create_task(
                self._download_single_file(download_info, gallery_name, statistics_tracker, track_completion)
            )
            tasks.append(task)
        
        # Wait for all downloads to complete
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            download_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    download_info = downloads[i]
                    download_results.append({
                        'file_path': download_info.local_path,
                        'success': False,
                        'error': str(result),
                        'bytes_downloaded': 0,
                        'duration_seconds': 0,
                        # Add detailed error information for better reporting
                        'file_name': download_info.photo.file_name if download_info.photo else 'Unknown',
                        'photo_id': download_info.photo.id if download_info.photo else 'Unknown',
                        'url': download_info.url,
                        'expected_size': download_info.expected_size,
                        'local_path': download_info.local_path,
                        'attempts': self.retry_manager.last_attempt_count
                    })
                else:
                    download_results.append(result)
            
            return download_results
            
        except Exception as e:
            logger.error(f"Error in concurrent download: {e}")
            raise
    
    async def _download_single_file(
        self,
        download_info: DownloadInfo,
        gallery_name: str,
        statistics_tracker: StatisticsTracker,
        completion_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Download a single file with retry logic.
        
        Args:
            download_info: Download information
            gallery_name: Gallery name for tracking
            statistics_tracker: Statistics tracker
            completion_callback: Optional callback to call when file completes
            
        Returns:
            Download result dictionary
        """
        async with self.semaphore:  # Limit concurrent downloads
            if not self.is_running:
                return {
                    'file_path': download_info.local_path,
                    'success': False,
                    'error': 'Download stopped',
                    'bytes_downloaded': 0,
                    'duration_seconds': 0,
                    # Add detailed error information for better reporting
                    'file_name': download_info.photo.file_name if download_info.photo else 'Unknown',
                    'photo_id': download_info.photo.id if download_info.photo else 'Unknown',
                    'url': download_info.url,
                    'expected_size': download_info.expected_size,
                    'local_path': download_info.local_path,
                    'attempts': 'Unknown'
                }
            
            download_task = DownloadTask(download_info, gallery_name)
            self.active_downloads[download_info.local_path] = download_task
            
            try:
                # Use retry manager for robust downloading
                result = await self.retry_manager.retry_download(
                    self._perform_download,
                    download_info.local_path,
                    download_info,
                    download_task
                )
                
                # Update statistics on success
                statistics_tracker.record_file_completed(
                    gallery_name,
                    download_task.bytes_downloaded
                )
                
                # Update progress display
                if completion_callback:
                    await completion_callback()
                
                return result
                
            except Exception as e:
                # Update statistics on failure
                statistics_tracker.record_file_failed(gallery_name)
                
                download_task.error = e
                log_download_error(download_info.local_path, e)
                
                # Get actual attempt count from retry manager
                attempts = self.retry_manager.last_attempt_count
                
                return {
                    'file_path': download_info.local_path,
                    'success': False,
                    'error': str(e),
                    'bytes_downloaded': download_task.bytes_downloaded,
                    'duration_seconds': download_task.duration_seconds,
                    # Add detailed error information for better reporting
                    'file_name': download_info.photo.file_name if download_info.photo else 'Unknown',
                    'photo_id': download_info.photo.id if download_info.photo else 'Unknown',
                    'url': download_info.url,
                    'expected_size': download_info.expected_size,
                    'local_path': download_info.local_path,
                    'attempts': attempts
                }
                
            finally:
                # Clean up tracking
                self.active_downloads.pop(download_info.local_path, None)
                self.completed_downloads.append(download_task)
    
    async def _perform_download(
        self,
        download_info: DownloadInfo,
        download_task: DownloadTask
    ) -> Dict[str, Any]:
        """Perform the actual file download.
        
        Args:
            download_info: Download information
            download_task: Download task for tracking
            
        Returns:
            Download result dictionary
        """
        download_task.start_time = datetime.now()
        file_path = Path(download_info.local_path)
        
        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check disk space if file size is known
            if download_info.expected_size:
                # This would use directory_manager.check_disk_space()
                # For now, we'll skip this check
                pass
            
            log_download_start(download_info.local_path, download_info.expected_size)
            
            # Debug logging for download request
            headers = self.client.auth.get_auth_headers()
            logger.debug(f"Downloading file: {download_info.url}")
            logger.debug(f"Download headers: {headers}")
            logger.debug(f"Expected size: {download_info.expected_size}")
            
            # Download the file with extended timeout for large files
            download_timeout = aiohttp.ClientTimeout(total=self.settings.download_timeout)
            async with self.client.session.get(
                download_info.url,
                headers=headers,
                timeout=download_timeout
            ) as response:
                
                # Debug logging for download response
                logger.debug(f"Download response status: {response.status}")
                logger.debug(f"Download response headers: {dict(response.headers)}")
                
                # Check response status with enhanced debugging
                if response.status == 401:
                    response_text = await response.text()
                    logger.debug(f"Download auth error for {download_info.url} - Response: {response_text[:500]}")
                    raise NetworkError("Authentication required - token may have expired")
                elif response.status == 403:
                    response_text = await response.text()
                    logger.debug(f"Download forbidden for {download_info.url} - Response: {response_text[:500]}")
                    raise NetworkError("Access forbidden")
                elif response.status == 404:
                    response_text = await response.text()
                    logger.debug(f"Download not found for {download_info.url} - Response: {response_text[:500]}")
                    raise NetworkError("File not found on server")
                elif response.status == 429:
                    retry_after = float(response.headers.get('Retry-After', 60))
                    response_text = await response.text()
                    logger.debug(f"Download rate limited for {download_info.url} - Retry after: {retry_after}s - Response: {response_text[:500]}")
                    raise RateLimitError("Rate limit exceeded", retry_after=retry_after)
                elif response.status >= 500:
                    response_text = await response.text()
                    # Clean up server error messages - don't show HTML content to user
                    if "cloudflare" in response_text.lower() or "<html>" in response_text.lower():
                        error_msg = f"Server temporarily unavailable (HTTP {response.status})"
                        logger.debug(f"Server error {response.status} for {download_info.url} - Cloudflare/HTML response detected")
                    else:
                        error_msg = f"Server error {response.status}: {response_text[:100]}"
                        logger.debug(f"Server error {response.status} for {download_info.url} - Response: {response_text[:500]}")
                    
                    raise NetworkError(error_msg)
                elif response.status != 200:
                    response_text = await response.text()
                    logger.debug(f"Download HTTP error {response.status} for {download_info.url} - Response: {response_text[:500]}")
                    raise NetworkError(f"HTTP {response.status}: {response.reason}")
                
                # Get content length
                content_length = response.headers.get('Content-Length')
                expected_size = int(content_length) if content_length else None
                
                # Download file in chunks
                with open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(self.settings.chunk_size):
                        if not self.is_running:
                            raise Exception("Download cancelled")
                        
                        f.write(chunk)
                        download_task.bytes_downloaded += len(chunk)
            
            download_task.end_time = datetime.now()
            download_task.success = True
            
            # Verify file integrity if enabled
            if self.settings.verify_integrity:
                verification = self.integrity_checker.verify_download_integrity(download_info)
                if verification['errors']:
                    # Categorize errors - only treat actual corruption as serious
                    serious_errors = []
                    filesystem_errors = []
                    minor_errors = []
                    
                    for error in verification['errors']:
                        error_lower = error.lower()
                        if 'invalid argument' in error_lower or 'filesystem error' in error_lower:
                            filesystem_errors.append(error)
                        elif 'corrupted' in error_lower and 'hash' in error_lower:
                            serious_errors.append(error)
                        elif 'empty' in error_lower or 'incomplete' in error_lower:
                            serious_errors.append(error)
                        else:
                            minor_errors.append(error)
                    
                    if serious_errors:
                        logger.debug(f"File integrity check failed for {download_info.local_path}: {serious_errors}")
                        self.integrity_checker.cleanup_partial_download(download_info.local_path)
                        raise NetworkError(f"File integrity check failed: {serious_errors}")
                    else:
                        # For filesystem errors and minor issues, just log and continue
                        all_minor = filesystem_errors + minor_errors
                        logger.debug(f"Minor integrity issues for {download_info.local_path}: {all_minor}")
            
            # Preserve file timestamp if enabled
            if self.settings.preserve_timestamps:
                self.integrity_checker.preserve_file_timestamp(
                    download_info.local_path,
                    download_info.photo
                )
            
            log_download_complete(
                download_info.local_path,
                download_task.duration_seconds,
                download_task.bytes_downloaded
            )
            
            return {
                'file_path': download_info.local_path,
                'success': True,
                'bytes_downloaded': download_task.bytes_downloaded,
                'duration_seconds': download_task.duration_seconds,
                'download_speed_mbps': download_task.download_speed_mbps
            }
            
        except Exception as e:
            download_task.end_time = datetime.now()
            download_task.error = e
            
            # Clean up partial download
            if file_path.exists():
                try:
                    file_path.unlink()
                    logger.debug(f"Cleaned up partial download: {file_path}")
                except OSError:
                    logger.debug(f"Failed to clean up partial download: {file_path}")
            
            raise
    
    def get_active_downloads(self) -> List[Dict[str, Any]]:
        """Get information about currently active downloads.
        
        Returns:
            List of active download information
        """
        active = []
        for file_path, task in self.active_downloads.items():
            active.append({
                'file_path': file_path,
                'gallery_name': task.gallery_name,
                'bytes_downloaded': task.bytes_downloaded,
                'duration_seconds': task.duration_seconds,
                'download_speed_mbps': task.download_speed_mbps,
                'expected_size': task.download_info.expected_size
            })
        return active
    
    def get_download_statistics(self) -> Dict[str, Any]:
        """Get download statistics.
        
        Returns:
            Dictionary with download statistics
        """
        total_downloads = len(self.completed_downloads)
        successful_downloads = sum(1 for task in self.completed_downloads if task.success)
        failed_downloads = total_downloads - successful_downloads
        
        total_bytes = sum(task.bytes_downloaded for task in self.completed_downloads)
        total_duration = sum(task.duration_seconds for task in self.completed_downloads)
        
        avg_speed = 0.0
        if total_duration > 0:
            avg_speed = (total_bytes / (1024 * 1024)) / total_duration
        
        return {
            'total_downloads': total_downloads,
            'successful_downloads': successful_downloads,
            'failed_downloads': failed_downloads,
            'active_downloads': len(self.active_downloads),
            'total_bytes_downloaded': total_bytes,
            'total_duration_seconds': total_duration,
            'average_speed_mbps': avg_speed,
            'success_rate': (successful_downloads / total_downloads * 100) if total_downloads > 0 else 0
        }
    
    def stop(self) -> None:
        """Stop all downloads."""
        self.is_running = False
        logger.debug("Concurrent downloader stop requested")
    
    def resume(self) -> None:
        """Resume downloads."""
        self.is_running = True
        logger.debug("Concurrent downloader resumed")