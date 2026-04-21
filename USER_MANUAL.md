# BeeSmartVA — User Manual

> **How to use this manual:** Jump to your role section. Every command shows exactly who can use it and what it does. Commands marked **[Menu]** can also be done through the guided `/menu` button interface.

---

## Table of Contents

1. [What is BeeSmartVA?](#1-what-is-beesmartva)
2. [Roles at a Glance](#2-roles-at-a-glance)
3. [First-Time Setup (Business Manager)](#3-first-time-setup-business-manager)
4. [Virtual Assistant (VA) Guide](#4-virtual-assistant-va-guide)
5. [Supervisor Guide](#5-supervisor-guide)
6. [Client Guide](#6-client-guide)
7. [Business Manager Guide](#7-business-manager-guide)
8. [Automated Reminders & Scheduled Behaviors](#8-automated-reminders--scheduled-behaviors)
9. [User IDs Explained](#9-user-ids-explained)
10. [Rate Privacy Rules](#10-rate-privacy-rules)
11. [Command Quick Reference](#11-command-quick-reference)

---

## 1. What is BeeSmartVA?

BeeSmartVA is a Telegram-based team management bot for Virtual Assistant workflows. It runs inside a Telegram group and handles:

- **Hour logging and timesheet approvals** — VAs log daily hours; supervisors and clients approve weekly timesheets
- **Task management** — create, assign, complete, and flag tasks
- **Content draft review** — VAs submit content drafts; supervisors and clients review them before posting
- **Lead follow-up tracking** — VAs log prospect connections and track follow-up progress
- **Invoicing** — generate invoice summaries from approved timesheets
- **Automated nudges** — daily reminders, weekly digests, escalation alerts

All commands are typed in the group chat. The bot also sends private messages to supervisors and clients when something needs their attention.

---

## 2. Roles at a Glance

| Role | Who this is | What they do |
|------|-------------|--------------|
| **VA** (Virtual Assistant) | The person doing the work | Logs hours, completes tasks, submits drafts, tracks follow-ups |
| **SUPERVISOR** | Team lead / account manager | Reviews timesheets and drafts, manages tasks, handles escalations |
| **CLIENT** | The end client | Gives final approval on timesheets and content drafts, rates satisfaction |
| **BUSINESS_MANAGER** | Owner / senior manager | Full access — combines supervisor + client privileges + workspace admin |

> A workspace can have multiple VAs and supervisors, but only **one Business Manager** globally.

---

## 3. First-Time Setup (Business Manager)

### Step 1 — Create the workspace

Run this command **in the Telegram group**:

```
/setup | Client Name | Business Name | Timezone | Primary Service | Tagline | Description
```

**Example:**
```
/setup | Jane Smith | Smith Digital | Europe/London | Lead Generation | Smart VA support | Full-service VA team for daily ops and outreach
```

- `Timezone` must be a valid IANA timezone (e.g. `Europe/London`, `America/New_York`, `Asia/Manila`)
- The person who runs `/setup` becomes the Business Manager
- This must be done before any other commands will work

---

### Step 2 — Add team members

```
/adduser [telegram_id] [ROLE] [Full Name]
```

| Field | Options |
|-------|---------|
| `telegram_id` | Ask the person to message **@userinfobot** on Telegram to get their numeric ID |
| `ROLE` | `VA`, `SUPERVISOR`, `CLIENT`, or `BUSINESS_MANAGER` |
| `Full Name` | How they will appear in the system |

**Examples:**
```
/adduser 123456789 VA Sarah Jones
/adduser 987654321 SUPERVISOR Mark Davies
/adduser 555000111 CLIENT Emma Thompson
```

After adding a VA, the bot shows a setup checklist with their **User ID** and the remaining steps.

---

### Step 3 — Assign a supervisor to each VA *(required for timesheets)*

```
/set supervisor [va_user_id] [supervisor_user_id]
```

Both IDs are shown in `/groups`. Without this, the VA can log hours but **cannot submit timesheets**.

---

### Step 4 — Set each VA's hourly rate *(required for invoicing)*

```
/set rate [va_user_id] [amount]
```

Without this, invoice calculations will show $0. Rates are encrypted — only the VA themselves and supervisors can see them.

---

### Step 5 — Ask everyone to run `/start` in the group

Each team member must type `/start` in the group to activate their account and confirm their role.

---

### Useful admin commands

| Command | What it does |
|---------|-------------|
| `/groups` | List all registered users, their User IDs, and roles |
| `/auditlog` | View last 20 changes made in the workspace |
| `/set timezone [tg_id\|client] [timezone]` | Update a user's or the client's timezone |
| `/update [field] [value]` | Update workspace settings (name, business_name, tagline, etc.) |
| `/setmanager [telegram_id] [display_name]` | Transfer Business Manager role to someone else |

---

## 4. Virtual Assistant (VA) Guide

### Getting started

1. Make sure your supervisor has run `/adduser` to register you
2. Type `/start` in the group — you will see your account readiness status
3. Check that supervisor and rate are configured (if not, ask your Business Manager)

---

### Logging hours

```
/hours [date] [hours] [note]
```

| Argument | Examples |
|----------|---------|
| `date` | `today`, `yesterday`, `2024-04-15` |
| `hours` | `4`, `2.5`, `0.5` |
| `note` | Brief description of work done |

**Examples:**
```
/hours today 4 LinkedIn outreach and email replies
/hours yesterday 3 Strategy planning call with client
/hours 2024-04-15 2 Content research
```

**[Menu]** `/menu → Log Hours` guides you step by step.

---

### Editing a logged entry

```
/hours edit [date] [hours] [new note]
```

**Example:**
```
/hours edit today 3.5 Updated description
```

---

### Checking your week

```
/myweek
```

Shows all hours logged this week, broken down by day with notes and running total.

---

### Submitting your timesheet

```
/submit hours
```

**[Menu]** `/menu → Submit Timesheet`

- Submits the current week for supervisor review
- **Requirement:** A supervisor must be assigned to your account first
- Your hours are never lost — you can always log and resubmit

**What happens next:**
1. Your supervisor receives a private message with the full timesheet and Approve / Query buttons
2. If approved, the client receives it for final sign-off (hours only, no rate shown)
3. Once the client approves, the timesheet is marked as **APPROVED**

---

### Managing tasks

**View your tasks:**
```
/tasks
```

**Create a task:**
```
/task [description]
```
**[Menu]** `/menu → Create Task`

**Complete a task:**
```
/done [task_id]
```
**[Menu]** `/menu → My Tasks → tap task → Mark Done`

**Flag a task as blocked:**
```
/cantdo [task_id] skill|time [optional note]
```

| Reason | Use when |
|--------|---------|
| `skill` | You lack the access or skills needed |
| `time` | You have too many priorities |

**Examples:**
```
/cantdo 12 skill No Canva access to edit this graphic
/cantdo 12 time Too many tasks this week — need help prioritising
```

Your supervisor is notified and can reassign or help resolve the blocker.

---

### Submitting content drafts

```
/draft [platform] [content]
```

| Platform | Use for |
|----------|---------|
| `linkedin` | LinkedIn posts |
| `email` | Email campaigns |
| `instagram` | Instagram captions |
| `other` | Any other platform |

**Example:**
```
/draft linkedin Here is the draft post text for this week's LinkedIn update...
```

**[Menu]** `/menu → Submit Draft` guides you through platform selection then content.

**Draft approval flow:**
1. Supervisor receives your draft and approves or requests changes
2. If approved, the client reviews and gives final sign-off
3. Once approved, you receive: *"Draft approved and ready to post"*
4. After posting, mark it as published:

```
/posted [draft_code]
```

**Example:** `/posted DFT-001` (draft code is shown in `/drafts`)

**If changes are requested:** You will receive a message explaining what to revise. Submit again with `/draft platform updated_content` — it will be linked to the original.

---

### Tracking prospect connections and follow-ups

**Log a new connection:**
```
/connection [name] [platform] (title) (company)
```

**[Menu]** `/menu → Log Connection`

**Examples:**
```
/connection "Sarah Jones" LinkedIn
/connection "Mark Davies" LinkedIn "Head of Marketing" "Acme Corp"
```

A follow-up reminder is automatically scheduled 3 days later.

**Update follow-up status:**

| Command | Use when |
|---------|---------|
| `/followdone [name]` | You followed up — reschedules next follow-up |
| `/replied [name]` | They replied — supervisor is notified |
| `/booked [name] (date)` | Meeting/call booked — closes the follow-up cycle |
| `/noresponse [name]` | No response — closes the record |

**View pending follow-ups:**
```
/followups
```

---

### Communicating with your supervisor

These send a **private message** to your supervisor — use them for anything that needs their attention without broadcasting to the whole group.

| Command | Use for |
|---------|--------|
| `/ask [message]` | Questions and clarifications |
| `/flag [message]` | Blocking issues or alerts |
| `/confirm [question]` | Yes/no decisions |

**Examples:**
```
/ask Should I prioritise LinkedIn or email outreach today?
/flag I don't have access to the LinkedIn account
/confirm Should I send the proposal today or wait until Thursday?
```

**[Menu]** `/menu → Quick Actions`

---

### Messaging the client directly

```
/notify client [message]
```

**Example:**
```
/notify client The LinkedIn campaign went live at 10am today
```

---

### Viewing your rate

```
/rate
```

Shows your own hourly rate if one has been set. You cannot see other VAs' rates.

---

## 5. Supervisor Guide

### Daily workflow

- Check your `/menu` or run `/stats` for a quick overview of what needs attention
- Respond to timesheet and draft approval requests received in private chat
- Use `/tasks` to monitor team task progress

---

### Managing users

**View all team members and their IDs:**
```
/groups
```

**Assign a supervisor to a VA:**
```
/set supervisor [va_user_id] [supervisor_user_id]
```

**Set a VA's hourly rate:**
```
/set rate [va_user_id] [amount]
```
or
```
/set rate tg:[telegram_id] [amount]
```

**[Menu]** `/menu → Set Supervisor` and `/menu → Set Rate` for guided flows.

---

### Reviewing timesheets

When a VA submits, you receive a **private message** with the full timesheet including hours breakdown, rate, and estimated total.

**Buttons:**
- ✅ **Approve** — sends to the client for final sign-off
- ❓ **Query** — marks as queried; VA is notified to follow up

**List all pending timesheets:**
```
/timesheets
```

---

### Reviewing content drafts

When a VA submits a draft, you receive a **private message** with the content.

**Buttons:**
- ✅ **Approve** — forwards draft to client for final review
- ✏️ **Revise** — sends VA a revision request

---

### Managing tasks

**View all open tasks:**
```
/tasks
```

**Create a task:**
```
/task [description]
```

**Assign a task to a VA:**
```
/assign [task_id] [va_user_id]
```

**View blocked tasks:**
```
/flagged
```

**View stalled tasks (open > 48 hours):**
```
/overdue
```

---

### Checking a VA's rate

```
/rate [va_user_id]
```

User IDs are shown in `/groups`.

---

### Invoicing

**Preview an invoice for a date range:**
```
/invoice summary [va_telegram_id] [YYYY-MM-DD:YYYY-MM-DD]
```

Shows total approved hours, hourly rate, and total amount owed. Only counts **APPROVED** timesheets.

**Example:**
```
/invoice summary 123456789 2024-01-01:2024-01-31
```

**Record that an invoice has been sent:**
```
/invoice sent [va_telegram_id] [YYYY-MM-DD:YYYY-MM-DD]
```

---

### Reports

| Command | Shows |
|---------|-------|
| `/weekly` | Team activity this week (tasks, hours, drafts, connections) |
| `/monthly` | Monthly overview and trends |
| `/report all` | Executive summary across all workspaces (sent to private chat) |
| `/stats` | Quick dashboard: open tasks, flagged, hours, pending items |
| `/scores` | Satisfaction score history from the client |

**Send a satisfaction survey to the client on demand:**
```
/send scorecheck
```

---

## 6. Client Guide

As a Client, you are mostly notified by the bot in **private chat** when something needs your approval. You do not need to type commands regularly.

---

### Approving timesheets

When a supervisor approves a timesheet, you receive a **private message** showing:
- VA name
- Week covered
- Daily hours breakdown with notes
- Total hours

**Buttons:**
- ✅ **Approve** — marks the timesheet as fully approved
- ❓ **I have a question** — marks as queried; supervisor will follow up

> Hourly rates and cost totals are **not shown to clients** — you see hours only.

---

### Approving content drafts

When a supervisor approves a draft, you receive a **private message** with the full content.

**Buttons:**
- ✅ **Approve** — VA is notified and will post the content
- ✏️ **Request Revision** — VA is sent back to revise and resubmit

---

### Rating satisfaction

Once a month (or when triggered by your supervisor), you receive a **private message** asking you to rate the team's performance.

**Buttons:** 1 😕 Poor → 5 🌟 Excellent

Your ratings are tracked over time and visible to supervisors.

---

### Viewing reports

```
/weekly    — This week's activity summary
/monthly   — Monthly overview
/stats     — Quick dashboard
```

---

## 7. Business Manager Guide

The Business Manager has full access to everything supervisors and clients can do, plus exclusive admin capabilities.

All commands from the [Supervisor Guide](#5-supervisor-guide) and [Client Guide](#6-client-guide) apply here.

---

### Exclusive Business Manager commands

**Transfer the Business Manager role:**
```
/setmanager [telegram_id] [display_name]
```

This removes the BM role from you and assigns it to the new person in all workspaces. Use with caution.

**Financial executive report:**
```
/report all
```

Unlike supervisors who see only operational data, Business Managers receive approved hours totals and financial summaries across all workspaces.

---

### Workspace setup and admin

All setup commands (`/setup`, `/adduser`, `/set rate`, `/set supervisor`, `/groups`, `/auditlog`, `/update`) are available to Business Managers — see [First-Time Setup](#3-first-time-setup-business-manager).

---

## 8. Automated Reminders & Scheduled Behaviors

The bot sends automatic messages — you don't need to do anything to trigger these.

### VA reminders

| Time | Message |
|------|---------|
| 9am daily | Check open tasks and due follow-ups |
| 12pm daily | Reminder to log today's hours |
| Friday 4pm | Reminder to submit weekly timesheet |

### Supervisor reminders

| Time | Message |
|------|---------|
| 2pm weekdays | Action digest: pending timesheets, drafts, flagged tasks |
| Tuesday 10am | Reminder if timesheets are waiting for review |
| Monday 10am | Weekly operational report |
| 1st Monday of month, 11am | Monthly performance report |

### Client reminders

| Time | Message |
|------|---------|
| Friday 9am | Reminder if timesheets are waiting for final approval |
| Alternating Friday 5pm | Weekly digest of work done and pending items |

### Draft escalation

| Trigger | Action |
|---------|--------|
| Draft pending supervisor review for 48h | Supervisor receives a reminder |
| Draft pending client approval for 48h | Client receives a nudge |
| Draft pending client approval for 72h | Supervisor receives an escalation alert |

### Follow-up reminders

Connections with a due follow-up date send the VA a daily nudge at 9am.

---

## 9. User IDs Explained

Every user in BeeSmartVA has a **User ID** — a 4-digit random number (e.g. `2847`).

- It is assigned when you are added to the system and never changes
- It is **not sequential** — it tells you nothing about how many users are in the system
- It is used in commands like `/set supervisor 2847 5193` and `/assign 12 2847`

**To look up User IDs:**
```
/groups
```
Shows all registered users with their ID, name, and role.

> Note: This ID is different from your Telegram ID. Your Telegram ID is a long number from @userinfobot. The User ID is the short 4-digit number used in bot commands.

---

## 10. Rate Privacy Rules

Hourly rates are encrypted in storage. Visibility is strictly controlled:

| Who | What they can see |
|-----|------------------|
| **VA** | Their **own** rate only — via `/rate` |
| **Client** | **Nothing** — rate is never shown to clients |
| **Supervisor / BM** | Any VA's rate — via `/rate [va_user_id]` |

When a timesheet is sent to a client for approval, the `💰 Rate` and `💵 Estimated` lines are automatically removed — the client sees hours only.

---

## 11. Command Quick Reference

### All roles

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and account readiness check |
| `/help` | Role-specific command reference |
| `/guide [topic]` | Step-by-step guides (hours, timesheets, tasks, drafts, etc.) |
| `/menu` | Guided button interface for all features |
| `/profile` | Your name, role, client, and timezone |
| `/stats` | Quick team dashboard |
| `/weekly` | This week's activity summary |
| `/monthly` | Monthly overview |
| `/links` | Workspace booking links |
| `/contacts` | Restricted contacts list |

### VA only

| Command | Description |
|---------|-------------|
| `/hours [date] [h] [note]` | Log work hours |
| `/hours edit [date] [h] [note]` | Edit a logged entry |
| `/myweek` | This week's hours breakdown |
| `/submit hours` | Submit timesheet for review |
| `/rate` | View your own hourly rate |
| `/task [description]` | Create a task |
| `/tasks` | View your assigned tasks |
| `/done [task_id]` | Complete a task |
| `/cantdo [task_id] skill\|time [note]` | Flag a task as blocked |
| `/draft [platform] [content]` | Submit content draft |
| `/drafts` | List all your drafts |
| `/posted [draft_code]` | Mark draft as published |
| `/connection [name] [platform]` | Log a new prospect |
| `/followups` | View pending follow-ups |
| `/followdone [name]` | Mark follow-up done |
| `/replied [name]` | Prospect replied |
| `/booked [name]` | Meeting booked |
| `/noresponse [name]` | Close — no response |
| `/ask [message]` | Ask supervisor a question |
| `/flag [message]` | Alert supervisor to a blocker |
| `/confirm [question]` | Request a decision from supervisor |
| `/notify client [message]` | Send message to client |

### Supervisor & Business Manager

| Command | Description |
|---------|-------------|
| `/adduser [tg_id] [ROLE] [Name]` | Register a new team member |
| `/groups` | List all users and their IDs |
| `/set supervisor [va_id] [sup_id]` | Assign VA's supervisor |
| `/set rate [va_id] [amount]` | Set VA's hourly rate |
| `/set timezone [tg_id\|client] [tz]` | Update user or client timezone |
| `/rate [va_user_id]` | View a VA's hourly rate |
| `/timesheets` | List pending timesheets |
| `/assign [task_id] [va_id]` | Assign task to a VA |
| `/overdue` | Tasks open longer than 48 hours |
| `/flagged` | Blocked tasks flagged by VAs |
| `/drafts` | All draft submissions |
| `/followups` | All team follow-ups |
| `/invoice summary [tg_id] [range]` | Preview invoice for a period |
| `/invoice sent [tg_id] [range]` | Record invoice as sent |
| `/report all` | Executive summary (private chat) |
| `/scores` | Client satisfaction history |
| `/send scorecheck` | Send satisfaction survey to client |
| `/auditlog` | Last 20 changes in the workspace |

### Business Manager only

| Command | Description |
|---------|-------------|
| `/setup \| ...` | Initialize workspace (first-time only) |
| `/setmanager [tg_id] [name]` | Transfer Business Manager role |

---

*Last updated: 2026-04-21*
