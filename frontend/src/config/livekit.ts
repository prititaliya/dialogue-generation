/**
 * Centralized LiveKit configuration.
 * All LiveKit-related configuration should be imported from here.
 * 
 * Note: The LiveKit URL is typically received from the backend token endpoint,
 * but this file provides a fallback if needed.
 */

// LiveKit URL (fallback - usually comes from backend token response)
// This should match the default in backend/config.py
export const LIVEKIT_URL = import.meta.env.VITE_LIVEKIT_URL || 'wss://voice-agent-dsp63yns.livekit.cloud';

/**
 * Get LiveKit configuration
 * @returns LiveKit configuration object
 */
export function getLiveKitConfig() {
  return {
    url: LIVEKIT_URL,
  };
}

/**
 * Check if LiveKit configuration is available
 * @returns true if configuration is valid
 */
export function isLiveKitConfigured(): boolean {
  return !!LIVEKIT_URL;
}

