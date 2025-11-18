import os
import logging
import asyncio
from collections.abc import AsyncIterable
from typing import List, Dict, Tuple, Optional

from dotenv import load_dotenv
from livekit import rtc, agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ModelSettings
from livekit.agents import stt
from livekit.plugins import noise_cancellation, silero, speechmatics
from livekit.plugins.turn_detector.multilingual import MultilingualModel

try:
    from sounddevice import PortAudioError
except ImportError:
    PortAudioError = None

stop_flag = asyncio.Event()
load_dotenv(".env.local")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diarizer")

logging.getLogger("livekit.agents.voice.audio_recognition").setLevel(logging.ERROR)
logging.getLogger("livekit.plugins.turn_detector").setLevel(logging.ERROR)
logging.getLogger("livekit.agents").setLevel(logging.ERROR)
logging.getLogger("livekit.agents.voice.room_io._output").setLevel(logging.ERROR)
logging.getLogger("livekit.rtc.participant").setLevel(logging.ERROR)

transcripts: List[Tuple[str, str]] = []
speaker_label_map: Dict[str, str] = {}
next_speaker_num: int = 1

_transcript_manager = None
_update_transcript_incremental_fn = None

def _get_transcript_manager():
    global _transcript_manager
    if _transcript_manager is None:
        from api_server import get_transcript_manager
        _transcript_manager = get_transcript_manager()
    return _transcript_manager

def _get_update_transcript_incremental():
    global _update_transcript_incremental_fn
    if _update_transcript_incremental_fn is None:
        from api_server import update_transcript_incremental
        _update_transcript_incremental_fn = update_transcript_incremental
    return _update_transcript_incremental_fn

def label_for_speaker_id(speaker_id: Optional[str]) -> str:
    global next_speaker_num
    if not speaker_id:
        speaker_id = "unknown"
    if speaker_id not in speaker_label_map:
        speaker_label_map[speaker_id] = f"Speaker {next_speaker_num}"
        next_speaker_num += 1
    return speaker_label_map[speaker_id]


class DiarizationAgent(Agent):
    def __init__(self, ctx: agents.JobContext) -> None:
        super().__init__(
            instructions=(
                "You are a silent transcription agent. "
                "Do not respond or speak; only transcribe user speech with speaker labels."
            )
        )
        self.ctx = ctx

    def stt_node(self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings) -> AsyncIterable[stt.SpeechEvent | str]:
        async def _transcribe():
            async for ev in Agent.default.stt_node(self, audio, model_settings):
                if isinstance(ev, stt.SpeechEvent) and ev.alternatives:
                    alt = ev.alternatives[0]
                    text = alt.text or ""
                    spk = getattr(alt, "speaker_id", None) or getattr(alt, "speaker", None) or "speaker_1"
                    label = label_for_speaker_id(spk)
                    
                    ev_type = getattr(ev, "type", None)
                    ev_type_name = getattr(ev_type, "name", str(ev_type)) if ev_type else None
                    is_final = ev_type_name and "FINAL" in ev_type_name.upper()
                    
                    if is_final and len(text.lower().strip()) >= 10:
                        text_lower = " ".join(text.lower().strip().split())
                        if "stop recording" in text_lower or "stop the recording" in text_lower:
                            room_name = self.ctx.room.name if self.ctx.room else "Meeting"
                            with open("transcript.txt", "w") as f:
                                for sp, t in transcripts:
                                    f.write(f"{sp}: {t}\n")
                                f.write(f"\nStop command detected: {text}\n")
                            
                            try:
                                import aiohttp
                                async with aiohttp.ClientSession() as session:
                                    async with session.post(
                                        f"{os.getenv('API_SERVER_URL', 'http://localhost:8000')}/transcripts/update",
                                        json={"transcripts": transcripts, "room_name": room_name}
                                    ) as resp:
                                        if resp.status == 200:
                                            await resp.json()
                            except Exception as e:
                                logger.error(f"Error updating API server: {e}")
                            
                            asyncio.create_task(_get_transcript_manager().send_complete_transcript(room_name, transcripts))
                            stop_flag.set()
                            print("\n🛑 STOP COMMAND DETECTED! Stopping recording...\n")

                    text_stripped = text.strip()
                    if text_stripped:
                        room_name = self.ctx.room.name if self.ctx.room else "Meeting"
                        
                        if is_final:
                            updated = False
                            if transcripts:
                                last_speaker, last_text = transcripts[-1]
                                if label == last_speaker and last_text == text_stripped:
                                    continue
                                elif label == last_speaker and last_text in text_stripped and len(text_stripped) > len(last_text):
                                    transcripts[-1] = (label, text_stripped)
                                    updated = True
                                elif any(e[0] == label and e[1] == text_stripped for e in transcripts[-20:]):
                                    continue
                            
                            if not updated:
                                transcripts.append((label, text_stripped))
                            
                            print(f"[Final] {label}: {text}")
                            print(f"\n📝 Full Transcript so far:\n" + "\n".join([f"{sp}: {t}" for sp, t in transcripts]) + "\n")
                            
                            try:
                                _get_update_transcript_incremental()(room_name, label, text_stripped, is_final=True)
                            except Exception as e:
                                logger.error(f"Error updating transcript: {e}")
                            
                            asyncio.create_task(_get_transcript_manager().update_transcripts(label, text_stripped, is_final=True))
                            
                            try:
                                import aiohttp
                                async def sync():
                                    try:
                                        async with aiohttp.ClientSession() as s:
                                            async with s.post(f"{os.getenv('API_SERVER_URL', 'http://localhost:8000')}/transcripts/update",
                                                json={"transcripts": transcripts, "room_name": room_name}) as r:
                                                pass
                                    except: pass
                                asyncio.create_task(sync())
                            except: pass
                        else:
                            print(f"[Interim] {label}: {text}")
                            try:
                                _get_update_transcript_incremental()(room_name, label, text_stripped, is_final=False)
                            except Exception as e:
                                logger.error(f"Error updating transcript (interim): {e}")
                            asyncio.create_task(_get_transcript_manager().update_transcripts(label, text_stripped, is_final=False))

                yield ev

        return _transcribe()

    def llm_node(self, chat_ctx, tools, model_settings):
        async def _silent():
            if False: yield ""
        return _silent()

    def tts_node(self, text, model_settings):
        async def _silent():
            async for _ in text: pass
            if False: yield rtc.AudioFrame()
        return _silent()

async def entrypoint(ctx: agents.JobContext):
    stop_flag.clear()
    
    sm_api_key = os.environ.get("SPEECHMATICS_API_KEY", "")
    if not sm_api_key:
        raise RuntimeError("SPEECHMATICS_API_KEY is required in environment")
    
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
    
    try:
        await session.start(
            room=ctx.room,
            agent=DiarizationAgent(ctx),
            room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()),
        )
    except Exception as e:
        if PortAudioError and isinstance(e, PortAudioError) or "PortAudio" in type(e).__name__ or "sounddevice" in str(e).lower():
            logger.warning(f"Ignoring local microphone error: {e}")
        else:
            raise


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
