"""
OntServe User model with ontology-specific permissions
"""
import sys
import os

# Add the shared directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


def create_ontserve_user_model(db):
    """Create OntServe-specific User model"""
    
    class User(UserMixin, db.Model):
        """OntServe User model with ontology management permissions"""
        
        __tablename__ = 'users'
        
        # Core user fields (from shared auth)
        id = db.Column(db.Integer, primary_key=True)
        username = db.Column(db.String(80), unique=True, nullable=False, index=True)
        email = db.Column(db.String(120), unique=True, nullable=False, index=True)
        password_hash = db.Column(db.String(256), nullable=False)
        
        # Profile information
        first_name = db.Column(db.String(50))
        last_name = db.Column(db.String(50))
        organization = db.Column(db.String(100))
        
        # Account status
        is_active = db.Column(db.Boolean, default=True, nullable=False)
        is_admin = db.Column(db.Boolean, default=False, nullable=False)
        
        # OntServe-specific permissions
        can_import_ontologies = db.Column(db.Boolean, default=True, nullable=False)
        can_edit_ontologies = db.Column(db.Boolean, default=True, nullable=False)
        can_delete_ontologies = db.Column(db.Boolean, default=False, nullable=False)
        can_publish_versions = db.Column(db.Boolean, default=True, nullable=False)
        can_access_api = db.Column(db.Boolean, default=True, nullable=False)
        
        # Timestamps - Use timezone-aware datetime
        created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
        updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
        last_login = db.Column(db.DateTime)
        
        def __init__(self, username, email, password, **kwargs):
            self.username = username
            self.email = email
            self.set_password(password)
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)
        
        def set_password(self, password):
            """Hash and set the user's password"""
            self.password_hash = generate_password_hash(password)
        
        def check_password(self, password):
            """Check if provided password matches the hash"""
            return check_password_hash(self.password_hash, password)
        
        def get_full_name(self):
            """Get the user's full name"""
            if self.first_name and self.last_name:
                return f"{self.first_name} {self.last_name}"
            return self.username
        
        def can_perform_action(self, action):
            """Check if user can perform a specific action"""
            if self.is_admin:
                return True  # Admins can do everything
                
            permission_map = {
                'import': self.can_import_ontologies,
                'edit': self.can_edit_ontologies,
                'delete': self.can_delete_ontologies,
                'publish': self.can_publish_versions,
                'api': self.can_access_api,
            }
            
            return permission_map.get(action, False)
        
        def to_dict(self):
            """Convert user to dictionary for API responses"""
            return {
                'id': self.id,
                'username': self.username,
                'email': self.email,
                'full_name': self.get_full_name(),
                'organization': self.organization,
                'is_active': self.is_active,
                'is_admin': self.is_admin,
                'permissions': {
                    'can_import_ontologies': self.can_import_ontologies,
                    'can_edit_ontologies': self.can_edit_ontologies,
                    'can_delete_ontologies': self.can_delete_ontologies,
                    'can_publish_versions': self.can_publish_versions,
                    'can_access_api': self.can_access_api,
                },
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'last_login': self.last_login.isoformat() if self.last_login else None
            }
        
        def __repr__(self):
            return f'<OntServeUser {self.username}>'
    
    return User