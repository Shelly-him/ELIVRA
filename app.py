import os
import hashlib
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

# App Configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///elivra.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from models import db, User, Voter, Anomaly, AuditLog
from anomaly_engine import run_anomaly_checks

db.init_app(app)

# Authentication Setup
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Audit Logging Helper
def log_action(action, entity_type=None, entity_id=None, description=""):
    log = AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()

# --- PUBLIC PORTAL ROUTES ---

@app.route('/public/register')
def public_register_page():
    return render_template('public_register.html')

@app.route('/api/public/register', methods=['POST'])
def public_voter_register():
    data = request.json or {}

    # Validation: Required Fields
    required_fields = ['full_name', 'national_id', 'date_of_birth', 'county', 'constituency', 'ward']
    for field in required_fields:
        if not data.get(field):
            return jsonify({"success": False, "message": f"Missing required field: {field}"}), 400

    national_id = str(data.get('national_id')).strip()

    # Validation: National ID Format (7-8 digits)
    if not national_id.isdigit() or len(national_id) < 7 or len(national_id) > 8:
        return jsonify({"success": False, "message": "National ID must be a valid 7 or 8 digit numeric string."}), 400

    # Validation: Duplicate National ID
    existing_voter = Voter.query.filter_by(national_id=national_id).first()
    if existing_voter:
        return jsonify({"success": False, "message": "This National ID is already registered in the system."}), 400

    # Validation: Age Verification (>= 18 years)
    try:
        dob = datetime.strptime(data.get('date_of_birth'), '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"success": False, "message": "Invalid date format. Expected YYYY-MM-DD."}), 400

    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    if age < 18:
        return jsonify({"success": False, "message": f"Registration denied. Applicant is {age} years old; must be at least 18."}), 400

    # Record Generation & SHA-256 Hashing
    reg_id = f"REG-{hashlib.sha256(national_id.encode()).hexdigest()[:6].upper()}"

    new_voter = Voter(
        registration_id=reg_id,
        full_name=data.get('full_name'),
        national_id=national_id,
        date_of_birth=dob,
        county=data.get('county'),
        constituency=data.get('constituency'),
        ward=data.get('ward'),
        verification_status='Pending'
    )
    
    if hasattr(new_voter, 'calculate_hash'):
        new_voter.integrity_hash = new_voter.calculate_hash()
    else:
        raw_str = f"{new_voter.registration_id}{new_voter.full_name}{new_voter.national_id}{new_voter.county}"
        new_voter.integrity_hash = hashlib.sha256(raw_str.encode()).hexdigest()

    db.session.add(new_voter)
    db.session.commit()

    log_action("Public Voter Self-Registration", "Voter", new_voter.id, f"Created public record {new_voter.registration_id}")
    anomalies = run_anomaly_checks(new_voter)

    return jsonify({
        "success": True,
        "message": "Voter registration submitted successfully.",
        "credentials": {
            "registration_id": new_voter.registration_id,
            "full_name": new_voter.full_name,
            "national_id": new_voter.national_id,
            "county": new_voter.county,
            "status": new_voter.verification_status,
            "receipt_hash": new_voter.integrity_hash
        },
        "anomalies_detected": len(anomalies)
    }), 201

@app.route('/api/public/verify-status', methods=['GET'])
def public_verify_status():
    national_id = request.args.get('national_id')

    if not national_id:
        return jsonify({"success": False, "message": "National ID parameter is required."}), 400

    voter = Voter.query.filter_by(national_id=national_id).first()

    if not voter:
        return jsonify({"success": False, "message": "No voter record found for this National ID."}), 404

    return jsonify({
        "success": True,
        "voter": {
            "registration_id": voter.registration_id,
            "full_name": voter.full_name,
            "national_id": f"****{voter.national_id[-4:]}" if len(voter.national_id) >= 4 else voter.national_id,
            "county": voter.county,
            "constituency": voter.constituency,
            "ward": voter.ward,
            "status": voter.verification_status,
            "receipt_hash": voter.integrity_hash
        }
    })

# --- ADMIN AUTHENTICATION ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username_or_email = request.form.get('identifier')
        password = request.form.get('password')

        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()

        if user and check_password_hash(user.password_hash, password):
            if user.status != 'Active':
                flash('Your account has been deactivated.', 'danger')
                return render_template('login.html')

            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)

            log_action("Admin Login", "User", user.id, f"User {user.username} logged in successfully.")
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username/email or password.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    log_action("Admin Logout", "User", current_user.id, f"User {current_user.username} logged out.")
    logout_user()
    return redirect(url_for('login'))

# --- DASHBOARD & ADMINISTRATIVE APIS ---

@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html', username=current_user.username)

@app.route('/api/dashboard', methods=['GET'])
@login_required
def api_dashboard():
    return jsonify({
        "total_voters": Voter.query.count(),
        "verified_voters": Voter.query.filter_by(verification_status="Verified").count(),
        "pending_voters": Voter.query.filter_by(verification_status="Pending").count(),
        "total_anomalies": Anomaly.query.count(),
        "open_anomalies": Anomaly.query.filter_by(status="Open").count(),
        "resolved_anomalies": Anomaly.query.filter_by(status="Resolved").count(),
        "integrity_alerts": Anomaly.query.filter_by(anomaly_type="Data Integrity Violation").count()
    })

@app.route('/api/voters', methods=['GET', 'POST'])
@login_required
def api_voters():
    if request.method == 'POST':
        data = request.json
        dob = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date() if data.get('date_of_birth') else None
        
        new_voter = Voter(
            registration_id=data['registration_id'],
            full_name=data['full_name'],
            national_id=data['national_id'],
            date_of_birth=dob,
            county=data['county'],
            constituency=data['constituency'],
            ward=data['ward'],
            verification_status='Pending'
        )
        new_voter.integrity_hash = new_voter.calculate_hash()
        
        db.session.add(new_voter)
        db.session.commit()

        log_action("Voter Registration", "Voter", new_voter.id, f"Created voter {new_voter.registration_id}")
        anomalies = run_anomaly_checks(new_voter)

        return jsonify({
            "message": "Voter created successfully",
            "voter_id": new_voter.id,
            "anomalies_detected": len(anomalies)
        }), 201

    voters = Voter.query.all()
    out = []
    for v in voters:
        out.append({
            "id": v.id,
            "registration_id": v.registration_id,
            "full_name": v.full_name,
            "national_id": f"****{v.national_id[-4:]}" if len(v.national_id) >= 4 else v.national_id,
            "raw_national_id": v.national_id,
            "county": v.county,
            "constituency": v.constituency,
            "ward": v.ward,
            "verification_status": v.verification_status,
            "integrity_hash": v.integrity_hash
        })
    return jsonify(out)

@app.route('/api/integrity/check/<int:voter_id>', methods=['POST'])
@login_required
def check_integrity(voter_id):
    voter = Voter.query.get_or_404(voter_id)
    calculated = voter.calculate_hash()
    
    if calculated == voter.integrity_hash:
        log_action("Integrity Check Passed", "Voter", voter.id, f"Hash verified for {voter.registration_id}")
        return jsonify({"status": "INTEGRITY_VERIFIED", "match": True})
    else:
        anomaly = Anomaly(
            voter_id=voter.id,
            anomaly_type="Data Integrity Violation",
            severity="Critical",
            description=f"Calculated hash ({calculated[:10]}...) does not match recorded database hash ({voter.integrity_hash[:10]}...)."
        )
        db.session.add(anomaly)
        db.session.commit()
        log_action("Integrity Violation Detected", "Voter", voter.id, f"Integrity failure on {voter.registration_id}")
        return jsonify({"status": "INTEGRITY_VIOLATION_DETECTED", "match": False}), 400

@app.route('/api/audit-logs', methods=['GET'])
@login_required
def api_audit_logs():
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).all()
    out = []
    for l in logs:
        out.append({
            "id": l.id,
            "user_id": l.user_id,
            "action": l.action,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "description": l.description,
            "ip_address": l.ip_address,
            "created_at": l.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    return jsonify(out)

# --- ANOMALY MANAGEMENT APIS ---

@app.route('/api/anomalies', methods=['GET'])
@login_required
def api_anomalies():
    anomalies = Anomaly.query.order_by(Anomaly.created_at.desc()).all()
    out = []
    for a in anomalies:
        out.append({
            "id": a.id,
            "voter_id": a.voter_id,
            "anomaly_type": a.anomaly_type,
            "severity": a.severity,
            "status": a.status,
            "description": a.description,
            "investigator": getattr(a, 'investigator', 'Unassigned'),
            "notes": getattr(a, 'notes', ''),
            "created_at": a.created_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(a, 'created_at') else ''
        })
    return jsonify(out)

@app.route('/api/anomalies/<int:anomaly_id>', methods=['GET'])
@login_required
def api_anomaly_detail(anomaly_id):
    anomaly = Anomaly.query.get_or_404(anomaly_id)
    voter_data = None
    if anomaly.voter_id:
        v = Voter.query.get(anomaly.voter_id)
        if v:
            voter_data = {
                "id": v.id,
                "registration_id": v.registration_id,
                "full_name": v.full_name,
                "national_id": v.national_id,
                "county": v.county,
                "constituency": v.constituency,
                "ward": v.ward,
                "verification_status": v.verification_status,
                "integrity_hash": v.integrity_hash,
                "calculated_hash": v.calculate_hash()
            }
    
    return jsonify({
        "anomaly": {
            "id": anomaly.id,
            "anomaly_type": anomaly.anomaly_type,
            "severity": anomaly.severity,
            "status": anomaly.status,
            "description": anomaly.description,
            "investigator": getattr(anomaly, 'investigator', 'Unassigned'),
            "notes": getattr(anomaly, 'notes', '')
        },
        "affected_record": voter_data
    })

@app.route('/api/anomalies/<int:anomaly_id>/update', methods=['POST'])
@login_required
def api_update_anomaly(anomaly_id):
    anomaly = Anomaly.query.get_or_404(anomaly_id)
    data = request.json or {}

    if 'investigator' in data:
        anomaly.investigator = data['investigator']
    if 'notes' in data:
        anomaly.notes = data['notes']
    if 'status' in data:
        anomaly.status = data['status']

    db.session.commit()

    log_action(
        "Anomaly Updated", 
        "Anomaly", 
        anomaly.id, 
        f"Updated anomaly #{anomaly.id} to status '{anomaly.status}' by {data.get('investigator', 'Unassigned')}."
    )

    return jsonify({"message": "Anomaly updated successfully"})

# Application Entry Point
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Seed default administrator
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            hashed_pw = generate_password_hash('AdminPass123!', method='pbkdf2:sha256')
            default_admin = User(
                username='admin',
                email='admin@elivra.org',
                password_hash=hashed_pw,
                role='Administrator',
                status='Active'
            )
            db.session.add(default_admin)
            db.session.commit()
            print("[ELIVRA] Fresh setup initialized. Default admin: admin / AdminPass123!")

    app.run(debug=True)