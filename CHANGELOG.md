# Updated BeeSmartVA bot

This revision adds and changes the following:

## Major changes
- Added `BUSINESS_MANAGER` role with broader authority than `SUPERVISOR`
- Setup now registers the creator as `BUSINESS_MANAGER`
- Strengthened tenant isolation for timesheet, draft, and score callbacks
- Added reply-keyboard shortcuts so common actions can be tapped instead of typed
- Enabled manager actions for both `SUPERVISOR` and `BUSINESS_MANAGER`
- Allowed rate setting by internal user id as well as `tg:<telegram_id>`
- Prevented duplicate `/setup` in the same Telegram group
- Prevented a submitted timesheet from being committed when no supervisor is assigned
- Expanded report-all into an executive summary for supervisors and business managers

## Important notes
- This update is a code-level refactor and feature pass, not a full end-to-end product redesign.
- Many flows are now more button-friendly, but some operations still require text input because they create new content (for example `/task`, `/draft`, `/hours`).
- Existing database rows continue to work with the current SQLite schema.
