"""
Import Foundation Ontologies to OntServer Repository

Imports the downloaded BFO, RO, and IAO ontologies into OntServer's 
ontology repository so they're available for the upgrade workflow.
"""

import shutil
from pathlib import Path
from datetime import datetime

def import_foundations_to_ontserver():
    """Import foundation ontologies to OntServer repository."""
    
    print("Importing Foundation Ontologies to OntServer Repository")
    print("=" * 60)
    
    # Foundation files that were downloaded
    foundation_files = {
        "bfo-2.0.owl": {
            "source": "OntServe/data/foundation/bfo-2.0.owl",
            "target": "storage/ontologies/bfo-2.0.owl",
            "name": "Basic Formal Ontology 2.0"
        },
        "ro-2015.owl": {
            "source": "OntServe/data/foundation/ro-2015.owl", 
            "target": "storage/ontologies/ro-2015.owl",
            "name": "Relations Ontology 2015"
        },
        "iao-2020.owl": {
            "source": "OntServe/data/foundation/iao-2020.owl",
            "target": "storage/ontologies/iao-2020.owl", 
            "name": "Information Artifact Ontology 2020"
        }
    }
    
    # Ensure target directory exists
    Path("storage/ontologies").mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    for file_key, config in foundation_files.items():
        source_path = Path(config["source"])
        target_path = Path(config["target"])
        
        if source_path.exists():
            print(f"📁 Importing {config['name']}...")
            shutil.copy2(source_path, target_path)
            
            # Verify copy
            if target_path.exists():
                size = target_path.stat().st_size
                print(f"   ✅ Imported to {target_path} ({size:,} bytes)")
                success_count += 1
            else:
                print(f"   ❌ Failed to copy {config['name']}")
        else:
            print(f"   ❌ Source file not found: {source_path}")
    
    print("\n" + "=" * 60)
    print(f"Foundation Import Summary: {success_count}/3 ontologies imported")
    
    if success_count == 3:
        print("✅ All foundation ontologies are now in OntServer repository!")
        print("📂 Available at: storage/ontologies/")
        return True
    else:
        print("⚠️ Some foundation ontologies failed to import")
        return False

if __name__ == "__main__":
    import_foundations_to_ontserver()
