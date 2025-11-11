import type { Transcript, TranscriptMessage } from '../types';

export class TranscriptService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 3000;
  private listeners: Set<(transcript: Transcript) => void> = new Set();
  private onInitialTranscripts: ((transcripts: Transcript[]) => void) | null = null;
  private onCompleteTranscript: ((meetingTitle: string, transcripts: Transcript[]) => void) | null = null;
  private connectionCallbacks: Set<() => void> = new Set();
  private isIntentionallyDisconnecting = false;
  private apiUrl: string;

  constructor(apiUrl: string = 'ws://localhost:8000') {
    this.apiUrl = apiUrl;
  }

  connect(
    onTranscript: (transcript: Transcript) => void, 
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

    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    if (this.ws?.readyState === WebSocket.CONNECTING) {
      return;
    }

    this.connectWebSocket();
  }

  onConnect(callback: () => void) {
    this.connectionCallbacks.add(callback);
    return () => this.connectionCallbacks.delete(callback);
  }

  private connectWebSocket() {
    try {
      const wsUrl = `${this.apiUrl}/ws/transcripts`;
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
                  listener(transcript);
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
            // Handle complete transcript with meeting title
            console.log('Received complete_transcript:', {
              meeting_title: message.meeting_title,
              transcript_count: message.transcripts?.length || 0
            });
            if (this.onCompleteTranscript && message.transcripts && message.meeting_title) {
              try {
                this.onCompleteTranscript(message.meeting_title, message.transcripts);
                console.log('Successfully processed complete transcript');
              } catch (err) {
                console.error('Error in complete transcript callback:', err);
              }
            } else {
              console.warn('Missing data in complete_transcript message:', {
                hasCallback: !!this.onCompleteTranscript,
                hasTranscripts: !!message.transcripts,
                hasTitle: !!message.meeting_title
              });
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
        
        // Only reconnect if it wasn't a normal closure and we haven't exceeded max attempts
        if (event.code !== 1000 && event.code !== 1001 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          console.log(`Reconnecting... (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
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
    console.log('Requesting transcript for room:', roomName);
    console.log('WebSocket state:', this.ws ? this.ws.readyState : 'null');
    
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        const message = {
          type: 'request_transcript',
          room_name: roomName
        };
        console.log('Sending request_transcript message:', message);
        this.ws.send(JSON.stringify(message));
      } catch (error) {
        console.error('Error requesting transcript:', error);
      }
    } else {
      console.warn('WebSocket is not connected. Current state:', this.ws?.readyState);
      // Try to reconnect if not connected
      if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
        console.log('Attempting to reconnect WebSocket...');
        this.connectWebSocket();
        // Wait a bit for connection, then retry
        setTimeout(() => {
          if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            const message = {
              type: 'request_transcript',
              room_name: roomName
            };
            console.log('Retrying request_transcript after reconnect:', message);
            this.ws.send(JSON.stringify(message));
          } else {
            console.error('Failed to reconnect WebSocket. Please refresh the page.');
          }
        }, 1000);
      }
    }
  }

  disconnect() {
    this.isIntentionallyDisconnecting = true;
    if (this.ws) {
      const ws = this.ws;
      this.ws = null; // Clear reference first to prevent race conditions
      
      try {
        // Remove event handlers first to prevent any callbacks from firing
        ws.onclose = null;
        ws.onerror = null;
        ws.onopen = null;
        ws.onmessage = null;
        
        // Only close if the WebSocket is in a state that allows closing
        const readyState = ws.readyState;
        if (readyState === WebSocket.OPEN) {
          ws.close(1000, 'Intentional disconnect');
        } else if (readyState === WebSocket.CONNECTING) {
          // If still connecting, just close without waiting
          // The browser will handle the cleanup
          ws.close();
        }
        // If CLOSING or CLOSED, do nothing
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

