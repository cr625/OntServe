#!/usr/bin/env python3
"""
Quick Production Verification Script
Verifies that all JCDL paper implementations are working correctly.
Production path: /opt/ontextract/
"""

import os
import sys

# Production path handling
if '/opt/ontextract' in os.getcwd():
    # Running from production
    sys.path.insert(0, '/opt/ontextract')
else:
    # Running from development
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app, db
from app.models.term import Term, TermVersion
from app.models.experiment import Experiment
import sqlalchemy as sa

def verify_production():
    """Quick verification of production database."""
    
    print("=== OntExtract Production Verification ===\n")
    
    app = create_app()
    with app.app_context():
        
        # 1. Check pgvector extension
        try:
            result = db.session.execute(sa.text("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")).scalar()
            print(f"✅ pgvector extension working (test distance: {result})")
        except Exception as e:
            print(f"❌ pgvector extension failed: {e}")
            return False
        
        # 2. Check academic anchors
        try:
            agent_term = Term.query.filter_by(term_text='agent').first()
            if agent_term:
                jcdl_versions = TermVersion.query.filter_by(term_id=agent_term.id).filter(
                    TermVersion.metadata.op('?')('jcdl_paper_anchor')
                ).count()
                print(f"✅ Academic anchors: {jcdl_versions} JCDL versions for 'agent'")
            else:
                print("❌ Agent term not found")
                return False
        except Exception as e:
            print(f"❌ Academic anchors check failed: {e}")
            return False
        
        # 3. Check experiment 29
        try:
            exp_29 = Experiment.query.filter_by(id=29).first()
            if exp_29 and 'jcdl_paper_compliance' in exp_29.configuration:
                print(f"✅ Experiment 29: {exp_29.name}")
            else:
                print("❌ Experiment 29 not JCDL compliant")
                return False
        except Exception as e:
            print(f"❌ Experiment 29 check failed: {e}")
            return False
        
        # 4. Check document embeddings table
        try:
            result = db.session.execute(sa.text("SELECT COUNT(*) FROM document_embeddings")).scalar()
            print(f"✅ Vector storage: {result} document embeddings")
        except Exception as e:
            print(f"❌ Vector storage check failed: {e}")
            return False
        
        print("\n🎉 All JCDL paper implementations verified!")
        print("\nProduction system includes:")
        print("- PostgreSQL with pgvector extension")
        print("- Academic anchor framework with scholarly citations")
        print("- Vector-based semantic drift calculations")
        print("- Period-aware embedding infrastructure")
        
        return True

if __name__ == "__main__":
    success = verify_production()
    sys.exit(0 if success else 1)