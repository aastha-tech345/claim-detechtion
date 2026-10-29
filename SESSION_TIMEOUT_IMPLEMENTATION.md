# Session Timeout & Token Refresh Implementation Guide

## Overview

This project now includes comprehensive session timeout and token refresh logic to enhance security and manage user sessions effectively. The implementation includes:

1. **Session Timeout Detection** - Configurable idle and absolute session timeouts
2. **Automatic Token Refresh** - Pre-expiration token refresh to keep sessions alive
3. **Session Warnings** - User-friendly warnings before session expiration
4. **Graceful Session Cleanup** - Clean logout on timeout

## Architecture

### Core Components

#### 1. `waterfall_guard/session_manager.py`
The main module that handles all session lifecycle management.

**Key Classes:**
- `SessionManager` - Static methods for session operations

**Key Methods:**
- `check_session_status()` - Returns comprehensive session status
- `refresh_access_token()` - Attempts token refresh using refresh token
- `check_and_refresh_token()` - Smart refresh check before expiration
- `end_session()` - Terminates session and clears state
- `require_valid_session()` - Validates session or stops execution

#### 2. `waterfall_guard/auth_app_integration.py`
Integration helpers for `auth_app.py` to use session management.

**Key Functions:**
- `initialize_auth_app_session()` - Setup session state
- `handle_authentication_result()` - Process login/signup results
- `render_protected_page()` - Render pages with session validation
- `get_session_status_info()` - Formatted session status
- `render_session_info_sidebar()` - Debug info display

### Integration Points

#### `auth_app.py`
- Login page initializes session tracking on successful authentication
- Dashboard validates session before rendering
- Automatic logout on session expiration

#### `app.py` (OpenClaw Dashboard)
- Session validation on page load
- Automatic redirect to login on timeout
- Token refresh before expiration

## Configuration

### Environment Variables (.env)

```env
# Session and Token Management
# Absolute maximum session duration (minutes)
SESSION_TIMEOUT_MINUTES=30

# Idle timeout - session expires if no activity for this duration (minutes)
IDLE_TIMEOUT_MINUTES=20

# How many minutes before token expiration to attempt refresh
TOKEN_REFRESH_THRESHOLD_MINUTES=5

# Show warning this many minutes before idle timeout
SESSION_WARNING_THRESHOLD_MINUTES=2
```

### Default Values

| Variable | Default | Purpose |
|----------|---------|---------|
| SESSION_TIMEOUT_MINUTES | 30 | Max total session duration |
| IDLE_TIMEOUT_MINUTES | 20 | Inactivity timeout |
| TOKEN_REFRESH_THRESHOLD_MINUTES | 5 | Preemptive refresh window |
| SESSION_WARNING_THRESHOLD_MINUTES | 2 | Warning display threshold |

## How It Works

### 1. Session Initialization

When a user logs in successfully:
```python
SessionManager._initialize_session_tracking()
```

This sets:
- `session_start_time` - When the session began
- `last_activity_time` - Last user interaction timestamp
- Session tracking flags

### 2. Activity Tracking

Every call to `SessionManager.check_session_status()` automatically updates `last_activity_time`, effectively resetting the idle timer.

This means:
- Any user interaction keeps session alive
- Idle time only accumulates during periods of no interaction
- Pure viewing of dashboards won't timeout

### 3. Token Expiration Check

The system monitors JWT token expiration claims (`exp`):

```python
SessionManager._is_token_about_to_expire()  # Returns True if within threshold
SessionManager.check_and_refresh_token()     # Attempts refresh if needed
```

When token is within `TOKEN_REFRESH_THRESHOLD_MINUTES` of expiration:
1. System extracts `exp` claim from JWT
2. Calculates time until expiration
3. Automatically refreshes using refresh token
4. Updates both tokens in session state

### 4. Session Status Checking

`SessionManager.check_session_status()` returns:
```python
{
    "is_valid": True,                    # Session is active and valid
    "is_idle_timeout": False,            # Did not exceed idle timeout
    "is_absolute_timeout": False,        # Did not exceed absolute timeout  
    "is_token_invalid": False,           # Token is valid
    "is_expiration_warning": False,      # Not in warning window
    "idle_duration_minutes": 5.2,        # Minutes since last activity
    "session_duration_minutes": 15.3,    # Total session time
    "message": "Session active"          # Human-readable status
}
```

### 5. Session Expiration

Session expires if either condition is met:
1. **Idle Timeout**: No activity for `IDLE_TIMEOUT_MINUTES`
2. **Absolute Timeout**: Total session duration exceeds `SESSION_TIMEOUT_MINUTES`

When expired:
1. `is_valid` returns `False`
2. User receives expiration message
3. `SessionManager.end_session()` clears all session data
4. User is redirected to login

### 6. Expiration Warning

Before idle timeout, users see a warning when:
- Idle time > `(IDLE_TIMEOUT_MINUTES - SESSION_WARNING_THRESHOLD_MINUTES)`

Example: With defaults (20 min idle, 2 min warning):
- At 18 minutes of inactivity → Warning shown
- At 20 minutes → Session expires

## Usage in Your Application

### Protect Streamlit Pages

**Option 1: Using decorator (preferred)**
```python
from waterfall_guard.session_manager import require_session

@require_session
def my_protected_page():
    st.title("Protected Dashboard")
    # Page code here
```

**Option 2: Manual validation**
```python
from waterfall_guard.session_manager import require_valid_session

def my_protected_page():
    if not require_valid_session():
        return
    
    st.title("Protected Dashboard")
    # Page code here
```

### Get Session Status

```python
from waterfall_guard.session_manager import SessionManager

status = SessionManager.check_session_status()

if not status["is_valid"]:
    st.error(f"Session expired: {status['message']}")
else:
    st.info(f"Session active for {status['session_duration_minutes']:.1f} minutes")
```

### Check for Token Expiration

```python
SessionManager.check_and_refresh_token()  # Returns True if valid
```

### Manual Session Termination

```python
SessionManager.end_session()  # Cleanup and logout
```

## Security Considerations

### 1. Token Refresh
- Uses Supabase `refresh_token` for secure token rotation
- Old tokens are invalidated server-side
- Only works if Supabase session exists

### 2. JWT Validation
- Signature verification using `SUPABASE_JWT_SECRET`
- Expiration (`exp`) claim validation
- Required claims checking (`sub`, `exp`)

### 3. Activity Tracking
- Timestamps use UTC timezone
- Activity updates on any session check
- Prevents clock skew issues

### 4. Session State Management
- Cleared on logout
- Expires on timeout
- Cannot be extended beyond `SESSION_TIMEOUT_MINUTES`

## Customization

### Modify Timeout Thresholds

Edit `.env`:
```env
# Make sessions last longer
SESSION_TIMEOUT_MINUTES=60
IDLE_TIMEOUT_MINUTES=45

# Show warning earlier
SESSION_WARNING_THRESHOLD_MINUTES=5
```

### Disable Idle Timeout

Set `IDLE_TIMEOUT_MINUTES` to a very large value:
```env
IDLE_TIMEOUT_MINUTES=999999
```

### Custom Session Handler

Create a wrapper function:
```python
from waterfall_guard.session_manager import SessionManager, require_valid_session

def my_custom_session_check():
    """Custom session validation logic"""
    status = SessionManager.check_session_status()
    
    if status["is_expiration_warning"]:
        # Show custom warning
        st.warning("Custom session warning message")
    
    return status["is_valid"]

if not my_custom_session_check():
    st.stop()
```

## Troubleshooting

### Session times out immediately

**Problem**: User is logged out right after login
- Check: Is `SESSION_TIMEOUT_MINUTES` set to 0 or negative?
- Check: Is `IDLE_TIMEOUT_MINUTES` too small?
- Check: Is system clock synced (affects JWT `exp` validation)?

### Token refresh fails

**Problem**: "Token refresh failed" in logs
- Check: Is `refresh_token` present in session state?
- Check: Is Supabase connection working?
- Check: Has the refresh token expired on the backend?
- Check: Is `SUPABASE_URL` and credentials correct?

### Session expires during long operations

**Problem**: Users get logged out while performing actions
- This is expected if operation takes longer than `IDLE_TIMEOUT_MINUTES`
- Solution: Increase `IDLE_TIMEOUT_MINUTES` for your use case
- Or: Perform long operations in a background job

### JWT signature verification fails

**Problem**: "Token signature verification failed" error
- Check: Is `SUPABASE_JWT_SECRET` set in `.env`?
- Check: Does it match the value from Supabase project settings?
- Check: Is there trailing whitespace in the env var?

### Multiple session checks causing lag

**Problem**: Each page check is slow
- Solution: Session checks include network call to validate token
- Optimization: Reduce check frequency by increasing thresholds
- Or: Cache session status for a few seconds

## Logging & Monitoring

The `session_manager.py` uses Python's standard logging:

```python
import logging

logger = logging.getLogger(__name__)
# Logs go to Python logger with name "waterfall_guard.session_manager"
```

Enable debug logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Key log messages:
- "Token refreshed successfully for user [email]"
- "Token about to expire, attempting refresh"
- "Token validation failed: [error]"
- "Session expired due to inactivity"

## Testing

### Manual Test 1: Idle Timeout

1. Log in to application
2. Set `IDLE_TIMEOUT_MINUTES=1` in `.env`
3. Don't interact with page for 1 minute
4. Refresh page
5. Should see: "Session expired due to inactivity"

### Manual Test 2: Token Refresh

1. Add debug logging (see above)
2. Log in
3. Watch logs for token refresh attempts
4. Should see: "Token refreshed successfully" in logs

### Manual Test 3: Warning Display

1. Set `IDLE_TIMEOUT_MINUTES=2` and `SESSION_WARNING_THRESHOLD_MINUTES=1`
2. Log in and don't interact for 1 minute
3. Should see warning: "Session will expire in ~1 minute(s)"

## Best Practices

1. **Set reasonable timeouts** - Balance security with user experience
2. **Communicate timeouts** - Show session info in sidebar/header
3. **Warn before expiring** - Users should be notified in advance
4. **Auto-save work** - Periodically save user work in case of timeout
5. **Handle refresh gracefully** - Provide clear error messages
6. **Test edge cases** - Network failures, clock skew, etc.

## Future Enhancements

Possible improvements:
- [ ] "Remember me" option to extend session
- [ ] Session refresh confirmation dialogs
- [ ] Per-user timeout settings in database
- [ ] Session activity audit logs
- [ ] Multiple device session management
- [ ] Concurrent session limiting
- [ ] Session history dashboard

## Support & Issues

If you encounter issues:

1. Check environment variables in `.env`
2. Enable debug logging
3. Check Supabase connection status
4. Verify JWT secret configuration
5. Check browser console for errors
6. Review Streamlit app logs

For complex issues, check:
- Supabase JWT configuration (Project Settings → Authentication)
- Token expiration times in Supabase Auth settings
- Network connectivity and SSL verification settings
- System clock synchronization
