"""
OntServe Configuration Package

Provides standalone configuration loading for OntServe without dependency on shared services.
"""

from .config_loader import load_ontserve_config, ConfigLoader

__all__ = ['load_ontserve_config', 'ConfigLoader']
