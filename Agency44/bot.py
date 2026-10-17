import sqlite3
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8713857250:AAFs-Zsk37udri97_4ttfANB18Ae87fH1k8"  # Вставь свой токен от BotFather
ADMIN_IDS = [6096550279]  # Вставь свой Telegram ID

bot = Bot(token=TOKEN)
router = Router()

def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            exp INTEGER DEFAULT 0,
            earned TEXT DEFAULT '0$',
            last_daily TEXT DEFAULT '',
            registered_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, name, exp, earned, last_daily FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def register_user(user_id: int, username: str, name: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, name, exp, earned, registered_at) VALUES (?, ?, ?, 0, '0$', ?)", (user_id, username, name, now))
    cursor.execute("UPDATE users SET name = ? WHERE user_id = ?", (name, user_id))
    conn.commit()
    conn.close()

def update_user_exp(user_id: int, add_exp: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT exp FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        new_exp = row[0] + add_exp
        cursor.execute("UPDATE users SET exp = ? WHERE user_id = ?", (new_exp, user_id))
        conn.commit()
    conn.close()

def update_user_earned(user_id: int, new_earned: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET earned = ? WHERE user_id = ?", (new_earned, user_id))
    conn.commit()
    conn.close()

def update_daily_timer(user_id: int):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (now, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, exp, earned FROM users")
    rows = cursor.fetchall()
    conn.close()
    return rows

class RegistrationState(StatesGroup):
    waiting_for_name = State()

class AdminState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_earned_value = State()

def generate_battery_bar(exp: int, min_val: int, max_val: int):
    span = max_val - min_val
    current = exp - min_val
    percent = int((current / span) * 100)
    if percent > 100: percent = 100
    if percent < 0: percent = 0
    filled = int(percent / 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"🔋 [{bar}] {percent}%"

def get_rank_info(exp: int):
    if exp < 100:
        return "Нуб", 0, 100, generate_battery_bar(exp, 0, 100)
    elif exp < 300:
        return "Средний", 100, 300, generate_battery_bar(exp, 100, 300)
    elif exp < 600:
        return "Профи", 300, 600, generate_battery_bar(exp, 300, 600)
    elif exp < 1000:
        return "Мастер", 600, 1000, generate_battery_bar(exp, 600, 1000)
    elif exp < 2000:
        return "Менеджер", 1000, 2000, generate_battery_bar(exp, 1000, 2000)
    else:
        return "Заместитель", 2000, 10000, "🔋 [██████████] MAX"

def main_menu_kb(user_id: int):
    keyboard = [
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="📋 Задания", callback_data="tasks")],
        [InlineKeyboardButton(text="📖 Мануалы", callback_data="manuals")]
    ]
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def back_to_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]])

def tasks_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сдать отчет: TikTok (+10 EXP)", callback_data="task_tt")],
        [InlineKeyboardButton(text="✅ Сдать отчет: Аутрич (+25 EXP)", callback_data="task_outreach")],
        [InlineKeyboardButton(text="⭐ Забрать ежедневный бонус (+3 EXP)", callback_data="task_daily")],
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Изменить заработок юзеру", callback_data="admin_set_earned")],
        [InlineKeyboardButton(text="📊 Статистика базы", callback_data="admin_stats")],
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    ])

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user or not user[2]:
        await message.answer("🖤 <b>Добро пожаловать!</b>\n\nПожалуйста, напиши своё имя:")
        await state.set_state(RegistrationState.waiting_for_name)
    else:
        await message.answer(f"🖤 С возвращением, <b>{user[2]}</b>!", reply_markup=main_menu_kb(message.from_user.id), parse_mode="HTML")

@router.message(RegistrationState.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    register_user(message.from_user.id, message.from_user.username or "", name)
    await state.clear()
    await message.answer(f"✅ Регистрация пройдена, <b>{name}</b>!", reply_markup=main_menu_kb(message.from_user.id), parse_mode="HTML")

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    name = user[2] if user and user[2] else "Сотрудник"
    await callback.message.edit_text(f"🖤 Главное меню, <b>{name}</b>!", reply_markup=main_menu_kb(callback.from_user.id), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user: return
    username, name, exp, earned = f"@{user[1]}" if user[1] else "нет", user[2], user[3], user[4]
    rank_name, _, _, battery = get_rank_info(exp)
    text = f"👤 <b>{username} | {name}</b>\n\n🎖 <b>Ранг:</b> {rank_name}\n📈 <b>EXP:</b> {exp}\n{battery}\n\n💰 <b>Заработано:</b> {earned}"
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "tasks")
async def cb_tasks(callback: CallbackQuery):
    text = "📋 <b>Задания:</b>\n\n1️⃣ 3 видео в ТТ (+10 EXP)\n2️⃣ 100+ аутрич (+25 EXP)\n3️⃣ Бонус (+3 EXP)"
    await callback.message.edit_text(text, reply_markup=tasks_kb(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "task_tt")
async def cb_task_tt(callback: CallbackQuery):
    update_user_exp(callback.from_user.id, 10)
    await callback.answer("🎉 +10 EXP!", show_alert=True)
    await cb_tasks(callback)@router.callback_query(F.data == "task_outreach")
async def cb_task_outreach(callback: CallbackQuery):
    update_user_exp(callback.from_user.id, 25)
    await callback.answer("🎉 +25 EXP!", show_alert=True)
    await cb_tasks(callback)

@router.callback_query(F.data == "task_daily")
async def cb_task_daily(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    if user[5]:
        last_time = datetime.strptime(user[5], "%Y-%m-%d %H:%M:%S")
        if datetime.now() - last_time < timedelta(hours=24):
            await callback.answer("⏳ Бонус доступен раз в 24 часа!", show_alert=True)
            return
    update_user_exp(callback.from_user.id, 3)
    update_daily_timer(callback.from_user.id)
    await callback.answer("⭐ +3 EXP!", show_alert=True)
    await cb_tasks(callback)

@router.callback_query(F.data == "manuals")
async def cb_manuals(callback: CallbackQuery):
    text = "📖 <b>Мануал</b>\n\nПривет! Наша цель — привлекать трафик, продвигать экспертов и выстраивать поток клиентов."
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    await callback.message.edit_text("⚙️ Админ-панель", reply_markup=admin_kb(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    users = get_all_users()
    await callback.message.edit_text(f"📊 Всего юзеров: {len(users)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]]), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "admin_set_earned")
async def cb_admin_set_earned(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    users = get_all_users()
    text = "👥 Юзеры:\n" + "".join([f"ID: <code>{u[0]}</code> | {u[1]} | Заработано: {u[3]}\n" for u in users]) + "\nВведите ID:"
    await callback.message.edit_text(text, parse_mode="HTML")
    await state.set_state(AdminState.waiting_for_user_id)
    await callback.answer()

@router.message(AdminState.waiting_for_user_id)
async def admin_get_user_id(message: Message, state: FSMContext):
    try:
        target_id = int(message.text.strip())
        await state.update_data(target_id=target_id)
        await message.answer("Введите новое значение заработка (например: 150$):")
        await state.set_state(AdminState.waiting_for_earned_value)
    except ValueError:
        await message.answer("Введите числовой ID:")

@router.message(AdminState.waiting_for_earned_value)
async def admin_get_earned(message: Message, state: FSMContext):
    val = message.text.strip()
    data = await state.get_data()
    update_user_earned(data.get("target_id"), val)
    await state.clear()
    await message.answer("✅ Баланс обновлен!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админку", callback_data="admin_panel")]]))

async def main():
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())