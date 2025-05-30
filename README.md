# Zenfolio Downloader

A robust Python application for downloading photos and videos from Zenfolio galleries with advanced features like resume capability, concurrent downloads, and comprehensive error handling.

## Features

- **Concurrent Downloads**: Download multiple files simultaneously for faster processing
- **Resume Capability**: Automatically resume interrupted downloads from where they left off
- **Retry Logic**: Intelligent retry mechanism with exponential backoff for failed downloads
- **Progress Tracking**: Real-time progress bars and detailed statistics
- **Cache System**: Gallery hierarchy caching to avoid redundant API calls
- **Error Handling**: Comprehensive error reporting and logging
- **File Integrity**: Optional verification of downloaded files
- **Timestamp Preservation**: Maintain original file timestamps

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd zenfolio-downloader

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Copy the sample environment file and configure your settings:

```bash
cp .env.sample .env
```

Edit `.env` with your Zenfolio credentials and preferences:

```bash
# Required: Your Zenfolio account credentials
ZENFOLIO_USERNAME=your_username
ZENFOLIO_PASSWORD=your_password

# Optional: Customize download settings
CONCURRENT_DOWNLOADS=8
DEFAULT_OUTPUT_DIR=./downloads
LOG_LEVEL=INFO
```

### 3. Usage

Run the interactive downloader:

```bash
python main.py
```

Or use the batch download script:

```bash
./download_complete_archive.sh
```

## Configuration

### Environment Variables

The application uses environment variables for configuration. All settings can be customized in the `.env` file:

#### Required Settings
- `ZENFOLIO_USERNAME`: Your Zenfolio username
- `ZENFOLIO_PASSWORD`: Your Zenfolio password

#### Download Settings
- `CONCURRENT_DOWNLOADS`: Number of simultaneous downloads (1-20, default: 8)
- `DEFAULT_OUTPUT_DIR`: Where to save downloaded files (default: ./downloads)
- `OVERWRITE_EXISTING`: Whether to overwrite existing files (default: false)

#### Performance Settings
- `MAX_RETRIES`: Maximum retry attempts for failed downloads (default: 5)
- `REQUEST_TIMEOUT`: API request timeout in seconds (default: 60)
- `DOWNLOAD_TIMEOUT`: File download timeout in seconds (default: 30)

#### Logging
- `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `LOG_FILE`: Path to log file (default: zenfolio_downloader.log)

#### Cache Settings
- `CACHE_ENABLED`: Enable gallery caching (default: true)
- `CACHE_DIR`: Cache directory path (default: .zenfolio_cache)
- `CACHE_TTL_HOURS`: Cache expiration time in hours (default: 24)

See `.env.sample` for all available configuration options with detailed descriptions.

## Project Structure

```
zenfolio-downloader/
├── .env.sample              # Sample environment configuration
├── .gitignore              # Git ignore rules
├── main.py                 # Main application entry point
├── requirements.txt        # Python dependencies
├── api/                    # Zenfolio API client and models
├── auth/                   # Authentication management
├── cache/                  # Caching system
├── config/                 # Configuration management
├── download/               # Download management and retry logic
├── filesystem/             # File system utilities
├── logs/                   # Logging configuration
├── progress/               # Progress tracking and checkpoints
└── utils/                  # Utility functions
```

## Features in Detail

### Resume Capability
The downloader automatically saves progress and can resume interrupted downloads:
- Tracks completed, failed, and skipped files
- Saves checkpoint after each gallery
- Shows accurate progress on restart

### Concurrent Downloads
- Configurable number of simultaneous downloads
- Intelligent rate limiting to avoid overwhelming the server
- Progress tracking for each concurrent download

### Error Handling
- Comprehensive retry logic with exponential backoff
- Detailed error logging with HTTP status codes
- Graceful handling of network timeouts and server errors

### Caching System
- Caches gallery hierarchy to avoid redundant API calls
- Configurable cache expiration
- Automatic cache invalidation for updated content

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Verify your Zenfolio username and password in `.env`
   - Check if your account has access to the galleries

2. **Download Timeouts**
   - Increase `DOWNLOAD_TIMEOUT` for large files
   - Reduce `CONCURRENT_DOWNLOADS` if experiencing network issues

3. **Permission Errors**
   - Ensure the output directory is writable
   - Check file permissions for existing files

### Logs

Check the log file (default: `zenfolio_downloader.log`) for detailed error information:

```bash
tail -f zenfolio_downloader.log
```

Set `LOG_LEVEL=DEBUG` in `.env` for verbose logging.

## Development

### Requirements
- Python 3.8+
- See `requirements.txt` for package dependencies

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

[Add your license information here]

## Support

[Add support contact information here]