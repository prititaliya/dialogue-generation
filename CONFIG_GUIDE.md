# Configuration Guide

## Centralized Configuration Files

All LiveKit-related configuration is now centralized in single files for easy updates.

### Backend Configuration

**File:** `backend/config.py`

This file contains all LiveKit configuration. To update LiveKit settings, edit this file or update your `.env.local` file:

```python
# LiveKit Configuration
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "wss://voice-agent-dsp63yns.livekit.cloud")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")
```

**To change LiveKit URL/API keys:**

1. **Option 1 (Recommended):** Update `backend/.env.local`:
   ```env
   LIVEKIT_URL=wss://your-new-livekit-url.livekit.cloud
   LIVEKIT_API_KEY=your_new_api_key
   LIVEKIT_API_SECRET=your_new_api_secret
   ```

2. **Option 2:** Edit `backend/config.py` directly to change the default URL:
   ```python
   LIVEKIT_URL = os.getenv("LIVEKIT_URL", "wss://your-new-url.livekit.cloud")
   ```

**Usage in code:**
```python
from config import LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, get_livekit_config

# Use individual variables
url = LIVEKIT_URL
api_key = LIVEKIT_API_KEY

# Or get all config at once
config = get_livekit_config()
url = config["url"]
api_key = config["api_key"]
```

### Frontend Configuration

**File:** `frontend/src/config/livekit.ts`

This file provides LiveKit configuration for the frontend (though the URL is typically received from the backend token endpoint).

**To change LiveKit URL:**

1. **Option 1 (Recommended):** Update `frontend/.env`:
   ```env
   VITE_LIVEKIT_URL=wss://your-new-livekit-url.livekit.cloud
   ```

2. **Option 2:** Edit `frontend/src/config/livekit.ts` directly:
   ```typescript
   export const LIVEKIT_URL = import.meta.env.VITE_LIVEKIT_URL || 'wss://your-new-url.livekit.cloud';
   ```

**Usage in code:**
```typescript
import { LIVEKIT_URL, getLiveKitConfig } from '../config/livekit';

// Use the URL
const url = LIVEKIT_URL;

// Or get all config
const config = getLiveKitConfig();
```

## Current Configuration Locations

### Backend Files Using LiveKit Config:
- ✅ `backend/api_server.py` - Uses `config.py` for token generation
- ✅ `backend/config.py` - Centralized configuration file

### Frontend Files:
- ✅ `frontend/src/config/livekit.ts` - Centralized configuration file
- Note: Frontend typically receives LiveKit URL from backend token response

## Quick Update Guide

**To change LiveKit URL everywhere:**

1. **Backend:** Update `backend/.env.local`:
   ```env
   LIVEKIT_URL=wss://your-new-url.livekit.cloud
   ```

2. **Frontend (if needed):** Update `frontend/.env`:
   ```env
   VITE_LIVEKIT_URL=wss://your-new-url.livekit.cloud
   ```

3. **Restart services** for changes to take effect

**To change LiveKit API keys:**

1. Update `backend/.env.local`:
   ```env
   LIVEKIT_API_KEY=your_new_key
   LIVEKIT_API_SECRET=your_new_secret
   ```

2. Restart the backend API server

## Benefits

✅ Single source of truth for LiveKit configuration
✅ Easy to update - change one file, reflects everywhere
✅ Type-safe configuration access
✅ Validation functions to ensure config is complete
✅ Clear documentation of all LiveKit settings

