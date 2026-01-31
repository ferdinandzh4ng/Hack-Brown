# AgentCity Intent Dispatcher

An intelligent agent that parses user travel requests and creates structured activity plans.

## Features

- **Intent Parsing**: Analyzes user travel requests and extracts key information (location, budget, time, preferences)
- **Vagueness Detection**: Identifies vague requests and prompts users for clarification
- **Transaction Analysis**: Analyzes user transaction history to provide personalized recommendations
- **Location Research**: Researches popular activities in specified locations
- **Activity Planning**: Generates structured activity lists with constraints and agent recommendations

## Capabilities

The agent can handle various types of travel requests:

- **Simple Location Requests**: "I want to visit Paris"
- **Detailed Plans**: "Plan a weekend trip to New York City with a budget of $500"
- **Specific Queries**: "Find me a restaurant in Boston for dinner tonight"
- **Multi-day Trips**: "Plan a 3-day trip to Tokyo with activities"

## How It Works

1. **Message Reception**: Receives chat messages from users via the Chat Protocol
2. **Structured Extraction**: Uses structured output protocol to extract intent parameters from user messages
3. **Intent Processing**: 
   - Checks if request is vague and needs clarification
   - Analyzes user transaction history for personalized recommendations
   - Researches location-specific activities if needed
   - Generates structured activity plans
4. **Response**: Returns either:
   - A complete dispatch plan with activities, constraints, and agent recommendations
   - A clarification prompt if more information is needed
   - An error message if processing fails

## Output Format

The agent returns structured JSON with:

```json
{
  "activity_list": [
    "specific activity 1",
    "specific activity 2",
    ...
  ],
  "constraints": {
    "budget": number or null,
    "start_time": "ISO 8601 datetime string or null",
    "end_time": "ISO 8601 datetime string or null",
    "location": "...",
    "preferences": [ ... ]
  },
  "agents_to_call": [ ... ],
  "notes": "short explanation"
}
```

## Integration

This agent integrates with:
- **MongoDB**: For transaction history analysis
- **ASI-1 AI**: For natural language processing and intent extraction
- **Structured Output Protocol**: For reliable data extraction
- **Chat Protocol**: For user communication

## Usage Examples

**Example 1: Simple Request**
```
User: "I want to visit Paris"
Agent: [Clarification prompt or activity plan based on transaction history]
```

**Example 2: Detailed Request**
```
User: "Plan a weekend trip to New York City with a budget of $500"
Agent: [Structured activity plan with budget constraints]
```

**Example 3: Specific Query**
```
User: "Find me a restaurant in Boston for dinner tonight"
Agent: [Restaurant recommendation with booking agent call]
```

## Technical Details

- **Protocols**: Chat Protocol, Structured Output Protocol
- **Storage**: Session-based conversation state management
- **Error Handling**: Graceful error handling with user-friendly messages
- **State Management**: Maintains conversation context across multiple messages

## Requirements

- Python 3.8+
- uagents framework
- MongoDB connection (optional, for transaction analysis)
- ASI-1 API key

## Author

AgentCity Team

