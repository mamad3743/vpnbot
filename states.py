from aiogram.fsm.state import State, StatesGroup


class BuyFlow(StatesGroup):
    waiting_discount_code = State()


class WalletFlow(StatesGroup):
    waiting_receipt = State()


class AdminFlow(StatesGroup):
    waiting_plan_info = State()
    waiting_code_info = State()
    waiting_broadcast = State()
