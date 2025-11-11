export interface Transcript {
  speaker: string;
  text: string;
  is_final: boolean;
  timestamp?: number;
}

export interface TranscriptMessage {
  type: 'transcript' | 'initial_transcripts' | 'ack' | 'complete_transcript';
  speaker?: string;
  text?: string;
  is_final?: boolean;
  transcripts?: Transcript[];
  message?: string;
  meeting_title?: string;
}

export interface RoomConnectionState {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
  roomName: string | null;
}

