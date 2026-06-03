"""
Shared pytest fixtures.
We add the router/ dir to sys.path so tests can `import classifier`, etc.
without needing the package installed.
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
ROUTER = HERE.parent / "router"
sys.path.insert(0, str(ROUTER))

# Force SQLite paths into a temp dir so tests don't touch real /app/data
_TMP = Path(tempfile.mkdtemp(prefix="viren-test-"))
os.environ.setdefault("TENANT_DB", str(_TMP / "tenants.db"))
os.environ.setdefault("EVENTS_DB", str(_TMP / "events.db"))
os.environ.setdefault("GATEWAY_MASTER_KEY", "test-master-key-do-not-use")
os.environ.setdefault("ENABLE_SEMANTIC_CACHE", "false")
os.environ.setdefault("ENABLE_PII_REDACTION", "true")
