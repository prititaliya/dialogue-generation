import os
import sys
import signal
import logging
import time
import threading
from collections.abc import AsyncIterable
from typing import List, Dict, Tuple, Optional

from dotenv import load_dotenv

from livekit import rtc, agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ModelSettings
from livekit.agents import stt
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

# Speechmatics STT with diarization
from livekit.plugins import speechmatics

# ------------------------------------------------------------
# Env & logging
# ------------------------------------------------------------
# .env.local should include:
# SPEECHMATICS_API_KEY=sm_api_key
# LIVEKIT_URL=wss://<your-livekit>/ (if required by runner)
# LIVEKIT_API_KEY=...
# LIVEKIT_API_SECRET=...
load_dotenv(".env.local")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diarizer")

# Reduce verbosity of turn detector timeout errors (they're non-critical)
# These timeouts happen when turn detection takes too long, but don't affect transcription
logging.getLogger("livekit.agents.voice.audio_recognition").setLevel(logging.ERROR)
logging.getLogger("livekit.plugins.turn_detector").setLevel(logging.ERROR)
logging.getLogger("livekit.agents").setLevel(logging.WARNING)  # Reduce INFO level noise

# ------------------------------------------------------------
# Transcript state
# ------------------------------------------------------------
transcripts: List[Tuple[str, str]] = []
speaker_label_map: Dict[str, str] = {}
next_speaker_num: int = 1
shutdown_requested = False

def save_transcripts():
    """Save transcripts to a file."""
    global transcripts
    if not transcripts:
        print("\n⚠️  No transcripts to save")
        return
    
    project_dir = os.path.dirname(os.path.abspath(__file__))
    filename = os.path.join(project_dir, f"transcript_{int(time.time())}.txt")
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("Full Transcript\n")
            f.write("=" * 50 + "\n\n")
            for speaker, text in transcripts:
                f.write(f"{speaker}: {text}\n\n")
        print(f"\n✅ Transcripts saved to: {os.path.basename(filename)}")
        print(f"📁 Full path: {os.path.abspath(filename)}")
        print(f"📊 Total entries: {len(transcripts)}")
        return filename
    except Exception as e:
        logger.error(f"Failed to save transcripts: {e}", exc_info=True)
        print(f"❌ Error saving transcripts: {e}")
        return None

def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    print("\n\n🛑 Shutdown requested. Saving transcripts and exiting...")
    shutdown_requested = True
    save_transcripts()
    sys.exit(0)

def exit_command_listener():
    """Background thread that listens for exit commands."""
    global shutdown_requested
    print("\n💡 Tip: Type 'quit', 'exit', 'q', or 'save' to save and exit (Ctrl+C also works)\n")
    
    while not shutdown_requested:
        try:
            user_input = input().strip().lower()
            
            if user_input in ['quit', 'exit', 'q']:
                print("\n🛑 Exit command received. Saving transcripts and exiting...")
                shutdown_requested = True
                save_transcripts()
                os._exit(0)
            elif user_input == 'save':
                print("\n💾 Manual save requested...")
                save_transcripts()
                print("✅ Save complete. Continue transcribing or type 'quit' to exit.\n")
        except (EOFError, KeyboardInterrupt):
            break
        except Exception as e:
            logger.error(f"Error in exit command listener: {e}")
            break

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C (still works)
signal.signal(signal.SIGTERM, signal_handler)  # Termination signal

# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------
def label_for_speaker_id(speaker_id: Optional[str]) -> str:
    global next_speaker_num
    if not speaker_id:
        speaker_id = "unknown"
    if speaker_id not in speaker_label_map:
        speaker_label_map[speaker_id] = f"Speaker {next_speaker_num}"
        next_speaker_num += 1
    return speaker_label_map[speaker_id]

# ------------------------------------------------------------
# Agent
# ------------------------------------------------------------
class DiarizationAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a silent transcription agent. "
                "Do not respond or speak; only transcribe user speech with speaker labels."
            ),
        )

    def stt_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncIterable[stt.SpeechEvent | str]:
        """
        Consume SpeechEvents from the base STT node and print transcripts with speaker labels.
        Correctly reads diarization from alt.speaker_id for both partial and final events.
        """
        async def _transcribe():
            async for ev in Agent.default.stt_node(self, audio, model_settings):
                if isinstance(ev, stt.SpeechEvent) and ev.alternatives:
                    alt = ev.alternatives[0]  # livekit.agents.stt.SpeechData
                    text = alt.text or ""
                    spk = getattr(alt, "speaker_id", None)   # <-- canonical field
                    label = label_for_speaker_id(spk)

                    # Check if this is a final transcript
                    ev_type = getattr(ev, "type", None)
                    ev_type_name = getattr(ev_type, "name", str(ev_type)) if ev_type else None
                    is_final = False
                    
                    # Only treat as final if explicitly marked as FINAL_TRANSCRIPT
                    if ev_type_name and "FINAL" in ev_type_name.upper():
                        is_final = True
                    
                    text_stripped = text.strip()
                    if text_stripped:
                        if is_final:
                            # Final transcript - only store truly final ones
                            # Check if this is an update to the last transcript from the same speaker
                            updated_existing = False
                            if transcripts:
                                last_speaker, last_text = transcripts[-1]
                                # If same speaker and new text contains the old text (it's an update/extension)
                                if label == last_speaker and last_text in text_stripped:
                                    transcripts[-1] = (label, text_stripped)
                                    updated_existing = True
                            
                            if not updated_existing:
                                if not transcripts or transcripts[-1][1] != text_stripped:
                                    transcripts.append((label, text_stripped))
                                    logger.info(f"Stored transcript {len(transcripts)}: {label} - {text_stripped[:50]}...")
                            
                            # Always display the final transcript
                            print(f"[Final] {label}: {text}")
                            lines = [f"{sp}: {t}" for sp, t in transcripts]
                            print("\n📝 Full Transcript so far:\n" + "\n".join(lines) + "\n")
                            
                            if len(transcripts) % 10 == 0 and len(transcripts) > 0:
                                saved_file = save_transcripts()
                                if saved_file:
                                    print(f"💡 Auto-saved: {os.path.basename(saved_file)}")
                        else:
                            # Interim transcript - just display, never store
                            print(f"[Interim] {label}: {text}")

                yield ev

        return _transcribe()

    def llm_node(self, chat_ctx: agents.ChatContext, tools: list, model_settings: ModelSettings) -> AsyncIterable[str]:
        async def _silent():
            if False:
                yield ""
        return _silent()

    def tts_node(self, text: AsyncIterable[str], model_settings: ModelSettings) -> AsyncIterable[rtc.AudioFrame]:
        async def _silent():
            async for _ in text:
                pass
            if False:
                yield rtc.AudioFrame()
        return _silent()

# ------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------
async def entrypoint(ctx: agents.JobContext):
    """
    Starts an AgentSession with Speechmatics STT configured for diarization.
    """
    sm_api_key = os.environ.get("SPEECHMATICS_API_KEY", "")
    if not sm_api_key:
        raise RuntimeError("SPEECHMATICS_API_KEY is required in environment")

    # Configure Speechmatics STT with native speaker diarization
    sm_stt = speechmatics.STT(
        api_key=sm_api_key,
        language="en",
        enable_diarization=True,
        # Optional tuning:
        # max_speakers=4,
        # diarization_sensitivity=0.6,
        # prefer_current_speaker=True,
        # focus_speakers=None,
        # ignore_speakers=None,
        # You can also customize how the text formats speaker tags on the wire:
        # speaker_active_format="@{speaker_id}: {text}",
        # speaker_passive_format="@{speaker_id} [bg]: {text}",
    )

    session = AgentSession(
        llm="google/gemini-2.5-flash",
        stt=sm_stt,
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    try:
        await session.start(
            room=ctx.room,
            agent=DiarizationAgent(),
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        )
    finally:
        print("\n💾 Session ended. Saving transcripts...")
        save_transcripts()

if __name__ == "__main__":
    threading.Thread(target=exit_command_listener, daemon=True).start()
    
    try:
        agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user. Saving transcripts...")
        save_transcripts()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        save_transcripts()
        raise
