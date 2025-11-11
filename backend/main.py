import os
import sys
import signal
import logging
import time
import threading
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
from api_server import get_transcript_manager

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
logging.getLogger("livekit.agents").setLevel(logging.ERROR)  # Suppress WARNING level noise including transcription publishing errors

# Suppress transcription publishing warnings when room is closed (expected during cleanup)
logging.getLogger("livekit.agents.voice.room_io._output").setLevel(logging.ERROR)
logging.getLogger("livekit.rtc.participant").setLevel(logging.ERROR)  # Suppress PublishTranscriptionError warnings

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

    def stt_node(self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings) -> AsyncIterable[stt.SpeechEvent | str]:
        async def _transcribe():            
            async for ev in Agent.default.stt_node(self, audio, model_settings):
                if isinstance(ev, stt.SpeechEvent) and ev.alternatives:
                    if ev.type and "FINAL" in ev.type.upper():
                        
                        alt = ev.alternatives[0]  # livekit.agents.stt.SpeechData
                        text = alt.text or ""
                        print(text)
                        if "stop sampling" in text.lower():
                            self.done_sampling = True
                            logger.info("📢 'Done sampling' detected - setting handoff flag...")
                            # Set the handoff flag to trigger handoff in entrypoint
                            handoff_flag.set()

                        else:
                            spk = getattr(alt, "speaker_id", None)   # <-- canonical field
                            if spk not in speaker_label_map:
                                # Lazy import to avoid slow transformers import during multiprocessing
                                from langchain_openai import ChatOpenAI
                                
                                class responseSchema(BaseModel):
                                    speaker_name: str
                                    speaker_id: int
                                print(text)
                                chatModel = ChatOpenAI(model="gpt-4o-mini", temperature=0).with_structured_output(responseSchema)
                                response = chatModel.invoke(f"for the given text {text}, please give me the unique speaker's name and match with thier speaker_id which is {spk} if speaker name is not mentioned in the text, please give me the name as 'unknown'")
                                print(response)
                                if response.speaker_name == "unknown":
                                    continue
                                else:
                                    print(f"Speaker name: {response.speaker_name} and speaker id: {spk}")
                                    speaker_label_map[spk] = response.speaker_name
                                    # Update transcript manager
                                    transcript_manager.update_speaker_label(spk, response.speaker_name)
                        
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
class DiarizationAgent(Agent):
    def __init__(self,ctx: agents.JobContext) -> None:
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
                    spk = getattr(alt, "speaker_id", None)   # <-- canonical field
                    label = label_for_speaker_id(spk)
                    # Check for stop command (case-insensitive)
                    text_lower = text.lower()
                    if "stop recording" in text_lower or "stop the recording" in text_lower:
                        logger.info(f"Stop command detected: '{text}' - setting stop flag")
                        room_name = self.ctx.room.name if self.ctx.room else "Meeting"
                        
                        # Save to old transcript.txt format for backward compatibility
                        with open("transcript.txt", "w") as f:
                            for sp, t in transcripts:
                                f.write(f"{sp}: {t}\n")
                            f.write("\n")
                            f.write("Stop command detected: "+text)
                            f.write("\n")
                        
                        # Update the API server's transcript manager via HTTP (this will also save to JSON file)
                        try:
                            import aiohttp
                            async with aiohttp.ClientSession() as session:
                                api_url = os.getenv("API_SERVER_URL", "http://localhost:8000")
                                async with session.post(
                                    f"{api_url}/transcripts/update",
                                    json={"transcripts": transcripts, "room_name": room_name}
                                ) as resp:
                                    if resp.status == 200:
                                        result = await resp.json()
                                        logger.info(f"✅ Updated API server with {len(transcripts)} transcripts and saved to {room_name}.json")
                                    else:
                                        logger.warning(f"⚠️  Failed to update API server: {resp.status}")
                        except Exception as e:
                            logger.error(f"❌ Error updating API server: {e}")
                        
                        # Then send via WebSocket (this will use API server's transcript manager)
                        asyncio.create_task(
                            transcript_manager.send_complete_transcript(room_name, transcripts)
                        )
                        
                        stop_flag.set()
                        print(f"\n🛑 STOP COMMAND DETECTED! Stopping recording...\n")
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
                            
                            # Update transcript manager's internal list (but don't broadcast)
                            # This allows the API server to retrieve transcripts when requested
                            asyncio.create_task(
                                transcript_manager.update_transcripts(label, text_stripped)
                            )
                            
                            # Also sync to API server in real-time so it has the latest transcripts
                            # This ensures the API server has transcripts when button is clicked
                            try:
                                import aiohttp
                                async def sync_to_api_server():
                                    try:
                                        async with aiohttp.ClientSession() as session:
                                            api_url = os.getenv("API_SERVER_URL", "http://localhost:8000")
                                            async with session.post(
                                                f"{api_url}/transcripts/update",
                                                json={"transcripts": transcripts, "room_name": self.ctx.room.name if self.ctx.room else "Meeting"}
                                            ) as resp:
                                                if resp.status != 200:
                                                    logger.debug(f"Failed to sync transcript to API server: {resp.status}")
                                    except Exception as e:
                                        # Don't log errors for every transcript sync to avoid spam
                                        pass
                                asyncio.create_task(sync_to_api_server())
                            except Exception:
                                pass
                            
                            # Don't broadcast in real-time - accumulate transcripts instead
                            # Transcripts will be sent when "stop recording" is detected or button is pressed
                            
                        else:
                            # Interim transcript - just display, never store
                            print(f"[Interim] {label}: {text}")
                            # Don't broadcast interim transcripts either

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

    # Start with sampling agent
# Note: Agent only uses room audio input, local microphone errors can be ignored
    try:
        await session.start(
            room=ctx.room,
            agent=DiarizationAgent(ctx),
            room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()),
        )
    except Exception as e:
        # Ignore PortAudio errors for local microphone - agent uses room audio only
        error_type = type(e).__name__
        if PortAudioError and isinstance(e, PortAudioError):
            logger.warning(f"Ignoring local microphone error (agent uses room audio only): {e}")
            # Session should still work with room audio, continue
        elif "PortAudio" in error_type or "sounddevice" in str(e).lower():
            logger.warning(f"Ignoring local microphone error (agent uses room audio only): {e}")
            # Session should still work with room audio, continue
        else:
            raise
     # optional: observe close events for diagnostics
    # @session.on("close")
    # def _on_close(ev=None):
    #     async def _close():
    #         logger.info("AgentSession closed")
    #     asyncio.create_task(_close())

    # async def on_shutdown(reason: str = ""):
    #     logger.info(f"shutdown hook fired: {reason}")

    # ctx.add_shutdown_callback(on_shutdown)

    # # Reset handoff flag at the start
    # handoff_flag.clear()
    
    # # Start with sampling agent
    # # Note: Agent only uses room audio input, local microphone errors can be ignored
    # try:
    #     await session.start(
    #         room=ctx.room,
    #         agent=DiarizationAgent(ctx),
    #         room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()),
    #     )
    # except Exception as e:
    #     # Ignore PortAudio errors for local microphone - agent uses room audio only
    #     error_type = type(e).__name__
    #     if PortAudioError and isinstance(e, PortAudioError):
    #         logger.warning(f"Ignoring local microphone error (agent uses room audio only): {e}")
    #         # Session should still work with room audio, continue
    #     elif "PortAudio" in error_type or "sounddevice" in str(e).lower():
    #         logger.warning(f"Ignoring local microphone error (agent uses room audio only): {e}")
    #         # Session should still work with room audio, continue
    #     else:
    #         raise

    # logger.info("AgentSession started with sampling agent. Waiting for 'done sampling' or stop command...")
    
    # # Wait for either handoff or stop signal
    # # handoff_task = asyncio.create_task(handoff_flag.wait())
    # # stop_task = asyncio.create_task(stop_flag.wait())
    
    # # done, pending = await asyncio.wait(
    # #     [handoff_task, stop_task],
    # #     return_when=asyncio.FIRST_COMPLETED
    # # )
    
    # # Cancel the pending task
    # for task in pending:
    #     task.cancel()
    #     try:
    #         await task
    #     except asyncio.CancelledError:
    #         pass
    
    # if handoff_flag.is_set():
    #     logger.info("🔄 Handoff flag triggered - switching to DiarizationAgent...")
    #     try:
    #         # Close the current session
    #         await session.aclose()
    #         logger.info("Closed sampling session")
            
    #         # Create a new session with DiarizationAgent
    #         new_session = AgentSession(
    #             llm="google/gemini-2.5-flash",
    #             stt=sm_stt,
    #             vad=silero.VAD.load(),
    #             turn_detection=MultilingualModel(),
    #         )
            
    #         @new_session.on("close")
    #         def _on_close_new(ev=None):
    #             async def _close():
    #                 logger.info("DiarizationAgent session closed")
    #             asyncio.create_task(_close())
            
    #         # Note: Agent only uses room audio input, local microphone errors can be ignored
    #         try:
    #             await new_session.start(
    #                 room=ctx.room,
    #                 agent=DiarizationAgent(ctx),
    #                 room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()),
    #             )
    #         except Exception as e:
    #             # Ignore PortAudio errors for local microphone - agent uses room audio only
    #             error_type = type(e).__name__
    #             if PortAudioError and isinstance(e, PortAudioError):
    #                 logger.warning(f"Ignoring local microphone error (agent uses room audio only): {e}")
    #                 # Session should still work with room audio, continue
    #             elif "PortAudio" in error_type or "sounddevice" in str(e).lower():
    #                 logger.warning(f"Ignoring local microphone error (agent uses room audio only): {e}")
    #                 # Session should still work with room audio, continue
    #             else:
    #                 raise
            
    #         logger.info("✅ Successfully handed off to DiarizationAgent")
            
    #         # Now wait for stop signal
    #         try:
    #             await stop_flag.wait()
    #             logger.info("Stop flag triggered - shutting down session")
    #         finally:
    #             logger.info("Closing diarization session and shutting down...")
    #             await new_session.aclose()
    #             ctx.shutdown(reason="Session ended")
    #     except Exception as e:
    #         logger.error(f"❌ Error during handoff: {e}")
    #         await session.aclose()
    #         ctx.shutdown(reason=f"Handoff failed: {e}")
    # else:
    #     # Stop flag was triggered
    #     logger.info("Stop flag triggered - shutting down session")
    #     try:
    #         await session.aclose()
    #     finally:
    #         ctx.shutdown(reason="Session ended")
    

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
