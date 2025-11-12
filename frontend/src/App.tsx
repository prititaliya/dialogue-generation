import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import { Login } from './components/Login'
import { Signup } from './components/Signup'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Dashboard } from './components/Dashboard'

function LoginPage() {
  const navigate = useNavigate()
  return (
    <Login
      onLogin={() => navigate('/')}
    />
  )
}

function SignupPage() {
  const navigate = useNavigate()
  return (
    <Signup
      onSignup={() => navigate('/')}
    />
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
