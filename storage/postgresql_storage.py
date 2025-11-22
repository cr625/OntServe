"""
PostgreSQL storage backend implementation for OntServe.

Provides concrete implementation of the StorageBackend interface
using PostgreSQL with pgvector for semantic search capabilities.
"""

import os
import json
import hashlib
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import asyncio

import asyncpg
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from psycopg2.pool import SimpleConnectionPool

from .base import StorageBackend, StorageError

logger = logging.getLogger(__name__)


class PostgreSQLStorage(StorageBackend):
    """
    PostgreSQL storage backend with vector search capabilities.
    
    Supports both synchronous and asynchronous operations for ontology
    and concept storage with full versioning and audit trail.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize PostgreSQL storage backend.
        
        Args:
            config: Configuration dictionary containing:
                - db_url: PostgreSQL connection URL
                - pool_size: Connection pool size (default: 10)
                - pool_max_size: Maximum pool size (default: 20)
                - timeout: Query timeout in seconds (default: 30)
                - enable_vector_search: Enable pgvector features (default: True)
        """
        # Set config first
        self.config = config or {}
        
        # Database configuration - set before calling super().__init__()
        self.db_url = self.config.get('db_url') or os.environ.get(
            'ONTSERVE_DB_URL',
            'postgresql://postgres:PASS@localhost:5432/ontserve'
        )
        
        self.pool_size = self.config.get('pool_size', 5)
        self.pool_max_size = self.config.get('pool_max_size', 20)
        self.timeout = self.config.get('timeout', 30)
        self.enable_vector_search = self.config.get('enable_vector_search', True)
        
        # Connection pools (will be initialized in _initialize)
        self._sync_pool = None
        self._async_pool = None
        
        logger.info(f"PostgreSQL storage initialized with pool size {self.pool_size}")
        
        # Now call super to trigger _initialize()
        super().__init__(config)
    
    def _initialize(self):
        """Initialize database connections and verify schema."""
        try:
            # Parse database URL for connection parameters
            import urllib.parse
            parsed = urllib.parse.urlparse(self.db_url)
            
            self._db_params = {
                'host': parsed.hostname,
                'port': parsed.port or 5432,
                'database': parsed.path.lstrip('/'),
                'user': parsed.username,
                'password': parsed.password
            }
            
            # Create synchronous connection pool
            self._sync_pool = SimpleConnectionPool(
                minconn=1,
                maxconn=self.pool_size,
                **self._db_params
            )
            
            # Test connection and verify schema
            self._verify_schema()
            
            logger.info("PostgreSQL storage backend initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL storage: {e}")
            raise StorageError(f"Database initialization failed: {str(e)}")
    
    def _verify_schema(self):
        """Verify that the required database schema exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check for required tables
            required_tables = [
                'domains', 'ontologies', 'ontology_versions', 
                'concepts', 'concept_versions', 'concept_triples',
                'candidate_metadata', 'approval_workflows'
            ]
            
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = ANY(%s)
            """, (required_tables,))
            
            existing_tables = {row[0] for row in cursor.fetchall()}
            missing_tables = set(required_tables) - existing_tables
            
            if missing_tables:
                raise StorageError(
                    f"Missing required tables: {', '.join(missing_tables)}. "
                    "Please run the schema.sql file to initialize the database."
                )
            
            # Check for pgvector extension if vector search is enabled
            if self.enable_vector_search:
                cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
                if not cursor.fetchone()[0]:
                    logger.warning("pgvector extension not found. Vector search will be disabled.")
                    self.enable_vector_search = False
    
    def _get_connection(self):
        """Get a connection from the pool."""
        if not self._sync_pool:
            raise StorageError("Database connection pool not initialized")
        return self._sync_pool.getconn()
    
    def _return_connection(self, conn):
        """Return a connection to the pool."""
        if self._sync_pool:
            self._sync_pool.putconn(conn)
    
    async def _get_async_connection(self):
        """Get an async connection."""
        if not self._async_pool:
            # Create async pool if not exists
            self._async_pool = await asyncpg.create_pool(
                self.db_url,
                min_size=1,
                max_size=self.pool_size,
                command_timeout=self.timeout
            )
        return await self._async_pool.acquire()
    
    def _execute_query(self, query: str, params: Tuple = (), fetch_one: bool = False, 
                      fetch_all: bool = False) -> Any:
        """Execute a query with error handling."""
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                
                result = None
                if fetch_one:
                    result = cursor.fetchone()
                elif fetch_all:
                    result = cursor.fetchall()
                else:
                    result = cursor.rowcount
                
                # Always commit the transaction
                conn.commit()
                return result
                    
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database query error: {e}")
            logger.debug(f"Query: {query}")
            logger.debug(f"Params: {params}")
            raise StorageError(f"Database operation failed: {str(e)}")
        finally:
            if conn:
                self._return_connection(conn)
    
    def _generate_content_hash(self, content: str) -> str:
        """Generate SHA-256 hash of content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    # Implementation of abstract methods from StorageBackend
    
    def store(self, ontology_id: str, content: str, 
              metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Store an ontology with versioning."""
        try:
            # Parse ontology_id to extract domain and name
            if ':' in ontology_id:
                domain_name, ontology_name = ontology_id.split(':', 1)
            else:
                domain_name = 'engineering-ethics'  # Default domain
                ontology_name = ontology_id
            
            metadata = metadata or {}
            content_hash = self._generate_content_hash(content)
            
            # Get or create domain
            domain_id = self._get_or_create_domain(domain_name)
            
            # Get or create ontology
            ontology_db_id = self._get_or_create_ontology(domain_id, ontology_name, metadata)
            
            # Create new version
            version_number = self._create_ontology_version(
                ontology_db_id, content, content_hash, metadata
            )
            
            return {
                'ontology_id': ontology_id,
                'version_number': version_number,
                'content_hash': content_hash,
                'stored_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            raise StorageError(f"Failed to store ontology {ontology_id}: {str(e)}")
    
    def retrieve(self, ontology_id: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve an ontology."""
        try:
            # Parse ontology_id
            if ':' in ontology_id:
                domain_name, ontology_name = ontology_id.split(':', 1)
            else:
                domain_name = 'engineering-ethics'
                ontology_name = ontology_id
            
            if version:
                # Retrieve specific version
                query = """
                    SELECT ov.content, ov.metadata, ov.version_number,
                           ov.created_at, ov.created_by, o.name, d.name as domain_name
                    FROM ontology_versions ov
                    JOIN ontologies o ON ov.ontology_id = o.id
                    JOIN domains d ON o.domain_id = d.id
                    WHERE d.name = %s AND o.name = %s AND ov.version_number = %s
                """
                params = (domain_name, ontology_name, int(version))
            else:
                # Retrieve latest version
                query = """
                    SELECT ov.content, ov.metadata, ov.version_number,
                           ov.created_at, ov.created_by, o.name, d.name as domain_name
                    FROM ontology_versions ov
                    JOIN ontologies o ON ov.ontology_id = o.id
                    JOIN domains d ON o.domain_id = d.id
                    WHERE d.name = %s AND o.name = %s AND ov.is_current = true
                """
                params = (domain_name, ontology_name)
            
            result = self._execute_query(query, params, fetch_one=True)
            
            if not result:
                raise StorageError(f"Ontology not found: {ontology_id}")
            
            return {
                'content': result['content'],
                'metadata': result['metadata'] or {},
                'version': str(result['version_number']),
                'created_at': result['created_at'].isoformat(),
                'created_by': result['created_by'],
                'ontology_name': result['name'],
                'domain_name': result['domain_name']
            }
            
        except Exception as e:
            if "not found" in str(e):
                raise
            raise StorageError(f"Failed to retrieve ontology {ontology_id}: {str(e)}")
    
    def exists(self, ontology_id: str) -> bool:
        """Check if an ontology exists."""
        try:
            if ':' in ontology_id:
                domain_name, ontology_name = ontology_id.split(':', 1)
            else:
                domain_name = 'engineering-ethics'
                ontology_name = ontology_id
            
            query = """
                SELECT 1 FROM ontologies o
                JOIN domains d ON o.domain_id = d.id
                WHERE d.name = %s AND o.name = %s
            """
            
            result = self._execute_query(query, (domain_name, ontology_name), fetch_one=True)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error checking ontology existence: {e}")
            return False
    
    def delete(self, ontology_id: str, version: Optional[str] = None) -> bool:
        """Delete an ontology or specific version."""
        try:
            if ':' in ontology_id:
                domain_name, ontology_name = ontology_id.split(':', 1)
            else:
                domain_name = 'engineering-ethics'
                ontology_name = ontology_id
            
            if version:
                # Delete specific version
                query = """
                    DELETE FROM ontology_versions ov
                    USING ontologies o, domains d
                    WHERE ov.ontology_id = o.id AND o.domain_id = d.id
                    AND d.name = %s AND o.name = %s AND ov.version_number = %s
                """
                params = (domain_name, ontology_name, int(version))
            else:
                # Delete entire ontology (cascade will handle versions)
                query = """
                    DELETE FROM ontologies o
                    USING domains d
                    WHERE o.domain_id = d.id AND d.name = %s AND o.name = %s
                """
                params = (domain_name, ontology_name)
            
            rows_affected = self._execute_query(query, params)
            return rows_affected > 0
            
        except Exception as e:
            raise StorageError(f"Failed to delete ontology {ontology_id}: {str(e)}")
    
    def list_ontologies(self, filter_criteria: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """List available ontologies."""
        try:
            where_clauses = ["d.is_active = true"]
            params = []
            
            if filter_criteria:
                if 'domain' in filter_criteria:
                    where_clauses.append("d.name = %s")
                    params.append(filter_criteria['domain'])
                
                if 'is_base' in filter_criteria:
                    where_clauses.append("o.is_base = %s")
                    params.append(filter_criteria['is_base'])
            
            query = f"""
                SELECT o.name, o.description, o.base_uri, o.is_base, o.is_editable,
                       o.created_at, o.updated_at, o.metadata,
                       d.name as domain_name, d.display_name as domain_display_name,
                       COUNT(ov.id) as version_count,
                       MAX(ov.version_number) as latest_version
                FROM ontologies o
                JOIN domains d ON o.domain_id = d.id
                LEFT JOIN ontology_versions ov ON o.id = ov.ontology_id
                WHERE {' AND '.join(where_clauses)}
                GROUP BY o.id, o.name, o.description, o.base_uri, o.is_base, 
                         o.is_editable, o.created_at, o.updated_at, o.metadata,
                         d.name, d.display_name
                ORDER BY d.display_name, o.name
            """
            
            results = self._execute_query(query, tuple(params), fetch_all=True)
            
            return [
                {
                    'name': row['name'],
                    'description': row['description'],
                    'base_uri': row['base_uri'],
                    'is_base': row['is_base'],
                    'is_editable': row['is_editable'],
                    'domain_name': row['domain_name'],
                    'domain_display_name': row['domain_display_name'],
                    'version_count': row['version_count'],
                    'latest_version': row['latest_version'],
                    'created_at': row['created_at'].isoformat(),
                    'updated_at': row['updated_at'].isoformat(),
                    'metadata': row['metadata'] or {}
                }
                for row in results
            ]
            
        except Exception as e:
            raise StorageError(f"Failed to list ontologies: {str(e)}")
    
    def list_versions(self, ontology_id: str) -> List[Dict[str, Any]]:
        """List available versions of an ontology."""
        try:
            if ':' in ontology_id:
                domain_name, ontology_name = ontology_id.split(':', 1)
            else:
                domain_name = 'engineering-ethics'
                ontology_name = ontology_id
            
            query = """
                SELECT ov.version_number, ov.version_tag, ov.change_summary,
                       ov.created_at, ov.created_by, ov.is_current, ov.metadata
                FROM ontology_versions ov
                JOIN ontologies o ON ov.ontology_id = o.id
                JOIN domains d ON o.domain_id = d.id
                WHERE d.name = %s AND o.name = %s
                ORDER BY ov.version_number DESC
            """
            
            results = self._execute_query(query, (domain_name, ontology_name), fetch_all=True)
            
            return [
                {
                    'version_number': row['version_number'],
                    'version_tag': row['version_tag'],
                    'change_summary': row['change_summary'],
                    'created_at': row['created_at'].isoformat(),
                    'created_by': row['created_by'],
                    'is_current': row['is_current'],
                    'metadata': row['metadata'] or {}
                }
                for row in results
            ]
            
        except Exception as e:
            raise StorageError(f"Failed to list versions for {ontology_id}: {str(e)}")
    
    def get_metadata(self, ontology_id: str, 
                    version: Optional[str] = None) -> Dict[str, Any]:
        """Get metadata for an ontology."""
        try:
            data = self.retrieve(ontology_id, version)
            return data['metadata']
        except Exception as e:
            raise StorageError(f"Failed to get metadata for {ontology_id}: {str(e)}")
    
    def update_metadata(self, ontology_id: str, metadata: Dict[str, Any],
                       version: Optional[str] = None) -> bool:
        """Update metadata for an ontology."""
        try:
            if ':' in ontology_id:
                domain_name, ontology_name = ontology_id.split(':', 1)
            else:
                domain_name = 'engineering-ethics'
                ontology_name = ontology_id
            
            if version:
                # Update specific version metadata
                query = """
                    UPDATE ontology_versions SET metadata = %s
                    WHERE ontology_id = (
                        SELECT o.id FROM ontologies o
                        JOIN domains d ON o.domain_id = d.id
                        WHERE d.name = %s AND o.name = %s
                    ) AND version_number = %s
                """
                params = (Json(metadata), domain_name, ontology_name, int(version))
            else:
                # Update ontology metadata
                query = """
                    UPDATE ontologies SET metadata = %s
                    WHERE id = (
                        SELECT o.id FROM ontologies o
                        JOIN domains d ON o.domain_id = d.id
                        WHERE d.name = %s AND o.name = %s
                    )
                """
                params = (Json(metadata), domain_name, ontology_name)
            
            rows_affected = self._execute_query(query, params)
            return rows_affected > 0
            
        except Exception as e:
            raise StorageError(f"Failed to update metadata for {ontology_id}: {str(e)}")
    
    # Helper methods for database operations
    
    def _get_or_create_domain(self, domain_name: str) -> int:
        """Get or create a domain, return its ID."""
        # Try to get existing domain
        query = "SELECT id FROM domains WHERE name = %s"
        result = self._execute_query(query, (domain_name,), fetch_one=True)
        
        if result:
            return result['id']
        
        # Create new domain
        query = """
            INSERT INTO domains (name, display_name, namespace_uri, description)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """
        
        display_name = domain_name.replace('-', ' ').title()
        namespace_uri = f"http://proethica.org/ontology/{domain_name}#"
        description = f"Professional domain: {display_name}"
        
        result = self._execute_query(
            query, 
            (domain_name, display_name, namespace_uri, description),
            fetch_one=True
        )
        
        return result['id']
    
    def _get_or_create_ontology(self, domain_id: int, ontology_name: str, 
                               metadata: Dict[str, Any]) -> int:
        """Get or create an ontology, return its ID."""
        # Try to get existing ontology
        query = "SELECT id FROM ontologies WHERE domain_id = %s AND name = %s"
        result = self._execute_query(query, (domain_id, ontology_name), fetch_one=True)
        
        if result:
            return result['id']
        
        # Create new ontology
        base_uri = metadata.get('base_uri', f"http://proethica.org/ontology/{ontology_name}#")
        description = metadata.get('description', f"Ontology: {ontology_name}")
        is_base = metadata.get('is_base', False)
        is_editable = metadata.get('is_editable', True)
        
        query = """
            INSERT INTO ontologies (domain_id, name, base_uri, description, is_base, is_editable, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """
        
        result = self._execute_query(
            query,
            (domain_id, ontology_name, base_uri, description, is_base, is_editable, Json(metadata)),
            fetch_one=True
        )
        
        return result['id']
    
    def _create_ontology_version(self, ontology_id: int, content: str,
                                content_hash: str, metadata: Dict[str, Any]) -> int:
        """Create a new version of an ontology."""
        # Get next version number
        query = "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version FROM ontology_versions WHERE ontology_id = %s"
        result = self._execute_query(query, (ontology_id,), fetch_one=True)
        version_number = result['next_version'] if result else 1
        
        # Mark all previous versions as non-current
        query = "UPDATE ontology_versions SET is_current = false WHERE ontology_id = %s"
        self._execute_query(query, (ontology_id,))
        
        # Insert new version
        created_by = metadata.get('created_by', 'system')
        change_summary = metadata.get('change_summary', f'Version {version_number}')
        version_tag = metadata.get('version_tag')
        
        query = """
            INSERT INTO ontology_versions 
            (ontology_id, version_number, version_tag, content, content_hash, 
             change_summary, created_by, is_current, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, true, %s)
        """
        
        self._execute_query(
            query,
            (ontology_id, version_number, version_tag, content, content_hash,
             change_summary, created_by, Json(metadata))
        )
        
        return version_number
    
    def close(self):
        """Close database connections."""
        if self._sync_pool:
            self._sync_pool.closeall()
            self._sync_pool = None
        
        if self._async_pool:
            asyncio.create_task(self._async_pool.close())
            self._async_pool = None
        
        logger.info("PostgreSQL storage backend closed")
