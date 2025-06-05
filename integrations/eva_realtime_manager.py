#!/usr/bin/env python3
"""
Eva Realtime Manager - Integration with GPT-4o Realtime API for Eva voice interface
"""
import asyncio
import json
import uuid
import os
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import logging
from .gpt4o_realtime_client import GPT4oRealtimeClient
from .realtime_cost_tracker import get_realtime_tracker, CostLimits

@dataclass
class EvaRealtimeConfig:
    """Configuration for Eva's realtime integration"""
    max_cost_per_session: float = 0.50      # $0.50 per session (conservative)
    max_cost_per_day: float = 5.0           # $5 per day
    max_session_duration: int = 180         # 3 minutes per session
    max_daily_sessions: int = 30            # 30 sessions per day
    warning_threshold: float = 0.8          # Warn at 80%
    
    # Audio settings
    enable_audio_input: bool = True
    enable_audio_output: bool = True
    
    # Safety settings
    require_user_confirmation: bool = True  # Require confirmation before starting
    auto_terminate_on_limit: bool = True    # Auto-terminate when limits reached

class EvaRealtimeManager:
    """Manages GPT-4o Realtime API sessions for Eva with comprehensive cost controls"""
    
    def __init__(self, config: Optional[EvaRealtimeConfig] = None):
        self.config = config or EvaRealtimeConfig()
        self.cost_tracker = get_realtime_tracker()
        
        # Update cost tracker limits
        self.cost_tracker.update_limits({
            "max_cost_per_session": self.config.max_cost_per_session,
            "max_cost_per_day": self.config.max_cost_per_day,
            "max_session_duration": self.config.max_session_duration,
            "max_daily_sessions": self.config.max_daily_sessions,
            "warning_threshold": self.config.warning_threshold
        })
        
        # Active clients
        self.active_clients = {}
        
        # Event handlers for Eva integration
        self.eva_handlers = {}
        
        # Logger
        self.logger = logging.getLogger(__name__)
        
        # Get API key
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
    
    def on_eva_event(self, event_type: str, handler: Callable):
        """Register Eva event handler"""
        self.eva_handlers[event_type] = handler
    
    def emit_eva_event(self, event_type: str, data: Any = None):
        """Emit event to Eva"""
        if event_type in self.eva_handlers:
            try:
                self.eva_handlers[event_type](data)
            except Exception as e:
                self.logger.error(f"Error in Eva event handler for {event_type}: {e}")
    
    async def request_realtime_session(self, user_id: str = "default") -> Dict[str, Any]:
        """Request a new realtime session with cost validation"""
        
        # Check daily limits
        daily_summary = self.cost_tracker.get_daily_summary()
        permission = self.cost_tracker.can_start_session()
        
        if not permission["allowed"]:
            return {
                "approved": False,
                "reason": permission["reason"],
                "daily_summary": daily_summary
            }
        
        # Generate session info
        session_id = f"eva_realtime_{user_id}_{uuid.uuid4().hex[:8]}"
        
        session_info = {
            "session_id": session_id,
            "user_id": user_id,
            "approved": True,
            "limits": {
                "max_cost": self.config.max_cost_per_session,
                "max_duration_minutes": self.config.max_session_duration / 60,
                "estimated_cost_per_minute": 0.30  # Rough estimate
            },
            "warnings": permission.get("warnings", []),
            "daily_summary": daily_summary
        }
        
        # If user confirmation required, return session info for approval
        if self.config.require_user_confirmation:
            session_info["requires_confirmation"] = True
            session_info["confirmation_message"] = (
                f"Realtime voice session will cost up to ${self.config.max_cost_per_session:.2f} "
                f"for max {self.config.max_session_duration // 60} minutes. "
                f"Daily remaining: ${daily_summary['remaining']['cost']:.2f}. Continue?"
            )
        
        return session_info
    
    async def start_realtime_session(self, session_id: str, user_confirmed: bool = False) -> Dict[str, Any]:
        """Start a realtime session after confirmation"""
        
        if self.config.require_user_confirmation and not user_confirmed:
            return {
                "started": False,
                "error": "User confirmation required"
            }
        
        # Check if session already exists
        if session_id in self.active_clients:
            return {
                "started": False,
                "error": "Session already active"
            }
        
        try:
            # Create realtime client
            client = GPT4oRealtimeClient(self.api_key, session_id)
            
            # Register event handlers
            self._setup_client_handlers(client, session_id)
            
            # Connect to API
            connect_result = await client.connect()
            
            if connect_result.get("connected"):
                self.active_clients[session_id] = client
                
                # Start audio input if enabled and available
                if self.config.enable_audio_input:
                    audio_result = await client.start_audio_input()
                    if "error" in audio_result:
                        self.logger.warning(f"Audio input not available: {audio_result['error']}")
                
                # Emit to Eva
                self.emit_eva_event("realtime_session_started", {
                    "session_id": session_id,
                    "warnings": connect_result.get("warnings", [])
                })
                
                return {
                    "started": True,
                    "session_id": session_id,
                    "audio_input_enabled": self.config.enable_audio_input,
                    "audio_output_enabled": self.config.enable_audio_output
                }
            else:
                return {
                    "started": False,
                    "error": connect_result.get("error", "Failed to connect")
                }
                
        except Exception as e:
            self.logger.error(f"Failed to start realtime session {session_id}: {e}")
            return {
                "started": False,
                "error": str(e)
            }
    
    def _setup_client_handlers(self, client: GPT4oRealtimeClient, session_id: str):
        """Setup event handlers for realtime client"""
        
        client.on("transcription", lambda data: self.emit_eva_event("user_speech", {
            "session_id": session_id,
            "text": data.get("text", ""),
            "source": "realtime"
        }))
        
        client.on("text_delta", lambda data: self.emit_eva_event("eva_response_text", {
            "session_id": session_id,
            "text": data.get("text", ""),
            "type": "delta"
        }))
        
        client.on("audio_delta", lambda data: self.emit_eva_event("eva_response_audio", {
            "session_id": session_id,
            "audio_data": data.get("audio", ""),
            "duration": data.get("duration", 0)
        }))
        
        client.on("cost_warning", lambda data: self.emit_eva_event("cost_warning", {
            "session_id": session_id,
            "message": data.get("message", ""),
            "level": "warning"
        }))
        
        client.on("cost_limit_reached", lambda data: self.emit_eva_event("cost_limit_reached", {
            "session_id": session_id,
            "reason": data.get("reason", "Cost limit exceeded"),
            "level": "critical"
        }))
        
        client.on("session_ended", lambda data: self._handle_session_end(session_id, data))
        
        client.on("error", lambda data: self.emit_eva_event("realtime_error", {
            "session_id": session_id,
            "error": data
        }))
    
    def _handle_session_end(self, session_id: str, data: Dict[str, Any]):
        """Handle session end cleanup"""
        if session_id in self.active_clients:
            del self.active_clients[session_id]
        
        self.emit_eva_event("realtime_session_ended", {
            "session_id": session_id,
            "summary": data.get("session_summary", {})
        })
    
    async def send_text_to_session(self, session_id: str, text: str) -> Dict[str, Any]:
        """Send text message to active session"""
        if session_id not in self.active_clients:
            return {"sent": False, "error": "Session not found"}
        
        client = self.active_clients[session_id]
        result = await client.send_text(text)
        
        return result
    
    async def end_session(self, session_id: str) -> Dict[str, Any]:
        """End a realtime session"""
        if session_id not in self.active_clients:
            return {"ended": False, "error": "Session not found"}
        
        try:
            client = self.active_clients[session_id]
            result = await client.disconnect()
            
            # Remove from active clients
            if session_id in self.active_clients:
                del self.active_clients[session_id]
            
            return {"ended": True, "summary": result}
            
        except Exception as e:
            self.logger.error(f"Error ending session {session_id}: {e}")
            return {"ended": False, "error": str(e)}
    
    async def end_all_sessions(self) -> Dict[str, Any]:
        """End all active sessions"""
        results = {}
        
        for session_id in list(self.active_clients.keys()):
            results[session_id] = await self.end_session(session_id)
        
        return {
            "ended_sessions": len(results),
            "results": results
        }
    
    def get_active_sessions(self) -> Dict[str, Any]:
        """Get information about active sessions"""
        sessions = {}
        
        for session_id, client in self.active_clients.items():
            sessions[session_id] = client.get_session_stats()
        
        return {
            "active_count": len(sessions),
            "sessions": sessions,
            "daily_summary": self.cost_tracker.get_daily_summary()
        }
    
    def get_cost_summary(self) -> Dict[str, Any]:
        """Get comprehensive cost summary"""
        return self.cost_tracker.get_daily_summary()
    
    def update_config(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """Update configuration and cost limits"""
        try:
            # Update local config
            for key, value in new_config.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
            
            # Update cost tracker limits
            limit_mapping = {
                "max_cost_per_session": "max_cost_per_session",
                "max_cost_per_day": "max_cost_per_day", 
                "max_session_duration": "max_session_duration",
                "max_daily_sessions": "max_daily_sessions",
                "warning_threshold": "warning_threshold"
            }
            
            cost_updates = {}
            for config_key, limit_key in limit_mapping.items():
                if config_key in new_config:
                    cost_updates[limit_key] = new_config[config_key]
            
            if cost_updates:
                self.cost_tracker.update_limits(cost_updates)
            
            return {"updated": True, "config": new_config}
            
        except Exception as e:
            self.logger.error(f"Error updating config: {e}")
            return {"updated": False, "error": str(e)}

# Global manager instance
_eva_realtime_manager = None

def get_eva_realtime_manager(config: Optional[EvaRealtimeConfig] = None) -> EvaRealtimeManager:
    """Get the global Eva realtime manager instance"""
    global _eva_realtime_manager
    if _eva_realtime_manager is None:
        _eva_realtime_manager = EvaRealtimeManager(config)
    return _eva_realtime_manager