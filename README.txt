Quartet Payment Calculator

OPEN THE APP

Windows:
- Double-click QuartetPaymentCalculator.exe (in this folder or in QuartetPaymentCalculator-Release)

macOS:
- Double-click QuartetPaymentCalculator.app in QuartetPaymentCalculator-Release
- If macOS says the app cannot be opened: right-click the app, choose Open, then Open again (Gatekeeper)
- Data folder sits next to the .app in the release folder

REBUILD (developers)

Windows: in this folder, with Python 3:
  python -m venv build_env
  build_env\Scripts\activate
  pip install -r requirements-build.txt
  python build.py

macOS: double-click build_mac.command in this folder, or the same steps as above using build_env/bin/activate.
If double-click does nothing, run once in Terminal: chmod +x build_mac.command
(PyInstaller must run on each platform; you cannot build the Mac .app from Windows.)

HOW TO USE

1. Open the app (double-click)
2. Enter gig details
3. Click "Save & Log Payment" to record the gig in your ledger
4. Totals update as you type; calendar data saves automatically

CALENDAR:
- Track bookings
- Add/edit appointments

EXPORT / IMPORT:
- Click "Export Spreadsheet" to save your records
- Click "Import Spreadsheet" to load an exported file into your ledger (replaces data/payments_log.csv)

NOTES:
- All data is stored in the "data" folder
- Do not delete files inside that folder

That's it.
