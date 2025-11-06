import os
import logging
import time
from collections.abc import AsyncIterable
from typing import List, Dict, Tuple, Optional
from collections import deque

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

# ------------------------------------------------------------
# Transcript state
# ------------------------------------------------------------
transcripts: List[Tuple[str, str]] = []                  # (Speaker N, text)
speaker_label_map: Dict[str, str] = {}                   # sm speaker_id -> Speaker N
next_speaker_num: int = 1
recent_turns: deque = deque(maxlen=10)                   # optional

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
    def __init__(self, room: rtc.Room | None = None) -> None:
        super().__init__(
            instructions=(
                "You are a silent transcription agent. "
                "Do not respond or speak; only transcribe user speech with speaker labels."
            ),
        )
        self.room = room
        self.last_turn_time: float = 0.0

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

                    # Debug: show raw type and speaker id coming from STT
                    ev_type = getattr(ev, "type", None)
                    ev_type_name = getattr(ev_type, "name", str(ev_type))
                    logger.debug(f"SpeechEvent type={ev_type_name}, speaker_id={spk}, text='{text}'")

                    if text.strip():
                        # If event is final (FINAL_TRANSCRIPT), persist it; else, show interim
                        if ev_type_name == "FINAL_TRANSCRIPT":
                            transcripts.append((label, text))
                            print(f"[Final] {label}: {text}")
                            lines = [f"{sp}: {t}" for sp, t in transcripts]
                            print("\n📝 Full Transcript so far:\n" + "\n".join(lines) + "\n")
                        else:
                            print(f"[Interim] {label}: {text}")

                # always yield back into pipeline
                yield ev

        return _transcribe()

    async def on_user_turn_completed(
        self, turn_ctx: agents.ChatContext, new_message: agents.ChatMessage,
    ) -> None:
        """
        Optional hook; diarization and persistence are handled inside stt_node.
        """
        self.last_turn_time = time.time()

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
        llm="google/gemini-2.5-flash",   # pipeline requirement; agent stays silent
        stt=sm_stt,
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    await session.start(
        room=ctx.room,
        agent=DiarizationAgent(room=ctx.room),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
