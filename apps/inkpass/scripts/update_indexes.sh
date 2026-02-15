#!/bin/bash
# Quick index update runner for inkPass documentation
echo "📚 Updating inkPass documentation indexes..."
python /app/scripts/generators/generate_manifests.py
python /app/scripts/generators/generate_index.py
python /app/scripts/generators/generate_task_map.py
python /app/scripts/generators/generate_ontology.py
python /app/scripts/validation/validate_structure.py
echo "✅ Indexes updated"
