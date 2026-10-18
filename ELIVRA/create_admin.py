from app import app, db, User
from werkzeug.security import generate_password_hash
import getpass

def create_admin():
    with app.app_context():
        print("=== ELIVRA Administrator Setup ===")
        username = input("Enter admin username: ").strip()
        email = input("Enter admin email: ").strip()
        password = getpass.getpass("Enter secure admin password: ").strip()
        confirm_pass = getpass.getpass("Confirm admin password: ").strip()

        if password != confirm_pass:
            print("[ERROR] Passwords do not match. Aborting.")
            return

        if User.query.filter((User.username == username) | (User.email == email)).first():
            print("[ERROR] Username or Email already exists.")
            return

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        admin = User(
            username=username,
            email=email,
            password_hash=hashed_password,
            role='Administrator',
            status='Active'
        )
        
        db.session.add(admin)
        db.session.commit()
        print(f"[SUCCESS] Admin account '{username}' successfully created!")

if __name__ == '__main__':
    create_admin()