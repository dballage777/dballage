# Email the daily reports to yourself (optional)

The daily Action already writes a **CSV** (`paper/reports/standings.csv`) and a
**PDF** (`paper/reports/shadow_report.pdf`) into your repo every run — you can
download them from GitHub any time. This page turns on **automatic email
delivery** of those two files.

> The email step only runs if you add the secrets below. Without them it is
> skipped silently — nothing breaks.

## Easiest path: a Gmail sender + app password (≈5 min)

You email *from* a Gmail account *to* whatever address you want (e.g. your
`@nafcs.org`). Using a personal Gmail as the sender avoids org SMTP restrictions.

1. **Make an app password** on a Gmail account:
   - Enable 2-Step Verification (myaccount.google.com → Security).
   - Then myaccount.google.com → Security → **App passwords** → create one,
     name it "github". Copy the 16-character code.

2. **Add repo secrets:** GitHub → your repo → **Settings → Secrets and variables
   → Actions → New repository secret**. Add:

   | Secret name | Value |
   |---|---|
   | `MAIL_USERNAME` | your gmail address (the sender) |
   | `MAIL_PASSWORD` | the 16-char app password |
   | `MAIL_TO` | where to send it (e.g. `dballage@nafcs.org`) — optional, defaults to that |

That's it. The next daily run emails you the CSV + PDF.

## Other providers (optional)

Set these extra secrets if you don't use Gmail:

| Secret | Gmail (default) | Microsoft 365 / Outlook |
|---|---|---|
| `MAIL_SERVER` | `smtp.gmail.com` | `smtp.office365.com` |
| `MAIL_PORT` | `465` | `587` |

(For port 587 the connection uses STARTTLS; the action handles it. Org accounts
sometimes block SMTP/app passwords — if so, use the Gmail-sender path above.)

## Test it without waiting for the schedule

GitHub → **Actions → "Daily Shadow Paper Test" → Run workflow**. If the secrets
are set, you'll get the email within a couple minutes. If you didn't set them,
the run still succeeds — it just skips the email step.

## What you get

- **`standings.csv`** — the scoreboard (one row per variant: days, cum return,
  Sharpe, win%, exposure). Opens straight in Google Sheets/Excel.
- **`shadow_report.pdf`** — a one-page summary you can read on your phone.

Full Markdown detail always lives at
`https://github.com/dballage777/dballage/tree/main/paper/reports`.
