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
  isCurrent?: boolean
}

export function Dashboard() {
  const [transcripts, setTranscripts] = useState<Transcript[]>([])
  const [realtimeUpdates, setRealtimeUpdates] = useState<Transcript[]>([])
  const [displayText, setDisplayText] = useState<string>('')
  const [meetingTitle, setMeetingTitle] = useState<string | null>(null)
  const [wsConnected, setWsConnected] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [roomName, setRoomName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const transcriptEndRef = useRef<HTMLDivElement>(null)
  const realtimeUpdatesEndRef = useRef<HTMLDivElement>(null)
  const [availableTranscripts, setAvailableTranscripts] = useState<TranscriptFile[]>([])
  const [selectedMeeting, setSelectedMeeting] = useState<string | null>(null)
  const [loadingTranscripts, setLoadingTranscripts] = useState(false)
  const [initialLoadComplete, setInitialLoadComplete] = useState(false)
  const [user, setUser] = useState<User | null>(null)
  const navigate = useNavigate()
  const roomNameRef = useRef<string>(roomName)
  const isRecordingRef = useRef<boolean>(isRecording)
  const selectedMeetingRef = useRef<string | null>(selectedMeeting)
  
  // Keep refs in sync with state
  useEffect(() => {
    roomNameRef.current = roomName
  }, [roomName])
  
  useEffect(() => {
    isRecordingRef.current = isRecording
  }, [isRecording])
  
  useEffect(() => {
    selectedMeetingRef.current = selectedMeeting
  }, [selectedMeeting])
  
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

      const handleRealtimeTranscript = (transcript: Transcript, _meetingName?: string) => {
        const currentlyRecording = isRecordingRef.current
        const currentSelectedMeeting = selectedMeetingRef.current
        
        // Always add to real-time updates section
        setRealtimeUpdates((prev) => {
          const lastIndex = prev.length - 1;
          const lastUpdate = prev[lastIndex];

          // Update last entry if same speaker and interim, or append new
          if (lastUpdate && 
              lastUpdate.speaker === transcript.speaker && 
              !lastUpdate.is_final && 
              !transcript.is_final) {
            const updated = [...prev];
            updated[lastIndex] = transcript;
            return updated;
          } 
          else if (lastUpdate && 
                   lastUpdate.speaker === transcript.speaker && 
                   !lastUpdate.is_final && 
                   transcript.is_final) {
            const updated = [...prev];
            updated[lastIndex] = transcript;
            return updated;
          }
          else {
            return [...prev, transcript];
          }
        });

        // During recording OR when watching a specific meeting, ALWAYS update transcripts
        const shouldUpdate = currentlyRecording || currentSelectedMeeting;
        
        if (shouldUpdate) {
          setTranscripts((prevTranscripts) => {
            const lastIndex = prevTranscripts.length - 1;
            const lastTranscript = prevTranscripts[lastIndex];

            let updatedTranscripts;

            if (lastTranscript && 
                lastTranscript.speaker === transcript.speaker && 
                !lastTranscript.is_final && 
                !transcript.is_final) {
              updatedTranscripts = [...prevTranscripts];
              updatedTranscripts[lastIndex] = transcript;
            } 
            else if (lastTranscript && 
                     lastTranscript.speaker === transcript.speaker && 
                     !lastTranscript.is_final && 
                     transcript.is_final) {
              updatedTranscripts = [...prevTranscripts];
              updatedTranscripts[lastIndex] = transcript;
            }
            else if (lastTranscript && 
                     lastTranscript.speaker === transcript.speaker && 
                     lastTranscript.is_final && 
                     transcript.is_final &&
                     lastTranscript.text && 
                     transcript.text.includes(lastTranscript.text)) {
              updatedTranscripts = [...prevTranscripts];
              updatedTranscripts[lastIndex] = transcript;
            }
            else {
              updatedTranscripts = [...prevTranscripts, transcript];
            }

            return updatedTranscripts;
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
      setTimeout(() => {
        try {
          if (transcriptService) {
            transcriptService.disconnect()
          }
        } catch (err) {
          console.error('Error disconnecting:', err)
        }
      }, 200)
    }
  }, [transcriptService])

  useEffect(() => {
    if (displayText) {
      setTimeout(() => {
        transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    }
  }, [displayText])

  useEffect(() => {
    if (realtimeUpdates.length > 0) {
      setTimeout(() => {
        realtimeUpdatesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }, 100)
    }
  }, [realtimeUpdates])

  // Update displayText when transcripts change (for BOTH recording and watching)
  useEffect(() => {
    // Update displayText whenever transcripts change (during recording OR watching)
    if ((isRecording || selectedMeeting) && transcripts.length > 0) {
      // Build text from transcripts for display
      let newText = '';
      let lastFinalIdx = -1;
      
      // Find the last final transcript index
      for (let i = transcripts.length - 1; i >= 0; i--) {
        if (transcripts[i]?.is_final) {
          lastFinalIdx = i;
          break;
        }
      }
      
      // Add all final transcripts (each on a new line)
      for (let i = 0; i <= lastFinalIdx; i++) {
        if (transcripts[i]?.is_final && transcripts[i].text) {
          newText += transcripts[i].text.trim() + '\n';
        }
      }
      
      // Add current interim transcript if it exists (appends to current line)
      if (lastFinalIdx < transcripts.length - 1) {
        const currentInterim = transcripts[transcripts.length - 1];
        if (!currentInterim.is_final && currentInterim.text) {
          newText += currentInterim.text.trim();
        }
      }
      
      setDisplayText(newText);
    } else if ((isRecording || selectedMeeting) && transcripts.length === 0) {
      // Clear displayText when starting a new recording or watching empty transcript
      setDisplayText('');
    }
  }, [transcripts, selectedMeeting, isRecording])

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
      setMeetingTitle(roomName)
      setSelectedMeeting(roomName)
      setTranscripts([])
      transcriptService.watchTranscript(roomName)
    } else if (!isRecording && roomName && transcriptService) {
      transcriptService.watchTranscript(roomName)
    }
  }, [isRecording, roomName, transcriptService])

  useEffect(() => {
    const loadAvailableTranscripts = async () => {
      let controller: AbortController | null = null
      let timeoutId: ReturnType<typeof setTimeout> | null = null
      
      try {
        controller = new AbortController()
        timeoutId = setTimeout(() => {
          if (controller) {
            controller.abort()
          }
        }, 10000)
        
        const response = await fetch(`${HTTP_API_URL}/transcripts/list`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            ...authService.getAuthHeaders(),
          },
          signal: controller.signal,
        })
        
        if (timeoutId) {
          clearTimeout(timeoutId)
          timeoutId = null
        }
        
        if (response.ok) {
          const data = await response.json()
          setAvailableTranscripts(data.transcripts || [])
          if (data.transcripts && data.transcripts.length > 0) {
            const mostRecent = data.transcripts[0].file_name
            setLoadingTranscripts(true)
            
            let transcriptController: AbortController | null = null
            let transcriptTimeoutId: ReturnType<typeof setTimeout> | null = null
            
            try {
              transcriptController = new AbortController()
              transcriptTimeoutId = setTimeout(() => {
                if (transcriptController) {
                  transcriptController.abort()
                }
              }, 10000)
              
              const transcriptResponse = await fetch(`${HTTP_API_URL}/transcripts?meeting_name=${encodeURIComponent(mostRecent)}`, {
                headers: {
                  'Content-Type': 'application/json',
                  ...authService.getAuthHeaders(),
                },
                signal: transcriptController.signal,
              })
              
              if (transcriptTimeoutId) {
                clearTimeout(transcriptTimeoutId)
                transcriptTimeoutId = null
              }
              
              if (transcriptResponse.ok) {
                const transcriptData = await transcriptResponse.json()
                setMeetingTitle(transcriptData.meeting_name || mostRecent)
                setTranscripts(transcriptData.transcripts || [])
                setSelectedMeeting(mostRecent)
              } else {
                console.error('Failed to load transcript:', transcriptResponse.status, await transcriptResponse.text())
              }
            } catch (err) {
              if (transcriptTimeoutId) {
                clearTimeout(transcriptTimeoutId)
              }
              
              if (!(err instanceof Error && err.name === 'AbortError')) {
                setError(`Failed to load transcript: ${err instanceof Error ? err.message : 'Unknown error'}`)
              }
            } finally {
              setLoadingTranscripts(false)
            }
          } else {
            setLoadingTranscripts(false)
          }
        } else if (response.status === 404) {
          setError('API endpoint not found. Please restart the backend server to load the latest code.')
          setLoadingTranscripts(false)
        } else {
          const errorText = await response.text()
          console.error('Failed to load transcripts list:', response.status, errorText)
          setError(`Failed to load transcripts list: ${response.status} ${errorText}`)
          setLoadingTranscripts(false)
        }
      } catch (err) {
        if (timeoutId) {
          clearTimeout(timeoutId)
        }
        
        if (!(err instanceof Error && err.name === 'AbortError')) {
          setError(`Cannot connect to API server at ${HTTP_API_URL}. Make sure the backend server is running.`)
        }
        setLoadingTranscripts(false)
      } finally {
        setInitialLoadComplete(true)
      }
    }
    
    loadAvailableTranscripts()
    
    const safetyTimeout = setTimeout(() => {
      setInitialLoadComplete(true)
      setLoadingTranscripts(false)
    }, 3000)
    
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
      setRealtimeUpdates([])
      setDisplayText('')
      setMeetingTitle(null)

      // Add current meeting to available transcripts list immediately
      const currentTimestamp = Math.floor(Date.now() / 1000)
      const newMeeting: TranscriptFile = {
        meeting_name: roomName,
        file_name: `${roomName}.json`,
        total_entries: 0,
        last_modified: currentTimestamp,
        isCurrent: true
      }
      
      // Check if meeting already exists in the list
      setAvailableTranscripts(prev => {
        const existingIndex = prev.findIndex(t => t.meeting_name === roomName)
        if (existingIndex >= 0) {
          // Update existing entry to mark as current
          const updated = [...prev]
          updated[existingIndex] = { ...updated[existingIndex], isCurrent: true, last_modified: currentTimestamp }
          return updated
        } else {
          // Add new entry at the beginning
          return [newMeeting, ...prev]
        }
      })
      
      // Set selected meeting to current room so transcripts update correctly
      setSelectedMeeting(roomName)
      setMeetingTitle(roomName)

      const tokenData = await getLiveKitToken(roomName)
      await liveKitService.connect(tokenData.url, tokenData.token, tokenData.room_name)
    } catch (err) {
      console.error('❌ Failed to start recording:', err)
      setError(err instanceof Error ? err.message : 'Failed to start recording')
      setIsRecording(false)
      
      // Remove isCurrent flag if recording failed
      setAvailableTranscripts(prev => 
        prev.map(t => t.meeting_name === roomName ? { ...t, isCurrent: false } : t)
      )
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
      
      // Wait a moment for the backend to finish processing and save the transcript
      await new Promise(resolve => setTimeout(resolve, 1000))
      
      // Update meeting entry in available transcripts: remove isCurrent flag and update counts
      if (roomName) {
        const finalCount = transcripts.length
        const currentTimestamp = Math.floor(Date.now() / 1000)
        
        setAvailableTranscripts(prev => 
          prev.map(t => 
            t.meeting_name === roomName 
              ? { 
                  ...t, 
                  isCurrent: false, 
                  total_entries: finalCount,
                  last_modified: currentTimestamp
                } 
              : t
          )
        )
        
        // Call stop recording endpoint to store in vector DB and delete JSON file
        try {
          const response = await fetch(`${HTTP_API_URL}/transcripts/stop-recording`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...authService.getAuthHeaders(),
            },
            body: JSON.stringify({ meeting_name: roomName })
          })
          
          if (response.ok) {
            const data = await response.json()
            console.log('Stop recording response:', data)
            if (data.stored_to_vector_db) {
              console.log('✅ Transcript stored in vector database')
            }
          } else {
            const errorData = await response.json().catch(() => ({ message: 'Unknown error' }))
            console.warn('Stop recording endpoint returned error:', errorData)
          }
        } catch (err) {
          console.error('Failed to call stop recording endpoint:', err)
          // Continue with fallback logic
        }
      }
      
      if (transcriptService && roomName) {
        setMeetingTitle(roomName)
        setSelectedMeeting(roomName)
        
        if (!wsConnected) {
          setTimeout(() => {
            if (transcriptService && roomName) {
              transcriptService.requestTranscript(roomName);
            }
          }, 1000);
        } else {
          transcriptService.requestTranscript(roomName);
        }
        
        setTimeout(async () => {
          try {
            const response = await fetch(`${HTTP_API_URL}/transcripts?meeting_name=${encodeURIComponent(roomName)}`, {
              headers: {
                'Content-Type': 'application/json',
                ...authService.getAuthHeaders(),
              },
            })
            if (response.ok) {
              const data = await response.json()
              if (data.transcripts && data.transcripts.length > 0) {
                setMeetingTitle(data.meeting_name || roomName)
                setTranscripts(data.transcripts || [])
                setSelectedMeeting(roomName)
              }
            }
          } catch (err) {
            // HTTP fallback failed, WebSocket should handle it
          }
        }, 2000)
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
                disabled={loadingTranscripts || transcript.isCurrent}
                style={{
                  padding: '12px',
                  background: selectedMeeting === transcript.file_name ? '#007bff' : transcript.isCurrent ? '#fff5f5' : '#f8f9fa',
                  color: selectedMeeting === transcript.file_name ? 'white' : transcript.isCurrent ? '#dc3545' : '#333',
                  border: `2px solid ${selectedMeeting === transcript.file_name ? '#007bff' : transcript.isCurrent ? '#dc3545' : '#ddd'}`,
                  borderRadius: '8px',
                  cursor: loadingTranscripts || transcript.isCurrent ? 'not-allowed' : 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s ease',
                  opacity: loadingTranscripts ? 0.6 : 1,
                  position: 'relative'
                }}
                onMouseEnter={(e) => {
                  if (!loadingTranscripts && selectedMeeting !== transcript.file_name && !transcript.isCurrent) {
                    e.currentTarget.style.background = '#e9ecef'
                    e.currentTarget.style.borderColor = '#007bff'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!loadingTranscripts && selectedMeeting !== transcript.file_name) {
                    e.currentTarget.style.background = transcript.isCurrent ? '#fff5f5' : '#f8f9fa'
                    e.currentTarget.style.borderColor = transcript.isCurrent ? '#dc3545' : '#ddd'
                  }
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                  <div style={{ fontWeight: '600' }}>
                    {transcript.meeting_name}
                  </div>
                  {transcript.isCurrent && (
                    <span style={{
                      fontSize: '10px',
                      backgroundColor: '#dc3545',
                      color: 'white',
                      padding: '2px 6px',
                      borderRadius: '3px',
                      fontWeight: '600',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}>
                      <span style={{
                        width: '6px',
                        height: '6px',
                        borderRadius: '50%',
                        backgroundColor: 'white',
                        animation: 'pulse 1.5s infinite'
                      }} />
                      Recording
                    </span>
                  )}
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

      {/* Current Meeting Section */}
      {((isRecording && roomName) || (selectedMeeting && !isRecording)) && (
        <div style={{ 
          marginTop: '20px',
          padding: '20px',
          background: 'white',
          borderRadius: '5px',
          border: isRecording ? '2px solid #dc3545' : '2px solid #007bff',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
        }}>
          <h3 style={{ 
            marginTop: 0, 
            marginBottom: '15px',
            fontSize: '20px',
            fontWeight: '600',
            color: isRecording ? '#dc3545' : '#007bff',
            display: 'flex',
            alignItems: 'center',
            gap: '10px'
          }}>
            <span style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              background: isRecording ? '#dc3545' : '#007bff',
              animation: 'pulse 1.5s infinite'
            }} />
            {isRecording ? `Current Meeting: ${roomName}` : `Watching: ${selectedMeeting}`}
          </h3>
          <div style={{ 
            maxHeight: '400px',
            overflowY: 'auto',
            overflowX: 'hidden',
            padding: '15px',
            background: '#ffffff',
            borderRadius: '8px',
            border: '1px solid #e0e0e0',
            fontFamily: 'system-ui, -apple-system, sans-serif',
            fontSize: '16px',
            lineHeight: '1.6',
            color: '#333'
          }}>
            {displayText ? (
              <pre style={{
                margin: 0,
                padding: 0,
                whiteSpace: 'pre-wrap',
                wordWrap: 'break-word',
                fontFamily: 'inherit',
                fontSize: 'inherit',
                lineHeight: 'inherit',
                color: 'inherit',
                background: 'transparent',
                border: 'none'
              }}>
                {displayText}
              </pre>
            ) : (
              <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                padding: '40px',
                color: '#999',
                fontStyle: 'italic'
              }}>
                <p style={{ margin: 0, textAlign: 'center' }}>
                  {isRecording 
                    ? '🎙️ Recording in progress... Transcripts will appear here in real-time as you speak.'
                    : '👁️ Watching meeting... Real-time transcripts will appear here.'}
                </p>
              </div>
            )}
            <div ref={transcriptEndRef} style={{ height: '1px' }} />
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
                ? '🎙️ Recording in progress... Transcripts will appear here in real-time as you speak.' 
                : 'No transcript yet. Start recording to see transcripts appear in real-time.'}
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

        {/* Real-time Updates Section */}
        {isRecording && realtimeUpdates.length > 0 && (
          <div style={{
            marginTop: '30px',
            padding: '20px',
            backgroundColor: '#f8f9fa',
            borderRadius: '8px',
            border: '1px solid #e0e0e0'
          }}>
            <h3 style={{
              margin: '0 0 15px 0',
              color: '#007bff',
              fontSize: '18px',
              fontWeight: '600',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}>
              <span style={{
                display: 'inline-block',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: '#28a745',
                animation: 'pulse 2s infinite'
              }} />
              Real-time Updates
            </h3>
            <div style={{
              maxHeight: '300px',
              overflowY: 'auto',
              padding: '10px',
              backgroundColor: '#fff',
              borderRadius: '4px',
              border: '1px solid #ddd'
            }}>
              {realtimeUpdates.map((t, idx) => (
                <div
                  key={idx}
                  style={{
                    marginBottom: '12px',
                    padding: '10px',
                    backgroundColor: t.is_final ? '#f0f8ff' : '#fff9e6',
                    borderRadius: '4px',
                    borderLeft: `3px solid ${t.is_final ? '#007bff' : '#ffc107'}`,
                    opacity: t.is_final ? 1 : 0.8
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '5px' }}>
                    {t.speaker && (
                      <div style={{
                        width: '32px',
                        height: '32px',
                        borderRadius: '50%',
                        backgroundColor: '#007bff',
                        color: '#fff',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '12px',
                        fontWeight: 'bold'
                      }}>
                        {(t.speaker || 'U').charAt(0).toUpperCase()}
                      </div>
                    )}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <strong style={{ color: '#007bff', fontSize: '14px' }}>
                        {t.speaker || 'Unknown Speaker'}
                      </strong>
                      {!t.is_final && (
                        <span style={{
                          fontSize: '11px',
                          color: '#ffc107',
                          backgroundColor: '#fff9e6',
                          padding: '2px 6px',
                          borderRadius: '3px',
                          fontWeight: '500'
                        }}>
                          Interim
                        </span>
                      )}
                      {t.is_final && (
                        <span style={{
                          fontSize: '11px',
                          color: '#28a745',
                          backgroundColor: '#f0f8ff',
                          padding: '2px 6px',
                          borderRadius: '3px',
                          fontWeight: '500'
                        }}>
                          Final
                        </span>
                      )}
                    </div>
                  </div>
                  <p style={{
                    margin: 0,
                    color: '#333',
                    lineHeight: '1.6',
                    fontSize: '14px',
                    whiteSpace: 'pre-wrap',
                    wordWrap: 'break-word'
                  }}>
                    {t.text}
                  </p>
                </div>
              ))}
              <div ref={realtimeUpdatesEndRef} style={{ height: '1px' }} />
            </div>
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

