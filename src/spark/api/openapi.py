"""Write the API's OpenAPI document: `python -m spark.api.openapi frontend/src/api/openapi.json`.
CI regenerates it and fails when the committed copy is stale, so the TypeScript types
in the frontend always match the Python routes."""

import json
import sys

from spark.api.app import api

out = sys.argv[1] if len(sys.argv) > 1 else "-"
doc = json.dumps(api.openapi(), indent=2, sort_keys=True) + "\n"
if out == "-":
    sys.stdout.write(doc)
else:
    with open(out, "w") as f:
        f.write(doc)
