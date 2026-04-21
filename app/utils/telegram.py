from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.enums import Role


def timesheet_supervisor_keyboard(timesheet_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Approve — send to client for final sign-off', callback_data=f'ts:sup_approve:{timesheet_id}')],
        [InlineKeyboardButton('❓ Query — I have a question about these hours', callback_data=f'ts:query:{timesheet_id}')],
    ])


def timesheet_client_keyboard(timesheet_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Approve — hours look correct, all good', callback_data=f'ts:client_approve:{timesheet_id}')],
        [InlineKeyboardButton('❓ I have a question about these hours', callback_data=f'ts:query:{timesheet_id}')],
    ])


def draft_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Approve — forward to client for final sign-off', callback_data=f'df:approve:{draft_id}')],
        [InlineKeyboardButton('✏️ Request Revision — needs changes before client sees it', callback_data=f'df:revise:{draft_id}')],
    ])


def draft_client_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✅ Approve — looks good, ready to post', callback_data=f'df:client_approve:{draft_id}')],
        [InlineKeyboardButton('✏️ Request Revision — needs changes', callback_data=f'df:client_revise:{draft_id}')],
    ])


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('Yes', callback_data='cf:yes'), InlineKeyboardButton('No', callback_data='cf:no')],
    ])


def score_keyboard(target: str) -> InlineKeyboardMarkup:
    labels = [('1 😕 Poor', '1'), ('2 😐 Okay', '2'), ('3 🙂 Good', '3'), ('4 😊 Great', '4'), ('5 🌟 Excellent', '5')]
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f'sc:{target}:{value}') for label, value in labels]])


def role_main_keyboard(role: Role | None) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton('/menu'), KeyboardButton('/help')],
        [KeyboardButton('/guide'), KeyboardButton('/profile')],
    ]
    if role == Role.VA:
        rows += [
            [KeyboardButton('/hours today'), KeyboardButton('/myweek')],
            [KeyboardButton('/submit hours'), KeyboardButton('/tasks')],
            [KeyboardButton('/drafts'), KeyboardButton('/followups')],
        ]
    elif role == Role.CLIENT:
        rows += [
            [KeyboardButton('/weekly'), KeyboardButton('/monthly')],
            [KeyboardButton('/scores'), KeyboardButton('/drafts')],
        ]
    elif role in {Role.SUPERVISOR, Role.MANAGER}:
        rows += [
            [KeyboardButton('/timesheets'), KeyboardButton('/tasks')],
            [KeyboardButton('/flagged'), KeyboardButton('/overdue')],
            [KeyboardButton('/weekly'), KeyboardButton('/monthly')],
            [KeyboardButton('/groups'), KeyboardButton('/drafts')],
        ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)
