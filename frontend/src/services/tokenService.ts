const API_URL = import.meta.env.VITE_HTTP_API_URL || import.meta.env.VITE_API_URL?.replace('ws://', 'http://').replace('wss://', 'https://') || 'http://localhost:8000'

export interface TokenResponse {
  token: string
  url: string
  room_name: string
  identity: string
}

export async function getLiveKitToken(roomName: string, identity?: string): Promise<TokenResponse> {
  const requestBody: { room_name: string; identity?: string } = {
    room_name: roomName,
  }
  
  // Only include identity if it's provided
  if (identity) {
    requestBody.identity = identity
  }
  
  const response = await fetch(`${API_URL}/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(requestBody),
  })

  if (!response.ok) {
    const error = await response.json()
    throw new Error(error.detail || 'Failed to get LiveKit token')
  }

  return response.json()
}

