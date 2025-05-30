"""Manages Zenfolio image retrieval queue for delayed downloads."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from logs.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalItem:
    """Represents an image in Zenfolio's retrieval queue."""
    photo_id: int
    gallery_id: int
    gallery_title: str
    file_name: str
    original_url: str
    local_path: str
    file_size: int
    mime_type: str
    added_at: str
    last_attempt: str
    attempt_count: int
    error_message: str


class RetrievalQueueManager:
    """Manages the queue of images waiting for Zenfolio retrieval."""
    
    def __init__(self, queue_file: Path = None):
        """Initialize the retrieval queue manager.
        
        Args:
            queue_file: Path to the retrieval queue JSON file
        """
        self.queue_file = queue_file or Path("zenfolio_retrieval_queue.json")
        self.queue: List[RetrievalItem] = []
        self.load_queue()
    
    def load_queue(self) -> None:
        """Load the retrieval queue from file."""
        try:
            if self.queue_file.exists():
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.queue = [RetrievalItem(**item) for item in data]
                logger.debug(f"Loaded {len(self.queue)} items from retrieval queue")
            else:
                self.queue = []
                logger.debug("No existing retrieval queue found")
        except Exception as e:
            logger.error(f"Failed to load retrieval queue: {e}")
            self.queue = []
    
    def save_queue(self) -> None:
        """Save the retrieval queue to file."""
        try:
            # Create directory if it doesn't exist
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to JSON-serializable format
            data = [asdict(item) for item in self.queue]
            
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved {len(self.queue)} items to retrieval queue")
        except Exception as e:
            logger.error(f"Failed to save retrieval queue: {e}")
    
    def add_retrieval_item(
        self,
        photo_id: int,
        gallery_id: int,
        gallery_title: str,
        file_name: str,
        original_url: str,
        local_path: str,
        file_size: int,
        mime_type: str,
        error_message: str
    ) -> None:
        """Add an item to the retrieval queue.
        
        Args:
            photo_id: Zenfolio photo ID
            gallery_id: Zenfolio gallery ID
            gallery_title: Gallery title for organization
            file_name: Original file name
            original_url: Zenfolio URL that timed out
            local_path: Where the file should be saved
            file_size: Expected file size in bytes
            mime_type: File MIME type
            error_message: Error that occurred
        """
        now = datetime.now().isoformat()
        
        # Check if item already exists (update instead of duplicate)
        existing_item = None
        for item in self.queue:
            if item.photo_id == photo_id:
                existing_item = item
                break
        
        if existing_item:
            # Update existing item
            existing_item.last_attempt = now
            existing_item.attempt_count += 1
            existing_item.error_message = error_message
            logger.debug(f"Updated retrieval queue item for photo {photo_id} (attempt {existing_item.attempt_count})")
        else:
            # Add new item
            item = RetrievalItem(
                photo_id=photo_id,
                gallery_id=gallery_id,
                gallery_title=gallery_title,
                file_name=file_name,
                original_url=original_url,
                local_path=local_path,
                file_size=file_size,
                mime_type=mime_type,
                added_at=now,
                last_attempt=now,
                attempt_count=1,
                error_message=error_message
            )
            self.queue.append(item)
            logger.debug(f"Added photo {photo_id} ({file_name}) to retrieval queue")
        
        self.save_queue()
    
    def add_gallery_retry_item(
        self,
        gallery_id: int,
        gallery_title: str,
        error_message: str
    ) -> None:
        """Add a gallery-level retry item to the queue.
        
        This is used when an entire gallery fails to load (e.g., API timeout)
        and needs to be retried later.
        
        Args:
            gallery_id: Zenfolio gallery ID
            gallery_title: Gallery title for organization
            error_message: Error that occurred
        """
        now = datetime.now().isoformat()
        
        # Create a special gallery-level retry item with photo_id = 0
        # This will be handled differently during retry processing
        item = RetrievalItem(
            photo_id=0,  # Special marker for gallery-level retry
            gallery_id=gallery_id,
            gallery_title=gallery_title,
            file_name=f"GALLERY_RETRY_{gallery_id}",
            original_url="",
            local_path="",
            file_size=0,
            mime_type="gallery/retry",
            added_at=now,
            last_attempt=now,
            attempt_count=1,
            error_message=error_message
        )
        self.queue.append(item)
        logger.debug(f"Added gallery {gallery_title} (ID: {gallery_id}) to retry queue")
        self.save_queue()
    
    def remove_completed_item(self, photo_id: int) -> bool:
        """Remove an item from the queue after successful download.
        
        Args:
            photo_id: Photo ID to remove (0 for gallery-level retries)
            
        Returns:
            True if item was found and removed
        """
        for i, item in enumerate(self.queue):
            if item.photo_id == photo_id:
                removed_item = self.queue.pop(i)
                if photo_id == 0:
                    logger.debug(f"Removed completed gallery retry {removed_item.gallery_title} from retrieval queue")
                else:
                    logger.debug(f"Removed completed photo {photo_id} ({removed_item.file_name}) from retrieval queue")
                self.save_queue()
                return True
        return False
    
    def remove_gallery_retry_items(self, gallery_id: int) -> int:
        """Remove all gallery-level retry items for a specific gallery.
        
        Args:
            gallery_id: Gallery ID to remove retry items for
            
        Returns:
            Number of items removed
        """
        original_count = len(self.queue)
        self.queue = [
            item for item in self.queue
            if not (item.photo_id == 0 and item.gallery_id == gallery_id)
        ]
        removed_count = original_count - len(self.queue)
        
        if removed_count > 0:
            logger.debug(f"Removed {removed_count} gallery retry items for gallery {gallery_id}")
            self.save_queue()
        
        return removed_count
    
    def get_queue_summary(self) -> Dict[str, Any]:
        """Get a summary of the retrieval queue.
        
        Returns:
            Dictionary with queue statistics
        """
        if not self.queue:
            return {
                'total_items': 0,
                'galleries': {},
                'oldest_item': None,
                'newest_item': None
            }
        
        # Group by gallery
        galleries = {}
        for item in self.queue:
            if item.gallery_title not in galleries:
                galleries[item.gallery_title] = {
                    'count': 0,
                    'total_size': 0,
                    'items': []
                }
            galleries[item.gallery_title]['count'] += 1
            galleries[item.gallery_title]['total_size'] += item.file_size
            galleries[item.gallery_title]['items'].append({
                'file_name': item.file_name,
                'added_at': item.added_at,
                'attempt_count': item.attempt_count
            })
        
        # Find oldest and newest items
        sorted_queue = sorted(self.queue, key=lambda x: x.added_at)
        oldest_item = sorted_queue[0] if sorted_queue else None
        newest_item = sorted_queue[-1] if sorted_queue else None
        
        return {
            'total_items': len(self.queue),
            'galleries': galleries,
            'oldest_item': {
                'file_name': oldest_item.file_name,
                'gallery_title': oldest_item.gallery_title,
                'added_at': oldest_item.added_at,
                'attempt_count': oldest_item.attempt_count
            } if oldest_item else None,
            'newest_item': {
                'file_name': newest_item.file_name,
                'gallery_title': newest_item.gallery_title,
                'added_at': newest_item.added_at,
                'attempt_count': newest_item.attempt_count
            } if newest_item else None
        }
    
    def get_items_for_retry(self, max_age_hours: int = 24) -> List[RetrievalItem]:
        """Get items that are ready for retry.
        
        Args:
            max_age_hours: Only retry items older than this many hours
            
        Returns:
            List of items ready for retry
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        retry_items = []
        
        for item in self.queue:
            try:
                last_attempt = datetime.fromisoformat(item.last_attempt)
                if last_attempt < cutoff_time:
                    retry_items.append(item)
            except ValueError:
                # If we can't parse the date, include it for retry
                retry_items.append(item)
        
        return retry_items
    
    def clear_old_items(self, max_age_days: int = 30) -> int:
        """Remove items older than specified days.
        
        Args:
            max_age_days: Remove items older than this many days
            
        Returns:
            Number of items removed
        """
        cutoff_time = datetime.now() - timedelta(days=max_age_days)
        original_count = len(self.queue)
        
        self.queue = [
            item for item in self.queue
            if datetime.fromisoformat(item.added_at) > cutoff_time
        ]
        
        removed_count = original_count - len(self.queue)
        if removed_count > 0:
            logger.debug(f"Removed {removed_count} old items from retrieval queue")
            self.save_queue()
        
        return removed_count