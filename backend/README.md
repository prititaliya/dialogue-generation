# Dialogue Generation System

A two-phase real-time dialogue transcription system that automatically identifies speakers and transcribes multi-speaker conversations with speaker labels.

## Overview

This system uses LiveKit agents to:
1. **Sampling Phase**: Automatically identify and map speaker names to speaker IDs using AI
2. **Diarization Phase**: Transcribe conversations with proper speaker labels

## Features

- 🎤 Real-time speech-to-text transcription
- 👥 Automatic speaker diarization (identifies who said what)
- 🤖 AI-powered speaker name extraction
- 📝 Real-time transcript display
- 💾 Automatic transcript saving
- 🔄 Seamless agent handoff between phases

## Prerequisites

- Python 3.12 or higher
- LiveKit server (local or cloud)
- API keys for:
  - Speechmatics (for STT and diarization)
  - OpenAI (for speaker name extraction)

## Installation

1. **Clone the repository** (if applicable) or navigate to the project directory:
   ```bash
   cd dialogue-generation
   ```

2. **Install dependencies** using `uv` (recommended) or `pip`:
   ```bash
   # Using uv (recommended)
   uv sync
   
   # Or using pip
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   Create a `.env.local` file in the project root:
   ```bash
   SPEECHMATICS_API_KEY=your_speechmatics_api_key_here
   OPENAI_API_KEY=your_openai_api_key_here
   ```

## Configuration

### Required Environment Variables

- `SPEECHMATICS_API_KEY`: Your Speechmatics API key for speech-to-text and diarization
- `OPENAI_API_KEY`: Your OpenAI API key for speaker name extraction

### Optional Configuration

You can customize the Speechmatics STT settings in `main.py`:
- `enable_diarization`: Enable speaker diarization (default: True)
- `language`: Language code (default: "en")

## Usage

### Starting the Agent

Run the main script:
```bash
python main.py dev
```

Or if using LiveKit cloud:
```bash
python main.py start
```

### Workflow

#### Phase 1: Sampling Agent

1. **Start the agent** - The system begins in sampling mode
2. **Speak naturally** - As different speakers talk, the system will:
   - Detect new speakers by their `speaker_id`
   - Extract speaker names from the conversation using AI
   - Map speaker names to their IDs
   - Display: `Speaker name: [name] and speaker id: [id]`
3. **End sampling** - When you're ready to start transcription, say:
   ```
   "stop sampling"
   ```

#### Phase 2: Diarization Agent

1. **Automatic handoff** - The system automatically switches to transcription mode
2. **Real-time transcription** - The system will:
   - Transcribe all speech in real-time
   - Label each utterance with the speaker's name
   - Display transcripts in the format: `[Final] Speaker Name: transcript text`
   - Show interim (partial) transcripts as: `[Interim] Speaker Name: partial text`
3. **Stop recording** - To end the session, say:
   ```
   "stop recording"
   or
   "stop the recording"
   ```

### Output

- **Console Output**: Real-time transcripts are displayed in the terminal
- **Transcript File**: When you say "stop recording", a `transcript.txt` file is created with:
  - All final transcripts with speaker labels
  - The stop command that ended the session

### Example Session

```
# Phase 1: Sampling
[User speaks] "Hi, I'm John and this is my colleague Sarah"
Speaker name: John and speaker id: spk_0
Speaker name: Sarah and speaker id: spk_1

[User says] "stop sampling"
📢 'Done sampling' detected - setting handoff flag...
🔄 Handoff flag triggered - switching to DiarizationAgent...
✅ Successfully handed off to DiarizationAgent

# Phase 2: Transcription
[Final] John: So, let's discuss the project timeline
[Final] Sarah: I think we should aim for Q2 delivery
[Final] John: That sounds reasonable

[User says] "stop recording"
🛑 STOP COMMAND DETECTED! Stopping recording...
```

## How It Works

### Architecture

1. **SamplingAgent**:
   - Listens for speech and detects new speakers
   - Uses OpenAI GPT-4o-mini to extract speaker names from context
   - Maps speaker names to speaker IDs
   - Ignores speakers with "unknown" names
   - Triggers handoff when "stop sampling" is detected

2. **DiarizationAgent**:
   - Transcribes all speech in real-time
   - Uses the speaker label map from the sampling phase
   - Displays transcripts with proper speaker labels
   - Saves transcripts to file when stopped

### Speaker Identification

The system uses AI to extract speaker names from the conversation context. For example:
- If someone says "Hi, I'm Alice", the system will identify that speaker as "Alice"
- If a name isn't mentioned, it returns "unknown" and skips that speaker
- Speaker IDs are automatically assigned by Speechmatics diarization

## Troubleshooting

### Common Issues

1. **"SPEECHMATICS_API_KEY is required"**
   - Make sure your `.env.local` file exists and contains the API key
   - Check that the file is in the project root directory

2. **Speaker names not being detected**
   - Ensure speakers mention their names in the conversation
   - The AI will return "unknown" if names aren't found, and those speakers are skipped

3. **Handoff not working**
   - Make sure you say "stop sampling" (not "done sampling")
   - Check the console logs for handoff status messages

4. **Transcripts not saving**
   - The transcript file is only created when you say "stop recording"
   - Check that you have write permissions in the project directory

## File Structure

```
dialogue-generation/
├── main.py                 # Main application code
├── requirements.txt        # Python dependencies
├── pyproject.toml          # Project configuration
├── .env.local              # Environment variables (create this)
├── transcript.txt          # Output transcript file (generated)
└── README.md              # This file
```

## Dependencies

- `livekit-agents`: LiveKit agent framework
- `livekit-plugins-speechmatics`: Speechmatics STT integration
- `livekit-plugins-noise-cancellation`: Noise cancellation
- `langchain-openai`: OpenAI integration for speaker name extraction
- `python-dotenv`: Environment variable management

## Notes

- The system requires an active LiveKit room connection
- Real-time transcription works best with clear audio
- Speaker identification works best when speakers introduce themselves
- The system is designed for English language (can be configured for others)

## License

[Add your license here]

## Support

For issues or questions, please check the logs for detailed error messages. The system provides extensive logging to help diagnose problems.

