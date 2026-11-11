#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

command -v zip >/dev/null 2>&1 || { echo "Missing: zip" >&2; exit 1; }
rm -f "$ROOT/FlexbarBridge.sublime-package"
(
  cd "$ROOT"
  zip -qr "$ROOT/FlexbarBridge.sublime-package" . \
    -x './.git/*' './tests/*' './README.md' './LIESMICH.md' './LICENSE' './build.sh' \
       './.gitignore' './FlexbarBridge.sublime-package' './__pycache__/*' \
       './FlexbarBridge.sublime-commands' './*.webp' './*.png'
)
python3 -m unittest discover -s tests -p 'test_bridge.py'
echo "Created: $ROOT/FlexbarBridge.sublime-package"
