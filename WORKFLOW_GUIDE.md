# BeeSmartVA — Practical Workflow Guide

A simple, step-by-step walkthrough of the everyday workflow for **Clients** and **Virtual Assistants (VAs)**.

---

## For Clients

> **Good news:** You barely need to do anything. The bot will message you directly when something needs your attention — all you have to do is tap a button.

---

### What to expect

The bot will send you **private Telegram messages** in two situations:

1. **A timesheet is ready for your approval** (usually end of week)
2. **A piece of content is ready for your review** (e.g. a LinkedIn post or email draft)

That's it. Everything else is handled by the team.

---

### Approving a timesheet

When the bot messages you about a timesheet, you'll see something like:

```
📋 Timesheet for Sarah Jones
Week: 14 Apr – 18 Apr

Mon: 4h — LinkedIn outreach
Tue: 3h — Email campaign
Wed: 4h — Strategy call
Thu: 2h — Content research
Fri: 3h — Follow-ups

Total: 16 hours
```

Tap one of the two buttons:

| Button | When to use it |
|--------|---------------|
| ✅ **Approve** | Hours look right — tap this to confirm |
| ❓ **I have a question** | Something doesn't look right — your supervisor will reach out to clarify |

> You will never see hourly rates or cost totals — that's handled privately between the team and your manager.

---

### Reviewing a content draft

When a draft is ready, the bot will send you the full text of the post, email, or caption.

Tap one of the two buttons:

| Button | When to use it |
|--------|---------------|
| ✅ **Approve** | You're happy with it — the VA will post it |
| ✏️ **Request Revision** | You'd like changes — the VA will revise and resubmit |

---

### Monthly satisfaction rating

Once a month, the bot will ask you to rate the team's performance. It looks like this:

```
How satisfied are you with the team this month?
1 😕  2 😐  3 🙂  4 😊  5 🌟
```

Just tap a number. It takes 2 seconds and helps the team improve.

---

### Reminders

The bot will send you a gentle reminder on **Friday mornings** if there are timesheets waiting for your approval. You don't need to check anything manually.

---

---

## For Virtual Assistants (VAs)

Your weekly routine follows a simple rhythm: **log → submit → act on feedback**.

---

### Daily — Log your hours

At the end of each working day, log your hours in the group chat:

```
/hours today 4 LinkedIn outreach and email replies
/hours yesterday 3 Strategy call prep
/hours 2024-04-15 2 Content research
```

**Format:** `/hours [date] [hours] [what you did]`

- Use `today` or `yesterday` for convenience
- Use a date like `2024-04-15` for anything older
- Half-hours are fine: `2.5`, `0.5`

Made a mistake? Edit it:

```
/hours edit today 3.5 Updated description
```

Check your week at any time:

```
/myweek
```

---

### End of week — Submit your timesheet

Every Friday, submit your hours for review:

```
/submit hours
```

**What happens next:**

1. Your supervisor receives your timesheet and reviews it
2. If approved, it goes to the client for final sign-off
3. Once the client approves, you're done for that week

> Your hours are never lost. If something is queried, you'll be notified and can follow up.

---

### Submitting content drafts

When you've written a post, email, or caption, submit it for review:

```
/draft linkedin Here is the LinkedIn post text...
/draft email Subject line and email body here...
/draft instagram Caption text here...
```

**What happens next:**

1. Your supervisor reviews it — they'll approve it or ask for changes
2. If approved, the client reviews it
3. Once the client approves, you'll get a message: *"Draft approved and ready to post"*
4. Post it, then mark it as published:

```
/posted DFT-001
```

(The draft code is shown in `/drafts`)

If changes are requested, you'll receive a message explaining what to fix. Just submit the revised version again with `/draft`.

---

### Managing tasks

**See your tasks:**
```
/tasks
```

**Create a task:**
```
/task Write LinkedIn post for product launch
```

**Complete a task:**
```
/done 12
```
(Use the task ID shown in `/tasks`)

**Stuck on something?** Flag it instead of leaving it open:
```
/cantdo 12 skill I don't have access to the LinkedIn account
/cantdo 12 time Too many priorities this week — need help
```

Your supervisor is notified and can step in.

---

### Tracking prospect follow-ups

**Log a new connection:**
```
/connection "Sarah Jones" LinkedIn
/connection "Mark Davies" LinkedIn "Head of Marketing" "Acme Corp"
```

A follow-up reminder is automatically set for 3 days later. When it's time to follow up, update the status:

| Command | Use when |
|---------|---------|
| `/followdone "Sarah Jones"` | You followed up — reschedules next reminder |
| `/replied "Sarah Jones"` | They replied — supervisor is notified |
| `/booked "Sarah Jones" 2024-04-25` | Meeting booked — closes the follow-up |
| `/noresponse "Sarah Jones"` | No response — closes the record |

See all pending follow-ups:
```
/followups
```

---

### Communicating with your supervisor

Use these instead of messaging the group — they go directly to your supervisor in private:

| Command | Use for |
|---------|--------|
| `/ask Should I prioritise LinkedIn or email this week?` | Questions |
| `/flag I don't have access to the Canva account` | Blocking issues |
| `/confirm Should I send the proposal today or wait?` | Yes/no decisions |

To message the client directly:
```
/notify client The LinkedIn campaign went live at 10am today
```

---

### Your daily rhythm

| Time | What to do |
|------|-----------|
| **Morning** | Check `/tasks` and `/followups` |
| **During the day** | Do the work |
| **End of day** | Log hours with `/hours today` |
| **Friday** | Submit timesheet with `/submit hours` |

The bot will also send you reminders at 9am (tasks/follow-ups), 12pm (log hours), and Friday 4pm (submit timesheet) — so you won't forget.

---

*For a full command reference, see [USER_MANUAL.md](USER_MANUAL.md)*
