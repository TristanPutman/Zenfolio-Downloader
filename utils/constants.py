"""Constants for Zenfolio downloader."""

# Application constants
DEFAULT_USER_AGENT = "Zenfolio-Python-Downloader/1.0"
MAX_FILENAME_LENGTH = 255
CHUNK_SIZE_DEFAULT = 8192

# Supported file extensions
SUPPORTED_IMAGE_EXTENSIONS = {
    'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'tif',
    'webp', 'raw', 'cr2', 'nef', 'arw', 'dng', 'orf'
}

SUPPORTED_VIDEO_EXTENSIONS = {
    'mp4', 'mov', 'avi', 'mkv', 'wmv', 'flv', 'webm',
    'm4v', '3gp', 'ogv', 'mts', 'm2ts'
}

# API constants
ZENFOLIO_API_BASE_URL = "https://api.zenfolio.com/api/1.8/zfapi.asmx"
SOAP_ACTION_BASE = "http://www.zenfolio.com/api/1.8/"

# Download constants
DEFAULT_CONCURRENT_DOWNLOADS = 8
MIN_CONCURRENT_DOWNLOADS = 1
MAX_CONCURRENT_DOWNLOADS = 20

# Retry constants
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF = 1.0
DEFAULT_MAX_BACKOFF = 60.0

# File size constants
BYTES_PER_KB = 1024
BYTES_PER_MB = 1024 * 1024
BYTES_PER_GB = 1024 * 1024 * 1024

# Time constants
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400

# Progress update intervals
PROGRESS_UPDATE_INTERVAL = 1.0  # seconds
CHECKPOINT_SAVE_INTERVAL = 30.0  # seconds

# Logging constants
LOG_FORMAT_CONSOLE = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)

LOG_FORMAT_FILE = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
    "{name}:{function}:{line} | {message}"
)

# Error messages
ERROR_AUTHENTICATION_FAILED = "Authentication failed"
ERROR_NETWORK_TIMEOUT = "Network timeout"
ERROR_RATE_LIMIT_EXCEEDED = "API rate limit exceeded"
ERROR_INSUFFICIENT_DISK_SPACE = "Insufficient disk space"
ERROR_FILE_NOT_FOUND = "File not found"
ERROR_PERMISSION_DENIED = "Permission denied"

# Success messages
SUCCESS_AUTHENTICATION = "Authentication successful"
SUCCESS_DOWNLOAD_COMPLETE = "Download completed successfully"
SUCCESS_CHECKPOINT_SAVED = "Checkpoint saved"
SUCCESS_CHECKPOINT_LOADED = "Checkpoint loaded"