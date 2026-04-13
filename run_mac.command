#!/bin/bash
# Double-click in Finder to open Quartet Payment Calculator (no .app / Gatekeeper issues).
cd "$(dirname "$0")" || exit 1
if [[ ! -f "app/quartet_payment_calculator.py" ]]; then
  echo "Missing app/quartet_payment_calculator.py — run this from the project folder." >&2
  read -r -p "Press Enter to close..."
  exit 1
fi
python3 app/quartet_payment_calculator.py
status=$?
if [[ $status -ne 0 ]]; then
  read -r -p "Press Enter to close..."
fi
exit "$status"
