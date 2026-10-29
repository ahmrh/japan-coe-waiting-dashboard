from __future__ import annotations

import json
import logging

from .database import initialize_database
from .refresh import refresh_estat

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    initialize_database()
    print(json.dumps(refresh_estat(), ensure_ascii=False, indent=2))
