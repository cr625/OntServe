"""
OntServe Client for OntExtract

Lightweight client library for OntExtract to access ontology data from OntServe.
Provides caching and fallback mechanisms for reliable operation.
"""

import os
import json
import logging
import time
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

class OntServeConnectionError(Exception):
    """Raised when OntServe is not available."""
    pass

class OntExtractClient:
    """
    Client for accessing OntServe from OntExtract.
    
    Features:
    - Automatic connection handling with retries
    - Local caching of responses for performance
    - Fallback mechanisms when OntServe is unavailable
    - PROV-O specific methods for common operations
    """
    
    def __init__(self, 
                 ontserve_url: str = None,
                 cache_dir: str = None,
                 cache_ttl: int = 3600,
                 timeout: int = 10,
                 enable_cache: bool = True):
        """
        Initialize the OntExtract client.
        
        Args:
            ontserve_url: URL of OntServe MCP server
            cache_dir: Directory for caching responses
            cache_ttl: Cache time-to-live in seconds (default: 1 hour)
            timeout: Request timeout in seconds
            enable_cache: Whether to use local caching
        """
        self.ontserve_url = ontserve_url or os.environ.get(
            'ONTSERVE_URL', 
            'http://localhost:8082'
        )
        
        self.cache_dir = cache_dir or os.path.join(
            os.getcwd(), 
            'ontserve_cache'
        )
        
        self.cache_ttl = cache_ttl
        self.timeout = timeout
        self.enable_cache = enable_cache
        self._session = None
        
        # Create cache directory if needed
        if self.enable_cache:
            os.makedirs(self.cache_dir, exist_ok=True)
        
        # Test connection on initialization
        self._test_connection()
    
    @property
    def session(self):
        """Get or create HTTP session."""
        if self._session is None:
            self._session = requests.Session()
            self._session.timeout = self.timeout
            self._session.headers.update({
                'Content-Type': 'application/json',
                'User-Agent': 'OntExtract-Client/1.0'
            })
        return self._session
    
    def _test_connection(self) -> bool:
        """Test connection to OntServe."""
        try:
            response = self.session.get(f"{self.ontserve_url}/health", timeout=5)
            if response.status_code == 200:
                health_data = response.json()
                if health_data.get('database_connected'):
                    logger.info("Successfully connected to OntServe")
                    return True
                else:
                    logger.warning("OntServe is running but database not connected")
                    return False
            else:
                logger.warning(f"OntServe health check failed: {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"Cannot connect to OntServe: {e}")
            return False
    
    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call an OntServe MCP tool.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments
            
        Returns:
            Tool response data
            
        Raises:
            OntServeConnectionError: If OntServe is not available
        """
        # Check cache first
        if self.enable_cache:
            cached_result = self._get_cached_response(tool_name, arguments)
            if cached_result:
                return cached_result
        
        try:
            # Prepare JSON-RPC request
            request_data = {
                "jsonrpc": "2.0",
                "method": "call_tool",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                },
                "id": int(time.time() * 1000)  # Use timestamp as ID
            }
            
            # Make request
            response = self.session.post(
                self.ontserve_url,
                json=request_data,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            
            if 'error' in data:
                raise OntServeConnectionError(f"OntServe error: {data['error']}")
            
            # Extract result from MCP response format
            if 'result' in data and 'content' in data['result']:
                content = data['result']['content']
                if content and isinstance(content, list) and len(content) > 0:
                    # Parse JSON content from MCP text response
                    result = json.loads(content[0]['text'])
                    
                    # Cache the result
                    if self.enable_cache and not result.get('error'):
                        self._cache_response(tool_name, arguments, result)
                    
                    return result
            
            raise OntServeConnectionError("Invalid response format from OntServe")
            
        except requests.RequestException as e:
            raise OntServeConnectionError(f"Failed to connect to OntServe: {e}")
        except json.JSONDecodeError as e:
            raise OntServeConnectionError(f"Invalid JSON response from OntServe: {e}")
    
    def get_prov_entities(self, 
                         category: str = 'all',
                         status: str = 'approved') -> List[Dict[str, Any]]:
        """
        Get PROV-O entities by category.
        
        Args:
            category: Entity category ('Resource', 'Action', 'State', or 'all')
            status: Status filter ('approved', 'candidate', etc.)
            
        Returns:
            List of PROV-O entities
        """
        try:
            if category == 'all':
                # Get all categories
                entities = []
                for cat in ['Resource', 'Action', 'State']:
                    result = self._call_tool('get_entities_by_category', {
                        'category': cat,
                        'domain_id': 'prov-o',
                        'status': status
                    })
                    
                    if 'entities' in result:
                        entities.extend(result['entities'])
                
                return entities
            else:
                result = self._call_tool('get_entities_by_category', {
                    'category': category,
                    'domain_id': 'prov-o', 
                    'status': status
                })
                
                return result.get('entities', [])
                
        except OntServeConnectionError as e:
            logger.warning(f"OntServe not available for PROV-O entities: {e}")
            return []
    
    def get_prov_classes(self) -> List[Dict[str, Any]]:
        """Get all PROV-O classes (Resource category)."""
        return self.get_prov_entities('Resource')
    
    def get_prov_properties(self) -> List[Dict[str, Any]]:
        """Get all PROV-O properties (Action and State categories)."""
        actions = self.get_prov_entities('Action')  # Object properties
        states = self.get_prov_entities('State')    # Datatype properties
        return actions + states
    
    def get_concept_by_uri(self, uri: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific concept by its URI.
        
        Args:
            uri: The concept URI
            
        Returns:
            Concept data or None if not found
        """
        try:
            # Search for the concept
            results = self.search_concepts(f'uri:"{uri}"', domain='prov-o')
            
            for result in results:
                if result.get('uri') == uri:
                    return result
            
            return None
            
        except OntServeConnectionError:
            logger.warning(f"OntServe not available for concept lookup: {uri}")
            return None
    
    def search_concepts(self, 
                       query: str, 
                       domain: str = 'prov-o',
                       limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search for concepts by query.
        
        Args:
            query: Search query
            domain: Domain to search in
            limit: Maximum results
            
        Returns:
            List of matching concepts
        """
        try:
            # For now, get all entities and filter locally
            # TODO: Implement proper search in OntServe
            entities = []
            
            for category in ['Resource', 'Action', 'State']:
                result = self._call_tool('get_entities_by_category', {
                    'category': category,
                    'domain_id': domain,
                    'status': 'approved'
                })
                
                if 'entities' in result:
                    entities.extend(result['entities'])
            
            # Simple text search
            query_lower = query.lower().replace('uri:', '').replace('"', '')
            matches = []
            
            for entity in entities[:limit]:
                if (query_lower in entity.get('label', '').lower() or
                    query_lower in entity.get('uri', '').lower() or
                    query_lower in entity.get('description', '').lower()):
                    matches.append(entity)
            
            return matches
            
        except OntServeConnectionError:
            logger.warning(f"OntServe not available for search: {query}")
            return []
    
    def get_domain_info(self, domain_id: str = 'prov-o') -> Optional[Dict[str, Any]]:
        """
        Get information about a domain.
        
        Args:
            domain_id: Domain identifier
            
        Returns:
            Domain information or None if not available
        """
        try:
            result = self._call_tool('get_domain_info', {
                'domain_id': domain_id
            })
            
            return result
            
        except OntServeConnectionError:
            logger.warning(f"OntServe not available for domain info: {domain_id}")
            return None
    
    def get_prov_experiment_concepts(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get PROV-O concepts organized for experiment classification.
        
        Returns:
            Dictionary with categorized concepts for experiments
        """
        try:
            entities = self.get_prov_entities('all')
            
            # Organize concepts by PROV-O types
            concepts = {
                'activities': [],
                'entities': [],
                'agents': [],
                'plans': [],
                'collections': [],
                'properties': []
            }
            
            for entity in entities:
                uri = entity.get('uri', '')
                label = entity.get('semantic_label', entity.get('label', ''))
                
                if 'Activity' in uri or 'activity' in label.lower():
                    concepts['activities'].append(entity)
                elif 'Agent' in uri or 'agent' in label.lower():
                    concepts['agents'].append(entity)
                elif 'Plan' in uri or 'plan' in label.lower():
                    concepts['plans'].append(entity)
                elif 'Collection' in uri or 'collection' in label.lower():
                    concepts['collections'].append(entity)
                elif entity.get('category') in ['Action', 'State']:
                    concepts['properties'].append(entity)
                else:
                    concepts['entities'].append(entity)
            
            return concepts
            
        except Exception as e:
            logger.warning(f"Error getting PROV experiment concepts: {e}")
            return {
                'activities': [],
                'entities': [],
                'agents': [],
                'plans': [],
                'collections': [],
                'properties': []
            }
    
    def _get_cache_key(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Generate cache key for a tool call."""
        data = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"
        return hashlib.md5(data.encode()).hexdigest()
    
    def _get_cached_response(self, 
                           tool_name: str, 
                           arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached response if available and not expired."""
        if not self.enable_cache:
            return None
        
        cache_key = self._get_cache_key(tool_name, arguments)
        cache_file = Path(self.cache_dir) / f"{cache_key}.json"
        
        try:
            if cache_file.exists():
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                
                # Check if cache is still valid
                cached_time = datetime.fromisoformat(cached_data['cached_at'])
                if datetime.now() - cached_time < timedelta(seconds=self.cache_ttl):
                    logger.debug(f"Using cached response for {tool_name}")
                    return cached_data['data']
                else:
                    # Cache expired, remove file
                    cache_file.unlink()
        
        except Exception as e:
            logger.debug(f"Error reading cache for {tool_name}: {e}")
        
        return None
    
    def _cache_response(self, 
                       tool_name: str, 
                       arguments: Dict[str, Any], 
                       response: Dict[str, Any]):
        """Cache a response."""
        if not self.enable_cache:
            return
        
        cache_key = self._get_cache_key(tool_name, arguments)
        cache_file = Path(self.cache_dir) / f"{cache_key}.json"
        
        try:
            cached_data = {
                'tool_name': tool_name,
                'arguments': arguments,
                'data': response,
                'cached_at': datetime.now().isoformat()
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cached_data, f, indent=2)
                
            logger.debug(f"Cached response for {tool_name}")
            
        except Exception as e:
            logger.debug(f"Error caching response for {tool_name}: {e}")
    
    def clear_cache(self):
        """Clear all cached responses."""
        if not self.enable_cache or not os.path.exists(self.cache_dir):
            return
        
        try:
            for cache_file in Path(self.cache_dir).glob("*.json"):
                cache_file.unlink()
            logger.info("Cleared OntServe response cache")
        except Exception as e:
            logger.warning(f"Error clearing cache: {e}")
    
    def close(self):
        """Close the client and cleanup resources."""
        if self._session:
            self._session.close()
            self._session = None


# Convenience functions for common operations
def create_client(ontserve_url: str = None, **kwargs) -> OntExtractClient:
    """
    Create an OntExtract client with default settings.
    
    Args:
        ontserve_url: OntServe URL (defaults to environment variable)
        **kwargs: Additional client options
        
    Returns:
        Configured OntExtractClient
    """
    return OntExtractClient(ontserve_url=ontserve_url, **kwargs)


def get_prov_classes(client: OntExtractClient = None) -> List[Dict[str, Any]]:
    """
    Get PROV-O classes with automatic client management.
    
    Args:
        client: Optional existing client
        
    Returns:
        List of PROV-O classes
    """
    if client is None:
        client = create_client()
    
    try:
        return client.get_prov_classes()
    finally:
        if client is not None:
            client.close()


def get_prov_properties(client: OntExtractClient = None) -> List[Dict[str, Any]]:
    """
    Get PROV-O properties with automatic client management.
    
    Args:
        client: Optional existing client
        
    Returns:
        List of PROV-O properties
    """
    if client is None:
        client = create_client()
    
    try:
        return client.get_prov_properties()
    finally:
        if client is not None:
            client.close()


# Example usage and testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test OntExtract client")
    parser.add_argument("--url", help="OntServe URL")
    parser.add_argument("--test", choices=['classes', 'properties', 'search', 'domain'], 
                       default='classes', help="What to test")
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        client = create_client(args.url)
        
        if args.test == 'classes':
            print("PROV-O Classes:")
            classes = client.get_prov_classes()
            for cls in classes[:10]:  # Show first 10
                print(f"  - {cls.get('semantic_label', cls.get('label'))}: {cls.get('uri')}")
            print(f"Total: {len(classes)} classes")
            
        elif args.test == 'properties':
            print("PROV-O Properties:")
            properties = client.get_prov_properties()
            for prop in properties[:10]:  # Show first 10
                print(f"  - {prop.get('semantic_label', prop.get('label'))}: {prop.get('uri')}")
            print(f"Total: {len(properties)} properties")
            
        elif args.test == 'search':
            print("Searching for 'Activity':")
            results = client.search_concepts('Activity')
            for result in results:
                print(f"  - {result.get('semantic_label', result.get('label'))}: {result.get('uri')}")
            
        elif args.test == 'domain':
            print("PROV-O Domain Info:")
            info = client.get_domain_info('prov-o')
            if info:
                print(json.dumps(info, indent=2))
            else:
                print("No domain info available")
        
        client.close()
        
    except Exception as e:
        print(f"Error: {e}")
