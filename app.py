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
        """Load severity and likelihood scales from uploaded CSV files"""
        # Default likelihood scale
        self.likelihood_scale = {
            0: {'label': 'Impossible', 'description': 'Cannot happen'},
            2: {'label': 'Rare', 'description': 'Extremely unlikely (once in 10+ years)'},
            4: {'label': 'Unlikely', 'description': 'Could happen exceptionally (once every 5-10 years)'},
            6: {'label': 'Possible', 'description': 'Might happen occasionally (once every 1-5 years)'},
            8: {'label': 'Likely', 'description': 'Expected to happen regularly (once per year or more)'},
            10: {'label': 'Almost Certain', 'description': 'Will almost certainly happen (multiple times per year)'}
        }
        
        # Default severity scales
        self.severity_scale = {
            'people': {
                0: {'description': 'No injury or risk of harm', 'keywords': ['safe', 'no harm', 'uninjured']},
                2: {'description': 'First aid only; no lost time', 'keywords': ['first aid', 'minor', 'band-aid']},
                4: {'description': 'Medical treatment; lost time injury', 'keywords': ['medical', 'treatment', 'doctor visit']},
                6: {'description': 'Serious injury; hospitalization', 'keywords': ['hospital', 'serious', 'admitted']},
                8: {'description': 'Permanent disability', 'keywords': ['disability', 'amputation', 'permanent']},
                10: {'description': 'Single or multiple fatalities', 'keywords': ['death', 'fatality', 'killed']}
            },
            'environment': {
                0: {'description': 'No environmental impact', 'keywords': ['clean', 'contained', 'no spill']},
                2: {'description': 'Minor spill/release contained on-site', 'keywords': ['small spill', 'minor leak']},
                4: {'description': 'Moderate spill requiring cleanup', 'keywords': ['spill', 'cleanup', 'moderate']},
                6: {'description': 'Significant environmental damage', 'keywords': ['environmental damage', 'contamination']},
                8: {'description': 'Major environmental impact', 'keywords': ['major spill', 'widespread']},
                10: {'description': 'Catastrophic environmental damage', 'keywords': ['catastrophic', 'disaster']}
            },
            'cost': {
                0: {'description': 'No financial impact (<$1K)', 'keywords': ['minimal cost', 'no expense']},
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
                10: {'description': 'Severe legal consequences', 'keywords': ['lawsuit', 'criminal liability']}
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
