/**
 * Centralized API configuration
 * 
 * This file automatically detects the current host and constructs API URLs accordingly.
 * It works for both localhost and network IP addresses (e.g., http://192.168.2.12:5174/)
 * 
 * How it works:
 * - If you access the app at http://192.168.2.12:5174/, it will automatically use http://192.168.2.12:8000 for the backend API
 * - If you access at http://localhost:5174/, it will use http://localhost:8000
 * - The backend port defaults to 8000, but can be overridden with VITE_BACKEND_PORT env variable
 * 
 * Environment Variables (optional):
 * - VITE_API_URL: Override WebSocket URL (e.g., ws://192.168.2.12:8000)
 * - VITE_HTTP_API_URL: Override HTTP URL (e.g., http://192.168.2.12:8000)
 * - VITE_BACKEND_PORT: Override backend port (default: 8000)
 * 
 * Usage:
 *   import { apiConfig } from '../config/api'
 *   const httpUrl = apiConfig.httpUrl  // http://192.168.2.12:8000
 *   const wsUrl = apiConfig.wsUrl      // ws://192.168.2.12:8000
 */

/**
 * Get the current hostname and port from the browser
 */
function getCurrentHost(): { hostname: string; port: string; protocol: string } {
  const { hostname, port, protocol } = window.location;
  return { hostname, port, protocol };
}

/**
 * Get the backend API port (defaults to 8000)
 */
function getBackendPort(): string {
  // Check environment variable first
  if (import.meta.env.VITE_BACKEND_PORT) {
    return import.meta.env.VITE_BACKEND_PORT;
  }
  // Default backend port
  return '8000';
}

/**
 * Construct WebSocket API URL
 */
function getWebSocketApiUrl(): string {
  // Check environment variable first
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  const { hostname, protocol } = getCurrentHost();
  const backendPort = getBackendPort();
  
  // Use wss:// for https://, ws:// for http://
  const wsProtocol = protocol === 'https:' ? 'wss:' : 'ws:';
  
  return `${wsProtocol}//${hostname}:${backendPort}`;
}

/**
 * Construct HTTP API URL
 */
function getHttpApiUrl(): string {
  // Check environment variable first
  if (import.meta.env.VITE_HTTP_API_URL) {
    return import.meta.env.VITE_HTTP_API_URL;
  }

  const { hostname, protocol } = getCurrentHost();
  const backendPort = getBackendPort();
  
  // Use https:// for https://, http:// for http://
  const httpProtocol = protocol === 'https:' ? 'https:' : 'http:';
  
  return `${httpProtocol}//${hostname}:${backendPort}`;
}

/**
 * Export API configuration
 */
export const apiConfig = {
  /**
   * WebSocket API URL (e.g., ws://192.168.2.12:8000 or wss://example.com:8000)
   */
  wsUrl: getWebSocketApiUrl(),
  
  /**
   * HTTP API URL (e.g., http://192.168.2.12:8000 or https://example.com:8000)
   */
  httpUrl: getHttpApiUrl(),
  
  /**
   * Get current host info (for debugging)
   */
  getCurrentHost,
  
  /**
   * Get backend port
   */
  getBackendPort,
};

// Log the API URLs in development mode
if (import.meta.env.DEV) {
  console.log('🔧 API Configuration:', {
    wsUrl: apiConfig.wsUrl,
    httpUrl: apiConfig.httpUrl,
    currentHost: getCurrentHost(),
    backendPort: getBackendPort(),
  });
}

