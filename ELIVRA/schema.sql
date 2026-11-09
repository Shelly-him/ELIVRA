-- SQLite Schema for ELIVRA System
PRAGMA foreign_keys = ON;

-- --------------------------------------------------------
-- Table: users
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'Investigator',
    status VARCHAR(20) DEFAULT 'Active',
    last_login DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- --------------------------------------------------------
-- Table: voters
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS voters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    registration_id VARCHAR(50) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL,
    national_id VARCHAR(20) NOT NULL,
    date_of_birth DATE,
    county VARCHAR(100) NOT NULL,
    constituency VARCHAR(100) NOT NULL,
    ward VARCHAR(100) NOT NULL,
    verification_status VARCHAR(50) DEFAULT 'Pending',
    integrity_hash VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- --------------------------------------------------------
-- Table: anomalies
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    voter_id INTEGER,
    anomaly_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) DEFAULT 'Medium',
    status VARCHAR(20) DEFAULT 'Open',
    description TEXT,
    investigator VARCHAR(100) DEFAULT 'Unassigned',
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (voter_id) REFERENCES voters(id) ON DELETE SET NULL
);

-- --------------------------------------------------------
-- Table: audit_logs
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id INTEGER,
    description TEXT,
    ip_address VARCHAR(45),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- --------------------------------------------------------
-- Indexes for performance
-- --------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_voters_national_id ON voters(national_id);
CREATE INDEX IF NOT EXISTS idx_voters_county ON voters(county);
CREATE INDEX IF NOT EXISTS idx_anomalies_status ON anomalies(status);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);