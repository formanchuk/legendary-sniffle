import asyncio
import logging
import sqlite3
import os
from datetime import datetime
from typing import List, Dict
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.exceptions import TelegramAPIError

# Беремо змінні з оточення (Render їх підставить)
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
YOUR_USERNAME = os.environ.get("YOUR_USERNAME")
PORTFOLIO_LINK = os.environ.get("PORTFOLIO_LINK")

# Перевірка чи всі змінні є
if not all([TOKEN, ADMIN_ID, YOUR_USERNAME, PORTFOLIO_LINK]):
    raise ValueError("❌ Відсутні обов'язкові змінні оточення!")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN)
dp = Dispatcher()

class Database:
    def __init__(self, db_name="bot.db"):
        self.conn = sqlite3.connect(db_name)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
    
    def create_tables(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                registered_at TIMESTAMP,
                last_active TIMESTAMP
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                contact TEXT,
                description TEXT,
                budget TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)
        self.conn.commit()
    
    def register_user(self, user_id: int, username: str, full_name: str):
        self.conn.execute("""
            INSERT OR REPLACE INTO users (user_id, username, full_name, registered_at, last_active)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, full_name, datetime.now(), datetime.now()))
        self.conn.commit()
    
    def save_order(self, user_id: int, data: dict) -> int:
        cursor = self.conn.execute("""
            INSERT INTO orders (user_id, name, contact, description, budget, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, data['name'], data['contact'], data['description'], 
              data['budget'], datetime.now(), datetime.now()))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_user_orders(self, user_id: int) -> List[Dict]:
        cursor = self.conn.execute("""
            SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]

db = Database()

class OrderBot(StatesGroup):
    name = State()
    contact = State()
    description = State()
    budget = State()
    confirm = State()

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🤖 Замовити бота")],
        [KeyboardButton(text="💼 Приклади робіт"), KeyboardButton(text="💰 Ціни")],
        [KeyboardButton(text="ℹ️ Про нас"), KeyboardButton(text="📞 Контакти")],
        [KeyboardButton(text="📊 Мої замовлення")]
    ],
    resize_keyboard=True
)

back_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="⬅️ Повернутись назад")]],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Скасувати замовлення")]],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def start(message: types.Message):
    db.register_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "без ніка",
        full_name=message.from_user.full_name
    )
    
    await message.answer(
        "👋 Вітаю! Я створюю Telegram-ботів під ключ\n\n"
        f"✨ Привіт, {message.from_user.first_name}!\n"
        "👇 Оберіть дію:",
        reply_markup=main_kb
    )
    logger.info(f"Користувач {message.from_user.id} запустив бота")

@dp.message(F.text == "❌ Скасувати замовлення")
async def cancel_order(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer(
            "❌ *Замовлення скасовано!*\n\nВи повернулись в головне меню.",
            reply_markup=main_kb,
            parse_mode="Markdown"
        )
    else:
        await message.answer("У вас немає активних замовлень.", reply_markup=main_kb)

@dp.message(F.text == "💼 Приклади робіт")
async def works(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer(
            "⚠️ *У вас є активне замовлення!*\n\nСпочатку завершіть або скасуйте поточне замовлення.",
            parse_mode="Markdown"
        )
        return
    
    examples_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Бот для заявок", callback_data="example_orders")],
        [InlineKeyboardButton(text="🛍️ Бот для продажів", callback_data="example_sales")],
        [InlineKeyboardButton(text="📊 Бот для бізнесу", callback_data="example_business")],
        [InlineKeyboardButton(text="🎮 Бот з міні-іграми", callback_data="example_games")],
        [InlineKeyboardButton(text="🧠 Бот зі ШІ", callback_data="example_ai")],
        [InlineKeyboardButton(text="📁 Всі роботи в портфоліо", url=PORTFOLIO_LINK)],
        [InlineKeyboardButton(text="📩 Замовити такого ж бота", callback_data="order_same")]
    ])
    
    await message.answer(
        "💼 *Мої роботи та портфоліо*\n\n👇 *Оберіть категорію:*",
        reply_markup=examples_kb,
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data.startswith("example_"))
async def show_example(callback: types.CallbackQuery):
    example_type = callback.data.split("_")[1]
    
    examples = {
        "orders": "📝 *Бот для заявок*\n\n✅ Функціонал: Прийом заявок 24/7\n💰 Вартість: від 50$\n⏱️ Термін: 2-3 дні",
        "sales": "🛍️ *Бот для продажів*\n\n✅ Функціонал: Каталог, кошик, оплата\n💰 Вартість: від 100$\n⏱️ Термін: 4-5 днів",
        "business": "📊 *Бот для бізнесу*\n\n✅ Функціонал: CRM, аналітика\n💰 Вартість: від 150$\n⏱️ Термін: 5-7 днів",
        "games": "🎮 *Бот з міні-іграми*\n\n✅ Функціонал: Вікторини, рейтинги\n💰 Вартість: від 120$\n⏱️ Термін: 4-6 днів",
        "ai": "🧠 *Бот зі ШІ*\n\n✅ Функціонал: ChatGPT, база знань\n💰 Вартість: від 200$\n⏱️ Термін: 7-10 днів"
    }
    
    example_text = examples.get(example_type, "Приклад буде додано найближчим часом")
    
    detail_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Замовити такого бота", callback_data=f"order_{example_type}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_examples")]
    ])
    
    await callback.message.edit_text(text=example_text, reply_markup=detail_kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_examples")
async def back_to_examples(callback: types.CallbackQuery):
    examples_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Бот для заявок", callback_data="example_orders")],
        [InlineKeyboardButton(text="🛍️ Бот для продажів", callback_data="example_sales")],
        [InlineKeyboardButton(text="📊 Бот для бізнесу", callback_data="example_business")],
        [InlineKeyboardButton(text="🎮 Бот з міні-іграми", callback_data="example_games")],
        [InlineKeyboardButton(text="🧠 Бот зі ШІ", callback_data="example_ai")],
        [InlineKeyboardButton(text="📁 Всі роботи в портфоліо", url=PORTFOLIO_LINK)],
        [InlineKeyboardButton(text="📩 Замовити такого ж бота", callback_data="order_same")]
    ])
    
    await callback.message.edit_text(
        text="💼 *Мої роботи та портфоліо*\n\n👇 *Оберіть категорію:*",
        reply_markup=examples_kb,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(F.text == "💰 Ціни")
async def price(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer(
            "⚠️ *У вас є активне замовлення!*\n\nСпочатку завершіть або скасуйте поточне замовлення.",
            parse_mode="Markdown"
        )
        return
    
    price_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Зв'язатися", url=f"https://t.me/{YOUR_USERNAME}")],
        [InlineKeyboardButton(text="🤖 Розрахувати вартість", callback_data="calculate_price")]
    ])
    
    await message.answer(
        "💰 *Прайс-лист*\n\n🔹 Простий бот — 50–70$\n🔹 Середній бот — 90–130$\n🔹 Складний бот — від 200$\n\n💡 *Розрахуйте точну вартість!*",
        reply_markup=price_kb,
        parse_mode="Markdown"
    )

@dp.message(F.text == "🤖 Замовити бота")
async def order_start(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer(
            "⚠️ *У вас вже є активне замовлення!*\n\nНатисніть '❌ Скасувати замовлення'.",
            parse_mode="Markdown"
        )
        return
    
    await state.set_state(OrderBot.name)
    await message.answer(
        "📝 *Створимо бота разом!* 🚀\n\n*Крок 1 з 5:*\nЯк до вас звертатися?\n\n❌ *Скасувати - кнопка нижче*",
        reply_markup=cancel_kb,
        parse_mode="Markdown"
    )

@dp.message(OrderBot.name)
async def get_name(message: types.Message, state: FSMContext):
    if message.text == "❌ Скасувати замовлення":
        await cancel_order(message, state)
        return
    
    if len(message.text) < 2:
        await message.answer("❌ Ім'я занадто коротке. Представтесь:")
        return
    
    await state.update_data(name=message.text)
    await state.set_state(OrderBot.contact)
    await message.answer(
        "*Крок 2 з 5:*\n📱 Залиште контакт для зв'язку (Telegram username):\n\n⬅️ *Повернутись - кнопка нижче*",
        reply_markup=back_kb,
        parse_mode="Markdown"
    )

@dp.message(OrderBot.contact)
async def get_contact(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Повернутись назад":
        await state.set_state(OrderBot.name)
        await message.answer(
            "*Крок 1 з 5:*\nЯк до вас звертатися?",
            reply_markup=cancel_kb,
            parse_mode="Markdown"
        )
        return
    
    await state.update_data(contact=message.text)
    await state.set_state(OrderBot.description)
    await message.answer(
        "*Крок 3 з 5:*\n🤖 Опишіть, якого бота ви хочете:\n\n• Для чого потрібен\n• Який функціонал\n• Особливості\n\n⬅️ *Повернутись - кнопка нижче*",
        reply_markup=back_kb,
        parse_mode="Markdown"
    )

@dp.message(OrderBot.description)
async def get_description(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Повернутись назад":
        await state.set_state(OrderBot.contact)
        await message.answer(
            "*Крок 2 з 5:*\n📱 Залиште контакт для зв'язку:",
            reply_markup=back_kb,
            parse_mode="Markdown"
        )
        return
    
    if len(message.text) < 10:
        await message.answer("❌ Опишіть проект детальніше (мінімум 10 символів):")
        return
    
    await state.update_data(description=message.text)
    await state.set_state(OrderBot.budget)
    
    budget_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="50-100$", callback_data="budget_low")],
        [InlineKeyboardButton(text="100-200$", callback_data="budget_medium")],
        [InlineKeyboardButton(text="200-300$", callback_data="budget_high")],
        [InlineKeyboardButton(text="300-500$", callback_data="budget_pro")],
        [InlineKeyboardButton(text="500$+", callback_data="budget_enterprise")]
    ])
    
    await message.answer(
        "*Крок 4 з 5:*\n💰 Який у вас бюджет?\n\n👇 *Оберіть варіант:*",
        reply_markup=budget_kb,
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data.startswith("budget_"))
async def get_budget(callback: types.CallbackQuery, state: FSMContext):
    budgets = {
        "low": "50-100$", "medium": "100-200$", "high": "200-300$",
        "pro": "300-500$", "enterprise": "500$+"
    }
    budget_key = callback.data.split("_")[1]
    await state.update_data(budget=budgets.get(budget_key, "Не вказано"))
    await state.set_state(OrderBot.confirm)
    
    data = await state.get_data()
    confirm_text = (
        "📋 *Перевірте дані:*\n\n"
        f"👤 Ім'я: {data['name']}\n"
        f"📱 Контакт: {data['contact']}\n"
        f"💰 Бюджет: {data['budget']}\n\n"
        f"📝 Опис:\n{data['description']}\n\n"
        "✅ *Все правильно?*"
    )
    
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Так, відправити", callback_data="confirm_yes")],
        [InlineKeyboardButton(text="❌ Ні, скасувати", callback_data="confirm_no")]
    ])
    
    await callback.message.edit_text(confirm_text, reply_markup=confirm_kb, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "confirm_yes")
async def send_order(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_id = db.save_order(callback.from_user.id, data)
    
    admin_text = (
        f"🔥 *НОВА ЗАЯВКА #{order_id}!*\n\n"
        f"👤 Ім'я: {data['name']}\n"
        f"📱 Контакт: {data['contact']}\n"
        f"💰 Бюджет: {data['budget']}\n"
        f"🆔 User ID: {callback.from_user.id}\n"
        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"📝 Опис:\n{data['description']}"
    )
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написати клієнту", url=f"tg://user?id={callback.from_user.id}")]
    ])
    
    try:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="Markdown", reply_markup=admin_kb)
        
        await callback.message.edit_text(
            "✅ *Заявку відправлено!*\n\n"
            f"🎉 Дякую, {data['name']}!\n\n"
            "⏳ Я зв'яжуся з вами найближчим часом.\n\n"
            "💡 Перегляньте портфоліо:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📁 Портфоліо", url=PORTFOLIO_LINK)]
            ]),
            parse_mode="Markdown"
        )
        
        logger.info(f"Заявка #{order_id} відправлена")
        
    except TelegramAPIError as e:
        logger.error(f"Помилка: {e}")
        await callback.message.edit_text(
            f"❌ Помилка. Напишіть напряму: @{YOUR_USERNAME}",
            parse_mode="Markdown"
        )
    
    await state.clear()
    await callback.answer()

@dp.callback_query(lambda c: c.data == "confirm_no")
async def cancel_order_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ *Замовлення скасовано.*", parse_mode="Markdown")
    await state.clear()
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("order_") or c.data == "order_same" or c.data == "calculate_price")
async def order_from_example(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await callback.message.answer("⚠️ *У вас вже є активне замовлення!*", parse_mode="Markdown")
        await callback.answer()
        return
    
    await callback.message.answer("📝 *Чудово! Почнімо зі знайомства 👇*", parse_mode="Markdown")
    await order_start(callback.message, state)
    await callback.answer()

@dp.message(F.text == "ℹ️ Про нас")
async def about(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer("⚠️ *У вас є активне замовлення!*", parse_mode="Markdown")
        return
    
    await message.answer(
        "🌟 *Про розробника*\n\nПривіт! Я професійний розробник Telegram-ботів.\n\n*Досвід:* 1 рік\n*Проектів:* 15+\n\n✅ Індивідуальний підхід\n✅ Безкоштовна консультація\n✅ Техпідтримка 24/7",
        parse_mode="Markdown",
        reply_markup=back_kb
    )

@dp.message(F.text == "📞 Контакти")
async def contact(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer("⚠️ *У вас є активне замовлення!*", parse_mode="Markdown")
        return
    
    contact_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написати", url=f"https://t.me/{YOUR_USERNAME}")]
    ])
    
    await message.answer(
        f"📞 *Зв'язатись:* @{YOUR_USERNAME}\n\n🚀 Пишіть!",
        parse_mode="Markdown",
        reply_markup=contact_kb
    )

@dp.message(F.text == "📊 Мої замовлення")
async def my_orders(message: types.Message):
    orders = db.get_user_orders(message.from_user.id)
    
    if not orders:
        await message.answer("📭 *У вас ще немає замовлень*", parse_mode="Markdown")
        return
    
    orders_text = "📊 *МОЇ ЗАМОВЛЕННЯ*\n\n"
    for order in orders[:5]:
        orders_text += f"📝 #{order['id']} | {order['budget']} | {order['status']}\n📅 {order['created_at']}\n\n"
    
    await message.answer(orders_text, parse_mode="Markdown")

@dp.message(F.text == "⬅️ Повернутись назад")
async def go_back(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await cancel_order(message, state)
    else:
        await message.answer("⬅️ Головне меню", reply_markup=main_kb)

@dp.message()
async def unknown(message: types.Message):
    if message.text not in ["🤖 Замовити бота", "💼 Приклади робіт", "💰 Ціни", 
                           "ℹ️ Про нас", "📞 Контакти", "⬅️ Повернутись назад", 
                           "❌ Скасувати замовлення", "📊 Мої замовлення"]:
        await message.answer("❓ Невідома команда. Скористайтесь кнопками 👇", reply_markup=main_kb)

async def main():
    try:
        logger.info("🚀 Бот запускається...")
        print("✅ Бот успішно запущено!")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Помилка: {e}")
        print(f"❌ Помилка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
