#!/usr/bin/env python3
"""
GPT-4o Realtime API Web Application for Railway Deployment
"""
import os
import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, Any
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, disconnect
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import our realtime integration (copy the files here)
import sys
sys.path.append('..')
from integrations.eva_realtime_manager import EvaRealtimeManager, EvaRealtimeConfig
from integrations.realtime_cost_tracker import get_realtime_tracker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global realtime manager
realtime_manager = None
active_sessions = {}

def init_realtime_manager():
    """Initialize the realtime manager"""
    global realtime_manager
    
    config = EvaRealtimeConfig(
        max_cost_per_session=0.50,      # $0.50 per session
        max_cost_per_day=10.0,          # $10 per day  
        max_session_duration=300,       # 5 minutes
        max_daily_sessions=50,          # 50 sessions per day
        require_user_confirmation=False, # Auto-approve for web
        enable_audio_input=False,       # Text only for web demo
        enable_audio_output=False
    )
    
    realtime_manager = EvaRealtimeManager(config)
    
    # Setup event handlers
    realtime_manager.on_eva_event("realtime_session_started", on_session_started)
    realtime_manager.on_eva_event("user_speech", on_user_speech)
    realtime_manager.on_eva_event("eva_response_text", on_eva_response_text)
    realtime_manager.on_eva_event("cost_warning", on_cost_warning)
    realtime_manager.on_eva_event("cost_limit_reached", on_cost_limit_reached)
    realtime_manager.on_eva_event("realtime_session_ended", on_session_ended)
    realtime_manager.on_eva_event("realtime_error", on_realtime_error)

def on_session_started(data):
    """Handle session started event"""
    session_id = data.get('session_id')
    if session_id in active_sessions:
        socketio.emit('session_started', {
            'session_id': session_id,
            'message': 'Session started successfully!',
            'warnings': data.get('warnings', [])
        }, room=active_sessions[session_id]['socket_id'])

def on_user_speech(data):
    """Handle user speech transcription"""
    session_id = data.get('session_id')
    if session_id in active_sessions:
        socketio.emit('user_speech', {
            'text': data.get('text', ''),
            'timestamp': datetime.now().isoformat()
        }, room=active_sessions[session_id]['socket_id'])

def on_eva_response_text(data):
    """Handle Eva's text response"""
    session_id = data.get('session_id')
    if session_id in active_sessions:
        socketio.emit('eva_response', {
            'text': data.get('text', ''),
            'type': data.get('type', 'delta'),
            'timestamp': datetime.now().isoformat()
        }, room=active_sessions[session_id]['socket_id'])

def on_cost_warning(data):
    """Handle cost warnings"""
    session_id = data.get('session_id')
    if session_id in active_sessions:
        socketio.emit('cost_warning', {
            'message': data.get('message', ''),
            'level': 'warning',
            'timestamp': datetime.now().isoformat()
        }, room=active_sessions[session_id]['socket_id'])

def on_cost_limit_reached(data):
    """Handle cost limit reached"""
    session_id = data.get('session_id')
    if session_id in active_sessions:
        socketio.emit('cost_limit_reached', {
            'reason': data.get('reason', ''),
            'level': 'critical',
            'timestamp': datetime.now().isoformat()
        }, room=active_sessions[session_id]['socket_id'])
        
        # Remove from active sessions
        del active_sessions[session_id]

def on_session_ended(data):
    """Handle session ended"""
    session_id = data.get('session_id')
    if session_id in active_sessions:
        socketio.emit('session_ended', {
            'summary': data.get('summary', {}),
            'timestamp': datetime.now().isoformat()
        }, room=active_sessions[session_id]['socket_id'])
        
        # Remove from active sessions
        del active_sessions[session_id]

def on_realtime_error(data):
    """Handle realtime errors"""
    session_id = data.get('session_id')
    if session_id in active_sessions:
        socketio.emit('realtime_error', {
            'error': data.get('error', {}),
            'timestamp': datetime.now().isoformat()
        }, room=active_sessions[session_id]['socket_id'])

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """Cost monitoring dashboard"""
    return render_template('dashboard.html')

@app.route('/api/status')
def get_status():
    """Get current cost and usage status"""
    if not realtime_manager:
        return jsonify({'error': 'Realtime manager not initialized'}), 500
    
    try:
        cost_summary = realtime_manager.get_cost_summary()
        active_sessions_info = realtime_manager.get_active_sessions()
        
        return jsonify({
            'status': 'ready',
            'cost_summary': cost_summary,
            'active_sessions': active_sessions_info,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/dashboard')
def get_dashboard_data():
    """Get comprehensive dashboard data"""
    if not realtime_manager:
        return jsonify({'error': 'Realtime manager not initialized'}), 500
    
    try:
        cost_summary = realtime_manager.get_cost_summary()
        active_sessions_info = realtime_manager.get_active_sessions()
        
        # Get session history from cost tracker
        cost_tracker = get_realtime_tracker()
        session_history = cost_tracker.daily_data.get('sessions', [])
        
        # Generate usage trends (mock data for now - you can implement real trend tracking)
        usage_trends = []
        current_hour = datetime.now().hour
        for i in range(24):
            hour = (current_hour - i) % 24
            # Mock trend data - replace with real data from your cost tracker
            usage_trends.append({
                'hour': f"{hour:02d}:00",
                'cost': cost_summary['totals']['cost'] * (0.1 if i < 6 else 0.05)  # Mock distribution
            })
        usage_trends.reverse()
        
        return jsonify({
            'cost_summary': cost_summary,
            'active_sessions': active_sessions_info,
            'session_history': session_history[-20:],  # Last 20 sessions
            'usage_trends': usage_trends,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/setup-email-reports', methods=['POST'])
def setup_email_reports():
    """Setup email reports for cost monitoring"""
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({'success': False, 'error': 'Email address required'}), 400
        
        # Store email preference (you can use a database or file)
        email_config = {
            'email': email,
            'setup_date': datetime.now().isoformat(),
            'reports_enabled': True
        }
        
        # Save to file for now (replace with database in production)
        import json
        try:
            with open('email_config.json', 'w') as f:
                json.dump(email_config, f)
        except Exception as e:
            logger.error(f"Failed to save email config: {e}")
        
        # Send test email notification
        from integrations.eva_email_integration import send_cost_report
        cost_summary = realtime_manager.get_cost_summary()
        report_data = {'cost_summary': cost_summary}
        send_cost_report(email, report_data, "setup")
        
        return jsonify({
            'success': True,
            'message': f'Email reports configured for {email}'
        })
        
    except Exception as e:
        logger.error(f"Error setting up email reports: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def send_cost_report_email(email, report_type="daily"):
    """Send cost report via email"""
    try:
        if not realtime_manager:
            return False
        
        cost_summary = realtime_manager.get_cost_summary()
        cost_tracker = get_realtime_tracker()
        
        if report_type == "setup":
            subject = "Eva Realtime - Email Reports Configured"
            message = f"""
            📧 Email Reports Setup Complete!
            
            You will now receive:
            • Daily cost summaries
            • Budget alerts
            • Session reports
            • Weekly usage trends
            
            Current Status:
            • Daily Cost: ${cost_summary['totals']['cost']:.4f}
            • Budget Remaining: ${cost_summary['remaining']['cost']:.2f}
            • Sessions Today: {cost_summary['totals']['sessions']}
            
            Dashboard: https://evarealtime-production.up.railway.app/dashboard
            
            🤖 Eva Realtime Cost Monitor
            """
        else:
            subject = f"Eva Realtime - {report_type.title()} Cost Report"
            sessions = cost_tracker.daily_data.get('sessions', [])
            
            message = f"""
            📊 Daily Cost Report - {datetime.now().strftime('%Y-%m-%d')}
            
            💰 Cost Summary:
            • Total Cost Today: ${cost_summary['totals']['cost']:.4f}
            • Budget Used: {(cost_summary['totals']['cost'] / cost_summary['limits']['max_cost_per_day'] * 100):.1f}%
            • Sessions: {cost_summary['totals']['sessions']}
            • Audio Time: {cost_summary['totals']['audio_seconds']:.1f}s
            
            🎯 Budget Status:
            • Daily Limit: ${cost_summary['limits']['max_cost_per_day']:.2f}
            • Remaining: ${cost_summary['remaining']['cost']:.2f}
            • Sessions Remaining: {cost_summary['remaining']['sessions']}
            
            📈 Recent Sessions:
            """
            
            for session in sessions[-5:]:  # Last 5 sessions
                start_time = datetime.fromisoformat(session['start_time']).strftime('%H:%M')
                message += f"• {start_time}: ${session['cost']:.4f} ({session['duration_seconds']}s)\n"
            
            message += f"""
            
            View detailed dashboard: https://evarealtime-production.up.railway.app/dashboard
            
            🤖 Eva Realtime Cost Monitor
            """
        
        # Here you would integrate with your email service
        # For now, we'll log the email content
        logger.info(f"EMAIL TO {email}: {subject}")
        logger.info(f"CONTENT: {message}")
        
        # You can integrate with:
        # - Resend API (like in original Eva)
        # - SendGrid
        # - AWS SES
        # - Or trigger Eva to send the email
        
        # For demo purposes, we'll simulate success
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to GPT-4o Realtime API server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")
    
    # End any active sessions for this client
    sessions_to_remove = []
    for session_id, session_info in active_sessions.items():
        if session_info['socket_id'] == request.sid:
            sessions_to_remove.append(session_id)
    
    for session_id in sessions_to_remove:
        asyncio.run(realtime_manager.end_session(session_id))
        del active_sessions[session_id]

@socketio.on('request_session')
def handle_request_session(data):
    """Handle session request"""
    if not realtime_manager:
        emit('error', {'message': 'Realtime manager not initialized'})
        return
    
    try:
        user_id = data.get('user_id', f'web_user_{uuid.uuid4().hex[:8]}')
        
        # Run async function in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        request_result = loop.run_until_complete(
            realtime_manager.request_realtime_session(user_id)
        )
        
        loop.close()
        
        if request_result.get('approved'):
            session_id = request_result['session_id']
            active_sessions[session_id] = {
                'socket_id': request.sid,
                'user_id': user_id,
                'start_time': datetime.now().isoformat()
            }
            
            emit('session_approved', {
                'session_id': session_id,
                'limits': request_result.get('limits', {}),
                'warnings': request_result.get('warnings', []),
                'daily_summary': request_result.get('daily_summary', {})
            })
        else:
            emit('session_denied', {
                'reason': request_result.get('reason', 'Unknown error'),
                'daily_summary': request_result.get('daily_summary', {})
            })
    
    except Exception as e:
        logger.error(f"Error requesting session: {e}")
        emit('error', {'message': str(e)})

@socketio.on('start_session')
def handle_start_session(data):
    """Handle session start"""
    if not realtime_manager:
        emit('error', {'message': 'Realtime manager not initialized'})
        return
    
    try:
        session_id = data.get('session_id')
        
        if session_id not in active_sessions:
            emit('error', {'message': 'Session not found'})
            return
        
        # Run async function in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        start_result = loop.run_until_complete(
            realtime_manager.start_realtime_session(session_id, user_confirmed=True)
        )
        
        loop.close()
        
        if start_result.get('started'):
            emit('session_starting', {
                'session_id': session_id,
                'message': 'Session starting...'
            })
        else:
            emit('session_start_failed', {
                'error': start_result.get('error', 'Unknown error')
            })
            
            # Remove from active sessions
            if session_id in active_sessions:
                del active_sessions[session_id]
    
    except Exception as e:
        logger.error(f"Error starting session: {e}")
        emit('error', {'message': str(e)})

@socketio.on('send_message')
def handle_send_message(data):
    """Handle sending a message"""
    if not realtime_manager:
        emit('error', {'message': 'Realtime manager not initialized'})
        return
    
    try:
        session_id = data.get('session_id')
        message = data.get('message', '').strip()
        
        if not message:
            emit('error', {'message': 'Message cannot be empty'})
            return
        
        if session_id not in active_sessions:
            emit('error', {'message': 'Session not found'})
            return
        
        # Run async function in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        send_result = loop.run_until_complete(
            realtime_manager.send_text_to_session(session_id, message)
        )
        
        loop.close()
        
        if send_result.get('text_sent'):
            emit('message_sent', {
                'message': message,
                'timestamp': datetime.now().isoformat()
            })
        else:
            emit('message_send_failed', {
                'error': send_result.get('error', 'Unknown error')
            })
    
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        emit('error', {'message': str(e)})

@socketio.on('end_session')
def handle_end_session(data):
    """Handle ending a session"""
    if not realtime_manager:
        emit('error', {'message': 'Realtime manager not initialized'})
        return
    
    try:
        session_id = data.get('session_id')
        
        if session_id not in active_sessions:
            emit('error', {'message': 'Session not found'})
            return
        
        # Run async function in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        end_result = loop.run_until_complete(
            realtime_manager.end_session(session_id)
        )
        
        loop.close()
        
        emit('session_ending', {
            'session_id': session_id,
            'summary': end_result.get('summary', {})
        })
        
        # Remove from active sessions
        if session_id in active_sessions:
            del active_sessions[session_id]
    
    except Exception as e:
        logger.error(f"Error ending session: {e}")
        emit('error', {'message': str(e)})

if __name__ == '__main__':
    # Check for required environment variables
    if not os.getenv('OPENAI_API_KEY'):
        logger.error("OPENAI_API_KEY environment variable not set")
        exit(1)
    
    # Initialize realtime manager
    init_realtime_manager()
    
    # Get port from environment (Railway provides this)
    port = int(os.getenv('PORT', 5000))
    
    logger.info(f"Starting GPT-4o Realtime API server on port {port}")
    logger.info("Dashboard available at /dashboard")
    
    # Run the app
    socketio.run(app, host='0.0.0.0', port=port, debug=False)