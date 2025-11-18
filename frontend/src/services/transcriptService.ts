import type { Transcript, TranscriptMessage } from '../types';
import { authService } from './authService';
import { apiConfig } from '../config/api';

export class TranscriptService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 3000;
  private listeners: Set<(transcript: Transcript, meetingName?: string) => void> = new Set();
  private onInitialTranscripts: ((transcripts: Transcript[]) => void) | null = null;
  private onCompleteTranscript: ((meetingTitle: string, transcripts: Transcript[]) => void) | null = null;
  private connectionCallbacks: Set<() => void> = new Set();
  private isIntentionallyDisconnecting = false;
  private apiUrl: string;

  constructor(apiUrl?: string) {
    // Use provided URL or default to config
    this.apiUrl = apiUrl || apiConfig.wsUrl;
  }

  connect(
    onTranscript: (transcript: Transcript, meetingName?: string) => void, 
    onInitial?: (transcripts: Transcript[]) => void,
    onComplete?: (meetingTitle: string, transcripts: Transcript[]) => void
  ) {
    if (onInitial) {
      this.onInitialTranscripts = onInitial;
    }
    if (onComplete) {
      this.onCompleteTranscript = onComplete;
    }
    this.listeners.add(onTranscript);

    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    // If there's a closed/closing WebSocket, clean it up first
    if (this.ws && (this.ws.readyState === WebSocket.CLOSED || this.ws.readyState === WebSocket.CLOSING)) {
      this.ws = null;
    }

    this.connectWebSocket();
  }

  onConnect(callback: () => void) {
    this.connectionCallbacks.add(callback);
    return () => this.connectionCallbacks.delete(callback);
  }

  private connectWebSocket() {
    try {
      if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
        return;
      }
      
      const token = authService.getToken();
      if (!token) {
        console.error('Cannot connect to WebSocket: No authentication token. Please log in.');
        return;
      }
      
      const wsUrl = `${this.apiUrl}/ws/transcripts?token=${encodeURIComponent(token)}`;
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.isIntentionallyDisconnecting = false;
        this.connectionCallbacks.forEach(cb => {
          try {
            cb();
          } catch (err) {
            console.error('Error in connection callback:', err);
          }
        });
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as TranscriptMessage;
          console.log('📨 WebSocket message received:', {
            type: message.type,
            meeting_name: message.meeting_name,
            timestamp: new Date().toLocaleTimeString()
          });
          
          if (message.type === 'transcript') {
            if (message.speaker && message.text !== undefined) {
              const transcript = {
                speaker: message.speaker,
                text: message.text,
                is_final: message.is_final ?? true,
                timestamp: Date.now(),
              } as Transcript;
              
              this.listeners.forEach((listener) => {
                try {
                  // Always pass both transcript and meeting_name (meeting_name may be undefined)
                  listener(transcript, message.meeting_name);
                } catch (err) {
                  console.error('Error in transcript listener:', err);
                }
              });
            }
          } else if (message.type === 'initial_transcripts' && message.transcripts) {
            if (this.onInitialTranscripts) {
              this.onInitialTranscripts(message.transcripts);
            }
          } else if (message.type === 'complete_transcript') {
            if (this.onCompleteTranscript && message.transcripts && message.meeting_title) {
              try {
                this.onCompleteTranscript(message.meeting_title, message.transcripts);
              } catch (err) {
                console.error('Error in complete transcript callback:', err);
              }
            }
          } else if (message.type === 'transcript_new' || message.type === 'transcript_update') {
            console.log(`📡 WebSocket: ${message.type} message received`, {
              meeting_name: message.meeting_name,
              transcript_count: message.transcripts?.length || 0,
              timestamp: new Date().toLocaleTimeString()
            });
            
            if (message.transcripts && message.transcripts.length > 0) {
              const transcripts = message.transcripts;
              
              transcripts.forEach((transcriptData: any, index: number) => {
                const transcript = {
                  speaker: transcriptData.speaker,
                  text: transcriptData.text,
                  is_final: transcriptData.is_final ?? true,
                  timestamp: Date.now(),
                } as Transcript;
                
                console.log(`  📦 Transcript ${index + 1}/${transcripts.length}:`, {
                  speaker: transcript.speaker,
                  text: transcript.text?.substring(0, 100),
                  is_final: transcript.is_final,
                  meeting: message.meeting_name
                });
                
                const listenersArray = Array.from(this.listeners);
                listenersArray.forEach((listener, listenerIndex) => {
                  try {
                    console.log(`    → Calling listener ${listenerIndex + 1} with transcript`);
                    listener(transcript, message.meeting_name);
                  } catch (err) {
                    console.error(`    ❌ Error in transcript listener ${listenerIndex + 1}:`, err);
                  }
                });
              });
            } else {
              console.warn(`⚠️ WebSocket: ${message.type} message received but no transcripts in payload`);
            }
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        // Don't log the error event details as they're not very useful
      };

      this.ws.onclose = (event) => {
        this.ws = null;
        
        // Don't reconnect if we intentionally disconnected
        if (this.isIntentionallyDisconnecting) {
          this.isIntentionallyDisconnecting = false;
          return;
        }
        
        // Handle authentication errors (1008 = Policy Violation, used for auth failures)
        if (event.code === 1008) {
          console.error('❌ WebSocket authentication failed. Please log in again.');
          // Clear invalid token and prevent reconnection
          authService.logout();
          return;
        }
        
        if (event.code !== 1000 && event.code !== 1001 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          setTimeout(() => this.connectWebSocket(), this.reconnectDelay);
        } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
          console.error('Max reconnection attempts reached. Please refresh the page.');
        }
      };
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
    }
  }

  requestTranscript(roomName: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify({
          type: 'request_transcript',
          room_name: roomName
        }));
      } catch (error) {
        console.error('Error requesting transcript:', error);
      }
    } else {
      if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
        this.connectWebSocket();
        setTimeout(() => {
          if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
              type: 'request_transcript',
              room_name: roomName
            }));
          }
        }, 1000);
      }
    }
  }

  watchTranscript(meetingName: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify({
          type: 'watch_transcript',
          meeting_name: meetingName,
          room_name: meetingName
        }));
      } catch (error) {
        console.error('Error requesting to watch transcript:', error);
      }
    } else {
      if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
        this.connectWebSocket();
        setTimeout(() => {
          if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
              type: 'watch_transcript',
              meeting_name: meetingName,
              room_name: meetingName
            }));
          }
        }, 1000);
      }
    }
  }

  unwatchTranscript(meetingName: string) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify({
          type: 'unwatch_transcript',
          meeting_name: meetingName,
          room_name: meetingName
        }));
      } catch (error) {
        console.error('Error requesting to unwatch transcript:', error);
      }
    }
  }

  disconnect() {
    this.isIntentionallyDisconnecting = true;
    if (this.ws) {
      const ws = this.ws;
      this.ws = null; // Clear reference first to prevent race conditions
      
      try {
        // Only close if the WebSocket is in a state that allows closing
        const readyState = ws.readyState;
        
        // If CONNECTING, wait a bit for it to either open or fail before closing
        if (readyState === WebSocket.CONNECTING) {
          // Set a timeout to close after a short delay if still connecting
          setTimeout(() => {
            try {
              if (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN) {
                ws.close(1000, 'Intentional disconnect');
              }
            } catch (err) {
              // Ignore errors
            }
          }, 100);
        } else if (readyState === WebSocket.OPEN) {
          // Remove event handlers first to prevent any callbacks from firing
          ws.onclose = null;
          ws.onerror = null;
          ws.onopen = null;
          ws.onmessage = null;
          ws.close(1000, 'Intentional disconnect');
        } else if (readyState === WebSocket.CLOSING || readyState === WebSocket.CLOSED) {
          // Already closing or closed, just remove handlers
          ws.onclose = null;
          ws.onerror = null;
          ws.onopen = null;
          ws.onmessage = null;
        }
      } catch (err) {
        // Ignore errors when closing - the WebSocket might already be closed or in an invalid state
        // This is expected in React Strict Mode during development
      }
    }
    this.listeners.clear();
    this.onInitialTranscripts = null;
    this.onCompleteTranscript = null;
    this.reconnectAttempts = 0; // Reset reconnect attempts on intentional disconnect
  }
}

