# Hack-Brown Copilot Instructions

## Architecture Overview

**Hack-Brown** is an agentic travel planning system built on the **uagents framework**. It uses an intent-based dispatch pattern where user travel requests flow through a chain of specialized agents.

### Core Flow
1. **AgentCity Intent Dispatcher** (`agents.py`) - Main entry point listening on Chat Protocol
2. **Structured Output** - Uses AI agent to parse user intent into `IntentRequest` model
3. **Intent Processing** (`functions.py`) - Analyzes request, manages conversation state
4. **Response Types** - Returns dispatch plan, clarification prompt, or error

### Key Components

- **[agents.py](Agents/agents.py)**: Main agent hosting on Agentverse. Handles Chat Protocol messages, sends to AI for structured extraction, processes responses. Uses session-based storage.
- **[functions.py](Agents/functions.py)**: Business logic hub. Contains vagueness detection, location research, transaction analysis, and activity finalization.
- **MongoDB Integration**: Optional transaction history analysis for personalized recommendations (connection string via env vars).
- **ASI-1 AI API**: Used for NLP tasks (vagueness check, transaction analysis, activity finalization).

## Critical Patterns

### Intent Processing Pipeline
The `dispatch_intent()` function handles three paths:

1. **Vague Request Detection** → Clarification Workflow
   - `check_vagueness()` determines if location is extractable
   - If vague: research activities via `research_location_activities()`, prompt user for preferences
   - Stores conversation state in `ctx.storage` with `waiting_for_clarification` flag

2. **Transaction-Based Personalization**
   - `get_user_transactions()` fetches user history from MongoDB
   - `analyze_transaction_preferences()` infers activity patterns from past spending
   - If sufficient data (3+ similar activities), skips clarification and generates plan directly

3. **Direct Dispatch**
   - Non-vague requests proceed directly to activity finalization

### Conversation State Management
- Stored in `ctx.storage` with key `conversation_state_{sender_address}`
- Persists: original request, extracted location/budget/time, research categories, transaction data
- Cleared after successful dispatch plan generation

### Response Models
- **IntentRequest**: Structured input extracted from user text (user_request, location, budget, times, preferences)
- **IntentResponse**: Structured output containing activity_list, constraints, agents_to_call, notes

## Environment Configuration

Required `.env` variables:
- `AGENT_SEED_PHRASE` - Agent identity seed
- `FETCH_API_KEY` - ASI-1 API credentials
- `MONGODB_CONNECTION_STRING` OR (`MONGODB_USERNAME`, `MONGODB_PASSWORD`, `MONGODB_CLUSTER`, `MONGODB_DATABASE`)

Agent runs on **testnet** (no funds needed for registration). Default port: 8001.

## Development Patterns

### Adding New Intent Handlers
1. Define new `check_*()` function in [functions.py](Agents/functions.py) following vagueness/research pattern
2. Add logic in `dispatch_intent()` to branch on condition
3. Return dict with `{"type": "...", "data": {...}}`

### Modifying AI Prompts
All system prompts are defined as constants in [functions.py](Agents/functions.py):
- `VAGUENESS_CHECK_PROMPT` - JSON validation for vagueness detection
- `RESEARCH_PROMPT` - Activity categories generation
- `FINALIZE_PROMPT` - Personalized activity list creation
- `DISPATCHER_SYSTEM_PROMPT` - Agent selection and dispatch logic

**Important**: Prompts return ONLY valid JSON (no markdown, no extra text). Responses are immediately parsed with `json.loads()`.

### Error Handling Strategy
- All API calls wrapped in try/except with graceful degradation
- Vagueness check failure → assume not vague
- MongoDB errors → skip transaction analysis
- AI response parsing failure → return error response type
- Session not found → discard message with warning log

## Common Workflows

### Debugging Intent Processing
1. Check logs: `ctx.logger.info()` statements in `agents.py` trace message flow
2. Inspect conversation state: Set breakpoint after `ctx.storage.get(conversation_state_key)`
3. Validate JSON extraction: Print `msg.output` from structured output response
4. Test AI parsing: Call `check_vagueness()` or `analyze_transaction_preferences()` directly

### Testing New Activity Categories
- Modify `RESEARCH_PROMPT` to include new categories
- Test via `research_location_activities("test_location")`
- Verify returned JSON has `general_categories` array with category/description/examples

### Adding Transaction Analysis
- Ensure MongoDB has `transactions` collection with user_id index
- Transaction schema: `{user_id, activity/name, category/type, amount, location, timestamp}`
- Test via `analyze_transaction_preferences()` with mock transaction list

## eventsScaperAgent.py
Currently empty placeholder. Intended for event-specific scraping logic (museum hours, event listings, etc.).

## Dependencies
- `uagents`, `uagents_core` - Agent framework and Chat Protocol
- `openai` - ASI-1 API client
- `pymongo` - MongoDB integration
- `python-dotenv` - Environment configuration
- `fastapi`, `uvicorn` - (included via uagents)
