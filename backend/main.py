import os
import logging
from collections.abc import AsyncIterable
from typing import List, Dict, Tuple, Optional
from pydantic import BaseModel

from dotenv import load_dotenv

from livekit import rtc, agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ModelSettings
from livekit.agents import stt
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from livekit.plugins import speechmatics
import asyncio
from api_server import get_transcript_manager, update_transcript_incremental

# Import for handling microphone errors (agent uses room audio only)
try:
    from sounddevice import PortAudioError
except ImportError:
    PortAudioError = None

stop_flag = asyncio.Event()
handoff_flag = asyncio.Event()
load_dotenv(".env.local")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diarizer")

# Reduce verbosity of turn detector timeout errors (they're non-critical)
# These timeouts happen when turn detection takes too long, but don't affect transcription
logging.getLogger("livekit.agents.voice.audio_recognition").setLevel(logging.ERROR)
logging.getLogger("livekit.plugins.turn_detector").setLevel(logging.ERROR)
logging.getLogger("livekit.agents").setLevel(
    logging.ERROR
)  # Suppress WARNING level noise including transcription publishing errors

# Suppress transcription publishing warnings when room is closed (expected during cleanup)
logging.getLogger("livekit.agents.voice.room_io._output").setLevel(logging.ERROR)
logging.getLogger("livekit.rtc.participant").setLevel(
    logging.ERROR
)  # Suppress PublishTranscriptionError warnings

# ------------------------------------------------------------
# Transcript state
# ------------------------------------------------------------
transcripts: List[Tuple[str, str]] = []
speaker_label_map: Dict[str, str] = {}
next_speaker_num: int = 1
shutdown_requested = False

# Get transcript manager for WebSocket broadcasting
transcript_manager = get_transcript_manager()


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


class sampingAgent(Agent):
    global speaker_label_map

    def __init__(self, ctx: agents.JobContext) -> None:
        super().__init__(
            instructions=(
                "You are doing sampling of unique speaker's name and match with thier speaker_id,  "
            ),
        )
        self.ctx = ctx
        self.done_sampling = False

    def stt_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncIterable[stt.SpeechEvent | str]:
        async def _transcribe():
            async for ev in Agent.default.stt_node(self, audio, model_settings):
                if isinstance(ev, stt.SpeechEvent) and ev.alternatives:
                    if ev.type and "FINAL" in ev.type.upper():
                        alt = ev.alternatives[0]  # livekit.agents.stt.SpeechData
                        text = alt.text or ""
                        print(text)
                        if "stop sampling" in text.lower():
                            self.done_sampling = True
                            logger.info(
                                "📢 'Done sampling' detected - setting handoff flag..."
                            )
                            # Set the handoff flag to trigger handoff in entrypoint
                            handoff_flag.set()

                        else:
                            spk = getattr(
                                alt, "speaker_id", None
                            )  # <-- canonical field
                            if spk not in speaker_label_map:
                                # Lazy import to avoid slow transformers import during multiprocessing
                                from langchain_openai import ChatOpenAI

                                class responseSchema(BaseModel):
                                    speaker_name: str
                                    speaker_id: int

                                print(text)
                                chatModel = ChatOpenAI(
                                    model="gpt-4o-mini", temperature=0
                                ).with_structured_output(responseSchema)
                                response = chatModel.invoke(
                                    f"for the given text {text}, please give me the unique speaker's name and match with thier speaker_id which is {spk} if speaker name is not mentioned in the text, please give me the name as 'unknown'"
                                )
                                print(response)
                                if response.speaker_name == "unknown":
                                    continue
                                else:
                                    print(
                                        f"Speaker name: {response.speaker_name} and speaker id: {spk}"
                                    )
                                    speaker_label_map[spk] = response.speaker_name
                                    # Update transcript manager
                                    transcript_manager.update_speaker_label(
                                        spk, response.speaker_name
                                    )

                        yield ev

        return _transcribe()

    def llm_node(
        self, chat_ctx: agents.ChatContext, tools: list, model_settings: ModelSettings
    ) -> AsyncIterable[str]:
        async def _silent():
            if False:
                yield ""

        return _silent()

    def tts_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncIterable[rtc.AudioFrame]:
        async def _silent():
            async for _ in text:
                pass
            if False:
                yield rtc.AudioFrame()

        return _silent()


class DiarizationAgent(Agent):
    def __init__(self, ctx: agents.JobContext) -> None:
        super().__init__(
            instructions=(
                "You are a silent transcription agent. "
                "Do not respond or speak; only transcribe user speech with speaker labels."
            )
        )
        self.ctx = ctx

    def stt_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncIterable[stt.SpeechEvent | str]:
        """
        Consume SpeechEvents from the base STT node and print transcripts with speaker labels.
        Correctly reads diarization from alt.speaker_id for both partial and final events.
        """
        print("diarization agent initialized")

        async def _transcribe():
            async for ev in Agent.default.stt_node(self, audio, model_settings):
                if isinstance(ev, stt.SpeechEvent) and ev.alternatives:
                    print(ev)
                    alt = ev.alternatives[0]  # livekit.agents.stt.SpeechData
                    text = alt.text or ""
                    spk = getattr(alt, "speaker_id", None)  # <-- canonical field
                    label = label_for_speaker_id(spk)
                    # Check for stop command (case-insensitive)
                    text_lower = text.lower()
                    if (
                        "stop recording" in text_lower
                        or "stop the recording" in text_lower
                    ):
                        logger.info(
                            f"Stop command detected: '{text}' - setting stop flag"
                        )
                        room_name = self.ctx.room.name if self.ctx.room else "Meeting"

                        # Save to old transcript.txt format for backward compatibility
                        with open("transcript.txt", "w") as f:
                            for sp, t in transcripts:
                                f.write(f"{sp}: {t}\n")
                            f.write("\n")
                            f.write("Stop command detected: " + text)
                            f.write("\n")

                        # Update the API server's transcript manager via HTTP (this will also save to JSON file)
                        try:
                            import aiohttp

                            async with aiohttp.ClientSession() as session:
                                api_url = os.getenv(
                                    "API_SERVER_URL", "http://localhost:8000"
                                )
                                async with session.post(
                                    f"{api_url}/transcripts/update",
                                    json={
                                        "transcripts": transcripts,
                                        "room_name": room_name,
                                    },
                                ) as resp:
                                    if resp.status == 200:
                                        await resp.json()
                                        logger.info(
                                            f"✅ Updated API server with {len(transcripts)} transcripts and saved to {room_name}.json"
                                        )
                                    else:
                                        logger.warning(
                                            f"⚠️  Failed to update API server: {resp.status}"
                                        )
                        except Exception as e:
                            logger.error(f"❌ Error updating API server: {e}")

                        # Then send via WebSocket (this will use API server's transcript manager)
                        asyncio.create_task(
                            transcript_manager.send_complete_transcript(
                                room_name, transcripts
                            )
                        )

                        stop_flag.set()
                        print("\n🛑 STOP COMMAND DETECTED! Stopping recording...\n")
                    # Check if this is a final transcript
                    ev_type = getattr(ev, "type", None)
                    ev_type_name = (
                        getattr(ev_type, "name", str(ev_type)) if ev_type else None
                    )
                    is_final = False

                    # Only treat as final if explicitly marked as FINAL_TRANSCRIPT
                    if ev_type_name and "FINAL" in ev_type_name.upper():
                        is_final = True

                    text_stripped = text.strip()
                    if text_stripped:
                        room_name = self.ctx.room.name if self.ctx.room else "Meeting"

                        if is_final:
                            # Final transcript - mark current entry as final
                            # Check if this is an update to the last transcript from the same speaker
                            updated_existing = False
                            is_duplicate = False

                            if transcripts:
                                last_speaker, last_text = transcripts[-1]

                                # Check for exact duplicate with last entry
                                if label == last_speaker and last_text == text_stripped:
                                    # Exact duplicate - skip adding
                                    logger.debug(
                                        f"⏭️  Skipping duplicate final transcript: {label} - {text_stripped[:50]}..."
                                    )
                                    is_duplicate = True
                                # If same speaker and new text contains the old text (it's an update/extension)
                                elif (
                                    label == last_speaker
                                    and last_text in text_stripped
                                    and len(text_stripped) > len(last_text)
                                ):
                                    transcripts[-1] = (label, text_stripped)
                                    updated_existing = True
                                else:
                                    # Check if this exact text already exists in recent entries (prevent repeats)
                                    # Check last 3 entries to catch duplicates
                                    for entry in transcripts[-3:]:
                                        entry_speaker, entry_text = entry
                                        if (
                                            entry_speaker == label
                                            and entry_text == text_stripped
                                        ):
                                            is_duplicate = True
                                            logger.debug(
                                                f"⏭️  Skipping duplicate final transcript (found in recent entries): {label} - {text_stripped[:50]}..."
                                            )
                                            break

                            if not updated_existing and not is_duplicate:
                                transcripts.append((label, text_stripped))
                                logger.info(
                                    f"Stored transcript {len(transcripts)}: {label} - {text_stripped[:50]}..."
                                )

                            # Always display the final transcript
                            print(f"[Final] {label}: {text}")
                            lines = [f"{sp}: {t}" for sp, t in transcripts]
                            print(
                                "\n📝 Full Transcript so far:\n"
                                + "\n".join(lines)
                                + "\n"
                            )

                            # Update JSON file incrementally for final event
                            try:
                                update_transcript_incremental(
                                    room_name, label, text_stripped, is_final=True
                                )
                            except Exception as e:
                                logger.error(
                                    f"❌ Error updating transcript incrementally: {e}"
                                )

                            # Update transcript manager's internal list (but don't broadcast)
                            # This allows the API server to retrieve transcripts when requested
                            asyncio.create_task(
                                transcript_manager.update_transcripts(
                                    label, text_stripped, is_final=True
                                )
                            )

                            # Also sync to API server in real-time so it has the latest transcripts
                            # This ensures the API server has transcripts when button is clicked
                            try:
                                import aiohttp

                                async def sync_to_api_server():
                                    try:
                                        async with aiohttp.ClientSession() as session:
                                            api_url = os.getenv(
                                                "API_SERVER_URL",
                                                "http://localhost:8000",
                                            )
                                            async with session.post(
                                                f"{api_url}/transcripts/update",
                                                json={
                                                    "transcripts": transcripts,
                                                    "room_name": room_name,
                                                },
                                            ) as resp:
                                                if resp.status != 200:
                                                    logger.debug(
                                                        f"Failed to sync transcript to API server: {resp.status}"
                                                    )
                                    except Exception:
                                        # Don't log errors for every transcript sync to avoid spam
                                        pass

                                asyncio.create_task(sync_to_api_server())
                            except Exception:
                                pass

                            # Don't broadcast in real-time - accumulate transcripts instead
                            # Transcripts will be sent when "stop recording" is detected or button is pressed

                        else:
                            # Interim transcript - update JSON file in real-time as words come in
                            print(f"[Interim] {label}: {text}")

                            # Update JSON file incrementally for interim event
                            try:
                                update_transcript_incremental(
                                    room_name, label, text_stripped, is_final=False
                                )
                            except Exception as e:
                                logger.error(
                                    f"❌ Error updating transcript incrementally (interim): {e}"
                                )

                            # Update transcript manager's internal list for interim events
                            asyncio.create_task(
                                transcript_manager.update_transcripts(
                                    label, text_stripped, is_final=False
                                )
                            )

                yield ev

        return _transcribe()

    def llm_node(
        self, chat_ctx: agents.ChatContext, tools: list, model_settings: ModelSettings
    ) -> AsyncIterable[str]:
        async def _silent():
            if False:
                yield ""

        return _silent()

    def tts_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncIterable[rtc.AudioFrame]:
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
    # Reset stop flag at the start of each session
    stop_flag.clear()

    sm_api_key = os.environ.get("SPEECHMATICS_API_KEY", "")
    if not sm_api_key:
        raise RuntimeError("SPEECHMATICS_API_KEY is required in environment")

    # Configure Speechmatics STT with native speaker diarization
    sm_stt = speechmatics.STT(
        api_key=sm_api_key,
        language="en",
        enable_diarization=True,
    )

    session = AgentSession(
        llm="google/gemini-2.5-flash",
        stt=sm_stt,
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    # Start with sampling agent
    # Note: Agent only uses room audio input, local microphone errors can be ignored
    try:
        await session.start(
            room=ctx.room,
            agent=DiarizationAgent(ctx),
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVC()
            ),
        )
    except Exception as e:
        # Ignore PortAudio errors for local microphone - agent uses room audio only
        error_type = type(e).__name__
        if PortAudioError and isinstance(e, PortAudioError):
            logger.warning(
                f"Ignoring local microphone error (agent uses room audio only): {e}"
            )
            # Session should still work with room audio, continue
        elif "PortAudio" in error_type or "sounddevice" in str(e).lower():
            logger.warning(
                f"Ignoring local microphone error (agent uses room audio only): {e}"
            )
            # Session should still work with room audio, continue
        else:
            raise


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
