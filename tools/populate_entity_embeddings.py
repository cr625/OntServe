#!/usr/bin/env python3
"""Populate ``ontology_entities.embedding`` rows where it is NULL.

The proethica auto-commit duplicate matcher does a pgvector cosine
lookup against this column. The schema (``vector(384)`` with an
IVFFlat cosine index) was already in place; this script fills it.

Embedding text matches the ProEthica paper Section 3.5 pattern,
``f"{label}: {comment}"``, so the matcher's candidate-side embedding
and the stored class-side embedding share the same input format.

Usage:
    python tools/populate_entity_embeddings.py
    python tools/populate_entity_embeddings.py --type class
    python tools/populate_entity_embeddings.py --type class --batch 200
    python tools/populate_entity_embeddings.py --dry-run
    python tools/populate_entity_embeddings.py --force  # re-embed all rows

Idempotent by default: only rows where embedding IS NULL are processed.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# OntServe path bootstrap (script lives at OntServe/tools/)
script_dir = Path(__file__).parent
ontserve_root = script_dir.parent
web_dir = ontserve_root / "web"
if str(ontserve_root) not in sys.path:
    sys.path.insert(0, str(ontserve_root))
if str(web_dir) not in sys.path:
    sys.path.insert(0, str(web_dir))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("populate_entity_embeddings")


def build_text(entity) -> str:
    """Compose the embedding text for one entity.

    Returns ``"{label}: {comment}"`` when both are present, ``label``
    alone if no comment, and the URI as a last resort.
    """
    label = (entity.label or "").strip()
    comment = (entity.comment or "").strip()
    if label and comment:
        return f"{label}: {comment}"
    if label:
        return label
    return entity.uri  # last resort; URI is always non-null


def _resolve_device() -> str:
    """Pick the embedding device. EMBEDDINGS_DEVICE overrides; otherwise use the GPU only after a
    real kernel op succeeds, else CPU. Machine-adaptive: the RTX 4090 dev box (Area51) uses CUDA,
    while a dev box with a mismatched CUDA build (cudaErrorNoKernelImageForDevice) or a no-GPU server
    falls back to CPU. Embeddings are computed on whichever local box is capable and shipped to
    production via the DB dump/restore; production never computes them."""
    pref = os.environ.get("EMBEDDINGS_DEVICE")
    if pref:
        return pref
    try:
        import torch
        if torch.cuda.is_available():
            t = torch.zeros(1, device="cuda")
            _ = (t + 1).item()  # force a real kernel; raises on a mismatched build
            return "cuda"
    except Exception as exc:  # no torch, no GPU, or a broken CUDA build -> CPU
        logger.info("GPU probe failed (%s); using CPU", type(exc).__name__)
    return "cpu"


def populate(entity_type: str | None, batch_size: int, dry_run: bool, force: bool,
             ontology_names: list[str] | None = None) -> int:
    """Returns number of embeddings written (or that would be written in dry-run)."""
    from flask import Flask
    import importlib.util
    config_spec = importlib.util.spec_from_file_location(
        "web_config", str(web_dir / "app_config.py")
    )
    web_config_module = importlib.util.module_from_spec(config_spec)
    config_spec.loader.exec_module(web_config_module)
    config = web_config_module.config

    from models import db, OntologyEntity
    from sentence_transformers import SentenceTransformer

    app = Flask(__name__)
    config_name = os.environ.get("FLASK_CONFIG", "development")
    app.config.from_object(config[config_name])
    db.init_app(app)

    written = 0
    with app.app_context():
        query = OntologyEntity.query
        if entity_type:
            query = query.filter(OntologyEntity.entity_type == entity_type)
        if ontology_names:
            from sqlalchemy import text as _text
            rows = db.session.execute(
                _text("SELECT name, id FROM ontologies WHERE name = ANY(:names)"),
                {"names": ontology_names},
            ).fetchall()
            found = {r[0]: r[1] for r in rows}
            missing = [n for n in ontology_names if n not in found]
            if missing:
                raise SystemExit(f"Unknown ontology name(s): {', '.join(missing)}")
            query = query.filter(OntologyEntity.ontology_id.in_(list(found.values())))
            logger.info("Restricting to ontologies: %s", ", ".join(ontology_names))
        if not force:
            query = query.filter(OntologyEntity.embedding.is_(None))

        total = query.count()
        if total == 0:
            logger.info("No rows to process (entity_type=%s, force=%s).", entity_type, force)
            return 0

        logger.info(
            "Processing %d rows (entity_type=%s, batch=%d, dry_run=%s, force=%s).",
            total, entity_type or "<all>", batch_size, dry_run, force,
        )

        if dry_run:
            sample = query.limit(5).all()
            for entity in sample:
                preview = build_text(entity)
                logger.info("  [dry-run sample] %s -> %s", entity.uri, preview[:120])
            return total

        # Pick the device (GPU when its kernels actually run, else CPU; see _resolve_device).
        # Computed on a capable local box and shipped to production via the DB dump; prod never computes.
        device = _resolve_device()
        logger.info("Loading sentence-transformer model all-MiniLM-L6-v2 on %s ...", device)
        model = SentenceTransformer("all-MiniLM-L6-v2", device=device)
        logger.info("Model loaded.")

        # Stream in batches by primary key to keep memory bounded.
        last_id = 0
        while True:
            batch_query = query.filter(OntologyEntity.id > last_id).order_by(
                OntologyEntity.id.asc()
            ).limit(batch_size)
            batch = batch_query.all()
            if not batch:
                break

            texts = [build_text(e) for e in batch]
            embeddings = model.encode(texts, show_progress_bar=False)

            for entity, vec in zip(batch, embeddings):
                entity.embedding = vec.tolist()

            db.session.commit()
            written += len(batch)
            last_id = batch[-1].id
            logger.info("  wrote %d / %d (last id=%d)", written, total, last_id)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--type",
        dest="entity_type",
        choices=["class", "individual", "property"],
        default="class",
        help="Restrict to one entity_type (default: class). Use --type='' to disable filter.",
    )
    parser.add_argument("--batch", type=int, default=128, help="Batch size (default: 128).")
    parser.add_argument("--dry-run", action="store_true", help="Report counts and a few samples; do not write.")
    parser.add_argument("--force", action="store_true", help="Re-embed rows that already have an embedding.")
    parser.add_argument(
        "--ontology", dest="ontology_names", action="append", default=None, metavar="NAME",
        help="Restrict to one or more ontologies by name (repeatable). Default: all ontologies.",
    )
    args = parser.parse_args()

    entity_type = args.entity_type or None
    written = populate(
        entity_type=entity_type,
        batch_size=args.batch,
        dry_run=args.dry_run,
        force=args.force,
        ontology_names=args.ontology_names,
    )
    if args.dry_run:
        logger.info("Dry-run complete. Would process %d rows.", written)
    else:
        logger.info("Done. Wrote embeddings for %d rows.", written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
