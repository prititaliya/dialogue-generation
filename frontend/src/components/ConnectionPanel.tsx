import { useState } from 'react';
import type { RoomConnectionState } from '../types';

interface ConnectionPanelProps {
  connectionState: RoomConnectionState;
  onConnect: (roomName: string, token: string) => void;
  onDisconnect: () => void;
}

export default function ConnectionPanel({
  connectionState,
  onConnect,
  onDisconnect,
}: ConnectionPanelProps) {
  const [roomName, setRoomName] = useState('');
  const [token, setToken] = useState('');

  const handleConnect = () => {
    if (roomName && token) {
      onConnect(roomName, token);
    }
  };

  return (
    <div style={{
      background: '#1f2937',
      padding: '24px',
      borderRadius: '8px',
      border: '1px solid #374151'
    }}>
      <h3 style={{ margin: '0 0 16px 0', fontSize: '18px', fontWeight: '600', color: 'white' }}>
        Room Connection
      </h3>
      
      {!connectionState.isConnected ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#d1d5db', marginBottom: '8px' }}>
              Room Name
            </label>
            <input
              type="text"
              value={roomName}
              onChange={(e) => setRoomName(e.target.value)}
              placeholder="Enter room name"
              disabled={connectionState.isConnecting}
              style={{
                width: '100%',
                padding: '8px 12px',
                background: '#374151',
                border: '1px solid #4b5563',
                borderRadius: '6px',
                color: 'white',
                fontSize: '14px'
              }}
            />
          </div>
          
          <div>
            <label style={{ display: 'block', fontSize: '14px', fontWeight: '500', color: '#d1d5db', marginBottom: '8px' }}>
              Access Token
            </label>
            <textarea
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Paste LiveKit access token"
              rows={4}
              disabled={connectionState.isConnecting}
              style={{
                width: '100%',
                padding: '8px 12px',
                background: '#374151',
                border: '1px solid #4b5563',
                borderRadius: '6px',
                color: 'white',
                fontSize: '12px',
                fontFamily: 'monospace',
                resize: 'vertical'
              }}
            />
          </div>
          
          <button
            onClick={handleConnect}
            disabled={!roomName || !token || connectionState.isConnecting}
            style={{
              width: '100%',
              padding: '10px',
              background: connectionState.isConnecting || !roomName || !token ? '#6b7280' : '#2563eb',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontSize: '16px',
              fontWeight: '500',
              cursor: connectionState.isConnecting || !roomName || !token ? 'not-allowed' : 'pointer'
            }}
          >
            {connectionState.isConnecting ? 'Connecting...' : 'Connect to Room'}
          </button>
          
          {connectionState.error && (
            <div style={{
              background: '#991b1b',
              border: '1px solid #dc2626',
              color: '#fca5a5',
              padding: '12px',
              borderRadius: '6px',
              fontSize: '14px'
            }}>
              Error: {connectionState.error}
            </div>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#4ade80' }}>
            <div style={{
              width: '8px',
              height: '8px',
              background: '#4ade80',
              borderRadius: '50%'
            }}></div>
            <span style={{ fontWeight: '500' }}>Connected to: {connectionState.roomName}</span>
          </div>
          
          <button
            onClick={onDisconnect}
            style={{
              width: '100%',
              padding: '10px',
              background: '#dc2626',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontSize: '16px',
              fontWeight: '500',
              cursor: 'pointer'
            }}
          >
            Disconnect
          </button>
        </div>
      )}
    </div>
  );
}

