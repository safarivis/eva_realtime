#!/usr/bin/env python3
"""
Eva Email Integration for Realtime Cost Reports
"""
import os
import json
import requests
import logging
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class EvaEmailIntegration:
    """Integration with Eva for sending cost report emails"""
    
    def __init__(self, eva_endpoint: Optional[str] = None):
        self.eva_endpoint = eva_endpoint or os.getenv('EVA_ENDPOINT', 'http://localhost:8000')
        self.resend_api_key = os.getenv('RESEND_API_KEY')
        
    def send_cost_report_via_eva(self, email: str, report_data: Dict[str, Any], report_type: str = "daily") -> bool:
        """Send cost report by asking Eva to send email"""
        try:
            # Format the report as a message to Eva
            eva_message = self._format_eva_message(report_data, report_type, email)
            
            # Send to Eva's chat endpoint
            response = requests.post(
                f"{self.eva_endpoint}/api/chat",
                json={
                    "message": eva_message,
                    "session_id": f"cost_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "user_id": "cost_monitor"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Successfully requested Eva to send cost report to {email}")
                return True
            else:
                logger.error(f"Eva API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send report via Eva: {e}")
            return False
    
    def send_direct_email(self, email: str, subject: str, content: str) -> bool:
        """Send email directly using Resend API"""
        if not self.resend_api_key:
            logger.warning("No Resend API key configured")
            return False
            
        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self.resend_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": "eva-realtime@updates.yourapp.com",
                    "to": [email],
                    "subject": subject,
                    "text": content,
                    "html": self._format_html_email(content)
                },
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Email sent successfully to {email}")
                return True
            else:
                logger.error(f"Resend API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send direct email: {e}")
            return False
    
    def _format_eva_message(self, report_data: Dict[str, Any], report_type: str, email: str) -> str:
        """Format cost report as a message for Eva to process"""
        cost_summary = report_data.get('cost_summary', {})
        
        if report_type == "setup":
            return f"""
            Please send a confirmation email to {email} with the subject "Eva Realtime - Email Reports Configured".
            
            Include this information:
            - Email reports are now set up for GPT-4o Realtime API cost monitoring
            - They will receive daily cost summaries, budget alerts, and session reports
            - Current daily cost: ${cost_summary.get('totals', {}).get('cost', 0):.4f}
            - Budget remaining: ${cost_summary.get('remaining', {}).get('cost', 0):.2f}
            - Dashboard link: https://evarealtime-production.up.railway.app/dashboard
            
            Make it friendly and informative!
            """
        
        elif report_type == "daily":
            sessions = report_data.get('session_history', [])
            return f"""
            Please send a daily cost report email to {email} with the subject "Eva Realtime - Daily Cost Report".
            
            Include this cost summary:
            - Total cost today: ${cost_summary.get('totals', {}).get('cost', 0):.4f}
            - Budget used: {(cost_summary.get('totals', {}).get('cost', 0) / cost_summary.get('limits', {}).get('max_cost_per_day', 1) * 100):.1f}%
            - Sessions today: {cost_summary.get('totals', {}).get('sessions', 0)}
            - Audio time: {cost_summary.get('totals', {}).get('audio_seconds', 0):.1f} seconds
            - Budget remaining: ${cost_summary.get('remaining', {}).get('cost', 0):.2f}
            
            Recent sessions: {len(sessions)} sessions completed
            
            Include dashboard link: https://evarealtime-production.up.railway.app/dashboard
            
            Make it professional but friendly!
            """
        
        elif report_type == "budget_alert":
            usage_percent = report_data.get('usage_percent', 0)
            return f"""
            URGENT: Please send a budget alert email to {email} with the subject "⚠️ Eva Realtime - Budget Alert".
            
            Alert details:
            - Budget usage: {usage_percent:.1f}% of daily limit
            - Current cost: ${cost_summary.get('totals', {}).get('cost', 0):.4f}
            - Daily limit: ${cost_summary.get('limits', {}).get('max_cost_per_day', 0):.2f}
            - Remaining budget: ${cost_summary.get('remaining', {}).get('cost', 0):.2f}
            
            Recommend they monitor usage closely and consider ending sessions if needed.
            Include dashboard link for real-time monitoring.
            
            Make it urgent but not alarming!
            """
        
        return f"Please send a {report_type} cost report email to {email} about GPT-4o Realtime API usage."
    
    def _format_html_email(self, text_content: str) -> str:
        """Convert text email to HTML format"""
        html = text_content.replace('\n', '<br>')
        html = html.replace('•', '&bull;')
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 20px; border-radius: 0 0 10px 10px; }}
                .footer {{ text-align: center; margin-top: 20px; font-size: 0.9em; color: #666; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>🤖 Eva Realtime Cost Monitor</h2>
                </div>
                <div class="content">
                    {html}
                </div>
                <div class="footer">
                    <p>This email was generated by Eva Realtime API Cost Monitor</p>
                    <p><a href="https://evarealtime-production.up.railway.app/dashboard">View Dashboard</a></p>
                </div>
            </div>
        </body>
        </html>
        """

# Global integration instance
_eva_email_integration = None

def get_eva_email_integration() -> EvaEmailIntegration:
    """Get the global Eva email integration instance"""
    global _eva_email_integration
    if _eva_email_integration is None:
        _eva_email_integration = EvaEmailIntegration()
    return _eva_email_integration

def send_cost_report(email: str, report_data: Dict[str, Any], report_type: str = "daily") -> bool:
    """Send cost report via Eva integration or direct email"""
    integration = get_eva_email_integration()
    
    # Try Eva first, fall back to direct email
    if integration.send_cost_report_via_eva(email, report_data, report_type):
        return True
    
    # Fallback to direct email if Eva is not available
    subject = f"Eva Realtime - {report_type.title()} Report"
    content = _format_direct_email_content(report_data, report_type)
    
    return integration.send_direct_email(email, subject, content)

def _format_direct_email_content(report_data: Dict[str, Any], report_type: str) -> str:
    """Format email content for direct sending"""
    cost_summary = report_data.get('cost_summary', {})
    
    if report_type == "setup":
        return f"""
📧 Email Reports Setup Complete!

You will now receive:
• Daily cost summaries
• Budget alerts  
• Session reports
• Weekly usage trends

Current Status:
• Daily Cost: ${cost_summary.get('totals', {}).get('cost', 0):.4f}
• Budget Remaining: ${cost_summary.get('remaining', {}).get('cost', 0):.2f}
• Sessions Today: {cost_summary.get('totals', {}).get('sessions', 0)}

Dashboard: https://evarealtime-production.up.railway.app/dashboard

🤖 Eva Realtime Cost Monitor
        """
    
    return f"Cost report for {report_type} - {datetime.now().strftime('%Y-%m-%d')}"