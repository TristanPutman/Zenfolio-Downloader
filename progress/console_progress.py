"""Console progress display for Zenfolio downloads."""

import sys
import time
from datetime import datetime
from typing import Optional


class ConsoleProgress:
    """Manages clean console progress display with real-time percentage updates."""
    
    def __init__(self):
        self.current_gallery: Optional[str] = None
        self.parent_path: Optional[str] = None
        self.total_items: int = 0
        self.completed_items: int = 0
        self.last_update_time: float = 0
        self.update_interval: float = 0.1  # Update every 100ms
        self.start_time: float = 0
        self.completion_info: Optional[str] = None
        self.retry_info: Optional[str] = None
        
    def start_gallery(self, gallery_name: str, total_items: int, parent_path: str = None) -> None:
        """Start tracking progress for a new gallery."""
        # Clear any previous line and start fresh
        if self.current_gallery:
            self._clear_line()
            
        self.current_gallery = gallery_name
        self.parent_path = parent_path or gallery_name
        self.total_items = total_items
        self.completed_items = 0
        self.last_update_time = time.time()
        self.start_time = time.time()
        self.completion_info = None
        self.retry_info = None
        
        # Show initial 0% progress
        self._update_display()
        
    def update_progress(self, completed: int) -> None:
        """Update the progress display."""
        self.completed_items = completed
        
        # Throttle updates to avoid flickering
        current_time = time.time()
        if current_time - self.last_update_time >= self.update_interval:
            self._update_display()
            self.last_update_time = current_time
            
    def set_completion_info(self, downloaded: int, already_existed: int, failed: int) -> None:
        """Set completion information for display."""
        duration = time.time() - self.start_time
        # Ensure duration is never negative (can happen with very fast operations)
        duration = max(0.0, duration)
        total_processed = downloaded + already_existed
        self.completion_info = f"{total_processed}/{self.total_items} files in {duration:.2f}s"
        
    def set_retry_info(self, retry_count: int, max_retries: int) -> None:
        """Set retry information for display."""
        if retry_count > 0:
            self.retry_info = f"(retry {retry_count}/{max_retries})"
        else:
            self.retry_info = None
        self._update_display()
        
    def set_skip_info(self, reason: str = "will be added to retry queue") -> None:
        """Set skip information for display."""
        self.retry_info = f"({reason})"
        self._update_display()
        
    def clear_retry_info(self) -> None:
        """Clear retry information."""
        self.retry_info = None
        self._update_display()
        
    def complete_gallery(self) -> None:
        """Mark the current gallery as complete and move to next line."""
        if self.current_gallery:
            # Show final 100% with completion info and move to next line
            self.completed_items = self.total_items
            self._update_display()
            print()  # Move to next line
            
        self.current_gallery = None
        self.total_items = 0
        self.completed_items = 0
        self.completion_info = None
        
    def _update_display(self) -> None:
        """Update the console display with current progress."""
        if not self.current_gallery:
            return
            
        percentage = (self.completed_items / self.total_items * 100) if self.total_items > 0 else 0
        
        # Create progress line with consistent formatting and padding
        bar_width = 20
        filled_width = int(bar_width * percentage / 100)
        bar = '█' * filled_width + '░' * (bar_width - filled_width)
        
        # Get current timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Format with consistent padding for alignment
        # Combine parent path and gallery name, then truncate the whole thing
        if self.parent_path:
            full_path = f"{self.parent_path}: {self.current_gallery}"
        else:
            full_path = self.current_gallery
        
        # Truncate the entire path to a consistent length for alignment
        gallery_part = f"{full_path[:80]:<80}"
        items_part = f"({self.total_items:>3} items):"
        bar_part = f"[{bar}]"
        percentage_part = f"{percentage:>3.0f}%"
        
        progress_line = f"{timestamp} | {gallery_part} {items_part} {bar_part} {percentage_part}"
        
        # Add retry info if available (during retries)
        if self.retry_info:
            progress_line += f" {self.retry_info}"
        
        # Add completion info if available (when at 100%)
        if self.completion_info and percentage >= 100:
            progress_line += f" - {self.completion_info}"
        
        # Clear line and write new progress
        self._clear_line()
        sys.stdout.write(progress_line)
        sys.stdout.flush()
        
    def _clear_line(self) -> None:
        """Clear the current console line."""
        sys.stdout.write('\r' + ' ' * 120 + '\r')  # Clear with spaces then return to start
        sys.stdout.flush()
        
    def cleanup(self) -> None:
        """Clean up any remaining progress display."""
        if self.current_gallery:
            self._clear_line()


# Global instance for use throughout the application
console_progress = ConsoleProgress()