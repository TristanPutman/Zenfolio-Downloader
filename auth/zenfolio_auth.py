"""Zenfolio authentication implementation."""

import hashlib
from typing import Optional
from api.models import AuthChallenge
from api.exceptions import AuthenticationError
from logs.logger import get_logger

logger = get_logger(__name__)


class ZenfolioAuth:
    """Handles Zenfolio authentication using challenge-response mechanism."""
    
    def __init__(self):
        self._token: Optional[str] = None
    
    @property
    def token(self) -> Optional[str]:
        """Get the current authentication token."""
        return self._token
    
    @property
    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return self._token is not None
    
    def set_token(self, token: str) -> None:
        """Set the authentication token."""
        self._token = token
        logger.debug("Authentication token set")
    
    def clear_token(self) -> None:
        """Clear the authentication token."""
        self._token = None
        logger.debug("Authentication token cleared")
    
    @staticmethod
    def hash_data(salt: bytes, data: bytes) -> bytes:
        """Compute salted data hash using SHA-256.
        
        This implements the same hashing logic as the C# version:
        - Concatenate salt + data
        - Compute SHA-256 hash
        
        Args:
            salt: Salt bytes
            data: Data bytes to hash
            
        Returns:
            SHA-256 hash bytes
        """
        buffer = salt + data
        return hashlib.sha256(buffer).digest()
    
    def compute_challenge_response(self, challenge: AuthChallenge, password: str) -> bytes:
        """Compute the challenge response for authentication.
        
        This follows the same logic as the C# ZenfolioClient:
        1. Hash password with password salt
        2. Hash challenge with password hash to create proof
        
        Args:
            challenge: Authentication challenge from API
            password: User password
            
        Returns:
            Challenge response bytes
        """
        try:
            # Convert password to UTF-8 bytes
            password_bytes = password.encode('utf-8')
            
            # Hash password with salt
            password_hash = self.hash_data(challenge.password_salt, password_bytes)
            
            # Compute proof by hashing challenge with password hash
            proof = self.hash_data(challenge.challenge, password_hash)
            
            logger.debug("Challenge response computed successfully")
            return proof
            
        except Exception as e:
            logger.error(f"Failed to compute challenge response: {e}")
            raise AuthenticationError(f"Failed to compute challenge response: {e}")
    
    def validate_credentials(self, username: str, password: str) -> None:
        """Validate that credentials are provided and not empty.
        
        Args:
            username: Username to validate
            password: Password to validate
            
        Raises:
            AuthenticationError: If credentials are invalid
        """
        if not username or not username.strip():
            raise AuthenticationError("Username cannot be empty")
        
        if not password or not password.strip():
            raise AuthenticationError("Password cannot be empty")
        
        logger.debug(f"Credentials validated for user: {username}")
    
    def get_auth_headers(self) -> dict:
        """Get authentication headers for API requests.
        
        Returns:
            Dictionary of headers to include in requests
        """
        if not self.is_authenticated:
            return {}
        
        return {
            "X-Zenfolio-Token": self._token
        }
    
    def handle_auth_error(self, error: Exception) -> None:
        """Handle authentication errors by clearing token.
        
        Args:
            error: The authentication error that occurred
        """
        logger.warning(f"Authentication error occurred: {error}")
        self.clear_token()
        
        # Re-raise as AuthenticationError if it's not already
        if not isinstance(error, AuthenticationError):
            raise AuthenticationError(f"Authentication failed: {error}")
        raise error