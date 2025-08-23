"""
Database models for OntServe Web Application

Uses SQLAlchemy with pgvector extension for semantic search.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, text
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
import uuid

db = SQLAlchemy()


class Domain(db.Model):
    """Professional domains (replacing 'worlds' concept)."""
    
    __tablename__ = 'domains'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False, unique=True)
    display_name = db.Column(db.String(255))
    namespace_uri = db.Column(db.Text, nullable=False, unique=True)
    description = db.Column(db.Text)
    meta_data = db.Column('metadata', db.JSON, default={})  # Map to 'metadata' column in DB
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    ontologies = db.relationship('Ontology', backref='domain', lazy='dynamic')
    
    def __repr__(self):
        return f'<Domain {self.name}>'


class Ontology(db.Model):
    """Main ontology model for storing ontology information."""
    
    __tablename__ = 'ontologies'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    domain_id = db.Column(db.Integer, db.ForeignKey('domains.id'))
    name = db.Column(db.String(255), nullable=False)
    base_uri = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    is_base = db.Column(db.Boolean, default=False)
    is_editable = db.Column(db.Boolean, default=True)
    
    # JSON metadata field for flexible storage
    meta_data = db.Column('metadata', db.JSON, default={})  # Map to 'metadata' column in DB
    
    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    versions = db.relationship('OntologyVersion', back_populates='ontology', 
                              cascade='all, delete-orphan')
    entities = db.relationship('OntologyEntity', back_populates='ontology',
                              cascade='all, delete-orphan')
    
    @property
    def current_content(self):
        """Get the content of the current version."""
        current_version = OntologyVersion.query.filter_by(
            ontology_id=self.id, 
            is_current=True
        ).first()
        return current_version.content if current_version else None
    
    @property
    def current_version(self):
        """Get the current version object."""
        return OntologyVersion.query.filter_by(
            ontology_id=self.id, 
            is_current=True
        ).first()
    
    @property
    def triple_count(self):
        """Get count of total entities (approximation of triples)."""
        return OntologyEntity.query.filter_by(ontology_id=self.id).count()
    
    @property
    def class_count(self):
        """Get count of class entities."""
        return OntologyEntity.query.filter_by(
            ontology_id=self.id, 
            entity_type='class'
        ).count()
    
    @property
    def property_count(self):
        """Get count of property entities."""
        return OntologyEntity.query.filter_by(
            ontology_id=self.id, 
            entity_type='property'
        ).count()
    
    def __repr__(self):
        return f'<Ontology {self.name}>'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ontology to dictionary representation."""
        return {
            'id': self.id,
            'uuid': str(self.uuid),
            'domain_id': self.domain_id,
            'name': self.name,
            'base_uri': self.base_uri,
            'description': self.description,
            'is_base': self.is_base,
            'is_editable': self.is_editable,
            'metadata': self.meta_data if self.meta_data else {},
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'version_count': len(self.versions) if hasattr(self, 'versions') else 0
        }


class OntologyVersion(db.Model):
    """Version tracking for ontologies."""
    
    __tablename__ = 'ontology_versions'
    
    id = db.Column(db.Integer, primary_key=True)
    ontology_id = db.Column(db.Integer, db.ForeignKey('ontologies.id'), nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    version_tag = db.Column(db.String(50))
    content = db.Column(db.Text, nullable=False)
    content_hash = db.Column(db.String(64))  # SHA-256 hash
    change_summary = db.Column(db.Text)
    created_by = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    is_current = db.Column(db.Boolean, default=False)
    is_draft = db.Column(db.Boolean, default=True)  # True for draft versions, False for published
    workflow_status = db.Column(db.String(20), default='draft')  # draft, review, published
    meta_data = db.Column('metadata', db.JSON, default={})
    
    # Relationships
    ontology = db.relationship('Ontology', back_populates='versions')
    
    # Unique constraint on ontology_id + version_number
    __table_args__ = (
        db.UniqueConstraint('ontology_id', 'version_number', name='uq_ontology_version'),
    )
    
    def __repr__(self):
        return f'<OntologyVersion {self.version_number} for Ontology {self.ontology_id}>'


class OntologyEntity(db.Model):
    """
    Extracted entities from ontologies with embeddings for semantic search.
    
    Stores classes, properties, and individuals with their vector embeddings.
    """
    
    __tablename__ = 'ontology_entities'
    
    id = db.Column(db.Integer, primary_key=True)
    ontology_id = db.Column(db.Integer, db.ForeignKey('ontologies.id'), nullable=False)
    
    # Entity information
    entity_type = db.Column(db.String(50), nullable=False)  # class, property, individual
    uri = db.Column(db.Text, nullable=False)
    label = db.Column(db.String(255))
    comment = db.Column(db.Text)
    
    # Hierarchical information
    parent_uri = db.Column(db.Text)  # For subclass/subproperty relationships
    
    # Additional metadata
    domain = db.Column(db.JSON)  # For properties
    range = db.Column(db.JSON)   # For properties
    properties = db.Column(db.JSON)  # For individuals
    
    # Vector embedding for semantic search (384 dimensions for all-MiniLM-L6-v2)
    embedding = db.Column(Vector(384))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    ontology = db.relationship('Ontology', back_populates='entities')
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_entity_type', 'entity_type'),
        Index('idx_entity_label', 'label'),
        Index('idx_ontology_entity', 'ontology_id', 'entity_type'),
        # Vector similarity index will be created separately
    )
    
    def __repr__(self):
        return f'<OntologyEntity {self.entity_type}: {self.label or self.uri}>'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary representation."""
        return {
            'id': self.id,
            'ontology_id': self.ontology_id,
            'entity_type': self.entity_type,
            'uri': self.uri,
            'label': self.label,
            'comment': self.comment,
            'parent_uri': self.parent_uri,
            'domain': self.domain,
            'range': self.range,
            'properties': self.properties
        }
    
    @classmethod
    def search_similar(cls, query_embedding: List[float], 
                      limit: int = 10, 
                      entity_type: Optional[str] = None,
                      ontology_id: Optional[int] = None) -> List['OntologyEntity']:
        """
        Search for similar entities using vector similarity.
        
        Args:
            query_embedding: Query vector
            limit: Maximum number of results
            entity_type: Filter by entity type
            ontology_id: Filter by ontology
            
        Returns:
            List of similar entities ordered by similarity
        """
        query = cls.query
        
        if entity_type:
            query = query.filter_by(entity_type=entity_type)
        if ontology_id:
            query = query.filter_by(ontology_id=ontology_id)
        
        # Use pgvector's <-> operator for cosine distance
        results = query.order_by(
            cls.embedding.cosine_distance(query_embedding)
        ).limit(limit).all()
        
        return results


class SearchHistory(db.Model):
    """Track search queries for analytics and improvement."""
    
    __tablename__ = 'search_history'
    
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.Text, nullable=False)
    query_type = db.Column(db.String(50))  # text, sparql, semantic
    results_count = db.Column(db.Integer)
    execution_time = db.Column(db.Float)  # in seconds
    
    # User tracking (if auth is added)
    user_id = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    
    # Timestamp
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f'<SearchHistory {self.query_type}: {self.query[:50]}...>'


def init_db(app):
    """
    Initialize the database with the Flask app.
    
    Args:
        app: Flask application instance
    """
    db.init_app(app)
    
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Create vector similarity index if it doesn't exist
        try:
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_entity_embedding_vector 
                ON ontology_entities 
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """))
            db.session.commit()
        except Exception as e:
            app.logger.warning(f"Could not create vector index: {e}")
            db.session.rollback()
