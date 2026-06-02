# Instructions

This guide explains how to make `hku-booking-agent` work and how the system works internally.

## 1. What You Are Setting Up

`hku-booking-agent` is a personal booking assistant. It reads your Google Calendar, finds a free study slot, asks you on Telegram which room to try, stores your approval in SQLite, and later opens the HKUL booking website with Playwright.

The agent is intentionally human-approved. It must ask you first and only proceeds after you confirm a room choice.

It does not bypass CAPTCHA, MFA, login checks, rate limits, access controls, or HKU/HKUL rules.

## 2. Create And Activate A Virtual Environment

Open either `cmd.exe` or PowerShell from the project directory.

For `cmd.exe`:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

For PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Upgrade pip:

```powershell
python -m pip install --upgrade pip
```

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Install the Playwright browser:

```powershell
python -m playwright install chromium
```

## 3. Create Your `.env` File

Copy the example config.

For `cmd.exe`:

```bat
copy .env.example .env
```

For PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` and fill in the required values:

```env
GOOGLE_CALENDAR_ID=primary
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
HKUL_BOOKING_URL=
TIMEZONE=Asia/Hong_Kong
DEFAULT_SLOT_DURATION_MINUTES=120
TARGET_BOOKING_OFFSET_DAYS=2
PLANNER_HOUR=23
PLANNER_MINUTE=30
BOOKING_HOUR=0
BOOKING_MINUTE=0
PLAYWRIGHT_AUTH_STATE_PATH=playwright/.auth/hku.json
SCREENSHOT_DIR=data/screenshots
DATABASE_PATH=data/bookings.db
DRY_RUN=true
```

Keep `DRY_RUN=true` until the booking page selectors have been inspected and implemented.

## 4. Set Up Google Calendar

1. Go to Google Cloud Console.
2. Create or select a project.
3. Enable the Google Calendar API.
4. Configure OAuth consent.
5. Create an OAuth Client ID for a desktop application.
6. Download the OAuth JSON file.
7. Save it in this project root as:

```text
credentials.json
```

Then run:

```powershell
python scripts/setup_google_oauth.py
```

A browser window opens. Sign in to your Google account and approve access. The project saves the OAuth token to:

```text
token.json
```

Both `credentials.json` and `token.json` are ignored by git.

Test calendar access:

```powershell
python -m app.main test-calendar
```

## 5. Set Up Telegram

1. Open Telegram.
2. Message `@BotFather`.
3. Run `/newbot`.
4. Follow the prompts and copy the bot token.
5. Put the token in `.env` as `TELEGRAM_BOT_TOKEN`.
6. Send a message to your new bot from your Telegram account.
7. Get your chat ID:

For `cmd.exe`:

```bat
curl "https://api.telegram.org/botYOUR_TOKEN/getUpdates"
```

For PowerShell:

```powershell
Invoke-RestMethod "https://api.telegram.org/botYOUR_TOKEN/getUpdates"
```

Replace `YOUR_TOKEN` with the exact value from `TELEGRAM_BOT_TOKEN`. Do not include `<` or `>` around the token. Find the `chat.id` value and put it in `.env` as `TELEGRAM_CHAT_ID`.

Test Telegram:

```powershell
python -m app.main test-telegram
```

## 6. Initialize The Database

Create the SQLite database:

```powershell
python -m app.main init-db
```

This creates:

```text
data/bookings.db
```

The database is ignored by git.

## 7. Save HKUL Login State

Run:

```powershell
python -m app.main login-hkul
```

Playwright opens a visible browser at `HKUL_BOOKING_URL`.

Log in manually. Complete MFA, CAPTCHA, or any other normal login step yourself. When the website shows that you are logged in, return to the terminal and press Enter.

The browser login state is saved to:

```text
playwright/.auth/hku.json
```

This file is ignored by git.

## 8. Run The Planner Manually

Run:

```powershell
python -m app.main plan-now --target 2-days-after
```

This does the same thing as the scheduled 23:30 planner job:

1. Calculates the target booking date.
2. Reads your Google Calendar busy events.
3. Finds free slots.
4. Picks the best configured-duration booking slot.
5. Sends you a Telegram message asking which room to try.
6. Stores a pending booking request in SQLite.

Manual planning supports `--target today`, `--target tomorrow`, and `--target 2-days-after`. Without `--target`, it uses `TARGET_BOOKING_OFFSET_DAYS` from `.env`.

You can revise the Telegram plan conversationally. Example:

```text
Bot: I found this booking slot for Thursday: 13:00-15:00.
You: no, choose 14:00-16:00
Bot: Which library/facility do you want?
You: Chi Wah
Bot: Which room should I choose?
You: 6
Bot: Thursday 14:00-16:00, Chi Wah Learning Commons, room 6. Is that correct?
You: yes
```

Library names are matched case-insensitively, including aliases like `Chiwah`, `Main Lib`, `Law Library`, and `Music Library`.

Reply in Telegram with one of:

```text
room 5
room 6
any
yes room 5
no
cancel
```

After replying in Telegram, sync the reply into the database:

```powershell
python -m app.main poll-telegram
```

`book-now` also does a quick Telegram poll before checking for a confirmed request. When `run` is active, Telegram replies are polled every minute.

## 9. Run A Booking Dry Run

After you confirm a pending booking request, run this only if you want to test the booking flow manually:

```powershell
python -m app.main book-now --dry-run
```

Dry-run mode:

1. Opens the HKUL booking page.
2. Reuses the saved login state.
3. Takes screenshots.
4. Stops before submitting anything.

Screenshots are saved under:

```text
data/screenshots/
```

## 10. Live Booking Is Not Ready Until Selectors Are Added

The file `app/booking_browser.py` intentionally contains TODO placeholder selectors.

Before live booking can work, you must inspect the HKUL booking page and replace the placeholder selector comments with real selectors for:

1. Date selection.
2. Start time selection.
3. End time selection.
4. Facility or room selection.
5. Review or confirmation page.
6. Final submit button.

You must also add checks that the visible page clearly matches the requested booking:

1. Target date.
2. Start time.
3. End time.
4. Room or facility choice.

Only after those checks exist should you use:

```powershell
python -m app.main book-now --live
```

## 11. Run The Scheduler

Start the continuous scheduler:

```powershell
python -m app.main run
```

By default:

1. Planner runs daily at 23:30.
2. Telegram replies are polled every minute.
3. Booking attempt runs daily at 00:00.
4. The planner asks about today plus 2 days by default. The midnight job books the earliest confirmed request whose target date is not in the past.

Date offsets use normal calendar arithmetic. For example, if today is May 30, `tomorrow` is May 31 and `2-days-after` is June 1.

You can change these values in `.env`:

```env
PLANNER_HOUR=23
PLANNER_MINUTE=30
BOOKING_HOUR=0
BOOKING_MINUTE=0
TARGET_BOOKING_OFFSET_DAYS=2
```

## 12. How The System Works

### Config

`app/config.py` loads `.env` with `python-dotenv` and exposes a `settings` object used by the rest of the app.

Important settings include:

1. Google Calendar ID.
2. Telegram bot token and chat ID.
3. HKUL booking URL.
4. Timezone.
5. Booking target offset.
6. Screenshot directory.
7. SQLite database path.
8. Dry-run mode.

### Calendar

`app/calendar_client.py` connects to Google Calendar using OAuth.

It reads events for the target date and converts them into busy blocks. Busy calendar events are treated as unavailable time. Transparent/free events are ignored.

### Slot Picking

`app/slot_picker.py` receives busy blocks and finds free time between 08:00 and 23:00.

It ranks slots by:

1. Prefer slots after 15:00.
2. Prefer 2-hour slots.
3. Prefer not too late.
4. Avoid times outside the configured day window.

### Telegram

`app/telegram_bot.py` sends messages and screenshots through the Telegram Bot API.

It parses replies such as:

```text
room 5
any
yes room 5
no
cancel
```

Confirming a room changes a booking request from `pending` to `confirmed`. Saying `no` or `cancel` marks it as `cancelled`.

### Database

`app/db.py` stores booking requests in SQLite.

The main table is:

```text
booking_requests
```

Statuses are:

```text
pending
confirmed
booked
failed
cancelled
```

### Browser Booking

`app/booking_browser.py` uses Playwright.

It has two main functions:

```python
save_auth_state_manual_login()
book_room(request, dry_run=True)
```

Manual login saves browser state once. Booking reuses that saved state later.

Dry-run mode stops before final submission. Live mode is intentionally blocked until real HKUL selectors and visible-detail verification are implemented.

### Scheduler

`app/scheduler.py` defines two jobs:

1. `daily_planner_job()` at 23:30.
2. `midnight_booking_job()` at 00:00.

The planner asks for approval. The scheduler polls Telegram replies while it waits. The midnight job only proceeds if there is a confirmed request whose target date is not in the past.

### CLI

`app/main.py` exposes the command line interface:

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

## 13. Run Tests

Run:

```powershell
python -m pytest -q
```

Current tests cover:

1. Free slot generation.
2. Overlapping busy blocks.
3. Slot ranking.
4. SQLite booking request lifecycle.

## 14. Common Problems

### Telegram message does not send

Check:

1. `TELEGRAM_BOT_TOKEN` is correct.
2. `TELEGRAM_CHAT_ID` is correct.
3. You sent at least one message to the bot before calling `getUpdates`.

### Google Calendar fails

Check:

1. `credentials.json` exists in the project root.
2. Calendar API is enabled in Google Cloud Console.
3. OAuth consent was completed.
4. `token.json` was created.

### HKUL opens logged out

Run again:

```powershell
python -m app.main login-hkul
```

### Dry run cannot continue

Check:

1. `HKUL_BOOKING_URL` is set.
2. `playwright/.auth/hku.json` exists.
3. Your saved login session has not expired.

### Live booking fails

This is expected until `app/booking_browser.py` has real selectors and verification checks.

## 15. Recommended Safe Workflow

Use this order:

```powershell
python -m app.main init-db
python -m app.main test-telegram
python -m app.main test-calendar
python -m app.main login-hkul
python -m app.main plan-now --target 2-days-after
python -m app.main poll-telegram
python -m app.main book-now --dry-run
python -m app.main run
```

Only use live booking after the HKUL selectors have been implemented and tested in dry-run mode.

