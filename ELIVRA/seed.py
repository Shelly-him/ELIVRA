from datetime import datetime, date
from app import app
from models import db, User, Voter, Anomaly, AuditLog

def seed_database():
    with app.app_context():
        # Ensure tables exist
        db.create_all()

        # Clear existing data for a clean test run
        Anomaly.query.delete()
        Voter.query.delete()
        AuditLog.query.delete()
        db.session.commit()

        # Get default admin user for audit log mapping
        admin = User.query.filter_by(username='admin').first()
        admin_id = admin.id if admin else None

        print("[ELIVRA SEED] Preloading Nationwide Kenya voter anomaly dataset...")

        # --- 1. PRELOAD NATIONWIDE VOTER RECORDS ---
        voters = [
            # Verified Voter - Nairobi County
            Voter(
                registration_id="NRB-2026-101",
                full_name="Wanjiku Mwangi",
                national_id="30192847",
                date_of_birth=date(1992, 4, 15),
                county="Nairobi",
                constituency="Westlands",
                ward="Parklands",
                verification_status="Verified"
            ),
            # Verified Voter - Mombasa County
            Voter(
                registration_id="MSA-2026-202",
                full_name="Hassan Said Ali",
                national_id="29481029",
                date_of_birth=date(1988, 11, 23),
                county="Mombasa",
                constituency="Mvita",
                ward="Majengo",
                verification_status="Verified"
            ),
            # Scenario 1: Duplicate Registration (Nairobi vs. Eldoret/Uasin Gishu)
            Voter(
                registration_id="NRB-2026-303A",
                full_name="Kipchumba Kiprop",
                national_id="32849102",
                date_of_birth=date(1996, 7, 8),
                county="Nairobi",
                constituency="Starehe",
                ward="Pangani",
                verification_status="Pending"
            ),
            Voter(
                registration_id="UGS-2026-303B",
                full_name="Kipchumba Kiprop",
                national_id="32849102",  # Duplicate National ID across counties
                date_of_birth=date(1996, 7, 8),
                county="Uasin Gishu",
                constituency="Ainabkoi",
                ward="Kapsoya",
                verification_status="Pending"
            ),
            # Scenario 2: Conflicting Details / Underage DOB (Mombasa County)
            Voter(
                registration_id="MSA-2026-404",
                full_name="Fatuma Amina",
                national_id="18491029",
                date_of_birth=date(2009, 9, 12),  # Underage conflict
                county="Mombasa",
                constituency="Kisauni",
                ward="Bamburi",
                verification_status="Pending"
            ),
            # Scenario 4: Hash Integrity Tampering Mismatch (Nakuru County)
            Voter(
                registration_id="NKR-2026-505",
                full_name="Maina Kamau",
                national_id="24910293",
                date_of_birth=date(1985, 2, 28),
                county="Nakuru",
                constituency="Nakuru East",
                ward="Flamingo",
                verification_status="Verified"
            ),
            # Verified Voter - Garissa County
            Voter(
                registration_id="GSA-2026-606",
                full_name="Abdi Mohamed Noor",
                national_id="31920481",
                date_of_birth=date(1990, 6, 19),
                county="Garissa",
                constituency="Garissa Township",
                ward="Iftin",
                verification_status="Verified"
            )
        ]

        # Calculate initial hashes
        for v in voters:
            v.integrity_hash = v.calculate_hash()
            db.session.add(v)

        db.session.commit()

        # Corrupt stored hash on Maina Kamau (Nakuru County) to simulate database tampering
        tampered_voter = Voter.query.filter_by(registration_id="NKR-2026-505").first()
        if tampered_voter:
            tampered_voter.integrity_hash = "TAMPERED_HASH_FAILURE_NAKURU_SEC_99"
            db.session.commit()

        # --- 2. PRELOAD ANOMALIES ACROSS KENYA ---
        voter_dupe = Voter.query.filter_by(registration_id="UGS-2026-303B").first()
        voter_underage = Voter.query.filter_by(registration_id="MSA-2026-404").first()
        voter_tampered = Voter.query.filter_by(registration_id="NKR-2026-505").first()

        anomalies = [
            # Scenario 1: Inter-County Duplicate Registration
            Anomaly(
                voter_id=voter_dupe.id if voter_dupe else None,
                anomaly_type="Duplicate Registration",
                severity="High",
                status="Open",
                description="Cross-county collision: National ID 32849102 registered in Nairobi (Starehe) and Uasin Gishu (Ainabkoi)."
            ),
            # Scenario 2: Underage Birthdate Conflict
            Anomaly(
                voter_id=voter_underage.id if voter_underage else None,
                anomaly_type="Conflicting Personal Details",
                severity="Medium",
                status="Open",
                description="Age restriction failure: DOB (2009-09-12) submitted in Mombasa (Kisauni) is under legal voting age."
            ),
            # Scenario 3: BVR Kit Packet Loss / Missing Record
            Anomaly(
                voter_id=None,  # No record exists in database
                anomaly_type="Missing Registration Record",
                severity="High",
                status="Open",
                description="BVR Sequence Gap: Garissa Township Kit #09 logged packet GSA-2026-707, but record was not committed to central DB."
            ),
            # Scenario 4: Cryptographic Hash Tampering
            Anomaly(
                voter_id=voter_tampered.id if voter_tampered else None,
                anomaly_type="Data Integrity Violation",
                severity="Critical",
                status="Open",
                description="Database tampering detected: Stored hash on Nakuru record NKR-2026-505 failed cryptographic recalculation."
            )
        ]

        for a in anomalies:
            db.session.add(a)

        # --- 3. PRELOAD NATIONWIDE AUDIT LOGS ---
        logs = [
            # Scenario 5: Direct DB Modification Bypassing API
            AuditLog(
                user_id=admin_id,
                action="UNAUTHORIZED_DB_UPDATE",
                entity_type="Voter",
                entity_id=voter_tampered.id if voter_tampered else None,
                description="SUSPICIOUS MODIFICATION: Record NKR-2026-505 modified directly in SQLite bypassing Flask API layer.",
                ip_address="192.168.10.42"
            ),
            AuditLog(
                user_id=admin_id,
                action="ANOMALY_TRIGGERED",
                entity_type="Voter",
                entity_id=voter_dupe.id if voter_dupe else None,
                description="Duplicate ID alert generated across Nairobi & Uasin Gishu BVR sync streams.",
                ip_address="127.0.0.1"
            ),
            AuditLog(
                user_id=admin_id,
                action="SYSTEM_AUDIT",
                entity_type="System",
                entity_id=None,
                description="Nationwide integrity verification run across all 47 counties completed.",
                ip_address="127.0.0.1"
            )
        ]

        for l in logs:
            db.session.add(l)

        db.session.commit()
        print("[ELIVRA SEED] Database preloaded with nationwide Kenyan anomaly scenarios successfully!")

if __name__ == '__main__':
    seed_database()