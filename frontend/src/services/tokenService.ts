import { authService } from './authService'
import { apiConfig } from '../config/api'

const API_URL = apiConfig.httpUrl

export interface TokenResponse {
  token: string
  url: string
  room_name: string
  identity: string
}

export async function getLiveKitToken(roomName: string, identity?: string): Promise<TokenResponse> {
  // Check if user is authenticated
  if (!authService.isAuthenticated()) {
    throw new Error('You must be logged in to start a recording. Please log in and try again.')
  }

  const requestBody: { room_name: string; identity?: string } = {
    room_name: roomName,
  }
  
  // Only include identity if it's provided
  if (identity) {
    requestBody.identity = identity
  }
  
  const authHeaders = authService.getAuthHeaders()
  if (!authHeaders['Authorization']) {
    throw new Error('Authentication token is missing. Please log in again.')
  }
  
  const response = await fetch(`${API_URL}/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
    },
    body: JSON.stringify(requestBody),
  })

  if (!response.ok) {
    let errorMessage = 'Failed to get LiveKit token'
    try {
      const error = await response.json()
      errorMessage = error.detail || error.message || errorMessage
      
      // Handle authentication errors specifically
      if (response.status === 401) {
        if (error.detail?.includes('Invalid') || error.detail?.includes('credentials')) {
          errorMessage = 'Invalid authentication credentials. Please log in again.'
          // Clear invalid token
          authService.logout()
        } else {
          errorMessage = 'Authentication required. Please log in again.'
        }
      }
    } catch {
      if (response.status === 401) {
        errorMessage = 'Authentication required. Please log in again.'
      } else {
        errorMessage = `Server error: ${response.status} ${response.statusText}`
      }
    }
    throw new Error(errorMessage)
  }

  return response.json()
}

