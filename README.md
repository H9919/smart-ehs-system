# 🛡️ Smart EHS Management System

AI-Powered Environment, Health, and Safety Management System with intelligent incident reporting, chemical safety management, and risk assessment capabilities.

## 🌟 Features

- 🤖 **AI-Powered Chat Interface** - Natural language processing for safety queries
- 🚨 **Intelligent Incident Reporting** - Guided workflows with automated risk assessment
- 📄 **SDS Management** - Chemical safety data sheet storage and intelligent search
- ⚠️ **Safety Concern Reporting** - Hazard identification and tracking system
- 📊 **Risk Assessment Matrix** - Multi-dimensional severity and likelihood calculations
- 📱 **Mobile Responsive Design** - Works perfectly on all devices
- 🌐 **Cloud Deployed** - Accessible anywhere via Render platform

## 🚀 Live Demo

This system is deployed and running live on Render:
**[🔗 Visit Live System](https://smart-ehs-system.onrender.com)** *(Update with your actual URL after deployment)*

## ⚡ Quick Start

### Option 1: Use Live System (Recommended)
Simply visit the live URL above - no installation required!
- Try: "I need to report an incident"
- Try: "Tell me about chemical safety"
- Try: "I have a safety concern"

### Option 2: Local Development
```bash
git clone https://github.com/YOUR_USERNAME/smart-ehs-system.git
cd smart-ehs-system
pip install -r requirements.txt
python app.py
```

Visit `http://localhost:5000`

## 🎯 How to Use

### 💬 Chat Interface Commands
- **"I need to report an incident"** → Starts guided incident reporting
- **"Tell me about chemical safety"** → Chemical and SDS information
- **"I have a safety concern"** → Safety hazard reporting
- **"Help me assess risk"** → Risk assessment tools
- **"Help"** → Complete system guide

### 📊 Dashboard Features
- **Real-time statistics** - Incident counts and system status
- **Quick action buttons** - One-click access to common functions
- **Responsive design** - Works on desktop, tablet, and mobile
- **Live updates** - Data refreshes automatically

## 🏗️ Technology Stack

- **Backend**: Python Flask with SQLite database
- **AI/ML**: Transformers, Sentence-BERT, PyTorch (CPU optimized)
- **Frontend**: HTML5, Tailwind CSS, vanilla JavaScript
- **Deployment**: Render cloud platform with auto-scaling
- **Security**: HTTPS, input validation, session management

## 📋 System Capabilities

### 🚨 Incident Management
- **Multiple incident types**: Injury/Illness, Near Miss, Property Damage, Environmental, Security
- **Automated risk scoring**: Using severity × likelihood matrix
- **Guided reporting workflows**: Step-by-step incident capture
- **Real-time notifications**: Immediate alerts for high-risk events

### 📄 Chemical Safety (SDS)
- **Intelligent search**: AI-powered chemical information retrieval
- **Safety recommendations**: Contextual PPE and handling guidance
- **Hazard identification**: Automated GHS and NFPA classification
- **Regulatory compliance**: OSHA, EPA, and international standards

### ⚠️ Safety Concerns
- **Proactive reporting**: Encourage hazard identification before incidents
- **Categorized tracking**: Equipment, environmental, procedural concerns
- **Follow-up workflows**: Automated corrective action assignment
- **Trend analysis**: Pattern recognition for prevention

### 📊 Risk Assessment
- **Multi-dimensional matrix**: People, Environment, Cost, Reputation, Legal
- **Automated calculations**: Risk score = Severity × Likelihood
- **Action recommendations**: Risk-based response suggestions
- **Audit trail**: Complete history of all assessments

## 🔧 Configuration

### Environment Variables
See `.env.example` for all available configuration options.

### Deployment Settings
Optimized for Render deployment with:
- Automatic dependency installation
- Database initialization on startup
- Health monitoring endpoints
- Production-ready security settings

## 🌐 Deployment Guide

### Deploy to Render (Recommended)
1. **Fork this repository** to your GitHub account
2. **Sign up at [render.com](https://render.com)** with GitHub
3. **Create new Web Service** → Connect this repository
4. **Configure service** (auto-detected from `render.yaml`)
5. **Deploy** → Get your live URL in 10-15 minutes

### Local Development
```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/smart-ehs-system.git
cd smart-ehs-system

# Install dependencies
pip install -r requirements.txt

# Run development server
python app.py
```

## 🔒 Security Features

- **HTTPS Everywhere**: Automatic SSL certificates via Render
- **Input Validation**: Protection against injection attacks
- **Session Security**: Secure cookie management
- **Audit Logging**: Complete activity tracking
- **Access Control**: Role-based permissions ready

## 📈 Performance & Scaling

- **CDN Distribution**: Global content delivery via Render
- **Auto-scaling**: Handles traffic spikes automatically
- **Optimized AI Models**: CPU-optimized for cloud deployment
- **Database Ready**: Easily upgradeable from SQLite to PostgreSQL
- **File Storage**: Ready for cloud storage integration (S3, etc.)

## 🤝 Contributing

### Development Guidelines
1. Fork the repository
2. Create feature branch: `git checkout -b feature-name`
3. Make changes and test thoroughly
4. Commit with descriptive messages
5. Push and create pull request

### Reporting Issues
- Use GitHub Issues for bug reports
- Include steps to reproduce
- Specify environment details
- Attach logs if applicable

## 📜 License

This Smart EHS Management System is designed for workplace safety management. 
See LICENSE file for terms and conditions.

## 📞 Support & Documentation

### Getting Help
- **Built-in Help**: Type "help" in the chat interface
- **Health Check**: Visit `/health` endpoint for system status
- **API Documentation**: Available at deployed URL
- **Community**: GitHub Discussions for questions

### System Status
- **Live Status**: Check health endpoint for real-time status
- **Performance**: Monitor response times in Render dashboard
- **Logs**: Access detailed logs via Render interface

---

## 🎉 Ready to Deploy?

1. **⭐ Star this repository** if you find it useful
2. **🍴 Fork to your GitHub** account
3. **🚀 Deploy to Render** following the guide above
4. **🛡️ Start managing safety** with AI-powered intelligence!

**Built with ❤️ for workplace safety • Powered by AI • Deployed on Render**

---

### 📊 Quick Stats
- **Lines of Code**: ~800+
- **AI Models**: 2 (Intent Classification + Semantic Search)
- **Database Tables**: 4 (Users, Incidents, SDS, Chat History)
- **API Endpoints**: 5+
- **Deployment Time**: ~15 minutes
- **Global Accessibility**: ✅
- **Mobile Friendly**: ✅
- **Production Ready**: ✅
