import hashlib
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='Administrator')
    status = db.Column(db.String(20), default='Active')
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to AuditLog
    audit_logs = db.relationship('AuditLog', backref='user', lazy=True)


class Voter(db.Model):
    __tablename__ = 'voters'
    
    id = db.Column(db.Integer, primary_key=True)
    registration_id = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    
    # Indexed for rapid duplicate checks, but not constrained to unique
    national_id = db.Column(db.String(50), index=True, nullable=False)
    
    date_of_birth = db.Column(db.Date, nullable=True)
    county = db.Column(db.String(100))
    constituency = db.Column(db.String(100))
    ward = db.Column(db.String(100))
    verification_status = db.Column(db.String(50), default='Pending')
    integrity_hash = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to Anomaly
    anomalies = db.relationship('Anomaly', backref='voter', lazy=True)

    def calculate_hash(self):
        data = f"{self.registration_id}:{self.full_name}:{self.national_id}:{self.county}:{self.constituency}:{self.ward}"
        return hashlib.sha256(data.encode('utf-8')).hexdigest()


class Anomaly(db.Model):
    __tablename__ = 'anomalies'
    
    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.Integer, db.ForeignKey('voters.id'), nullable=True)
    anomaly_type = db.Column(db.String(100), nullable=False)
    severity = db.Column(db.String(20), default='Medium')
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='Open')
    investigator = db.Column(db.String(100), default='Unassigned')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)