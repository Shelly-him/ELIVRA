import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Load environment variables (SECRET_KEY, DATABASE_URL) from a local .env file
load_dotenv()

# --- APP CONFIGURATION ---

app = Flask(__name__)
# Secret key used to sign session cookies. NOTE: the fallback value is only
# suitable for development; always set SECRET_KEY in the environment in production.
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key')
# Database location; defaults to a local SQLite file if DATABASE_URL isn't set
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///elivra.db')
# Disable SQLAlchemy's event system for tracking object changes (saves overhead)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Models and anomaly logic are imported after the app is configured
from models import db, User, Voter, Anomaly, AuditLog
from anomaly_engine import run_anomaly_checks

# Bind the SQLAlchemy instance to this Flask app
db.init_app(app)

# --- AUTHENTICATION SETUP ---

login_manager = LoginManager()
# Unauthenticated users hitting a @login_required route are redirected here
login_manager.login_view = 'login'
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    # Called by Flask-Login on each request to reload the user from the session's stored ID
    return User.query.get(int(user_id))


# --- HELPERS ---

def log_action(action, entity_type=None, entity_id=None, description=""):
    """Write an entry to the audit log.

    Records who did what (if a user is logged in), which entity was affected,
    and the client's IP address. Commits immediately so the log entry is
    persisted even if later logic fails.
    """
    log = AuditLog(
        # Anonymous actions (e.g. failed logins) are stored with user_id = None
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()


# --- AUTH ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Already-logged-in users don't need to see the login page again
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        # The form field accepts either a username or an email address
        username_or_email = request.form.get('identifier')
        password = request.form.get('password')

        # Look the user up by username OR email
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()

        # Verify the submitted password against the stored hash
        if user and check_password_hash(user.password_hash, password):
            # Block deactivated accounts even if the credentials are correct
            if user.status != 'Active':
                flash('Your account has been deactivated.', 'danger')
                return render_template('login.html')

            # Record the login time, then start the session
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)

            log_action("Admin Login", "User", user.id, f"User {user.username} logged in successfully.")
            return redirect(url_for('dashboard'))
        else:
            # Same message for unknown user and wrong password, so attackers
            # can't tell which usernames exist
            flash('Invalid username/email or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    # Log before logout_user() so current_user is still available for the audit entry
    log_action("Admin Logout", "User", current_user.id, f"User {current_user.username} logged out.")
    logout_user()
    return redirect(url_for('login'))


# --- DASHBOARD & PAGES ---

@app.route('/')
@login_required
def dashboard():
    # Renders the main dashboard page; the data itself is loaded via /api/dashboard
    return render_template('dashboard.html', username=current_user.username)


# --- REST APIs ---

@app.route('/api/dashboard', methods=['GET'])
@login_required
def api_dashboard():
    # Summary counts shown on the dashboard: voters, anomalies, and integrity alerts
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
    # POST: register a new voter
    if request.method == 'POST':
        data = request.json
        
        # Parse the optional date of birth (expected format: YYYY-MM-DD)
        dob = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date() if data.get('date_of_birth') else None
        
        new_voter = Voter(
            registration_id=data['registration_id'],
            full_name=data['full_name'],
            national_id=data['national_id'],
            date_of_birth=dob,
            county=data['county'],
            constituency=data['constituency'],
            ward=data['ward'],
            # New registrations always start as Pending until verified
            verification_status='Pending'
        )
        # Store a hash of the record's contents so later tampering can be detected
        new_voter.integrity_hash = new_voter.calculate_hash()
        
        db.session.add(new_voter)
        db.session.commit()

        log_action("Voter Registration", "Voter", new_voter.id, f"Created voter {new_voter.registration_id}")

        # Run anomaly detection (e.g. duplicates, suspicious data) on the new record
        anomalies = run_anomaly_checks(new_voter)

        return jsonify({
            "message": "Voter created successfully",
            "voter_id": new_voter.id,
            "anomalies_detected": len(anomalies)
        }), 201

    # GET: list all voters
    voters = Voter.query.all()
    out = []
    for v in voters:
        out.append({
            "id": v.id,
            "registration_id": v.registration_id,
            "full_name": v.full_name,
            # Masked national ID: only the last 4 characters are shown
            "national_id": f"****{v.national_id[-4:]}" if len(v.national_id) >= 4 else v.national_id,
            # NOTE: the unmasked ID is also returned here, which defeats the masking above
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
    # Recompute the hash from the record's current data
    calculated = voter.calculate_hash()
    
    # Hash matches the stored one -> record hasn't been altered
    if calculated == voter.integrity_hash:
        log_action("Integrity Check Passed", "Voter", voter.id, f"Hash verified for {voter.registration_id}")
        return jsonify({"status": "INTEGRITY_VERIFIED", "match": True})
    else:
        # Mismatch -> the record was modified outside the normal flow; raise a Critical anomaly
        # (only the first 10 characters of each hash are included in the description)
        anomaly = Anomaly(
            voter_id=voter.id,
            anomaly_type="Data Integrity Violation",
            severity="Critical",
            description=f"Calculated hash ({calculated[:10]}...) does not match recorded database hash ({voter.integrity_hash[:10]}...)."
        )
        db.session.add(anomaly)
        db.session.commit()
        log_action("Integrity Violation Detected", "Voter", voter.id, f"Integrity failure on {voter.registration_id}")
        # 400 status signals the failed check to the client
        return jsonify({"status": "INTEGRITY_VIOLATION_DETECTED", "match": False}), 400


@app.route('/api/audit-logs', methods=['GET'])
@login_required
def api_audit_logs():
    # Return every audit entry, newest first
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
    # List all anomalies, newest first
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
            # getattr with defaults guards against the model lacking these optional fields
            "investigator": getattr(a, 'investigator', 'Unassigned'),
            "notes": getattr(a, 'notes', ''),
            "created_at": a.created_at.strftime('%Y-%m-%d %H:%M:%S') if hasattr(a, 'created_at') else ''
        })
    return jsonify(out)


@app.route('/api/anomalies/<int:anomaly_id>', methods=['GET'])
@login_required
def api_anomaly_detail(anomaly_id):
    # Fetch a single anomaly along with the voter record it relates to
    anomaly = Anomaly.query.get_or_404(anomaly_id)
    voter_data = None
    # Some anomalies may not be tied to a specific voter
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
                # Included so investigators can compare stored vs. freshly computed hashes
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
    # Fall back to an empty dict if no JSON body was sent
    data = request.json or {}

    # Partial update: only fields present in the request are changed
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


# --- ENTRY POINT ---

if __name__ == '__main__':
    with app.app_context():
        # Create database tables if they don't exist yet
        db.create_all()
        
        # Seed a default administrator on first run
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            # NOTE: hard-coded default credentials; change the password immediately after first login
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

    # NOTE: debug=True enables the interactive debugger; never use it in production
    app.run(debug=True)