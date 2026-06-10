# HKU Booking Agent

Personal automation assistant for managing HKU study room booking attempts from your Google Calendar, Telegram, SQLite, and a Playwright-controlled browser.

The agent plans a candidate booking slot, asks you on Telegram which room to try, stores your approval, and later opens the HKUL booking site. It only submits a live booking after you have confirmed and after the page visibly matches the requested details.

## What It Does

- Reads Google Calendar events as busy time.
- Finds free study slots for a configurable target date.
- Prefers slots after classes, with a default 2-hour duration.
- Sends a Telegram approval prompt.
- Stores pending, confirmed, booked, failed, and cancelled requests in SQLite.
- Reuses a manually saved Playwright login state.
- Takes screenshots of booking attempts and sends the result on Telegram.
- Selects HKUL booking form fields with Playwright selectors for library, facility type, room/facility, date, session checkboxes, description, submit, and confirmation.
- Defaults to dry-run mode.

## What It Does Not Do

- It does not bypass CAPTCHA, MFA, access controls, anti-bot systems, rate limits, or HKU/HKUL terms.
- It does not hardcode passwords or secrets.
- It does not log in to HKUL by itself; you must save a valid login state with `python -m app.main login-hkul`.
- It does not guarantee booking success if HKUL changes its page, your login expires, or the selected room/session is unavailable.

## Safety Notes

Use this only for your own account and follow HKU/HKUL policies. If login, MFA, CAPTCHA, or anti-bot checks appear, complete them manually. If automation is blocked, the agent should stop, screenshot the page, and tell you what happened.

Secrets and local state are gitignored:

- `.env`
- `credentials.json`
- `token.json`
- `data/*.db`
- `data/screenshots/`
- `playwright/.auth/`

## Setup

From the project directory, use the command block for your shell.

For `cmd.exe`:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
python -m app.main init-db
```

For PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
python -m app.main init-db
```

Edit `.env` and set:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `HKUL_BOOKING_URL`

## Google Calendar API Setup

1. Open Google Cloud Console.
2. Create or select a project.
3. Enable the Google Calendar API.
4. Configure OAuth consent for a desktop app.
5. Create an OAuth Client ID with application type `Desktop app`.
6. Download the JSON file and save it as `credentials.json` in this project root.
7. Run:

```powershell
python scripts/setup_google_oauth.py
```

This opens a browser for consent and saves `token.json`. Both files are ignored by git.

## Telegram Bot Setup

1. Open Telegram and message `@BotFather`.
2. Run `/newbot` and follow the prompts.
3. Copy the token into `TELEGRAM_BOT_TOKEN`.
4. Send any message to your bot.
5. Find your chat ID with:

For `cmd.exe`:

```bat
curl "https://api.telegram.org/botYOUR_TOKEN/getUpdates"
```

For PowerShell:

```powershell
Invoke-RestMethod "https://api.telegram.org/botYOUR_TOKEN/getUpdates"
```

Replace `YOUR_TOKEN` with the exact value from `TELEGRAM_BOT_TOKEN`. Do not include `<` or `>` around the token. Put the `chat.id` value in `TELEGRAM_CHAT_ID`, then test:

```powershell
python -m app.main test-telegram
```

## Manual HKUL Login State

Run:

```powershell
python -m app.main login-hkul
```

A headed browser opens at `HKUL_BOOKING_URL`. Log in manually, including MFA if required, then return to the terminal and press Enter. Playwright stores browser state at `playwright/.auth/hku.json`, which is gitignored.

## Dry-Run Testing

Dry-run mode opens the booking site, saves screenshots, and stops before final submission.

```powershell
python -m app.main plan-now --target 2-days-after
python -m app.main poll-telegram
python -m app.main book-now --dry-run
```

Manual planning supports `--target today`, `--target tomorrow`, and `--target 2-days-after`; without `--target`, it uses `TARGET_BOOKING_OFFSET_DAYS` from `.env`. Reply in Telegram before running `poll-telegram`. `book-now` also does a quick Telegram poll before checking for a confirmed request. In the continuous scheduler, replies are polled every minute and the booking attempt waits until the configured booking time, default `00:00`. You can also set `DRY_RUN=true` in `.env`, which is the default.

Telegram replies can revise the plan before confirmation. For example, reply `no, choose 14:00-16:00`, then send a library such as `Chi Wah` or `Main Lib`, then a room such as `room 6` or `6`, then confirm the final summary.

To customize Telegram wording or accepted phrases, edit `app/telegram_bot.py`: `AFFIRMATIVE_REPLIES`, `CANCEL_REPLIES`, `ANY_ROOM_REPLIES`, `LIBRARY_ALIASES`, `HELP_TEXT`, and the `send_message(...)` calls in `_handle_pending_reply()`.

## Current Booking Automation Status

The HKUL booking selectors are implemented in `app/booking_browser.py`. The automation opens the New Booking page, verifies that the booking form is loaded, selects the requested library, facility type, room/facility, date, and session checkboxes, fills a description, screenshots the ready-to-submit page, and then:

- In dry-run mode, stops before submission.
- In live mode, clicks Submit, clicks the final Yes confirmation, screenshots the result, and marks the request as booked unless HKUL returns an error.

Dry-run mode is still recommended after HKUL login changes or if HKUL updates its site.

Manual live booking:

```powershell
python -m app.main book-now --live
```

Continuous live booking through `python booker.py` requires:

```env
DRY_RUN=false
```

## Desktop App

Booker can also run from a small desktop interface instead of typing CLI commands.

From PowerShell:

```powershell
python booker_app.py
```

On Windows, you can also double-click `start_booker_app.bat`.

The app provides buttons for setup checks, database initialization, HKUL login, manual planning, Telegram polling, dry-run booking, live booking, and starting or stopping the continuous scheduler. The output panel shows the same logs and command results you would normally see in the terminal.

During HKUL login, complete the browser login manually, then click **Finish login** in the Booker app. Live booking still asks for confirmation before it runs.

## Running Continuously

On a laptop:

```powershell
python booker.py
```

By default, this asks about a booking date two days ahead during the planner job, records your Telegram approval, then tries the confirmed booking at `00:00` the next day.

Date offsets use normal calendar arithmetic, so planning on May 30 with `--target 2-days-after` checks June 1.

Keep this process running. It polls Telegram continuously and uses the real current date/time from the machine clock. Press `Ctrl+C` in the terminal to stop Booker.

On Raspberry Pi 5:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
python -m app.main init-db
python booker.py
```

For long-running use on a Pi, create a `systemd` service that starts the virtualenv Python from this project directory.

## CLI Commands

```powershell
python -m app.main init-db
python -m app.main login-hkul
python -m app.main plan-now
python -m app.main book-now --dry-run
python -m app.main book-now --live
python -m app.main run
python -m app.main test-telegram
python -m app.main test-calendar
python -m app.main poll-telegram
```

## Troubleshooting

- `Missing credentials.json`: download the OAuth desktop client JSON and save it in the project root.
- Telegram test fails: check `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and whether you have sent a message to the bot first.
- HKUL opens logged out: run `python -m app.main login-hkul` again.
- Booking dry-run fails before screenshots: check `HKUL_BOOKING_URL` and the saved auth state path.
- No free slots found: adjust `DEFAULT_SLOT_DURATION_MINUTES`, `TARGET_BOOKING_OFFSET_DAYS`, or your calendar events.
- Live booking fails: check the screenshot in `data/screenshots/`, confirm your HKUL login state is still valid, and verify the selected date/session is available on HKUL.

## Booking Selector Notes

The current selectors are based on the HKUL New Booking page fields observed during setup. HKUL can still change the DOM, option labels, available facilities, login flow, or confirmation flow. If booking starts failing after a site change, inspect the latest screenshot in `data/screenshots/` and update `app/booking_browser.py`.

## Commands From Scratch

Open a terminal in the project directory first.

For `cmd.exe`:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
copy .env.example .env
python -m app.main init-db
python -m app.main test-telegram
python -m app.main test-calendar
python -m app.main login-hkul
python -m app.main plan-now --target 2-days-after
python -m app.main poll-telegram
python -m app.main book-now --dry-run
python booker.py
```

For PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
python -m app.main init-db
python -m app.main test-telegram
python -m app.main test-calendar
python -m app.main login-hkul
python -m app.main plan-now --target 2-days-after
python -m app.main poll-telegram
python -m app.main book-now --dry-run
python booker.py
```
