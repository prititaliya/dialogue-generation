import { useState, useEffect } from 'react'
import type { Transcript } from './types'
import { TranscriptService } from './services/transcriptService'
import { LiveKitService } from './services/livekit'
import { getLiveKitToken } from './services/tokenService'

const WS_API_URL = import.meta.env.VITE_API_URL || 'ws://localhost:8000'

function App() {
  const [transcripts, setTranscripts] = useState<Transcript[]>([])
  const [wsConnected, setWsConnected] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [roomName, setRoomName] = useState('')
  const [error, setError] = useState<string | null>(null)
  
  const [transcriptService] = useState(() => {
    try {
      return new TranscriptService(WS_API_URL)
    } catch (err) {
      console.error('Failed to create TranscriptService:', err)
      return null as any
    }
  })
  const [liveKitService] = useState(() => {
    try {
      return new LiveKitService()
    } catch (err) {
      console.error('Failed to create LiveKitService:', err)
      return null as any
    }
  })

  // WebSocket connection for transcripts
  useEffect(() => {
    if (!transcriptService) {
      return
    }

    let unsubscribe: (() => void) | undefined
    
    try {
      const handleTranscript = (transcript: Transcript) => {
        setTranscripts(prev => {
          // Avoid duplicates
          const exists = prev.some(t => 
            t.speaker === transcript.speaker && 
            t.text === transcript.text && 
            t.is_final === transcript.is_final
          )
          if (exists) {
            return prev;
          }
          return [...prev, transcript];
        })
      }

      unsubscribe = transcriptService.onConnect(() => {
        setWsConnected(true)
      })

      transcriptService.connect(handleTranscript)
    } catch (err) {
      console.error('Failed to connect WebSocket:', err)
      setWsConnected(false)
    }

    return () => {
      if (unsubscribe) {
        unsubscribe()
      }
      try {
        if (transcriptService) {
          transcriptService.disconnect()
        }
      } catch (err) {
        console.error('Error disconnecting:', err)
      }
    }
  }, [transcriptService])

  const handleStartRecording = async () => {
    if (!roomName.trim()) {
      setError('Please enter a room name')
      return
    }

    if (!liveKitService) {
      setError('LiveKit service not available')
      return
    }

    try {
      setError(null)
      setIsRecording(true)

      // Get LiveKit token from backend
      const tokenData = await getLiveKitToken(roomName)

      // Connect to LiveKit room
      await liveKitService.connect(tokenData.url, tokenData.token, tokenData.room_name)
    } catch (err) {
      console.error('❌ Failed to start recording:', err)
      setError(err instanceof Error ? err.message : 'Failed to start recording')
      setIsRecording(false)
    }
  }

  const handleStopRecording = async () => {
    if (!liveKitService) {
      setError('LiveKit service not available')
      return
    }

    try {
      await liveKitService.disconnect()
      setIsRecording(false)
    } catch (err) {
      console.error('Failed to stop recording:', err)
      setError(err instanceof Error ? err.message : 'Failed to stop recording')
    }
  }

  return (
    <div style={{ 
      padding: '20px', 
      fontFamily: 'Arial, sans-serif',
      minHeight: '100vh',
      background: '#fafafa'
    }}>
      <h1 style={{ color: '#333', marginBottom: '20px' }}>Real-Time Transcription</h1>
      
      {/* Connection Status */}
      <div style={{ 
        padding: '15px', 
        marginBottom: '20px',
        background: wsConnected ? '#d4edda' : '#f8d7da',
        border: `2px solid ${wsConnected ? '#28a745' : '#dc3545'}`,
        borderRadius: '5px',
        color: wsConnected ? '#155724' : '#721c24'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <strong>WebSocket Status:</strong> {wsConnected ? '✅ Connected' : '❌ Disconnected'}
            <br />
            <small>URL: {WS_API_URL}/ws/transcripts</small>
          </div>
          {!wsConnected && (
            <button
              onClick={() => {
                if (transcriptService) {
                  transcriptService.disconnect();
                  setTimeout(() => {
                    transcriptService.connect(
                      (transcript) => {
                        setTranscripts(prev => {
                          const exists = prev.some(t => 
                            t.speaker === transcript.speaker && 
                            t.text === transcript.text && 
                            t.is_final === transcript.is_final
                          );
                          return exists ? prev : [...prev, transcript];
                        });
                      }
                    );
                  }, 500);
                }
              }}
              style={{
                padding: '8px 16px',
                background: '#007bff',
                color: 'white',
                border: 'none',
                borderRadius: '5px',
                cursor: 'pointer',
                fontSize: '14px'
              }}
            >
              🔄 Reconnect
            </button>
          )}
        </div>
      </div>

      {/* Recording Controls */}
      <div style={{ 
        padding: '20px',
        marginBottom: '20px',
        background: 'white',
        borderRadius: '5px',
        border: '1px solid #ddd',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
      }}>
        <h3 style={{ marginTop: 0, marginBottom: '15px' }}>Recording Controls</h3>
        
        {!isRecording ? (
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <input
              type="text"
              value={roomName}
              onChange={(e) => setRoomName(e.target.value)}
              placeholder="Enter room name (e.g., 'meeting-1')"
              disabled={isRecording}
              style={{
                flex: 1,
                padding: '10px',
                border: '1px solid #ddd',
                borderRadius: '5px',
                fontSize: '16px'
              }}
            />
            <button
              onClick={handleStartRecording}
              disabled={!roomName.trim() || !wsConnected}
              style={{
                padding: '10px 20px',
                background: !roomName.trim() || !wsConnected ? '#ccc' : '#dc3545',
                color: 'white',
                border: 'none',
                borderRadius: '5px',
                fontSize: '16px',
                fontWeight: 'bold',
                cursor: !roomName.trim() || !wsConnected ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              <span style={{
                width: '12px',
                height: '12px',
                borderRadius: '50%',
                background: 'white'
              }}></span>
              Start Recording
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              flex: 1,
              padding: '10px',
              background: '#fff3cd',
              borderRadius: '5px',
              border: '1px solid #ffc107'
            }}>
              <span style={{
                width: '12px',
                height: '12px',
                borderRadius: '50%',
                background: '#dc3545',
                animation: 'pulse 1.5s infinite'
              }}></span>
              <strong style={{ color: '#856404' }}>Recording in room: {roomName}</strong>
            </div>
            <button
              onClick={handleStopRecording}
              style={{
                padding: '10px 20px',
                background: '#6c757d',
                color: 'white',
                border: 'none',
                borderRadius: '5px',
                fontSize: '16px',
                fontWeight: 'bold',
                cursor: 'pointer'
              }}
            >
              Stop Recording
            </button>
          </div>
        )}

        {error && (
          <div style={{
            marginTop: '15px',
            padding: '12px',
            background: '#f8d7da',
            border: '1px solid #dc3545',
            borderRadius: '5px',
            color: '#721c24'
          }}>
            <strong>Error:</strong> {error}
          </div>
        )}
      </div>
      
      {/* Transcripts Display */}
      <div style={{ 
        marginTop: '20px',
        padding: '15px',
        background: 'white',
        borderRadius: '5px',
        border: '1px solid #ddd',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
      }}>
        <h3 style={{ marginTop: 0 }}>Transcripts ({transcripts.length})</h3>
        {transcripts.length === 0 ? (
          <p style={{ color: '#666', fontStyle: 'italic' }}>
            {isRecording 
              ? 'Start speaking to see transcripts appear here...' 
              : 'No transcripts yet. Start recording to begin transcription.'}
          </p>
        ) : (
          <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
            {transcripts.map((t, i) => (
              <div key={i} style={{ 
                margin: '10px 0', 
                padding: '12px', 
                background: '#f8f9fa',
                borderRadius: '5px',
                borderLeft: `4px solid ${t.is_final ? '#007bff' : '#ffc107'}`
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                  <strong style={{ color: '#007bff' }}>
                    {t.speaker || 'Unknown Speaker'}
                  </strong>
                  {!t.is_final && (
                    <span style={{
                      fontSize: '12px',
                      color: '#856404',
                      background: '#fff3cd',
                      padding: '2px 8px',
                      borderRadius: '4px'
                    }}>
                      Interim
                    </span>
                  )}
                </div>
                <p style={{ margin: 0, color: '#333' }}>
                  {t.text}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  )
}

export default App
