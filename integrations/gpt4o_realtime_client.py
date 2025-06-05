#!/usr/bin/env python3
"""
GPT-4o Realtime API WebSocket Client with Cost Controls
"""
import asyncio
import json
import uuid
import time
import base64
import websockets
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    print("Warning: PyAudio not available. Audio features disabled.")
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import logging
from .realtime_cost_tracker import get_realtime_tracker
from .openai_logger import get_openai_logger

@dataclass
class AudioConfig:
    """Audio configuration for realtime streaming"""
    sample_rate: int = 24000
    channels: int = 1
    chunk_size: int = 1024
    format: int = 16 if not PYAUDIO_AVAILABLE else pyaudio.paInt16

class GPT4oRealtimeClient:
    """GPT-4o Realtime API client with cost controls and session management"""
    
    def __init__(self, api_key: str, session_id: Optional[str] = None):
        self.api_key = api_key
        self.session_id = session_id or str(uuid.uuid4())
        
        # Cost tracking
        self.cost_tracker = get_realtime_tracker()
        self.logger = get_openai_logger()
        
        # WebSocket connection
        self.websocket = None
        self.connected = False
        
        # Audio configuration
        self.audio_config = AudioConfig()
        self.audio = None
        self.input_stream = None
        self.output_stream = None
        
        # Event handlers
        self.event_handlers = {}
        
        # Session state
        self.session_active = False
        self.audio_input_enabled = False
        self.conversation_id = None
        
        # Cost monitoring
        self.cost_check_interval = 5.0  # Check costs every 5 seconds
        self.last_cost_check = time.time()
        
        # Audio tracking
        self.audio_start_time = None
        self.current_audio_duration = 0.0
        
        self.api_logger = self.logger.api_logger
        self.api_logger.info(f"GPT-4o Realtime client initialized for session: {self.session_id}")
    
    def on(self, event_type: str, handler: Callable):
        """Register an event handler"""
        self.event_handlers[event_type] = handler
    
    def emit(self, event_type: str, data: Any = None):
        """Emit an event to registered handlers"""
        if event_type in self.event_handlers:
            try:
                self.event_handlers[event_type](data)
            except Exception as e:
                self.api_logger.error(f"Error in event handler for {event_type}: {e}")
    
    async def connect(self) -> Dict[str, Any]:
        """Connect to GPT-4o Realtime API"""
        # Check if session can start
        permission = self.cost_tracker.can_start_session()
        if not permission["allowed"]:
            self.emit("error", {"type": "cost_limit", "message": permission["reason"]})
            return permission
        
        # Start session tracking
        session_result = self.cost_tracker.start_session(self.session_id)
        if not session_result.get("session_started"):
            self.emit("error", {"type": "session_start_failed", "message": session_result})
            return session_result
        
        try:
            # Connect to OpenAI Realtime API
            url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
            
            self.websocket = await websockets.connect(url, additional_headers=headers)
            self.connected = True
            
            # Initialize audio (if available)
            if PYAUDIO_AVAILABLE:
                self.audio = pyaudio.PyAudio()
            else:
                self.audio = None
            
            # Send session configuration
            await self._send_session_update()
            
            # Start message handling
            asyncio.create_task(self._handle_messages())
            
            # Start cost monitoring
            asyncio.create_task(self._monitor_costs())
            
            self.emit("connected", {"session_id": self.session_id, "warnings": session_result.get("warnings", [])})
            
            return {"connected": True, "session_id": self.session_id}
            
        except Exception as e:
            self.api_logger.error(f"Failed to connect to GPT-4o Realtime API: {e}")
            self.emit("error", {"type": "connection_failed", "message": str(e)})
            return {"connected": False, "error": str(e)}
    
    async def _send_session_update(self):
        """Send session configuration to API"""
        session_config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": "You are Eva, a helpful AI assistant. Respond naturally and concisely.",
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500
                },
                "tools": [],
                "tool_choice": "none",
                "temperature": 0.8,
                "max_response_output_tokens": "inf"
            }
        }
        
        await self.websocket.send(json.dumps(session_config))
    
    async def _handle_messages(self):
        """Handle incoming WebSocket messages"""
        try:
            async for message in self.websocket:
                data = json.loads(message)
                await self._process_message(data)
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
            self.emit("disconnected", {"reason": "Connection closed"})
        except Exception as e:
            self.api_logger.error(f"Error handling messages: {e}")
            self.emit("error", {"type": "message_handling", "message": str(e)})
    
    async def _process_message(self, data: Dict[str, Any]):
        """Process incoming message from API"""
        msg_type = data.get("type", "")
        
        if msg_type == "session.created":
            self.session_active = True
            self.conversation_id = data.get("session", {}).get("id")
            self.emit("session_created", data)
            
        elif msg_type == "input_audio_buffer.speech_started":
            self.audio_start_time = time.time()
            self.emit("speech_started", data)
            
        elif msg_type == "input_audio_buffer.speech_stopped":
            if self.audio_start_time:
                duration = time.time() - self.audio_start_time
                self._track_audio_usage("input", duration)
                self.audio_start_time = None
            self.emit("speech_stopped", data)
            
        elif msg_type == "conversation.item.input_audio_transcription.completed":
            self.emit("transcription", {
                "text": data.get("transcript", ""),
                "item_id": data.get("item_id")
            })
            
        elif msg_type == "response.audio.delta":
            # Track output audio
            audio_data = data.get("delta", "")
            if audio_data:
                # Estimate duration from audio data size
                audio_bytes = base64.b64decode(audio_data)
                duration = len(audio_bytes) / (self.audio_config.sample_rate * 2)  # 16-bit PCM
                self._track_audio_usage("output", duration)
                
                # Play audio if output stream is available
                if self.output_stream:
                    self.output_stream.write(audio_bytes)
                    
                self.emit("audio_delta", {"audio": audio_data, "duration": duration})
            
        elif msg_type == "response.text.delta":
            self.emit("text_delta", {"text": data.get("delta", "")})
            
        elif msg_type == "response.done":
            self.emit("response_done", data)
            
        elif msg_type == "error":
            self.emit("error", {"type": "api_error", "message": data})
            
        else:
            # Log unknown message types for debugging
            self.api_logger.debug(f"Unknown message type: {msg_type}")
    
    def _track_audio_usage(self, audio_type: str, duration: float):
        """Track audio usage and check cost limits"""
        try:
            result = self.cost_tracker.track_audio_usage(self.session_id, audio_type, duration)
            
            # Check for warnings or termination
            if result.get("warnings"):
                for warning in result["warnings"]:
                    self.emit("cost_warning", {"message": warning})
            
            if result.get("should_terminate"):
                self.emit("cost_limit_reached", {"reason": "Cost or time limit exceeded"})
                asyncio.create_task(self.disconnect())
                
        except Exception as e:
            self.api_logger.error(f"Error tracking audio usage: {e}")
    
    async def _monitor_costs(self):
        """Periodically monitor costs and limits"""
        while self.connected and self.session_active:
            try:
                await asyncio.sleep(self.cost_check_interval)
                
                # Get session status from cost tracker
                if self.session_id in self.cost_tracker.session_data:
                    session = self.cost_tracker.session_data[self.session_id]
                    duration = time.time() - session["start_time"]
                    
                    # Check if we're approaching limits
                    if duration >= self.cost_tracker.limits.max_session_duration * 0.9:
                        self.emit("cost_warning", {
                            "message": f"Session will end in {self.cost_tracker.limits.max_session_duration - duration:.0f} seconds"
                        })
                        
            except Exception as e:
                self.api_logger.error(f"Error monitoring costs: {e}")
    
    async def start_audio_input(self):
        """Start capturing audio input"""
        if not self.connected:
            return {"error": "Not connected"}
        
        if not PYAUDIO_AVAILABLE or not self.audio:
            return {"error": "Audio not available"}
        
        try:
            self.input_stream = self.audio.open(
                format=self.audio_config.format,
                channels=self.audio_config.channels,
                rate=self.audio_config.sample_rate,
                input=True,
                frames_per_buffer=self.audio_config.chunk_size
            )
            
            self.audio_input_enabled = True
            
            # Start audio capture task
            asyncio.create_task(self._capture_audio())
            
            return {"audio_input_started": True}
            
        except Exception as e:
            self.api_logger.error(f"Failed to start audio input: {e}")
            return {"error": str(e)}
    
    async def _capture_audio(self):
        """Capture and send audio to API"""
        try:
            while self.audio_input_enabled and self.input_stream:
                audio_data = self.input_stream.read(self.audio_config.chunk_size)
                encoded_audio = base64.b64encode(audio_data).decode('utf-8')
                
                # Send audio to API
                audio_message = {
                    "type": "input_audio_buffer.append",
                    "audio": encoded_audio
                }
                
                await self.websocket.send(json.dumps(audio_message))
                
                # Small delay to prevent overwhelming the API
                await asyncio.sleep(0.01)
                
        except Exception as e:
            self.api_logger.error(f"Error capturing audio: {e}")
            self.emit("error", {"type": "audio_capture", "message": str(e)})
    
    async def stop_audio_input(self):
        """Stop capturing audio input"""
        self.audio_input_enabled = False
        if self.input_stream:
            self.input_stream.stop_stream()
            self.input_stream.close()
            self.input_stream = None
        
        return {"audio_input_stopped": True}
    
    async def send_text(self, text: str):
        """Send text message to the API"""
        if not self.connected:
            return {"error": "Not connected"}
        
        message = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}]
            }
        }
        
        await self.websocket.send(json.dumps(message))
        
        # Trigger response
        response_message = {"type": "response.create"}
        await self.websocket.send(json.dumps(response_message))
        
        return {"text_sent": True}
    
    async def disconnect(self):
        """Disconnect from the API and cleanup"""
        try:
            self.connected = False
            self.session_active = False
            
            # Stop audio
            await self.stop_audio_input()
            
            # Close WebSocket
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            
            # Cleanup audio
            if self.output_stream:
                self.output_stream.stop_stream()
                self.output_stream.close()
                self.output_stream = None
                
            if self.audio:
                self.audio.terminate()
                self.audio = None
            
            # End session tracking
            if self.session_id in self.cost_tracker.session_data:
                summary = self.cost_tracker.end_session(self.session_id)
                self.emit("session_ended", summary)
            
            self.emit("disconnected", {"reason": "Manual disconnect"})
            
            return {"disconnected": True}
            
        except Exception as e:
            self.api_logger.error(f"Error during disconnect: {e}")
            return {"error": str(e)}
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get current session statistics"""
        if self.session_id in self.cost_tracker.session_data:
            session = self.cost_tracker.session_data[self.session_id]
            duration = time.time() - session["start_time"]
            
            return {
                "session_id": self.session_id,
                "duration_seconds": round(duration, 1),
                "cost": round(session["cost"], 4),
                "audio_input_seconds": round(session["audio_input_seconds"], 2),
                "audio_output_seconds": round(session["audio_output_seconds"], 2),
                "remaining_cost": max(0, self.cost_tracker.limits.max_cost_per_session - session["cost"]),
                "remaining_time": max(0, self.cost_tracker.limits.max_session_duration - duration)
            }
        
        return {"error": "Session not found"}