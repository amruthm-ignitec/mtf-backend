#!/usr/bin/env python3
"""
Production script to create initial admin user
Usage: python scripts/create_admin_user.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import sessionmaker
from app.database.database import engine, Base
from app.models.user import User, UserRole
from app.core.security import hash_password

def create_admin_user():
    """Create initial admin user for production setup."""
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    # Create session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Check if admin user already exists
        existing_admin = db.query(User).filter(User.email == "admin@donoriq.com").first()
        if existing_admin:
            print("✅ Admin user already exists")
            return
        
        # Create admin user
        admin_user = User(
            email="admin@donoriq.com",
            hashed_password=hash_password("admin123"),
            full_name="System Administrator",
            role=UserRole.ADMIN.value,  # Use .value to ensure lowercase 'admin' is used
            is_active=True
        )
        
        db.add(admin_user)
        db.commit()
        print("✅ Admin user created successfully!")
        print("📧 Email: admin@donoriq.com")
        print("🔑 Password: admin123")
        print("⚠️  Please change the password after first login!")
        
    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user()


