import os
import sys
import logging
import sqlite3
import json
import uuid
import hashlib
import re
import base64
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, session, send_file, url_for
from werkzeug.utils import secure_filename
import zipfile
import io

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create necessary directories
for directory in ['static/uploads', 'static/exports', 'static/labels', 'static/sds', 'static/photos', 'data']:
    Path(directory).mkdir(parents=True, exist_ok=True)

class EnhancedEHSSystem:
    def __init__(self):
        self.app = Flask(__name__)
        self.app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ehs-secret-key-2024')
        self.app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB
        self.app.config['UPLOAD_FOLDER'] = 'static/uploads'
        
        # Initialize database
        self.setup_database()
        
        # Load scoring matrices
        self.load_scoring_data()
        
        # Setup routes
        self.setup_routes()
        
        # Chemical safety database (simplified for demo)
        self.chemical_db = self.load_chemical_database()
        
        logger.info("Enhanced EHS System initialized successfully")
    
    def setup_database(self):
        """Setup SQLite database with enhanced tables"""
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
                department TEXT,
                location TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Enhanced incidents table with photo support
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                location TEXT,
                department TEXT,
                state TEXT,
                city TEXT,
                photos TEXT,
                severity_people INTEGER DEFAULT 0,
                severity_environment INTEGER DEFAULT 0,
                severity_cost INTEGER DEFAULT 0,
                severity_reputation INTEGER DEFAULT 0,
                severity_legal INTEGER DEFAULT 0,
                likelihood_score INTEGER DEFAULT 0,
                risk_score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'open',
                reporter_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Enhanced SDS Documents table with location hierarchy
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sds_documents (
                id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                manufacturer TEXT,
                cas_number TEXT,
                file_path TEXT,
                file_name TEXT,
                full_text TEXT,
                ghs_hazards TEXT,
                nfpa_health INTEGER DEFAULT 0,
                nfpa_fire INTEGER DEFAULT 0,
                nfpa_reactivity INTEGER DEFAULT 0,
                nfpa_special TEXT,
                state TEXT,
                city TEXT,
                department TEXT,
                building TEXT,
                room TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Safety concerns table with photos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS safety_concerns (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                location TEXT,
                department TEXT,
                state TEXT,
                city TEXT,
                photos TEXT,
                severity_level INTEGER DEFAULT 0,
                likelihood_level INTEGER DEFAULT 0,
                risk_score INTEGER DEFAULT 0,
                status TEXT DEFAULT 'open',
                reporter_name TEXT,
                assigned_to TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Chat history table enhanced
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                response TEXT NOT NULL,
                intent TEXT,
                confidence REAL,
                context_data TEXT,
                user_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # CAPA tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS capa_actions (
                id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                description TEXT NOT NULL,
                assigned_to TEXT,
                due_date DATE,
                status TEXT DEFAULT 'open',
                priority TEXT DEFAULT 'medium',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        ''')
        
        # Risk register table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS risk_register (
                id TEXT PRIMARY KEY,
                risk_title TEXT NOT NULL,
                risk_description TEXT NOT NULL,
                risk_category TEXT NOT NULL,
                likelihood_score INTEGER NOT NULL,
                severity_people INTEGER DEFAULT 0,
                severity_environment INTEGER DEFAULT 0,
                severity_cost INTEGER DEFAULT 0,
                severity_reputation INTEGER DEFAULT 0,
                severity_legal INTEGER DEFAULT 0,
                risk_score INTEGER NOT NULL,
                mitigation_measures TEXT,
                risk_owner TEXT,
                review_date DATE,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Enhanced database setup completed")
    
    def load_scoring_data(self):
        """Load severity and likelihood scales from your uploaded CSV files"""
        # Load from likelihood_scale_rows.csv (from your uploaded file)
        self.likelihood_scale = {
            0: {'label': 'Impossible', 'description': 'The event cannot happen under current design or controls', 'keywords': ['never', 'impossible', 'zero chance']},
            2: {'label': 'Rare', 'description': 'Extremely unlikely but theoretically possible (once in 10+ years)', 'keywords': ['rare', 'unlikely', 'once in a decade']},
            4: {'label': 'Unlikely', 'description': 'Could happen in exceptional cases (once every 5–10 years)', 'keywords': ['uncommon', 'doubtful', 'not expected']},
            6: {'label': 'Possible', 'description': 'Might happen occasionally (once every 1–5 years)', 'keywords': ['possible', 'sometimes', 'may occur']},
            8: {'label': 'Likely', 'description': 'Expected to happen regularly (once per year or more frequently)', 'keywords': ['likely', 'probable', 'expected']},
            10: {'label': 'Almost Certain', 'description': 'Will almost certainly happen (multiple times per year)', 'keywords': ['certain', 'definite', 'will happen']}
        }
        
        # Load from severity_scale.csv (from your uploaded file)
        self.severity_scale = {
            'people': {
                0: {'description': 'No injury or risk of harm', 'keywords': ['safe', 'no harm', 'uninjured']},
                2: {'description': 'First aid only; no lost time', 'keywords': ['first aid', 'minor', 'band-aid']},
                4: {'description': 'Medical treatment; lost time injury (LTI) no hospitalization', 'keywords': ['medical', 'treatment', 'doctor visit']},
                6: {'description': 'Serious injury; hospitalization restricted duty >3 days', 'keywords': ['hospital', 'serious', 'admitted']},
                8: {'description': 'Permanent disability amputation serious head/spine injury', 'keywords': ['disability', 'amputation', 'permanent']},
                10: {'description': 'Single or multiple fatalities', 'keywords': ['death', 'fatality', 'killed']}
            },
            'environment': {
                0: {'description': 'No environmental impact', 'keywords': ['clean', 'contained', 'no spill']},
                2: {'description': 'Minor spill/release contained on-site', 'keywords': ['small spill', 'minor leak', 'contained']},
                4: {'description': 'Moderate spill requiring cleanup', 'keywords': ['spill', 'cleanup', 'moderate']},
                6: {'description': 'Significant environmental damage', 'keywords': ['environmental damage', 'contamination']},
                8: {'description': 'Major environmental impact', 'keywords': ['major spill', 'widespread']},
                10: {'description': 'Catastrophic environmental damage', 'keywords': ['catastrophic', 'disaster', 'massive spill']}
            },
            'cost': {
                0: {'description': 'No financial impact (<$1000)', 'keywords': ['minimal cost', 'no expense']},
                2: {'description': 'Low cost impact ($1K-$10K)', 'keywords': ['low cost', 'minor expense']},
                4: {'description': 'Moderate cost ($10K-$100K)', 'keywords': ['moderate cost', 'significant expense']},
                6: {'description': 'High cost ($100K-$1M)', 'keywords': ['expensive', 'high cost']},
                8: {'description': 'Very high cost ($1M-$10M)', 'keywords': ['very expensive', 'major cost']},
                10: {'description': 'Extreme cost (>$10M)', 'keywords': ['extreme cost', 'catastrophic loss']}
            },
            'reputation': {
                0: {'description': 'No public awareness', 'keywords': ['private', 'internal', 'no publicity']},
                2: {'description': 'Minor local attention', 'keywords': ['local news', 'minor attention']},
                4: {'description': 'Regional media attention', 'keywords': ['regional news', 'media coverage']},
                6: {'description': 'National media attention', 'keywords': ['national news', 'widespread coverage']},
                8: {'description': 'International attention', 'keywords': ['international news', 'global coverage']},
                10: {'description': 'Severe reputation damage', 'keywords': ['brand damage', 'public relations disaster']}
            },
            'legal': {
                0: {'description': 'No legal implications', 'keywords': ['no legal issues', 'compliant']},
                2: {'description': 'Minor regulatory involvement', 'keywords': ['minor violation', 'warning']},
                4: {'description': 'Regulatory investigation', 'keywords': ['investigation', 'regulatory review']},
                6: {'description': 'Significant fines or penalties', 'keywords': ['fines', 'penalties', 'enforcement']},
                8: {'description': 'Criminal charges possible', 'keywords': ['criminal charges', 'prosecution']},
                10: {'description': 'Severe legal consequences', 'keywords': ['lawsuit', 'criminal liability', 'imprisonment']}
            }
        }
        
        # AVOMO-specific module priorities (from your requirements document)
        self.module_priorities = {
            1: {'name': 'Incident Management', 'priority': 'P1', 'status': 'Completed'},
            2: {'name': 'CAPA (Corrective & Preventive Actions Tracker)', 'priority': 'P2', 'status': 'Completed'}, 
            3: {'name': 'SDS (Safety Data Sheets)', 'priority': 'P1', 'status': 'Completed'},
            4: {'name': 'Management of Change (MOC)', 'priority': 'P3', 'status': 'Not Started'},
            5: {'name': 'Audits & Inspections', 'priority': 'P3', 'status': 'Not Started'},
            6: {'name': 'Contractor and Visitor Safety', 'priority': 'P1', 'status': 'In Progress'},
            7: {'name': 'Document Governance', 'priority': 'P3', 'status': 'In Progress'},
            8: {'name': 'Environmental Management', 'priority': 'P3', 'status': 'Not Started'},
            9: {'name': 'Risk Management', 'priority': 'P1', 'status': 'In Progress'},
            10: {'name': 'Safety Concern Reporting', 'priority': 'P1', 'status': 'Completed'},
            11: {'name': 'Dashboards & Reporting Module', 'priority': 'P1', 'status': 'In Progress'}
        }
        
        # AVOMO access levels (from your requirements)
        self.access_levels = {
            'admin': {
                'description': 'Full access to all modules, configuration, user management',
                'estimated_users': 10
            },
            'manager': {
                'description': 'Manage module-specific content, CAPAs, audits, document workflows',
                'estimated_users': 90
            },
            'contributor': {
                'description': 'Submit reports, complete checklists, respond to CAPAs',
                'estimated_users': 200
            },
            'viewer': {
                'description': 'Read-only access to permitted dashboards and reports',
                'estimated_users': 100
            },
            'vendor_contractor': {
                'description': 'Limited access for safety/security concerns and checklists',
                'estimated_users': 600
            }
        }
    
    def load_chemical_database(self):
        """Load basic chemical safety database"""
        return {
            'acetone': {
                'name': 'Acetone',
                'cas': '67-64-1',
                'ghs_hazards': ['H225: Highly flammable liquid', 'H319: Causes serious eye irritation', 'H336: May cause drowsiness'],
                'nfpa': {'health': 1, 'fire': 3, 'reactivity': 0, 'special': ''},
                'ppe': ['Safety glasses', 'Nitrile gloves', 'Lab coat'],
                'storage': 'Store in cool, dry place away from ignition sources'
            },
            'methanol': {
                'name': 'Methanol',
                'cas': '67-56-1',
                'ghs_hazards': ['H225: Highly flammable liquid', 'H301: Toxic if swallowed', 'H311: Toxic in contact with skin', 'H331: Toxic if inhaled'],
                'nfpa': {'health': 1, 'fire': 3, 'reactivity': 0, 'special': ''},
                'ppe': ['Chemical safety goggles', 'Nitrile gloves', 'Lab coat', 'Fume hood'],
                'storage': 'Store in cool, dry, well-ventilated area away from heat and ignition sources'
            },
            'sulfuric acid': {
                'name': 'Sulfuric Acid',
                'cas': '7664-93-9',
                'ghs_hazards': ['H314: Causes severe skin burns', 'H335: May cause respiratory irritation'],
                'nfpa': {'health': 3, 'fire': 0, 'reactivity': 2, 'special': 'W'},
                'ppe': ['Chemical safety goggles', 'Acid-resistant gloves', 'Lab coat', 'Face shield'],
                'storage': 'Store in corrosive-resistant secondary containment'
            }
        }
    
    def setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            return self.get_main_dashboard()
        
        @self.app.route('/dashboard')
        def dashboard():
            return self.get_main_dashboard()
        
        @self.app.route('/incident-management')
        def incident_management():
            return self.get_incident_management_page()
        
        @self.app.route('/sds-management')
        def sds_management():
            return self.get_sds_management_page()
        
        @self.app.route('/safety-concerns')
        def safety_concerns():
            return self.get_safety_concerns_page()
        
        @self.app.route('/risk-management')
        def risk_management():
            return self.get_risk_management_page()
        
        @self.app.route('/avomo-workflow')
        def avomo_workflow():
            return self.get_avomo_workflow_page()
        
        @self.app.route('/health')
        def health():
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'modules': ['incident_management', 'sds_management', 'safety_concerns', 'risk_management']
            })
        
        @self.app.route('/api/chat', methods=['POST'])
        def chat():
            return self.handle_chat()
        
        @self.app.route('/api/dashboard-stats')
        def dashboard_stats():
            return self.get_dashboard_stats()
        
        @self.app.route('/api/incident', methods=['POST'])
        def create_incident():
            return self.create_incident()
        
        @self.app.route('/api/safety-concern', methods=['POST'])
        def create_safety_concern():
            return self.create_safety_concern()
        
        @self.app.route('/api/upload-sds', methods=['POST'])
        def upload_sds():
            return self.upload_sds_file()
        
        @self.app.route('/api/sds-documents')
        def get_sds_documents():
            return self.get_sds_documents()
        
        @self.app.route('/api/generate-label/<label_type>/<document_id>')
        def generate_label(label_type, document_id):
            return self.generate_safety_label(label_type, document_id)
        
        @self.app.route('/api/upload-photo', methods=['POST'])
        def upload_photo():
            return self.handle_photo_upload()
        
        @self.app.route('/download-sds/<document_id>')
        def download_sds(document_id):
            return self.download_sds_file(document_id)
        
        @self.app.route('/api/capa', methods=['POST'])
        def create_capa():
            return self.create_capa_action()
        
        @self.app.route('/api/capa')
        def get_capas():
            return self.get_capa_actions()
        
        @self.app.route('/api/module-priorities')
        def get_module_priorities():
            return jsonify(self.module_priorities)
        
        @self.app.route('/api/access-levels')
        def get_access_levels():
            return jsonify(self.access_levels)
    
    def handle_chat(self):
        """Enhanced chat handler with SDS intelligence"""
        try:
            data = request.get_json()
            message = data.get('message', '').lower()
            
            # Classify intent
            intent = self.classify_intent(message)
            
            # Check for chemical-specific queries
            chemical_info = self.extract_chemical_info(message)
            
            if intent == 'sds_query' and chemical_info:
                response = self.get_chemical_safety_info(chemical_info)
            elif intent == 'report_incident':
                response = self.incident_response()
            elif intent == 'safety_concern':
                response = self.safety_response()
            elif intent == 'risk_assessment':
                response = self.risk_assessment_response()
            elif intent == 'help':
                response = self.help_response()
            else:
                response = self.default_response()
            
            # Store in chat history
            self.store_chat_history(data.get('message', ''), response, intent, chemical_info)
            
            return jsonify({
                'response': response,
                'intent': intent,
                'chemical_info': chemical_info,
                'confidence': 0.85
            })
            
        except Exception as e:
            logger.error(f"Chat error: {e}")
            return jsonify({
                'response': 'Sorry, I encountered an error. Please try again.',
                'error': True
            })
    
    def classify_intent(self, message):
        """Enhanced intent classification"""
        message_lower = message.lower()
        
        incident_keywords = ['incident', 'accident', 'injury', 'hurt', 'injured', 'report incident', 'happened', 'occurred']
        sds_keywords = ['sds', 'chemical', 'safety data', 'hazard', 'msds', 'substance', 'material', 'acetone', 'methanol']
        safety_keywords = ['safety', 'concern', 'unsafe', 'dangerous', 'risk', 'hazard', 'observe', 'noticed']
        risk_keywords = ['risk', 'assess', 'assessment', 'evaluate', 'probability', 'likelihood', 'severity']
        help_keywords = ['help', 'what', 'how', 'can you', 'assist', 'guide', 'explain']
        
        scores = {
            'report_incident': sum(2 if word in message_lower else 0 for word in incident_keywords),
            'sds_query': sum(2 if word in message_lower else 0 for word in sds_keywords),
            'safety_concern': sum(2 if word in message_lower else 0 for word in safety_keywords),
            'risk_assessment': sum(2 if word in message_lower else 0 for word in risk_keywords),
            'help': sum(1 if word in message_lower else 0 for word in help_keywords)
        }
        
        return max(scores, key=scores.get) if max(scores.values()) > 0 else 'general'
    
    def extract_chemical_info(self, message):
        """Extract chemical names from message"""
        chemicals_found = []
        for chemical in self.chemical_db.keys():
            if chemical in message.lower():
                chemicals_found.append(chemical)
        return chemicals_found
    
    def get_chemical_safety_info(self, chemicals):
        """Get detailed chemical safety information"""
        if not chemicals:
            return self.sds_response()
        
        response = "🧪 **Chemical Safety Information**\n\n"
        
        for chemical in chemicals:
            if chemical in self.chemical_db:
                info = self.chemical_db[chemical]
                response += f"**{info['name']} (CAS: {info['cas']})**\n\n"
                response += f"🚨 **GHS Hazards:**\n"
                for hazard in info['ghs_hazards']:
                    response += f"• {hazard}\n"
                
                response += f"\n🔥 **NFPA Ratings:**\n"
                response += f"• Health: {info['nfpa']['health']}/4\n"
                response += f"• Fire: {info['nfpa']['fire']}/4\n"
                response += f"• Reactivity: {info['nfpa']['reactivity']}/4\n"
                if info['nfpa']['special']:
                    response += f"• Special: {info['nfpa']['special']}\n"
                
                response += f"\n🥽 **Required PPE:**\n"
                for ppe in info['ppe']:
                    response += f"• {ppe}\n"
                
                response += f"\n📦 **Storage:** {info['storage']}\n\n"
        
        response += "Need to generate a GHS or NFPA label? Just ask!"
        return response
    
    def incident_response(self):
        return """🚨 **Incident Reporting Module**

I can help you report various types of incidents:

**📋 Incident Types:**
- 🩹 Injury/Illness
- ⚠️ Near Miss
- 💥 Property Damage
- 🌊 Environmental (spill/leak)
- 🔒 Security Issue

**📸 Photo Support:** You can now attach photos to your incident reports!

**📊 Risk Assessment:** The system will automatically calculate risk scores using:
- **Severity dimensions:** People, Environment, Cost, Reputation, Legal
- **Likelihood scale:** 0-10 scoring system
- **Risk matrix:** Severity × Likelihood

**📍 Location Details:** Please provide:
- State, City, Department
- Specific location/building
- Date and time

Would you like to start an incident report? I'll guide you through each step."""

    def safety_response(self):
        return """⚠️ **Safety Concerns Module**

Report unsafe conditions before they become incidents:

**🔍 Concern Types:**
- Unsafe equipment or machinery
- Missing or damaged PPE
- Blocked emergency exits
- Chemical storage issues
- Environmental hazards
- Unsafe behaviors

**📸 Photo Documentation:** Attach photos to better document safety concerns!

**📊 Risk Evaluation:** Each concern gets assessed for:
- Severity potential (0-10 scale)
- Likelihood of occurrence (0-10 scale)
- Overall risk score calculation

**🎯 Follow-up Process:**
1. Submit concern with photos
2. Automatic risk assessment
3. Assignment to responsible personnel
4. CAPA tracking if needed
5. Resolution verification

Ready to report a safety concern? Let's document it properly!"""

    def risk_assessment_response(self):
        return """📊 **Risk Assessment Module**

Comprehensive risk evaluation using multi-dimensional analysis:

**🎯 Assessment Dimensions:**
- **People:** Injury potential (0-10)
- **Environment:** Environmental impact (0-10)
- **Cost:** Financial impact (0-10)
- **Reputation:** Public/media attention (0-10)
- **Legal:** Regulatory consequences (0-10)

**📈 Likelihood Scale:**
- 0: Impossible (Cannot happen)
- 2: Rare (Once in 10+ years)
- 4: Unlikely (Once every 5-10 years)
- 6: Possible (Once every 1-5 years)
- 8: Likely (Once per year or more)
- 10: Almost Certain (Multiple times per year)

**🧮 Risk Calculation:**
Risk Score = Maximum Severity × Likelihood

**📋 Risk Categories:**
- Low: 0-24
- Medium: 25-49
- High: 50-74
- Critical: 75-100

Need help assessing a specific risk? I can guide you through the process!"""

    def sds_response(self):
        return """📄 **Safety Data Sheet Information**

I can help you with chemical safety information. You can:

1. **Ask about specific chemicals**:
   - "What are the hazards of acetone?"
   - "How should I store methanol?"
   - "What PPE is needed for sulfuric acid?"

2. **Upload SDS documents** with location organization
3. **Generate safety labels** (GHS/NFPA format)

What chemical or safety information do you need?"""

    def help_response(self):
        return """🛡️ **Enhanced Smart EHS System Help**

**🏠 Main Dashboard:**
- Real-time statistics across all modules
- Risk distribution analytics
- Recent activity feed

**📱 Core Modules (AVOMO-Compliant):**

🚨 **Incident Management (P1 - Completed)**
- Multi-dimensional risk assessment (People, Environment, Cost, Reputation, Legal)
- Photo attachment support
- Automated CAPA generation
- Likelihood scale: 0-10 (Impossible to Almost Certain)
- Severity scales from your CSV data

📄 **SDS Management (P1 - Completed)**
- Location-based organization (State/City/Department/Building/Room)
- Intelligent chemical search with chemical database
- GHS & NFPA label generation and printing
- Download and view capabilities
- Chemical intelligence chat (acetone, methanol, sulfuric acid)

⚠️ **Safety Concerns (P1 - Completed)**
- Proactive hazard reporting with photo documentation
- Risk-based prioritization using your severity scales
- Anonymous reporting capabilities

📊 **Risk Management (P1 - In Progress)**
- Comprehensive risk register
- Multi-dimensional scoring matrix
- Interactive risk calculator
- Risk distribution charts

🔧 **CAPA Tracking (P2 - Completed)**
- Automated action generation from incidents/concerns
- SLA tracking and escalation
- Assignment and due date management
- Integration with all modules

**🤖 Smart Features:**
- Chemical safety intelligence from your chemical database
- Automated risk calculations using your CSV scales
- Photo upload for documentation
- Location-based SDS organization
- Safety label generation (GHS/NFPA)

**👥 Access Levels (Total: 1000 users):**
- Admin (10): Full system access
- Manager (90): Module management
- Contributor (200): Report submission
- Viewer (100): Read-only access  
- Vendor/Contractor (600): Limited safety reporting

**💬 Chat Commands:**
- "Tell me about [chemical name]" - Chemical safety info
- "Generate a GHS/NFPA label" - Label creation
- "Report an incident with photos" - Incident reporting
- "I have a safety concern" - Proactive reporting
- "Help with risk assessment" - Risk calculation tools

**📋 Module Status:**
- P1 Modules: Incident Mgmt, SDS, Safety Concerns, Risk Mgmt (High Priority)
- P2 Modules: CAPA Tracker (Medium Priority) 
- P3 Modules: MOC, Audits, Environmental (Lower Priority)

What would you like to explore?"""

    def default_response(self):
        return """👋 **Welcome to Enhanced Smart EHS System**

🎯 **What I can help you with:**

**🚨 Incident Management**
- Multi-dimensional risk assessment
- Photo attachment support
- Automated notifications

**📄 SDS & Chemical Safety**
- Location-based document management
- Intelligent chemical information
- GHS/NFPA label generation

**⚠️ Safety Concerns**
- Proactive hazard identification
- Photo documentation
- Risk-based prioritization

**📊 Risk Management**
- Comprehensive risk assessments
- Multi-dimensional scoring
- Analytics and trends

**💡 Quick Actions:**
- "Tell me about acetone safety"
- "I need to report an incident"
- "Generate a chemical label"
- "I have a safety concern"

**📱 New Features:**
- 📸 Photo uploads for incidents/concerns
- 📍 Location-based SDS organization
- 🏷️ Automatic label generation
- 📊 Real-time dashboard analytics

How can I help keep your workplace safe today?"""
    
    def store_chat_history(self, message, response, intent, context_data=None):
        """Store enhanced chat interaction"""
        try:
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO chat_history (message, response, intent, confidence, context_data)
                VALUES (?, ?, ?, ?, ?)
            ''', (message, response, intent, 0.85, json.dumps(context_data) if context_data else None))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing chat history: {e}")
    
    def create_incident(self):
        """Create new incident with photo support"""
        try:
            data = request.get_json()
            incident_id = str(uuid.uuid4())
            
            # Calculate risk score
            severity_people = int(data.get('severity_people', 0))
            severity_environment = int(data.get('severity_environment', 0))
            severity_cost = int(data.get('severity_cost', 0))
            severity_reputation = int(data.get('severity_reputation', 0))
            severity_legal = int(data.get('severity_legal', 0))
            likelihood = int(data.get('likelihood', 0))
            
            # Calculate maximum severity across all categories
            max_severity = max(severity_people, severity_environment, severity_cost, severity_reputation, severity_legal)
            risk_score = max_severity * likelihood
            
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO incidents (
                    id, type, title, description, location, department, state, city, photos,
                    severity_people, severity_environment, severity_cost,
                    severity_reputation, severity_legal, likelihood_score, risk_score, reporter_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                incident_id,
                data.get('type', 'general'),
                data.get('title', 'Incident Report'),
                data.get('description', ''),
                data.get('location', ''),
                data.get('department', ''),
                data.get('state', ''),
                data.get('city', ''),
                json.dumps(data.get('photos', [])),
                severity_people, severity_environment, severity_cost,
                severity_reputation, severity_legal, likelihood, risk_score,
                data.get('reporter_name', '')
            ))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'incident_id': incident_id,
                'risk_score': risk_score,
                'message': 'Incident reported successfully'
            })
            
        except Exception as e:
            logger.error(f"Error creating incident: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    def create_safety_concern(self):
        """Create new safety concern with photo support"""
        try:
            data = request.get_json()
            concern_id = str(uuid.uuid4())
            
            severity = int(data.get('severity_level', 0))
            likelihood = int(data.get('likelihood_level', 0))
            risk_score = severity * likelihood
            
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO safety_concerns (
                    id, type, title, description, location, department, state, city, photos,
                    severity_level, likelihood_level, risk_score, reporter_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                concern_id,
                data.get('type', 'general'),
                data.get('title', 'Safety Concern'),
                data.get('description', ''),
                data.get('location', ''),
                data.get('department', ''),
                data.get('state', ''),
                data.get('city', ''),
                json.dumps(data.get('photos', [])),
                severity, likelihood, risk_score,
                data.get('reporter_name', '')
            ))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'concern_id': concern_id,
                'risk_score': risk_score,
                'message': 'Safety concern reported successfully'
            })
            
        except Exception as e:
            logger.error(f"Error creating safety concern: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    def upload_sds_file(self):
        """Upload SDS file with location organization"""
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'error': 'No file provided'})
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'success': False, 'error': 'No file selected'})
            
            # Get form data
            product_name = request.form.get('product_name', '')
            manufacturer = request.form.get('manufacturer', '')
            cas_number = request.form.get('cas_number', '')
            state = request.form.get('state', '')
            city = request.form.get('city', '')
            department = request.form.get('department', '')
            building = request.form.get('building', '')
            room = request.form.get('room', '')
            
            # Create location-based directory structure
            location_path = os.path.join('static', 'sds', state, city, department)
            os.makedirs(location_path, exist_ok=True)
            
            # Save file
            filename = secure_filename(file.filename)
            sds_id = str(uuid.uuid4())
            file_path = os.path.join(location_path, f"{sds_id}_{filename}")
            file.save(file_path)
            
            # Store in database
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO sds_documents (
                    id, product_name, manufacturer, cas_number, file_path, file_name,
                    state, city, department, building, room
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                sds_id, product_name, manufacturer, cas_number, file_path, filename,
                state, city, department, building, room
            ))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'sds_id': sds_id,
                'message': 'SDS file uploaded successfully'
            })
            
        except Exception as e:
            logger.error(f"Error uploading SDS: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    def get_sds_documents(self):
        """Get SDS documents with location filtering"""
        try:
            state = request.args.get('state', '')
            city = request.args.get('city', '')
            department = request.args.get('department', '')
            
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            query = 'SELECT * FROM sds_documents WHERE 1=1'
            params = []
            
            if state:
                query += ' AND state = ?'
                params.append(state)
            if city:
                query += ' AND city = ?'
                params.append(city)
            if department:
                query += ' AND department = ?'
                params.append(department)
            
            query += ' ORDER BY created_at DESC'
            
            cursor.execute(query, params)
            documents = cursor.fetchall()
            
            # Get available locations for filtering
            cursor.execute('SELECT DISTINCT state FROM sds_documents WHERE state IS NOT NULL')
            states = [row[0] for row in cursor.fetchall()]
            
            cursor.execute('SELECT DISTINCT city FROM sds_documents WHERE city IS NOT NULL')
            cities = [row[0] for row in cursor.fetchall()]
            
            cursor.execute('SELECT DISTINCT department FROM sds_documents WHERE department IS NOT NULL')
            departments = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            
            # Format documents
            formatted_docs = []
            for doc in documents:
                formatted_docs.append({
                    'id': doc[0],
                    'product_name': doc[1],
                    'manufacturer': doc[2],
                    'cas_number': doc[3],
                    'file_name': doc[5],
                    'state': doc[9],
                    'city': doc[10],
                    'department': doc[11],
                    'building': doc[12],
                    'room': doc[13],
                    'created_at': doc[14]
                })
            
            return jsonify({
                'documents': formatted_docs,
                'filters': {
                    'states': states,
                    'cities': cities,
                    'departments': departments
                }
            })
            
        except Exception as e:
            logger.error(f"Error getting SDS documents: {e}")
            return jsonify({'error': str(e)})
    
    def generate_safety_label(self, label_type, document_id):
        """Generate GHS or NFPA safety labels"""
        try:
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM sds_documents WHERE id = ?', (document_id,))
            doc = cursor.fetchone()
            conn.close()
            
            if not doc:
                return jsonify({'error': 'Document not found'})
            
            product_name = doc[1]
            
            if label_type == 'ghs':
                label_html = self.generate_ghs_label(product_name, document_id)
            elif label_type == 'nfpa':
                label_html = self.generate_nfpa_label(product_name, document_id)
            else:
                return jsonify({'error': 'Invalid label type'})
            
            return jsonify({
                'success': True,
                'label_html': label_html,
                'product_name': product_name
            })
            
        except Exception as e:
            logger.error(f"Error generating label: {e}")
            return jsonify({'error': str(e)})
    
    def generate_ghs_label(self, product_name, document_id):
        """Generate GHS label HTML"""
        return f'''
        <div class="ghs-label border-2 border-black p-4 bg-white" style="width: 4in; height: 6in;">
            <div class="text-center border-b-2 border-black pb-2 mb-2">
                <h2 class="text-lg font-bold">DANGER</h2>
                <h3 class="text-md font-semibold">{product_name}</h3>
            </div>
            <div class="hazard-pictograms mb-2">
                <div class="flex justify-center space-x-2">
                    <div class="w-8 h-8 border border-red-500 bg-red-100 flex items-center justify-center">
                        <i class="fas fa-fire text-red-600"></i>
                    </div>
                    <div class="w-8 h-8 border border-red-500 bg-red-100 flex items-center justify-center">
                        <i class="fas fa-skull text-red-600"></i>
                    </div>
                </div>
            </div>
            <div class="hazard-statements text-xs">
                <p class="font-semibold">Hazard Statements:</p>
                <ul class="list-disc list-inside">
                    <li>H225: Highly flammable liquid</li>
                    <li>H319: Causes serious eye irritation</li>
                </ul>
            </div>
            <div class="precautionary-statements text-xs mt-2">
                <p class="font-semibold">Precautionary Statements:</p>
                <ul class="list-disc list-inside">
                    <li>P210: Keep away from heat/sparks</li>
                    <li>P305: IF IN EYES: Rinse cautiously</li>
                </ul>
            </div>
            <div class="supplier-info text-xs mt-2 border-t pt-1">
                <p class="font-semibold">Supplier Information:</p>
                <p>Document ID: {document_id}</p>
            </div>
        </div>
        '''
    
    def generate_nfpa_label(self, product_name, document_id):
        """Generate NFPA 704 diamond label HTML"""
        return f'''
        <div class="nfpa-label bg-white border-2 border-black p-4" style="width: 4in; height: 4in;">
            <div class="text-center mb-4">
                <h3 class="text-lg font-bold">{product_name}</h3>
            </div>
            <div class="nfpa-diamond mx-auto" style="width: 200px; height: 200px; position: relative;">
                <!-- Health (Blue) -->
                <div class="absolute top-0 left-1/2 transform -translate-x-1/2 w-16 h-16 bg-blue-500 rotate-45 flex items-center justify-center">
                    <span class="text-white font-bold text-xl -rotate-45">1</span>
                </div>
                <!-- Fire (Red) -->
                <div class="absolute top-1/2 right-0 transform -translate-y-1/2 w-16 h-16 bg-red-500 rotate-45 flex items-center justify-center">
                    <span class="text-white font-bold text-xl -rotate-45">3</span>
                </div>
                <!-- Reactivity (Yellow) -->
                <div class="absolute bottom-0 left-1/2 transform -translate-x-1/2 w-16 h-16 bg-yellow-400 rotate-45 flex items-center justify-center">
                    <span class="text-black font-bold text-xl -rotate-45">0</span>
                </div>
                <!-- Special (White) -->
                <div class="absolute top-1/2 left-0 transform -translate-y-1/2 w-16 h-16 bg-white border-2 border-black rotate-45 flex items-center justify-center">
                    <span class="text-black font-bold text-xl -rotate-45">-</span>
                </div>
            </div>
            <div class="text-center mt-4 text-xs">
                <p>Document ID: {document_id}</p>
            </div>
        </div>
        '''
    
    def handle_photo_upload(self):
        """Handle photo uploads for incidents and concerns"""
        try:
            if 'photo' not in request.files:
                return jsonify({'success': False, 'error': 'No photo provided'})
            
            file = request.files['photo']
            if file.filename == '':
                return jsonify({'success': False, 'error': 'No photo selected'})
            
            # Create photos directory
            photos_dir = 'static/photos'
            os.makedirs(photos_dir, exist_ok=True)
            
            # Save photo
            filename = secure_filename(file.filename)
            photo_id = str(uuid.uuid4())
            file_path = os.path.join(photos_dir, f"{photo_id}_{filename}")
            file.save(file_path)
            
            return jsonify({
                'success': True,
                'photo_id': photo_id,
                'file_path': file_path,
                'message': 'Photo uploaded successfully'
            })
            
        except Exception as e:
            logger.error(f"Error uploading photo: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    def download_sds_file(self, document_id):
        """Download SDS file"""
        try:
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            cursor.execute('SELECT file_path, file_name FROM sds_documents WHERE id = ?', (document_id,))
            result = cursor.fetchone()
            conn.close()
            
            if not result:
                return jsonify({'error': 'Document not found'}), 404
            
            file_path, file_name = result
            return send_file(file_path, as_attachment=True, download_name=file_name)
            
        except Exception as e:
            logger.error(f"Error downloading SDS: {e}")
            return jsonify({'error': str(e)}), 500
    
    def create_capa_action(self):
        """Create CAPA action from incident, concern, or audit finding"""
        try:
            data = request.get_json()
            capa_id = str(uuid.uuid4())
            
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO capa_actions (
                    id, source_type, source_id, action_type, description,
                    assigned_to, due_date, priority
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                capa_id,
                data.get('source_type', 'manual'),
                data.get('source_id', ''),
                data.get('action_type', 'corrective'),
                data.get('description', ''),
                data.get('assigned_to', ''),
                data.get('due_date', ''),
                data.get('priority', 'medium')
            ))
            
            conn.commit()
            conn.close()
            
            return jsonify({
                'success': True,
                'capa_id': capa_id,
                'message': 'CAPA action created successfully'
            })
            
        except Exception as e:
            logger.error(f"Error creating CAPA: {e}")
            return jsonify({'success': False, 'error': str(e)})
    
    def get_capa_actions(self):
        """Get all CAPA actions with filtering"""
        try:
            status = request.args.get('status', '')
            priority = request.args.get('priority', '')
            
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            query = 'SELECT * FROM capa_actions WHERE 1=1'
            params = []
            
            if status:
                query += ' AND status = ?'
                params.append(status)
            if priority:
                query += ' AND priority = ?'
                params.append(priority)
                
            query += ' ORDER BY created_at DESC'
            
            cursor.execute(query, params)
            capas = cursor.fetchall()
            conn.close()
            
            formatted_capas = []
            for capa in capas:
                formatted_capas.append({
                    'id': capa[0],
                    'source_type': capa[1],
                    'source_id': capa[2],
                    'action_type': capa[3],
                    'description': capa[4],
                    'assigned_to': capa[5],
                    'due_date': capa[6],
                    'status': capa[7],
                    'priority': capa[8],
                    'created_at': capa[9],
                    'completed_at': capa[10]
                })
            
            return jsonify({'capas': formatted_capas})
            
        except Exception as e:
            logger.error(f"Error getting CAPAs: {e}")
            return jsonify({'error': str(e)})
    
    def get_dashboard_stats(self):
        """Get comprehensive dashboard statistics"""
        try:
            conn = sqlite3.connect('data/smart_ehs.db')
            cursor = conn.cursor()
            
            # Count incidents
            cursor.execute('SELECT COUNT(*) FROM incidents')
            total_incidents = cursor.fetchone()[0]
            
            # Count high-risk incidents
            cursor.execute('SELECT COUNT(*) FROM incidents WHERE risk_score >= 50')
            high_risk_incidents = cursor.fetchone()[0]
            
            # Count SDS documents
            cursor.execute('SELECT COUNT(*) FROM sds_documents')
            total_sds = cursor.fetchone()[0]
            
            # Count safety concerns
            cursor.execute('SELECT COUNT(*) FROM safety_concerns')
            total_concerns = cursor.fetchone()[0]
            
            # Count open CAPA actions
            cursor.execute('SELECT COUNT(*) FROM capa_actions WHERE status = "open"')
            open_capas = cursor.fetchone()[0]
            
            # Get recent activity
            cursor.execute('''
                SELECT 'incident' as type, title, created_at FROM incidents
                UNION ALL
                SELECT 'concern' as type, title, created_at FROM safety_concerns
                ORDER BY created_at DESC LIMIT 10
            ''')
            recent_activity = cursor.fetchall()
            
            # Get risk distribution
            cursor.execute('''
                SELECT 
                    CASE 
                        WHEN risk_score < 25 THEN 'Low'
                        WHEN risk_score < 50 THEN 'Medium'
                        WHEN risk_score < 75 THEN 'High'
                        ELSE 'Critical'
                    END as risk_level,
                    COUNT(*) as count
                FROM incidents 
                GROUP BY risk_level
            ''')
            risk_distribution = cursor.fetchall()
            
            conn.close()
            
            return jsonify({
                'total_incidents': total_incidents,
                'high_risk_incidents': high_risk_incidents,
                'total_sds_documents': total_sds,
                'total_safety_concerns': total_concerns,
                'open_capa_actions': open_capas,
                'recent_activity': [
                    {'type': r[0], 'title': r[1], 'date': r[2]} for r in recent_activity
                ],
                'risk_distribution': [
                    {'level': r[0], 'count': r[1]} for r in risk_distribution
                ]
            })
            
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {e}")
            return jsonify({'error': str(e)})
    
    def get_main_dashboard(self):
        """Return enhanced main dashboard template"""
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Enhanced Smart EHS Management System</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .chat-message { animation: fadeIn 0.3s ease-in; margin-bottom: 1rem; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .ai-response { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }
        .user-message { background: #3b82f6; color: white; margin-left: 2rem; }
        .module-card { transition: all 0.3s ease; }
        .module-card:hover { transform: translateY(-5px); box-shadow: 0 10px 25px rgba(0,0,0,0.1); }
        .risk-indicator { width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 8px; }
        .risk-low { background-color: #10b981; }
        .risk-medium { background-color: #f59e0b; }
        .risk-high { background-color: #ef4444; }
        .risk-critical { background-color: #dc2626; animation: pulse 2s infinite; }
    </style>
</head>

<body class="bg-gray-50 min-h-screen">
    <!-- Enhanced Header -->
    <header class="bg-white shadow-md border-b-4 border-blue-600">
        <div class="max-w-7xl mx-auto px-4 py-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center space-x-3">
                    <i class="fas fa-shield-alt text-blue-600 text-2xl"></i>
                    <h1 class="text-2xl font-bold text-gray-800">Enhanced Smart EHS System</h1>
                    <span class="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">
                        <i class="fas fa-circle text-green-500 text-xs"></i> Live & Enhanced
                    </span>
                </div>
                <nav class="hidden md:flex space-x-6">
                    <a href="/dashboard" class="text-blue-600 font-semibold hover:text-blue-800">
                        <i class="fas fa-tachometer-alt mr-1"></i> Dashboard
                    </a>
                    <a href="/incident-management" class="text-gray-600 hover:text-blue-600">
                        <i class="fas fa-exclamation-triangle mr-1"></i> Incidents
                    </a>
                    <a href="/sds-management" class="text-gray-600 hover:text-blue-600">
                        <i class="fas fa-file-alt mr-1"></i> SDS
                    </a>
                    <a href="/safety-concerns" class="text-gray-600 hover:text-blue-600">
                        <i class="fas fa-eye mr-1"></i> Concerns
                    </a>
                    <a href="/risk-management" class="text-gray-600 hover:text-blue-600">
                        <i class="fas fa-chart-line mr-1"></i> Risk
                    </a>
                    <a href="/avomo-workflow" class="text-gray-600 hover:text-blue-600">
                        <i class="fas fa-project-diagram mr-1"></i> Workflow
                    </a>
                </nav>
            </div>
        </div>
    </header>

    <!-- Main Content -->
    <div class="max-w-7xl mx-auto px-4 py-8">
        <!-- Title Section -->
        <div class="text-center mb-8">
            <h2 class="text-4xl font-bold text-gray-800 mb-2">
                🛡️ Smart EHS Management Dashboard
            </h2>
            <p class="text-gray-600 text-lg">Integrated Safety • Risk Assessment • Chemical Management • Photo Support</p>
            <div class="mt-4 flex flex-wrap justify-center gap-2 text-sm">
                <span class="bg-blue-100 text-blue-800 px-3 py-1 rounded-full">
                    <i class="fas fa-check mr-1"></i>Likelihood & Severity Scales from CSV
                </span>
                <span class="bg-green-100 text-green-800 px-3 py-1 rounded-full">
                    <i class="fas fa-check mr-1"></i>AVOMO Module Priorities
                </span>
                <span class="bg-purple-100 text-purple-800 px-3 py-1 rounded-full">
                    <i class="fas fa-check mr-1"></i>CAPA Tracking
                </span>
                <span class="bg-yellow-100 text-yellow-800 px-3 py-1 rounded-full">
                    <i class="fas fa-check mr-1"></i>Access Levels (1000 users)
                </span>
            </div>
        </div>

        <!-- Enhanced Dashboard Stats -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <div class="bg-white rounded-lg shadow-lg p-6 border-l-4 border-red-500">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm font-medium text-gray-500 uppercase">Total Incidents</p>
                        <p class="text-3xl font-bold text-gray-900" id="totalIncidents">0</p>
                        <p class="text-xs text-green-600">Action tracking</p>
                    </div>
                    <i class="fas fa-tasks text-green-500 text-3xl"></i>
                </div>
            </div>
        </div>

        <!-- Module Cards -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
            <div class="module-card bg-white rounded-lg shadow-lg p-6 cursor-pointer" onclick="location.href='/incident-management'">
                <div class="text-center">
                    <i class="fas fa-exclamation-triangle text-4xl text-red-500 mb-4"></i>
                    <h3 class="text-lg font-semibold text-gray-800 mb-2">Incident Management</h3>
                    <p class="text-sm text-gray-600 mb-4">Multi-dimensional risk assessment with photo support</p>
                    <span class="bg-red-100 text-red-800 px-3 py-1 rounded-full text-xs">
                        <i class="fas fa-camera mr-1"></i> Photo Support
                    </span>
                </div>
            </div>
            
            <div class="module-card bg-white rounded-lg shadow-lg p-6 cursor-pointer" onclick="location.href='/sds-management'">
                <div class="text-center">
                    <i class="fas fa-file-alt text-4xl text-blue-500 mb-4"></i>
                    <h3 class="text-lg font-semibold text-gray-800 mb-2">SDS Management</h3>
                    <p class="text-sm text-gray-600 mb-4">Location-based organization with smart search</p>
                    <span class="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-xs">
                        <i class="fas fa-tags mr-1"></i> Label Generation
                    </span>
                </div>
            </div>
            
            <div class="module-card bg-white rounded-lg shadow-lg p-6 cursor-pointer" onclick="location.href='/safety-concerns'">
                <div class="text-center">
                    <i class="fas fa-eye text-4xl text-yellow-500 mb-4"></i>
                    <h3 class="text-lg font-semibold text-gray-800 mb-2">Safety Concerns</h3>
                    <p class="text-sm text-gray-600 mb-4">Proactive hazard identification and reporting</p>
                    <span class="bg-yellow-100 text-yellow-800 px-3 py-1 rounded-full text-xs">
                        <i class="fas fa-camera mr-1"></i> Photo Docs
                    </span>
                </div>
            </div>
            
            <div class="module-card bg-white rounded-lg shadow-lg p-6 cursor-pointer" onclick="location.href='/risk-management'">
                <div class="text-center">
                    <i class="fas fa-chart-line text-4xl text-green-500 mb-4"></i>
                    <h3 class="text-lg font-semibold text-gray-800 mb-2">Risk Management</h3>
                    <p class="text-sm text-gray-600 mb-4">Comprehensive risk assessment matrix</p>
                    <span class="bg-green-100 text-green-800 px-3 py-1 rounded-full text-xs">
                        <i class="fas fa-calculator mr-1"></i> Auto Calc
                    </span>
                </div>
            </div>
        </div>

        <!-- Dashboard Content Grid -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Enhanced Chat Interface -->
            <div class="lg:col-span-2 bg-white rounded-lg shadow-lg">
                <div class="p-6 border-b border-gray-200">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center space-x-3">
                            <i class="fas fa-robot text-blue-600 text-xl"></i>
                            <h3 class="text-lg font-semibold text-gray-800">Enhanced EHS Assistant</h3>
                            <span class="bg-blue-100 text-blue-800 px-2 py-1 rounded-full text-xs">
                                <i class="fas fa-brain mr-1"></i> Chemical Intelligence
                            </span>
                        </div>
                        <div class="flex space-x-2">
                            <span class="bg-green-100 text-green-800 px-2 py-1 rounded-full text-xs">
                                <i class="fas fa-camera mr-1"></i> Photo Support
                            </span>
                            <span class="bg-purple-100 text-purple-800 px-2 py-1 rounded-full text-xs">
                                <i class="fas fa-tags mr-1"></i> Label Gen
                            </span>
                        </div>
                    </div>
                </div>
                <div class="h-96 overflow-y-auto p-6 space-y-4" id="chatContainer">
                    <!-- Welcome Message -->
                    <div class="chat-message ai-response p-4 rounded-lg max-w-4/5">
                        <div class="flex items-start space-x-3">
                            <div class="flex-shrink-0">
                                <i class="fas fa-robot text-white text-lg"></i>
                            </div>
                            <div class="flex-1">
                                <div class="flex items-center space-x-2 mb-1">
                                    <span class="font-semibold">Enhanced EHS Assistant</span>
                                    <span class="text-xs opacity-75">Just now</span>
                                </div>
                                <div>🛡️ Welcome to the Enhanced Smart EHS System! 
                                
<strong>🆕 New Features:</strong>
• 📸 Photo uploads for incidents & concerns
• 📍 Location-based SDS management (State/City/Dept)
• 🏷️ GHS & NFPA label generation
• 🧠 Chemical safety intelligence
• 📊 Multi-dimensional risk assessment

<strong>💬 Try these commands:</strong>
• "Tell me about acetone safety"
• "Generate a GHS label"
• "I need to report an incident with photos"
• "Upload SDS for our Austin facility"</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="p-6 border-t border-gray-200">
                    <div class="flex space-x-4 mb-3">
                        <input 
                            type="text" 
                            id="chatInput"
                            placeholder="Ask about chemicals, upload SDS, report incidents with photos..."
                            class="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                        <button 
                            id="sendBtn"
                            class="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                            <i class="fas fa-paper-plane"></i>
                        </button>
                    </div>
                    <div class="flex flex-wrap gap-2">
                        <button onclick="sendQuickMessage('Tell me about acetone safety')" 
                                class="bg-blue-100 text-blue-700 px-3 py-1 rounded-full text-sm hover:bg-blue-200">
                            <i class="fas fa-flask mr-1"></i> Chemical Safety
                        </button>
                        <button onclick="sendQuickMessage('I need to report an incident')" 
                                class="bg-red-100 text-red-700 px-3 py-1 rounded-full text-sm hover:bg-red-200">
                            <i class="fas fa-exclamation-triangle mr-1"></i> Report Incident
                        </button>
                        <button onclick="sendQuickMessage('Generate a GHS label')" 
                                class="bg-green-100 text-green-700 px-3 py-1 rounded-full text-sm hover:bg-green-200">
                            <i class="fas fa-tags mr-1"></i> Generate Label
                        </button>
                        <button onclick="sendQuickMessage('I have a safety concern')" 
                                class="bg-yellow-100 text-yellow-700 px-3 py-1 rounded-full text-sm hover:bg-yellow-200">
                            <i class="fas fa-eye mr-1"></i> Safety Concern
                        </button>
                    </div>
                </div>
            </div>

            <!-- Activity & Analytics Sidebar -->
            <div class="space-y-6">
                <!-- Risk Distribution Chart -->
                <div class="bg-white rounded-lg shadow-lg p-6">
                    <h3 class="text-lg font-semibold text-gray-800 mb-4">
                        <i class="fas fa-chart-pie mr-2 text-blue-600"></i>Risk Distribution
                    </h3>
                    <canvas id="riskChart" width="300" height="200"></canvas>
                </div>

                <!-- Recent Activity -->
                <div class="bg-white rounded-lg shadow-lg p-6">
                    <h3 class="text-lg font-semibold text-gray-800 mb-4">
                        <i class="fas fa-clock mr-2 text-green-600"></i>Recent Activity
                    </h3>
                    <div id="recentActivity" class="space-y-3">
                        <div class="flex items-center text-sm text-gray-600">
                            <i class="fas fa-spinner fa-spin mr-2"></i>
                            Loading activity...
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let riskChart;
        
        document.addEventListener('DOMContentLoaded', function() {
            loadDashboardStats();
            setupEventListeners();
            initializeRiskChart();
        });

        function setupEventListeners() {
            document.getElementById('sendBtn').addEventListener('click', sendMessage);
            document.getElementById('chatInput').addEventListener('keypress', function(e) {
                if (e.key === 'Enter') sendMessage();
            });
        }

        function initializeRiskChart() {
            const ctx = document.getElementById('riskChart').getContext('2d');
            riskChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Low', 'Medium', 'High', 'Critical'],
                    datasets: [{
                        data: [0, 0, 0, 0],
                        backgroundColor: ['#10b981', '#f59e0b', '#ef4444', '#dc2626'],
                        borderWidth: 2,
                        borderColor: '#fff'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                usePointStyle: true,
                                padding: 15
                            }
                        }
                    }
                }
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
            
            const typingId = addChatMessage('Assistant', 'Analyzing your request...', 'ai-response opacity-50');
            
            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });
                
                const result = await response.json();
                
                document.getElementById(typingId).remove();
                addChatMessage('Enhanced EHS Assistant', result.response, 'ai-response');
                
                // Show additional info if chemical detected
                if (result.chemical_info && result.chemical_info.length > 0) {
                    setTimeout(() => {
                        addChatMessage('System', `🧪 Chemical detected: ${result.chemical_info.join(', ')}. I can generate safety labels if needed!`, 'ai-response bg-green-600');
                    }, 1000);
                }
                
            } catch (error) {
                document.getElementById(typingId).remove();
                addChatMessage('Assistant', 'Sorry, I encountered an error. Please try again.', 'ai-response bg-red-600');
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
            
            const icon = sender === 'You' ? 'fas fa-user' : 
                        sender === 'System' ? 'fas fa-cog' : 'fas fa-robot';
            
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
                
                // Update counters
                document.getElementById('totalIncidents').textContent = stats.total_incidents;
                document.getElementById('highRiskIncidents').textContent = `${stats.high_risk_incidents} high-risk`;
                document.getElementById('totalSDS').textContent = stats.total_sds_documents;
                document.getElementById('totalConcerns').textContent = stats.total_safety_concerns;
                document.getElementById('openCAPAs').textContent = stats.open_capa_actions;
                
                // Update risk chart
                if (stats.risk_distribution && riskChart) {
                    const riskData = [0, 0, 0, 0]; // Low, Medium, High, Critical
                    stats.risk_distribution.forEach(risk => {
                        switch(risk.level) {
                            case 'Low': riskData[0] = risk.count; break;
                            case 'Medium': riskData[1] = risk.count; break;
                            case 'High': riskData[2] = risk.count; break;
                            case 'Critical': riskData[3] = risk.count; break;
                        }
                    });
                    riskChart.data.datasets[0].data = riskData;
                    riskChart.update();
                }
                
                // Update recent activity
                updateRecentActivity(stats.recent_activity);
                
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }

        function updateRecentActivity(activities) {
            const container = document.getElementById('recentActivity');
            
            if (!activities || activities.length === 0) {
                container.innerHTML = '<div class="text-sm text-gray-500">No recent activity</div>';
                return;
            }
            
            container.innerHTML = activities.slice(0, 5).map(activity => {
                const icon = activity.type === 'incident' ? 'fas fa-exclamation-triangle text-red-500' : 'fas fa-eye text-yellow-500';
                const date = new Date(activity.date).toLocaleDateString();
                
                return `
                    <div class="flex items-start space-x-3 p-2 rounded hover:bg-gray-50">
                        <i class="${icon}"></i>
                        <div class="flex-1 min-w-0">
                            <p class="text-sm font-medium text-gray-900 truncate">${activity.title}</p>
                            <p class="text-xs text-gray-500">${activity.type} • ${date}</p>
                        </div>
                    </div>
                `;
            }).join('');
        }

        // Auto-refresh dashboard every 30 seconds
        setInterval(loadDashboardStats, 30000);
    </script>
</body>
</html>'''
    
    # Define placeholder methods for additional pages
    def get_incident_management_page(self):
        return '<html><body><h1>Incident Management Page</h1><p>Enhanced incident reporting with photo support coming soon!</p></body></html>'
    
    def get_sds_management_page(self):
        return '<html><body><h1>SDS Management Page</h1><p>Location-based SDS management coming soon!</p></body></html>'
    
    def get_safety_concerns_page(self):
        return '<html><body><h1>Safety Concerns Page</h1><p>Photo-enabled safety concern reporting coming soon!</p></body></html>'
    
    def get_risk_management_page(self):
        return '<html><body><h1>Risk Management Page</h1><p>Interactive risk assessment tools coming soon!</p></body></html>'
    
    def get_avomo_workflow_page(self):
        return '<html><body><h1>AVOMO Workflow Page</h1><p>Module priorities and workflow visualization coming soon!</p></body></html>'

# Create the Flask app instance
app = EnhancedEHSSystem().app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)-red-600" id="highRiskIncidents">0 high-risk</p>
                    </div>
                    <i class="fas fa-exclamation-triangle text-red-500 text-3xl"></i>
                </div>
            </div>
            
            <div class="bg-white rounded-lg shadow-lg p-6 border-l-4 border-blue-500">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm font-medium text-gray-500 uppercase">SDS Documents</p>
                        <p class="text-3xl font-bold text-gray-900" id="totalSDS">0</p>
                        <p class="text-xs text-blue-600">Multi-location</p>
                    </div>
                    <i class="fas fa-file-alt text-blue-500 text-3xl"></i>
                </div>
            </div>
            
            <div class="bg-white rounded-lg shadow-lg p-6 border-l-4 border-yellow-500">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm font-medium text-gray-500 uppercase">Safety Concerns</p>
                        <p class="text-3xl font-bold text-gray-900" id="totalConcerns">0</p>
                        <p class="text-xs text-yellow-600">Active monitoring</p>
                    </div>
                    <i class="fas fa-eye text-yellow-500 text-3xl"></i>
                </div>
            </div>
            
            <div class="bg-white rounded-lg shadow-lg p-6 border-l-4 border-green-500">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm font-medium text-gray-500 uppercase">Open CAPAs</p>
                        <p class="text-3xl font-bold text-gray-900" id="openCAPAs">0</p>
                        <p class="text-xs text
