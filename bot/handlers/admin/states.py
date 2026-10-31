from aiogram.fsm.state import State, StatesGroup


class TplStates(StatesGroup):
    title = State()
    text = State()
    edit_text = State()


class PrizeStates(StatesGroup):
    custom_text = State()


class WriteStates(StatesGroup):
    message = State()


class AdminStates(StatesGroup):
    add = State()


class RuleStates(StatesGroup):
    deadline = State()
    top = State()
    goal = State()
