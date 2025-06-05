#!/usr/bin/env python3
"""
GPT-4o Realtime API Cost Tracker - Budget management and cost controls
"""
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass
from .openai_logger import get_openai_logger

@dataclass
class CostLimits:
    """Cost limit configuration"""
    max_cost_per_session: float = 1.0  # $1 per session
    max_cost_per_day: float = 10.0     # $10 per day
    max_session_duration: int = 300    # 5 minutes
    max_daily_sessions: int = 50       # 50 sessions per day
    warning_threshold: float = 0.8     # Warn at 80% of limits

class RealtimeCostTracker:
    """Track and manage costs for GPT-4o Realtime API usage"""
    
    def __init__(self, data_dir: str = "data/cost_tracking"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.limits = CostLimits()
        self.logger = get_openai_logger()
        
        # Load existing data
        self.daily_data = self._load_daily_data()
        self.session_data = {}
    
    def _load_daily_data(self) -> Dict[str, Any]:
        """Load daily usage data"""
        today = datetime.now().strftime("%Y-%m-%d")
        data_file = self.data_dir / f"realtime_costs_{today}.json"
        
        if data_file.exists():
            with open(data_file, 'r') as f:
                return json.load(f)
        
        return {
            "date": today,
            "total_cost": 0.0,
            "total_sessions": 0,
            "total_audio_seconds": 0.0,
            "sessions": []
        }
    
    def _save_daily_data(self):
        """Save daily usage data"""
        today = datetime.now().strftime("%Y-%m-%d")
        data_file = self.data_dir / f"realtime_costs_{today}.json"
        
        with open(data_file, 'w') as f:
            json.dump(self.daily_data, f, indent=2)
    
    def can_start_session(self) -> Dict[str, Any]:
        """Check if a new session can be started based on limits"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Check daily session limit
        if self.daily_data["total_sessions"] >= self.limits.max_daily_sessions:
            return {
                "allowed": False,
                "reason": "Daily session limit reached",
                "current_sessions": self.daily_data["total_sessions"],
                "limit": self.limits.max_daily_sessions
            }
        
        # Check daily cost limit
        if self.daily_data["total_cost"] >= self.limits.max_cost_per_day:
            return {
                "allowed": False,
                "reason": "Daily cost limit reached",
                "current_cost": self.daily_data["total_cost"],
                "limit": self.limits.max_cost_per_day
            }
        
        # Check if approaching limits (warning)
        warnings = []
        if self.daily_data["total_cost"] >= self.limits.max_cost_per_day * self.limits.warning_threshold:
            warnings.append(f"Approaching daily cost limit: ${self.daily_data['total_cost']:.2f}/${self.limits.max_cost_per_day:.2f}")
        
        if self.daily_data["total_sessions"] >= self.limits.max_daily_sessions * self.limits.warning_threshold:
            warnings.append(f"Approaching daily session limit: {self.daily_data['total_sessions']}/{self.limits.max_daily_sessions}")
        
        return {
            "allowed": True,
            "warnings": warnings,
            "remaining_cost": self.limits.max_cost_per_day - self.daily_data["total_cost"],
            "remaining_sessions": self.limits.max_daily_sessions - self.daily_data["total_sessions"]
        }
    
    def start_session(self, session_id: str) -> Dict[str, Any]:
        """Start tracking a new session"""
        permission = self.can_start_session()
        if not permission["allowed"]:
            return permission
        
        self.session_data[session_id] = {
            "start_time": time.time(),
            "cost": 0.0,
            "audio_input_seconds": 0.0,
            "audio_output_seconds": 0.0,
            "warnings_sent": []
        }
        
        # Log session start
        self.logger.log_realtime_session_start(session_id)
        
        return {
            "session_started": True,
            "session_id": session_id,
            "max_cost": self.limits.max_cost_per_session,
            "max_duration": self.limits.max_session_duration,
            "warnings": permission.get("warnings", [])
        }
    
    def track_audio_usage(self, session_id: str, audio_type: str, duration_seconds: float) -> Dict[str, Any]:
        """Track audio usage and check limits"""
        if session_id not in self.session_data:
            return {"error": "Session not found"}
        
        session = self.session_data[session_id]
        
        # Calculate cost
        cost = self.logger.log_realtime_audio(session_id, audio_type, duration_seconds)
        session["cost"] += cost
        
        if audio_type == "input":
            session["audio_input_seconds"] += duration_seconds
        else:
            session["audio_output_seconds"] += duration_seconds
        
        # Check session limits
        warnings = []
        should_terminate = False
        
        # Check session cost limit
        if session["cost"] >= self.limits.max_cost_per_session:
            warnings.append(f"Session cost limit reached: ${session['cost']:.4f}")
            should_terminate = True
        elif session["cost"] >= self.limits.max_cost_per_session * self.limits.warning_threshold:
            warning_msg = f"Session approaching cost limit: ${session['cost']:.4f}/${self.limits.max_cost_per_session:.2f}"
            if warning_msg not in session["warnings_sent"]:
                warnings.append(warning_msg)
                session["warnings_sent"].append(warning_msg)
        
        # Check session duration limit
        duration = time.time() - session["start_time"]
        if duration >= self.limits.max_session_duration:
            warnings.append(f"Session duration limit reached: {duration:.0f}s")
            should_terminate = True
        elif duration >= self.limits.max_session_duration * self.limits.warning_threshold:
            warning_msg = f"Session approaching duration limit: {duration:.0f}s/{self.limits.max_session_duration}s"
            if warning_msg not in session["warnings_sent"]:
                warnings.append(warning_msg)
                session["warnings_sent"].append(warning_msg)
        
        return {
            "session_id": session_id,
            "cost": round(cost, 6),
            "session_total_cost": round(session["cost"], 4),
            "session_duration": round(duration, 1),
            "warnings": warnings,
            "should_terminate": should_terminate,
            "remaining_cost": max(0, self.limits.max_cost_per_session - session["cost"]),
            "remaining_time": max(0, self.limits.max_session_duration - duration)
        }
    
    def end_session(self, session_id: str) -> Dict[str, Any]:
        """End a session and update daily totals"""
        if session_id not in self.session_data:
            return {"error": "Session not found"}
        
        session = self.session_data[session_id]
        
        # Get session summary from logger
        summary = self.logger.log_realtime_session_end(session_id)
        
        # Update daily totals
        self.daily_data["total_cost"] += session["cost"]
        self.daily_data["total_sessions"] += 1
        self.daily_data["total_audio_seconds"] += (session["audio_input_seconds"] + session["audio_output_seconds"])
        
        # Add session to daily log
        session_summary = {
            "session_id": session_id,
            "start_time": datetime.fromtimestamp(session["start_time"]).isoformat(),
            "end_time": datetime.now().isoformat(),
            "duration_seconds": summary.get("duration_seconds", 0),
            "cost": round(session["cost"], 4),
            "audio_input_seconds": round(session["audio_input_seconds"], 2),
            "audio_output_seconds": round(session["audio_output_seconds"], 2)
        }
        
        self.daily_data["sessions"].append(session_summary)
        
        # Save daily data
        self._save_daily_data()
        
        # Remove from active sessions
        del self.session_data[session_id]
        
        return {
            "session_ended": True,
            "session_summary": session_summary,
            "daily_totals": {
                "cost": self.daily_data["total_cost"],
                "sessions": self.daily_data["total_sessions"],
                "audio_seconds": self.daily_data["total_audio_seconds"]
            }
        }
    
    def get_daily_summary(self) -> Dict[str, Any]:
        """Get daily usage summary"""
        return {
            "date": self.daily_data["date"],
            "totals": {
                "cost": round(self.daily_data["total_cost"], 4),
                "sessions": self.daily_data["total_sessions"],
                "audio_seconds": round(self.daily_data["total_audio_seconds"], 2)
            },
            "limits": {
                "max_cost_per_day": self.limits.max_cost_per_day,
                "max_daily_sessions": self.limits.max_daily_sessions,
                "max_cost_per_session": self.limits.max_cost_per_session,
                "max_session_duration": self.limits.max_session_duration
            },
            "remaining": {
                "cost": max(0, self.limits.max_cost_per_day - self.daily_data["total_cost"]),
                "sessions": max(0, self.limits.max_daily_sessions - self.daily_data["total_sessions"])
            },
            "active_sessions": len(self.session_data)
        }
    
    def update_limits(self, new_limits: Dict[str, Any]) -> None:
        """Update cost limits"""
        for key, value in new_limits.items():
            if hasattr(self.limits, key):
                setattr(self.limits, key, value)

# Global tracker instance
_realtime_tracker = None

def get_realtime_tracker() -> RealtimeCostTracker:
    """Get the global realtime cost tracker instance"""
    global _realtime_tracker
    if _realtime_tracker is None:
        _realtime_tracker = RealtimeCostTracker()
    return _realtime_tracker