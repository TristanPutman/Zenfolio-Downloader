"""Main download manager for orchestrating Zenfolio downloads."""

import asyncio
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from config.settings import Settings
from api.zenfolio_client import ZenfolioClient
from api.models import Group, PhotoSet, Photo, DownloadInfo, InformationLevel, PhotoSetType
from progress.checkpoint_manager import CheckpointManager
from progress.statistics import StatisticsTracker
from progress.retrieval_queue import RetrievalQueueManager
from .concurrent_downloader import ConcurrentDownloader
from .integrity_checker import IntegrityChecker
from filesystem.directory_manager import DirectoryManager
from filesystem.duplicate_detector import DuplicateDetector
from logs.logger import (
    get_logger, log_gallery_start, log_gallery_complete,
    log_download_skip
)
from progress.console_progress import console_progress

logger = get_logger(__name__)


class DownloadManager:
    """Main download manager that orchestrates the entire download process."""
    
    def __init__(
        self,
        settings: Settings,
        client: ZenfolioClient,
        checkpoint_manager: CheckpointManager,
        statistics_tracker: StatisticsTracker
    ):
        """Initialize download manager.
        
        Args:
            settings: Application settings
            client: Zenfolio API client
            checkpoint_manager: Checkpoint manager for resume functionality
            statistics_tracker: Statistics tracker
        """
        self.settings = settings
        self.client = client
        self.checkpoint_manager = checkpoint_manager
        self.statistics_tracker = statistics_tracker
        self.retrieval_queue = RetrievalQueueManager()
        
        # Initialize components
        self.concurrent_downloader = ConcurrentDownloader(settings, client)
        self.integrity_checker = IntegrityChecker(settings)
        self.directory_manager = DirectoryManager(settings)
        self.duplicate_detector = DuplicateDetector(settings)
        
        # State
        self.is_running = False
        self.current_gallery: Optional[str] = None
    
    async def process_retrieval_queue(self, max_age_hours: int = 24) -> Dict[str, Any]:
        """Process items in the retrieval queue that are ready for retry.
        
        Args:
            max_age_hours: Only process items older than this many hours
            
        Returns:
            Processing results summary
        """
        # Get items ready for retry
        retry_items = self.retrieval_queue.get_items_for_retry(max_age_hours)
        
        if not retry_items:
            return {
                'total_items': 0,
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'still_pending': 0
            }
        
        print(f"Processing {len(retry_items)} items from retrieval queue...")
        
        # Group items by gallery for efficient processing
        gallery_groups = {}
        for item in retry_items:
            if item.gallery_id not in gallery_groups:
                gallery_groups[item.gallery_id] = {
                    'gallery_title': item.gallery_title,
                    'items': []
                }
            gallery_groups[item.gallery_id]['items'].append(item)
        
        # Process each gallery group
        total_processed = 0
        total_successful = 0
        total_failed = 0
        total_still_pending = 0
        
        for gallery_id, group_data in gallery_groups.items():
            gallery_title = group_data['gallery_title']
            items = group_data['items']
            
            print(f"Processing {len(items)} retrieval items from gallery: {gallery_title}")
            
            # Check if this is a gallery-level retry (photo_id = 0)
            gallery_retry_items = [item for item in items if item.photo_id == 0]
            photo_retry_items = [item for item in items if item.photo_id != 0]
            
            # Handle gallery-level retries first
            if gallery_retry_items:
                for gallery_retry_item in gallery_retry_items:
                    try:
                        # Attempt to reload the gallery from API
                        print(f"Retrying gallery metadata load: {gallery_title}")
                        from api.models import InformationLevel
                        full_gallery = await asyncio.wait_for(
                            self.client.load_photo_set(
                                gallery_id,
                                InformationLevel.LEVEL2,
                                include_photos=True
                            ),
                            timeout=120  # 2 minute timeout
                        )
                        
                        # Success - remove from retry queue
                        self.retrieval_queue.remove_gallery_retry_items(gallery_id)
                        total_successful += 1
                        total_processed += 1
                        print(f"Gallery {gallery_title} metadata loaded successfully")
                        
                        # Note: The actual gallery processing will happen in the main download flow
                        # This just confirms the gallery API is accessible again
                        
                    except asyncio.TimeoutError:
                        # Still timing out - keep in queue
                        total_still_pending += 1
                        total_processed += 1
                        print(f"Gallery {gallery_title} still timing out (kept in retry queue)")
                    except Exception as e:
                        # Other error - mark as failed
                        total_failed += 1
                        total_processed += 1
                        print(f"Gallery {gallery_title} failed with error: {e}")
            
            # Handle individual photo retries
            downloads_to_retry = []
            for item in photo_retry_items:
                try:
                    # Create a minimal Photo object for download
                    from api.models import Photo
                    photo = Photo(
                        id=item.photo_id,
                        title=f"Photo {item.photo_id}",
                        file_name=item.file_name,
                        uploaded_on=datetime.now(),
                        width=0,  # Unknown
                        height=0,  # Unknown
                        size=item.file_size or 0,
                        mime_type=item.mime_type,
                        original_url=item.original_url,
                        is_video=item.mime_type.startswith('video/') if item.mime_type else False
                    )
                    
                    # Create download info
                    download_info = DownloadInfo(
                        photo=photo,
                        local_path=Path(item.local_path),
                        url=item.original_url,
                        expected_size=item.file_size
                    )
                    downloads_to_retry.append(download_info)
                    
                except Exception as e:
                    logger.error(f"Failed to create download info for retrieval item {item.photo_id}: {e}")
                    total_failed += 1
            
            # Attempt downloads
            if downloads_to_retry:
                try:
                    download_results = await self.concurrent_downloader.download_files(
                        downloads_to_retry,
                        f"Retrieval Queue - {gallery_title}",
                        self.statistics_tracker
                    )
                    
                    # Process results
                    for i, result in enumerate(download_results):
                        item = photo_retry_items[i]  # Use photo_retry_items instead of items
                        total_processed += 1
                        
                        if result['success']:
                            # Remove from queue
                            self.retrieval_queue.remove_completed_item(item.photo_id)
                            total_successful += 1
                            print(f"Successfully downloaded retrieval item: {item.file_name}")
                        else:
                            # Check if still a timeout (still pending) or different error
                            error_str = str(result.get('error', '')).lower()
                            if 'timeout' in error_str:
                                total_still_pending += 1
                                logger.debug(f"Retrieval item still pending: {item.file_name}")
                            else:
                                total_failed += 1
                                print(f"Retrieval item failed with new error: {item.file_name} - {result.get('error')}")
                
                except Exception as e:
                    logger.debug(f"Failed to process retrieval items for gallery {gallery_title}: {e}")
                    total_failed += len(photo_retry_items)  # Use photo_retry_items instead of items
        
        # Clean up old items (older than 30 days)
        removed_count = self.retrieval_queue.clear_old_items(max_age_days=30)
        
        results = {
            'total_items': len(retry_items),
            'processed': total_processed,
            'successful': total_successful,
            'failed': total_failed,
            'still_pending': total_still_pending
        }
        
        return results
    
    async def download_all_galleries(
        self,
        root_group: Group,
        output_dir: Path,
        gallery_filter: Optional[str] = None,
        base_path: str = ""
    ) -> Dict[str, Any]:
        """Download all galleries from the root group.
        
        Args:
            root_group: Root group containing galleries
            output_dir: Output directory for downloads
            gallery_filter: Optional regex pattern to filter galleries
            base_path: Optional base path to prepend to all gallery paths
            
        Returns:
            Download results summary
        """
        self.is_running = True
        self.statistics_tracker.start_session()
        
        try:
            # Ensure output directory exists
            self.directory_manager.ensure_directory(output_dir)
            
            # Collect all galleries to process
            galleries_to_process = await self._collect_galleries(root_group, gallery_filter, base_path)
            
            logger.debug(f"Found {len(galleries_to_process)} galleries to process")
            
            # Process each gallery
            results = []
            successful_count = 0
            failed_count = 0
            skipped_count = 0
            
            for gallery_info in galleries_to_process:
                if not self.is_running:
                    break
                
                gallery_result = await self._process_gallery(
                    gallery_info['gallery'],
                    gallery_info['local_path'],
                    output_dir
                )
                results.append(gallery_result)
                
                # Count results by type
                if gallery_result.get('success', False):
                    successful_count += 1
                elif gallery_result.get('skipped', False):
                    skipped_count += 1
                else:
                    failed_count += 1
            
            # Generate final summary
            final_summary = self.statistics_tracker.get_final_summary()
            
            # Log summary
            logger.debug("All galleries processed")
            # Summary logging removed for clean output
            # Details are available in debug logs if needed
            
            return {
                'success': True,
                'galleries_processed': len(results),
                'successful_count': successful_count,
                'failed_count': failed_count,
                'skipped_count': skipped_count,
                'gallery_results': results,
                'summary': final_summary
            }
            
        except Exception as e:
            logger.error(f"Download process failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'galleries_processed': len(results) if 'results' in locals() else 0
            }
        finally:
            self.is_running = False
            self.statistics_tracker.end_session()
    
    async def _collect_galleries(
        self,
        group: Group,
        gallery_filter: Optional[str] = None,
        base_path: str = ""
    ) -> List[Dict[str, Any]]:
        """Recursively collect all galleries from a group.
        
        Args:
            group: Group to process
            gallery_filter: Optional regex pattern to filter galleries
            base_path: Base path for the current group
            
        Returns:
            List of gallery information dictionaries
        """
        galleries = []
        
        # Process galleries in this group
        for gallery in group.galleries:
            # Apply filter if specified
            if gallery_filter:
                try:
                    if not re.search(gallery_filter, gallery.title, re.IGNORECASE):
                        continue
                except re.error as e:
                    logger.debug(f"Invalid gallery filter regex: {e}")
                    # Continue without filter if regex is invalid
            
            gallery_path = self.directory_manager.sanitize_filename(gallery.title)
            local_path = Path(base_path) / gallery_path if base_path else Path(gallery_path)
            
            galleries.append({
                'gallery': gallery,
                'local_path': local_path,
                'full_title': f"{base_path}/{gallery.title}" if base_path else gallery.title
            })
        
        # Recursively process subgroups
        for subgroup in group.subgroups:
            subgroup_path = self.directory_manager.sanitize_filename(subgroup.title)
            new_base_path = f"{base_path}/{subgroup_path}" if base_path else subgroup_path
            
            subgroup_galleries = await self._collect_galleries(
                subgroup,
                gallery_filter,
                new_base_path
            )
            galleries.extend(subgroup_galleries)
        
        return galleries
    
    async def _process_gallery(
        self,
        gallery: PhotoSet,
        local_path: Path,
        output_dir: Path
    ) -> Dict[str, Any]:
        """Process a single gallery.
        
        Args:
            gallery: Gallery to process
            local_path: Local path for the gallery
            output_dir: Base output directory
            
        Returns:
            Gallery processing results
        """
        gallery_start_time = datetime.now()
        gallery_output_dir = output_dir / local_path
        
        self.current_gallery = gallery.title
        
        try:
            # Check if gallery is complete using cache-first approach
            is_complete, cached_photos_data = self._is_gallery_complete_with_cache(gallery, gallery_output_dir)
            logger.debug(f"Gallery completion check for {gallery.title}: is_complete={is_complete}, has_cached_data={cached_photos_data is not None}")
            
            if is_complete:
                # Gallery is already 100% complete - skip API call and show instant progress
                actual_count = len(cached_photos_data) if cached_photos_data else gallery.photo_count
                logger.debug(f"Skipping {gallery.title} - already complete with {actual_count} files")
                parent_path = str(local_path.parent) if local_path.parent != Path('.') else str(local_path)
                console_progress.start_gallery(gallery.title, actual_count, parent_path)
                console_progress.set_completion_info(0, actual_count, 0)
                console_progress.complete_gallery()
                
                gallery_duration = (datetime.now() - gallery_start_time).total_seconds()
                # Ensure duration is never negative (can happen with very fast operations)
                gallery_duration = max(0.0, gallery_duration)
                
                return {
                    'gallery_name': gallery.title,
                    'success': True,
                    'total_files': actual_count,
                    'downloaded': 0,
                    'failed': 0,
                    'already_existed': actual_count,
                    'duration_seconds': gallery_duration,
                    'local_path': str(local_path)
                }
            
            # Gallery is not complete - determine what photos we need
            photos_to_process = []
            logger.debug(f"Gallery {gallery.title} is incomplete - proceeding with download processing")
            
            if cached_photos_data:
                # Use cached photo metadata (no API call needed)
                logger.debug(f"Using cached photo metadata for {gallery.title} ({len(cached_photos_data)} photos)")
                
                # Convert cached data to Photo objects
                for photo_data in cached_photos_data:
                    try:
                        from api.models import Photo
                        photo = Photo(
                            id=photo_data['id'],
                            title=photo_data['title'],
                            file_name=photo_data['file_name'],
                            mime_type=photo_data['mime_type'],
                            size=photo_data['size'],
                            width=photo_data['width'],
                            height=photo_data['height'],
                            taken_on=datetime.fromisoformat(photo_data['taken_on']) if photo_data['taken_on'] else None,
                            uploaded_on=datetime.fromisoformat(photo_data['uploaded_on']),
                            original_url=photo_data['original_url'],
                            is_video=photo_data.get('is_video', False),
                            sequence=photo_data.get('sequence', None)
                        )
                        photos_to_process.append(photo)
                    except Exception as e:
                        logger.debug(f"Failed to deserialize cached photo: {e}")
                
                # Create a PhotoSet object with cached photos
                full_gallery = PhotoSet(
                    id=gallery.id,
                    title=gallery.title,
                    type=gallery.type,
                    created_on=gallery.created_on,
                    photo_count=len(photos_to_process),
                    photos=photos_to_process
                )
                
            else:
                # No cached data - load from API
                logger.debug(f"Loading gallery data from API: {gallery.title} (ID: {gallery.id})")
                try:
                    # Add timeout to prevent hanging
                    full_gallery = await asyncio.wait_for(
                        self.client.load_photo_set(
                            gallery.id,
                            InformationLevel.LEVEL2,
                            include_photos=True
                        ),
                        timeout=120  # 2 minute timeout
                    )
                    # Defensive programming: ensure photos is not None
                    api_photos_list = full_gallery.photos or []
                    logger.debug(f"Successfully loaded {gallery.title} from API ({len(api_photos_list)} photos)")
                    
                    # Check for empty gallery that should have photos (API inconsistency)
                    if len(api_photos_list) == 0 and gallery.photo_count > 0:
                        logger.debug(f"API returned 0 photos for {gallery.title} but gallery shows {gallery.photo_count} photos - possible API issue")
                        return {
                            'gallery_name': gallery.title,
                            'success': False,
                            'error': f"API returned empty gallery (expected {gallery.photo_count} photos)",
                            'skipped': True,
                            'local_path': str(local_path)
                        }
                    
                    # Save photo metadata to cache for future runs
                    if len(api_photos_list) > 0:
                        try:
                            from cache.cache_manager import CacheManager
                            cache_manager = CacheManager(
                                cache_dir=Path(self.settings.cache_dir),
                                cache_ttl_hours=self.settings.cache_ttl_hours
                            )
                            cache_manager.save_photo_metadata(gallery.id, api_photos_list)
                            logger.debug(f"Saved photo metadata to cache for {gallery.title}")
                        except Exception as cache_error:
                            logger.debug(f"Failed to save photo metadata to cache for {gallery.title}: {cache_error}")
                except asyncio.TimeoutError:
                    # Add entire gallery to retry queue instead of skipping
                    try:
                        # Create a gallery-level retry item using the gallery metadata
                        self.retrieval_queue.add_gallery_retry_item(
                            gallery_id=gallery.id,
                            gallery_title=gallery.title,
                            error_message=f"API timeout loading gallery metadata after 120 seconds"
                        )
                        print(f"Processing {gallery.title} (added to retry queue)")
                    except Exception as queue_error:
                        logger.debug(f"Failed to add gallery to retry queue: {queue_error}")
                        print(f"Processing {gallery.title} (added to retry queue)")
                    
                    # Return success with zero files processed
                    return {
                        'gallery_name': gallery.title,
                        'success': True,
                        'total_files': 0,
                        'downloaded': 0,
                        'failed': 0,
                        'already_existed': 0,
                        'duration_seconds': 0.0,
                        'local_path': str(local_path),
                        'added_to_retry_queue': True
                    }
                except Exception as api_error:
                    # Handle API errors (like 500 server errors) gracefully
                    if "Server error: 500" in str(api_error):
                        # Add gallery to retry queue instead of skipping
                        try:
                            self.retrieval_queue.add_gallery_retry_item(
                                gallery_id=gallery.id,
                                gallery_title=gallery.title,
                                error_message=f"Server error 500: {str(api_error)}"
                            )
                            print(f"Processing {gallery.title} (added to retry queue)")
                        except Exception as queue_error:
                            logger.debug(f"Failed to add gallery to retry queue: {queue_error}")
                            print(f"Processing {gallery.title} (added to retry queue)")
                        
                        # Return success with zero files processed
                        return {
                            'gallery_name': gallery.title,
                            'success': True,
                            'total_files': 0,
                            'downloaded': 0,
                            'failed': 0,
                            'already_existed': 0,
                            'duration_seconds': 0.0,
                            'local_path': str(local_path),
                            'added_to_retry_queue': True
                        }
                    else:
                        # Re-raise other API errors
                        raise
            
            # Start tracking this gallery
            photos_list = full_gallery.photos or []
            total_size = sum(photo.size for photo in photos_list if photo.size > 0)
            self.statistics_tracker.start_gallery(
                gallery.title,
                len(photos_list),
                total_size
            )
            
            # Start console progress display
            parent_path = str(local_path.parent) if local_path.parent != Path('.') else str(local_path)
            console_progress.start_gallery(gallery.title, len(photos_list), parent_path)
            
            # Ensure gallery directory exists
            self.directory_manager.ensure_directory(gallery_output_dir)
            
            # Prepare download list
            downloads_to_process = []
            for photo in photos_list:
                if not photo.is_downloadable:
                    logger.debug(f"Photo not downloadable: {photo.file_name}")
                    logger.debug(f"Photo debug info: {photo.debug_info()}")
                    continue
                
                try:
                    download_info = self.client.get_download_info(photo, str(gallery_output_dir))
                    
                    # Debug logging for download URL
                    logger.debug(f"Photo {photo.id} download URL: {download_info.url}")
                    
                    # Check if we should download this file
                    if self._should_download_file(download_info):
                        downloads_to_process.append(download_info)
                    else:
                        # File already exists and is complete
                        reason = self._get_skip_reason(download_info)
                        logger.debug(f"File already exists: {download_info.local_path} - {reason}")
                        
                        log_download_skip(download_info.local_path, reason)
                        self.statistics_tracker.record_file_skipped(
                            gallery.title,
                            photo.size
                        )
                        # Mark file as skipped in checkpoint
                        self.checkpoint_manager.mark_file_skipped(download_info.local_path)
                except Exception as e:
                    logger.error(f"Failed to create download info for photo {photo.id} ({photo.file_name}): {e}")
                    logger.debug(f"Photo debug info: {photo.debug_info()}")
            
            # Defensive programming: ensure photos is not None
            photos_list = full_gallery.photos or []
            existing_count = len(photos_list) - len(downloads_to_process)
            logger.debug(
                f"Gallery {gallery.title}: {len(downloads_to_process)} files to download, "
                f"{existing_count} files already exist"
            )
            
            # Download files with progress updates
            if downloads_to_process:
                download_results = await self.concurrent_downloader.download_files(
                    downloads_to_process,
                    gallery.title,
                    self.statistics_tracker
                )
                
                # Process results and update checkpoint tracking
                completed = 0
                failed = 0
                for result in download_results:
                    if result['success']:
                        completed += 1
                        # Mark file as completed in checkpoint
                        self.checkpoint_manager.mark_file_completed(result['file_path'])
                    else:
                        failed += 1
                        # Mark file as failed in checkpoint
                        self.checkpoint_manager.mark_file_failed(result['file_path'])
                
                # Log detailed error information for failed downloads
                if failed > 0:
                    logger.debug(f"Gallery {gallery.title} had {failed} failed downloads:")
                    for result in download_results:
                        if not result['success']:
                            error_details = {
                                'file_name': result.get('file_name', 'Unknown'),
                                'photo_id': result.get('photo_id', 'Unknown'),
                                'url': result.get('url', 'Unknown'),
                                'error': result.get('error', 'Unknown error'),
                                'attempts': result.get('attempts', 'Unknown'),
                                'file_size': result.get('expected_size', 'Unknown'),
                                'local_path': result.get('local_path', 'Unknown')
                            }
                            
                            # Check if this looks like a retrieval issue or server error
                            error_str = str(result.get('error', '')).lower()
                            should_retry = False
                            retry_reason = ""
                            
                            if 'timeout' in error_str and result.get('attempts', 0) >= 3:
                                should_retry = True
                                retry_reason = "Zenfolio retrieval timeout - image may be in processing queue"
                            elif 'server temporarily unavailable' in error_str or 'server error 5' in error_str:
                                should_retry = True
                                retry_reason = "Server temporarily unavailable"
                            elif 'bad gateway' in error_str or '502' in error_str:
                                should_retry = True
                                retry_reason = "Server gateway error"
                            elif 'service unavailable' in error_str or '503' in error_str:
                                should_retry = True
                                retry_reason = "Service temporarily unavailable"
                            
                            if should_retry:
                                # Add to retrieval queue for later retry
                                try:
                                    # Find the corresponding photo for more details
                                    photo_for_queue = None
                                    for photo in photos_list:
                                        if str(photo.id) == str(result.get('photo_id', '')):
                                            photo_for_queue = photo
                                            break
                                    
                                    if photo_for_queue:
                                        self.retrieval_queue.add_retrieval_item(
                                            photo_id=photo_for_queue.id,
                                            gallery_id=gallery.id,
                                            gallery_title=gallery.title,
                                            file_name=photo_for_queue.file_name,
                                            original_url=photo_for_queue.original_url,
                                            local_path=result.get('local_path', 'Unknown'),
                                            file_size=photo_for_queue.size or 0,
                                            mime_type=photo_for_queue.mime_type or 'unknown',
                                            error_message=f"{retry_reason}: {result.get('error', 'Unknown error')}"
                                        )
                                        # Note: Individual file retry queue additions are handled silently
                                        # The "(added to retry queue)" message is shown at gallery level
                                except Exception as queue_error:
                                    logger.debug(f"Failed to add item to retrieval queue: {queue_error}")
            else:
                download_results = []
                completed = 0
                failed = 0
            
            # Set completion info and complete the gallery progress display
            photos_list = full_gallery.photos or []
            already_existed = len(photos_list) - len(downloads_to_process)
            console_progress.set_completion_info(completed, already_existed, failed)
            console_progress.complete_gallery()
            
            # End gallery tracking
            gallery_duration = (datetime.now() - gallery_start_time).total_seconds()
            # Ensure duration is never negative (can happen with very fast operations)
            gallery_duration = max(0.0, gallery_duration)
            self.statistics_tracker.end_gallery(gallery.title)
            
            # Only log completion if there were actual downloads or errors (not for galleries with all existing files)
            if completed > 0 or failed > 0:
                log_gallery_complete(
                    gallery.title,
                    completed,
                    already_existed,
                    failed,
                    gallery_duration
                )
            
            # Save checkpoint after processing each gallery
            self.checkpoint_manager.save_checkpoint()
            
            return {
                'gallery_name': gallery.title,
                'success': True,
                'total_files': len(photos_list),
                'downloaded': completed,
                'failed': failed,
                'already_existed': len(photos_list) - len(downloads_to_process),
                'duration_seconds': gallery_duration,
                'local_path': str(local_path)
            }
            
        except Exception as e:
            logger.error(f"Failed to process gallery {gallery.title}: {e}")
            
            # End gallery tracking on error
            if self.current_gallery:
                self.statistics_tracker.end_gallery(gallery.title)
            
            return {
                'gallery_name': gallery.title,
                'success': False,
                'error': str(e),
                'local_path': str(local_path)
            }
        finally:
            # Always save checkpoint after processing a gallery (success or failure)
            self.checkpoint_manager.save_checkpoint()
            self.current_gallery = None
    
    def _should_download_file(self, download_info: DownloadInfo) -> bool:
        """Determine if a file should be downloaded.
        
        Args:
            download_info: Download information
            
        Returns:
            True if file should be downloaded
        """
        # Check checkpoint first
        if not self.checkpoint_manager.should_download_file(download_info.local_path):
            return False
        
        # Check if file should be re-downloaded based on integrity
        return self.integrity_checker.should_redownload(
            download_info,
            force_overwrite=self.settings.overwrite_existing
        )
    
    def _is_gallery_complete_with_cache(self, gallery: PhotoSet, gallery_output_dir: Path) -> tuple[bool, Optional[list]]:
        """Check if a gallery is complete using cache-first approach.
        
        Args:
            gallery: Gallery to check
            gallery_output_dir: Local directory for the gallery
            
        Returns:
            Tuple of (is_complete, cached_photos_data)
        """
        # Check if gallery directory exists
        if not gallery_output_dir.exists():
            logger.debug(f"Gallery directory does not exist: {gallery_output_dir}")
            return False, None
        
        # Count existing files in the gallery directory
        try:
            existing_files = list(gallery_output_dir.glob('*'))
            # Filter out directories and hidden files
            existing_files = [f for f in existing_files if f.is_file() and not f.name.startswith('.')]
            
            logger.debug(f"Found {len(existing_files)} files in {gallery.title} directory")
            
            # If no files exist, definitely not complete
            if len(existing_files) == 0:
                logger.debug(f"No files found in {gallery.title} - marking as incomplete")
                return False, None
            
            # Try to get cached photo metadata first (primary source of truth)
            try:
                from cache.cache_manager import CacheManager
                cache_manager = CacheManager(
                    cache_dir=Path(self.settings.cache_dir),
                    cache_ttl_hours=self.settings.cache_ttl_hours
                )
                cached_photos_data = cache_manager.load_photo_metadata(gallery.id)
                
                if cached_photos_data:
                    expected_count = len(cached_photos_data)
                    threshold = int(expected_count * 0.95)
                    logger.debug(f"Cache-first check for {gallery.title}: {len(existing_files)} files found, {expected_count} expected from cache, threshold={threshold}")
                    
                    # List existing files for debugging
                    file_names = [f.name for f in existing_files]
                    logger.debug(f"Existing files in {gallery.title}: {file_names}")
                    
                    # Check if we have all expected files (use exact match for better reliability)
                    if len(existing_files) >= expected_count:
                        logger.debug(f"Gallery {gallery.title} appears complete via cache check (exact match)")
                        return True, cached_photos_data
                    elif len(existing_files) >= threshold:
                        logger.debug(f"Gallery {gallery.title} appears complete via cache check (95% threshold)")
                        return True, cached_photos_data
                    else:
                        logger.debug(f"Gallery {gallery.title} appears incomplete: {len(existing_files)} files found, {expected_count} expected")
                        return False, cached_photos_data
                        
            except Exception as e:
                logger.debug(f"Failed to load cached photo metadata for {gallery.title}: {e}")
            
            # Fallback to hierarchy cache photo count
            expected_count = gallery.photo_count
            if expected_count > 0:
                if len(existing_files) >= expected_count * 0.95:
                    logger.debug(f"Gallery {gallery.title} appears complete via hierarchy cache: {len(existing_files)} files found, {expected_count} expected")
                    return True, None
                else:
                    logger.debug(f"Gallery {gallery.title} appears incomplete via hierarchy cache: {len(existing_files)} files found, {expected_count} expected")
                    return False, None
            
            # If we have files but no expected count, assume incomplete to be safe
            logger.debug(f"Gallery {gallery.title} has {len(existing_files)} files but no expected count - assuming incomplete")
            return False, None
                
        except Exception as e:
            logger.debug(f"Error checking gallery completeness for {gallery.title}: {e}")
            return False, None

    def _is_gallery_complete(self, gallery: PhotoSet, gallery_output_dir: Path) -> bool:
        """Check if a gallery is already 100% complete without making API calls.
        
        Args:
            gallery: Gallery to check
            gallery_output_dir: Local directory for the gallery
            
        Returns:
            True if gallery appears to be completely downloaded
        """
        is_complete, _ = self._is_gallery_complete_with_cache(gallery, gallery_output_dir)
        return is_complete

    def _get_skip_reason(self, download_info: DownloadInfo) -> str:
        """Get reason why a file is not being downloaded.
        
        Args:
            download_info: Download information
            
        Returns:
            Reason for not downloading
        """
        if self.checkpoint_manager.is_file_completed(download_info.local_path):
            return "previously downloaded successfully"
        elif self.checkpoint_manager.is_file_skipped(download_info.local_path):
            return "marked as skipped in previous session"
        elif Path(download_info.local_path).exists():
            return "file already exists and appears complete"
        else:
            return "unknown reason"
    
    async def analyze_galleries(self, root_group: Group) -> Dict[str, Any]:
        """Analyze galleries without downloading.
        
        Args:
            root_group: Root group to analyze
            
        Returns:
            Analysis results
        """
        galleries = await self._collect_galleries(root_group)
        
        total_photos = 0
        total_videos = 0
        total_size = 0
        
        for gallery_info in galleries:
            try:
                gallery = await self.client.load_photo_set(
                    gallery_info['gallery'].id,
                    InformationLevel.LEVEL2,
                    include_photos=True
                )
                
                for photo in gallery.photos:
                    if photo.is_video:
                        total_videos += 1
                    else:
                        total_photos += 1
                    
                    if photo.size > 0:
                        total_size += photo.size
                        
            except Exception as e:
                logger.debug(f"Failed to analyze gallery {gallery_info['gallery'].title}: {e}")
        
        return {
            'total_galleries': len(galleries),
            'total_photos': total_photos,
            'total_videos': total_videos,
            'total_size_mb': total_size / (1024 * 1024),
            'estimated_time': self._estimate_download_time(total_size, len(galleries))
        }
    
    def _estimate_download_time(self, total_bytes: int, file_count: int) -> str:
        """Estimate download time based on size and file count.
        
        Args:
            total_bytes: Total bytes to download
            file_count: Number of files
            
        Returns:
            Estimated time string
        """
        # Rough estimates based on typical download speeds and overhead
        estimated_speed_mbps = 5.0  # Conservative estimate
        overhead_per_file = 2.0  # Seconds overhead per file
        
        download_time = (total_bytes / (1024 * 1024)) / estimated_speed_mbps
        overhead_time = file_count * overhead_per_file
        total_time = download_time + overhead_time
        
        if total_time < 60:
            return f"{total_time:.0f} seconds"
        elif total_time < 3600:
            return f"{total_time / 60:.1f} minutes"
        else:
            return f"{total_time / 3600:.1f} hours"
    
    async def verify_existing_files(self, output_dir: Path) -> Dict[str, Any]:
        """Verify integrity of existing files.
        
        Args:
            output_dir: Directory to verify
            
        Returns:
            Verification results
        """
        # This would implement file verification logic
        # For now, return a placeholder
        return {
            'total_checked': 0,
            'valid_files': 0,
            'invalid_files': 0,
            'missing_files': 0
        }
    
    async def dry_run_analysis(
        self,
        root_group: Group,
        gallery_filter: Optional[str] = None,
        base_path: str = ""
    ) -> Dict[str, Any]:
        """Perform dry run analysis.
        
        Args:
            root_group: Root group to analyze
            gallery_filter: Optional gallery filter
            base_path: Optional base path to prepend to all gallery paths
            
        Returns:
            Dry run results
        """
        galleries = await self._collect_galleries(root_group, gallery_filter, base_path)
        
        files_to_download = 0
        files_to_skip = 0
        total_size = 0
        gallery_details = []
        
        # Use cached data for fast analysis - no API calls needed!
        logger.debug("Using cached gallery data for fast dry-run analysis...")
        
        for gallery_info in galleries:
            gallery = gallery_info['gallery']
            
            # Use cached photo count from hierarchy - no API call needed!
            photo_count = gallery.photo_count
            
            # Estimate downloads based on cached data
            # Most photos will likely be downloaded (conservative estimate)
            estimated_downloads = photo_count
            
            # Rough size estimation (average 5MB per high-quality photo)
            estimated_size_mb = photo_count * 5.0
            
            gallery_details.append({
                'name': gallery.title,
                'file_count': estimated_downloads,
                'skip_count': 0,  # Will know actual skips during real download
                'size_mb': estimated_size_mb,
                'photo_count': photo_count,
                'path': str(gallery_info['local_path'])
            })
            
            files_to_download += estimated_downloads
            total_size += estimated_size_mb * 1024 * 1024  # Convert to bytes
            
            logger.debug(f"Gallery '{gallery.title}': {photo_count} photos -> {estimated_downloads} estimated downloads")
        
        return {
            'galleries_count': len(galleries),
            'files_to_download': files_to_download,
            'files_to_skip': files_to_skip,
            'total_size_mb': total_size / (1024 * 1024),
            'galleries': gallery_details
        }
    
    async def list_galleries(
        self,
        root_group: Optional[Group] = None,
        show_details: bool = False,
        gallery_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all galleries with optional filtering and details.
        
        Args:
            root_group: Root group to list from (loads if None)
            show_details: Whether to include detailed information
            gallery_filter: Optional regex pattern to filter galleries
            
        Returns:
            List of gallery information dictionaries
        """
        if root_group is None:
            # Load user profile and hierarchy
            user_profile = await self.client.load_private_profile()
            root_group = await self.client.load_group_hierarchy(user_profile.login_name, force_refresh=False)
        
        # Get all galleries using the client's list method
        all_galleries = await self.client.list_galleries(root_group, show_details)
        
        # Apply filter if specified
        if gallery_filter:
            try:
                import re
                filtered_galleries = []
                for gallery in all_galleries:
                    if re.search(gallery_filter, gallery['title'], re.IGNORECASE):
                        filtered_galleries.append(gallery)
                return filtered_galleries
            except re.error as e:
                logger.debug(f"Invalid gallery filter regex: {e}")
                return all_galleries
        
        return all_galleries
    
    def stop(self) -> None:
        """Stop the download process."""
        self.is_running = False
        self.concurrent_downloader.stop()
        logger.debug("Download manager stop requested")