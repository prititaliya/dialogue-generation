import { authService } from './authService';
import { apiConfig } from '../config/api';

const HTTP_API_URL = apiConfig.httpUrl;

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface SummaryResponse {
  meeting_id: string;
  summary: string;
}

export class ChatbotService {
  /**
   * Generate summary for a transcript using meeting_id
   */
  async generateSummary(meetingId: string): Promise<SummaryResponse> {
    const response = await fetch(`${HTTP_API_URL}/chatbot/summary`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authService.getAuthHeaders(),
      },
      body: JSON.stringify({ meeting_id: meetingId }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Failed to generate summary' }));
      throw new Error(error.detail || 'Failed to generate summary');
    }

    return response.json();
  }

  /**
   * Stream chat response from the chatbot using meeting_id
   */
  async streamChatResponse(
    meetingId: string,
    question: string,
    chatHistory: ChatMessage[],
    onChunk: (chunk: string) => void,
    onComplete: () => void,
    onError: (error: Error) => void
  ): Promise<void> {
    try {
      const response = await fetch(`${HTTP_API_URL}/chatbot/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authService.getAuthHeaders(),
        },
        body: JSON.stringify({
          meeting_id: meetingId,
          question,
          chat_history: chatHistory,
        }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Failed to get chat response' }));
        throw new Error(error.detail || 'Failed to get chat response');
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data === '[DONE]') {
              onComplete();
              return;
            }
            
            try {
              const parsed = JSON.parse(data);
              if (parsed.chunk) {
                onChunk(parsed.chunk);
              }
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
      }

      onComplete();
    } catch (error) {
      onError(error instanceof Error ? error : new Error('Unknown error'));
    }
  }
}

export const chatbotService = new ChatbotService();

