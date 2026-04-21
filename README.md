# BeeSmartVA Bot

BeeSmartVA is an async Telegram workflow bot for VA teams. Each Telegram group is one client workspace. The bot supports hour logging, timesheets, draft review, follow-up tracking, reports, invoicing summaries, audit logging, and role-based permissions.

## Roles

- `VA`: logs hours, creates tasks, submits drafts.
- `SUPERVISOR`: reviews operational work, manages users, approves timesheets at manager stage.
- `CLIENT`: gives final approval and reviews drafts.
- `BUSINESS_MANAGER`: full access. Can do everything a supervisor and client can do, and receives a broader executive report.

- Guided `/menu` with button-driven flows for:
  - log hours
  - create task
  - submit draft
  - add user
  - set supervisor
  - set rate
- `BUSINESS_MANAGER` role added
- stronger callback tenant isolation
- duplicate `/setup` protection in one group
- `set rate` works with internal user ids
- migration helper script
- pytest coverage for core permissions and reports

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

## Group setup

Add the bot to a Telegram group, then run:

```text
/setup | Client Name | Business Name | Europe/Paris | Lead Generation | Smart support | Daily VA operations
```

The person who runs `/setup` becomes the `BUSINESS_MANAGER` for that workspace.

## Guided UX

Use `/menu` for the guided interface.

### Managers
- Add user: choose role, then enter Telegram ID once, then display name.
- Set supervisor: choose the VA, then choose the supervisor from existing users.
- Set rate: choose the VA, then enter the amount.

### VAs
- Log hours: choose date, choose hours, then send one note.
- Create task: tap button, then send one description.
- Submit draft: choose platform, then send draft content.

## Commands

Text commands remain available for power users. The main ones are:

- `/menu`
- `/help`
- `/groups`
- `/timesheets`
- `/submit hours`
- `/weekly`
- `/monthly`
- `/report all`

## Migration

Run this before deploying an older database to the new version:

```bash
python scripts/migrate_v2.py
```

## Tests

```bash
pytest -q
```


## Notification policy in this version

- Clients get one weekly digest on Friday with a summary of completed work and any payment confirmations waiting for them.
- Supervisors and business managers get proactive operational reminders and management summaries.
- VAs get daily nudges and weekly timesheet reminders.
- Overdue draft reminders are internal only and are not pushed to clients.
