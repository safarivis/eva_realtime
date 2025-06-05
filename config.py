#!/usr/bin/env python3
"""
Configuration management for Eva Realtime App
"""
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Centralized configuration management"""
    
    # Application Settings
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'your-secret-key-here')
    PORT: int = int(os.getenv('PORT', 5000))
    
    # OpenAI Settings
    OPENAI_API_KEY: str = os.getenv('OPENAI_API_KEY', '')
    
    # Dashboard & URL Settings
    DASHBOARD_URL: str = os.getenv('DASHBOARD_URL', 'https://evarealtime-production.up.railway.app/dashboard')
    APP_BASE_URL: str = os.getenv('APP_BASE_URL', 'https://evarealtime-production.up.railway.app')
    
    # Email Settings
    RESEND_API_KEY: Optional[str] = os.getenv('RESEND_API_KEY')
    FROM_EMAIL: str = os.getenv('FROM_EMAIL', 'eva-realtime@updates.yourapp.com')
    
    # Eva Integration
    EVA_ENDPOINT: str = os.getenv('EVA_ENDPOINT', 'http://localhost:8000')
    
    # Database Settings
    DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///eva_realtime.db')
    
    @classmethod
    def validate_required_config(cls) -> bool:
        """Validate that required configuration is present"""
        if not cls.OPENAI_API_KEY:
            return False
        return True
    
    @classmethod
    def get_dashboard_url(cls) -> str:
        """Get the dashboard URL (backwards compatible)"""
        return cls.DASHBOARD_URL
    
    @classmethod
    def get_app_base_url(cls) -> str:
        """Get the application base URL"""
        return cls.APP_BASE_URL

# Global config instance
config = Config()