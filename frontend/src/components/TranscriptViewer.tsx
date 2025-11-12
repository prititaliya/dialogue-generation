import { useEffect, useRef } from 'react';
import type { Transcript } from '../types';

interface TranscriptViewerProps {
  transcripts: Transcript[];
}

export default function TranscriptViewer({ transcripts }: TranscriptViewerProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcripts]);

  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: '100%', 
      background: '#1a1a1a', 
      color: 'white' 
    }}>
      <div style={{ padding: '16px', borderBottom: '1px solid #374151' }}>
        <h2 style={{ margin: 0, fontSize: '20px', fontWeight: '600' }}>Live Transcript</h2>
        <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#9ca3af' }}>
          {transcripts.length} {transcripts.length === 1 ? 'message' : 'messages'}
        </p>
      </div>
      
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px'
        }}
      >
        {transcripts.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#6b7280', marginTop: '32px' }}>
            <p>No transcripts yet. Start speaking to see transcripts appear here.</p>
          </div>
        ) : (
          transcripts.map((transcript, index) => (
            <div
              key={index}
              style={{
                padding: '12px',
                borderRadius: '8px',
                background: transcript.is_final ? '#1f2937' : '#1f2937',
                borderLeft: `4px solid ${transcript.is_final ? '#3b82f6' : '#fbbf24'}`,
                opacity: transcript.is_final ? 1 : 0.75
              }}
            >
              <div style={{ display: 'flex', gap: '12px' }}>
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: '#2563eb',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '14px',
                  fontWeight: '600',
                  flexShrink: 0
                }}>
                  {transcript.speaker.charAt(0).toUpperCase()}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <span style={{ fontWeight: '600', color: '#60a5fa' }}>
                      {transcript.speaker}
                    </span>
                    {!transcript.is_final && (
                      <span style={{
                        fontSize: '12px',
                        color: '#fbbf24',
                        background: 'rgba(251, 191, 36, 0.2)',
                        padding: '2px 8px',
                        borderRadius: '4px'
                      }}>
                        Interim
                      </span>
                    )}
                  </div>
                  <p style={{ margin: 0, color: '#e5e7eb', wordBreak: 'break-word' }}>
                    {transcript.text}
                  </p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

