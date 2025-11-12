export interface Transcript {
  speaker: string;
  text: string;
  is_final: boolean;
  timestamp?: number;
}

export interface TranscriptMessage {
  type: 'transcript' | 'initial_transcripts' | 'ack' | 'complete_transcript' | 'transcript_new' | 'transcript_update';
  speaker?: string;
  text?: string;
  is_final?: boolean;
  transcripts?: Transcript[];
  message?: string;
  meeting_title?: string;
  meeting_name?: string; // For real-time updates
  is_update?: boolean; // For transcript_update messages
}

export interface RoomConnectionState {
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;
  roomName: string | null;
}

