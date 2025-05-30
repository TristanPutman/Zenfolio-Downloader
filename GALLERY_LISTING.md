# Gallery Listing Functionality

This document describes the gallery listing functionality that has been implemented in the Zenfolio Python Downloader.

## Overview

The application now provides comprehensive gallery listing capabilities that allow you to view all available galleries in your Zenfolio account without downloading any files.

## Command Line Usage

### Basic Gallery Listing

```bash
# List all galleries (basic info)
python main.py --list-galleries

# List galleries with detailed information
python main.py --list-galleries --list-details

# List galleries matching a pattern
python main.py --list-galleries --galleries "Wedding.*2024"

# List galleries with details and filter
python main.py --list-galleries --list-details --galleries "Portfolio.*"
```

### Command Line Options

- `--list-galleries`: Enable gallery listing mode
- `--list-details`: Include detailed information (photo counts, sizes, etc.)
- `--galleries PATTERN`: Filter galleries using regex pattern

## Output Format

### Basic Listing

```
=== GALLERY LIST (15 galleries) ===

  1. Wedding Smith 2024
     ID: 12345
     Path: Weddings/Wedding Smith 2024
     Type: Gallery
     Photos: 150
     Created: 2024-03-15

  2. Portfolio Landscapes
     ID: 12346
     Path: Portfolio/Portfolio Landscapes
     Type: Gallery
     Photos: 45
     Created: 2024-02-10
```

### Detailed Listing

When using `--list-details`, additional information is shown:

```
  1. Wedding Smith 2024
     ID: 12345
     Path: Weddings/Wedding Smith 2024
     Type: Gallery
     Photos: 150
     Created: 2024-03-15
     Caption: Beautiful wedding ceremony and reception
     Actual Photos: 148
     Videos: 2
     Size: 2,450.75 MB
```

### Summary Information

With detailed listing, a summary is provided:

```
=== SUMMARY ===
Total galleries: 15
Total photos: 1,250
Total videos: 25
Total size: 15,678.50 MB
```

## Programmatic Usage

You can also use the gallery listing functionality programmatically:

```python
import asyncio
from config.settings import get_settings
from api.zenfolio_client import ZenfolioClient
from download.download_manager import DownloadManager
from progress.checkpoint_manager import CheckpointManager
from progress.statistics import StatisticsTracker

async def list_galleries():
    settings = get_settings()
    
    # Initialize components
    checkpoint_manager = CheckpointManager(settings)
    statistics_tracker = StatisticsTracker()
    
    async with ZenfolioClient(settings) as client:
        # Authenticate
        await client.authenticate(
            settings.zenfolio_username,
            settings.zenfolio_password
        )
        
        # Initialize download manager
        download_manager = DownloadManager(
            settings=settings,
            client=client,
            checkpoint_manager=checkpoint_manager,
            statistics_tracker=statistics_tracker
        )
        
        # List galleries
        galleries = await download_manager.list_galleries(
            show_details=True,
            gallery_filter="Wedding.*2024"
        )
        
        for gallery in galleries:
            print(f"Gallery: {gallery['title']} ({gallery['photo_count']} photos)")

# Run the listing
asyncio.run(list_galleries())
```

## API Methods

### ZenfolioClient.list_galleries()

```python
async def list_galleries(
    self, 
    root_group: Optional[Group] = None, 
    show_details: bool = False
) -> List[Dict[str, Any]]
```

Lists all galleries in a hierarchical structure.

**Parameters:**
- `root_group`: Root group to list from (loads if None)
- `show_details`: Whether to include detailed information

**Returns:**
List of gallery information dictionaries with keys:
- `id`: Gallery ID
- `title`: Gallery title
- `path`: Full path in hierarchy
- `type`: Gallery type (Gallery/Collection)
- `photo_count`: Number of photos
- `created_on`: Creation date (ISO format)
- `last_updated`: Last update date (ISO format)

When `show_details=True`, additional keys are included:
- `caption`: Gallery caption
- `actual_photo_count`: Actual number of photos loaded
- `total_size_mb`: Total size in MB
- `video_count`: Number of videos
- `photo_count_actual`: Number of photos (excluding videos)

### DownloadManager.list_galleries()

```python
async def list_galleries(
    self, 
    root_group: Optional[Group] = None, 
    show_details: bool = False,
    gallery_filter: Optional[str] = None
) -> List[Dict[str, Any]]
```

Lists galleries with optional filtering.

**Parameters:**
- `root_group`: Root group to list from
- `show_details`: Whether to include detailed information
- `gallery_filter`: Optional regex pattern to filter galleries

## Implementation Details

### XML Parsing

The implementation includes comprehensive XML parsing for Zenfolio API responses:

- **User Profile Parsing**: Extracts user information from `LoadPrivateProfile` responses
- **Group Hierarchy Parsing**: Recursively parses group structures from `LoadGroupHierarchy` responses
- **PhotoSet Parsing**: Extracts gallery information from `LoadPhotoSet` responses
- **Photo Parsing**: Parses individual photo metadata

### Error Handling

The implementation includes robust error handling:

- **Fallback Responses**: If XML parsing fails, fallback objects are created
- **Graceful Degradation**: Individual gallery parsing failures don't stop the entire listing
- **Detailed Error Reporting**: Errors are logged with context for debugging

### Performance Considerations

- **Lazy Loading**: Basic gallery info is loaded first, detailed info only when requested
- **Concurrent Processing**: Multiple galleries can be processed concurrently
- **Caching**: Authentication tokens are cached to avoid repeated authentication

## Authentication

Gallery listing requires authentication with your Zenfolio account. Ensure your credentials are properly configured in the `.env` file:

```env
ZENFOLIO_USERNAME=your_username
ZENFOLIO_PASSWORD=your_password
```

## Filtering

Gallery filtering uses Python regular expressions. Examples:

```bash
# Galleries starting with "Wedding"
--galleries "^Wedding"

# Galleries containing "2024"
--galleries ".*2024.*"

# Galleries ending with "Portfolio"
--galleries ".*Portfolio$"

# Case-insensitive matching (default)
--galleries "wedding.*smith"
```

## Integration with Existing Features

The gallery listing functionality integrates seamlessly with existing features:

- **Download Filtering**: Use the same `--galleries` pattern for both listing and downloading
- **Statistics**: Gallery listing provides the foundation for download statistics
- **Dry Run**: Gallery listing enhances the dry run functionality
- **Logging**: All gallery operations are properly logged

## Troubleshooting

### Common Issues

1. **Authentication Errors**: Verify credentials in `.env` file
2. **Network Timeouts**: Increase timeout settings for slow connections
3. **Empty Gallery List**: Check account permissions and gallery visibility
4. **Regex Errors**: Verify gallery filter patterns are valid regex

### Debug Mode

Enable debug logging for detailed information:

```bash
python main.py --list-galleries --log-level DEBUG
```

This will show detailed XML parsing information and API communication details.