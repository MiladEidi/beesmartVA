from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app.enums import Role


def timesheet_supervisor_keyboard(timesheet_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('Approve and send to client', callback_data=f'ts:sup_approve:{timesheet_id}')],
        [InlineKeyboardButton('Mark as queried', callback_data=f'ts:query:{timesheet_id}')],
    ])


def timesheet_client_keyboard(timesheet_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('Approve final', callback_data=f'ts:client_approve:{timesheet_id}')],
        [InlineKeyboardButton('I have a question', callback_data=f'ts:query:{timesheet_id}')],
    ])


def draft_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('Looks good', callback_data=f'df:approve:{draft_id}')],
        [InlineKeyboardButton('Needs revision', callback_data=f'df:revise:{draft_id}')],
    ])


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('Yes', callback_data='cf:yes'), InlineKeyboardButton('No', callback_data='cf:no')],
    ])


def score_keyboard(target: str) -> InlineKeyboardMarkup:
    labels = [('1 😕', '1'), ('2 😐', '2'), ('3 🙂', '3'), ('4 😊', '4'), ('5 🌟', '5')]
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=f'sc:{target}:{value}') for label, value in labels]])


def role_main_keyboard(role: Role | None) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton('/menu'), KeyboardButton('/help')], [KeyboardButton('/guide'), KeyboardButton('/profile')]]
    if role == Role.VA:
        rows += [
            [KeyboardButton('/hours today 1'), KeyboardButton('/myweek')],
            [KeyboardButton('/submit hours'), KeyboardButton('/tasks')],
            [KeyboardButton('/drafts'), KeyboardButton('/followups')],
        ]
    elif role == Role.CLIENT:
        rows += [
            [KeyboardButton('/weekly'), KeyboardButton('/monthly')],
            [KeyboardButton('/drafts'), KeyboardButton('/scores')],
        ]
    elif role in {Role.SUPERVISOR, Role.BUSINESS_MANAGER}:
        rows += [
            [KeyboardButton('/groups'), KeyboardButton('/timesheets')],
            [KeyboardButton('/tasks'), KeyboardButton('/flagged')],
            [KeyboardButton('/weekly'), KeyboardButton('/monthly')],
            [KeyboardButton('/report all'), KeyboardButton('/drafts')],
        ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)
