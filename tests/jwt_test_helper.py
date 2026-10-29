"""Helper utilities for JWT token generation in tests.

Provides convenience functions to generate valid JWT tokens for testing
authentication and authorization flows without needing valid Supabase credentials.
"""

import jwt
from datetime import datetime, timezone, timedelta


def create_valid_jwt_token(
    user_id: str = "test-user-123",
    exp_offset_seconds: int = 3600,
    additional_claims: dict = None,
) -> str:
    """Create a valid JWT token for testing.
    
    Args:
        user_id: The 'sub' (subject/user ID) claim
        exp_offset_seconds: Seconds in future for expiration (default: 1 hour)
        additional_claims: Additional claims to include in token
        
    Returns:
        Valid JWT token string
    """
    now = datetime.now(timezone.utc).timestamp()
    
    payload = {
        "sub": user_id,
        "exp": now + exp_offset_seconds,
        "iat": now,
        "email": f"{user_id}@example.com",
    }
    
    if additional_claims:
        payload.update(additional_claims)
    
    # Use a sufficiently long secret for HS256 (minimum 32 bytes recommended)
    test_secret = "test-secret-32-bytes-minimum-length-for-hmac-sha256"
    token = jwt.encode(payload, test_secret, algorithm="HS256")
    return token


def create_expired_jwt_token(user_id: str = "test-user-123") -> str:
    """Create an expired JWT token for testing rejection.
    
    Args:
        user_id: The 'sub' (subject/user ID) claim
        
    Returns:
        Expired JWT token string
    """
    return create_valid_jwt_token(user_id=user_id, exp_offset_seconds=-3600)


def _get_test_secret() -> str:
    """Get a test secret key that meets HMAC-SHA256 requirements (32+ bytes)."""
    return "test-secret-32-bytes-minimum-length-for-hmac-sha256"
