import type { Transcript, TranscriptMessage } from '../types';

export class TranscriptService {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 3000;
  private listeners: Set<(transcript: Transcript) => void> = new Set();
  private onInitialTranscripts: ((transcripts: Transcript[]) => void) | null = null;
  private connectionCallbacks: Set<() => void> = new Set();

  constructor(private apiUrl: string = 'ws://localhost:8000') {}

  connect(onTranscript: (transcript: Transcript) => void, onInitial?: (transcripts: Transcript[]) => void) {
    if (onInitial) {
      this.onInitialTranscripts = onInitial;
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

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.listeners.clear();
    this.onInitialTranscripts = null;
  }
}

