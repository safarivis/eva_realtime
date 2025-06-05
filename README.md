# 🤖 Eva Realtime - GPT-4o Realtime API Web Application

**A production-ready web application for testing OpenAI's GPT-4o Realtime API with comprehensive cost controls and safety features.**

> **What is this?** This is a standalone web application that provides a safe, cost-controlled interface to test and interact with OpenAI's new GPT-4o Realtime API. Built as part of the Eva AI assistant project, it includes enterprise-grade budget management and real-time cost monitoring.

## 🎯 **Purpose & Use Case**

This application was created to solve the challenge of safely testing OpenAI's expensive GPT-4o Realtime API ($0.06/minute input, $0.24/minute output) without accidentally running up large bills. It provides:

- **Safe Testing Environment** - Built-in cost limits prevent overspending
- **Real-time Monitoring** - Live cost tracking and usage dashboards  
- **Production Ready** - Enterprise-grade session management and error handling
- **Easy Deployment** - One-click Railway deployment with zero configuration

## Features

- 🎙️ Real-time text chat with GPT-4o
- 💰 Built-in cost tracking and budget controls
- 📊 Live usage dashboard
- 🛡️ Session limits and automatic cutoffs
- 🌐 Web-based interface (no installation needed)

## Cost Controls

- **Daily Budget**: $10.00 (configurable)
- **Session Limit**: $0.50 per session
- **Time Limit**: 5 minutes per session
- **Daily Sessions**: 50 sessions max
- **Real-time Monitoring**: Live cost tracking

## 🚀 **Quick Deploy to Railway**

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/gpt4o-realtime)

### **One-Click Deployment:**

1. **Click the Railway button above** or go to [Railway](https://railway.app)
2. **Connect this GitHub repository** 
3. **Set environment variables:**
   ```
   OPENAI_API_KEY=your-openai-api-key-here
   SECRET_KEY=any-random-string-for-flask-sessions
   ```
4. **Deploy!** - Railway automatically detects and builds the Flask app

### **Alternative: Railway CLI**

```bash
# Install Railway CLI
npm install -g @railway/cli

# Clone and deploy
git clone https://github.com/safarivis/eva_realtime.git
cd eva_realtime
railway login
railway init
railway deploy
```

### **Getting Your OpenAI API Key:**

1. Go to [OpenAI Platform](https://platform.openai.com/api-keys)
2. Create a new API key
3. **Important**: Add billing information and set usage limits
4. Copy the key to Railway environment variables

### Environment Variables

Required environment variables for Railway:

```
OPENAI_API_KEY=your-openai-api-key-here
SECRET_KEY=your-secret-flask-key-here
PORT=5000
```

## Local Development

```bash
cd realtime_app
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000

## Usage

1. **Start Session**: Click "Start Session" to begin
2. **Chat**: Type messages and get real-time responses
3. **Monitor Costs**: Watch the sidebar for usage tracking
4. **End Session**: Click "End Session" when done

## Cost Estimates

- ~$0.30/minute for typical conversations
- Text-only mode (audio disabled for web demo)
- Automatic session termination when limits reached

## Security Notes

- API keys are server-side only
- Session-based user management
- Automatic cleanup on disconnect
- Rate limiting built-in

## Tech Stack

- **Backend**: Flask + SocketIO
- **Frontend**: Vanilla JavaScript + WebSockets
- **Integration**: GPT-4o Realtime API via WebSockets
- **Deployment**: Railway (Nixpacks)