import sys
sys.path.insert(0, '/root/ai-factory')

from ai_factory.db.schema import ensure_entries_table, upgrade_entries_schema_to_latest

print("Ensuring entries table...")
ensure_entries_table()

print("Upgrading entries schema...")
upgrade_entries_schema_to_latest()

print("Done!")
