# E5 Token Validation Implementation Guide

**Status:** CRITICAL GAP — Token expiration NOT validated  
**Priority:** HIGH — Must implement before staging deployment  
**Estimated Effort:** 2–3 hours

---

## 1. Current Gap

### Problem

SessionValidator checks if `access_token` exists in session but does NOT validate:
- Token expiration (exp claim)
- Token signature (JWT integrity)
- Token format (valid JWT structure)
- Token revocation status

### Code Evidence

**File:** `waterfall_guard/auth_session.py` (Line 108–115)
```python
required_fields = ["user_id", "email", "tenant_id", "access_token"]
for field in required_fields:
    if field not in user_data or not user_data[field]:
        raise AuthenticationError(f"Missing required field: {field}")
# ^^^ Checks if field EXISTS, not if it's VALID
```

### Risk Scenario

1. User logs in at 2 PM → Valid JWT with exp = 3 PM received
2. Token stored in st.session_state
3. User works for 2 hours
4. At 4 PM, token is expired (exp < now)
5. User clicks "Post Resolution to Epic"
6. SessionValidator.require_authorized_role() checks access_token EXISTS ✓
7. writeback_client.post_resolution() is called
8. Epic FHIR API returns 401 (Unauthorized) → Token refresh attempt
9. Token refresh fails (session token expired)
10. Writeback fails with error, audit logged

**Better Outcome:**
- SessionValidator should validate token expiration BEFORE step 6
- Preemptively deny or refresh token
- User sees error: "Session expired, please log in again"
- No unnecessary Epic API call made

---

## 2. Implementation Plan

### 2.1 Install JWT Decoding Library

**File:** `requirements.txt`

**Add:**
```text
PyJWT>=2.8.0
```

**Install:**
```bash
pip install PyJWT>=2.8.0
```

### 2.2 Add JWT Token Validation to SessionValidator

**File:** `waterfall_guard/auth_session.py`

**Add imports:**
```python
import jwt
import logging
from datetime import datetime, timezone, timedelta
```

**Add helper method:**
```python
@staticmethod
def _decode_jwt_unverified(token: str) -> Optional[dict]:
    """Decode JWT without signature verification (to read exp claim).
    
    In production, you'd verify signature against Supabase's public key.
    For now, we trust the token was created by Supabase Auth.
    
    Args:
        token: JWT access token
    
    Returns:
        Decoded JWT payload, or None if malformed
    """
    try:
        # Decode without verification to read claims
        # (Supabase Auth verified signature when token was created)
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload
    except jwt.DecodeError as e:
        logger.warning(f"Invalid JWT format: {e}")
        return None
    except Exception as e:
        logger.warning(f"JWT decode error: {e}")
        return None

@staticmethod
def _is_token_expired(token: str) -> bool:
    """Check if JWT access token has expired.
    
    Args:
        token: JWT access token
    
    Returns:
        True if token is expired, False otherwise
    """
    payload = SessionValidator._decode_jwt_unverified(token)
    if not payload or "exp" not in payload:
        logger.warning("Token missing exp claim")
        return True  # Assume expired if no exp claim
    
    exp_timestamp = payload["exp"]
    now_timestamp = int(datetime.now(timezone.utc).timestamp())
    
    # Add 30-second buffer: consider expired if within 30 seconds of exp
    buffer_seconds = 30
    is_expired = (exp_timestamp - now_timestamp) <= buffer_seconds
    
    if is_expired:
        seconds_until_exp = max(0, exp_timestamp - now_timestamp)
        logger.info(f"Token expired (expires in {seconds_until_exp}s)")
    
    return is_expired

@staticmethod
def _get_token_expiry_time(token: str) -> Optional[datetime]:
    """Get token expiration time.
    
    Args:
        token: JWT access token
    
    Returns:
        Expiration datetime in UTC, or None if cannot determine
    """
    payload = SessionValidator._decode_jwt_unverified(token)
    if not payload or "exp" not in payload:
        return None
    
    exp_timestamp = payload["exp"]
    return datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
```

**Update get_authenticated_user() method:**
```python
@staticmethod
def get_authenticated_user() -> Optional[AuthenticatedUser]:
    """Get validated authenticated user from session.

    Validates that:
    1. Session is marked as authenticated
    2. All required fields present (user_id, email, tenant_id, access_token)
    3. Access token is not expired

    Returns:
        AuthenticatedUser if session is valid, None if not authenticated.

    Raises:
        AuthenticationError: If session is invalid or corrupt.
    """
    if not SessionValidator.is_authenticated():
        return None

    try:
        user_data = st.session_state.get("user", {})

        if not user_data:
            raise AuthenticationError("No user data in session")

        # Validate required fields from session
        required_fields = ["user_id", "email", "tenant_id", "access_token"]
        for field in required_fields:
            if field not in user_data or not user_data[field]:
                raise AuthenticationError(f"Missing required field: {field}")

        # NEW: Validate token is not expired
        access_token = user_data["access_token"]
        if SessionValidator._is_token_expired(access_token):
            raise AuthenticationError(
                "Your session has expired. Please log in again to continue."
            )

        # Derive role from session (default to ANALYST if not set)
        role_str = user_data.get("role", "analyst").lower()
        try:
            role = UserRole(role_str)
        except ValueError:
            logger.warning(f"Invalid role in session: {role_str}, defaulting to ANALYST")
            role = UserRole.ANALYST

        return AuthenticatedUser(
            user_id=user_data["user_id"],
            email=user_data["email"],
            tenant_id=user_data["tenant_id"],
            organization_name=user_data.get("organization_name", ""),
            role=role,
            access_token=access_token,
        )

    except KeyError as e:
        raise AuthenticationError(f"Malformed session: {e}")
    except Exception as e:
        raise AuthenticationError(f"Session validation failed: {e}")
```

**Add method to refresh expired tokens:**
```python
@staticmethod
def refresh_token_if_expired(user_data: dict) -> Tuple[bool, Optional[str]]:
    """Attempt to refresh token if expired or near expiration.
    
    Args:
        user_data: User data dict from session
    
    Returns:
        (success: bool, error: str or None)
    """
    if "access_token" not in user_data or "refresh_token" not in user_data:
        return False, "Missing tokens in session"
    
    if not SessionValidator._is_token_expired(user_data["access_token"]):
        return True, None  # Token still valid
    
    # Token expired, attempt refresh
    try:
        import os
        from supabase import create_client
        from dotenv import load_dotenv
        
        load_dotenv()
        supabase_url = os.getenv("SUPABASE_URL")
        anon_key = os.getenv("SUPABASE_ANON_KEY")
        
        if not supabase_url or not anon_key:
            return False, "Supabase credentials not available"
        
        client = create_client(supabase_url, anon_key)
        
        # Attempt to refresh token using refresh_token
        response = client.auth.refresh_session(user_data["refresh_token"])
        
        if response.session and response.session.access_token:
            # Update session with new tokens
            st.session_state.access_token = response.session.access_token
            st.session_state.refresh_token = response.session.refresh_token
            user_data["access_token"] = response.session.access_token
            user_data["refresh_token"] = response.session.refresh_token
            
            logger.info("Token refreshed successfully")
            return True, None
        else:
            return False, "Token refresh failed: empty response"
    
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return False, f"Token refresh failed: {str(e)}"
```

---

### 2.3 Update require_authorized_role() to Handle Expiry

**File:** `waterfall_guard/auth_session.py`

**Update method:**
```python
@staticmethod
def require_authorized_role(required_role: UserRole) -> AuthenticatedUser:
    """Require authenticated user with specific role or raise error.

    Validates:
    1. User is authenticated
    2. Session is valid
    3. Access token is not expired
    4. User has required role

    Args:
        required_role: Minimum required role (e.g., UserRole.SUPERVISOR)

    Returns:
        AuthenticatedUser if user has required role.

    Raises:
        AuthenticationError: If not authenticated, invalid session, token expired, or insufficient role.
    """
    user = SessionValidator.require_authenticated_user()

    # NEW: Additional token validation before authorization
    if SessionValidator._is_token_expired(user.access_token):
        raise AuthenticationError(
            "Your session has expired. Please log in again to continue."
        )

    # Role hierarchy: ANALYST < SUPERVISOR < ADMIN
    role_hierarchy = {
        UserRole.ANALYST: 0,
        UserRole.SUPERVISOR: 1,
        UserRole.ADMIN: 2,
    }

    if role_hierarchy.get(user.role, -1) < role_hierarchy.get(required_role, -1):
        raise AuthenticationError(
            f"Insufficient permissions: Your role ({user.role.value}) "
            f"cannot perform this action (requires {required_role.value})"
        )

    return user
```

---

### 2.4 Add Token Validation Tests

**File:** `tests/test_e5_authentication.py`

**Add test class:**
```python
class TestTokenExpiration(unittest.TestCase):
    """Test token expiration validation."""

    def test_is_token_expired_returns_false_for_valid_token(self):
        """is_token_expired() returns False for non-expired token."""
        # Create a token that expires in 1 hour
        from datetime import datetime, timezone, timedelta
        import jwt as pyjwt
        
        payload = {
            "sub": "user-123",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }
        token = pyjwt.encode(payload, "secret", algorithm="HS256")
        
        # Note: SessionValidator._is_token_expired() decodes without verification,
        # so this works even though we signed with a different key
        with patch("waterfall_guard.auth_session.jwt.decode", return_value=payload):
            result = SessionValidator._is_token_expired(token)
            self.assertFalse(result)

    def test_is_token_expired_returns_true_for_expired_token(self):
        """is_token_expired() returns True for expired token."""
        from datetime import datetime, timezone, timedelta
        import jwt as pyjwt
        
        # Create a token that expired 1 hour ago
        payload = {
            "sub": "user-123",
            "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
        }
        token = pyjwt.encode(payload, "secret", algorithm="HS256")
        
        with patch("waterfall_guard.auth_session.jwt.decode", return_value=payload):
            result = SessionValidator._is_token_expired(token)
            self.assertTrue(result)

    def test_is_token_expired_returns_true_for_malformed_token(self):
        """is_token_expired() returns True for malformed JWT."""
        token = "not-a-valid-jwt-token"
        
        with patch("waterfall_guard.auth_session.jwt.decode", side_effect=Exception("Invalid JWT")):
            result = SessionValidator._is_token_expired(token)
            self.assertTrue(result)  # Assume expired if cannot verify

    def test_get_authenticated_user_raises_if_token_expired(self):
        """get_authenticated_user() raises AuthenticationError if token expired."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-123",
                "email": "user@example.com",
                "tenant_id": "tenant-abc",
                "access_token": "expired-token",
            },
        }
        
        with patch("streamlit.session_state", session):
            with patch.object(SessionValidator, "_is_token_expired", return_value=True):
                with self.assertRaises(AuthenticationError) as context:
                    SessionValidator.get_authenticated_user()
                
                self.assertIn("expired", str(context.exception).lower())

    def test_require_authorized_role_raises_if_token_expired(self):
        """require_authorized_role() raises if token expired."""
        session = {
            "is_authenticated": True,
            "user": {
                "user_id": "uuid-123",
                "email": "user@example.com",
                "tenant_id": "tenant-abc",
                "role": "supervisor",
                "access_token": "expired-token",
            },
        }
        
        with patch("streamlit.session_state", session):
            with patch.object(SessionValidator, "_is_token_expired", return_value=True):
                with self.assertRaises(AuthenticationError) as context:
                    SessionValidator.require_authorized_role(UserRole.SUPERVISOR)
                
                self.assertIn("expired", str(context.exception).lower())

    def test_refresh_token_if_expired_no_ops_when_token_valid(self):
        """refresh_token_if_expired() returns success if token still valid."""
        user_data = {
            "access_token": "valid-token",
            "refresh_token": "refresh-token",
        }
        
        with patch.object(SessionValidator, "_is_token_expired", return_value=False):
            success, error = SessionValidator.refresh_token_if_expired(user_data)
            self.assertTrue(success)
            self.assertIsNone(error)

    def test_refresh_token_if_expired_attempts_refresh_when_expired(self):
        """refresh_token_if_expired() refreshes token when expired."""
        user_data = {
            "user_id": "uuid-123",
            "access_token": "expired-token",
            "refresh_token": "refresh-token",
        }
        
        mock_session = MagicMock()
        mock_session.access_token = "new-token"
        mock_session.refresh_token = "new-refresh-token"
        
        mock_response = MagicMock()
        mock_response.session = mock_session
        
        with patch("streamlit.session_state", {"user": user_data}):
            with patch.object(SessionValidator, "_is_token_expired", return_value=True):
                with patch("waterfall_guard.auth_session.create_client") as mock_client_factory:
                    mock_client = MagicMock()
                    mock_client.auth.refresh_session.return_value = mock_response
                    mock_client_factory.return_value = mock_client
                    
                    success, error = SessionValidator.refresh_token_if_expired(user_data)
                    self.assertTrue(success)
                    self.assertIsNone(error)
                    self.assertEqual(user_data["access_token"], "new-token")
```

---

### 2.5 Update Writeback Form to Validate Token

**File:** `app.py`

**Update writeback form handling (around line 1100):**
```python
if post_submitted:
    if not epic_task_id.strip() or not resolution_note.strip():
        st.error("Epic FHIR Task ID and resolution note are required.")
    else:
        try:
            # E5: Require authenticated user with SUPERVISOR or ADMIN role
            # NEW: This now validates token expiration
            auth_user = SessionValidator.require_authorized_role(UserRole.SUPERVISOR)
            
            user_id = auth_user.user_id
            user_email = auth_user.email
            user_role = auth_user.role
            tenant_id = auth_user.tenant_id
            
        except SessionAuthError as e:
            st.error(f"🔒 {str(e)}")
            st.stop()
        
        # ... rest of writeback logic
```

---

## 3. Deployment Checklist

Before staging:

- [ ] Install PyJWT: `pip install PyJWT>=2.8.0`
- [ ] Update `requirements.txt` with PyJWT dependency
- [ ] Implement JWT decoding helper methods in SessionValidator
- [ ] Update get_authenticated_user() to validate token expiration
- [ ] Update require_authorized_role() to validate token expiration
- [ ] Implement refresh_token_if_expired() method
- [ ] Add all token validation tests to test_e5_authentication.py
- [ ] Run tests: `python3 -m pytest tests/test_e5_authentication.py -v`
- [ ] Run full test suite: `python3 -m pytest tests/ -v`
- [ ] Manual smoke test: Wait for token to expire and verify writeback is denied
- [ ] Manual smoke test: Verify token refresh works if REFRESH_TOKEN available

---

## 4. Verification

After implementation:

**Scenario 1: Token Still Valid**
```
User logs in at 2 PM
Token expires at 3 PM
User clicks "Post Resolution" at 2:30 PM
→ get_authenticated_user() validates: exp > now ✓
→ writeback proceeds normally ✓
```

**Scenario 2: Token Expired**
```
User logs in at 2 PM
Token expires at 3 PM
User clicks "Post Resolution" at 4 PM
→ get_authenticated_user() validates: exp < now ✗
→ AuthenticationError raised: "Session expired"
→ st.error() shown to user
→ st.stop() prevents writeback
→ Audit log: writeback_denied (expired_session)
→ User sees: "Your session has expired. Please log in again."
✓ NO Epic API call made
✓ NO stale token sent
```

**Scenario 3: Token Near Expiration**
```
User logs in at 2 PM
Token expires at 3 PM
User clicks "Post Resolution" at 2:59:45 PM (15 seconds before exp)
→ get_authenticated_user() checks: (exp - now) <= 30 seconds ✓
→ Token is considered expired (buffer)
→ AuthenticationError raised: "Session expired"
→ Prompts user to log in again
✓ Prevents Epic API call with about-to-expire token
```

---

## 5. Edge Cases and Limitations

**Known Limitation 1: Offline Token Validation**
- Token signature is NOT verified (would need Supabase public key)
- We trust Supabase signed the token when session was created
- exp claim is read without verification (safe, it's just a timestamp)
- In production, could verify signature against Supabase's public key from JWKS endpoint

**Known Limitation 2: Refresh Token Also Expires**
- If refresh_token also expires, refresh will fail
- Session would need re-login
- This is acceptable (redirects to auth_app.py)

**Known Limitation 3: Token Revocation Not Checked**
- If token is revoked server-side, session won't know
- Only detected when Epic API rejects the token (401)
- EpicFHIRWritebackClient handles this with retry + refresh
- Could add optional call to Supabase Auth.verify_jwt() for extra security

**Known Limitation 4: Concurrent Requests**
- If user has multiple tabs open, token could expire in one tab
- User in other tab might still have old token in session
- Next writeback would fail with AuthenticationError
- Acceptable for internal tool (rare multi-tab usage)

---

## 6. Future Enhancements

**Optional: Verify Token Signature**
```python
@staticmethod
def get_supabase_public_key() -> Optional[str]:
    """Fetch Supabase public key from JWKS endpoint."""
    # Would fetch from: https://{supabase-url}/.well-known/jwks.json
    # Cache locally to avoid repeated HTTP calls
    pass

@staticmethod
def verify_token_signature(token: str) -> bool:
    """Verify JWT signature against Supabase public key."""
    # Would use: jwt.decode(token, key, algorithms=["HS256"])
    # Adds extra security layer (catches forged/tampered tokens)
    pass
```

**Optional: Automatic Token Refresh Before Expiry**
```python
@staticmethod
def ensure_token_fresh() -> bool:
    """Check and refresh token if near expiration."""
    user_data = st.session_state.get("user", {})
    success, error = SessionValidator.refresh_token_if_expired(user_data)
    if not success:
        raise AuthenticationError(f"Could not refresh token: {error}")
    return True
```

---

## 7. Timeline

**Implementation time:** 2–3 hours
- 30 min: Install PyJWT, implement helper methods
- 45 min: Update SessionValidator methods
- 30 min: Add token refresh logic
- 30 min: Write and run tests
- 15 min: Update app.py to use new validation
- 15 min: Documentation and verification

**Testing time:** 30 min
- Unit tests: 10 min
- Manual smoke tests: 20 min

**Total:** ~3 hours

---

**Document Version:** 1.0  
**Date:** 2026-10-27  
**Status:** Ready for implementation

## Appendix: JWT Structure Example

```
Header.Payload.Signature

Decoded Payload:
{
  "sub": "550e8400-e29b-41d4-a716-446655440000",  // user UUID
  "email": "user@hospital.com",
  "iss": "https://xyz.supabase.co/auth/v1",       // issuer
  "aud": "authenticated",
  "exp": 1730055000,                               // expiration timestamp
  "iat": 1730051400,                               // issued at timestamp
  "nbf": 1730051400,                               // not before timestamp
  "email_confirmed_at": "2026-10-27T18:00:00Z",
  "app_metadata": {...},
  "user_metadata": {...}
}

Expiration Check:
- Current time: 1730051500 (unix timestamp)
- Token exp: 1730055000
- Seconds until exp: 3500 (58 minutes, still valid)
- is_token_expired(): false
```
