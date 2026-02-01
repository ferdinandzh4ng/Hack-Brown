# Hack-Brown Copilot Instructions

## Architecture Overview

**Hack-Brown** is an agentic travel planning system built on **uagents framework**. Core design: user travel requests → intent parsing → clarification/research if needed → structured dispatch plan with activity categories.

### Core Message Flow
1. **User sends Chat Protocol message** to `agents.py`
2. **Structured Output Protocol** extracts raw intent via ASI-1 AI agent (address: `agent1qtlpfshtlcxekgrfcpmv7m9zpajuwu7d5jfyachvpa4u3dkt6k0uwwp2lct`)
3. **`dispatch_intent()`** determines: vague request → clarification workflow OR sufficient data → dispatch plan
4. **Response types**: `{"type": "dispatch_plan"|"clarification_needed"|"error", "data": {...}}`

### Key Components

- **[agents.py](Agents/agents.py)**: Runs on Agentverse (port 8001). Receives Chat Protocol messages, forwards to structured output AI, processes responses via `dispatch_intent()`. Session-based state in `ctx.storage`.
- **[functions.py](Agents/functions.py)**: Intent dispatch logic. Three main functions: `check_vagueness()`, `research_location_activities()`, `finalize_activity_list()`.
- **MongoDB** (optional): Analyzes user transaction history to infer activity preferences when planning similar trips.
- **ASI-1 AI API**: NLP backend for vagueness detection, transaction analysis, and activity list generation. Uses `openai` client pointed to `https://api.asi1.ai/v1`.

## Critical Patterns

### The Vague Request Workflow (Most Important Flow)
When user request is vague (e.g., "Plan me a day in Paris"), `dispatch_intent()` executes this multi-step flow:

1. **Detect Vagueness**: `check_vagueness(user_request)` → returns `{"is_vague": bool, "location": str, "reason": str}`
2. **Extract Basics**: Parse budget/times from request via ASI-1
3. **Check Transaction History**: `analyze_transaction_preferences(user_transactions, location)` → infers past preferences
   - If sufficient data (3+ similar activities): **skip clarification**, finalize activity list directly using inferred preferences
   - If insufficient data: continue to step 4
4. **Research Location**: `research_location_activities(location)` → returns `{"general_categories": [...]}`
5. **Prompt User**: `create_preference_prompt(categories)` → asks user to select from 6 category types (eat, sightsee, shop, entertainment, outdoor, cultural)
6. **Store Conversation State**: Save in `ctx.storage[conversation_state_{sender_address}]` with `waiting_for_clarification: True`
7. **Next Message**: User responds (e.g., "1, 3, 5" or "eat, sightsee") → `dispatch_intent()` detects `waiting_for_clarification` flag, calls `finalize_activity_list()`
8. **Return Dispatch Plan**: Activity list with GENERAL categories (not specific venues)

**Key invariant**: All `activity_list` entries must be general categories like "eat", "sightsee", "shop" — never specific venue names.

### Non-Vague Request Path
User provides enough detail (e.g., "Book me a museum visit in Paris tomorrow afternoon") → skip to direct `finalize_activity_list()` → return dispatch plan immediately.

### JSON Response Validation Critical Details
- `safe_json_parse()` handles malformed AI responses: extracts JSON from markdown blocks, balances braces, recovers partial responses
- All prompts return ONLY JSON (no markdown wrapper expected in final response)
- If parsing fails → fallback values extracted via regex (`activity_list` defaults to `["eat", "sightsee"]`)

### Conversation State Schema
```
conversation_state_{sender_address}: {
  "waiting_for_clarification": True/False,
  "original_request": str,
  "location": str,
  "budget": str (or "null"),
  "start_time": str or "null",
  "end_time": str or "null",
  "categories": [{"category": str, "description": str, "examples": [str]}],
  "transaction_data": {optional transaction analysis result}
}
```

## Environment Configuration & Startup

Required `.env` variables:
```
AGENT_SEED_PHRASE=<your-seed>
FETCH_API_KEY=<asi1-api-key>
# MongoDB connection (either full string or components):
MONGODB_CONNECTION_STRING=mongodb+srv://...  # OR individual components below:
MONGODB_USERNAME=<username>
MONGODB_PASSWORD=<password>
MONGODB_CLUSTER=<cluster-name>
MONGODB_DATABASE=HackBrown
```

**Startup**:
```bash
cd Agents && python agents.py
# Agent address printed to stdout; needed for mailbox setup on Agentverse
```

Agent runs on **testnet** (no funds required). Listens on port 8001.

## System Prompts (All in functions.py)
These are NOT aspirational — they directly control AI behavior:

- **VAGUENESS_CHECK_PROMPT**: Defines what constitutes a vague request. "Plan me a day in X" → vague. "Visit the Eiffel Tower" → not vague.
- **RESEARCH_PROMPT**: Generates 4-6 activity categories for a location with examples. Response format must have `general_categories` array.
- **FINALIZE_PROMPT**: Takes user preferences + location + budget/times → returns `activity_list` (general categories), `constraints`, `agents_to_call`, `notes`. **Must ensure `activity_list` is never empty**.
- **DISPATCHER_SYSTEM_PROMPT**: Fallback for non-vague requests. Same output format as FINALIZE_PROMPT.

All prompts expect ONLY valid JSON responses. Markdown code blocks not accepted.

### Error Handling Strategy
- All API calls wrapped in try/except with graceful degradation
- Vagueness check failure → assume not vague (proceeds with normal dispatch)
- MongoDB errors → skip transaction analysis (continues to clarification if vague)
- AI response parsing failure → `safe_json_parse()` extracts partial data or uses fallback values
- Session not found → discard message with warning log (no user response sent)
- Empty `activity_list` → automatic fallback to `["eat", "sightsee"]` (critical invariant maintained)

## Authentication & User Management

### Login System ([Login.py](Agents/Login.py))
**`LoginManager` class** handles user authentication with MongoDB and Google OAuth2:

**Traditional Authentication**:
- **`register_user(email, username, password, full_name)`**: Creates new user with hashed password (SHA-256 + salt). Enforces unique email/username constraints, 6+ char password. Returns (success: bool, message: str).
- **`login_user(username_or_email, password, remember_me)`**: Authenticates user, creates session token (30 days if remember_me=True, else 7 days). Returns (success: bool, message: str, token: str).

**Google OAuth2 Sign-In**:
- **`google_sign_in(google_token, remember_me)`**: Verifies Google OAuth2 ID token, creates or links user. Auto-creates user if first-time Google sign-in. Returns (success: bool, message: str, token: str).
- **`link_google_account(session_token, google_token)`**: Links Google account to existing user. Allows users with traditional auth to add Google sign-in option.

**Session Management**:
- **`verify_session(session_token)`**: Validates token against MongoDB sessions collection, checks expiry, updates last_activity. Returns (is_valid: bool, user_data: Dict).
- **`logout_user(session_token)`**: Invalidates session by deleting token from DB.

**User Profile**:
- **`get_user_profile(user_id)`**: Retrieves user profile (email, username, preferences, created_at, last_login) without password hash.
- **`update_user_preferences(user_id, preferences)`**: Updates user activity categories and budget preferences.

**MongoDB Collections**:
- `users`: email (unique), username (unique), password_hash (nullable for Google auth), full_name, google_id (for OAuth users), picture_url, auth_method, preferences, created_at, last_login, login_count, is_active
- `sessions`: token (unique), user_id, auth_method, expires_at, last_activity, remember_me flag
- `login_logs`: Audit trail of all login attempts (success/fail)

**Password Security**: Uses SHA-256 with 16-byte random salt. Salt is prepended to hash as `salt$hash` format.

**Environment Configuration**:
```
# Traditional auth (already configured)
MONGODB_CONNECTION_STRING=mongodb+srv://...
MONGODB_DATABASE=HackBrown

# Google OAuth2 (add to .env for Google Sign-In)
GOOGLE_CLIENT_ID=<your-google-client-id>  # Get from Google Cloud Console
```

**Frontend Integration Pattern**: 
```python
from Login import LoginManager
login_mgr = LoginManager()

# Traditional login
success, msg, token = login_mgr.login_user(username, password)

# Google sign-in (receive google_token from frontend after OAuth2 flow)
success, msg, token = login_mgr.google_sign_in(google_token)
```

## Project Files Overview

- **[Agents/budgetFilterAgent.py](Agents/budgetFilterAgent.py)**, **[fundAllocationAgent.py](Agents/fundAllocationAgent.py)**, **[eventsScaperAgent.py](Agents/eventsScaperAgent.py)**: Specialist agent templates (budget filtering, fund allocation, event scraping). Currently minimal/placeholder implementations.
- **[Frontend/](Frontend/)**: Next.js React app with Tailwind CSS. Displays demo UI for travel planning with budget breakdown. Data files in `data/` (insights.json, user-history.json, community-insights.json) are static references for UI testing.

## Dependencies
- `uagents`, `uagents_core` - Agent framework and Chat Protocol
- `openai` - ASI-1 API client
- `pymongo` - MongoDB integration
- `python-dotenv` - Environment configuration
- `fastapi`, `uvicorn` - (included via uagents)
