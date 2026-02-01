import backupProvidenceData from '@/data/backup-providence.json';

/**
 * Backup protocol for API failures
 * This function wraps the API call with timeout handling and automatic fallback
 * to Providence sample data when the API is unavailable
 */
export async function fetchScheduleWithBackup(
    chatInput: string,
    location: string,
    startTime: string,
    endTime: string,
    transformBackendResponse: (data: any) => Promise<any>
): Promise<{
    recommendations: any[];
    transitInfo: Map<number, any>;
    budget: number | null;
    isBackup: boolean;
    backupReason?: string;
}> {
    // Convert local datetime to ISO 8601
    const startTimeISO = new Date(startTime).toISOString();
    const endTimeISO = new Date(endTime).toISOString();

    // Create abort controller for timeout (10 seconds)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);

    try {
        // Call bridge server API
        const response = await fetch('http://localhost:8005/api/schedule', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                user_request: chatInput,
                location: location,
                start_time: startTimeISO,
                end_time: endTimeISO
            }),
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
            throw new Error(`API error: ${response.statusText}`);
        }

        const result = await response.json();

        if (!result.success) {
            throw new Error(result.error || 'Unknown error');
        }

        // Transform response
        const { recommendations, transitInfo } = await transformBackendResponse(result.data);

        return {
            recommendations,
            transitInfo,
            budget: result.data?.budget || null,
            isBackup: false
        };

    } catch (fetchError) {
        clearTimeout(timeoutId);

        // Determine the type of error
        const isTimeout = fetchError instanceof Error && fetchError.name === 'AbortError';
        const isNetworkError = fetchError instanceof TypeError;

        let backupReason: string;
        if (isTimeout) {
            backupReason = '⚠️ API timeout - showing Providence sample itinerary';
        } else if (isNetworkError) {
            backupReason = '⚠️ Network error - showing Providence sample itinerary';
        } else {
            backupReason = '⚠️ API unavailable - showing Providence sample itinerary';
        }

        console.warn('API call failed:', fetchError);
        console.log('Using backup Providence dataset...');

        // Use backup Providence data
        const { recommendations, transitInfo } = await transformBackendResponse(backupProvidenceData);

        return {
            recommendations,
            transitInfo,
            budget: backupProvidenceData.budget || null,
            isBackup: true,
            backupReason
        };
    }
}
