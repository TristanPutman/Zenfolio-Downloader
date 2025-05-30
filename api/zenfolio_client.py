"""Zenfolio API client implementation."""

import asyncio
import base64
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
import aiohttp
from xml.etree import ElementTree as ET
from urllib.parse import urljoin

from config.settings import Settings
from auth.zenfolio_auth import ZenfolioAuth
from auth.token_manager import TokenManager
from .models import (
    User, Group, PhotoSet, Photo, AuthChallenge,
    InformationLevel, PhotoSetType, DownloadInfo
)
from .exceptions import (
    ZenfolioAPIError, AuthenticationError, RateLimitError,
    NetworkError, InvalidResponseError, ResourceNotFoundError,
    PermissionError, ServerError
)
from logs.logger import get_logger, log_authentication_success, log_authentication_failure

logger = get_logger(__name__)


def _format_error_message(exception: Exception) -> str:
    """Format exception message for logging, handling empty messages."""
    error_msg = str(exception)
    if not error_msg or error_msg.strip() == "":
        return f"{type(exception).__name__}: {repr(exception)}"
    return error_msg


class ZenfolioClient:
    """Zenfolio API client with authentication and error handling."""
    
    def __init__(self, settings: Settings):
        """Initialize the Zenfolio client.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.auth = ZenfolioAuth()
        self.token_manager = TokenManager(cache_file=".zenfolio_token_cache")
        self.session: Optional[aiohttp.ClientSession] = None
        
        # API endpoints
        self.api_base_url = settings.zenfolio_api_url
        self.soap_action_base = "http://www.zenfolio.com/api/1.8/"
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def _ensure_session(self) -> None:
        """Ensure aiohttp session is created."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'User-Agent': 'Zenfolio-Python-Downloader/1.0',
                    'Content-Type': 'text/xml; charset=utf-8'
                }
            )
    
    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def authenticate(self, username: str, password: str, use_cache: bool = True) -> bool:
        """Authenticate with Zenfolio API.
        
        Args:
            username: Zenfolio username
            password: Zenfolio password
            use_cache: Whether to use cached token if available
            
        Returns:
            True if authentication successful
            
        Raises:
            AuthenticationError: If authentication fails
        """
        try:
            # Validate credentials
            self.auth.validate_credentials(username, password)
            
            # Try to load cached token first
            if use_cache and self.token_manager.load_cached_token(username):
                token = self.token_manager.token
                if token:
                    self.auth.set_token(token)
                    log_authentication_success(username)
                    return True
            
            # Get authentication challenge
            challenge = await self._get_challenge(username)
            
            # Compute challenge response
            proof = self.auth.compute_challenge_response(challenge, password)
            
            # Authenticate with challenge and proof
            token = await self._authenticate_with_challenge(challenge.challenge, proof)
            
            if token:
                self.auth.set_token(token)
                self.token_manager.set_token(token, username)
                log_authentication_success(username)
                return True
            else:
                raise AuthenticationError("Authentication failed - no token received")
                
        except Exception as e:
            log_authentication_failure(username, e)
            self.auth.handle_auth_error(e)
            return False
    
    async def _get_challenge(self, username: str) -> AuthChallenge:
        """Get authentication challenge from API.
        
        Args:
            username: Username to get challenge for
            
        Returns:
            Authentication challenge
        """
        soap_body = f"""
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <GetChallenge xmlns="http://www.zenfolio.com/api/1.8">
                    <loginName>{username}</loginName>
                </GetChallenge>
            </soap:Body>
        </soap:Envelope>
        """
        
        response_data = await self._make_soap_request("GetChallenge", soap_body)
        
        # Parse challenge response
        try:
            challenge_elem = response_data.find('.//{http://www.zenfolio.com/api/1.8}GetChallengeResult')
            if challenge_elem is None:
                raise InvalidResponseError("Challenge element not found in response")
            
            challenge_b64 = challenge_elem.find('.//{http://www.zenfolio.com/api/1.8}Challenge').text
            salt_b64 = challenge_elem.find('.//{http://www.zenfolio.com/api/1.8}PasswordSalt').text
            
            challenge_bytes = base64.b64decode(challenge_b64)
            salt_bytes = base64.b64decode(salt_b64)
            
            return AuthChallenge(challenge=challenge_bytes, password_salt=salt_bytes)
            
        except Exception as e:
            raise InvalidResponseError(f"Failed to parse challenge response: {e}")
    
    async def _authenticate_with_challenge(self, challenge: bytes, proof: bytes) -> str:
        """Authenticate using challenge and proof.
        
        Args:
            challenge: Challenge bytes
            proof: Computed proof bytes
            
        Returns:
            Authentication token
        """
        challenge_b64 = base64.b64encode(challenge).decode('utf-8')
        proof_b64 = base64.b64encode(proof).decode('utf-8')
        
        soap_body = f"""
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <Authenticate xmlns="http://www.zenfolio.com/api/1.8">
                    <challenge>{challenge_b64}</challenge>
                    <proof>{proof_b64}</proof>
                </Authenticate>
            </soap:Body>
        </soap:Envelope>
        """
        
        response_data = await self._make_soap_request("Authenticate", soap_body)
        
        # Parse authentication response
        try:
            token_elem = response_data.find('.//{http://www.zenfolio.com/api/1.8}AuthenticateResult')
            if token_elem is None or not token_elem.text:
                raise AuthenticationError("No authentication token in response")
            
            return token_elem.text
            
        except Exception as e:
            raise AuthenticationError(f"Failed to parse authentication response: {e}")
    
    async def _make_soap_request(self, action: str, soap_body: str, timeout: Optional[int] = None) -> ET.Element:
        """Make a SOAP request to the Zenfolio API.
        
        Args:
            action: SOAP action name
            soap_body: SOAP request body
            timeout: Optional timeout override for this request
            
        Returns:
            Parsed XML response
        """
        await self._ensure_session()
        
        headers = {
            'SOAPAction': f'"{self.soap_action_base}{action}"',
            'Content-Type': 'text/xml; charset=utf-8'
        }
        
        # Add authentication headers if available
        auth_headers = self.auth.get_auth_headers()
        headers.update(auth_headers)
        
        # Debug logging for SOAP requests
        logger.debug(f"Making SOAP request: {action}")
        logger.debug(f"Request URL: {self.api_base_url}")
        logger.debug(f"Request headers: {headers}")
        # Always log request body in debug mode
        logger.debug(f"Request body: {soap_body}")
        
        try:
            # Use custom timeout if provided, otherwise use session default
            request_timeout = None
            if timeout:
                request_timeout = aiohttp.ClientTimeout(total=timeout)
            
            async with self.session.post(
                self.api_base_url,
                data=soap_body.encode('utf-8'),
                headers=headers,
                timeout=request_timeout
            ) as response:
                
                # Debug logging for response
                logger.debug(f"Response status: {response.status}")
                logger.debug(f"Response headers: {dict(response.headers)}")
                
                # Handle HTTP errors with enhanced debugging
                if response.status == 401:
                    response_text = await response.text()
                    logger.error(f"Authentication error - Response: {response_text[:500]}")
                    raise AuthenticationError("Authentication required or token expired")
                elif response.status == 403:
                    response_text = await response.text()
                    logger.error(f"Permission error - Response: {response_text[:500]}")
                    raise PermissionError("Access forbidden")
                elif response.status == 404:
                    response_text = await response.text()
                    logger.error(f"Not found error - Response: {response_text[:500]}")
                    raise ResourceNotFoundError("API endpoint", action)
                elif response.status == 429:
                    retry_after = float(response.headers.get('Retry-After', 60))
                    response_text = await response.text()
                    logger.debug(f"Rate limit error - Retry after: {retry_after}s - Response: {response_text[:500]}")
                    raise RateLimitError(f"Rate limit exceeded", retry_after=retry_after)
                elif response.status >= 500:
                    response_text = await response.text()
                    logger.error(f"Server error {response.status} for action '{action}' - Response: {response_text[:1000]}")
                    raise ServerError(f"Server error: {response.status} - {response_text[:200]}")
                elif response.status != 200:
                    response_text = await response.text()
                    logger.error(f"HTTP error {response.status} for action '{action}' - Response: {response_text[:500]}")
                    raise ZenfolioAPIError(f"HTTP {response.status}: {response.reason}")
                
                # Parse XML response
                response_text = await response.text()
                # Always log response body in debug mode
                logger.debug(f"Response body: {response_text}")
                
                try:
                    return ET.fromstring(response_text)
                except ET.ParseError as e:
                    logger.error(f"XML parse error for action '{action}' - Response: {response_text[:1000]}")
                    raise InvalidResponseError(f"Invalid XML response: {e}")
                
        except aiohttp.ClientError as e:
            logger.error(f"Network error for action '{action}': {e}")
            raise NetworkError(f"Network error: {e}", original_error=e)
    
    async def load_private_profile(self) -> User:
        """Load the authenticated user's private profile.
        
        Returns:
            User profile information
        """
        if not self.auth.is_authenticated:
            raise AuthenticationError("Must be authenticated to load profile")
        
        soap_body = """
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <LoadPrivateProfile xmlns="http://www.zenfolio.com/api/1.8" />
            </soap:Body>
        </soap:Envelope>
        """
        
        response_data = await self._make_soap_request("LoadPrivateProfile", soap_body)
        
        # Parse user profile from XML response
        try:
            user_elem = response_data.find('.//{http://www.zenfolio.com/api/1.8}LoadPrivateProfileResult')
            if user_elem is None:
                raise InvalidResponseError("User profile element not found in response")
            
            return self._parse_user_element(user_elem)
            
        except Exception as e:
            logger.warning(f"Failed to parse user profile, using fallback: {e}")
            # Fallback to basic user object
            return User(
                id=0,
                login_name=self.settings.zenfolio_username,
                display_name=self.settings.zenfolio_username
            )
    
    async def load_group_hierarchy(self, login_name: str, force_refresh: bool = False) -> Group:
        """Load the group hierarchy for a user.
        
        Args:
            login_name: User's login name
            force_refresh: Force refresh from API, bypassing cache
            
        Returns:
            Root group with hierarchy
        """
        from cache.cache_manager import CacheManager
        
        cache_manager = CacheManager(
            cache_dir=Path(self.settings.cache_dir),
            cache_ttl_hours=self.settings.cache_ttl_hours
        )
        
        # Try to load from raw API cache first (unless force refresh)
        raw_xml_response = None
        if not force_refresh:
            raw_xml_response = cache_manager.load_raw_api_cache(login_name)
        
        # If no cached raw response, fetch from API
        if raw_xml_response is None:
            logger.debug("Fetching fresh group hierarchy from API...")
            soap_body = f"""
            <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
                <soap:Body>
                    <LoadGroupHierarchy xmlns="http://www.zenfolio.com/api/1.8">
                        <loginName>{login_name}</loginName>
                    </LoadGroupHierarchy>
                </soap:Body>
            </soap:Envelope>
            """
            
            response_data = await self._make_soap_request("LoadGroupHierarchy", soap_body)
            
            # Convert XML response back to string for caching
            import xml.etree.ElementTree as ET
            raw_xml_response = ET.tostring(response_data, encoding='unicode')
            
            # Cache the raw API response
            cache_manager.save_raw_api_cache(login_name, raw_xml_response)
        else:
            logger.debug("Using cached raw API response")
        
        # Parse group hierarchy from XML response
        try:
            import xml.etree.ElementTree as ET
            response_data = ET.fromstring(raw_xml_response)
            
            group_elem = response_data.find('.//{http://www.zenfolio.com/api/1.8}LoadGroupHierarchyResult')
            if group_elem is None:
                raise InvalidResponseError("Group hierarchy element not found in response")
            
            return self._parse_group_element(group_elem)
            
        except Exception as e:
            logger.warning(f"Failed to parse group hierarchy, using fallback: {e}")
            # Fallback to basic group object
            return Group(
                id=0,
                title="Root",
                created_on=datetime.now(),
                elements=[]
            )
    
    async def load_photo_set(self, photo_set_id: int, level: InformationLevel = InformationLevel.LEVEL2,
                           include_photos: bool = True) -> PhotoSet:
        """Load a photo set using the reliable photos-only approach that bypasses LoadPhotoSet.
        
        Args:
            photo_set_id: ID of the photo set to load
            level: Information level to load
            include_photos: Whether to include photos
            
        Returns:
            PhotoSet with photos (if include_photos=True) or metadata only
        """
        # Always use the photos-separately approach since LoadPhotoSet is unreliable
        photo_set = await self._load_photo_set_with_photos_separately(photo_set_id, level)
        
        # If photos are not requested, clear them but keep the metadata
        if not include_photos:
            photo_set.photos = []
        
        return photo_set
    
    async def _load_photo_set_with_photos_separately(self, photo_set_id: int, level: InformationLevel) -> PhotoSet:
        """Load photo set by bypassing LoadPhotoSet entirely and using LoadPhotoSetPhotos + cached metadata."""
        logger.debug(f"Loading photo set {photo_set_id} using photos-only approach (bypassing LoadPhotoSet)")
        
        # Create a minimal photo set from cached hierarchy data or defaults
        # We'll try to get metadata from the cached hierarchy if available
        photo_set = await self._create_photo_set_from_cache_or_default(photo_set_id)
        
        # Load photos using LoadPhotoSetPhotos (this method works reliably)
        try:
            photos = await self._load_photo_set_photos_safely(photo_set_id, photo_set.photo_count)
            photo_set.photos = photos
            # Update photo count based on actual photos loaded
            photo_set.photo_count = len(photos)
            logger.debug(f"Successfully loaded {len(photos)} photos for photo set {photo_set_id}")
        except Exception as e:
            logger.warning(f"Failed to load photos for photo set {photo_set_id}: {_format_error_message(e)}")
            # Leave photos empty if we can't load them
            photo_set.photos = []
            photo_set.photo_count = 0
        
        return photo_set
    
    async def _create_photo_set_from_cache_or_default(self, photo_set_id: int) -> PhotoSet:
        """Create a PhotoSet object from cached hierarchy data or use defaults."""
        try:
            # Try to find the photo set in cached hierarchy data
            from cache.cache_manager import CacheManager
            cache_manager = CacheManager(
                cache_dir=Path(self.settings.cache_dir),
                cache_ttl_hours=self.settings.cache_ttl_hours
            )
            
            # Try to load from cache and find the photo set
            cached_hierarchy = cache_manager.load_processed_cache(self.settings.zenfolio_username)
            if cached_hierarchy:
                photo_set_info = self._find_photo_set_in_hierarchy(cached_hierarchy, photo_set_id)
                if photo_set_info:
                    logger.debug(f"Found photo set {photo_set_id} in cached hierarchy: {photo_set_info.get('title', 'Unknown')}")
                    return PhotoSet(
                        id=photo_set_id,
                        title=photo_set_info.get('title', f'Gallery {photo_set_id}'),
                        caption=photo_set_info.get('caption'),
                        type=PhotoSetType.GALLERY if photo_set_info.get('type') == 'Gallery' else PhotoSetType.COLLECTION,
                        created_on=datetime.fromisoformat(photo_set_info['created_on']) if photo_set_info.get('created_on') else datetime.now(),
                        last_updated=datetime.fromisoformat(photo_set_info['last_updated']) if photo_set_info.get('last_updated') else None,
                        photo_count=photo_set_info.get('photo_count', 0),
                        photos=[]
                    )
        except Exception as e:
            logger.debug(f"Could not load photo set {photo_set_id} from cache: {e}")
        
        # Fallback to default photo set
        logger.debug(f"Creating default photo set for {photo_set_id}")
        return PhotoSet(
            id=photo_set_id,
            title=f"Gallery {photo_set_id}",
            type=PhotoSetType.GALLERY,
            created_on=datetime.now(),
            photo_count=0,
            photos=[]
        )
    
    def _find_photo_set_in_hierarchy(self, hierarchy_data: dict, photo_set_id: int) -> dict:
        """Recursively find a photo set in the hierarchy data."""
        if not hierarchy_data:
            return None
            
        # Check if this is the photo set we're looking for
        if hierarchy_data.get('id') == photo_set_id and hierarchy_data.get('type') in ['Gallery', 'Collection']:
            return hierarchy_data
        
        # Search in elements (subgroups and photo sets)
        elements = hierarchy_data.get('elements', [])
        for element in elements:
            if isinstance(element, dict):
                result = self._find_photo_set_in_hierarchy(element, photo_set_id)
                if result:
                    return result
        
        return None
    
    async def _load_photo_set_photos_safely(self, photo_set_id: int, estimated_total: int) -> List[Photo]:
        """Load photos from a photo set safely, handling server-side XML parsing issues."""
        
        # Check cache first to avoid API calls
        from cache.cache_manager import CacheManager
        cache_manager = CacheManager(
            cache_dir=Path(self.settings.cache_dir),
            cache_ttl_hours=self.settings.cache_ttl_hours
        )
        
        cached_photos_data = cache_manager.load_photo_metadata(photo_set_id)
        if cached_photos_data:
            logger.debug(f"Loading {len(cached_photos_data)} photos for gallery {photo_set_id} from cache")
            # Convert cached data back to Photo objects
            photos = []
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
                        uploaded_on=datetime.fromisoformat(photo_data['uploaded_on']) if photo_data['uploaded_on'] else None,
                        original_url=photo_data['original_url'],
                        is_video=photo_data.get('is_video', False),
                        sequence=photo_data.get('sequence', None)
                    )
                    photos.append(photo)
                except Exception as e:
                    logger.warning(f"Failed to deserialize cached photo: {_format_error_message(e)}")
            
            if photos:
                return photos
        
        # Cache miss or invalid cache - load from API
        logger.debug(f"Loading photos for gallery {photo_set_id} from API (cache miss)")
        photos = []
        
        # If we don't know the photo count, try to discover it by probing
        if estimated_total == 0:
            estimated_total = await self._discover_photo_count(photo_set_id)
        
        # Start with smaller batches for problematic galleries
        batch_size = 10  # Smaller initial batch size to isolate XML issues
        consecutive_empty_batches = 0
        max_empty_batches = 5  # Allow more empty batches before giving up
        
        start_index = 0
        while start_index < estimated_total or consecutive_empty_batches < max_empty_batches:
            # Dynamically adjust batch size based on success rate
            current_batch_size = min(batch_size, max(estimated_total - start_index, 1))
            
            try:
                batch_photos = await self._load_photo_set_photos_batch(photo_set_id, start_index, current_batch_size)
                if batch_photos:
                    photos.extend(batch_photos)
                    consecutive_empty_batches = 0
                    # Increase batch size on success, but cap it
                    batch_size = min(batch_size + 5, 50)
                    logger.debug(f"Successfully loaded {len(batch_photos)} photos starting at index {start_index}, new batch size: {batch_size}")
                else:
                    consecutive_empty_batches += 1
                    logger.debug(f"Empty batch at index {start_index}, consecutive empty: {consecutive_empty_batches}")
                    
            except Exception as e:
                # First log as debug - we'll upgrade to warning only if fallback also fails
                logger.debug(f"Batch load failed at {start_index} (size {current_batch_size}): {_format_error_message(e)}, trying individual loading")
                # Reduce batch size on failure
                batch_size = max(1, batch_size // 2)
                logger.debug(f"Reducing batch size to {batch_size} due to errors")
                
                # Try loading photos individually in this batch
                individual_photos = await self._load_photos_individually(photo_set_id, start_index, min(current_batch_size, 5))
                if individual_photos:
                    photos.extend(individual_photos)
                    consecutive_empty_batches = 0
                    logger.debug(f"Individual loading succeeded: recovered {len(individual_photos)} photos at index {start_index}")
                else:
                    consecutive_empty_batches += 1
                    # Only warn if both batch AND individual loading failed
                    logger.debug(f"Both batch and individual loading failed at {start_index} (size {current_batch_size}): {_format_error_message(e)}")
            
            start_index += current_batch_size
            
            # Safety break to prevent infinite loops
            if start_index > 10000:  # Reasonable upper limit
                logger.warning(f"Reached safety limit of 10000 photos for photo set {photo_set_id}")
                break
        
        logger.debug(f"Loaded {len(photos)} photos from photo set {photo_set_id} (estimated: {estimated_total})")
        
        # Save to cache for future use
        if photos:
            try:
                cache_manager.save_photo_metadata(photo_set_id, photos)
            except Exception as e:
                logger.warning(f"Failed to save photo metadata to cache: {_format_error_message(e)}")
        
        return photos
    
    async def _discover_photo_count(self, photo_set_id: int) -> int:
        """Try to discover the actual photo count by probing with different batch sizes."""
        logger.debug(f"Discovering photo count for photo set {photo_set_id}")
        
        # Try common photo counts first
        test_counts = [50, 100, 200, 500, 1000]
        
        for test_count in test_counts:
            try:
                # Try to load a small batch at the test position
                test_photos = await self._load_photo_set_photos_batch(photo_set_id, test_count - 1, 1)
                if test_photos:
                    logger.debug(f"Found photos at index {test_count - 1}, continuing search")
                    continue
                else:
                    # No photos at this position, so the count is likely less than test_count
                    logger.debug(f"No photos found at index {test_count - 1}, estimated count: {test_count}")
                    return test_count
            except Exception as e:
                logger.debug(f"Error testing photo count {test_count}: {e}")
                # If we get an error, assume the count is less than this
                return test_count
        
        # If we get here, there are likely more than 1000 photos
        logger.debug(f"Photo set {photo_set_id} appears to have more than 1000 photos, using 2000 as estimate")
        return 2000
    
    async def _load_photo_set_photos_batch(self, photo_set_id: int, start_index: int, count: int) -> List[Photo]:
        """Load a batch of photos from a photo set."""
        soap_body = f"""
        <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
            <soap:Body>
                <LoadPhotoSetPhotos xmlns="http://www.zenfolio.com/api/1.8">
                    <photoSetId>{photo_set_id}</photoSetId>
                    <startingIndex>{start_index}</startingIndex>
                    <numberOfPhotos>{count}</numberOfPhotos>
                </LoadPhotoSetPhotos>
            </soap:Body>
        </soap:Envelope>
        """
        
        # Use longer timeout for photo loading operations since they can take longer
        response_data = await self._make_soap_request("LoadPhotoSetPhotos", soap_body, timeout=self.settings.download_timeout)
        
        # Parse photos from XML response
        photos_elem = response_data.find('.//{http://www.zenfolio.com/api/1.8}LoadPhotoSetPhotosResult')
        if photos_elem is None:
            return []
        
        photos = []
        for photo_elem in photos_elem.findall('.//{http://www.zenfolio.com/api/1.8}Photo'):
            try:
                photo = self._parse_photo_element(photo_elem)
                photos.append(photo)
            except Exception as e:
                logger.warning(f"Failed to parse individual photo in batch: {_format_error_message(e)}")
        
        return photos
    
    async def _load_photos_individually(self, photo_set_id: int, start_index: int, count: int) -> List[Photo]:
        """Load photos individually when batch loading fails due to server-side XML issues."""
        photos = []
        consecutive_failures = 0
        max_consecutive_failures = 5  # Stop after 5 consecutive failures
        
        for i in range(count):
            try:
                batch_photos = await self._load_photo_set_photos_batch(photo_set_id, start_index + i, 1)
                if batch_photos:
                    photos.extend(batch_photos)
                    consecutive_failures = 0  # Reset failure counter on success
                    logger.debug(f"Successfully loaded individual photo at index {start_index + i}")
                else:
                    consecutive_failures += 1
                    logger.debug(f"No photo found at index {start_index + i}, consecutive failures: {consecutive_failures}")
                    
            except Exception as e:
                consecutive_failures += 1
                logger.debug(f"Failed to load individual photo at index {start_index + i}: {_format_error_message(e)}")
                
            # If we have too many consecutive failures, stop trying
            if consecutive_failures >= max_consecutive_failures:
                logger.debug(f"Stopping individual photo loading after {max_consecutive_failures} consecutive failures")
                break
                # Skip this photo since we can't load it due to server-side XML parsing problems
                continue
        
        return photos
    
    def get_download_info(self, photo: Photo, output_dir: str) -> DownloadInfo:
        """Get download information for a photo.
        
        Args:
            photo: Photo to download
            output_dir: Output directory path
            
        Returns:
            Download information
        """
        from pathlib import Path
        
        local_path = str(Path(output_dir) / photo.file_name)
        download_url = photo.download_url
        
        if not download_url:
            raise ValueError(f"No download URL available for photo: {photo.file_name}")
        
        return DownloadInfo(
            photo=photo,
            local_path=local_path,
            url=download_url,
            expected_size=photo.size if photo.size > 0 else None
        )
    
    def _parse_user_element(self, user_elem: ET.Element) -> User:
        """Parse a User element from XML.
        
        Args:
            user_elem: XML element containing user data
            
        Returns:
            User object
        """
        namespace = "http://www.zenfolio.com/api/1.8"
        
        def get_text(elem, tag: str, default: Any = None) -> Any:
            """Get text content from a child element."""
            child = elem.find(f'.//{{{namespace}}}{tag}')
            if child is None:
                child = elem.find(f'.//{tag}')  # Try without namespace
            return child.text if child is not None and child.text else default
        
        def get_int(elem, tag: str, default: int = 0) -> int:
            """Get integer content from a child element."""
            text = get_text(elem, tag)
            try:
                return int(text) if text else default
            except (ValueError, TypeError):
                return default
        
        def get_datetime(elem, tag: str) -> Optional[datetime]:
            """Get datetime content from a child element."""
            text = get_text(elem, tag)
            if not text:
                return None
            try:
                # Parse ISO format datetime
                return datetime.fromisoformat(text.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return None
        
        return User(
            id=get_int(user_elem, 'Id'),
            login_name=get_text(user_elem, 'LoginName', ''),
            display_name=get_text(user_elem, 'DisplayName'),
            first_name=get_text(user_elem, 'FirstName'),
            last_name=get_text(user_elem, 'LastName'),
            primary_email=get_text(user_elem, 'PrimaryEmail'),
            bio_photo=get_text(user_elem, 'BioPhoto'),
            bio=get_text(user_elem, 'Bio'),
            views=get_int(user_elem, 'Views'),
            gallery_count=get_int(user_elem, 'GalleryCount'),
            collection_count=get_int(user_elem, 'CollectionCount'),
            photo_count=get_int(user_elem, 'PhotoCount'),
            created_on=get_datetime(user_elem, 'CreatedOn'),
            last_updated=get_datetime(user_elem, 'LastUpdated')
        )
    
    def _parse_group_element(self, group_elem: ET.Element) -> Group:
        """Parse a Group element from XML.
        
        Args:
            group_elem: XML element containing group data
            
        Returns:
            Group object
        """
        namespace = "http://www.zenfolio.com/api/1.8"
        
        def get_text(elem, tag: str, default: Any = None) -> Any:
            """Get text content from a child element."""
            child = elem.find(f'.//{{{namespace}}}{tag}')
            if child is None:
                child = elem.find(f'.//{tag}')  # Try without namespace
            return child.text if child is not None and child.text else default
        
        def get_int(elem, tag: str, default: int = 0) -> int:
            """Get integer content from a child element."""
            text = get_text(elem, tag)
            try:
                return int(text) if text else default
            except (ValueError, TypeError):
                return default
        
        def get_datetime(elem, tag: str) -> Optional[datetime]:
            """Get datetime content from a child element."""
            text = get_text(elem, tag)
            if not text:
                return None
            try:
                return datetime.fromisoformat(text.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return None
        
        # Parse basic group info
        group_id = get_int(group_elem, 'Id')
        title = get_text(group_elem, 'Title', f'Group {group_id}')
        caption = get_text(group_elem, 'Caption')
        created_on = get_datetime(group_elem, 'CreatedOn') or datetime.now()
        last_updated = get_datetime(group_elem, 'LastUpdated')
        
        # Parse elements (subgroups and photo sets)
        elements = []
        elements_elem = group_elem.find(f'.//{{{namespace}}}Elements')
        if elements_elem is None:
            elements_elem = group_elem.find('.//Elements')  # Try without namespace
        
        if elements_elem is not None:
            # Parse DIRECT children only (not descendants) - this is the key fix!
            # Use single '.' instead of '//' to get immediate children only
            
            # Parse subgroups (immediate children only)
            for subgroup_elem in elements_elem.findall(f'./{{{namespace}}}Group'):
                try:
                    subgroup = self._parse_group_element(subgroup_elem)
                    elements.append(subgroup)
                except Exception as e:
                    logger.warning(f"Failed to parse subgroup: {e}")
            
            # Also try without namespace (immediate children only)
            for subgroup_elem in elements_elem.findall('./Group'):
                try:
                    subgroup = self._parse_group_element(subgroup_elem)
                    elements.append(subgroup)
                except Exception as e:
                    logger.warning(f"Failed to parse subgroup: {e}")
            
            # Parse photo sets (immediate children only)
            for photoset_elem in elements_elem.findall(f'./{{{namespace}}}PhotoSet'):
                try:
                    photoset = self._parse_photoset_element(photoset_elem, include_photos=False)
                    elements.append(photoset)
                except Exception as e:
                    logger.warning(f"Failed to parse photo set: {e}")
            
            # Also try without namespace (immediate children only)
            for photoset_elem in elements_elem.findall('./PhotoSet'):
                try:
                    photoset = self._parse_photoset_element(photoset_elem, include_photos=False)
                    elements.append(photoset)
                except Exception as e:
                    logger.warning(f"Failed to parse photo set: {e}")
        
        return Group(
            id=group_id,
            title=title,
            caption=caption,
            created_on=created_on,
            last_updated=last_updated,
            elements=elements
        )
    
    def _parse_photoset_element(self, photoset_elem: ET.Element, include_photos: bool = True) -> PhotoSet:
        """Parse a PhotoSet element from XML.
        
        Args:
            photoset_elem: XML element containing photo set data
            include_photos: Whether to parse photos
            
        Returns:
            PhotoSet object
        """
        namespace = "http://www.zenfolio.com/api/1.8"
        
        def get_text(elem, tag: str, default: Any = None) -> Any:
            """Get text content from a child element."""
            child = elem.find(f'.//{{{namespace}}}{tag}')
            if child is None:
                child = elem.find(f'.//{tag}')  # Try without namespace
            return child.text if child is not None and child.text else default
        
        def get_int(elem, tag: str, default: int = 0) -> int:
            """Get integer content from a child element."""
            text = get_text(elem, tag)
            try:
                return int(text) if text else default
            except (ValueError, TypeError):
                return default
        
        def get_datetime(elem, tag: str) -> Optional[datetime]:
            """Get datetime content from a child element."""
            text = get_text(elem, tag)
            if not text:
                return None
            try:
                return datetime.fromisoformat(text.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return None
        
        # Parse basic photo set info
        photoset_id = get_int(photoset_elem, 'Id')
        title = get_text(photoset_elem, 'Title', f'Gallery {photoset_id}')
        caption = get_text(photoset_elem, 'Caption')
        created_on = get_datetime(photoset_elem, 'CreatedOn') or datetime.now()
        last_updated = get_datetime(photoset_elem, 'LastUpdated')
        photo_count = get_int(photoset_elem, 'PhotoCount')
        
        # Determine type (Gallery or Collection)
        type_text = get_text(photoset_elem, 'Type', 'Gallery')
        photoset_type = PhotoSetType.GALLERY if type_text == 'Gallery' else PhotoSetType.COLLECTION
        
        # Parse photos if requested
        photos = []
        if include_photos:
            photos_elem = photoset_elem.find(f'.//{{{namespace}}}Photos')
            if photos_elem is None:
                photos_elem = photoset_elem.find('.//Photos')  # Try without namespace
            
            if photos_elem is not None:
                for photo_elem in photos_elem.findall(f'.//{{{namespace}}}Photo'):
                    try:
                        photo = self._parse_photo_element(photo_elem)
                        photos.append(photo)
                    except Exception as e:
                        logger.warning(f"Failed to parse photo: {e}")
                
                # Also try without namespace
                for photo_elem in photos_elem.findall('.//Photo'):
                    try:
                        photo = self._parse_photo_element(photo_elem)
                        photos.append(photo)
                    except Exception as e:
                        logger.warning(f"Failed to parse photo: {e}")
        
        return PhotoSet(
            id=photoset_id,
            title=title,
            caption=caption,
            type=photoset_type,
            created_on=created_on,
            last_updated=last_updated,
            photo_count=photo_count,
            photos=photos
        )
    
    def _parse_photo_element(self, photo_elem: ET.Element) -> Photo:
        """Parse a Photo element from XML.
        
        Args:
            photo_elem: XML element containing photo data
            
        Returns:
            Photo object
        """
        namespace = "http://www.zenfolio.com/api/1.8"
        
        def get_text(elem, tag: str, default: Any = None) -> Any:
            """Get text content from a child element."""
            child = elem.find(f'.//{{{namespace}}}{tag}')
            if child is None:
                child = elem.find(f'.//{tag}')  # Try without namespace
            return child.text if child is not None and child.text else default
        
        def get_int(elem, tag: str, default: int = 0) -> int:
            """Get integer content from a child element."""
            text = get_text(elem, tag)
            try:
                return int(text) if text else default
            except (ValueError, TypeError):
                return default
        
        def get_float(elem, tag: str, default: float = 0.0) -> float:
            """Get float content from a child element."""
            text = get_text(elem, tag)
            try:
                return float(text) if text else default
            except (ValueError, TypeError):
                return default
        
        def get_bool(elem, tag: str, default: bool = False) -> bool:
            """Get boolean content from a child element."""
            text = get_text(elem, tag)
            if not text:
                return default
            return text.lower() in ('true', '1', 'yes')
        
        def get_datetime(elem, tag: str) -> Optional[datetime]:
            """Get datetime content from a child element."""
            text = get_text(elem, tag)
            if not text:
                return None
            try:
                return datetime.fromisoformat(text.replace('Z', '+00:00'))
            except (ValueError, TypeError):
                return None
        
        # Parse basic photo info
        photo_id = get_int(photo_elem, 'Id')
        title = get_text(photo_elem, 'Title', f'Photo {photo_id}')
        file_name = get_text(photo_elem, 'FileName', f'photo_{photo_id}.jpg')
        uploaded_on = get_datetime(photo_elem, 'UploadedOn') or datetime.now()
        taken_on = get_datetime(photo_elem, 'TakenOn')
        width = get_int(photo_elem, 'Width')
        height = get_int(photo_elem, 'Height')
        size = get_int(photo_elem, 'Size')
        is_video = get_bool(photo_elem, 'IsVideo')
        mime_type = get_text(photo_elem, 'MimeType')
        original_url = get_text(photo_elem, 'OriginalUrl', '')
        sequence = get_int(photo_elem, 'Sequence')
        
        # Video-specific fields
        duration = get_float(photo_elem, 'Duration') if is_video else None
        video_url = get_text(photo_elem, 'VideoUrl') if is_video else None
        
        return Photo(
            id=photo_id,
            title=title,
            file_name=file_name,
            uploaded_on=uploaded_on,
            taken_on=taken_on,
            width=width,
            height=height,
            size=size,
            is_video=is_video,
            mime_type=mime_type,
            original_url=original_url,
            sequence=sequence,
            duration=duration,
            video_url=video_url
        )
    
    async def list_galleries(self, root_group: Optional[Group] = None, show_details: bool = False) -> List[Dict[str, Any]]:
        """List all galleries in a hierarchical structure.
        
        Args:
            root_group: Root group to list from (loads if None)
            show_details: Whether to include detailed information
            
        Returns:
            List of gallery information dictionaries
        """
        if root_group is None:
            # Load user profile first
            user_profile = await self.load_private_profile()
            root_group = await self.load_group_hierarchy(user_profile.login_name, force_refresh=False)
        
        galleries = []
        await self._collect_gallery_info(root_group, galleries, "", show_details)
        return galleries
    
    async def _collect_gallery_info(
        self,
        group: Group,
        galleries: List[Dict[str, Any]],
        path: str,
        show_details: bool
    ) -> None:
        """Recursively collect gallery information.
        
        Args:
            group: Group to process
            galleries: List to append gallery info to
            path: Current path in hierarchy
            show_details: Whether to include detailed information
        """
        # Process galleries in this group
        for gallery in group.galleries:
            gallery_path = f"{path}/{gallery.title}" if path else gallery.title
            
            gallery_info = {
                'id': gallery.id,
                'title': gallery.title,
                'path': gallery_path,
                'type': gallery.type.value,
                'photo_count': gallery.photo_count,
                'created_on': gallery.created_on.isoformat() if gallery.created_on else None,
                'last_updated': gallery.last_updated.isoformat() if gallery.last_updated else None
            }
            
            if show_details:
                try:
                    # Load detailed gallery information
                    detailed_gallery = await self.load_photo_set(gallery.id, InformationLevel.LEVEL2, True)
                    gallery_info.update({
                        'caption': detailed_gallery.caption,
                        'actual_photo_count': len(detailed_gallery.photos),
                        'total_size_mb': sum(p.size for p in detailed_gallery.photos if p.size > 0) / (1024 * 1024),
                        'video_count': sum(1 for p in detailed_gallery.photos if p.is_video),
                        'photo_count_actual': sum(1 for p in detailed_gallery.photos if not p.is_video)
                    })
                except Exception as e:
                    logger.warning(f"Failed to load details for gallery {gallery.title}: {e}")
                    gallery_info['error'] = str(e)
            
            galleries.append(gallery_info)
        
        # Recursively process subgroups
        for subgroup in group.subgroups:
            subgroup_path = f"{path}/{subgroup.title}" if path else subgroup.title
            await self._collect_gallery_info(subgroup, galleries, subgroup_path, show_details)