import os
import sys
import logging
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, session
import sqlite3
from datetime import datetime
import json
import uuid
import hashlib
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create necessary directories
for directory in ['static/uploads', 'static/exports', 'static/labels', 'data']:
    Path(directory).mkdir(parents=True, exist_ok=True)

class SmartEHSSystem:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ehs-secret-key-2024')
        self.app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
        
        # Initialize database
        self.setup_database()
        
        # Load scoring matrices
        self.load_scoring_data()
        
        # Setup routes
        self.setup_routes()
        
        # Initialize without heavy AI libraries for now
        self.ai_enabled = False
        self.sentence_model = None
        self.intent_classifier = None
        
        logger.info("Smart EHS System initialized successfully")
    
    def setup_database(self):
        """Setup SQLite database"""
        db_path = 'data/smart_ehs.db'
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'contributor',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Incidents table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                location TEXT,
                severity_people INTEGER DEFAULT 0,
                severity_environment INTEGER DEFAULT 0,
                severity_cost INTEGER DEFAULT 0,
                severity_reputation INTEGER DEFAULT 0,
                severity_legal INTEGER DEFAULT 0,
                likelihood_score INTEGER DEFAULT 0,
                risk_score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # SDS Documents table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sds_documents (
                id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                manufacturer TEXT,
                file_path TEXT,
                full_text TEXT,
                ghs_info TEXT,
                nfpa_info TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Chat history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                intent TEXT,
                confidence REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert default admin user
        cursor.execute('''
            INSERT OR IGNORE INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
        ''', ('admin', 'pbkdf2:sha256:260000$salt$hash', 'admin'))
        
        conn.commit()
        conn.close()
        logger.info("Database setup completed")
    
    def load_scoring_data(self):
        """Load severity and likelihood scales"""
        # Default likelihood scale
        self.likelihood_scale = {
            0: {'label': 'Impossible', 'description': 'Cannot happen'},
            2: {'label': 'Rare', 'description': 'Extremely unlikely'},
            4: {'label': 'Unlikely', 'description': 'Could happen exceptionally'},
            6: {'label': 'Possible', 'description': 'Might happen occasionally'},
            8: {'label': 'Likely', 'description': 'Expected to happen'},
            10: {'label': 'Almost Certain', 'description': 'Will almost certainly happen'}
        }
        
        # Default severity scale
        self.severity_scale = {
            'people': {
                0: {'description': 'No injury', 'keywords': ['safe', 'no harm']},
                2: {'description': 'First aid only', 'keywords': ['minor', 'first aid']},
                4: {'description': 'Medical treatment', 'keywords': ['medical', 'treatment']},
                6: {'description': 'Hospitalization', 'keywords': ['hospital', 'serious']},
                8: {'description': 'Permanent disability', 'keywords': ['disability']},
                10: {'description': 'Fatality', 'keywords': ['death', 'fatal']}
            },
            'environment': {
                0: {'description': 'No environmental impact', 'keywords': ['clean', 'contained']},
                4: {'description': 'Minor spill/leak', 'keywords': ['small spill', 'minor']},
                8: {'description': 'Major environmental damage', 'keywords': ['major spill', 'contamination']}
            }
        }
    
    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            return self.get_main_template()
        
        @self.app.route('/health')
        def health():
            return jsonify({
                'status': 'healthy',
                'ai_enabled': self.ai_enabled,
                'timestamp': datetime.now().isoformat()
            })
        
        @self.app.route('/api/chat', methods=['POST'])
        def chat():
            return self.handle_chat()
        
        @self.app.route('/api/incident', methods=['POST'])
        def create_incident():
            return self.create_incident()
        
        @self.app.route('/api/dashboard-stats')
        def dashboard_stats():
            return self.get_dashboard_stats()
    
    def handle_chat(self):
        """Handle chat messages"""
        try:
            data = request.get_json()
            message = data.get('message', '').lower()
            
            # Classify intent
            intent = self.classify_intent(message)
            
            # Generate response based on intent
            if intent == 'report_incident':
                response = self.incident_response()
            elif intent == 'sds_query':
                response = self.sds_response()
            elif intent == 'safety_concern':
                response = self.safety_response()
            elif intent == 'help':
                response = self.help_response()
            else:
                response = self.default_response()
            
            # Store in chat history
            self.store_chat_history(data.get('message', ''), response, intent)
            
            return jsonify({
                'response': response,
                'intent': intent,
                'ai_enabled': self.ai_enabled,
                'confidence': 0.8
            })
            
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return jsonify({
                'response': 'Sorry, I encountered an error. Please try again.',
                'error': True
            })
    
    def classify_intent(self, message):
        """Classify user intent using keyword matching"""
        message_lower = message.lower()
        
        # Enhanced keyword-based classification
        incident_keywords = ['incident', 'accident', 'injury', 'hurt', 'injured', 'report', 'happened', 'occurred']
        sds_keywords = ['sds', 'chemical', 'safety data', 'hazard', 'msds', 'substance', 'material']
        safety_keywords = ['safety', 'concern', 'unsafe', 'dangerous', 'risk', 'hazard', 'observe', 'noticed']
        help_keywords = ['help', 'what', 'how', 'can you', 'assist', 'guide', 'explain']
        
        # Score each intent
        scores = {
            'report_incident': sum(1 for word in incident_keywords if word in message_lower),
            'sds_query': sum(1 for word in sds_keywords if word in message_lower),
            'safety_concern': sum(1 for word in safety_keywords if word in message_lower),
            'help': sum(1 for word in help_keywords if word in message_lower)
        }
        
        # Return the intent with highest score
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        else:
            return 'general'
    
    def incident_response(self):
        return """🚨 **Incident Reporting**

I can help you report an incident. Please provide:

1. **Type of incident**:
   - Injury/Illness
   - Near Miss
   - Property Damage
   - Environmental (spill/leak)
   - Security Issue

2. **Location**: Where did it happen?
3. **Description**: What happened?
4. **When**: Date and time

Example: "There was a chemical spill in Laboratory A at 2:30 PM today"

For immediate emergencies, contact emergency services first!"""

    def sds_response(self):
        return """📄 **Safety Data Sheet Information**

I can help you with chemical safety information. You can:

1. **Ask about specific chemicals**:
   - "What are the hazards of acetone?"
   - "How should I store methanol?"
   - "What PPE is needed for sulfuric acid?"

2. **Upload SDS documents** (coming soon)
3. **Generate safety labels** (GHS/NFPA format)

What chemical or safety information do you need?"""

    def safety_response(self):
        return """⚠️ **Safety Concerns**

Report any unsafe conditions or behaviors you observe:

**Common Safety Concerns**:
- Unsafe equipment or machinery
- Missing or damaged PPE
- Blocked emergency exits
- Chemical storage issues
- Environmental hazards

**What to include**:
- Location of the concern
- Description of the hazard
- Potential consequences
- Suggested solutions"""

    def help_response(self):
        return """🛡️ **Smart EHS System Help**

**I can assist with**:
- 🚨 **Incident Reporting**: Report workplace accidents, injuries, near misses
- 📄 **SDS Management**: Chemical safety information and documentation
- ⚠️ **Safety Concerns**: Report unsafe conditions or behaviors
- 📊 **Risk Assessment**: Evaluate and manage workplace risks

**Quick Commands**:
- "Report an incident" - Start incident reporting
- "Chemical safety info" - Get SDS information
- "Safety concern" - Report hazards
- "Help me assess risk" - Risk assessment tools

How can I help you stay safe today?"""

    def default_response(self):
        return """👋 Hello! I'm your Smart EHS Assistant.

I can help you with:
- 🚨 Report incidents and accidents
- 📄 Find chemical safety information
- ⚠️ Report safety concerns
- 📊 Assess workplace risks

Try saying:
- "I need to report an incident"
- "Tell me about chemical safety"
- "I have a safety concern"
- "Help me with risk assessment"

What can I help you with today?"""
    
    def store_chat_history(self, message, response, intent):
        """Store chat interaction in database"""
        try:
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO chat_history (message, response, intent, confidence)
                VALUES (?, ?, ?, ?)
            ''', (message, response, intent, 0.8))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing chat history: {e}")
    
    def create_incident(self):
        """Create new incident"""
        try:
            data = request.get_json()
            incident_id = str(uuid.uuid4())
            
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO incidents (
                    id, type, title, description, location,
                    severity_people, severity_environment, severity_cost,
                    severity_reputation, severity_legal, likelihood_score, risk_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                incident_id,
                data.get('type', 'general'),
                data.get('title', 'Incident Report'),
                data.get('description', ''),
                data.get('location', ''),
                data.get('severity_people', 0),
                data.get('severity_environment', 0),
                data.get('severity_cost', 0),
                data.get('severity_reputation', 0),
                data.get('severity_legal', 0),
                data.get('likelihood', 0),
                data.get('risk_score', 0)
            ))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'incident_id': incident_id,
                'message': 'Incident reported successfully'
            })
            
        except Exception as e:
            logger.error(f"Error creating incident: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    def get_dashboard_stats(self):
        """Get dashboard statistics"""
        try:
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            # Count incidents
            cursor.execute('SELECT COUNT(*) FROM incidents')
            total_incidents = cursor.fetchone()[0]
            
            # Count SDS documents
            cursor.execute('SELECT COUNT(*) FROM sds_documents')
            total_sds = cursor.fetchone()[0]
            
            # Get recent incidents
            cursor.execute('''
                SELECT type, created_at FROM incidents 
                ORDER BY created_at DESC LIMIT 5
            ''')
            recent_incidents = cursor.fetchall()
            
            conn.close()
            
            return jsonify({
                'total_incidents': total_incidents,
                'total_sds_documents': total_sds,
                'pending_actions': 0,
                'high_risk_items': 0,
                'recent_incidents': [
                    {'type': r[0], 'date': r[1]} for r in recent_incidents
                ]
            })
            
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {e}")
            return jsonify({'error': str(e)})
    
    def get_main_template(self):
        """Return main HTML template"""
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart EHS Management System</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        .chat-message { animation: fadeIn 0.3s ease-in; margin-bottom: 1rem; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .ai-response { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .user-message { background: #3b82f6; color: white; margin-left: 2rem; }
    </style>
</head>

<body class="bg-gray-50 min-h-screen">
    <!-- Header -->
    <header class="bg-white shadow-md">
        <div class="max-w-7xl mx-auto px-4 py-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <i class="fas fa-shield-alt text-blue-600 text-2xl"></i>
                    <h1 class="text-2xl font-bold text-gray-800">Smart EHS System</h1>
                    <span class="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">
                        Live on Render
                    </span>
                </div>
            </div>
        </div>
    </header>

    <!-- Main Content -->
    <div class="max-w-7xl mx-auto px-4 py-8">
        <!-- Title Section -->
        <div class="text-center mb-8">
            <h2 class="text-4xl font-bold text-gray-800 mb-2">
                🛡️ Smart EHS Management System
            </h2>
            <p class="text-gray-600 text-lg">AI-Powered Safety Management • Incident Reporting • Chemical Safety</p>
        </div>

        <!-- Dashboard Stats -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div class="bg-white rounded-lg shadow p-6">
                <div class="flex items-center">
                    <i class="fas fa-exclamation-triangle text-red-500 text-2xl"></i>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Total Incidents</p>
                        <p class="text-2xl font-semibold text-gray-900" id="totalIncidents">0</p>
                    </div>
                </div>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <div class="flex items-center">
                    <i class="fas fa-file-alt text-blue-500 text-2xl"></i>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">SDS Documents</p>
                        <p class="text-2xl font-semibold text-gray-900" id="totalSDS">0</p>
                    </div>
                </div>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <div class="flex items-center">
                    <i class="fas fa-tasks text-yellow-500 text-2xl"></i>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">Pending Actions</p>
                        <p class="text-2xl font-semibold text-gray-900" id="pendingActions">0</p>
                    </div>
                </div>
            </div>
            <div class="bg-white rounded-lg shadow p-6">
                <div class="flex items-center">
                    <i class="fas fa-heartbeat text-green-500 text-2xl"></i>
                    <div class="ml-4">
                        <p class="text-sm font-medium text-gray-500">System Status</p>
                        <p class="text-2xl font-semibold text-gray-900">Online</p>
                    </div>
                </div>
            </div>
        </div>

        <!-- Chat Interface -->
        <div class="grid grid-cols-1 lg:grid-cols-1 gap-8">
            <div class="bg-white rounded-lg shadow">
                <div class="p-6 border-b border-gray-200">
                    <div class="flex items-center space-x-3">
                        <i class="fas fa-robot text-blue-600 text-xl"></i>
                        <h3 class="text-lg font-semibold text-gray-800">EHS Assistant</h3>
                        <span class="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">
                            AI Powered
                        </span>
                    </div>
                </div>
                <div class="h-96 overflow-y-auto p-6 space-y-4" id="chatContainer">
                    <!-- Welcome Message -->
                    <div class="chat-message ai-response p-4 rounded-lg max-w-4/5">
                        <div class="flex items-start space-x-3">
                            <div class="flex-shrink-0">
                                <i class="fas fa-robot text-white"></i>
                            </div>
                            <div class="flex-1">
                                <div class="flex items-center space-x-2 mb-1">
                                    <span class="font-semibold">EHS Assistant</span>
                                    <span class="text-xs opacity-75">Just now</span>
                                </div>
                                <div>Welcome to the Smart EHS System! I can help you with:
                                <ul class="mt-2 space-y-1">
                                    <li>• 🚨 Report incidents - workplace injuries, accidents, near misses</li>
                                    <li>• 📄 Chemical safety - SDS information and hazard data</li>
                                    <li>• ⚠️ Safety concerns - hazard identification and reporting</li>
                                    <li>• 📊 Risk assessment - evaluate workplace risks</li>
                                </ul>
                                <p class="mt-2">Try: "I need to report an incident" or "Tell me about chemical safety"</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="p-6 border-t border-gray-200">
                    <div class="flex space-x-4">
                        <input 
                            type="text" 
                            id="chatInput"
                            placeholder="Ask about safety, report incidents, or get help..."
                            class="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                        <button 
                            id="sendBtn"
                            class="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                            <i class="fas fa-paper-plane"></i>
                        </button>
                    </div>
                    <div class="mt-3 flex flex-wrap gap-2">
                        <button onclick="sendQuickMessage('I need to report an incident')" 
                                class="bg-gray-100 text-gray-700 px-3 py-1 rounded-full text-sm hover:bg-gray-200">
                            Report Incident
                        </button>
                        <button onclick="sendQuickMessage('Tell me about chemical safety')" 
                                class="bg-gray-100 text-gray-700 px-3 py-1 rounded-full text-sm hover:bg-gray-200">
                            Chemical Safety
                        </button>
                        <button onclick="sendQuickMessage('I have a safety concern')" 
                                class="bg-gray-100 text-gray-700 px-3 py-1 rounded-full text-sm hover:bg-gray-200">
                            Safety Concern
                        </button>
                        <button onclick="sendQuickMessage('Help me assess risk')" 
                                class="bg-gray-100 text-gray-700 px-3 py-1 rounded-full text-sm hover:bg-gray-200">
                            Risk Assessment
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            loadDashboardStats();
            setupEventListeners();
        });

        function setupEventListeners() {
            document.getElementById('sendBtn').addEventListener('click', sendMessage);
            document.getElementById('chatInput').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') sendMessage();
            });
        }

        function sendQuickMessage(message) {
            document.getElementById('chatInput').value = message;
            sendMessage();
        }

        async function sendMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            
            if (!message) return;
            
            addChatMessage('You', message, 'user-message');
            input.value = '';
            
            const typingId = addChatMessage('Assistant', 'Thinking...', 'ai-response opacity-50');
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });
                
                const result = await response.json();
                
                document.getElementById(typingId).remove();
                addChatMessage('EHS Assistant', result.response, 'ai-response');
                
            } catch (error) {
                document.getElementById(typingId).remove();
                addChatMessage('Assistant', 'Sorry, I encountered an error. Please try again.', 'ai-response');
                console.error('Chat error:', error);
            }
        }

        function addChatMessage(sender, message, className) {
            const chatContainer = document.getElementById('chatContainer');
            const messageDiv = document.createElement('div');
            const messageId = 'msg-' + Date.now();
            
            messageDiv.id = messageId;
            messageDiv.className = `chat-message ${className} p-4 rounded-lg max-w-4/5`;
            
            if (className.includes('user-message')) {
                messageDiv.classList.add('ml-auto');
            }
            
            const icon = sender === 'You' ? 'fas fa-user' : 'fas fa-robot';
            
            messageDiv.innerHTML = `
                <div class="flex items-start space-x-3">
                    <div class="flex-shrink-0">
                        <i class="${icon}"></i>
                    </div>
                    <div class="flex-1">
                        <div class="flex items-center space-x-2 mb-1">
                            <span class="font-semibold">${sender}</span>
                            <span class="text-xs opacity-75">${new Date().toLocaleTimeString()}</span>
                        </div>
                        <div class="whitespace-pre-wrap">${message}</div>
                    </div>
                </div>
            `;
            
            chatContainer.appendChild(messageDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
            
            return messageId;
        }

        async function loadDashboardStats() {
            try {
                const response = await fetch('/api/dashboard-stats');
                const stats = await response.json();
                
                document.getElementById('totalIncidents').textContent = stats.total_incidents;
                document.getElementById('totalSDS').textContent = stats.total_sds_documents;
                document.getElementById('pendingActions').textContent = stats.pending_actions;
                
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }
    </script>
</body>
</html>'''

# Create the Flask app instance
app = SmartEHSSystem().app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
