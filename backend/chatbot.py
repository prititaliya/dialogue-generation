from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field   
from langchain_redis import RedisVectorStore
from dotenv import load_dotenv
from pathlib import Path
import os
import redis  
import json
# from langgraph.graph import StateGraph, START, END  # Commented out - not used by new async functions
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage, SystemMessage
import typing
import asyncio

class State(BaseModel):
    transcript: str = ""
    meeting_id: str = ""
    meeting_name: str = ""
    user_id: int = ""
    timestamp: int = ""
    speakers: list[str] = []
    chat_history: list[BaseMessage] = []
    context: str = ""
    summary: str = ""
    question: str = ""
    answer: str = ""

env_path = Path(__file__).parent / ".env.local"
load_dotenv(env_path)

redis_url = os.getenv("REDIS_URL")

vector_store = RedisVectorStore(
    redis_url=redis_url,
    # index_name="transcripts:index",
    embeddings=OpenAIEmbeddings(),
)
def get_transcripts_for_user(user_id: int):
    redis_client = redis.from_url(os.getenv("REDIS_URL"), decode_responses=False)
    keys = redis_client.keys("transcript:*")

    transcripts = []
    for key in keys:

        data = redis_client.hgetall(key)
        stored_by_user_id = data.get(b'user_id')
        stored_by_user_id = int(stored_by_user_id.decode('utf-8'))
        if stored_by_user_id == user_id:
            transcripts.append({
                'meeting_id': data.get(b'meeting_id', b'').decode('utf-8'),
                'meeting_name': data.get(b'meeting_name', b'').decode('utf-8'),
                'user_id': user_id,
                'timestamp': int(data.get(b'timestamp', b'0').decode('utf-8')),
                'speakers': json.loads(data.get(b'speakers', b'[]').decode('utf-8')),
                'transcript_text': data.get(b'transcript_text', b'').decode('utf-8'),
            })

    return transcripts

def get_transcript_for_meeting(meeting_id: str):
    redis_client = redis.from_url(os.getenv("REDIS_URL"), decode_responses=False)
    data = redis_client.hgetall(f"transcript:{meeting_id}")
    return data.get(b'transcript_text', b'').decode('utf-8')



def get_chatbot_graph(state: State):
    llm=ChatOpenAI(model="gpt-4o-mini", temperature=0)
    prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful assistant that answers questions strictly based on the provided transcript.

    Guidelines:
    - Only answer questions using information explicitly stated in the transcript
    - If the answer cannot be found in the transcript, respond with "I don't know" or "This information is not available in the transcript"
    - Do not make assumptions or provide information from outside the transcript
    - Do not suggest follow-up questions or offer to expand on topics
    - Be concise and direct in your responses
    - Use exact quotes from the transcript when possible to support your answers"""),
        ("user", "Transcript:\n{transcript}"),
        ("user", "Summary of the transcript: {summary}"),
        ("user", "Chat history: {chat_history}"),
        ("user", "Question: {question}")
    ])

    final_prompt=prompt.format(transcript=state.transcript, summary=state.summary, chat_history=state.chat_history, question=state.question)
    response=llm.invoke(final_prompt)
    print(response.content)
    return {"answer": response.content}

def get_summary_graph(state: State):
    llm=ChatOpenAI(model="gpt-4o-mini", temperature=0)
    prompt=ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant that can summarize the transcript."),
        ("user", "The transcript is: {transcript}"),
    ])
    response=llm.invoke(prompt.invoke(prompt.format(transcript=state.transcript)))
    return {"summary": response.content}

def maintain_chat_history_graph(state: State):
    history=state.chat_history
    history.append(HumanMessage(content=state.question))
    history.append(AIMessage(content=state.answer))
    # history.question=""
    # history.answer=""
    return {"chat_history": history}


def condtion_chatbot_node(state: State):
    if state.question.lower() == "exit":
        return "exit"
    else:
        return "chatbot"
def get_input_graph(state: State):
    return {"question": input("Enter a question: ")}

# Old graph code - commented out as it's not compatible with current langgraph version
# and not used by the new async API functions
# graph=StateGraph(State)
# graph.add_node("chatbot", get_chatbot_graph)
# graph.add_node("summary", get_summary_graph)
# graph.add_node("maintain_chat_history", maintain_chat_history_graph)
# graph.add_node("input", get_input_graph)
# graph.add_node("condition_chatbot", condtion_chatbot_node)
# graph.add_edge(START, "summary")
# 
# graph.add_edge("summary", "input")
# graph.add_conditional_edges("input", condtion_chatbot_node,{'chatbot': 'chatbot', 'exit': END})
# graph.add_edge("chatbot", "maintain_chat_history")
# graph.add_edge("maintain_chat_history", "input")
# 
# 
# app=graph.compile()
# init_state={"transcript": get_transcript_for_meeting("1_kdiso_1763149743"), "chat_history": [HumanMessage(content="Hello, how are you?")]}
# 
# response=app.invoke(init_state)

 
def init_chatbot(id:str):
    """Legacy function - kept for backward compatibility but not actively used"""
    # This function would need to be updated if the old graph code is re-enabled
    pass


async def generate_summary(transcript_text: str) -> str:
    """Generate a summary for the given transcript text"""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant that can summarize the transcript. Provide a concise summary of the key points discussed."),
        ("user", "The transcript is: {transcript}"),
    ])
    
    formatted_prompt = prompt.format_messages(transcript=transcript_text)
    response = await llm.ainvoke(formatted_prompt)
    return response.content


async def stream_chat_response(
    transcript_text: str,
    summary: str,
    chat_history: list[BaseMessage],
    question: str,
    meeting_name: str = ""
):
    """Stream chat response based on transcript"""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, streaming=True)
    
    # Format chat history for the prompt
    chat_history_str = ""
    if chat_history:
        for msg in chat_history:
            if isinstance(msg, HumanMessage):
                chat_history_str += f"User: {msg.content}\n"
            elif isinstance(msg, AIMessage):
                chat_history_str += f"Assistant: {msg.content}\n"
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a helpful assistant that answers questions strictly based on the provided transcript.

    Guidelines:
    - Only answer questions using information explicitly stated in the transcript
    - If the answer cannot be found in the transcript, respond with "I don't know" or "This information is not available in the transcript"
    - Do not make assumptions or provide information from outside the transcript
    - Do not suggest follow-up questions or offer to expand on topics
    - Be concise and direct in your responses
    - Use exact quotes from the transcript when possible to support your answers"""),
        ("user", "Transcript:\n{transcript}"),
        ("user", "Summary of the transcript: {summary}"),
        ("user", "Chat history:\n{chat_history}"),
        ("user", "Question: {question}")
    ])
    
    formatted_prompt = prompt.format_messages(
        transcript=transcript_text,
        summary=summary,
        chat_history=chat_history_str if chat_history_str else "No previous conversation.",
        question=question
    )
    
    async for chunk in llm.astream(formatted_prompt):
        if chunk.content:
            yield chunk.content

