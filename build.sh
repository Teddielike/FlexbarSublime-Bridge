#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

command -v zip >/dev/null 2>&1 || { echo "Missing: zip" >&2; exit 1; }
rm -f "$ROOT/FlexbarBridge.sublime-package"
(
  cd "$ROOT/FlexbarBridge"
  zip -qr "$ROOT/FlexbarBridge.sublime-package" . -x './__pycache__/*' './FlexbarBridge.sublime-commands'
)
python3 -m unittest discover -s tests -p 'test_bridge.py'
echo "Created: $ROOT/FlexbarBridge.sublime-package"
