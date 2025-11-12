const HTTP_API_URL = import.meta.env.VITE_HTTP_API_URL || import.meta.env.VITE_API_URL?.replace('ws://', 'http://').replace('wss://', 'https://') || 'http://localhost:8000'

export interface User {
  id: number
  username: string
  email: string
  is_active: boolean
  created_at?: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

class AuthService {
  private tokenKey = 'auth_token'
  private userKey = 'auth_user'

  async signup(username: string, email: string, password: string): Promise<AuthResponse> {
    try {
      const response = await fetch(`${HTTP_API_URL}/auth/signup`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, email, password }),
      })

      if (!response.ok) {
        let errorMessage = 'Signup failed'
        try {
          const error = await response.json()
          errorMessage = error.detail || error.message || errorMessage
        } catch {
          // If response is not JSON, try to get text
          try {
            const text = await response.text()
            errorMessage = text || errorMessage
          } catch {
            errorMessage = `Server error: ${response.status} ${response.statusText}`
          }
        }
        throw new Error(errorMessage)
      }

      const data: AuthResponse = await response.json()
      this.setToken(data.access_token)
      this.setUser(data.user)
      return data
    } catch (error) {
      if (error instanceof TypeError && error.message.includes('fetch')) {
        throw new Error('Cannot connect to server. Please make sure the backend server is running.')
      }
      throw error
    }
  }

  async login(username: string, password: string): Promise<AuthResponse> {
    const response = await fetch(`${HTTP_API_URL}/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username, password }),
    })

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.detail || 'Login failed')
    }

    const data: AuthResponse = await response.json()
    this.setToken(data.access_token)
    this.setUser(data.user)
    return data
  }

  async getCurrentUser(): Promise<User | null> {
    const token = this.getToken()
    if (!token) {
      return null
    }

    try {
      const response = await fetch(`${HTTP_API_URL}/auth/me`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })

      if (!response.ok) {
        this.logout()
        return null
      }

      const user: User = await response.json()
      this.setUser(user)
      return user
    } catch (error) {
      console.error('Error fetching current user:', error)
      this.logout()
      return null
    }
  }

  getToken(): string | null {
    return localStorage.getItem(this.tokenKey)
  }

  setToken(token: string): void {
    localStorage.setItem(this.tokenKey, token)
  }

  getUser(): User | null {
    const userStr = localStorage.getItem(this.userKey)
    if (!userStr) return null
    try {
      return JSON.parse(userStr)
    } catch {
      return null
    }
  }

  setUser(user: User): void {
    localStorage.setItem(this.userKey, JSON.stringify(user))
  }

  logout(): void {
    localStorage.removeItem(this.tokenKey)
    localStorage.removeItem(this.userKey)
  }

  isAuthenticated(): boolean {
    return !!this.getToken()
  }

  getAuthHeaders(): Record<string, string> {
    const token = this.getToken()
    return token ? { 'Authorization': `Bearer ${token}` } : {}
  }
}

export const authService = new AuthService()

