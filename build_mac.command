#!/bin/bash
# Double-click in Finder (or run in Terminal) to rebuild QuartetPaymentCalculator.app
set -e
cd "$(dirname "$0")"
if [[ ! -f "build.py" || ! -f "app/quartet_payment_calculator.py" ]]; then
  echo "Run this from the QFT project folder (build.py missing)." >&2
  exit 1
fi
if [[ ! -d "build_env" ]]; then
  python3 -m venv build_env
fi
# shellcheck source=/dev/null
source build_env/bin/activate
python -m pip install -q -r requirements-build.txt
python build.py
deactivate
echo
echo "Done. Open QuartetPaymentCalculator-Release/QuartetPaymentCalculator.app"
