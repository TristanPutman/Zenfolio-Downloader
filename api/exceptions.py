"""API exceptions for Zenfolio client."""

from typing import Optional


class ZenfolioAPIError(Exception):
    """Base exception for Zenfolio API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class AuthenticationError(ZenfolioAPIError):
    """Exception raised when authentication fails."""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class RateLimitError(ZenfolioAPIError):
    """Exception raised when API rate limit is exceeded."""
    
    def __init__(self, message: str = "API rate limit exceeded", retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class NetworkError(ZenfolioAPIError):
    """Exception raised for network-related errors."""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class InvalidResponseError(ZenfolioAPIError):
    """Exception raised when API response is invalid or unexpected."""
    
    def __init__(self, message: str, response_data: Optional[dict] = None):
        super().__init__(message, response_data=response_data)


class ResourceNotFoundError(ZenfolioAPIError):
    """Exception raised when a requested resource is not found."""
    
    def __init__(self, resource_type: str, resource_id: str):
        message = f"{resource_type} with ID '{resource_id}' not found"
        super().__init__(message, status_code=404)
        self.resource_type = resource_type
        self.resource_id = resource_id


class PermissionError(ZenfolioAPIError):
    """Exception raised when user lacks permission to access a resource."""
    
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, status_code=403)


class ServerError(ZenfolioAPIError):
    """Exception raised for server-side errors."""
    
    def __init__(self, message: str = "Server error", status_code: int = 500):
        super().__init__(message, status_code=status_code)