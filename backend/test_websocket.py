"""
Test script to verify WebSocket endpoint is working
"""
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws/transcripts"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected successfully!")
            
            # Send a test message
            await websocket.send("test message")
            print("Sent: test message")
            
            # Wait for response
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received: {response}")
                data = json.loads(response)
                print(f"Parsed: {data}")
            except asyncio.TimeoutError:
                print("⚠️  No response received (timeout)")
            
            print("✅ WebSocket test completed successfully!")
            
    except ConnectionRefusedError:
        print("❌ Connection refused - API server is not running!")
        print("   Start it with: python start_server.py")
    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"   Type: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_websocket())

