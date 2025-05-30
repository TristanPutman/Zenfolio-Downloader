# Zenfolio Downloader

A robust, feature-rich Python application for downloading photos and videos from Zenfolio galleries with advanced capabilities including resume functionality, concurrent downloads, interactive menus, batch processing, and comprehensive error handling.

## ✨ Features

### Core Functionality
- **🚀 Concurrent Downloads**: Download multiple files simultaneously with configurable concurrency
- **⏯️ Resume Capability**: Automatically resume interrupted downloads from where they left off
- **🔄 Intelligent Retry Logic**: Exponential backoff retry mechanism for failed downloads
- **📊 Progress Tracking**: Real-time progress bars, detailed statistics, and checkpoint management
- **🗂️ Cache System**: Gallery hierarchy caching to minimize API calls and improve performance
- **🛡️ Comprehensive Error Handling**: Detailed error reporting, logging, and graceful failure recovery
- **✅ File Integrity Verification**: Optional verification of downloaded files
- **🕒 Timestamp Preservation**: Maintain original file creation and modification timestamps

### User Interface Options
- **🎯 Interactive Menu Mode**: User-friendly menu system for browsing and selecting galleries
- **⚡ Command-Line Interface**: Full CLI with extensive options for automation and scripting
- **📦 Batch Processing**: Download entire archives or specific folder collections
- **🔍 Advanced Filtering**: Filter galleries by name patterns, IDs, or folder hierarchies

### Advanced Features
- **📋 Retrieval Queue Management**: Handle Zenfolio's retrieval queue for archived content
- **🏗️ Metadata Export**: Export complete gallery structure and metadata to JSON/CSV
- **🔧 Debug Tools**: Comprehensive debugging utilities for troubleshooting
- **⚙️ First-Time Setup**: Guided configuration wizard for new users
- **📈 Statistics & Analytics**: Detailed download statistics and progress reporting

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd zenfolio-downloader

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. First-Time Setup

Run the setup wizard to configure your credentials and preferences:

```bash
python main.py --setup
```

Or manually create your configuration:

```bash
# Copy the sample environment file
cp .env.sample .env

# Edit .env with your Zenfolio credentials
nano .env  # or your preferred editor
```

### 3. Basic Usage

#### Interactive Mode (Recommended for Beginners)
```bash
python main.py
```
Launches an interactive menu where you can browse folders, select galleries, and manage downloads.

#### Command-Line Mode
```bash
# Download all galleries
python main.py

# Download specific folder by ID
python main.py --folder-id 1234567890

# Download specific gallery by ID  
python main.py --gallery-id 9876543210

# Download with custom settings
python main.py --concurrent-downloads 4 --output-dir ./my-photos
```

## ⚙️ Configuration

### Environment Variables

The application uses a comprehensive `.env` configuration file. All settings are documented in [`.env.sample`](.env.sample):

#### 🔐 Required Credentials
```bash
ZENFOLIO_USERNAME=your_zenfolio_username
ZENFOLIO_PASSWORD=your_zenfolio_password
```

#### 📥 Download Settings
```bash
CONCURRENT_DOWNLOADS=8          # Simultaneous downloads (1-20)
DEFAULT_OUTPUT_DIR=./downloads  # Download destination
OVERWRITE_EXISTING=false        # Overwrite existing files
```

#### 🔄 Retry & Performance Settings
```bash
MAX_RETRIES=5                   # Maximum retry attempts (0-50)
INITIAL_BACKOFF_SECONDS=1.0     # Initial retry delay
MAX_BACKOFF_SECONDS=60.0        # Maximum retry delay
REQUEST_TIMEOUT=60              # API request timeout (5-300s)
DOWNLOAD_TIMEOUT=30             # File download timeout (10-300s)
CHUNK_SIZE=8192                 # Download chunk size in bytes
```

#### 📝 Logging Configuration
```bash
LOG_LEVEL=INFO                  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE=zenfolio_downloader.log # Log file path (empty to disable)
```

#### 🗄️ Cache Settings
```bash
CACHE_ENABLED=true              # Enable gallery hierarchy caching
CACHE_DIR=.zenfolio_cache       # Cache directory path
CACHE_TTL_HOURS=48              # Cache expiration time (1-168 hours)
```

#### 📁 File Management
```bash
VERIFY_INTEGRITY=true           # Verify downloaded file integrity
PRESERVE_TIMESTAMPS=true        # Maintain original file timestamps
```

## 🏗️ Project Structure

```
zenfolio-downloader/
├── 📄 main.py                     # Main application entry point
├── 📄 requirements.txt            # Python dependencies
├── 📄 .env.sample                 # Sample configuration file
├── 📄 .gitignore                  # Git ignore rules
├── 📁 api/                        # Zenfolio API client and models
│   ├── __init__.py
│   ├── exceptions.py              # API exception classes
│   ├── models.py                  # Data models (Gallery, Group, etc.)
│   └── zenfolio_client.py         # Main API client
├── 📁 auth/                       # Authentication management
│   ├── __init__.py
│   ├── token_manager.py           # Authentication token handling
│   └── zenfolio_auth.py           # Zenfolio authentication logic
├── 📁 cache/                      # Caching system
│   ├── __init__.py
│   └── cache_manager.py           # Gallery hierarchy caching
├── 📁 config/                     # Configuration management
│   ├── __init__.py
│   └── settings.py                # Settings validation and loading
├── 📁 download/                   # Download management
│   ├── __init__.py
│   ├── concurrent_downloader.py   # Concurrent download handling
│   ├── download_manager.py        # Main download orchestration
│   ├── integrity_checker.py       # File integrity verification
│   └── retry_manager.py           # Retry logic and backoff
├── 📁 filesystem/                 # File system utilities
│   ├── __init__.py
│   ├── directory_manager.py       # Directory creation and management
│   ├── duplicate_detector.py      # Duplicate file detection
│   └── file_manager.py            # File operations and metadata
├── 📁 logs/                       # Logging configuration
│   ├── __init__.py
│   └── logger.py                  # Logging setup and configuration
├── 📁 progress/                   # Progress tracking and checkpoints
│   ├── __init__.py
│   ├── checkpoint_manager.py      # Download checkpoint management
│   ├── console_progress.py        # Console progress display
│   ├── progress_tracker.py        # Progress tracking utilities
│   ├── retrieval_queue.py         # Zenfolio retrieval queue handling
│   └── statistics.py              # Download statistics tracking
└── 📁 utils/                      # Utility functions
    ├── __init__.py
    ├── constants.py               # Application constants
    ├── first_time_setup.py        # Initial setup wizard
    ├── helpers.py                 # General utility functions
    ├── interactive_menu.py        # Interactive menu system
    └── metadata_exporter.py       # Metadata export functionality

```

## 🎯 Usage Examples

### Command-Line Interface

#### Basic Operations
```bash
# List all available galleries
python main.py --list-galleries

# List only folders/groups
python main.py --list-folders --folder-depth 2

# Show detailed gallery information
python main.py --list-galleries --list-details --show-ids

# Perform dry run (show what would be downloaded)
python main.py --dry-run

# Show download statistics without downloading
python main.py --stats-only
```

#### Targeted Downloads
```bash
# Download specific folder and all its contents
python main.py --folder-id 1234567890

# Download specific gallery
python main.py --gallery-id 9876543210

# Download galleries matching a pattern
python main.py --galleries "Wedding.*2023"

# Download specific folder by name pattern
python main.py --folder "Marketing.*"
```

#### Advanced Options
```bash
# Resume interrupted download
python main.py --resume

# Force overwrite existing files
python main.py --overwrite

# Custom output directory and concurrency
python main.py --output-dir /path/to/photos --concurrent-downloads 12

# Verify existing files integrity
python main.py --verify-integrity

# Verify download completion
python main.py --verify

# Export complete metadata structure
python main.py --export-metadata --metadata-format json
```

#### Cache Management
```bash
# Refresh gallery hierarchy cache
python main.py --refresh-cache

# Show cache information
python main.py --cache-info

# Clear cache
python main.py --clear-cache
```

#### Debug Operations
```bash
# Debug single photo download
python main.py --debug-download 1234567890

# Debug first photo from gallery
python main.py --debug-gallery 9876543210

# Enable verbose logging
python main.py --log-level DEBUG
```

### Interactive Menu Mode

When run without arguments, the application launches an interactive menu:

```bash
python main.py
```

The interactive mode provides:
- **📂 Folder Browser**: Navigate through your Zenfolio hierarchy
- **🎯 Selective Downloads**: Choose specific folders or galleries
- **✅ Verification Tools**: Verify completed downloads
- **📋 Queue Management**: Process Zenfolio's retrieval queue
- **📊 Status Reports**: View download progress and statistics

## 🔧 Advanced Features

### Retrieval Queue Management

Zenfolio archives some content in a retrieval queue. The downloader can:
- **📋 Check Queue Status**: View pending items in the retrieval queue
- **⚡ Process Queue**: Download available items from the queue
- **📊 Queue Analytics**: Show detailed queue statistics

```bash
# Check retrieval queue status
python check_retrieval_queue.py

# Process retrieval queue (interactive mode)
python main.py  # Select "Process Retrieval Queue" from menu
```

### Metadata Export

Export complete gallery structure and metadata:

```bash
# Export to JSON format
python main.py --export-metadata --metadata-format json

# Export to CSV format  
python main.py --export-metadata --metadata-format csv

# Export to both formats
python main.py --export-metadata --metadata-format both
```

### Checkpoint System

The application automatically saves progress and can resume interrupted downloads:
- **💾 Auto-Save**: Progress saved after each gallery
- **🔄 Smart Resume**: Skips completed galleries on restart
- **📊 Progress Tracking**: Shows accurate completion status

```bash
# Clear checkpoint and start fresh
python main.py --clear-checkpoint

# Resume with explicit flag (default behavior)
python main.py --resume
```

## 🛠️ Troubleshooting

### Common Issues

#### 🔐 Authentication Problems
```bash
# Verify credentials in .env file
cat .env | grep ZENFOLIO

# Test authentication
python main.py --list-galleries
```

**Solutions:**
- Verify username and password in `.env`
- Check account access to galleries
- Ensure no special characters in credentials

#### ⏱️ Download Timeouts
```bash
# Increase timeouts for large files
DOWNLOAD_TIMEOUT=120
REQUEST_TIMEOUT=180
```

**Solutions:**
- Increase `DOWNLOAD_TIMEOUT` for large files
- Reduce `CONCURRENT_DOWNLOADS` if experiencing network issues
- Check network stability

#### 📁 Permission Errors
**Solutions:**
- Ensure output directory is writable: `chmod 755 ./downloads`
- Check disk space availability
- Verify file permissions for existing files

#### 🗄️ Cache Issues
```bash
# Clear and rebuild cache
python main.py --clear-cache
python main.py --refresh-cache
```

### Debug Tools

#### Enable Verbose Logging
```bash
# Set debug level in .env
LOG_LEVEL=DEBUG

# Or use command line
python main.py --log-level DEBUG
```

#### Debug Specific Downloads
```bash
# Debug single photo
python main.py --debug-download 1234567890

# Debug gallery
python main.py --debug-gallery 9876543210
```

#### Check Log Files
```bash
# Monitor logs in real-time
tail -f zenfolio_downloader.log

# Search for errors
grep -i error zenfolio_downloader.log
```

### Performance Optimization

#### Optimize Concurrent Downloads
```bash
# For fast connections
CONCURRENT_DOWNLOADS=12

# For slower connections or to be gentle on servers
CONCURRENT_DOWNLOADS=4
```

#### Cache Optimization
```bash
# Longer cache for stable galleries
CACHE_TTL_HOURS=168  # 1 week

# Shorter cache for frequently updated content
CACHE_TTL_HOURS=24   # 1 day
```

## 🔧 Development

### Requirements
- **Python**: 3.8+ (tested with 3.12.3)
- **Dependencies**: See [`requirements.txt`](requirements.txt)

### Key Dependencies
- **aiohttp**: Async HTTP client for API communication
- **pydantic**: Data validation and settings management
- **tqdm**: Progress bars and status display
- **click**: Command-line interface framework
- **loguru**: Advanced logging capabilities
- **tenacity**: Retry logic with exponential backoff

### Development Setup
```bash
# Install development dependencies (uncomment in requirements.txt)
pip install pytest pytest-asyncio black flake8 mypy

# Run code formatting
black .

# Run linting
flake8 .

# Run type checking
mypy .
```

### Architecture

The application follows a modular architecture with clear separation of concerns:

- **🔌 API Layer**: Handles Zenfolio API communication and authentication
- **📥 Download Layer**: Manages concurrent downloads and retry logic
- **💾 Storage Layer**: Handles file system operations and integrity checking
- **📊 Progress Layer**: Tracks progress, checkpoints, and statistics
- **🎛️ Interface Layer**: Provides CLI and interactive menu interfaces
- **⚙️ Configuration Layer**: Manages settings and environment variables

## 📚 Additional Documentation

- **[Architecture Plan](ARCHITECTURE_PLAN.md)**: Technical architecture overview
- **[Debug Guide](DEBUG_GUIDE.md)**: Comprehensive debugging information
- **[Gallery Listing](GALLERY_LISTING.md)**: Gallery structure documentation

## 🤝 Contributing

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes** with proper testing
4. **Follow code style**: Use `black` for formatting
5. **Add tests** if applicable
6. **Update documentation** as needed
7. **Submit a pull request**

### Code Style Guidelines
- Follow PEP 8 conventions
- Use type hints for all functions
- Add docstrings for public methods
- Keep functions focused and modular
- Use meaningful variable names

## 📄 License

[Add your license information here]

## 🆘 Support

For support, please:
1. **Check the troubleshooting section** above
2. **Review log files** for detailed error information
3. **Search existing issues** in the repository
4. **Create a new issue** with detailed information including:
   - Error messages and log excerpts
   - Configuration details (without credentials)
   - Steps to reproduce the issue
   - System information (OS, Python version)

## 🙏 Acknowledgments

- **Zenfolio**: For providing the API that makes this tool possible
- **Contributors**: Thanks to all who have contributed to this project
- **Community**: For feedback, bug reports, and feature suggestions