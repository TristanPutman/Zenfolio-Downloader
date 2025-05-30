"""Data models for Zenfolio API objects."""

from datetime import datetime
from enum import Enum
from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator


class PhotoSetType(str, Enum):
    """Photo set type enumeration."""
    GALLERY = "Gallery"
    COLLECTION = "Collection"


class InformationLevel(int, Enum):
    """Information level for API requests."""
    LEVEL1 = 1
    LEVEL2 = 2


class AuthChallenge(BaseModel):
    """Authentication challenge from Zenfolio API."""
    challenge: bytes
    password_salt: bytes


class User(BaseModel):
    """Zenfolio user model."""
    id: int
    login_name: str
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    primary_email: Optional[str] = None
    bio_photo: Optional[str] = None
    bio: Optional[str] = None
    views: Optional[int] = None
    gallery_count: Optional[int] = None
    collection_count: Optional[int] = None
    photo_count: Optional[int] = None
    created_on: Optional[datetime] = None
    last_updated: Optional[datetime] = None


class Photo(BaseModel):
    """Zenfolio photo model."""
    id: int
    title: str
    file_name: str
    uploaded_on: datetime
    taken_on: Optional[datetime] = None
    width: int
    height: int
    size: int  # File size in bytes
    is_video: bool = False
    mime_type: Optional[str] = None
    original_url: str
    sequence: Optional[int] = None
    access_descriptor: Optional[dict] = None
    
    # Video-specific fields
    duration: Optional[float] = None  # Duration in seconds for videos
    video_url: Optional[str] = None  # Highest quality video URL
    
    @field_validator('size')
    @classmethod
    def validate_size(cls, v):
        """Ensure size is never None."""
        if v is None:
            return 0
        return v
    
    @property
    def is_downloadable(self) -> bool:
        """Check if the photo/video is downloadable."""
        return bool(self.original_url or self.video_url)
    
    @property
    def download_url(self) -> Optional[str]:
        """Get the best available download URL."""
        # For videos, Zenfolio's API only provides preview URLs with size suffixes
        # like "-200.mp4". Full-quality video downloads may not be available
        # through the public API. We use the available URL but note the limitation.
        if self.original_url:
            return self.original_url
        elif self.is_video and self.video_url:
            return self.video_url
        return None
    
    def debug_info(self) -> dict:
        """Get debug information about this photo."""
        return {
            'id': self.id,
            'title': self.title,
            'file_name': self.file_name,
            'is_video': self.is_video,
            'size': self.size,
            'mime_type': self.mime_type,
            'original_url': self.original_url,
            'video_url': self.video_url,
            'download_url': self.download_url,
            'is_downloadable': self.is_downloadable,
            'access_descriptor': self.access_descriptor
        }


class PhotoSet(BaseModel):
    """Zenfolio photo set (gallery or collection) model."""
    id: int
    title: str
    caption: Optional[str] = None
    type: PhotoSetType
    created_on: datetime
    last_updated: Optional[datetime] = None
    photo_count: int = 0
    photos: List[Photo] = Field(default_factory=list)
    access_descriptor: Optional[dict] = None
    
    @property
    def is_gallery(self) -> bool:
        """Check if this is a gallery (not a collection)."""
        return self.type == PhotoSetType.GALLERY


class GroupElement(BaseModel):
    """Base class for group elements (groups or photo sets)."""
    id: int
    title: str
    created_on: datetime
    last_updated: Optional[datetime] = None
    access_descriptor: Optional[dict] = None


class Group(GroupElement):
    """Zenfolio group model."""
    caption: Optional[str] = None
    elements: List[Union['Group', PhotoSet]] = Field(default_factory=list)
    
    @property
    def galleries(self) -> List[PhotoSet]:
        """Get all galleries in this group."""
        return [elem for elem in self.elements if isinstance(elem, PhotoSet) and elem.is_gallery]
    
    @property
    def subgroups(self) -> List['Group']:
        """Get all subgroups in this group."""
        return [elem for elem in self.elements if isinstance(elem, Group)]


# Update forward references
Group.model_rebuild()


class PhotoResult(BaseModel):
    """Result from photo search operations."""
    photos: List[Photo]
    total_count: int


class PhotoSetResult(BaseModel):
    """Result from photo set search operations."""
    photo_sets: List[PhotoSet]
    total_count: int


class DownloadInfo(BaseModel):
    """Information about a file to be downloaded."""
    photo: Photo
    local_path: str
    url: str
    expected_size: Optional[int] = None
    
    @property
    def file_extension(self) -> str:
        """Get the file extension from the filename."""
        return self.photo.file_name.split('.')[-1].lower() if '.' in self.photo.file_name else ''
    
    @property
    def is_video_file(self) -> bool:
        """Check if this is a video file based on extension."""
        video_extensions = {'mp4', 'mov', 'avi', 'mkv', 'wmv', 'flv', 'webm', 'm4v'}
        return self.file_extension in video_extensions or self.photo.is_video


class DownloadProgress(BaseModel):
    """Progress information for downloads."""
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    total_bytes: int = 0
    downloaded_bytes: int = 0
    current_file: Optional[str] = None
    start_time: Optional[datetime] = None
    
    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.completed_files / self.total_files) * 100
    
    @property
    def bytes_percentage(self) -> float:
        """Calculate bytes completion percentage."""
        if self.total_bytes == 0:
            return 0.0
        return (self.downloaded_bytes / self.total_bytes) * 100
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        if not self.start_time:
            return 0.0
        return (datetime.now() - self.start_time).total_seconds()
    
    @property
    def download_speed_mbps(self) -> float:
        """Calculate download speed in MB/s."""
        elapsed = self.elapsed_time
        if elapsed == 0:
            return 0.0
        return (self.downloaded_bytes / (1024 * 1024)) / elapsed