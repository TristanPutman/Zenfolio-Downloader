"""Helper utility functions for Zenfolio downloader."""

import re
from pathlib import Path
from typing import Union
from .constants import BYTES_PER_KB, BYTES_PER_MB, BYTES_PER_GB


def format_bytes(bytes_value: int) -> str:
    """Format bytes into human-readable string.
    
    Args:
        bytes_value: Number of bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB", "2.3 GB")
    """
    if bytes_value < BYTES_PER_KB:
        return f"{bytes_value} B"
    elif bytes_value < BYTES_PER_MB:
        return f"{bytes_value / BYTES_PER_KB:.1f} KB"
    elif bytes_value < BYTES_PER_GB:
        return f"{bytes_value / BYTES_PER_MB:.1f} MB"
    else:
        return f"{bytes_value / BYTES_PER_GB:.1f} GB"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted string (e.g., "1m 30s", "2h 15m")
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        if remaining_seconds < 1:
            return f"{minutes}m"
        else:
            return f"{minutes}m {remaining_seconds:.0f}s"
    else:
        hours = int(seconds // 3600)
        remaining_minutes = int((seconds % 3600) // 60)
        if remaining_minutes == 0:
            return f"{hours}h"
        else:
            return f"{hours}h {remaining_minutes}m"


def sanitize_path(path_str: str) -> str:
    """Sanitize a path string for safe filesystem usage.
    
    Args:
        path_str: Path string to sanitize
        
    Returns:
        Sanitized path string
    """
    # Remove or replace invalid characters
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    sanitized = re.sub(invalid_chars, '_', path_str)
    
    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip('. ')
    
    # Ensure it's not empty
    if not sanitized:
        sanitized = "unnamed"
    
    return sanitized


def calculate_eta(completed: int, total: int, elapsed_seconds: float) -> str:
    """Calculate estimated time of arrival for completion.
    
    Args:
        completed: Number of completed items
        total: Total number of items
        elapsed_seconds: Time elapsed so far
        
    Returns:
        Formatted ETA string
    """
    if completed == 0 or total == 0:
        return "Unknown"
    
    if completed >= total:
        return "Complete"
    
    rate = completed / elapsed_seconds
    remaining = total - completed
    eta_seconds = remaining / rate
    
    return format_duration(eta_seconds)


def calculate_progress_percentage(completed: int, total: int) -> float:
    """Calculate progress percentage.
    
    Args:
        completed: Number of completed items
        total: Total number of items
        
    Returns:
        Progress percentage (0.0 to 100.0)
    """
    if total == 0:
        return 0.0
    return min(100.0, (completed / total) * 100.0)


def truncate_string(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate a string to maximum length with optional suffix.
    
    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncating
        
    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    
    if len(suffix) >= max_length:
        return text[:max_length]
    
    return text[:max_length - len(suffix)] + suffix


def safe_filename(filename: str, max_length: int = 255) -> str:
    """Create a safe filename from any string.
    
    Args:
        filename: Original filename
        max_length: Maximum filename length
        
    Returns:
        Safe filename
    """
    # Remove path separators and invalid characters
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', filename)
    
    # Remove leading/trailing dots and spaces
    safe = safe.strip('. ')
    
    # Truncate if too long
    if len(safe) > max_length:
        name, ext = Path(safe).stem, Path(safe).suffix
        max_name_length = max_length - len(ext)
        safe = name[:max_name_length] + ext
    
    # Ensure we have a valid filename
    if not safe or safe in ['.', '..']:
        safe = "unnamed"
    
    return safe


def parse_content_range(content_range: str) -> tuple:
    """Parse HTTP Content-Range header.
    
    Args:
        content_range: Content-Range header value
        
    Returns:
        Tuple of (start, end, total) or (None, None, None) if invalid
    """
    # Format: "bytes start-end/total"
    match = re.match(r'bytes (\d+)-(\d+)/(\d+|\*)', content_range)
    if match:
        start = int(match.group(1))
        end = int(match.group(2))
        total = int(match.group(3)) if match.group(3) != '*' else None
        return start, end, total
    
    return None, None, None


def is_valid_url(url: str) -> bool:
    """Check if a string is a valid URL.
    
    Args:
        url: URL string to validate
        
    Returns:
        True if URL appears valid
    """
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return url_pattern.match(url) is not None


def get_file_extension(filename: str) -> str:
    """Get file extension from filename.
    
    Args:
        filename: Filename to extract extension from
        
    Returns:
        File extension (lowercase, without dot)
    """
    return Path(filename).suffix.lower().lstrip('.')


def is_image_file(filename: str) -> bool:
    """Check if filename represents an image file.
    
    Args:
        filename: Filename to check
        
    Returns:
        True if filename has image extension
    """
    from .constants import SUPPORTED_IMAGE_EXTENSIONS
    extension = get_file_extension(filename)
    return extension in SUPPORTED_IMAGE_EXTENSIONS


def is_video_file(filename: str) -> bool:
    """Check if filename represents a video file.
    
    Args:
        filename: Filename to check
        
    Returns:
        True if filename has video extension
    """
    from .constants import SUPPORTED_VIDEO_EXTENSIONS
    extension = get_file_extension(filename)
    return extension in SUPPORTED_VIDEO_EXTENSIONS


def create_progress_bar(
    completed: int,
    total: int,
    width: int = 50,
    fill_char: str = '█',
    empty_char: str = '░'
) -> str:
    """Create a text-based progress bar.
    
    Args:
        completed: Number of completed items
        total: Total number of items
        width: Width of progress bar in characters
        fill_char: Character for completed portion
        empty_char: Character for remaining portion
        
    Returns:
        Progress bar string
    """
    if total == 0:
        percentage = 0
    else:
        percentage = min(100, (completed / total) * 100)
    
    filled_width = int(width * percentage / 100)
    bar = fill_char * filled_width + empty_char * (width - filled_width)
    
    return f"[{bar}] {percentage:.1f}%"


def merge_dicts(*dicts) -> dict:
    """Merge multiple dictionaries, with later ones taking precedence.
    
    Args:
        *dicts: Dictionaries to merge
        
    Returns:
        Merged dictionary
    """
    result = {}
    for d in dicts:
        if d:
            result.update(d)
    return result


def ensure_list(value: Union[list, tuple, str, None]) -> list:
    """Ensure a value is a list.
    
    Args:
        value: Value to convert to list
        
    Returns:
        List containing the value(s)
    """
    if value is None:
        return []
    elif isinstance(value, (list, tuple)):
        return list(value)
    else:
        return [value]