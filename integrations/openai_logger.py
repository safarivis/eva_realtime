#!/usr/bin/env python3
"""
OpenAI API Logger - Comprehensive logging and tracing for OpenAI API calls
"""
import logging
import json
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import asyncio
import httpx
from functools import wraps

class OpenAILogger:
    """Comprehensive OpenAI API logging and tracing"""
    
    def __init__(self, log_dir: str = "logs/openai", log_level: str = "INFO"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create separate loggers for different purposes
        self.api_logger = self._setup_logger("openai_api", "openai_api.log", log_level)
        self.error_logger = self._setup_logger("openai_errors", "openai_errors.log", "ERROR")
        self.trace_logger = self._setup_logger("openai_trace", "openai_trace.log", "DEBUG")
        
        # Track request metrics
        self.request_count = 0
        self.total_tokens = 0
        self.total_cost = 0.0
        
        # Track realtime sessions
        self.realtime_sessions = {}
        self.total_audio_seconds = 0.0
        
    def _setup_logger(self, name: str, filename: str, level: str) -> logging.Logger:
        """Setup a logger with file and console handlers"""
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level))
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # File handler
        file_handler = logging.FileHandler(self.log_dir / filename)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Console handler for errors
        if level == "ERROR":
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(
                '🚨 OPENAI ERROR - %(asctime)s - %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        return logger
    
    def estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars = 1 token)"""
        return len(text) // 4
    
    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int = 0, 
                      audio_seconds: float = 0) -> float:
        """Estimate API call cost based on model and tokens"""
        # Pricing as of 2024 (USD per 1M tokens)
        pricing = {
            "gpt-4.1": {"input": 15.0, "output": 60.0},
            "gpt-4-turbo": {"input": 10.0, "output": 30.0},
            "gpt-4o": {"input": 5.0, "output": 15.0},
            "gpt-4o-mini": {"input": 0.15, "output": 0.6},
            "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
            "dall-e-3": {"per_image": 40.0},
            "dall-e-2": {"per_image": 20.0},
            "whisper": {"per_minute": 6.0},
            # GPT-4o Realtime API pricing (per minute of audio)
            "gpt-4o-realtime": {"audio_input": 6.0, "audio_output": 24.0}
        }
        
        if model in pricing:
            rates = pricing[model]
            if "per_image" in rates:
                return rates["per_image"] / 1000  # Convert to dollars
            elif "audio_input" in rates:
                # Realtime API pricing (per minute)
                minutes = audio_seconds / 60.0
                input_cost = minutes * rates["audio_input"] / 100  # Convert cents to dollars
                output_cost = minutes * rates["audio_output"] / 100
                return input_cost + output_cost
            else:
                input_cost = (input_tokens / 1_000_000) * rates["input"]
                output_cost = (output_tokens / 1_000_000) * rates["output"]
                return input_cost + output_cost
        
        return 0.0
    
    def log_request_start(self, method: str, url: str, payload: Dict[str, Any]) -> str:
        """Log the start of an API request"""
        request_id = str(uuid.uuid4())[:8]
        self.request_count += 1
        
        # Extract key information
        model = payload.get("model", "unknown")
        messages = payload.get("messages", [])
        
        # Estimate tokens
        total_input_text = ""
        for msg in messages:
            if isinstance(msg.get("content"), str):
                total_input_text += msg["content"]
            elif isinstance(msg.get("content"), list):
                for content in msg["content"]:
                    if content.get("type") == "text":
                        total_input_text += content.get("text", "")
        
        estimated_tokens = self.estimate_tokens(total_input_text)
        estimated_cost = self.estimate_cost(model, estimated_tokens)
        
        # Log request details
        log_data = {
            "request_id": request_id,
            "timestamp": datetime.now().isoformat(),
            "method": method,
            "url": url,
            "model": model,
            "estimated_input_tokens": estimated_tokens,
            "estimated_cost_usd": round(estimated_cost, 6),
            "message_count": len(messages),
            "has_tools": "tools" in payload,
            "tool_choice": payload.get("tool_choice", "none"),
            "parallel_tool_calls": payload.get("parallel_tool_calls", True)
        }
        
        self.api_logger.info(f"📤 REQUEST START: {json.dumps(log_data)}")
        self.trace_logger.debug(f"Full payload: {json.dumps(payload, indent=2)}")
        
        return request_id
    
    def log_request_end(self, request_id: str, response_data: Dict[str, Any], 
                       duration: float, status_code: int):
        """Log the end of an API request"""
        
        # Extract response information
        usage = response_data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
        output_tokens = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", input_tokens + output_tokens)
        
        # Update totals
        self.total_tokens += total_tokens
        
        # Calculate actual cost
        model = response_data.get("model", "unknown")
        actual_cost = self.estimate_cost(model, input_tokens, output_tokens)
        self.total_cost += actual_cost
        
        # Log response details
        log_data = {
            "request_id": request_id,
            "timestamp": datetime.now().isoformat(),
            "status_code": status_code,
            "duration_seconds": round(duration, 3),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "actual_cost_usd": round(actual_cost, 6),
            "cumulative_tokens": self.total_tokens,
            "cumulative_cost_usd": round(self.total_cost, 4)
        }
        
        if status_code == 200:
            self.api_logger.info(f"✅ REQUEST SUCCESS: {json.dumps(log_data)}")
        else:
            self.api_logger.error(f"❌ REQUEST FAILED: {json.dumps(log_data)}")
            
        self.trace_logger.debug(f"Full response: {json.dumps(response_data, indent=2)}")
    
    def log_error(self, request_id: str, error: Exception, context: Dict[str, Any] = None):
        """Log an API error"""
        error_data = {
            "request_id": request_id,
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {}
        }
        
        self.error_logger.error(f"API Error: {json.dumps(error_data)}")
        
        # Also log to console for immediate visibility
        print(f"🚨 OpenAI API Error [{request_id}]: {error}")
    
    def log_realtime_session_start(self, session_id: str) -> None:
        """Log the start of a realtime session"""
        self.realtime_sessions[session_id] = {
            "start_time": time.time(),
            "audio_input_seconds": 0.0,
            "audio_output_seconds": 0.0,
            "cost": 0.0
        }
        
        log_data = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "event": "realtime_session_start"
        }
        self.api_logger.info(f"🎙️ REALTIME SESSION START: {json.dumps(log_data)}")
    
    def log_realtime_audio(self, session_id: str, audio_type: str, duration_seconds: float) -> float:
        """Log audio usage and return cost"""
        if session_id not in self.realtime_sessions:
            self.log_realtime_session_start(session_id)
        
        session = self.realtime_sessions[session_id]
        
        # Update audio duration
        if audio_type == "input":
            session["audio_input_seconds"] += duration_seconds
        else:
            session["audio_output_seconds"] += duration_seconds
        
        # Calculate incremental cost
        incremental_cost = self.estimate_cost("gpt-4o-realtime", 0, 0, duration_seconds)
        session["cost"] += incremental_cost
        self.total_cost += incremental_cost
        self.total_audio_seconds += duration_seconds
        
        log_data = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "audio_type": audio_type,
            "duration_seconds": round(duration_seconds, 2),
            "incremental_cost_usd": round(incremental_cost, 6),
            "session_total_cost_usd": round(session["cost"], 4)
        }
        
        self.api_logger.info(f"🔊 REALTIME AUDIO: {json.dumps(log_data)}")
        
        return incremental_cost
    
    def log_realtime_session_end(self, session_id: str) -> Dict[str, Any]:
        """Log the end of a realtime session and return summary"""
        if session_id not in self.realtime_sessions:
            return {"error": "Session not found"}
        
        session = self.realtime_sessions[session_id]
        duration = time.time() - session["start_time"]
        
        summary = {
            "session_id": session_id,
            "duration_seconds": round(duration, 2),
            "audio_input_seconds": round(session["audio_input_seconds"], 2),
            "audio_output_seconds": round(session["audio_output_seconds"], 2),
            "total_audio_seconds": round(session["audio_input_seconds"] + session["audio_output_seconds"], 2),
            "total_cost_usd": round(session["cost"], 4),
            "timestamp": datetime.now().isoformat()
        }
        
        self.api_logger.info(f"🏁 REALTIME SESSION END: {json.dumps(summary)}")
        
        # Remove session from active sessions
        del self.realtime_sessions[session_id]
        
        return summary
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current usage statistics"""
        return {
            "total_requests": self.request_count,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost, 4),
            "avg_tokens_per_request": round(self.total_tokens / max(1, self.request_count), 2),
            "total_audio_seconds": round(self.total_audio_seconds, 2),
            "active_realtime_sessions": len(self.realtime_sessions)
        }
    
    def log_stats(self):
        """Log current statistics"""
        stats = self.get_stats()
        self.api_logger.info(f"📊 STATS: {json.dumps(stats)}")

# Global logger instance
_openai_logger = None

def get_openai_logger() -> OpenAILogger:
    """Get the global OpenAI logger instance"""
    global _openai_logger
    if _openai_logger is None:
        _openai_logger = OpenAILogger()
    return _openai_logger

def log_openai_request(func):
    """Decorator to automatically log OpenAI API requests"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger = get_openai_logger()
        
        # Extract request details from arguments
        request_data = {}
        if len(args) > 0 and hasattr(args[0], 'json'):
            # httpx request
            request_data = args[0].json
        elif 'json' in kwargs:
            request_data = kwargs['json']
        
        # Start logging
        request_id = logger.log_request_start(
            method="POST",
            url=kwargs.get('url', 'unknown'),
            payload=request_data
        )
        
        start_time = time.time()
        
        try:
            # Execute the function
            result = await func(*args, **kwargs)
            
            # Log success
            duration = time.time() - start_time
            response_data = result.json() if hasattr(result, 'json') else {}
            logger.log_request_end(request_id, response_data, duration, 
                                 getattr(result, 'status_code', 200))
            
            return result
            
        except Exception as e:
            # Log error
            duration = time.time() - start_time
            logger.log_error(request_id, e, {"duration": duration})
            raise
    
    return wrapper

# Utility functions
def log_token_usage(model: str, input_tokens: int, output_tokens: int = 0):
    """Quick function to log token usage"""
    logger = get_openai_logger()
    cost = logger.estimate_cost(model, input_tokens, output_tokens)
    logger.total_tokens += input_tokens + output_tokens
    logger.total_cost += cost
    
    log_data = {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6)
    }
    logger.api_logger.info(f"💰 TOKEN_USAGE: {json.dumps(log_data)}")

def print_usage_summary():
    """Print a summary of API usage"""
    logger = get_openai_logger()
    stats = logger.get_stats()
    
    print("\n" + "="*50)
    print("📊 OpenAI API Usage Summary")
    print("="*50)
    print(f"Total Requests: {stats['total_requests']}")
    print(f"Total Tokens: {stats['total_tokens']:,}")
    print(f"Total Cost: ${stats['total_cost_usd']:.4f}")
    print(f"Avg Tokens/Request: {stats['avg_tokens_per_request']:.1f}")
    print("="*50)