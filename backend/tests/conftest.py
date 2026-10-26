import os
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

_archivo = Path(tempfile.gettempdir()) / "parqueadero_test.db"
os.environ["PARQUEADERO_DB"] = str(_archivo)
if _archivo.exists():
    _archivo.unlink()

from app.database import inicializar  # noqa: E402

inicializar()
