"""Token management for Zenfolio authentication."""

import json
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
from logs.logger import get_logger

logger = get_logger(__name__)


class TokenManager:
    """Manages authentication tokens with optional persistence."""
    
    def __init__(self, cache_file: Optional[str] = None):
        """Initialize token manager.
        
        Args:
            cache_file: Optional file path to cache tokens
        """
        self.cache_file = Path(cache_file) if cache_file else None
        self._token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._username: Optional[str] = None
    
    @property
    def token(self) -> Optional[str]:
        """Get the current token if it's still valid."""
        if self._token and self.is_token_valid():
            return self._token
        return None
    
    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        return self.token is not None
    
    def set_token(self, token: str, username: str, expires_in_seconds: Optional[int] = None) -> None:
        """Set a new authentication token.
        
        Args:
            token: The authentication token
            username: Username associated with the token
            expires_in_seconds: Token expiration time in seconds (default: 1 hour)
        """
        self._token = token
        self._username = username
        
        # Default to 1 hour expiration if not specified
        if expires_in_seconds is None:
            expires_in_seconds = 3600
        
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in_seconds)
        
        logger.debug(f"Token set for user {username}, expires at {self._token_expires_at}")
        
        # Save to cache if configured
        if self.cache_file:
            self._save_token_cache()
    
    def clear_token(self) -> None:
        """Clear the current token."""
        self._token = None
        self._token_expires_at = None
        self._username = None
        
        # Clear cache file if it exists
        if self.cache_file and self.cache_file.exists():
            try:
                self.cache_file.unlink()
                logger.debug("Token cache file cleared")
            except Exception as e:
                logger.warning(f"Failed to clear token cache file: {e}")
        
        logger.debug("Token cleared")
    
    def is_token_valid(self) -> bool:
        """Check if the current token is still valid.
        
        Returns:
            True if token exists and hasn't expired
        """
        if not self._token:
            return False
        
        if not self._token_expires_at:
            # If no expiration time, assume it's still valid
            return True
        
        # Check if token has expired (with 5 minute buffer)
        buffer_time = timedelta(minutes=5)
        return datetime.now() < (self._token_expires_at - buffer_time)
    
    def load_cached_token(self, username: str) -> bool:
        """Load token from cache file if available and valid.
        
        Args:
            username: Username to match against cached token
            
        Returns:
            True if valid cached token was loaded
        """
        if not self.cache_file or not self.cache_file.exists():
            return False
        
        try:
            with open(self.cache_file, 'r') as f:
                cache_data = json.load(f)
            
            # Validate cache data structure
            required_fields = ['token', 'username', 'expires_at']
            if not all(field in cache_data for field in required_fields):
                logger.warning("Invalid token cache file format")
                return False
            
            # Check if username matches
            if cache_data['username'] != username:
                logger.debug("Cached token is for different user")
                return False
            
            # Parse expiration time
            expires_at = datetime.fromisoformat(cache_data['expires_at'])
            
            # Check if token has expired
            if datetime.now() >= expires_at:
                logger.debug("Cached token has expired")
                return False
            
            # Load the token
            self._token = cache_data['token']
            self._username = cache_data['username']
            self._token_expires_at = expires_at
            
            logger.debug(f"Loaded cached token for user {username}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to load token cache: {e}")
            return False
    
    def _save_token_cache(self) -> None:
        """Save current token to cache file."""
        if not self.cache_file or not self._token:
            return
        
        try:
            # Ensure cache directory exists
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            cache_data = {
                'token': self._token,
                'username': self._username,
                'expires_at': self._token_expires_at.isoformat() if self._token_expires_at else None,
                'cached_at': datetime.now().isoformat()
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            # Set restrictive permissions on cache file
            self.cache_file.chmod(0o600)
            
            logger.debug(f"Token cached to {self.cache_file}")
            
        except Exception as e:
            logger.warning(f"Failed to save token cache: {e}")
    
    def get_token_info(self) -> dict:
        """Get information about the current token.
        
        Returns:
            Dictionary with token information
        """
        return {
            'has_token': self._token is not None,
            'is_valid': self.is_token_valid(),
            'username': self._username,
            'expires_at': self._token_expires_at.isoformat() if self._token_expires_at else None,
            'expires_in_seconds': (
                int((self._token_expires_at - datetime.now()).total_seconds())
                if self._token_expires_at else None
            )
        }