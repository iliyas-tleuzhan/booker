from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from tkinter import END, BOTH, DISABLED, LEFT, NORMAL, RIGHT, X, Y, StringVar, Tk, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from app import db
from app.config import settings


ROOT = Path(__file__).resolve().parents[1]
TARGET_CHOICES = {
    "Default from .env": None,
    "Today": "today",
    "Tomorrow": "tomorrow",
    "2 days after": "2-days-after",
}


@dataclass(frozen=True)
class Check:
    label: str
    ok: bool
    detail: str


class BookerApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Booker")
        self.root.geometry("1120x720")
        self.root.minsize(960, 620)

        self.output_queue: queue.Queue[str] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.process_name = ""
        self.target_choice = StringVar(value="Default from .env")
        self.status_var = StringVar(value="Ready")

        self._build_ui()
        self.refresh_status()
        self.refresh_requests()
        self.root.after(100, self._drain_output)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(self.root, padding=16)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.columnconfigure(0, weight=1)

        title = ttk.Label(sidebar, text="Booker", font=("Segoe UI", 20, "bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 4))
        subtitle = ttk.Label(sidebar, text="HKU study room booking assistant")
        subtitle.grid(row=1, column=0, sticky="w", pady=(0, 18))

        self.start_button = ttk.Button(sidebar, text="Start Booker", command=self.start_scheduler)
        self.start_button.grid(row=2, column=0, sticky="ew", pady=3)
        self.stop_button = ttk.Button(sidebar, text="Stop Booker", command=self.stop_process, state=DISABLED)
        self.stop_button.grid(row=3, column=0, sticky="ew", pady=3)

        ttk.Separator(sidebar).grid(row=4, column=0, sticky="ew", pady=14)

        ttk.Label(sidebar, text="One-time actions", font=("Segoe UI", 10, "bold")).grid(row=5, column=0, sticky="w")
        ttk.Button(sidebar, text="Initialize database", command=lambda: self.run_command("Initialize database", ["init-db"])).grid(
            row=6, column=0, sticky="ew", pady=(8, 3)
        )
        ttk.Button(sidebar, text="Login to HKUL", command=self.login_hkul).grid(row=7, column=0, sticky="ew", pady=3)
        self.finish_login_button = ttk.Button(sidebar, text="Finish login", command=self.finish_login, state=DISABLED)
        self.finish_login_button.grid(row=8, column=0, sticky="ew", pady=3)

        ttk.Separator(sidebar).grid(row=9, column=0, sticky="ew", pady=14)

        ttk.Label(sidebar, text="Manual run", font=("Segoe UI", 10, "bold")).grid(row=10, column=0, sticky="w")
        target = ttk.Combobox(sidebar, textvariable=self.target_choice, values=list(TARGET_CHOICES), state="readonly")
        target.grid(row=11, column=0, sticky="ew", pady=(8, 3))
        ttk.Button(sidebar, text="Plan now", command=self.plan_now).grid(row=12, column=0, sticky="ew", pady=3)
        ttk.Button(sidebar, text="Poll Telegram", command=lambda: self.run_command("Poll Telegram", ["poll-telegram"])).grid(
            row=13, column=0, sticky="ew", pady=3
        )
        ttk.Button(sidebar, text="Book dry run", command=lambda: self.run_command("Book dry run", ["book-now", "--dry-run"])).grid(
            row=14, column=0, sticky="ew", pady=3
        )
        ttk.Button(sidebar, text="Book live", command=self.book_live).grid(row=15, column=0, sticky="ew", pady=3)

        ttk.Separator(sidebar).grid(row=16, column=0, sticky="ew", pady=14)

        ttk.Label(sidebar, text="Checks", font=("Segoe UI", 10, "bold")).grid(row=17, column=0, sticky="w")
        ttk.Button(sidebar, text="Test Telegram", command=lambda: self.run_command("Test Telegram", ["test-telegram"])).grid(
            row=18, column=0, sticky="ew", pady=(8, 3)
        )
        ttk.Button(sidebar, text="Test Calendar", command=lambda: self.run_command("Test Calendar", ["test-calendar"])).grid(
            row=19, column=0, sticky="ew", pady=3
        )

        ttk.Separator(sidebar).grid(row=20, column=0, sticky="ew", pady=14)
        ttk.Button(sidebar, text="Open screenshots", command=lambda: self.open_path(settings.screenshot_dir)).grid(
            row=21, column=0, sticky="ew", pady=3
        )
        ttk.Button(sidebar, text="Refresh", command=self.refresh_all).grid(row=22, column=0, sticky="ew", pady=3)

        main = ttk.Frame(self.root, padding=(0, 16, 16, 16))
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(2, weight=1)
        main.rowconfigure(4, weight=2)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, textvariable=self.status_var, font=("Segoe UI", 11)).grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="Open project folder", command=lambda: self.open_path(ROOT)).grid(row=0, column=1, sticky="e")

        self.check_frame = ttk.LabelFrame(main, text="Setup status", padding=10)
        self.check_frame.grid(row=1, column=0, sticky="ew", pady=(12, 10))
        self.check_frame.columnconfigure(0, weight=1)

        requests_frame = ttk.LabelFrame(main, text="Recent booking requests", padding=10)
        requests_frame.grid(row=2, column=0, sticky="nsew")
        requests_frame.columnconfigure(0, weight=1)
        requests_frame.rowconfigure(0, weight=1)
        columns = ("id", "target", "time", "status", "library", "room", "updated")
        self.requests = ttk.Treeview(requests_frame, columns=columns, show="headings", height=8)
        for column, label, width in (
            ("id", "ID", 50),
            ("target", "Target date", 100),
            ("time", "Time", 130),
            ("status", "Status", 90),
            ("library", "Library", 130),
            ("room", "Room", 130),
            ("updated", "Updated", 150),
        ):
            self.requests.heading(column, text=label)
            self.requests.column(column, width=width, anchor="w")
        self.requests.grid(row=0, column=0, sticky="nsew")
        request_scroll = ttk.Scrollbar(requests_frame, orient="vertical", command=self.requests.yview)
        request_scroll.grid(row=0, column=1, sticky="ns")
        self.requests.configure(yscrollcommand=request_scroll.set)

        log_header = ttk.Frame(main)
        log_header.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        log_header.columnconfigure(0, weight=1)
        ttk.Label(log_header, text="Output", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(log_header, text="Clear output", command=self.clear_output).grid(row=0, column=1, sticky="e")

        self.output = ScrolledText(main, height=14, wrap="word", font=("Consolas", 10))
        self.output.grid(row=4, column=0, sticky="nsew", pady=(6, 0))
        self.output.configure(state=DISABLED)

    def refresh_all(self) -> None:
        self.refresh_status()
        self.refresh_requests()

    def refresh_status(self) -> None:
        checks = [
            Check("Telegram bot token", bool(settings.telegram_bot_token), "Set TELEGRAM_BOT_TOKEN in .env"),
            Check("Telegram chat ID", bool(settings.telegram_chat_id), "Set TELEGRAM_CHAT_ID in .env"),
            Check("HKUL booking URL", bool(settings.hkul_booking_url), "Set HKUL_BOOKING_URL in .env"),
            Check("Google credentials", (ROOT / "credentials.json").exists(), "Add credentials.json"),
            Check("Google token", (ROOT / "token.json").exists(), "Run Google OAuth setup"),
            Check("HKUL login state", (ROOT / settings.playwright_auth_state_path).exists(), "Run Login to HKUL"),
            Check("Database", (ROOT / settings.database_path).exists(), "Run Initialize database"),
        ]
        for child in self.check_frame.winfo_children():
            child.destroy()
        for index, check in enumerate(checks):
            state = "OK" if check.ok else "Needs setup"
            label = ttk.Label(self.check_frame, text=f"{state}: {check.label}")
            label.grid(row=index, column=0, sticky="w", pady=1)
            detail = ttk.Label(self.check_frame, text=check.detail if not check.ok else "")
            detail.grid(row=index, column=1, sticky="e", padx=(20, 0), pady=1)
        missing = sum(1 for check in checks if not check.ok)
        if self.process is None:
            self.status_var.set("Ready" if missing == 0 else f"Ready, {missing} setup item(s) need attention")

    def refresh_requests(self) -> None:
        for item in self.requests.get_children():
            self.requests.delete(item)
        try:
            db.init_db()
            with db.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT id, target_date, start_time, end_time, status, library_choice,
                           room_choice, updated_at
                    FROM booking_requests
                    ORDER BY created_at DESC, id DESC
                    LIMIT 20
                    """
                ).fetchall()
        except Exception as exc:
            self._append_output(f"Could not load booking requests: {exc}\n")
            return

        for row in rows:
            time_range = f"{row['start_time'][11:16]}-{row['end_time'][11:16]}"
            self.requests.insert(
                "",
                END,
                values=(
                    row["id"],
                    row["target_date"],
                    time_range,
                    row["status"],
                    row["library_choice"] or "",
                    row["room_choice"] or "",
                    row["updated_at"],
                ),
            )

    def run_command(self, name: str, args: list[str], *, interactive: bool = False) -> None:
        if self.process is not None:
            messagebox.showinfo("Booker is busy", f"{self.process_name} is already running.")
            return
        command = [sys.executable, "-m", "app.main", *args]
        stdin = subprocess.PIPE if interactive else subprocess.DEVNULL
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        self._append_output(f"\n$ {' '.join(command)}\n")
        self.process_name = name
        self.status_var.set(f"Running: {name}")
        self._set_running_state(True)
        try:
            self.process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except Exception as exc:
            self.process = None
            self.status_var.set("Ready")
            self._set_running_state(False)
            messagebox.showerror("Could not start Booker", str(exc))
            return
        threading.Thread(target=self._read_process_output, daemon=True).start()

    def start_scheduler(self) -> None:
        self.run_command("Continuous Booker", ["run"])

    def login_hkul(self) -> None:
        self.run_command("HKUL login", ["login-hkul"], interactive=True)
        if self.process is not None:
            self.finish_login_button.configure(state=NORMAL)

    def finish_login(self) -> None:
        if self.process is None or self.process.stdin is None:
            return
        try:
            self.process.stdin.write("\n")
            self.process.stdin.flush()
            self.finish_login_button.configure(state=DISABLED)
        except Exception as exc:
            messagebox.showerror("Could not finish login", str(exc))

    def plan_now(self) -> None:
        command = ["plan-now"]
        selected = TARGET_CHOICES[self.target_choice.get()]
        if selected is not None:
            command.extend(["--target", selected])
        self.run_command("Plan now", command)

    def book_live(self) -> None:
        if messagebox.askyesno(
            "Live booking",
            "This will submit a real HKUL booking if the confirmed request is ready. Continue?",
        ):
            self.run_command("Book live", ["book-now", "--live"])

    def stop_process(self) -> None:
        if self.process is None:
            return
        self._append_output(f"\nStopping {self.process_name}...\n")
        self.process.terminate()

    def open_path(self, path: Path) -> None:
        full_path = path if path.is_absolute() else ROOT / path
        full_path.mkdir(parents=True, exist_ok=True) if full_path.suffix == "" else None
        try:
            os.startfile(full_path)  # type: ignore[attr-defined]
        except Exception as exc:
            messagebox.showerror("Could not open path", str(exc))

    def clear_output(self) -> None:
        self.output.configure(state=NORMAL)
        self.output.delete("1.0", END)
        self.output.configure(state=DISABLED)

    def _read_process_output(self) -> None:
        assert self.process is not None
        if self.process.stdout is not None:
            for line in self.process.stdout:
                self.output_queue.put(line)
        return_code = self.process.wait()
        self.output_queue.put(f"\n{self.process_name} exited with code {return_code}.\n")
        self.output_queue.put("__PROCESS_DONE__")

    def _drain_output(self) -> None:
        try:
            while True:
                line = self.output_queue.get_nowait()
                if line == "__PROCESS_DONE__":
                    self.process = None
                    self.process_name = ""
                    self._set_running_state(False)
                    self.finish_login_button.configure(state=DISABLED)
                    self.refresh_all()
                else:
                    self._append_output(line)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_output)

    def _append_output(self, text: str) -> None:
        self.output.configure(state=NORMAL)
        self.output.insert(END, text)
        self.output.see(END)
        self.output.configure(state=DISABLED)

    def _set_running_state(self, running: bool) -> None:
        self.start_button.configure(state=DISABLED if running else NORMAL)
        self.stop_button.configure(state=NORMAL if running else DISABLED)


def main() -> None:
    root = Tk()
    try:
        root.call("tk", "scaling", 1.25)
    except Exception:
        pass
    app = BookerApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: _close(root, app))
    root.mainloop()


def _close(root: Tk, app: BookerApp) -> None:
    if app.process is not None:
        if not messagebox.askyesno("Quit Booker", "A Booker command is still running. Stop it and quit?"):
            return
        app.process.terminate()
    root.destroy()


if __name__ == "__main__":
    main()
