import { Room, RoomEvent, LocalAudioTrack, createLocalAudioTrack } from 'livekit-client';
import type { RoomConnectionState } from '../types';

export class LiveKitService {
  private room: Room | null = null;
  private localAudioTrack: LocalAudioTrack | null = null;
  private connectionState: RoomConnectionState = {
    isConnected: false,
    isConnecting: false,
    error: null,
    roomName: null,
  };
  private stateListeners: Set<(state: RoomConnectionState) => void> = new Set();

  async connect(roomUrl: string, token: string, roomName: string): Promise<void> {
    if (this.room?.state === 'connected') {
      return;
    }

    this.updateState({ isConnecting: true, error: null, roomName });

    try {
      if (this.room) {
        await this.room.disconnect();
      }

      this.room = new Room();
      this.setupRoomListeners();

      await this.room.connect(roomUrl, token);
      
      // Request microphone access and publish audio
      await this.startAudio();
      
      this.updateState({ 
        isConnected: true, 
        isConnecting: false, 
        error: null,
        roomName 
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      this.updateState({ 
        isConnected: false, 
        isConnecting: false, 
        error: errorMessage,
        roomName: null 
      });
      throw error;
    }
  }

  async startAudio(): Promise<void> {
    if (!this.room || this.localAudioTrack) {
      return;
    }

    try {
      // Request microphone access
      this.localAudioTrack = await createLocalAudioTrack({
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      });

      // Publish audio track to room
      await this.room.localParticipant.publishTrack(this.localAudioTrack);
      console.log('✅ Microphone audio published to room');
    } catch (error) {
      console.error('❌ Failed to start audio:', error);
      throw error;
    }
  }

  async stopAudio(): Promise<void> {
    if (this.localAudioTrack) {
      this.localAudioTrack.stop();
      this.localAudioTrack = null;
    }
  }

  private setupRoomListeners() {
    if (!this.room) return;

    this.room.on(RoomEvent.Connected, () => {
      this.updateState({ isConnected: true, isConnecting: false });
    });

    this.room.on(RoomEvent.Disconnected, () => {
      this.updateState({ isConnected: false, isConnecting: false });
    });
  }

  async disconnect(): Promise<void> {
    await this.stopAudio();
    if (this.room) {
      await this.room.disconnect();
      this.room = null;
    }
    this.updateState({ 
      isConnected: false, 
      isConnecting: false, 
      error: null,
      roomName: null 
    });
  }

  getRoom(): Room | null {
    return this.room;
  }

  getConnectionState(): RoomConnectionState {
    return { ...this.connectionState };
  }

  onStateChange(listener: (state: RoomConnectionState) => void) {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  private updateState(updates: Partial<RoomConnectionState>) {
    this.connectionState = { ...this.connectionState, ...updates };
    this.stateListeners.forEach(listener => listener(this.connectionState));
  }
}

