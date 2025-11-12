import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Transcript } from '../types'
import { TranscriptService } from '../services/transcriptService'
import { LiveKitService } from '../services/livekit'
import { getLiveKitToken } from '../services/tokenService'
import { authService } from '../services/authService'
import type { User } from '../services/authService'

const WS_API_URL = import.meta.env.VITE_API_URL || 'ws://localhost:8000'
const HTTP_API_URL = import.meta.env.VITE_HTTP_API_URL || import.meta.env.VITE_API_URL?.replace('ws://', 'http://').replace('wss://', 'https://') || 'http://localhost:8000'

interface TranscriptFile {
  meeting_name: string
  file_name: string
  total_entries: number
  last_modified: number
}

export function Dashboard() {
  const [transcripts, setTranscripts] = useState<Transcript[]>([])
  const [meetingTitle, setMeetingTitle] = useState<string | null>(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [roomName, setRoomName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const transcriptEndRef = useRef<HTMLDivElement>(null)
  const [availableTranscripts, setAvailableTranscripts] = useState<TranscriptFile[]>([])
  const [selectedMeeting, setSelectedMeeting] = useState<string | null>(null)
  const [loadingTranscripts, setLoadingTranscripts] = useState(false)
  const [initialLoadComplete, setInitialLoadComplete] = useState(false)
  const [user, setUser] = useState<User | null>(null)
  const navigate = useNavigate()
  
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

  // Load user info on mount
  useEffect(() => {
    const loadUser = async () => {
      const currentUser = await authService.getCurrentUser()
      if (currentUser) {
        setUser(currentUser)
      } else {
        navigate('/login')
      }
    }
    loadUser()
  }, [navigate])

  // WebSocket connection for transcripts
  useEffect(() => {
    if (!transcriptService) {
      return
    }

    let unsubscribe: (() => void) | undefined
    
    try {
      const handleCompleteTranscript = (title: string, transcriptList: Transcript[]) => {
        console.log('handleCompleteTranscript called:', { title, count: transcriptList.length });
        setMeetingTitle(title)
        setTranscripts(transcriptList)
        setSelectedMeeting(title)
        refreshTranscriptsList()
        setTimeout(() => {
          transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
        }, 100)
      }

      unsubscribe = transcriptService.onConnect(() => {
        setWsConnected(true)
      })

      const handleRealtimeTranscript = (transcript: Transcript, meetingName?: string) => {
        console.log('Real-time transcript received:', transcript, 'for meeting:', meetingName);
        
        const shouldUpdate = isRecording || 
                             !selectedMeeting || 
                             (meetingName && selectedMeeting === meetingName) ||
                             (meetingTitle && meetingName && meetingTitle === meetingName);
        
        if (shouldUpdate) {
          setTranscripts((prevTranscripts) => {
            const lastIndex = prevTranscripts.length - 1;
            const lastTranscript = prevTranscripts[lastIndex];
            
            if (lastTranscript && 
                lastTranscript.speaker === transcript.speaker && 
                !lastTranscript.is_final && 
                !transcript.is_final) {
              const updated = [...prevTranscripts];
              updated[lastIndex] = transcript;
              return updated;
            } 
            else if (lastTranscript && 
                     lastTranscript.speaker === transcript.speaker && 
                     !lastTranscript.is_final && 
                     transcript.is_final) {
              const updated = [...prevTranscripts];
              updated[lastIndex] = transcript;
              return updated;
            }
            else if (lastTranscript && 
                     lastTranscript.speaker === transcript.speaker && 
                     lastTranscript.is_final && 
                     transcript.is_final &&
                     lastTranscript.text && 
                     transcript.text.includes(lastTranscript.text)) {
              const updated = [...prevTranscripts];
              updated[lastIndex] = transcript;
              return updated;
            }
            else {
              return [...prevTranscripts, transcript];
            }
          });
        }
      };

      transcriptService.connect(
        handleRealtimeTranscript,
        undefined,
        handleCompleteTranscript
      )
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

  useEffect(() => {
    if (transcripts.length > 0) {
      setTimeout(() => {
        transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    }
  }, [transcripts])

  const refreshTranscriptsList = async () => {
    try {
      const response = await fetch(`${HTTP_API_URL}/transcripts/list`, {
        headers: {
          'Content-Type': 'application/json',
          ...authService.getAuthHeaders(),
        },
      })
      if (response.ok) {
        const data = await response.json()
        setAvailableTranscripts(data.transcripts || [])
      }
    } catch (err) {
      console.error('Error refreshing transcripts list:', err)
    }
  }

  const loadTranscript = async (meetingName: string) => {
    if (selectedMeeting && selectedMeeting !== meetingName && transcriptService) {
      transcriptService.unwatchTranscript(selectedMeeting)
    }
    
    setLoadingTranscripts(true)
    try {
      const response = await fetch(`${HTTP_API_URL}/transcripts?meeting_name=${encodeURIComponent(meetingName)}`, {
        headers: {
          'Content-Type': 'application/json',
          ...authService.getAuthHeaders(),
        },
      })
      if (response.ok) {
        const data = await response.json()
        setMeetingTitle(data.meeting_name || meetingName)
        setTranscripts(data.transcripts || [])
        setSelectedMeeting(meetingName)
        console.log('Loaded transcript for:', meetingName, data.transcripts?.length)
        
        if (transcriptService) {
          transcriptService.watchTranscript(meetingName)
        }
      } else {
        const errorData = await response.json()
        setError(`Failed to load transcript: ${errorData.detail || 'Unknown error'}`)
      }
    } catch (err) {
      console.error('Error loading transcript:', err)
      setError('Failed to load transcript')
    } finally {
      setLoadingTranscripts(false)
    }
  }
  
  useEffect(() => {
    if (isRecording && roomName && transcriptService) {
      console.log('Recording started, watching transcript file:', roomName)
      transcriptService.watchTranscript(roomName)
    }
  }, [isRecording, roomName, transcriptService])

  useEffect(() => {
    const loadAvailableTranscripts = async () => {
      try {
        console.log('Fetching transcripts list from:', `${HTTP_API_URL}/transcripts/list`)
        const controller = new AbortController()
        const timeoutId = setTimeout(() => {
          controller.abort()
          console.warn('Request timed out after 5 seconds')
        }, 5000)
        
        const response = await fetch(`${HTTP_API_URL}/transcripts/list`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            ...authService.getAuthHeaders(),
          },
          signal: controller.signal,
        })
        
        clearTimeout(timeoutId)
        
        if (response.ok) {
          const data = await response.json()
          setAvailableTranscripts(data.transcripts || [])
          console.log('Loaded available transcripts:', data.transcripts)
          if (data.transcripts && data.transcripts.length > 0) {
            const mostRecent = data.transcripts[0].file_name
            setLoadingTranscripts(true)
            try {
              const transcriptController = new AbortController()
              const transcriptTimeoutId = setTimeout(() => transcriptController.abort(), 5000)
              
              const transcriptResponse = await fetch(`${HTTP_API_URL}/transcripts?meeting_name=${encodeURIComponent(mostRecent)}`, {
                headers: {
                  'Content-Type': 'application/json',
                  ...authService.getAuthHeaders(),
                },
                signal: transcriptController.signal,
              })
              
              clearTimeout(transcriptTimeoutId)
              if (transcriptResponse.ok) {
                const transcriptData = await transcriptResponse.json()
                setMeetingTitle(transcriptData.meeting_name || mostRecent)
                setTranscripts(transcriptData.transcripts || [])
                setSelectedMeeting(mostRecent)
              } else {
                console.error('Failed to load transcript:', transcriptResponse.status, await transcriptResponse.text())
              }
            } catch (err) {
              console.error('Error loading most recent transcript:', err)
              if (err instanceof Error && err.name === 'AbortError') {
                console.warn('Transcript loading timed out, but page will still render')
              } else {
                setError(`Failed to load transcript: ${err instanceof Error ? err.message : 'Unknown error'}`)
              }
            } finally {
              setLoadingTranscripts(false)
            }
          } else {
            setLoadingTranscripts(false)
          }
        } else if (response.status === 404) {
          console.warn('Transcripts list endpoint not found. The server may need to be restarted.')
          setError('API endpoint not found. Please restart the backend server to load the latest code.')
          setLoadingTranscripts(false)
        } else {
          const errorText = await response.text()
          console.error('Failed to load transcripts list:', response.status, errorText)
          setError(`Failed to load transcripts list: ${response.status} ${errorText}`)
          setLoadingTranscripts(false)
        }
      } catch (err) {
        console.error('Error loading transcripts list:', err)
        if (err instanceof Error && err.name === 'AbortError') {
          setError(`Request timed out. The API server at ${HTTP_API_URL} may not be responding.`)
        } else {
          setError(`Cannot connect to API server at ${HTTP_API_URL}. Make sure the backend server is running.`)
        }
        setLoadingTranscripts(false)
      } finally {
        setInitialLoadComplete(true)
      }
    }
    
    loadAvailableTranscripts()
    
    const safetyTimeout = setTimeout(() => {
      console.warn('Safety timeout: Showing page even though API call may still be pending')
      setInitialLoadComplete(true)
      setLoadingTranscripts(false)
    }, 2000)
    
    return () => {
      clearTimeout(safetyTimeout)
    }
  }, [])

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
      setTranscripts([])
      setMeetingTitle(null)

      const tokenData = await getLiveKitToken(roomName)
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
      
      if (transcriptService && roomName) {
        console.log('Stopping recording, requesting transcript for room:', roomName);
        console.log('WebSocket connected status:', wsConnected);
        
        if (!wsConnected) {
          console.warn('WebSocket not connected, waiting before requesting transcript...');
          setTimeout(() => {
            if (transcriptService && roomName) {
              transcriptService.requestTranscript(roomName);
            }
          }, 500);
        } else {
          transcriptService.requestTranscript(roomName);
        }
      }
    } catch (err) {
      console.error('Failed to stop recording:', err)
      setError(err instanceof Error ? err.message : 'Failed to stop recording')
    }
  }

  const handleLogout = () => {
    authService.logout()
    navigate('/login')
  }

  if (!initialLoadComplete) {
    return (
      <div style={{ 
        padding: '20px', 
        fontFamily: 'Arial, sans-serif',
        minHeight: '100vh',
        background: '#fafafa',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexDirection: 'column',
        gap: '20px'
      }}>
        <h1 style={{ color: '#333' }}>Real-Time Transcription</h1>
        <div style={{ 
          padding: '20px',
          background: 'white',
          borderRadius: '8px',
          border: '1px solid #ddd'
        }}>
          <p style={{ color: '#666', margin: 0 }}>Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div style={{ 
      padding: '20px', 
      fontFamily: 'Arial, sans-serif',
      minHeight: '100vh',
      background: '#fafafa'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h1 style={{ color: '#333', margin: 0 }}>Real-Time Transcription</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          {user && (
            <span style={{ color: '#666', fontSize: '14px' }}>
              Welcome, <strong>{user.username}</strong>
            </span>
          )}
          <button
            onClick={handleLogout}
            style={{
              padding: '8px 16px',
              background: '#6c757d',
              color: 'white',
              border: 'none',
              borderRadius: '5px',
              cursor: 'pointer',
              fontSize: '14px'
            }}
          >
            Logout
          </button>
        </div>
      </div>
      
      {/* Rest of the component remains the same - Connection Status, Recording Controls, etc. */}
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
                    const handleCompleteTranscript = (title: string, transcriptList: Transcript[]) => {
                      setMeetingTitle(title)
                      setTranscripts(transcriptList)
                    }
                    transcriptService.connect(
                      () => {},
                      undefined,
                      handleCompleteTranscript
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#333', marginBottom: '5px' }}>
                Meeting Name (will be saved as {roomName || 'meeting-name'}.json)
              </label>
            <input
              type="text"
              value={roomName}
              onChange={(e) => setRoomName(e.target.value)}
                placeholder="Enter meeting name (e.g., 'team-meeting-2024')"
              disabled={isRecording}
              style={{
                  width: '100%',
                padding: '10px',
                border: '1px solid #ddd',
                borderRadius: '5px',
                fontSize: '16px'
              }}
            />
            </div>
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
                gap: '8px',
                justifyContent: 'center'
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
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
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
              <div style={{ flex: 1 }}>
                <strong style={{ color: '#856404', display: 'block' }}>Recording in progress</strong>
                <span style={{ color: '#856404', fontSize: '14px' }}>Meeting: <strong>{roomName}</strong> (will be saved as {roomName}.json)</span>
              </div>
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
        
        {!isRecording && (
          <div style={{ marginTop: '10px', padding: '10px', background: '#e7f3ff', borderRadius: '5px', fontSize: '14px', color: '#004085' }}>
            💡 <strong>Note:</strong> The meeting name you enter will be used to save the transcript as <code>{roomName || 'meeting-name'}.json</code> in the backend/transcripts/ directory.
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
      
      {/* Available Transcripts List */}
      {loadingTranscripts && (
        <div style={{ 
          marginTop: '20px',
          padding: '15px',
          background: 'white',
          borderRadius: '5px',
          border: '1px solid #ddd',
          textAlign: 'center'
        }}>
          <p style={{ color: '#666' }}>Loading transcripts...</p>
        </div>
      )}
      
      {availableTranscripts.length > 0 && (
        <div style={{ 
          marginTop: '20px',
          padding: '15px',
          background: 'white',
          borderRadius: '5px',
          border: '1px solid #ddd',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
        }}>
          <h3 style={{ marginTop: 0, marginBottom: '15px', fontSize: '18px', fontWeight: '600' }}>
            📚 Available Transcripts ({availableTranscripts.length})
          </h3>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', 
            gap: '10px' 
          }}>
            {availableTranscripts.map((transcript) => (
              <button
                key={transcript.file_name}
                onClick={() => loadTranscript(transcript.file_name)}
                disabled={loadingTranscripts}
                style={{
                  padding: '12px',
                  background: selectedMeeting === transcript.file_name ? '#007bff' : '#f8f9fa',
                  color: selectedMeeting === transcript.file_name ? 'white' : '#333',
                  border: `2px solid ${selectedMeeting === transcript.file_name ? '#007bff' : '#ddd'}`,
                  borderRadius: '8px',
                  cursor: loadingTranscripts ? 'not-allowed' : 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s ease',
                  opacity: loadingTranscripts ? 0.6 : 1
                }}
                onMouseEnter={(e) => {
                  if (!loadingTranscripts && selectedMeeting !== transcript.file_name) {
                    e.currentTarget.style.background = '#e9ecef'
                    e.currentTarget.style.borderColor = '#007bff'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!loadingTranscripts && selectedMeeting !== transcript.file_name) {
                    e.currentTarget.style.background = '#f8f9fa'
                    e.currentTarget.style.borderColor = '#ddd'
                  }
                }}
              >
                <div style={{ fontWeight: '600', marginBottom: '4px' }}>
                  {transcript.meeting_name}
                </div>
                <div style={{ fontSize: '12px', opacity: 0.8 }}>
                  {transcript.total_entries} {transcript.total_entries === 1 ? 'entry' : 'entries'}
                </div>
                <div style={{ fontSize: '11px', opacity: 0.6, marginTop: '4px' }}>
                  {new Date(transcript.last_modified * 1000).toLocaleDateString()}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Transcripts Display */}
      <div style={{ 
        marginTop: '20px',
        padding: '15px',
        background: 'white',
        borderRadius: '5px',
        border: '1px solid #ddd',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
        display: 'flex',
        flexDirection: 'column',
        height: '70vh',
        minHeight: '500px'
      }}>
        {meetingTitle ? (
          <>
            <h2 style={{ 
              marginTop: 0, 
              marginBottom: '10px',
              fontSize: '24px',
              fontWeight: '600',
              color: '#333',
              borderBottom: '2px solid #007bff',
              paddingBottom: '10px',
              flexShrink: 0
            }}>
              {meetingTitle}
            </h2>
            <h3 style={{ marginTop: 0, marginBottom: '15px', color: '#666', fontSize: '16px', flexShrink: 0 }}>
              Meeting Transcript ({transcripts.length} {transcripts.length === 1 ? 'entry' : 'entries'})
            </h3>
          </>
        ) : (
          <h3 style={{ marginTop: 0, flexShrink: 0 }}>Meeting Transcript</h3>
        )}
        
        {transcripts.length === 0 ? (
          <div style={{ 
            flex: 1, 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center' 
          }}>
            <p style={{ color: '#666', fontStyle: 'italic', textAlign: 'center' }}>
            {isRecording 
                ? 'Recording in progress... Transcript will appear here when you stop recording.' 
                : 'No transcript yet. Start recording and then stop to see the transcript.'}
            </p>
          </div>
        ) : (
          <div style={{ 
            flex: 1,
            overflowY: 'auto',
            overflowX: 'hidden',
            padding: '10px',
            background: '#fafafa',
            borderRadius: '8px',
            border: '1px solid #e0e0e0'
          }}>
            {transcripts.map((t, i) => {
              const prevSpeaker = i > 0 ? transcripts[i - 1].speaker : null;
              const isSameSpeaker = prevSpeaker === t.speaker;
              
              return (
                <div 
                  key={i} 
                  style={{ 
                    marginBottom: isSameSpeaker ? '8px' : '16px',
                    padding: isSameSpeaker ? '8px 12px' : '12px 16px',
                    background: isSameSpeaker ? '#ffffff' : '#ffffff',
                    borderRadius: '8px',
                    borderLeft: `4px solid ${isSameSpeaker ? '#90caf9' : '#007bff'}`,
                    boxShadow: isSameSpeaker ? 'none' : '0 1px 3px rgba(0,0,0,0.1)',
                    transition: 'all 0.2s ease'
                  }}
                >
                  {!isSameSpeaker && (
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '8px', 
                      marginBottom: '6px' 
                    }}>
                      <div style={{
                        width: '32px',
                        height: '32px',
                        borderRadius: '50%',
                        background: '#007bff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: 'white',
                        fontSize: '14px',
                        fontWeight: '600',
                        flexShrink: 0
                      }}>
                        {(t.speaker || 'U').charAt(0).toUpperCase()}
                      </div>
                      <strong style={{ color: '#007bff', fontSize: '15px' }}>
                        {t.speaker || 'Unknown Speaker'}
                      </strong>
                    </div>
                  )}
                  <p style={{ 
                    margin: 0, 
                    color: '#333', 
                    lineHeight: '1.7',
                    fontSize: '15px',
                    whiteSpace: 'pre-wrap',
                    wordWrap: 'break-word'
                  }}>
                  {t.text}
                </p>
              </div>
              );
            })}
            <div ref={transcriptEndRef} style={{ height: '1px' }} />
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

