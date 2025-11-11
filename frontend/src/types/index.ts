export interface Transcript {
  speaker: string;
  text: string;
  is_final: boolean;
  timestamp?: number;
}

export interface TranscriptMessage {
  type: 'transcript' | 'initial_transcripts' | 'ack';
  speaker?: string;
  text?: string;
  is_final?: boolean;
  transcripts?: Transcript[];
  message?: string;
}

export interface RoomConnectionState {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
  roomName: string | null;
}

