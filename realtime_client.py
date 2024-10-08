import websockets
import json
import base64
import asyncio
from typing import Optional, Callable, List, Dict, Any
from enum import Enum
from pydub import AudioSegment
import io


class TurnDetectionMode(Enum):
    SERVER_VAD = "server_vad"
    MANUAL = "manual"

class RealtimeClient:
    def __init__(
        self, 
        api_key: str,
        model: str = "gpt-4o-realtime-preview-2024-10-01",
        voice: str = "alloy",
        instructions: str = "You are a helpful assistant",
        on_text_delta: Optional[Callable[[str], None]] = None,
        on_audio_delta: Optional[Callable[[bytes], None]] = None,
        on_function_call: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.ws = None
        self.on_text_delta = on_text_delta
        self.on_audio_delta = on_audio_delta
        self.on_function_call = on_function_call
        self.instructions = instructions
        self.base_url = "wss://api.openai.com/v1/realtime"
        self.conversation_history = []
        
    async def connect(self) -> None:
        """Establish WebSocket connection with the Realtime API."""
        url = f"{self.base_url}?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        self.ws = await websockets.connect(url, extra_headers=headers)
        
        # Set up default session configuration
        await self.update_session({
            "modalities": ["text", "audio"],
            "instructions": self.instructions,
            "voice": self.voice,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": "whisper-1"
            },
            "tools": [],
            "tool_choice": "auto",
            "temperature": 0.8,
        }
    )

    async def update_session(self, config: Dict[str, Any]) -> None:
        """Update session configuration."""
        event = {
            "type": "session.update",
            "session": config
        }
        await self.ws.send(json.dumps(event))

    async def send_text(self, text: str) -> None:
        """Send text message to the API."""
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": text
                }]
            }
        }
        await self.ws.send(json.dumps(event))
        await self.create_response()

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Send audio data to the API."""
        # Convert audio to required format (24kHz, mono, PCM16)
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
        audio = audio.set_frame_rate(24000).set_channels(1).set_sample_width(2)
        pcm_data = base64.b64encode(audio.raw_data).decode()
        
        # Append audio to buffer
        append_event = {
            "type": "input_audio_buffer.append",
            "audio": pcm_data
        }
        await self.ws.send(json.dumps(append_event))
        
        # Commit the buffer
        commit_event = {
            "type": "input_audio_buffer.commit"
        }
        await self.ws.send(json.dumps(commit_event))
        
        # In manual mode, we need to explicitly request a response
        await self.create_response()

    async def create_response(self, functions: Optional[List[Dict[str, Any]]] = None) -> None:
        """Request a response from the API."""
        event = {
            "type": "response.create",
            "response": {
                "modalities": ["text", "audio"]
            }
        }
        if functions:
            event["response"]["tools"] = functions
            
        await self.ws.send(json.dumps(event))

    async def send_function_result(self, function_call_id: str, result: Any) -> None:
        """Send function call result back to the API."""
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "function_call_id": function_call_id,
                "content": result
            }
        }
        await self.ws.send(json.dumps(event))

    async def cancel_response(self) -> None:
        """Cancel the current response."""
        event = {
            "type": "response.cancel"
        }
        await self.ws.send(json.dumps(event))

    async def handle_messages(self) -> None:
        """Main message handling loop."""
        try:
            async for message in self.ws:
                event = json.loads(message)
                event_type = event.get("type")
                
                print(f"Event: {event_type}")
                
                if event_type == "error":
                    print(f"Error: {event['error']}")
                    continue
                    
                elif event_type == "response.text.delta":
                    if self.on_text_delta:
                        self.on_text_delta(event["delta"])
                        
                elif event_type == "response.audio.delta":
                    if self.on_audio_delta:
                        audio_bytes = base64.b64decode(event["delta"])
                        self.on_audio_delta(audio_bytes)
                        
                elif event_type == "response.function_call_arguments.done":
                    if self.on_function_call:
                        self.on_function_call({
                            "name": event["name"],
                            "arguments": event["arguments"]
                        })

        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")
        except Exception as e:
            print(f"Error in message handling: {str(e)}")

    async def close(self) -> None:
        """Close the WebSocket connection."""
        if self.ws:
            await self.ws.close()

# Example usage:
async def main():
    def on_text(text: str):
        print(f"Text received: {text}")
        
    def on_audio(audio: bytes):
        # Handle audio chunks (e.g., play them or save to file)
        pass
        
    def on_function_call(func_data: Dict[str, Any]):
        print(f"Function call: {func_data}")
    
    client = RealtimeClient(
        api_key="your-api-key",
        on_text_delta=on_text,
        on_audio_delta=on_audio,
        on_function_call=on_function_call
    )
    
    try:
        await client.connect()
        
        # Start message handling in the background
        message_handler = asyncio.create_task(client.handle_messages())
        
        # Send a text message
        await client.send_text("Hello! How are you today?")
        
        # Wait for a while to receive responses
        await asyncio.sleep(5)
        
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
