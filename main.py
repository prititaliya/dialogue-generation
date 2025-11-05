import logging
from collections.abc import AsyncIterable
from typing import List

from livekit import rtc

from dotenv import load_dotenv

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, ModelSettings
from livekit.agents import stt
from livekit.plugins import noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv(".env.local")

logger = logging.getLogger(__name__)

# Store all transcripts
transcripts: List[str] = []


class TranscriptionAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a silent transcription agent. You only record what the user says.
            Do not respond, do not speak, just transcribe.""",
        )
    
    def stt_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncIterable[stt.SpeechEvent | str]:
        """Override STT node to capture transcripts as they come in."""
        async def _transcribe():
            async for speech_event in Agent.default.stt_node(self, audio, model_settings):
                if isinstance(speech_event, stt.SpeechEvent):
                    if speech_event.alternatives:
                        text = speech_event.alternatives[0].text
                        if text.strip():
                            logger.info(f"[Interim Transcript]: {text}")
                            print(f"[Interim]: {text}")
                yield speech_event
        
        return _transcribe()
    
    async def on_user_turn_completed(
        self, turn_ctx: agents.ChatContext, new_message: agents.ChatMessage,
    ) -> None:
        """Called when user completes a turn (final transcript after sentence)."""
        if new_message.content:
            said_text = ""
            for item in new_message.content:
                said_text += item.strip()
            if said_text:
                transcripts.append(said_text)
                logger.info(f"[Final Transcript]: {said_text}")
                print(f"[Final]: {said_text}")
                print(f"\n📝 Full Transcript so far:\n{chr(10).join(transcripts)}\n")
        
    def llm_node(
        self, chat_ctx: agents.ChatContext, tools: list, model_settings: ModelSettings
    ) -> AsyncIterable[str]:
        """Override LLM node to prevent any responses - agent stays silent."""
        async def _silent():
            # Return empty generator - agent won't speak
            if False:
                yield ""
        
        return _silent()
    
    def tts_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncIterable[rtc.AudioFrame]:
        """Override TTS node to prevent any audio output - agent stays silent."""
        async def _silent():
            # Don't generate any audio - consume input but yield nothing
            async for _ in text:
                pass
            if False:
                yield rtc.AudioFrame()
        
        return _silent()


async def entrypoint(ctx: agents.JobContext):
    # Need minimal LLM for turn detection, but TTS disabled
    session = AgentSession(
        llm="google/gemini-2.5-flash",  # Minimal LLM for turn detection
        stt="assemblyai/universal-streaming:en",
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    await session.start(
        room=ctx.room,
        agent=TranscriptionAgent(),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(), 
        ),
    )
    
    # Session will run until room disconnects
    # Transcripts are printed in real-time as user speaks
    # Final transcript summary will be available in the `transcripts` list

if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
