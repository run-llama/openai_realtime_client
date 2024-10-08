import asyncio
import pyaudio
import wave
import queue
import io
import os
from typing import Optional

from pydub import AudioSegment
from pynput import keyboard
import threading

from realtime_client import RealtimeClient

class AudioHandler:
    def __init__(self):
        # Audio parameters
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 24000
        self.chunk = 1024

        # Recording params
        self.audio = pyaudio.PyAudio()
        self.recording_stream: Optional[pyaudio.Stream] = None
        self.recording_thread = None
        self.recording = False

        # Playback params
        self.playback_stream = None
        self.playback_buffer = queue.Queue(maxsize=20)
        self.playback_thread = None
        self.stop_playback = False

    def start_recording(self) -> bytes:
        """Start recording audio from microphone and return bytes"""
        if self.recording:
            return b''
        
        self.recording = True
        self.recording_stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        
        print("\nRecording... Press 'space' to stop.")
        
        self.frames = []
        self.recording_thread = threading.Thread(target=self._record)
        self.recording_thread.start()
        
        return b''  # Return empty bytes, we'll send audio later

    def _record(self):
        while self.recording:
            try:
                data = self.recording_stream.read(self.chunk)
                self.frames.append(data)
            except Exception as e:
                print(f"Error recording: {e}")
                break

    def stop_recording(self) -> bytes:
        """Stop recording and return the recorded audio as bytes"""
        if not self.recording:
            return b''
        
        self.recording = False
        if self.recording_thread:
            self.recording_thread.join()
        
        # Clean up recording stream
        if self.recording_stream:
            self.recording_stream.stop_stream()
            self.recording_stream.close()
            self.recording_stream = None
        
        # Convert frames to WAV format in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format))
            wf.setframerate(self.rate)
            wf.writeframes(b''.join(self.frames))
        
        # Get the WAV data
        wav_buffer.seek(0)
        return wav_buffer.read()

    def play_audio(self, audio_data: bytes):
        """Add audio data to the buffer"""
        try:
            self.playback_buffer.put_nowait(audio_data)
        except queue.Full:
            # If the buffer is full, remove the oldest chunk and add the new one
            self.playback_buffer.get_nowait()
            self.playback_buffer.put_nowait(audio_data)
        
        if not self.playback_thread or not self.playback_thread.is_alive():
            self.stop_playback = False
            self.playback_thread = threading.Thread(target=self._continuous_playback)
            self.playback_thread.start()

    def _continuous_playback(self):
        """Continuously play audio from the buffer"""
        self.playback_stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            output=True,
            frames_per_buffer=self.chunk
        )

        while not self.stop_playback:
            try:
                audio_chunk = self.playback_buffer.get(timeout=0.1)
                self._play_audio_chunk(audio_chunk)
            except queue.Empty:
                continue

        if self.playback_stream:
            self.playback_stream.stop_stream()
            self.playback_stream.close()
            self.playback_stream = None

    def _play_audio_chunk(self, audio_chunk):
        try:
            # Convert the audio chunk to the correct format
            audio_segment = AudioSegment(
                audio_chunk,
                sample_width=2,
                frame_rate=24000,
                channels=1
            )
            
            # Ensure the audio is in the correct format for playback
            audio_data = audio_segment.raw_data
            
            # Play the audio chunk
            self.playback_stream.write(audio_data)
        except Exception as e:
            print(f"Error playing audio chunk: {e}")

    def cleanup(self):
        """Clean up audio resources"""
        self.stop_playback = True
        if self.playback_thread:
            self.playback_thread.join()

        self.recording = False
        if self.recording_stream:
            self.recording_stream.stop_stream()
            self.recording_stream.close()

        self.audio.terminate()

class InputHandler:
    def __init__(self):
        self.text_input = ""
        self.text_ready = asyncio.Event()
        self.command_queue = asyncio.Queue()
        self.loop = None

    def on_press(self, key):
        try:
            if key == keyboard.Key.space:
                self.loop.call_soon_threadsafe(
                    self.command_queue.put_nowait, ('space', None)
                )
            elif key == keyboard.Key.enter:
                self.loop.call_soon_threadsafe(
                    self.command_queue.put_nowait, ('enter', self.text_input)
                )
                self.text_input = ""
            elif key == keyboard.KeyCode.from_char('r'):
                self.loop.call_soon_threadsafe(
                    self.command_queue.put_nowait, ('r', None)
                )
            elif key == keyboard.KeyCode.from_char('q'):
                self.loop.call_soon_threadsafe(
                    self.command_queue.put_nowait, ('q', None)
                )
            elif hasattr(key, 'char'):
                if key == keyboard.Key.backspace:
                    self.text_input = self.text_input[:-1]
                else:
                    self.text_input += key.char
        except AttributeError:
            pass

async def main():
    # Initialize handlers
    audio_handler = AudioHandler()
    input_handler = InputHandler()
    input_handler.loop = asyncio.get_running_loop()
    
    # Initialize the realtime client
    client = RealtimeClient(
        api_key=os.environ.get("OPENAI_API_KEY"),
        on_text_delta=lambda text: print(f"\nAssistant: {text}", end="", flush=True),
        on_audio_delta=lambda audio: audio_handler.play_audio(audio)
    )
    
    # Start keyboard listener in a separate thread
    listener = keyboard.Listener(on_press=input_handler.on_press)
    listener.start()
    
    try:
        # Connect to the API
        await client.connect()
        
        # Start message handling in the background
        message_handler = asyncio.create_task(client.handle_messages())
        
        print("Connected to OpenAI Realtime API!")
        print("Commands:")
        print("- Type your message and press Enter to send text")
        print("- Press 'r' to start recording audio")
        print("- Press 'space' to stop recording")
        print("- Press 'q' to quit")
        print("")        
 
        while True:
            # Wait for commands from the input handler
            command, data = await input_handler.command_queue.get()
            
            if command == 'q':
                break
            elif command == 'r':
                # Start recording
                audio_handler.start_recording()
            elif command == 'space':
                print("[About to stop recording]")
                if audio_handler.recording:
                    # Stop recording and get audio data
                    audio_data = audio_handler.stop_recording()
                    print("[Recording stopped]")
                    if audio_data:
                        await client.send_audio(audio_data)
                        print("[Audio sent]")
            elif command == 'enter' and data:
                # Send text message
                await client.send_text(data)

            await asyncio.sleep(0.01) 
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Clean up
        listener.stop()
        audio_handler.cleanup()
        await client.close()

if __name__ == "__main__":
    # Install required packages:
    # pip install pyaudio pynput pydub websockets

    print("Starting Realtime API CLI...")
    asyncio.run(main())
