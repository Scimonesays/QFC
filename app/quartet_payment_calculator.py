#!/usr/bin/env python3
"""
Quartet Payment Calculator — cross-platform Tkinter tool for Windows and macOS.
Standard library only: tkinter, datetime, calendar, json, os, shutil, decimal, subprocess, csv, io.
"""

from __future__ import annotations

import calendar
import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from tkinter import filedialog, messagebox, ttk

def _is_frozen() -> bool:
    """True when running inside a PyInstaller bundle (.exe / .app)."""
    return bool(getattr(sys, "frozen", False))


def get_bundle_dir() -> str:
    """
    Portable app root: project folder next to app/ (dev) or the folder containing
    the .exe (Windows) / the .app bundle (macOS). All data lives under this folder.
    """
    if _is_frozen():
        exe = os.path.normpath(sys.executable)
        if sys.platform == "darwin":
            cur = exe
            for _ in range(16):
                if cur.lower().endswith(".app"):
                    return os.path.dirname(cur)
                nxt = os.path.dirname(cur)
                if nxt == cur:
                    break
                cur = nxt
        return os.path.dirname(exe)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


BASE_DIR = get_bundle_dir()
DATA_DIR = os.path.join(BASE_DIR, "data")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")

APPOINTMENTS_FILE = os.path.join(DATA_DIR, "appointments.json")
APPOINTMENTS_BACKUP_FILE = os.path.join(DATA_DIR, "appointments_backup.json")
PAYMENTS_LOG_FILE = os.path.join(DATA_DIR, "payments_log.csv")

_README_TEXT = """Quartet Payment Calculator

HOW TO USE:

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
"""


def ensure_portable_layout() -> None:
    """Create data/ and exports/, seed README.txt, migrate legacy root-level files."""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    ensure_payments_log_template()

    readme_path = os.path.join(BASE_DIR, "README.txt")
    if not os.path.isfile(readme_path):
        try:
            with open(readme_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(_README_TEXT)
        except OSError:
            pass

    # Legacy: JSON/CSV next to the app (pre–data/ folder layout).
    for name in (
        "appointments.json",
        "appointments_backup.json",
        "payments_log.csv",
    ):
        legacy = os.path.join(BASE_DIR, name)
        dest = os.path.join(DATA_DIR, name)
        if os.path.isfile(legacy) and not os.path.isfile(dest):
            try:
                shutil.move(legacy, dest)
            except OSError:
                pass

PAYMENT_LOG_HEADER = [
    "Date",
    "Gig Name",
    "Total Paid",
    "Gas",
    "Sheet Music",
    "Strings",
    "Misc",
    "Total Expenses",
    "Net Profit",
    "Each Person",
]


def ensure_payments_log_template() -> None:
    """Create payments_log.csv with a header row if the file does not exist yet."""
    if os.path.isfile(PAYMENTS_LOG_FILE):
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PAYMENTS_LOG_FILE, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerow(PAYMENT_LOG_HEADER)


# ---------------------------------------------------------------------------
# Parsing & math
# ---------------------------------------------------------------------------


def parse_money(value: str) -> float:
    """
    Parse a dollar amount from the user.
    Empty -> 0.0. Allows $ and comma separators.
    Raises ValueError if not a valid number.
    """
    s = (value or "").strip()
    if not s:
        return 0.0
    s = s.replace("$", "").replace(",", "").strip()
    return float(s)


def appointment_sheet_music_cost_numeric(appointment: dict) -> float:
    """
    Sheet music cost from a stored appointment dict: numeric, safe parse, blank/invalid -> 0.
    Prefers total_cost (payment-synced shape), then legacy cost.
    """
    if "total_cost" in appointment:
        raw = appointment.get("total_cost")
    else:
        raw = appointment.get("cost", 0)
    if raw is None:
        return 0.0
    if isinstance(raw, bool):
        return 0.0
    if isinstance(raw, (int, float)):
        try:
            f = float(raw)
        except (TypeError, ValueError):
            return 0.0
        if f != f:  # NaN
            return 0.0
        return f
    s = str(raw).strip()
    if not s:
        return 0.0
    try:
        return parse_money(s)
    except ValueError:
        return 0.0


def appointment_music_display(appointment: dict) -> str:
    """Human-readable sheet-music line: music_list (new shape) or legacy music string."""
    ml = appointment.get("music_list")
    if isinstance(ml, list) and ml:
        parts = [str(x) for x in ml if x is not None and str(x).strip()]
        if parts:
            return ", ".join(parts)
    return str(appointment.get("music", ""))


def format_usd_display(amount: float) -> str:
    """
    Numeric dollars only, 2 fraction digits (half-up), e.g. 175.125 -> 175.13.
    Internal math stays float; this is for display and saved files.
    """
    q = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:.2f}"


def format_currency(amount: float) -> str:
    """
    All user-visible and saved dollar amounts must go through this (never raw float formatting).
    Produces strings like $123.45 or $-50.00 (always two decimal places, half-up).
    """
    return f"${format_usd_display(amount)}"


def calculate_values(
    total_paid: str,
    gas: str,
    sheet_music: str,
    strings: str,
    misc: str,
) -> tuple[float, float, float, float, float, float, float, float]:
    """
    Compute totals from raw field strings.

    Returns:
        total_paid, gas, sheet_music, strings, misc,
        total_expenses, net_profit, individual_pay
    """
    tp = parse_money(total_paid)
    g = parse_money(gas)
    sm = parse_money(sheet_music)
    st = parse_money(strings)
    m = parse_money(misc)

    total_expenses = g + sm + st + m
    net_profit = tp - total_expenses
    # Option A: allow negative net; equal split shares the loss (net / 4).
    individual_pay = net_profit / 4.0
    return tp, g, sm, st, m, total_expenses, net_profit, individual_pay


def warn_if_operating_at_loss(parent: tk.Misc | None, net_profit: float) -> None:
    """Notify when expenses exceeded pay; split still reflects equal share of the loss."""
    if net_profit < 0:
        messagebox.showwarning(
            "Operating at a loss",
            "This gig operated at a loss.\n\n"
            "Net profit and the per-person split are negative: everyone shares the shortfall equally (÷4).",
            parent=parent,
        )


def open_saved_file(path: str) -> None:
    """
    Open the saved report in the default app (Windows: os.startfile; macOS: open;
    Linux: xdg-open). Fails silently if the OS cannot launch the file.
    """
    path = os.path.normpath(path)
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except OSError:
        pass


def open_folder(path: str) -> None:
    """
    Open a folder in Explorer / Finder (or xdg-open on Linux). Fails silently on error.
    """
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        return
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except OSError:
        pass


def has_data_changed(
    current: tuple[str, str, str, str, str, str, str],
    previous: tuple[str, str, str, str, str, str, str] | None,
) -> bool:
    """
    True when gig, date, or any money field differs from the last successful
    calculation that was written to the payment log.
    """
    if previous is None:
        return True
    return current != previous


def log_payment(
    gig_name: str,
    date_str: str,
    total_paid: float,
    gas: float,
    sheet_music: float,
    strings: float,
    misc: float,
    total_expenses: float,
    net_profit: float,
    individual_pay: float,
) -> None:
    """Append one CSV row to payments_log.csv (header written once if file is new/empty)."""
    os.makedirs(os.path.dirname(PAYMENTS_LOG_FILE), exist_ok=True)
    ds = date_str.strip() if date_str.strip() else date.today().isoformat()
    gig_line = gig_name.strip() if gig_name.strip() else "(no name)"
    new_file = (not os.path.isfile(PAYMENTS_LOG_FILE)) or os.path.getsize(
        PAYMENTS_LOG_FILE
    ) == 0
    row = [
        ds,
        gig_line,
        format_currency(total_paid),
        format_currency(gas),
        format_currency(sheet_music),
        format_currency(strings),
        format_currency(misc),
        format_currency(total_expenses),
        format_currency(net_profit),
        format_currency(individual_pay),
    ]
    with open(PAYMENTS_LOG_FILE, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(PAYMENT_LOG_HEADER)
        w.writerow(row)


def load_payment_log() -> str:
    """Full text of payments_log.csv for export; if missing, header-only placeholder."""
    if not os.path.isfile(PAYMENTS_LOG_FILE):
        buf = io.StringIO()
        csv.writer(buf).writerow(PAYMENT_LOG_HEADER)
        return buf.getvalue()
    with open(PAYMENTS_LOG_FILE, encoding="utf-8", newline="") as f:
        return f.read()


def export_payment_log(parent: tk.Misc, default_dir: str) -> bool:
    """
    Save dialog: copy payments_log.csv to a user-chosen path (default name includes date).
    Opens the exported file in the default app. Returns True if a file was written.
    """
    content = load_payment_log()
    default_name = f"QuartetPayment_Export_{date.today().isoformat()}.csv"
    path = filedialog.asksaveasfilename(
        parent=parent,
        title="Export spreadsheet",
        initialdir=default_dir,
        initialfile=default_name,
        defaultextension=".csv",
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )
    if not path:
        return False
    if os.path.exists(path):
        if not messagebox.askyesno(
            "Overwrite?",
            f"This file already exists:\n{path}\n\nOverwrite it?",
            parent=parent,
        ):
            return False
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    open_saved_file(path)
    messagebox.showinfo("Exported", f"Spreadsheet saved to:\n{path}", parent=parent)
    return True


def import_payment_log(parent: tk.Misc, default_dir: str) -> bool:
    """
    Open dialog: read a Quartet export CSV and replace data/payments_log.csv with it.
    Does not copy into exports/; updates the single live log file (after confirmation).
    """
    path = filedialog.askopenfilename(
        parent=parent,
        title="Import spreadsheet",
        initialdir=default_dir,
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )
    if not path:
        return False
    path = os.path.normpath(path)
    if os.path.isfile(PAYMENTS_LOG_FILE):
        try:
            if os.path.samefile(path, PAYMENTS_LOG_FILE):
                messagebox.showinfo(
                    "Import",
                    "That file is already your payment log.",
                    parent=parent,
                )
                return False
        except OSError:
            pass
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            content = f.read()
    except OSError as e:
        messagebox.showerror(
            "Import failed", f"Could not read file:\n{e}", parent=parent
        )
        return False
    reader = csv.reader(io.StringIO(content))
    try:
        first = next(reader)
    except StopIteration:
        messagebox.showerror("Import failed", "File is empty.", parent=parent)
        return False
    if [c.strip() for c in first] != PAYMENT_LOG_HEADER:
        messagebox.showerror(
            "Import failed",
            "This file does not look like a Quartet export (wrong header row).",
            parent=parent,
        )
        return False
    if not messagebox.askyesno(
        "Import spreadsheet",
        "This replaces your current payment log in the data folder.\n\nContinue?",
        parent=parent,
    ):
        return False
    if not content.endswith("\n"):
        content = content + "\n"
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = os.path.join(DATA_DIR, ".payments_log_import.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        os.replace(tmp, PAYMENTS_LOG_FILE)
    except OSError as e:
        try:
            if os.path.isfile(tmp):
                os.remove(tmp)
        except OSError:
            pass
        messagebox.showerror(
            "Import failed", f"Could not write payment log:\n{e}", parent=parent
        )
        return False
    messagebox.showinfo("Imported", "Payment log updated.", parent=parent)
    return True


def _approx_equal(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol


def run_tests() -> bool:
    """Validate calculate_values() and currency rounding before the GUI runs (dev only)."""
    all_ok = True

    def case(
        total_paid: str,
        gas: str,
        sheet_music: str,
        strings: str,
        misc: str,
        exp_total_expenses: float,
        exp_net_profit: float,
        exp_individual_pay: float,
        *,
        exp_display_each: str | None = None,
    ) -> None:
        nonlocal all_ok
        try:
            *_, total_exp, net, each = calculate_values(
                total_paid, gas, sheet_music, strings, misc
            )
        except Exception:
            all_ok = False
            return

        ok = (
            _approx_equal(total_exp, exp_total_expenses)
            and _approx_equal(net, exp_net_profit)
            and _approx_equal(each, exp_individual_pay)
        )
        if exp_display_each is not None and format_currency(each) != exp_display_each:
            ok = False
        if not ok:
            all_ok = False

    case("1000", "100", "50", "50", "", 200.0, 800.0, 200.0)
    case("400", "", "", "", "", 0.0, 400.0, 100.0)
    case(
        "750.50",
        "25.25",
        "24.75",
        "",
        "",
        50.0,
        700.5,
        175.125,
        exp_display_each="$175.13",
    )
    case(
        "100",
        "500",
        "",
        "",
        "",
        500.0,
        -400.0,
        -100.0,
        exp_display_each="$-100.00",
    )
    return all_ok


# ---------------------------------------------------------------------------
# UI updates & persistence
# ---------------------------------------------------------------------------


def update_results_display(
    parent: tk.Misc | None,
    lbl_total_expenses: ttk.Label,
    lbl_net_profit: ttk.Label,
    lbl_equal_split: ttk.Label,
    total_paid: str,
    gas: str,
    sheet_music: str,
    strings: str,
    misc: str,
    *,
    show_errors: bool = True,
) -> float | None:
    """
    Run calculate_values() and refresh the three result labels.
    Returns net_profit on success, or None if input is invalid.
    If show_errors, invalid input shows a messagebox; otherwise labels show placeholders (live typing).
    All dollar amounts in labels use format_currency() only.
    """
    try:
        *_, total_exp, net, each = calculate_values(
            total_paid, gas, sheet_music, strings, misc
        )
    except ValueError:
        if show_errors:
            messagebox.showerror(
                "Invalid input",
                "Enter numeric dollar amounts only.\n"
                "Leave a field blank to count it as 0.\n"
                "You may include $ and commas.",
                parent=parent,
            )
        else:
            lbl_total_expenses.config(text="Total Expenses: —")
            lbl_net_profit.config(text="Net Profit: —")
            lbl_equal_split.config(text="Each Gets: —")
        return None

    lbl_total_expenses.config(text=f"Total Expenses: {format_currency(total_exp)}")
    lbl_net_profit.config(text=f"Net Profit: {format_currency(net)}")
    lbl_equal_split.config(text=f"Each Gets: {format_currency(each)}")
    return net


def reset_fields(
    var_gig: tk.StringVar,
    var_date: tk.StringVar,
    money_vars: tuple[tk.StringVar, tk.StringVar, tk.StringVar, tk.StringVar, tk.StringVar],
    lbl_total_expenses: ttk.Label,
    lbl_net_profit: ttk.Label,
    lbl_equal_split: ttk.Label,
) -> None:
    """Clear inputs, reset date to today, and clear result labels."""
    var_gig.set("")
    var_date.set(date.today().isoformat())
    for v in money_vars:
        v.set("")
    lbl_total_expenses.config(text="Total Expenses: —")
    lbl_net_profit.config(text="Net Profit: —")
    lbl_equal_split.config(text="Each Gets: —")


# ---------------------------------------------------------------------------
# Booking calendar (appointments.json)
# ---------------------------------------------------------------------------


def load_appointments() -> dict[str, list[dict]]:
    """
    Load appointments keyed by ISO date (YYYY-MM-DD). Missing or bad file -> {}.
    One JSON load per app start; fine for typical quartet use (50+ bookings).
    """
    data, _reason = load_appointments_with_reason()
    return data


def load_appointments_with_reason() -> tuple[dict[str, list[dict]], str | None]:
    """
    Same as load_appointments(), but returns a reason when the file exists but
    cannot be used: 'corrupt_json', 'unreadable', or 'wrong_shape' (valid JSON, not an object).
    """
    if not os.path.isfile(APPOINTMENTS_FILE):
        return {}, None
    try:
        with open(APPOINTMENTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {}, "corrupt_json"
    except OSError:
        return {}, "unreadable"
    if not isinstance(data, dict):
        return {}, "wrong_shape"
    out: dict[str, list[dict]] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not isinstance(v, list):
            continue
        out[k] = [x for x in v if isinstance(x, dict)]
    return out, None


def save_appointments(
    data: dict[str, list[dict]], *, allow_empty: bool = False
) -> bool:
    """
    Write appointments JSON (UTF-8, readable).
    Backs up the current file, writes to a temp file, then replaces atomically.
    Refuses to persist an empty dict unless allow_empty=True (first-run seed or UI clear).
    Returns True if the file on disk now reflects ``data`` (or empty seed); False on skip/error.
    """
    if not data:
        if not allow_empty:
            print(
                "WARNING: Attempted to save empty appointments. Skipping write.",
                file=sys.stderr,
            )
            return False

    os.makedirs(os.path.dirname(APPOINTMENTS_FILE), exist_ok=True)
    temp_file = APPOINTMENTS_FILE + ".tmp"

    if os.path.isfile(APPOINTMENTS_FILE):
        try:
            shutil.copy2(APPOINTMENTS_FILE, APPOINTMENTS_BACKUP_FILE)
        except OSError as e:
            print("Warning: could not backup appointments before save:", e, file=sys.stderr)

    try:
        with open(temp_file, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(temp_file, APPOINTMENTS_FILE)
    except Exception as e:
        print("Error saving appointments:", e, file=sys.stderr)
        try:
            if os.path.isfile(temp_file):
                os.remove(temp_file)
        except OSError:
            pass
        return False
    return True


_DEFAULT_SYNC_MUSIC_LIST = ["General Repertoire"]


def _parse_iso_date_safe(date_str: str) -> date | None:
    s = (date_str or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _payment_appointment_name_match(stored: str, gig_name: str) -> bool:
    return (stored or "").strip() == (gig_name or "").strip()


def create_or_update_appointment_from_payment(
    gig_name: str,
    date_str: str,
    sheet_music: float,
    appointments: dict[str, list[dict]],
) -> None:
    """
    Mirror a logged payment as a calendar appointment (silent, no UI).
    Skips when gig name is empty or date is not valid ISO YYYY-MM-DD.
    Updates total_cost only when name+date already match an entry; otherwise inserts
    a new row with music_list / location / time per payment-sync rules.
    """
    name = (gig_name or "").strip()
    if not name:
        return
    d = _parse_iso_date_safe(date_str)
    if d is None:
        return
    try:
        q = Decimal(str(sheet_music)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cost_val = float(q)
    except (ArithmeticError, TypeError, ValueError):
        cost_val = 0.0
    if cost_val != cost_val:  # NaN
        cost_val = 0.0

    iso = d.isoformat()
    try:
        day_list = appointments.setdefault(iso, [])
        found: dict | None = None
        for a in day_list:
            if isinstance(a, dict) and _payment_appointment_name_match(
                str(a.get("name", "")), name
            ):
                found = a
                break
        if found is not None:
            found["total_cost"] = cost_val
        else:
            day_list.append(
                {
                    "name": name,
                    "music_list": list(_DEFAULT_SYNC_MUSIC_LIST),
                    "total_cost": cost_val,
                    "location": "",
                    "time": "",
                }
            )
        save_appointments(appointments)
    except Exception:
        pass  # payment mirror stays silent; empty/wrong dict is guarded inside save


def ensure_appointments_file_exists() -> None:
    """Create an empty appointments.json on first run so the data location is real and obvious."""
    if not os.path.isfile(APPOINTMENTS_FILE):
        save_appointments({}, allow_empty=True)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class QuartetPaymentCalculatorApp(tk.Tk):
    """Main window: Payments tab plus Calendar booking log (one window, minimal UI)."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Quartet Payment Calculator")
        self.minsize(380, 460)
        self.geometry("480x600")

        self.var_gig = tk.StringVar()
        self.var_date = tk.StringVar(value=date.today().isoformat())
        self.var_total = tk.StringVar()
        self.var_gas = tk.StringVar()
        self.var_sheet = tk.StringVar()
        self.var_strings = tk.StringVar()
        self.var_misc = tk.StringVar()

        # Suppress duplicate "operating at a loss" dialogs for the same money inputs.
        self._loss_warn_fingerprint: str | None = None
        # Dedupe payment log rows: same form state as last successful save -> no new CSV row.
        self._last_calc_snapshot: tuple[str, str, str, str, str, str, str] | None = None
        self._lbl_save_feedback: tk.Label | None = None
        self._save_feedback_after_id: str | None = None

        self._appts, self._appt_load_issue = load_appointments_with_reason()
        self._cal_year = date.today().year
        self._cal_month = date.today().month
        self._booking_list_date: date | None = None
        self._booking_day_list_active = False
        self._notebook: ttk.Notebook | None = None
        self._payment_tab: ttk.Frame | None = None
        self._booking_inner: ttk.Frame | None = None
        self._cal_title: ttk.Label | None = None
        self._booking_form_date: date = date.today()
        self._booking_edit_index: int | None = None
        self.var_appt_name = tk.StringVar()
        self.var_appt_music = tk.StringVar()
        self.var_appt_cost = tk.StringVar()
        self.var_appt_location = tk.StringVar()
        self.var_appt_time = tk.StringVar()

        self._build_ui()
        if self._appt_load_issue in ("corrupt_json", "wrong_shape", "unreadable"):
            self.after(300, self._notify_appointments_load_issue)

    def _notify_appointments_load_issue(self) -> None:
        """One-time notice when appointments.json could not be loaded (no crash)."""
        issue = self._appt_load_issue
        if issue == "corrupt_json":
            msg = (
                "appointments.json is not valid JSON.\n\n"
                "The calendar will start empty. Your previous file was not modified.\n"
                "Check appointments_backup.json in the data folder if you need an older copy "
                '(Payments or Calendar: "Open App Folder").'
            )
        elif issue == "wrong_shape":
            msg = (
                "appointments.json must contain a JSON object (date keys → lists).\n\n"
                "The calendar will start empty until you add bookings again."
            )
        else:
            msg = (
                "Could not read appointments.json (file error).\n\n"
                "The calendar will start empty until the file can be read."
            )
        messagebox.showwarning("Calendar data", msg, parent=self)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        nb = ttk.Notebook(self)
        nb.grid(row=0, column=0, sticky=tk.NSEW, padx=0, pady=0)
        self._notebook = nb

        pay_tab = ttk.Frame(nb, padding=10)
        nb.add(pay_tab, text="Payments")
        self._payment_tab = pay_tab
        self._build_payments_tab(pay_tab)

        cal_tab = ttk.Frame(nb, padding=10)
        nb.add(cal_tab, text="Calendar")
        self._booking_inner = ttk.Frame(cal_tab)
        self._booking_inner.pack(fill=tk.BOTH, expand=True)
        self.render_calendar()

        cal_footer = ttk.Frame(cal_tab)
        cal_footer.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(
            cal_footer,
            text="Open App Folder",
            command=self._on_open_app_folder,
        ).pack(anchor=tk.W)

    def _build_payments_tab(self, main: ttk.Frame) -> None:
        pad = {"padx": 5, "pady": 5}
        main.columnconfigure(1, weight=1)

        r = 0
        ttk.Label(main, text="Gig Name:").grid(row=r, column=0, sticky=tk.W, **pad)
        ttk.Entry(main, textvariable=self.var_gig, width=28).grid(
            row=r, column=1, sticky=tk.EW, **pad
        )
        r += 1
        ttk.Label(main, text="Date:").grid(row=r, column=0, sticky=tk.W, **pad)
        ttk.Entry(main, textvariable=self.var_date, width=28).grid(
            row=r, column=1, sticky=tk.EW, **pad
        )
        r += 1

        ttk.Label(main, text="--- Show Income ---").grid(
            row=r, column=0, columnspan=2, sticky=tk.W, **pad
        )
        r += 1
        ttk.Label(main, text="Total Paid:").grid(row=r, column=0, sticky=tk.W, **pad)
        ttk.Entry(main, textvariable=self.var_total, width=28).grid(
            row=r, column=1, sticky=tk.EW, **pad
        )
        r += 1

        ttk.Label(main, text="--- Shared Expenses ---").grid(
            row=r, column=0, columnspan=2, sticky=tk.W, **pad
        )
        r += 1
        expense_rows = [
            ("Gas:", self.var_gas),
            ("Sheet Music:", self.var_sheet),
            ("Instrument Cost:", self.var_strings),
            ("Misc:", self.var_misc),
        ]
        for label, var in expense_rows:
            ttk.Label(main, text=label).grid(row=r, column=0, sticky=tk.W, **pad)
            ttk.Entry(main, textvariable=var, width=28).grid(
                row=r, column=1, sticky=tk.EW, **pad
            )
            r += 1

        ttk.Label(main, text="--- Results ---").grid(
            row=r, column=0, columnspan=2, sticky=tk.W, **pad
        )
        r += 1
        self.lbl_total_exp = ttk.Label(
            main, text="Total Expenses: —", name="y6q8zt_total"
        )
        self.lbl_total_exp.grid(row=r, column=0, columnspan=2, sticky=tk.W, **pad)
        r += 1
        self.lbl_net = ttk.Label(main, text="Net Profit: —", name="y6q8zt_net")
        self.lbl_net.grid(row=r, column=0, columnspan=2, sticky=tk.W, **pad)
        r += 1
        self.lbl_split = ttk.Label(main, text="Each Gets: —", name="y6q8zt_split")
        self.lbl_split.grid(row=r, column=0, columnspan=2, sticky=tk.W, **pad)
        r += 1

        btn_area = ttk.Frame(main)
        btn_area.grid(row=r, column=0, columnspan=2, sticky=tk.EW, **pad)
        btn_area.columnconfigure(0, weight=1)
        r += 1

        style = ttk.Style(self)
        style.configure(
            "BigSave.TButton",
            font=("TkDefaultFont", 12, "bold"),
            padding=(16, 12),
        )
        ttk.Button(
            btn_area,
            text="Save & Log Payment",
            command=self.on_save_and_log_payment,
            style="BigSave.TButton",
        ).grid(row=0, column=0, sticky=tk.EW, pady=(0, 8))

        row_actions = ttk.Frame(btn_area)
        row_actions.grid(row=1, column=0, sticky=tk.W)
        ttk.Button(
            row_actions, text="Export Spreadsheet", command=self.on_export_spreadsheet
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(
            row_actions, text="Import Spreadsheet", command=self.on_import_spreadsheet
        ).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row_actions, text="Reset", command=self.on_reset).pack(
            side=tk.LEFT, padx=(0, 0)
        )

        self._lbl_save_feedback = tk.Label(
            main,
            text="",
            font=("TkDefaultFont", 9),
            fg="#1b5e20",
        )
        self._lbl_save_feedback.grid(
            row=r, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(2, 0)
        )
        r += 1
        ttk.Button(main, text="Open App Folder", command=self._on_open_app_folder).grid(
            row=r, column=0, columnspan=2, sticky=tk.W, **pad
        )
        r += 1
        tk.Label(
            main,
            text="Simple. Reliable. Always saved.",
            font=("TkDefaultFont", 8),
            fg="#666666",
        ).grid(row=r, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(12, 0))

        for v in self._money_vars():
            v.trace_add("write", self._on_payment_field_trace)

        self._refresh_payment_results_live()

    def _on_payment_field_trace(self, *_args: object) -> None:
        """Recalculate totals as the user types (no error spam on partial input)."""
        self._refresh_payment_results_live()

    def _refresh_payment_results_live(self) -> None:
        vt, vg, vs, vst, vm = self._money_vars()
        update_results_display(
            self,
            self.lbl_total_exp,
            self.lbl_net,
            self.lbl_split,
            vt.get(),
            vg.get(),
            vs.get(),
            vst.get(),
            vm.get(),
            show_errors=False,
        )

    def _booking_clear(self) -> None:
        inner = self._booking_inner
        if inner is None:
            return
        for w in inner.winfo_children():
            w.destroy()

    def _refresh_cal_title(self) -> None:
        if self._cal_title is None:
            return
        d0 = date(self._cal_year, self._cal_month, 1)
        self._cal_title.config(text=d0.strftime("%B %Y"))

    def _cal_prev_month(self) -> None:
        y, m = self._cal_year, self._cal_month
        if m <= 1:
            self._cal_year, self._cal_month = y - 1, 12
        else:
            self._cal_month = m - 1
        self.render_calendar()

    def _cal_next_month(self) -> None:
        y, m = self._cal_year, self._cal_month
        if m >= 12:
            self._cal_year, self._cal_month = y + 1, 1
        else:
            self._cal_month = m + 1
        self.render_calendar()

    def render_calendar(self) -> None:
        """Month grid (Sun–Sat); replaces current booking view."""
        self._booking_list_date = None
        self._booking_day_list_active = False
        self._booking_clear()
        inner = self._booking_inner
        if inner is None:
            return
        pad = {"padx": 4, "pady": 4}

        top = ttk.Frame(inner)
        top.pack(fill=tk.X, **pad)
        ttk.Button(top, text="<", width=3, command=self._cal_prev_month).pack(
            side=tk.LEFT
        )
        self._cal_title = ttk.Label(top, text="", anchor=tk.CENTER)
        self._cal_title.pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(top, text=">", width=3, command=self._cal_next_month).pack(
            side=tk.LEFT
        )
        self._refresh_cal_title()

        hdr = ttk.Frame(inner)
        hdr.pack(fill=tk.X, **pad)
        for col, name in enumerate(
            ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        ):
            ttk.Label(hdr, text=name, width=5, anchor=tk.CENTER).grid(
                row=0, column=col, **pad
            )

        grid = ttk.Frame(inner)
        grid.pack(fill=tk.BOTH, expand=True, **pad)
        cal = calendar.Calendar(firstweekday=calendar.SUNDAY)
        weeks = cal.monthdatescalendar(self._cal_year, self._cal_month)
        for ri, week in enumerate(weeks):
            for ci, d in enumerate(week):
                ttk.Button(
                    grid,
                    text=str(d.day),
                    width=4,
                    command=lambda day=d: self.open_day_view(day),
                ).grid(row=ri, column=ci, **pad)

    def open_day_view(self, d: date) -> None:
        """List appointments for one day; back returns to month grid."""
        self._booking_list_date = d
        self._booking_clear()
        self._cal_year, self._cal_month = d.year, d.month
        iso = d.isoformat()
        inner = self._booking_inner
        if inner is None:
            return
        pad = {"padx": 5, "pady": 5}

        ttk.Button(inner, text="< Back to Calendar", command=self.render_calendar).pack(
            anchor=tk.W, **pad
        )
        ttk.Label(inner, text=f"Date: {iso}").pack(anchor=tk.W, **pad)
        ttk.Label(inner, text="Appointments:").pack(anchor=tk.W, **pad)
        ttk.Separator(inner, orient=tk.HORIZONTAL).pack(fill=tk.X, **pad)

        appts = self._appts.get(iso, [])
        for i, a in enumerate(appts):
            name = str(a.get("name", "")).strip() or "(no name)"
            tm = str(a.get("time", "")).strip()
            line = f"{name} - {tm}" if tm else name
            ttk.Button(
                inner,
                text=f"[ {line} ]",
                command=lambda idx=i: self.open_appointment_detail(iso, idx),
            ).pack(anchor=tk.W, **pad)

        ttk.Button(
            inner, text="+ Add Appointment", command=lambda: self.open_add_form(d)
        ).pack(anchor=tk.W, **pad)
        self._booking_day_list_active = True

    def _try_save_appointments(self) -> bool:
        """Write JSON; on failure show error and return False (no crash)."""
        if not save_appointments(self._appts, allow_empty=True):
            messagebox.showerror(
                "Could not save",
                "Could not write appointments.json.",
                parent=self,
            )
            return False
        return True

    def _build_appt_form_ui(self, d: date) -> None:
        """Shared fields + Cancel; primary action is Save or Save Changes."""
        inner = self._booking_inner
        if inner is None:
            return
        pad = {"padx": 5, "pady": 5}
        rows = [
            ("Name:", self.var_appt_name),
            ("Sheet Music:", self.var_appt_music),
            ("Sheet Music Cost:", self.var_appt_cost),
            ("Location:", self.var_appt_location),
            ("Time:", self.var_appt_time),
        ]
        for label, var in rows:
            row = ttk.Frame(inner)
            row.pack(fill=tk.X, **pad)
            ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
            ttk.Entry(row, textvariable=var).pack(
                side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0)
            )

        btns = ttk.Frame(inner)
        btns.pack(**pad)
        is_edit = self._booking_edit_index is not None
        if is_edit:
            idx = self._booking_edit_index
            assert idx is not None
            ttk.Button(
                btns,
                text="Save Changes",
                command=lambda i=idx: self.save_edited_appointment(d, i),
            ).pack(side=tk.LEFT, padx=5)
        else:
            ttk.Button(btns, text="Save", command=self.save_appointment).pack(
                side=tk.LEFT, padx=5
            )
        ttk.Button(btns, text="Cancel", command=lambda: self.open_day_view(d)).pack(
            side=tk.LEFT, padx=5
        )

    def open_add_form(self, d: date) -> None:
        """Inline form to add an appointment for the given day."""
        self._booking_day_list_active = False
        self._booking_clear()
        self._booking_form_date = d
        self._booking_edit_index = None
        self.var_appt_name.set("")
        self.var_appt_music.set("")
        self.var_appt_cost.set("")
        self.var_appt_location.set("")
        self.var_appt_time.set("")
        self._build_appt_form_ui(d)

    def open_edit_form(self, d: date, index: int) -> None:
        """Same form as add, pre-filled; Save Changes updates list slot."""
        iso = d.isoformat()
        appts = self._appts.get(iso, [])
        if index < 0 or index >= len(appts):
            self.open_day_view(d)
            return
        self._booking_day_list_active = False
        self._booking_clear()
        self._booking_form_date = d
        self._booking_edit_index = index
        a = appts[index]
        self.var_appt_name.set(str(a.get("name", "")))
        self.var_appt_music.set(appointment_music_display(a))
        cost_f = appointment_sheet_music_cost_numeric(a)
        self.var_appt_cost.set(format_usd_display(cost_f))
        self.var_appt_location.set(str(a.get("location", "")))
        self.var_appt_time.set(str(a.get("time", "")))
        self._build_appt_form_ui(d)

    def save_appointment(self) -> None:
        """Validate add form, append appointment, persist JSON, return to day view."""
        if self._booking_edit_index is not None:
            return
        d = self._booking_form_date
        iso = d.isoformat()
        try:
            cost_val = parse_money(self.var_appt_cost.get())
        except ValueError:
            messagebox.showerror(
                "Invalid input",
                "Sheet music cost must be a valid dollar amount.",
                parent=self,
            )
            return
        name = self.var_appt_name.get().strip()
        if not name:
            messagebox.showerror("Invalid input", "Name is required.", parent=self)
            return
        music_s = self.var_appt_music.get().strip()
        entry = {
            "name": name,
            "music": music_s,
            "music_list": [music_s] if music_s else list(_DEFAULT_SYNC_MUSIC_LIST),
            "cost": cost_val,
            "total_cost": cost_val,
            "location": self.var_appt_location.get().strip(),
            "time": self.var_appt_time.get().strip(),
        }
        self._appts.setdefault(iso, []).append(entry)
        if not self._try_save_appointments():
            self._appts[iso].pop()
            return
        self.open_day_view(d)

    def save_edited_appointment(self, d: date, index: int) -> None:
        """Replace appointment at index for that date; persist; day view."""
        iso = d.isoformat()
        appts = self._appts.get(iso, [])
        if index < 0 or index >= len(appts):
            self.open_day_view(d)
            return
        try:
            cost_val = parse_money(self.var_appt_cost.get())
        except ValueError:
            messagebox.showerror(
                "Invalid input",
                "Sheet music cost must be a valid dollar amount.",
                parent=self,
            )
            return
        name = self.var_appt_name.get().strip()
        if not name:
            messagebox.showerror("Invalid input", "Name is required.", parent=self)
            return
        music_s = self.var_appt_music.get().strip()
        previous = appts[index]
        entry = dict(previous) if isinstance(previous, dict) else {}
        entry["name"] = name
        entry["music"] = music_s
        entry["cost"] = cost_val
        entry["total_cost"] = cost_val
        entry["location"] = self.var_appt_location.get().strip()
        entry["time"] = self.var_appt_time.get().strip()
        if isinstance(previous, dict) and isinstance(previous.get("music_list"), list):
            entry["music_list"] = (
                [music_s] if music_s else list(_DEFAULT_SYNC_MUSIC_LIST)
            )
        appts[index] = entry
        if not self._try_save_appointments():
            appts[index] = previous
            return
        self._booking_edit_index = None
        self.open_day_view(d)

    def delete_appointment(self, d: date, index: int) -> None:
        """Remove appointment at index after confirmation handled by caller."""
        iso = d.isoformat()
        appts = self._appts.get(iso, [])
        if index < 0 or index >= len(appts):
            self.open_day_view(d)
            return
        del appts[index]
        if not appts:
            del self._appts[iso]
        if not self._try_save_appointments():
            # Reload from disk if write failed (best-effort restore)
            self._appts = load_appointments()
            self.open_day_view(d)
            return
        self.open_day_view(d)

    def _confirm_delete_appointment(self, d: date, index: int) -> None:
        if not messagebox.askyesno(
            "Delete this appointment?",
            "Delete this appointment?",
            parent=self,
        ):
            return
        self.delete_appointment(d, index)

    def open_appointment_detail(self, iso: str, index: int) -> None:
        """Detail for one appointment; Edit / Delete reuse inline views."""
        appts = self._appts.get(iso, [])
        if index < 0 or index >= len(appts):
            self.open_day_view(date.fromisoformat(iso))
            return
        self._booking_day_list_active = False
        a = appts[index]
        self._booking_clear()
        inner = self._booking_inner
        if inner is None:
            return
        pad = {"padx": 5, "pady": 5}
        d = date.fromisoformat(iso)

        ttk.Button(
            inner, text="< Back", command=lambda: self.open_day_view(d)
        ).pack(anchor=tk.W, **pad)

        cost_f = appointment_sheet_music_cost_numeric(a)

        ttk.Label(inner, text=f"Name: {a.get('name', '')}").pack(anchor=tk.W, **pad)
        ttk.Label(inner, text=f"Sheet Music: {appointment_music_display(a)}").pack(
            anchor=tk.W, **pad
        )
        ttk.Label(inner, text=f"Cost: {format_currency(cost_f)}").pack(
            anchor=tk.W, **pad
        )
        ttk.Label(inner, text=f"Location: {a.get('location', '')}").pack(
            anchor=tk.W, **pad
        )
        ttk.Label(inner, text=f"Time: {a.get('time', '')}").pack(anchor=tk.W, **pad)

        actions = ttk.Frame(inner)
        actions.pack(anchor=tk.W, **pad)
        ttk.Button(
            actions,
            text="Edit",
            command=lambda day=d, idx=index: self.open_edit_form(day, idx),
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            actions,
            text="Delete",
            command=lambda day=d, idx=index: self._confirm_delete_appointment(day, idx),
        ).pack(side=tk.LEFT)

        ttk.Button(
            inner,
            text="[ Use for Payment ]",
            name="p3r8kw",
            command=lambda: self.load_appointment_into_payment(iso, a),
        ).pack(anchor=tk.W, **pad)

    def load_appointment_into_payment(self, date_iso: str, appointment: dict) -> None:
        """Switch to Payments and fill gig, date, sheet music expense from booking (nothing else)."""
        nb = self._notebook
        pt = self._payment_tab
        if nb is not None and pt is not None:
            nb.select(pt)

        self.var_gig.set(str(appointment.get("name", "")).strip())
        self.var_date.set((date_iso or "").strip())

        sm_cost = appointment_sheet_music_cost_numeric(appointment)
        self.var_sheet.set("" if sm_cost == 0.0 else format_usd_display(sm_cost))

        vt, vg, vs, vst, vm = self._money_vars()
        net = update_results_display(
            self,
            self.lbl_total_exp,
            self.lbl_net,
            self.lbl_split,
            vt.get(),
            vg.get(),
            vs.get(),
            vst.get(),
            vm.get(),
        )
        if net is not None:
            self.maybe_warn_operating_at_loss(net)

    def _money_vars(self) -> tuple[tk.StringVar, tk.StringVar, tk.StringVar, tk.StringVar, tk.StringVar]:
        return (self.var_total, self.var_gas, self.var_sheet, self.var_strings, self.var_misc)

    def _money_input_fingerprint(self) -> str:
        return "|".join(v.get() for v in self._money_vars())

    def maybe_warn_operating_at_loss(self, net_profit: float) -> None:
        """One loss warning per distinct set of dollar inputs (no double-prompt on repeat click)."""
        if net_profit >= 0:
            self._loss_warn_fingerprint = None
            return
        fp = self._money_input_fingerprint()
        if self._loss_warn_fingerprint == fp:
            return
        warn_if_operating_at_loss(self, net_profit)
        self._loss_warn_fingerprint = fp

    def _flash_save_logged(self) -> None:
        """Brief confirmation after a new row is written to the payment log."""
        if self._save_feedback_after_id is not None:
            self.after_cancel(self._save_feedback_after_id)
            self._save_feedback_after_id = None
        lbl = self._lbl_save_feedback
        if lbl is not None:
            lbl.config(text="Saved ✓")

        def _clear() -> None:
            if self._lbl_save_feedback is not None:
                self._lbl_save_feedback.config(text="")
            self._save_feedback_after_id = None

        self._save_feedback_after_id = self.after(1800, _clear)

    def on_save_and_log_payment(self) -> None:
        vt, vg, vs, vst, vm = self._money_vars()
        snapshot = (
            self.var_gig.get(),
            self.var_date.get(),
            vt.get(),
            vg.get(),
            vs.get(),
            vst.get(),
            vm.get(),
        )
        net = update_results_display(
            self,
            self.lbl_total_exp,
            self.lbl_net,
            self.lbl_split,
            vt.get(),
            vg.get(),
            vs.get(),
            vst.get(),
            vm.get(),
        )
        if net is None:
            return
        self.maybe_warn_operating_at_loss(net)
        if not has_data_changed(snapshot, self._last_calc_snapshot):
            return
        try:
            tp, g, sm, st, m, total_exp, net2, each = calculate_values(
                vt.get(), vg.get(), vs.get(), vst.get(), vm.get()
            )
        except ValueError:
            return
        log_payment(
            self.var_gig.get(),
            self.var_date.get(),
            tp,
            g,
            sm,
            st,
            m,
            total_exp,
            net2,
            each,
        )
        create_or_update_appointment_from_payment(
            self.var_gig.get(),
            self.var_date.get(),
            sm,
            self._appts,
        )
        pay_d = _parse_iso_date_safe(self.var_date.get())
        if (
            self._booking_day_list_active
            and pay_d is not None
            and self._booking_list_date == pay_d
        ):
            self.after_idle(lambda d=pay_d: self.open_day_view(d))
        self._last_calc_snapshot = snapshot
        self._flash_save_logged()

    def on_export_spreadsheet(self) -> None:
        export_payment_log(self, EXPORT_DIR)

    def on_import_spreadsheet(self) -> None:
        import_payment_log(self, EXPORT_DIR)

    def _on_open_app_folder(self) -> None:
        """Open the portable app root (contains data/ and exports/)."""
        open_folder(BASE_DIR)

    def on_reset(self) -> None:
        self._loss_warn_fingerprint = None
        self._last_calc_snapshot = None
        if self._save_feedback_after_id is not None:
            self.after_cancel(self._save_feedback_after_id)
            self._save_feedback_after_id = None
        if self._lbl_save_feedback is not None:
            self._lbl_save_feedback.config(text="")
        reset_fields(
            self.var_gig,
            self.var_date,
            self._money_vars(),
            self.lbl_total_exp,
            self.lbl_net,
            self.lbl_split,
        )


def main() -> None:
    if not _is_frozen():
        if not run_tests():
            print(
                "Quartet Payment Calculator: internal self-check failed.",
                file=sys.stderr,
            )
            sys.exit(1)
    ensure_portable_layout()
    ensure_appointments_file_exists()
    app = QuartetPaymentCalculatorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
