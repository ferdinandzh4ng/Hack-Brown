# Backup Protocol for API Failures

## Overview
This document describes the backup protocol implemented to handle API failures, timeouts, and network errors gracefully.

## Components

### 1. Backup Dataset
**Location**: `Frontend/data/backup-providence.json`

A comprehensive Providence, Rhode Island itinerary with:
- 8 activities (breakfast, museum, lunch, afternoon activity, coffee, dinner, dessert)
- Transit information between venues
- Real coordinates for map display
- Total cost: $148 (within $200 budget)
- Remaining budget: $52

### 2. Backup Protocol Utility
**Location**: `Frontend/lib/backup-protocol.ts`

The `fetchScheduleWithBackup` function provides:
- **Timeout Handling**: 10-second timeout on API calls
- **Automatic Fallback**: Switches to Providence backup data on failure
- **Error Classification**: Distinguishes between timeout, network, and API errors
- **User Notification**: Returns appropriate warning messages

## How It Works

### Normal Flow
1. User submits search request
2. API call is made with 10-second timeout
3. Response is transformed and displayed
4. Budget is calculated from API response

### Backup Flow (When API Fails)
1. API call fails (timeout/network/error)
2. System logs the failure
3. Backup Providence dataset is loaded
4. Data is transformed using the same pipeline
5. Warning message is shown to user:
   - "⚠️ API timeout - showing Providence sample itinerary"
   - "⚠️ Network error - showing Providence sample itinerary"
   - "⚠️ API unavailable - showing Providence sample itinerary"
6. Warning auto-dismisses after 5 seconds
7. Results are displayed normally

## Usage

```typescript
import { fetchScheduleWithBackup } from '@/lib/backup-protocol';

const result = await fetchScheduleWithBackup(
  chatInput,
  location,
  startTime,
  endTime,
  transformBackendResponse
);

// Result contains:
// - recommendations: Array of activities
// - transitInfo: Map of transit between activities
// - budget: Total budget (number or null)
// - isBackup: Boolean indicating if backup data was used
// - backupReason: Optional warning message if backup was used
```

## Testing the Backup

To test the backup protocol:

1. **Simulate Timeout**: Stop the backend server
2. **Simulate Network Error**: Use invalid API endpoint
3. **Simulate API Error**: Backend returns error response

In all cases, the system will automatically fall back to the Providence dataset.

## Benefits

- **Resilience**: Application remains functional even when backend is down
- **User Experience**: No blank screens or cryptic error messages
- **Development**: Can work on frontend without backend running
- **Demonstration**: Always have working data to show

## Future Enhancements

- Multiple backup datasets for different cities
- Configurable timeout duration
- Retry logic before falling back
- Cache successful API responses
- User preference to always use backup data
