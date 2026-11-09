from models import db, Voter, Anomaly

def run_anomaly_checks(voter):
    anomalies = []

    # Check 1: Duplicate National ID
    duplicate_nid = Voter.query.filter(Voter.national_id == voter.national_id, Voter.id != voter.id).first()
    if duplicate_nid:
        a = Anomaly(
            voter_id=voter.id,
            anomaly_type="Duplicate National ID",
            severity="High",
            description=f"National ID {voter.national_id} matches existing voter ID {duplicate_nid.id}."
        )
        anomalies.append(a)

    # Check 2: Duplicate Registration ID
    duplicate_reg = Voter.query.filter(Voter.registration_id == voter.registration_id, Voter.id != voter.id).first()
    if duplicate_reg:
        a = Anomaly(
            voter_id=voter.id,
            anomaly_type="Duplicate Registration ID",
            severity="Critical",
            description=f"Registration ID {voter.registration_id} is already in use."
        )
        anomalies.append(a)

    for anomaly in anomalies:
        db.session.add(anomaly)
    
    if anomalies:
        db.session.commit()

    return anomalies