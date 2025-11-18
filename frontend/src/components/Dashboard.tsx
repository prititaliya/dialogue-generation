import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Transcript } from '../types'
import { TranscriptService } from '../services/transcriptService'
import { LiveKitService } from '../services/livekit'
import { getLiveKitToken } from '../services/tokenService'
import { authService } from '../services/authService'
import type { User } from '../services/authService'
import { chatbotService, type ChatMessage } from '../services/chatbotService'

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
  
  // CRUD operation states
  const [deleteConfirm, setDeleteConfirm] = useState<{show: boolean, meetingName: string | null}>({show: false, meetingName: null})
  const [editModal, setEditModal] = useState<{show: boolean, meetingName: string | null, transcripts: Transcript[]}>({show: false, meetingName: null, transcripts: []})
  const [toasts, setToasts] = useState<Array<{id: number, message: string, type: 'success' | 'error' | 'info'}>>([])
  const [searchQuery, setSearchQuery] = useState<string>('')
  
  // Chatbot and Summary states
  const [summary, setSummary] = useState<string>('')
  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [currentQuestion, setCurrentQuestion] = useState<string>('')
  const [isStreaming, setIsStreaming] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<HTMLInputElement>(null)
  const chatMessagesContainerRef = useRef<HTMLDivElement>(null)
  
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

  // Scroll chat container to bottom when messages change (without affecting page scroll)
  useEffect(() => {
    if (chatMessages.length > 0 && chatMessagesContainerRef.current) {
      setTimeout(() => {
        const container = chatMessagesContainerRef.current
        if (container) {
          container.scrollTop = container.scrollHeight
        }
      }, 50)
    }
  }, [chatMessages])

  // Clear summary and chat when switching meetings
  useEffect(() => {
    setSummary('')
    setChatMessages([])
    setCurrentQuestion('')
  }, [selectedMeeting])

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

  // Toast notification helper
  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 3000)
  }

  // Delete transcript handler
  const handleDeleteTranscript = async (meetingName: string) => {
    try {
      const response = await fetch(`${HTTP_API_URL}/transcripts/${encodeURIComponent(meetingName)}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          ...authService.getAuthHeaders(),
        },
      })

      if (response.ok) {
        showToast(`Transcript "${meetingName}" deleted successfully`, 'success')
        setAvailableTranscripts(prev => prev.filter(t => t.meeting_name !== meetingName))
        if (selectedMeeting === meetingName) {
          setSelectedMeeting(null)
          setTranscripts([])
          setMeetingTitle(null)
        }
        setDeleteConfirm({ show: false, meetingName: null })
        refreshTranscriptsList()
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to delete transcript' }))
        showToast(errorData.detail || 'Failed to delete transcript', 'error')
      }
    } catch (err) {
      console.error('Error deleting transcript:', err)
      showToast('Failed to delete transcript', 'error')
    }
  }

  // Open edit modal
  const handleEditTranscript = async (meetingName: string) => {
    try {
      const response = await fetch(`${HTTP_API_URL}/transcripts?meeting_name=${encodeURIComponent(meetingName)}`, {
        headers: {
          'Content-Type': 'application/json',
          ...authService.getAuthHeaders(),
        },
      })
      
      if (response.ok) {
        const data = await response.json()
        setEditModal({
          show: true,
          meetingName: meetingName,
          transcripts: data.transcripts || []
        })
      } else {
        showToast('Failed to load transcript for editing', 'error')
      }
    } catch (err) {
      console.error('Error loading transcript for edit:', err)
      showToast('Failed to load transcript', 'error')
    }
  }

  // Save edited transcript
  const handleSaveEdit = async () => {
    if (!editModal.meetingName) return

    try {
      const response = await fetch(`${HTTP_API_URL}/transcripts/${encodeURIComponent(editModal.meetingName)}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...authService.getAuthHeaders(),
        },
        body: JSON.stringify({
          transcripts: editModal.transcripts.map(t => ({
            speaker: t.speaker,
            text: t.text
          }))
        })
      })

      if (response.ok) {
        const data = await response.json()
        showToast(`Transcript "${editModal.meetingName}" updated successfully`, 'success')
        setEditModal({ show: false, meetingName: null, transcripts: [] })
        
        // Update local state if this is the currently selected meeting
        if (selectedMeeting === editModal.meetingName) {
          setTranscripts(data.transcripts || [])
        }
        
        refreshTranscriptsList()
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to update transcript' }))
        showToast(errorData.detail || 'Failed to update transcript', 'error')
      }
    } catch (err) {
      console.error('Error updating transcript:', err)
      showToast('Failed to update transcript', 'error')
    }
  }

  // Filter transcripts based on search query
  const filteredTranscripts = availableTranscripts.filter(t => 
    t.meeting_name.toLowerCase().includes(searchQuery.toLowerCase())
  )

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
      fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%)',
      backgroundAttachment: 'fixed'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h1 style={{ 
          margin: 0,
          fontSize: '32px',
          fontWeight: '800',
          background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text'
        }}>
          Real-Time Transcription
        </h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          {user && (
            <span style={{ color: 'rgba(241, 245, 249, 0.8)', fontSize: '14px' }}>
              Welcome, <strong style={{ color: '#f1f5f9' }}>{user.username}</strong>
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
          padding: '24px',
          background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(139, 92, 246, 0.1) 50%, rgba(236, 72, 153, 0.1) 100%)',
          backdropFilter: 'blur(16px)',
          borderRadius: '16px',
          border: '1px solid rgba(255, 255, 255, 0.2)',
          boxShadow: '0 8px 32px rgba(0, 0, 0, 0.2)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h3 style={{ 
              margin: 0, 
              fontSize: '24px', 
              fontWeight: '700',
              background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text'
            }}>
              📚 Available Transcripts ({filteredTranscripts.length})
            </h3>
            <input
              type="text"
              placeholder="🔍 Search transcripts..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                padding: '10px 16px',
                background: 'rgba(255, 255, 255, 0.1)',
                backdropFilter: 'blur(10px)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '12px',
                color: '#f1f5f9',
                fontSize: '14px',
                width: '300px',
                outline: 'none',
                transition: 'all 0.3s ease'
              }}
              onFocus={(e) => {
                e.target.style.background = 'rgba(255, 255, 255, 0.15)'
                e.target.style.borderColor = 'rgba(99, 102, 241, 0.5)'
              }}
              onBlur={(e) => {
                e.target.style.background = 'rgba(255, 255, 255, 0.1)'
                e.target.style.borderColor = 'rgba(255, 255, 255, 0.2)'
              }}
            />
            <style>{`
              input::placeholder {
                color: rgba(241, 245, 249, 0.5) !important;
              }
            `}</style>
          </div>
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', 
            gap: '16px' 
          }}>
            {filteredTranscripts.map((transcript) => (
              <div
                key={transcript.file_name}
                style={{
                  padding: '20px',
                  background: selectedMeeting === transcript.file_name 
                    ? 'linear-gradient(135deg, rgba(99, 102, 241, 0.3) 0%, rgba(139, 92, 246, 0.3) 100%)'
                    : 'rgba(255, 255, 255, 0.1)',
                  backdropFilter: 'blur(16px)',
                  border: selectedMeeting === transcript.file_name
                    ? '2px solid rgba(99, 102, 241, 0.6)'
                    : '1px solid rgba(255, 255, 255, 0.2)',
                  borderRadius: '16px',
                  boxShadow: selectedMeeting === transcript.file_name
                    ? '0 8px 32px rgba(99, 102, 241, 0.3)'
                    : '0 4px 16px rgba(0, 0, 0, 0.1)',
                  transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                  cursor: transcript.isCurrent ? 'not-allowed' : 'pointer',
                  opacity: transcript.isCurrent ? 0.7 : 1,
                  position: 'relative',
                  overflow: 'hidden'
                }}
                onMouseEnter={(e) => {
                  if (!transcript.isCurrent) {
                    e.currentTarget.style.transform = 'translateY(-4px) scale(1.02)'
                    e.currentTarget.style.boxShadow = '0 12px 40px rgba(99, 102, 241, 0.4)'
                    e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.5)'
                  }
                }}
                onMouseLeave={(e) => {
                  if (!transcript.isCurrent) {
                    e.currentTarget.style.transform = 'translateY(0) scale(1)'
                    e.currentTarget.style.boxShadow = selectedMeeting === transcript.file_name
                      ? '0 8px 32px rgba(99, 102, 241, 0.3)'
                      : '0 4px 16px rgba(0, 0, 0, 0.1)'
                    e.currentTarget.style.borderColor = selectedMeeting === transcript.file_name
                      ? 'rgba(99, 102, 241, 0.6)'
                      : 'rgba(255, 255, 255, 0.2)'
                  }
                }}
                onClick={() => {
                  if (!transcript.isCurrent && !loadingTranscripts) {
                    loadTranscript(transcript.file_name)
                  }
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                      <div style={{ 
                        fontWeight: '700', 
                        fontSize: '16px',
                        color: '#f1f5f9'
                      }}>
                        {transcript.meeting_name}
                      </div>
                      {transcript.isCurrent && (
                        <span style={{
                          fontSize: '10px',
                          background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                          color: 'white',
                          padding: '4px 8px',
                          borderRadius: '6px',
                          fontWeight: '600',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          boxShadow: '0 2px 8px rgba(239, 68, 68, 0.4)'
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
                    <div style={{ fontSize: '13px', color: 'rgba(241, 245, 249, 0.8)', marginBottom: '4px' }}>
                      {transcript.total_entries} {transcript.total_entries === 1 ? 'entry' : 'entries'}
                    </div>
                    <div style={{ fontSize: '12px', color: 'rgba(241, 245, 249, 0.6)' }}>
                      {new Date(transcript.last_modified * 1000).toLocaleDateString()}
                    </div>
                  </div>
                </div>
                
                {/* Action Buttons */}
                {!transcript.isCurrent && (
                  <div style={{ 
                    display: 'flex', 
                    gap: '8px', 
                    marginTop: '16px',
                    paddingTop: '16px',
                    borderTop: '1px solid rgba(255, 255, 255, 0.1)'
                  }}
                  onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={() => handleEditTranscript(transcript.meeting_name)}
                      style={{
                        flex: 1,
                        padding: '8px 12px',
                        background: 'rgba(99, 102, 241, 0.2)',
                        border: '1px solid rgba(99, 102, 241, 0.4)',
                        borderRadius: '8px',
                        color: '#a5b4fc',
                        cursor: 'pointer',
                        fontSize: '13px',
                        fontWeight: '600',
                        transition: 'all 0.2s ease',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'rgba(99, 102, 241, 0.3)'
                        e.currentTarget.style.transform = 'scale(1.05)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'rgba(99, 102, 241, 0.2)'
                        e.currentTarget.style.transform = 'scale(1)'
                      }}
                    >
                      ✏️ Edit
                    </button>
                    <button
                      onClick={() => setDeleteConfirm({ show: true, meetingName: transcript.meeting_name })}
                      style={{
                        flex: 1,
                        padding: '8px 12px',
                        background: 'rgba(239, 68, 68, 0.2)',
                        border: '1px solid rgba(239, 68, 68, 0.4)',
                        borderRadius: '8px',
                        color: '#fca5a5',
                        cursor: 'pointer',
                        fontSize: '13px',
                        fontWeight: '600',
                        transition: 'all 0.2s ease',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = 'rgba(239, 68, 68, 0.3)'
                        e.currentTarget.style.transform = 'scale(1.05)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)'
                        e.currentTarget.style.transform = 'scale(1)'
                      }}
                    >
                      🗑️ Delete
                    </button>
                  </div>
                )}
              </div>
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

      {/* Summary and Chatbot Section */}
      {selectedMeeting && !isRecording && (
        <div style={{ 
          marginTop: '20px',
          padding: '20px',
          background: 'white',
          borderRadius: '5px',
          border: '1px solid #ddd',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
        }}>
          {/* Summary Section */}
          <div style={{ marginBottom: '30px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
              <h3 style={{ 
                margin: 0,
                fontSize: '20px',
                fontWeight: '600',
                color: '#333'
              }}>
                📝 Transcript Summary
              </h3>
              <button
                onClick={async () => {
                  if (!selectedMeeting) return
                  setIsGeneratingSummary(true)
                  setError(null)
                  try {
                    const result = await chatbotService.generateSummary(selectedMeeting)
                    setSummary(result.summary)
                  } catch (err) {
                    console.error('Error generating summary:', err)
                    setError(err instanceof Error ? err.message : 'Failed to generate summary')
                  } finally {
                    setIsGeneratingSummary(false)
                  }
                }}
                disabled={isGeneratingSummary}
                style={{
                  padding: '10px 20px',
                  background: isGeneratingSummary ? '#ccc' : 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '14px',
                  fontWeight: '600',
                  cursor: isGeneratingSummary ? 'not-allowed' : 'pointer',
                  boxShadow: isGeneratingSummary ? 'none' : '0 4px 12px rgba(99, 102, 241, 0.4)',
                  transition: 'all 0.2s ease'
                }}
              >
                {isGeneratingSummary ? '⏳ Generating...' : '✨ Generate Summary'}
              </button>
            </div>
            {summary ? (
              <div style={{
                padding: '15px',
                background: '#f8f9fa',
                borderRadius: '8px',
                border: '1px solid #e0e0e0',
                color: '#333',
                lineHeight: '1.6',
                fontSize: '15px',
                whiteSpace: 'pre-wrap',
                wordWrap: 'break-word'
              }}>
                {summary}
              </div>
            ) : (
              <div style={{
                padding: '20px',
                background: '#f8f9fa',
                borderRadius: '8px',
                border: '1px solid #e0e0e0',
                textAlign: 'center',
                color: '#999',
                fontStyle: 'italic'
              }}>
                Click "Generate Summary" to create a summary of this transcript
              </div>
            )}
          </div>

          {/* Chatbot Section */}
          <div>
            <h3 style={{ 
              margin: '0 0 15px 0',
              fontSize: '20px',
              fontWeight: '600',
              color: '#333'
            }}>
              💬 Chat with Transcript
            </h3>
            
            {/* Chat Messages */}
            <div 
              ref={chatMessagesContainerRef}
              style={{
                minHeight: '300px',
                maxHeight: '400px',
                overflowY: 'auto',
                padding: '15px',
                background: '#f8f9fa',
                borderRadius: '8px',
                border: '1px solid #e0e0e0',
                marginBottom: '15px'
              }}
            >
              {chatMessages.length === 0 ? (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '100%',
                  color: '#999',
                  fontStyle: 'italic',
                  textAlign: 'center'
                }}>
                  Start a conversation by asking a question about the transcript
                </div>
              ) : (
                chatMessages.map((msg, idx) => (
                  <div
                    key={idx}
                    style={{
                      marginBottom: '15px',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start'
                    }}
                  >
                    <div style={{
                      padding: '12px 16px',
                      background: msg.role === 'user' 
                        ? 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)'
                        : '#ffffff',
                      color: msg.role === 'user' ? 'white' : '#333',
                      borderRadius: '12px',
                      maxWidth: '80%',
                      boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                      wordWrap: 'break-word',
                      whiteSpace: 'pre-wrap',
                      lineHeight: '1.6'
                    }}>
                      {msg.content}
                    </div>
                  </div>
                ))
              )}
              <div ref={chatEndRef} style={{ height: '1px' }} />
            </div>

            {/* Chat Input */}
            <form
              onSubmit={async (e) => {
                e.preventDefault()
                if (!currentQuestion.trim() || isStreaming || !selectedMeeting) return

                const question = currentQuestion.trim()
                setCurrentQuestion('')
                
                // Focus the input immediately and keep it focused
                requestAnimationFrame(() => {
                  chatInputRef.current?.focus()
                })
                
                // Add user message
                const userMessage: ChatMessage = { role: 'user', content: question }
                const updatedChatMessages = [...chatMessages, userMessage]
                setChatMessages(updatedChatMessages)
                
                // Add placeholder assistant message
                const assistantMessage: ChatMessage = { role: 'assistant', content: '' }
                setChatMessages(prev => [...prev, assistantMessage])
                
                setIsStreaming(true)
                setError(null)

                try {
                  await chatbotService.streamChatResponse(
                    selectedMeeting,
                    question,
                    updatedChatMessages,
                    (chunk: string) => {
                      // Update the last message (assistant message) with streaming chunks
                      // Create a new object instead of mutating
                      setChatMessages(prev => {
                        const updated = [...prev]
                        const lastMsg = updated[updated.length - 1]
                        if (lastMsg && lastMsg.role === 'assistant') {
                          // Create a new message object instead of mutating
                          updated[updated.length - 1] = {
                            ...lastMsg,
                            content: lastMsg.content + chunk
                          }
                        }
                        return updated
                      })
                      // Scroll chat container to bottom (without affecting page scroll)
                      requestAnimationFrame(() => {
                        const container = chatMessagesContainerRef.current
                        if (container) {
                          container.scrollTop = container.scrollHeight
                        }
                      })
                    },
                    () => {
                      setIsStreaming(false)
                      // Focus input after streaming completes and scroll chat container
                      requestAnimationFrame(() => {
                        chatInputRef.current?.focus()
                        const container = chatMessagesContainerRef.current
                        if (container) {
                          container.scrollTop = container.scrollHeight
                        }
                      })
                    },
                    (err: Error) => {
                      console.error('Error streaming chat:', err)
                      setError(err.message)
                      setIsStreaming(false)
                      // Remove the placeholder assistant message on error
                      setChatMessages(prev => prev.slice(0, -1))
                      // Focus input after error
                      requestAnimationFrame(() => {
                        chatInputRef.current?.focus()
                      })
                    }
                  )
                } catch (err) {
                  console.error('Error starting chat:', err)
                  setError(err instanceof Error ? err.message : 'Failed to send message')
                  setIsStreaming(false)
                  setChatMessages(prev => prev.slice(0, -1))
                }
              }}
              style={{ display: 'flex', gap: '10px' }}
            >
              <input
                ref={chatInputRef}
                type="text"
                value={currentQuestion}
                onChange={(e) => setCurrentQuestion(e.target.value)}
                placeholder="Ask a question about the transcript..."
                disabled={isStreaming}
                style={{
                  flex: 1,
                  padding: '12px 16px',
                  border: '1px solid #ddd',
                  borderRadius: '8px',
                  fontSize: '14px',
                  outline: 'none',
                  transition: 'border-color 0.2s ease'
                }}
                onFocus={(e) => {
                  e.target.style.borderColor = '#6366f1'
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = '#ddd'
                }}
              />
              <button
                type="submit"
                disabled={!currentQuestion.trim() || isStreaming}
                style={{
                  padding: '12px 24px',
                  background: (!currentQuestion.trim() || isStreaming)
                    ? '#ccc'
                    : 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '8px',
                  fontSize: '14px',
                  fontWeight: '600',
                  cursor: (!currentQuestion.trim() || isStreaming) ? 'not-allowed' : 'pointer',
                  boxShadow: (!currentQuestion.trim() || isStreaming)
                    ? 'none'
                    : '0 4px 12px rgba(99, 102, 241, 0.4)',
                  transition: 'all 0.2s ease'
                }}
              >
                {isStreaming ? '⏳' : '📤 Send'}
              </button>
            </form>
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

      {/* Delete Confirmation Modal */}
      {deleteConfirm.show && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.7)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            animation: 'fadeIn 0.2s ease'
          }}
          onClick={() => setDeleteConfirm({ show: false, meetingName: null })}
        >
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.95) 100%)',
              backdropFilter: 'blur(20px)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '20px',
              padding: '32px',
              maxWidth: '500px',
              width: '90%',
              boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
              animation: 'slideUp 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: '0 0 16px 0', fontSize: '24px', fontWeight: '700', color: '#f1f5f9' }}>
              ⚠️ Delete Transcript?
            </h3>
            <p style={{ margin: '0 0 24px 0', color: 'rgba(241, 245, 249, 0.8)', lineHeight: '1.6' }}>
              Are you sure you want to delete <strong style={{ color: '#f1f5f9' }}>"{deleteConfirm.meetingName}"</strong>? 
              This action cannot be undone.
            </p>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button
                onClick={() => setDeleteConfirm({ show: false, meetingName: null })}
                style={{
                  padding: '10px 20px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  border: '1px solid rgba(255, 255, 255, 0.2)',
                  borderRadius: '10px',
                  color: '#f1f5f9',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: '600',
                  transition: 'all 0.2s ease'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.15)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)'
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => deleteConfirm.meetingName && handleDeleteTranscript(deleteConfirm.meetingName)}
                style={{
                  padding: '10px 20px',
                  background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
                  border: 'none',
                  borderRadius: '10px',
                  color: 'white',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: '600',
                  transition: 'all 0.2s ease',
                  boxShadow: '0 4px 12px rgba(239, 68, 68, 0.4)'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'scale(1.05)'
                  e.currentTarget.style.boxShadow = '0 6px 16px rgba(239, 68, 68, 0.5)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'scale(1)'
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(239, 68, 68, 0.4)'
                }}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editModal.show && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0, 0, 0, 0.7)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '20px',
            overflow: 'auto',
            animation: 'fadeIn 0.2s ease'
          }}
          onClick={() => setEditModal({ show: false, meetingName: null, transcripts: [] })}
        >
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.95) 100%)',
              backdropFilter: 'blur(20px)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '20px',
              padding: '32px',
              maxWidth: '900px',
              width: '100%',
              maxHeight: '90vh',
              overflow: 'auto',
              boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
              animation: 'slideUp 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ 
              margin: '0 0 24px 0', 
              fontSize: '28px', 
              fontWeight: '700',
              background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text'
            }}>
              ✏️ Edit Transcript: {editModal.meetingName}
            </h3>
            
            <div style={{ marginBottom: '24px', maxHeight: '60vh', overflowY: 'auto' }}>
              {editModal.transcripts.map((entry, index) => (
                <div
                  key={index}
                  style={{
                    marginBottom: '16px',
                    padding: '16px',
                    background: 'rgba(255, 255, 255, 0.05)',
                    borderRadius: '12px',
                    border: '1px solid rgba(255, 255, 255, 0.1)'
                  }}
                >
                  <div style={{ display: 'flex', gap: '12px', marginBottom: '12px' }}>
                    <input
                      type="text"
                      value={entry.speaker || ''}
                      onChange={(e) => {
                        const updated = [...editModal.transcripts]
                        updated[index] = { ...updated[index], speaker: e.target.value }
                        setEditModal({ ...editModal, transcripts: updated })
                      }}
                      placeholder="Speaker name"
                      style={{
                        flex: '0 0 150px',
                        padding: '10px 12px',
                        background: 'rgba(255, 255, 255, 0.1)',
                        border: '1px solid rgba(255, 255, 255, 0.2)',
                        borderRadius: '8px',
                        color: '#f1f5f9',
                        fontSize: '14px',
                        outline: 'none'
                      }}
                    />
                    <button
                      onClick={() => {
                        const updated = editModal.transcripts.filter((_, i) => i !== index)
                        setEditModal({ ...editModal, transcripts: updated })
                      }}
                      style={{
                        padding: '10px 16px',
                        background: 'rgba(239, 68, 68, 0.2)',
                        border: '1px solid rgba(239, 68, 68, 0.4)',
                        borderRadius: '8px',
                        color: '#fca5a5',
                        cursor: 'pointer',
                        fontSize: '14px',
                        fontWeight: '600'
                      }}
                    >
                      Remove
                    </button>
                  </div>
                  <textarea
                    value={entry.text || ''}
                    onChange={(e) => {
                      const updated = [...editModal.transcripts]
                      updated[index] = { ...updated[index], text: e.target.value }
                      setEditModal({ ...editModal, transcripts: updated })
                    }}
                    placeholder="Transcript text..."
                    style={{
                      width: '100%',
                      minHeight: '80px',
                      padding: '12px',
                      background: 'rgba(255, 255, 255, 0.1)',
                      border: '1px solid rgba(255, 255, 255, 0.2)',
                      borderRadius: '8px',
                      color: '#f1f5f9',
                      fontSize: '14px',
                      fontFamily: 'inherit',
                      resize: 'vertical',
                      outline: 'none'
                    }}
                  />
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'space-between' }}>
              <button
                onClick={() => {
                  setEditModal({
                    ...editModal,
                    transcripts: [...editModal.transcripts, { speaker: '', text: '', is_final: true }]
                  })
                }}
                style={{
                  padding: '10px 20px',
                  background: 'rgba(99, 102, 241, 0.2)',
                  border: '1px solid rgba(99, 102, 241, 0.4)',
                  borderRadius: '10px',
                  color: '#a5b4fc',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: '600'
                }}
              >
                + Add Entry
              </button>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  onClick={() => setEditModal({ show: false, meetingName: null, transcripts: [] })}
                  style={{
                    padding: '10px 20px',
                    background: 'rgba(255, 255, 255, 0.1)',
                    border: '1px solid rgba(255, 255, 255, 0.2)',
                    borderRadius: '10px',
                    color: '#f1f5f9',
                    cursor: 'pointer',
                    fontSize: '14px',
                    fontWeight: '600'
                  }}
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveEdit}
                  style={{
                    padding: '10px 20px',
                    background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
                    border: 'none',
                    borderRadius: '10px',
                    color: 'white',
                    cursor: 'pointer',
                    fontSize: '14px',
                    fontWeight: '600',
                    boxShadow: '0 4px 12px rgba(99, 102, 241, 0.4)'
                  }}
                >
                  Save Changes
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notifications */}
      <div
        style={{
          position: 'fixed',
          top: '20px',
          right: '20px',
          zIndex: 2000,
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            style={{
              padding: '16px 20px',
              background: toast.type === 'success' 
                ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.9) 0%, rgba(5, 150, 105, 0.9) 100%)'
                : toast.type === 'error'
                ? 'linear-gradient(135deg, rgba(239, 68, 68, 0.9) 0%, rgba(220, 38, 38, 0.9) 100%)'
                : 'linear-gradient(135deg, rgba(99, 102, 241, 0.9) 0%, rgba(139, 92, 246, 0.9) 100%)',
              backdropFilter: 'blur(16px)',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              borderRadius: '12px',
              color: 'white',
              fontSize: '14px',
              fontWeight: '600',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.3)',
              animation: 'slideInRight 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              minWidth: '300px',
              maxWidth: '400px'
            }}
          >
            {toast.message}
          </div>
        ))}
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes slideUp {
          from { 
            opacity: 0;
            transform: translateY(20px);
          }
          to { 
            opacity: 1;
            transform: translateY(0);
          }
        }
        @keyframes slideInRight {
          from {
            opacity: 0;
            transform: translateX(100%);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
      `}</style>
    </div>
  )
}

