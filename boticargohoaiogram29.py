import sys
import logging
import asyncio
import asyncpg
import redis.asyncio as redis
import re
import json
import io
import csv
from aiogram.types import InputMediaPhoto, InputMediaDocument
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import FSInputFile
from datetime import datetime
from aiogram.utils.chat_action import ChatActionSender
from aiogram import Router, BaseMiddleware
from aiogram.types import BufferedInputFile
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardRemove,
    Message,
    CallbackQuery,
    MenuButtonCommands
)
from aiogram.utils.i18n import I18n
from aiogram.utils.i18n.middleware import I18nMiddleware
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.redis import RedisStorage
from typing import Union, Any, Awaitable, Callable, Dict

TOKEN = '8579218072:AAGaw_yLW9zYWcR27jB0iF11V2HxMlNVj3A' #'8101685199:AAHKVVZILrkrjdJEUa8ziZnjbAwoyBUbae4'  #'8579218072:AAGaw_yLW9zYWcR27jB0iF11V2HxMlNVj3A'
ADMIN_ID = 5887184095 #8057417894  #5887184095  #8057417894 #8477309360 #5887184095
CHANNEL_USERNAME = "@paighomcarg0"

router = Router()

output = io.StringIO()
writer = csv.writer(output, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
writer.writerow(['Треккод', 'Соҳиби бор', 'Статус', 'Таърихи ҳаракат'])

pg_pool = None
redis_db = None

i18n = I18n(path='locales_тарчумаботикаргохо', default_locale='tj', domain='bot')
_ = i18n.gettext
class TypingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any]
    ) -> Any:
        chat_id = None
        if isinstance(event, Message):
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery):
            chat_id = event.message.chat.id

        if chat_id:
            async with ChatActionSender.typing(bot=data['bot'], chat_id=chat_id):
                return await handler(event, data)
        return await handler(event, data)
# Сохтани Middleware
class LoggerMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Ин ҷо ID-ро чоп мекунем (пеш аз иҷрои функсияҳо)
        print(f"--- Ҳодисаи нав ---")
        print(f"ID: {event.from_user.id}")
        print(f"Ном: {event.from_user.first_name}")
        if event.text:
            print(f"Матн: {event.text}")
            
        return await handler(event, data)

# Дар қисми main() инро ба Dispatcher пайваст кунед:
# dp.message.outer_middleware(LoggerMiddleware())

#
class RegState(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_surname = State()
    waiting_for_address = State()
    waiting_for_edit = State()
class AdminTrackState(StatesGroup):
    waiting_for_status = State()    # Интихоби статус
    waiting_for_track_code = State() # Треккод
    waiting_for_name = State()       # Ном дар бор
    waiting_for_phone = State()      # Тел дар бор
class AdminSearchState(StatesGroup):
    waiting_for_track_query = State()
class AdminSearch(StatesGroup):
    waiting_for_query = State()  # Ҳолати интизори ном ё телефон

class ЗабонMiddleware(I18nMiddleware):
    async def get_locale(self, event, data):
        user = data.get('event_from_user')
        if user:
            lang = await redis_db.get(f"user:{user.id}:lang")
            return lang or self.i18n.default_locale
        return self.i18n.default_locale

storage = RedisStorage.from_url("redis://127.0.0.1:6379")
bot = Bot(token=TOKEN) # Барои FSM мо Redis-ро истифода мебарем
dp = Dispatcher(storage=storage)
###########################ба копбарон пайём равон кардан
class AdminBroadcast(StatesGroup):
    waiting_for_message = State()
class FeedbackState(StatesGroup):
    waiting_for_feedback = State()
@dp.message(RegState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    pattern = r"^[A-Za-z]{3,13}$"
    if not re.match(pattern, name):
        await message.answer(
            _("❌ Формати ном нодуруст аст.\n"
              "Лутфан номро бо <b>ҳарфҳои англисӣ</b> ворид кунед (масалан: <b>Damirjon</b>)"),
            parse_mode="HTML"
        )
        return
    await state.update_data(temp_name=name)
    await message.answer(_("Ташаккур! Ҳоло насабатонро ворид кунед (масалан: <b>Valiev</b>):"), parse_mode="HTML")
    await state.set_state(RegState.waiting_for_surname)
@dp.message(RegState.waiting_for_surname)
async def process_surname(message: types.Message, state: FSMContext):
    surname = message.text.strip()
    pattern = r"^[A-Za-z]{3,13}$"
    if not re.match(pattern, surname):
        await message.answer(
            _("❌ Формати насаб нодуруст аст.\n"
              "Лутфан насабро бо <b>ҳарфҳои англисӣ</b> ворид кунед (масалан: <b>Valiev</b>)"),
            parse_mode="HTML"
        )
        return
    data = await state.get_data()
    first_name = data.get("temp_name")
    full_name = f"{first_name} {surname}"
    await state.update_data(full_name=full_name)
    await state.update_data(temp_name=None) # Тоза кардани маълумоти муваққатӣ
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=_("Фиристодани рақам 📱"), request_contact=True)]],
        resize_keyboard=True
    )
    await message.answer(_("Тугмаи поёниро зер карда рақами телефонатонро фиристед ё онро хати нависед!:"), reply_markup=keyboard)
    await state.set_state(RegState.waiting_for_phone)

@dp.message(RegState.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text
    cleaned_phone = re.sub(r'[^0-9+]', '', phone)
    final_phone = ""
    if cleaned_phone.startswith("992") and len(cleaned_phone) == 12:
        final_phone = "+" + cleaned_phone
    elif cleaned_phone.startswith("+992") and len(cleaned_phone) == 13:
        final_phone = cleaned_phone
    elif len(cleaned_phone) == 9 and cleaned_phone.isdigit():
        final_phone = "+992" + cleaned_phone
    else:
        await message.answer(
            _("❌ Формати рақам нодуруст аст.\n"
              "Лутфан рақамро бо формати <b>+992XXXXXXXXX</b> ё бе <b>+992</b>ворид кунед."),
            parse_mode="HTML"
        )
        return # Функсияро тамом мекунем, то рақами нодуруст сабт нашавад
    await state.update_data(phone=final_phone)
    await message.answer(_("Суроғаи худро ворид кунед (масалан: ш. Душанбе):"), reply_markup=ReplyKeyboardRemove())
    await state.set_state(RegState.waiting_for_address)
@dp.message(RegState.waiting_for_address)
async def process_address(message: types.Message, state: FSMContext):
    address = message.text.strip()
    words = address.split()
    word_count = len(words)
    errors = [] # Рӯйхати хатогиҳо
    if word_count < 2 or word_count > 6:
        errors.append(_("❌ Формати суроға нодуруст аст \nФормати дуруст <b>Кӯчаи Айни 56</b> ё <b>Шаҳри Душанбе кӯчаи * </b>"))
    if any(len(word) > 15 for word in words):
        errors.append(_("❌ Формати суроға нодуруст аст \nФормати дуруст <b>Кӯчаи Айни 56</b> ё <b>Шаҳри Душанбе кӯчаи * </b>"))
    if sum(c.isdigit() for c in address) > 3:
        errors.append(_("❌ Формати суроға нодуруст аст \nФормати дуруст <b>Кӯчаи Айни 56</b> ё <b>Шаҳри Душанбе кӯчаи * </b>"))
    if errors:
        final_error_message = _("<b>Хатогиҳо дар суроға:</b>\n\n") + "\n".join(errors)
        await message.answer(final_error_message, parse_mode="HTML")
        return
    data = await state.get_data()
    user_id = message.from_user.id
    
    async with pg_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, full_name, phone_number, address)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE SET full_name=$2, phone_number=$3, address=$4
        """, user_id, data['full_name'], data['phone'], address)
    username = message.from_user.username
    if username:
        nickname = f"@{username}"
    else:
        nickname = message.from_user.first_name

    await state.clear()
    await message.answer(_(f"Табрик <b>{nickname}</b>! Шумо бомуваффақият сабти ном шудед ✅"), parse_mode="HTML")
    await асоси(message)
async def тафтиш_ва_пурсиши_обуна(пайём: Union[types.Message, types.CallbackQuery], send_message: bool = True) -> bool:
    user_id = пайём.from_user.id  # Муайян кардани user_id
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ("member", "administrator", "creator"):
            return True
    except:
        pass
    if send_message:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=_("📢 Обуна шудан"), url=f"https://t.me/{CHANNEL_USERNAME[1:]}")],
            [InlineKeyboardButton(text=_("✅ Ман обуна шудам"), callback_data="check_sub")]
        ])
        msg_obj = пайём if isinstance(пайём, types.Message) else пайём.message # Объекти паёмро муайян мекунем
        temp_msg = await msg_obj.answer(
            _(" Тафтиши обуна..."), # 1. Фиристодани паёми муваққатӣ барои тоза кардани ReplyKeyboard (тугмаҳои забон)
            reply_markup=types.ReplyKeyboardRemove()
        )
        await temp_msg.delete() # 2. Нест кардани паёми муваққатӣ (то чат тоза монад)
        await msg_obj.answer( # 3. Фиристодани паёми асосӣ бо тугмаҳои Inline
            _("❌ Аввал ба канал обуна шавед:"), 
            reply_markup=keyboard
        )
    return False
@dp.message(Command("start"))
async def оғоз(паём_ё_колл: Union[types.Message, types.CallbackQuery], state: FSMContext = None):
    if isinstance(паём_ё_колл, types.CallbackQuery):  # Муайян мекунем, ки ин паём аст ё колбэк
        пайём = паём_ё_колл.message
        user = паём_ё_колл.from_user
    else:
        пайём = паём_ё_колл
        user = паём_ё_колл.from_user
    user_id = user.id
    if user_id == ADMIN_ID:
        await open_admin_panel(пайём)
        return
    lang = await redis_db.get(f"user:{user_id}:lang")
    if not lang:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text='Тоҷикӣ')]], #, KeyboardButton(text='Русский'), KeyboardButton(text='English')]],
            resize_keyboard=True
        )
        await пайём.answer("Забонро интихоб кунед / Выберите язык / Choose language:", reply_markup=keyboard)
        return
    i18n.ctx_locale.set(lang)
    if user_id != ADMIN_ID:
        if not await тафтиш_ва_пурсиши_обуна(паём_ё_колл):   # Дар ин ҷо бояд эҳтиёт бошед, ки тафтиш_ва_пурсиши_обуна бо ҳарду намуд кор кунад
            return
        async with pg_pool.acquire() as conn:
            db_user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            if not db_user:
                username = паём_ё_колл.from_user.username
                if username:
                    nickname = f"@{username}"
                else:
                    nickname = паём_ё_колл.from_user.first_name
                await пайём.answer(_(f"Хуш омадед <b>{nickname}</b>! Лутфан номатонро бо формати <b>Damirjon</b> бо ҳарфҳои англисӣ ворид кунед:"), reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
                await state.set_state(RegState.waiting_for_name)
                return
    await асоси(пайём)
    await set_main_menu(bot)
    await state.clear()

async def set_main_menu(bot: Bot):
    menu_button = MenuButtonCommands()
    await bot.set_chat_menu_button(menu_button=menu_button)
    await bot.set_my_commands([
        types.BotCommand(command="start", description="оғоз"),
    ])
# await set_main_menu(bot)

async def асоси(пайём: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=_('Суроға')), KeyboardButton(text=_('Маълумот оиди карго'))],
        [KeyboardButton(text=_('Нархнома')), KeyboardButton(text=_('Мӯҳлати даставка')), KeyboardButton(text=_('Молҳои манъшуда'))],
        [KeyboardButton(text=_('Пайгирии треккод')), KeyboardButton(text=_('Ҳуҷраи инфироди(утоқи шахси)'))],
        [KeyboardButton(text=_('Омӯзиши ройгон')), KeyboardButton(text=_('Ҳисоб кардани нархи бор'))],
        [KeyboardButton(text=_('Иваз кардани забон/Chouse language/ Изменить язык'))]
    ], resize_keyboard=True)
    await пайём.answer(_('Менюи асосӣ:'), reply_markup=kb)
    await set_main_menu(bot)
#хабаррасон
async def notify_user_delivery(bot, user_id, track_code: str):
    if not user_id:
        return

    try:
        # Мо аввал вақтро мегирем, то хатогӣ нашавад
        now = datetime.now()
        date_str = now.strftime('%d.%m.%Y %H:%M')
        photo_path = "succes.jpg" 
        photo = FSInputFile(photo_path)

        # 2. Сохтани матн барои тавсифи акс (caption)
        caption_text = (
            f"🔔 <b>ХАБАРНОМАИ НАВ</b>\n\n"
            f"✅ <b>Муштарии азиз, бори шумо супорида шуд!</b>\n"
            f"📦 <b>Треккод:</b> <code>{track_code}</code>\n\n"
            f"Ташаккур, ки аз хадамоти мо истифода мебаред! 😊"
        )

        await bot.send_message(
            chat_id=int(user_id),
            text=caption_text,
            parse_mode="HTML",
            disable_notification=False # Барои бо садо рафтан
        )
        print(f"DEBUG: Акс ба корбар {user_id} фиристода шуд.")

    except Exception as e:
        print(f"DEBUG: Хатогӣ ҳангоми фиристодани акс: {e}")

#хабаррасон
async def open_admin_panel(пайём: types.Message):
    # Санҷиши Админ дар оғоз
    if пайём.from_user.id != ADMIN_ID:
        return # Агар Админ набошад, функсияро тамом мекунем

    # Эҷоди клавиатура (акнун kb ҳамеша вуҷуд дорад)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📦 Қабули бор (Илова)")],
        [KeyboardButton(text="Маълумоти ботро Excel кардан")],
        [KeyboardButton(text="Ба корбарон пайём равон кардан")],
        [KeyboardButton(text="Ҷустуҷӯ бо ном, рақами телефон, id телеграм ва ё треккод")]
    ], resize_keyboard=True)
    username = пайём.from_user.username
    if username:
        nickname = f"@{username}"
    else:
        nickname = пайём.from_user.first_name 
    await пайём.answer(f"👑 Хуш омадед ба панели идоракунӣ, Админ <b>{nickname}</b>!", reply_markup=kb, parse_mode="HTML")

async def get_admin_order_counts(pg_pool):
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT status, COUNT(*) as count 
            FROM tracks 
            GROUP BY status
        """)
        return {row['status']: row['count'] for row in rows}
#
@dp.message(F.text == "📦 Қабули бор (Илова)")
async def admin_start_receive(message: types.Message, state: FSMContext, pg_pool): # pg_pool-ро илова кардем
    if message.from_user.id != ADMIN_ID: return
    
    # 1. Ҳисоб кардани миқдори ҳамаи борҳо аз база
    counts = await get_admin_order_counts(pg_pool) # Ин функсияро дар поён менависам

    kb_reply_main = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⬅️ Ба менюи асосӣ")]
        ],
        resize_keyboard=True
    )
    await message.answer("Шумо ба менюи админ ворид шудед.", reply_markup=kb_reply_main)

    # Функсияи ёрирасон барои иловаи рақамҳо ба тугма
    def fmt(label, key):
        count = counts.get(key, 0)
        return f"{label} ({count})" if count > 0 else label

    # 2. Сохтани клавиатура бо миқдори борҳо
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=fmt("🇨🇳 Сканер", "Дар анбор"), callback_data="st:Дар анбор")],
        [InlineKeyboardButton(text=fmt("🚚 Дар рох", "Дар роҳ"), callback_data="st:Дар роҳ")],
        [InlineKeyboardButton(text=fmt("🇹🇯 Дар Душанбе", "Душанбе"), callback_data="st:Душанбе")],
        [InlineKeyboardButton(text=fmt("✅ Супорида шуд", "Супорида шуд"), callback_data="st:Супорида шуд")],
        [InlineKeyboardButton(text=fmt("📦 Молхои беном", "Беном"), callback_data="st:Беном")],
        [InlineKeyboardButton(text=fmt("🚨 Молхои мушкилидошта", "Мушкилдор"), callback_data="st:Мушкилдор")]
    ])
    
    try:
        await message.delete()
    except:
        pass # Агар паём аллакай нест бошад, хатогӣ надиҳад

    await message.answer("Ҳолати борҳоро интихоб кунед:", reply_markup=kb)
    await state.set_state(AdminTrackState.waiting_for_status)

# --- ИН ФУНКСИЯРО ДАР БОЛОИ ФАЙЛ Ё ДАР ҶОИ МУНОСИБ МОНЕД ---
async def get_admin_order_counts(pg_pool):
    async with pg_pool.acquire() as conn:
        # Ин дархост ҳам аз рӯи статус ва ҳам аз рӯи категория (барои 'Беном') мешуморад
        rows = await conn.fetch("""
            SELECT status as key, COUNT(*) as count FROM tracks GROUP BY status
            UNION ALL
            SELECT category as key, COUNT(*) as count FROM tracks WHERE category = 'Беном' GROUP BY category
        """)
        return {row['key']: row['count'] for row in rows}
@dp.message(F.text == "Ҷустуҷӯ бо ном, рақами телефон, id телеграм ва ё треккод")
async def search_options_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Ҷустуҷӯ бо треккод", callback_data="search_by:track")],
        [InlineKeyboardButton(text="👤 Ҷустуҷӯ бо ному телефон", callback_data="search_by:name_phone")]
    ])
    await message.answer("Усули ҷустуҷӯро интихоб кунед:", reply_markup=kb)
@dp.callback_query(F.data == "ба_ҷустуҷӯ")
async def тугмаи_ҷустуҷӯ(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID: return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Ҷустуҷӯ бо треккод", callback_data="search_by:track")],
        [InlineKeyboardButton(text="👤 Ҷустуҷӯ бо ному телефон", callback_data="search_by:name_phone")]
    ])
    await call.message.edit_text("Усули ҷустуҷӯро интихоб кунед:", reply_markup=kb)
@dp.callback_query(F.data == "search_by:track")
async def start_track_search(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("📝 Қисми треккодро ворид кунед (масалан: 'TJ' ё '1234'):")
    await state.set_state(AdminSearchState.waiting_for_track_query)
    await call.answer()

@dp.message(AdminSearchState.waiting_for_track_query)
async def process_track_search(message: types.Message, pg_pool, state: FSMContext):
    query = message.text.strip()
    
    async with pg_pool.acquire() as conn:
        # Ҷустуҷӯи 10 треккоди ба матн монанд
        rows = await conn.fetch("""
            SELECT track_code FROM tracks 
            WHERE track_code LIKE $1 
            LIMIT 10
        """, f"%{query}%")

    if not rows:
        await message.answer("❌ Ягон треккод ёфт нашуд. Боз кӯшиш кунед:")
        return

    builder = InlineKeyboardBuilder()
    for row in rows:
        track = row['track_code']
        builder.row(InlineKeyboardButton(text=f"📦 {track}", callback_data=f"view_track:{track}"))
    
    builder.row(InlineKeyboardButton(text="⬅️ Баргашт", callback_data="ба_ҷустуҷӯ"))
    
    await message.answer(f"🔍 Натиҷаҳои ҷустуҷӯ барои '{query}':", reply_markup=builder.as_markup())
@dp.callback_query(F.data.startswith("view_track:"))
async def show_full_track_info(call: types.CallbackQuery, pg_pool):
    track_code = call.data.split(":")[1]
    
    async with pg_pool.acquire() as conn:
        # 1. Гирифтани маълумот аз ҷадвали tracks
        # Мо инчунин ҳисоб мекунем, ки бо ин ID ва ин Ном чанд бори дигар ҳаст
        row = await conn.fetchrow("""
            SELECT *, 
                (SELECT COUNT(*) FROM tracks WHERE user_id = t.user_id AND user_id IS NOT NULL) as user_total_orders,
                (SELECT COUNT(*) FROM tracks WHERE admin_owner_name = t.admin_owner_name AND admin_owner_phone = t.admin_owner_phone AND admin_owner_name IS NOT NULL) as admin_total_orders
            FROM tracks t 
            WHERE track_code = $1
        """, track_code)

        if not row:
            await call.answer("Маълумот ёфт нашуд.")
            return

        # 2. Гирифтани таърихи статусҳо
        history_rows = await conn.fetch("""
            SELECT new_status, changed_at 
            FROM track_history 
            WHERE track_code = $1 
            ORDER BY id ASC
        """, track_code)

    # Омода кардани матни таърихи статусҳо
    history_text = ""
    if history_rows:
        for i, h in enumerate(history_rows, 1):
            date_str = h['changed_at'].strftime('%d.%m.%Y %H:%M') if h['changed_at'] else '---'
            history_text += f"   {i}. <b>{h['new_status']}</b> — {date_str}\n"
    else:
        history_text = "   Таърих мавҷуд нест.\n"

    # Сохтани блоки ниҳоии маълумот
    info = (
        f"📊<b>МАЪЛУМОТИ ПУРРА ДАР БОРАИ БОР</b>\n"
        f"📦<b>Треккод:</b> <code>{row['track_code']}</code>\n"
        f"🏷 <b>Категория:</b> {row['category'] or '---'}\n"
        f"👤<b>Маълумоти борҷома:</b>\n"
        f"   ▪️ Ном: <code>{row['admin_owner_name'] or '---'}</code>\n"
        f"   ▪️ Тел: <code>{row['admin_owner_phone'] or '---'}</code>\n"
        f"📦<b>Фармоишҳои бо ном/номер:</b> <code>{row['admin_total_orders'] or 0} адад </code>\n"
        f"📱<b>Маълумоти корбар(телеграм):</b>\n"
        f"   ▪️ Ном: <code>{row['user_full_name'] or '---'}</code>\n"
        f"   ▪️ ID: <code>{row['user_id'] or 'Напайваст'}</code>\n"
        f"   ▪️ Тел: <code>{row['user_phone'] or '---'}</code>\n"
        f"    📍Суроға: <code>{row['user_address'] or '---'}</code>\n"
        f"🛍 <b>Треккодҳои Утоқи шахси:</b> {row['user_total_orders'] or 0}\n"
        f"🕒<b>Таърихи статусҳо:</b>\n"
        f"     {history_text}"
    )
    builder = InlineKeyboardBuilder()
    if row['admin_owner_phone']:
        builder.row(InlineKeyboardButton(
            text="📞 Борҳои бо ин номер алоқаманд", 
            callback_data=f"list_by_phone:{row['admin_owner_phone']}"
        ))
    if row['user_id']:
        builder.row(InlineKeyboardButton(
            text="🆔 Борҳои бо ин ID алоқаманд", 
            callback_data=f"list_by_id:{row['user_id']}"
        ))

    await call.message.answer(info, parse_mode="HTML", reply_markup=builder.as_markup())
    await call.answer()
@dp.callback_query(F.data.startswith("list_by_phone:"))
async def list_by_phone_detailed(call: types.CallbackQuery, pg_pool):
    phone = call.data.split(":")[1]
    
    async with pg_pool.acquire() as conn:
        # Гирифтани ҳамаи маълумот барои ҳар як бори ин номер
        rows = await conn.fetch("""
            SELECT *, 
                (SELECT COUNT(*) FROM tracks WHERE admin_owner_phone = $1) as admin_total_orders,
                (SELECT COUNT(*) FROM tracks WHERE user_id = t.user_id AND user_id IS NOT NULL) as user_total_orders
            FROM tracks t 
            WHERE admin_owner_phone = $1 
            ORDER BY created_at DESC
        """, phone)

    if not rows:
        await call.answer("Борҳо ёфт нашуданд.")
        return

    await call.answer() # Тез ҷавоб додани Telegram

    for row in rows:
        # Гирифтани таърихи статусҳо барои ҳар як бор алоҳида
        async with pg_pool.acquire() as conn:
            history_rows = await conn.fetch("""
                SELECT new_status, changed_at FROM track_history 
                WHERE track_code = $1 ORDER BY id ASC
            """, row['track_code'])

        h_text = ""
        for i, h in enumerate(history_rows, 1):
            d_str = h['changed_at'].strftime('%d.%m.%Y %H:%M') if h['changed_at'] else '---'
            h_text += f"   {i}. <b>{h['new_status']}</b> — {d_str}\n"

        info = (
            f"📍 <b>ҲОЛАТИ ҲОЗИРА: {row['status']}</b>\n"
            f"📦 <b>Треккод:</b> <code>{row['track_code']}</code>\n"
            f"🏷 <b>Категория:</b> {row['category'] or '---'}\n"
            f"👤 <b>Маълумоти борҷома:</b>\n"
            f"   ▪️ Ном: <code>{row['admin_owner_name'] or '---'}</code>\n"
            f"   ▪️ Тел: <code>{row['admin_owner_phone'] or '---'}</code>\n"
            f"📱 <b>Маълумоти Корбар|telegram:\n</b> {row['user_full_name']} (ID: {row['user_id']})\n"
            f"📞 <b>Тел:</b> {row['user_phone']}\n"
            f"🏠 <b>Суроға:</b> {row['user_address'] or '---'}\n"
            f"🕒 <b>Таърихи статусҳо:</b>\n{h_text or 'Таърих нест'}"
        )
        buttons = []
        # Шарти мураккаб: Ҳатман "Дар Душанбе" бошад ВА "Супорида шуд" набошад
        if row['status'] == "Душанбе" and row['status'] != "Супорида шуд":
            buttons.append([InlineKeyboardButton(
                text="✅ Ба 'Супорида шуд' иваз кардан",
                callback_data=f"set_delivered:{row['track_code']}"
            )])
        buttons.append([InlineKeyboardButton(text="⬅️ Ба қафо", callback_data="search_by:track")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await call.message.answer(info, parse_mode="HTML", reply_markup=kb)
@dp.callback_query(F.data.startswith("list_by_id:"))
async def list_by_id_detailed(call: types.CallbackQuery, pg_pool):
    user_id = call.data.split(":")[1]

    async with pg_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT *,
                (SELECT COUNT(*) FROM tracks WHERE user_id = t.user_id) as user_total_orders,
                (SELECT COUNT(*) FROM tracks WHERE admin_owner_name = t.admin_owner_name AND admin_owner_name IS NOT NULL) as admin_total_orders
            FROM tracks t
            WHERE user_id = $1::bigint
            ORDER BY created_at DESC
        """, int(user_id))
    if not rows:
        await call.answer("Борҳои ин корбар ёфт нашуданд.")
        return
    await call.answer()
    for row in rows:
        async with pg_pool.acquire() as conn:
            history_rows = await conn.fetch("""
                SELECT new_status, changed_at FROM track_history
                WHERE track_code = $1 ORDER BY id ASC
            """, row['track_code'])
        h_text = ""
        for i, h in enumerate(history_rows, 1):
            d_str = h['changed_at'].strftime('%d.%m.%Y %H:%M') if h['changed_at'] else '---'
            h_text += f"   {i}. <b>{h['new_status']}</b> — {d_str}\n"
        info = (
            f"📍 <b>ҲОЛАТИ ҲОЗИРА: {row['status']}</b>\n"
            f"📦 <b>Треккод:</b> <code>{row['track_code']}</code>\n"
            f"🏷 <b>Категория:</b> {row['category'] or '---'}\n"
            f"👤 <b>Маълумоти борҷома:</b>\n"
            f"   ▪️ Ном: <code>{row['admin_owner_name'] or '---'}</code>\n"
            f"   ▪️ Тел: <code>{row['admin_owner_phone'] or '---'}</code>\n"
            f"📱 <b>Маълумоти Корбар|telegram:\n</b> {row['user_full_name']} (ID: {row['user_id']})\n"
            f"📞 <b>Тел:</b> {row['user_phone']}\n"
            f"🏠 <b>Суроға:</b> {row['user_address'] or '---'}\n"
            f"🕒 <b>Таърихи статусҳо:</b>\n{h_text or 'Таърих нест'}"
        )
        buttons = []
        if row['status'] == "Душанбе" and row['status'] != "Супорида шуд":
            buttons.append([InlineKeyboardButton(
                text="✅ Ба 'Супорида шуд' иваз кардан", 
                callback_data=f"set_delivered:{row['track_code']}"
            )])
        buttons.append([InlineKeyboardButton(text="⬅️ Ба қафо", callback_data="search_by:track")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await call.message.answer(info, parse_mode="HTML", reply_markup=kb)
        await call.answer()
@dp.callback_query(F.data.startswith("set_delivered:"))
async def process_set_delivered(call: types.CallbackQuery, pg_pool):
    track_code = call.data.split(":")[1]
    async with pg_pool.acquire() as conn:
        await conn.execute("UPDATE tracks SET status = 'Супорида шуд' WHERE track_code = $1", track_code)
        await conn.execute("""
            INSERT INTO track_history (track_code, old_status, new_status, changed_at)
            VALUES ($1, 'Дар Душанбе', 'Супорида шуд', NOW())
        """, track_code)
        row = await conn.fetchrow("SELECT * FROM tracks WHERE track_code = $1", track_code)
        history_rows = await conn.fetch("""
            SELECT new_status, changed_at FROM track_history
            WHERE track_code = $1 ORDER BY id ASC
        """, track_code)
    if row and row['user_id']:
        asyncio.create_task(notify_user_delivery(call.bot, row['user_id'], track_code))
    h_text = ""
    if history_rows:
        for i, h in enumerate(history_rows, 1):
            d_str = h['changed_at'].strftime('%d.%m.%Y %H:%M') if h['changed_at'] else '---'
            h_text += f"   {i}. <b>{h['new_status']}</b> — {d_str}\n"
    new_info = (
        f"📍 <b>ҲОЛАТИ ҲОЗИРА: {row['status']}</b>\n"
        f"📦 <b>Треккод:</b> <code>{row['track_code']}</code>\n"
        f"🏷 <b>Категория:</b> {row['category'] or '---'}\n"
        f"👤 <b>Маълумоти борҷома:</b>\n"
        f"   ▪️ Ном: <code>{row['admin_owner_name'] or '---'}</code>\n"
        f"   ▪️ Тел: <code>{row['admin_owner_phone'] or '---'}</code>\n"
        f"📱 <b>Маълумоти Корбар|telegram:\n</b> {row['user_full_name']} ID: {row['user_id']}\n"
        f"📞 <b>Тел:</b> {row['user_phone']}\n"
        f"🏠 <b>Суроға:</b> {row['user_address'] or '---'}\n"
        f"🕒 <b>Таърихи статусҳо:</b>\n{h_text or 'Таърих нест'}"
    )

    new_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Ба қафо", callback_data="search_by:track")]
    ])

    await call.message.edit_text(text=new_info, parse_mode="HTML", reply_markup=new_kb)
    await call.answer("Статус ба 'Супорида шуд' иваз шуд ва хабарнома равон шуд ✅")
#
@dp.callback_query(F.data == "search_by:name_phone")
async def start_name_search(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    
    await state.set_state(AdminSearch.waiting_for_query)
    await call.message.answer("📝 Ном ё рақами телефонро ворид кунед (пурра ё қисман):")
    await call.answer()
@dp.message(AdminSearch.waiting_for_query)
async def process_name_phone_search(message: types.Message, state: FSMContext, pg_pool):
    if message.from_user.id != ADMIN_ID: return
    
    search_text = message.text.strip()
    words = search_text.split()  # Матни админро ба калимаҳо ҷудо мекунем (мисол: ['ilhom', '992...'])
    
    # Сохтани шарти SQL барои ҳар як калима
    # Мо мегӯем: (ном ё телефон LIKE калимаи 1) AND (ном ё телефон LIKE калимаи 2)
    conditions = []
    params = []
    for i, word in enumerate(words, 1):
        conditions.append(f"(admin_owner_name ILIKE ${i} OR admin_owner_phone ILIKE ${i})")
        params.append(f"%{word}%")

    where_clause = " AND ".join(conditions)
    
    sql_query = f"""
        SELECT admin_owner_name, admin_owner_phone, COUNT(track_code) as track_count
        FROM tracks
        WHERE {where_clause}
        GROUP BY admin_owner_name, admin_owner_phone
        LIMIT 15
    """

    async with pg_pool.acquire() as conn:
        rows = await conn.fetch(sql_query, *params)

    if not rows:
        await message.answer("❌ Бо ин маълумот ҳеҷ чиз ёфт нашуд. \nКӯшиш кунед танҳо ном ё танҳо қисми рақамро нависед.")
        return

    buttons = []
    for row in rows:
        name = row['admin_owner_name'] or "---"
        phone = row['admin_owner_phone'] or "---"
        count = row['track_count']
        btn_text = f"{name} {phone}({count})"
        callback_data = f"show_user_tracks:{phone}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=callback_data)])

    buttons.append([InlineKeyboardButton(text="⬅️ Ба қафо", callback_data="ба_ҷустуҷӯ")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(f"🔍 Натиҷаҳо барои: <i>{search_text}</i>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("show_user_tracks:"))
async def show_specific_user_tracks(call: types.CallbackQuery, pg_pool):
    phone = call.data.split(":")[1]
    
    async with pg_pool.acquire() as conn:
        # 1. Гирифтани ҳамаи борҳои ин корбар
        tracks = await conn.fetch("""
            SELECT * FROM tracks 
            WHERE admin_owner_phone = $1 
            ORDER BY created_at DESC
        """, phone)

        if not tracks:
            await call.answer("Борҳо ёфт нашуданд", show_alert=True)
            return

        # --- ҚИСМИ НАВ: Тафтиши мавҷудияти Telegram ID ва ҳисоби миқдор ---
        connected_user_id = None
        for r in tracks:
            if r['user_id']:
                connected_user_id = r['user_id']
                break
        
        kb_main = None
        if connected_user_id:
            # Ҳисоб кардани ҳамаи борҳои ин ID дар база
            count_id_tracks = await conn.fetchval("""
                SELECT COUNT(*) FROM tracks WHERE user_id = $1
            """, connected_user_id)
            
            # Иловаи миқдор ба матни тугма
            kb_main = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"🆔 Борҳои корбар бо ID ({count_id_tracks} адад)", 
                    callback_data=f"show_id_tracks:{connected_user_id}"
                )]
            ])

        # Фиристодани паёми сарлавҳа бо тугма (агар ID бошад)
        await call.message.answer(
            f"📦 <b>Рӯйхати муфассали борҳои:</b> <code>{phone}</code>", 
            parse_mode="HTML",
            reply_markup=kb_main
        )

        for row in tracks:
            track_code = row['track_code']
            
            # 2. Таърихи статусҳо
            history_rows = await conn.fetch("""
                SELECT old_status, new_status, changed_at 
                FROM track_history 
                WHERE track_code = $1 
                ORDER BY changed_at ASC
            """, track_code)

            history_text = "\n📜 <b>Таърихи статусҳо:</b>\n" + \
                "\n".join([f" ├ {h['changed_at'].strftime('%d.%m %H:%M')}: {h['old_status']} ➔ {h['new_status']}" 
                           for h in history_rows]) if history_rows else "\n📜 <b>Таърих:</b> Ёфт нашуд"

            # 3. Матни паём
            info = (
                f"📍 <b>ҲОЛАТИ КОРӢ: {row['status']}</b>\n"
                f"📦 <b>Треккод:</b> <code>{track_code}</code>\n"
                f"🆔 <b>Telegram ID:</b> <code>{row['user_id'] or '---'}</code>\n"
                f"👤 <b>Соҳиб (Админ):</b> {row['admin_owner_name'] or '---'}\n"
                f"📞 <b>Ном:</b> {row['user_full_name'] or '---'}\n"
                f"🏷 <b>Категория:</b> {row['category'] or '---'}\n"
                f"{history_text}\n"
                f"──────────────────"
            )
            
            kb_item = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ Идора", callback_data=f"search_by:track:{track_code}")]
            ])
            
            await call.message.answer(info, parse_mode="HTML", reply_markup=kb_item)

    await call.answer()

@dp.callback_query(F.data.startswith("show_id_tracks:"))
async def show_id_tracks_handler(call: types.CallbackQuery, pg_pool):
    user_id_raw = call.data.split(":")[1]
    if not user_id_raw or user_id_raw == 'None':
        await call.answer("ID барои ин корбар мавҷуд нест", show_alert=True)
        return
        
    user_id = int(user_id_raw)
    
    async with pg_pool.acquire() as conn:
        # 1. Аввал ҳамаи борҳоеро, ки бо ин ID пайвастанд, мегирем
        id_tracks = await conn.fetch("""
            SELECT * FROM tracks 
            WHERE user_id = $1 
            ORDER BY created_at DESC
        """, user_id)
        
        if not id_tracks:
            await call.answer("Борҳо бо ин ID ёфт нашуданд", show_alert=True)
            return

        # 2. Таърихи ҳамаи ин треккодҳоро дар як вақт мегирем (барои суръат)
        # Мо рӯйхати треккодҳоро месозем
        track_codes = [r['track_code'] for r in id_tracks]
        
        history_data = await conn.fetch("""
            SELECT track_code, old_status, new_status, changed_at 
            FROM track_history 
            WHERE track_code = ANY($1)
            ORDER BY changed_at ASC
        """, track_codes)

    # ДАР ИНҶО ПАЙВАСТШАВӢ БО БАЗА БАСТА ШУД. Акнун маълумотро коркард мекунем.

    # Гурӯҳбандии таърих барои ҳар як треккод
    histories_map = {}
    for h in history_data:
        t_code = h['track_code']
        if t_code not in histories_map:
            histories_map[t_code] = []
        histories_map[t_code].append(h)

    # 3. Чоп кардани ҳар як паём бо маълумоти пурра
    await call.message.answer(f"👤 <b>Ҳамаи борҳои пайваст ба ID:</b> <code>{user_id}</code>")

    for row in id_tracks:
        track_code = row['track_code']
        h_rows = histories_map.get(track_code, [])
        
        # Сохтани матни таърихи статусҳо
        if h_rows:
            history_text = "\n📜 <b>Таърихи статусҳо:</b>\n" + \
                "\n".join([f" ├ {h['changed_at'].strftime('%d.%m %H:%M')}: {h['old_status']} ➔ {h['new_status']}" 
                           for h in h_rows])
        else:
            history_text = "\n📜 <b>Таърих:</b> Ёфт нашуд"

        # Сохтани матни паём (ба мисли намунаи шумо)
        info = (
            f"📍 <b>ҲОЛАТИ КОРӢ: {row['status']}</b>\n"
            f"📦 <b>Треккод:</b> <code>{track_code}</code>\n"
            f"🆔 <b>Telegram ID:</b> <code>{row['user_id'] or '---'}</code>\n"
            f"👤 <b>Соҳиб (Админ):</b> {row['admin_owner_name'] or '---'}\n"
            f"📞 <b>Тел (Админ):</b> {row['admin_owner_phone'] or '---'}\n"
            f"👤 <b>Номи корбар:</b> {row['user_full_name'] or '---'}\n"
            f"📞 <b>Тел. корбар:</b> {row['user_phone'] or '---'}\n"
            f"🏷 <b>Категория:</b> {row['category'] or '---'}\n"
            f"🏠 <b>Суроға:</b> {row['user_address'] or '---'}\n"
            f"{history_text}\n"
            f"──────────────────"
        )
        
        kb_item = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Идора", callback_data=f"search_by:track:{track_code}")]
        ])
        
        await call.message.answer(info, parse_mode="HTML", reply_markup=kb_item)
    
    await call.answer()


#
#
#
#
@dp.message(StateFilter("*"), lambda m: m.text == "⬅️ Ба менюи асосӣ")
async def back_to_main_menu(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        current_state = await state.get_state()
        if current_state is not None:
            await state.clear()
            await open_admin_panel(message)
        else:
            await open_admin_panel(message)
@dp.callback_query(F.data.startswith("st:"))
async def process_status_choice(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    chosen_status = call.data.split(":")[1]
    if chosen_status == "Беном":
        async with pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT track_code, status, TO_CHAR(created_at, 'DD.MM.YYYY') as date 
                FROM tracks WHERE category = 'Беном' ORDER BY created_at DESC LIMIT 50
            """)
        kb_back = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Ба ақиб", callback_data="bulk:back_to_statuses")] ])
        if not rows:
            await call.message.edit_text("📭 Молҳои беном ёфт нашуданд.", reply_markup=kb_back)
        else:
            text = "📦 <b>Рӯйхати молҳои беном:</b>\n\n"
            for i, row in enumerate(rows, 1):
                text += f"{i}. <code>{row['track_code']}</code> | {row['date']} | {row['status']}\n"
            await call.message.edit_text(text, reply_markup=kb_back, parse_mode="HTML")
        await call.answer()
        return
    await state.update_data(status=chosen_status)
    await state.set_state(AdminTrackState.waiting_for_status)
    buttons = []
    # Агар статус ХИТОЙ бошад
    if chosen_status == "Дар анбор" or chosen_status == "Мушкилдор" or chosen_status == "Душанбе" or chosen_status == "Супорида шуд":
        buttons.append([InlineKeyboardButton(text="📝 Иловаи рӯйхати нав", callback_data="bulk:list")])
        buttons.append([InlineKeyboardButton(text=f"🔍 Дидани рӯйхати {chosen_status}", callback_data="bulk:view_current")])
    # Барои дигар статусҳо (Равон шуд, Анбор ва ғайра)
    else:
        buttons.append([InlineKeyboardButton(text="📅 Иваз бо санаи қабул", callback_data="bulk:date")])
        buttons.append([InlineKeyboardButton(text="📝 Иловаи рӯйхати нав", callback_data="bulk:list")])
        buttons.append([InlineKeyboardButton(text=f"🔍 Дидани рӯйхати {chosen_status}", callback_data="bulk:view_current")])
    buttons.append([InlineKeyboardButton(text="⬅️ Ба ақиб", callback_data="bulk:back_to_statuses")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await call.message.edit_text(
        f"Ҳолати интихобшуда: <b>{chosen_status}</b>\n\n"
        "Амалиёти лозимиро интихоб кунед:",
        reply_markup=kb, parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data.startswith("bulk:"))
async def handle_bulk_choice(call: types.CallbackQuery, state: FSMContext, pg_pool): # pg_pool-ро илова кунед
    if call.from_user.id != ADMIN_ID: return
    
    action = call.data.split(":")[1]
    
    if action == "back_to_statuses":
        # 1. Ҳисоб кардани миқдори ҳамаи борҳо аз база
        counts = await get_admin_order_counts(pg_pool)

        # Функсияи форматкунӣ барои иловаи рақамҳо
        def fmt(label, key):
            count = counts.get(key, 0)
            return f"{label} ({count})" if count > 0 else label

        # 2. Сохтани клавиатура бо шумораҳо
        kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=fmt("🇨🇳 Сканер", "Дар анбор"), callback_data="st:Дар анбор")],
                [InlineKeyboardButton(text=fmt("🚚 Дар рох", "Дар роҳ"), callback_data="st:Дар роҳ")],
                [InlineKeyboardButton(text=fmt("🇹🇯 Дар Душанбе", "Душанбе"), callback_data="st:Душанбе")],
                [InlineKeyboardButton(text=fmt("✅ Супорида шуд", "Супорида шуд"), callback_data="st:Супорида шуд")],
                [InlineKeyboardButton(text=fmt("📦 Молҳои беном", "Беном"), callback_data="st:Беном")],
                [InlineKeyboardButton(text=fmt("🚨 Молхои мушкилдор", "Мушкилдор"), callback_data="st:Мушкилдор")]
        ])
        
        await state.clear()
        # Таҳрир кардани паём бо клавиатураи навшуда
        await call.message.edit_text("Ҳолати борҳоро интихоб кунед:", reply_markup=kb)
        await call.answer()
        return
    kb_back = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ба ақиб", callback_data="bulk:back_to_statuses")] ])
    data = await state.get_data()
    status = data.get("status")
    if action == "date":
        await call.message.edit_text(f"📍 Статус: {status}\nСанаҳоро ворид кунед (масалан: 10.01.2026, 11.01.2026):", reply_markup=kb_back)
       # await call.message.answer(f"📍 Статус: {status}\nСанаҳоро ворид кунед (масалан: 10.01.2026, 11.01.2026):")
        await state.set_state("waiting_for_bulk_date")
    elif action == "list":
       # await call.message.answer(f"📍 Статус: {status}\nРӯйхати борҳоро фиристед (Треккод Ном Телефон):")
        await call.message.edit_text(f"📍 Статус: {status}\nРӯйхати борҳоро фиристед (Треккод Ном Телефон):", reply_markup=kb_back)
        await state.set_state(AdminTrackState.waiting_for_track_code)
    elif action == "view_current": #or action == "view_china":
        async with pg_pool.acquire() as conn:
            # Гирифтани маълумоти бор ва ТАМОМИ таърихи он
            rows = await conn.fetch("""
                SELECT 
                    t.track_code, 
                    t.admin_owner_name,
                    t.status as current_status,
                    (SELECT json_agg(h_list) FROM (
                        SELECT new_status, TO_CHAR(changed_at, 'DD.MM.YY HH24:MI') as dt
                        FROM track_history 
                        WHERE track_code = t.track_code 
                        ORDER BY changed_at ASC
                    ) h_list) as history
                FROM tracks t
                WHERE t.status = $1
                ORDER BY t.created_at DESC
                LIMIT 30
            """, status)
        kb_back = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Ба ақиб", callback_data="bulk:back_to_statuses")]
        ])
        if not rows:
            await call.message.edit_text(f"📭 Борҳо бо статуси <b>{status}</b> ёфт нашуданд.", parse_mode="HTML", reply_markup=kb_back)
        else:
            text = f"📋 <b>Рӯйхати борҳои {status}:</b>\n\n"
            file_has_data = False
            for row in rows:
                name = row['admin_owner_name'] or "Беном"
                # Таърих барои файл
                h_str = ""
                if row['history']:
                    h_data = json.loads(row['history'])
                    h_str = " | ".join([f"{h['new_status']} ({h['dt']})" for h in h_data])
                # Сабт дар файл (барои ҳамаи борҳо)
                writer.writerow([row['track_code'], name, status, h_str])
                file_has_data = True
                # Ташкили матн барои паём
                entry = f"📦 <b>{row['track_code']}</b> ({name})\n"
                if row['history']:
                    for h in json.loads(row['history']):
                        icon = "🔹"
                        if "Дар анбор" in h['new_status']: icon = "🏢🇨🇳"
                        elif "Дар роҳ" in h['new_status']: icon = "🚚"
                        elif "Душанбе" in h['new_status']: icon = "🏢🇹🇯"
                        elif "Супорида шуд" in h['new_status']: icon = "✅"
                        entry += f" ├ {icon} {h['new_status']}: <i>{h['dt']}</i>\n"
                else:
                    entry += " └ ⚠️ Таърих ёфт нашуд\n"
                entry += "\n"
                # Илова ба матн танҳо агар ҷой бошад
                if len(text) + len(entry) < 3800:
                    text += entry
                elif "...ва ғайра" not in text:
                    text += "<i>...давоми рӯйхат дар файли зер 👇</i>\n"
            # 2. Навсозии паёми матнӣ
            try:
                await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_back)
            except Exception:
                await call.message.edit_text("📋 Рӯйхати борҳо дар файл омода шуд.", reply_markup=kb_back)
            # 3. ФИРИСТОДАНИ ФАЙЛ (Ҳатман, агар маълумот бошад)
            if file_has_data:
                file_bytes = output.getvalue().encode('utf-8-sig')
                csv_file = BufferedInputFile(file_bytes, filename=f"Borkho_{status}.csv")
                # Мо answer_document-ро истифода мебарем, то файлро ҳамчун паёми нав фиристад
                await call.message.answer_document(
                    document=csv_file,
                    caption=f"📊 Файли пурраи борҳо ({len(rows)} адад)"
                )
    await call.answer()
########
@dp.message(StateFilter("waiting_for_bulk_date"))
async def perform_bulk_update_by_multiple_dates(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    
    date_list = [d.strip() for d in re.split(r'[,\s\n]+', message.text) if d.strip()]
    data = await state.get_data()
    new_status = data.get("status") # Статуси нав, ки админ интихоб кард
    
    total_updated = 0
    processed_dates = []
    error_dates = []
    
    async with pg_pool.acquire() as conn:
        for date_str in date_list:
            # Санҷиши формати сана (РР.ММ.СССС)
            if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', date_str):
                error_dates.append(date_str)
                continue
            
            status_condition = "AND status != $1::TEXT" # Пешфарз: танҳо иваз шавад, агар статус дигар бошад
            
            if new_status == "Дар роҳ":
                # Танҳо борҳое, ки ҳозир "Дар анбор" ҳастанд
                status_condition = "AND status = 'Дар анбор'"
            # --------------------------------------

            async with conn.transaction():
                # Сабти таърих
                await conn.execute(f"""
                    INSERT INTO track_history (track_code, old_status, new_status)
                    SELECT track_code, status, $1::TEXT FROM tracks
                    WHERE TO_CHAR(created_at, 'DD.MM.YYYY') = $2::TEXT
                    {status_condition}
                """, new_status, date_str)
                
                # Навсозии ҷадвали асосӣ
                result = await conn.execute(f"""
                    UPDATE tracks
                    SET
                        status = $1::TEXT,
                        category = CASE
                            WHEN user_id IS NOT NULL AND user_phone IS NOT NULL THEN 'normal'
                            WHEN admin_owner_name IS NOT NULL AND admin_owner_phone IS NOT NULL THEN 'normal'
                            ELSE 'Беном'
                        END
                    WHERE TO_CHAR(created_at, 'DD.MM.YYYY') = $2::TEXT
                    {status_condition}
                """, new_status, date_str)
                
                # Тафтиши натиҷаи UPDATE
                count = int(result.split(" ")[1])
                if count > 0:
                    total_updated += count
                    processed_dates.append(date_str)
                
    # Сохтани паёми ҷавобӣ
    report = f"📊 <b>Ҳисоботи навсозии гурӯҳӣ:</b>\n\n"
    report += f"📍 Статуси нав: <b>{new_status}</b>\n"
    report += f"✅ Санаҳои навшуда: {', '.join(processed_dates) if processed_dates else 'Ҳеҷ кадом'}\n"
    report += f"🔢 Ҳамагӣ борҳои ивазшуда: <b>{total_updated} адад</b>\n"
    
    if error_dates:
        report += f"\n⚠️ <b>Санаҳои хато (формати нодуруст):</b> {', '.join(error_dates)}"
        
    if total_updated == 0 and not error_dates:
        report += "\n🧐 Дар санаҳои воридшуда ягон бор бо статуси мувофиқ ёфт нашуд."

    kb_back = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сабт ва ба ақиб", callback_data="bulk:back_to_statuses")]
    ])
    await message.answer(report, parse_mode="HTML", reply_markup=kb_back)

########
@dp.callback_query(F.data == "view_anonymous_tracks")
async def view_anonymous_tracks(call: types.CallbackQuery):
    async with pg_pool.acquire() as conn:
        # Гирифтани ҳамаи борҳое, ки категорияашон "Беном" аст
        rows = await conn.fetch("""
            SELECT track_code, status, TO_CHAR(created_at, 'DD.MM.YYYY') as date 
            FROM tracks 
            WHERE category = 'Беном' 
            ORDER BY created_at DESC 
            LIMIT 50
        """)
    kb_back = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сабт ва ба ақиб", callback_data="bulk:back_to_statuses")]
    ])
    if not rows:
        await call.message.edit_text("📭 Молҳои беном ёфт нашуданд.", reply_markup=kb_back)
        await call.answer()
        return
    text = "📦 <b>Рӯйхати молҳои беном (охирин 50 та):</b>\n\n"
    for i, row in enumerate(rows, 1):
        text += f"{i}. <code>{row['track_code']}</code> | {row['date']} | {row['status']}\n"
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()
# 5. Агар "Иловаи рӯйхати нав" интихоб шавад
@dp.callback_query(F.data == "add_bulk_list")
async def bulk_list_request(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text(
        "Рӯйхати борҳоро фиристед.\nФормат:\n<code>треккод ном телефон</code>\n"
        "<i>Агар танҳо треккод бошад, ба 'Беном' меравад.</i>", 
        parse_mode="HTML"
    )
    await state.set_state(AdminTrackState.waiting_for_track_code)
    await call.answer()
#################
@dp.message(AdminTrackState.waiting_for_track_code)
async def process_bulk_input(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    selected_status = data.get("status")
    parts = [p.strip() for p in re.split(r'[,\s\n]+', message.text) if p.strip()]
    added_count = 0
    skipped_count = 0
    skipped_tracks = []
    user_notifications = {}
    async with pg_pool.acquire() as conn:
        for part in parts:
            words = part.split()
            if not words: continue
            track = words[0]
            new_name = None
            new_phone = None
            if len(words) > 1:
                if re.search(r'[А-Яа-яЁёA-Za-z]', words[1]):
                    new_name = words[1]
                    if len(words) > 2:
                        new_phone = words[2]
                else:
                    new_phone = words[1]
            old_data = await conn.fetchrow("SELECT status, user_id FROM tracks WHERE track_code = $1::TEXT", track)
            final_status = ""
            old_status = ""
            if not old_data:
                if selected_status == "Душанбе":
                    final_status = "Душанбе"
                elif selected_status == "Супорида шуд":
                    final_status = "Супорида шуд"
                else:
                    final_status = "Дар анбор"
                old_status = "Нав"
                user_id = None
            else:
                old_status = old_data['status']
                user_id = old_data['user_id']
                if selected_status == "Дар роҳ":
                    if old_status == "Дар анбор":
                        final_status = "Дар роҳ"
                    else:
                        skipped_tracks.append(f"{track} ({old_status})")
                        skipped_count += 1
                        continue
                else:
                    final_status = selected_status
            await conn.execute("""
                INSERT INTO tracks (track_code, admin_owner_name, admin_owner_phone, status, category)
                VALUES ($1::TEXT, $2::TEXT, $3::TEXT, $4::TEXT,
                    CASE WHEN $2::TEXT IS NOT NULL AND $3::TEXT IS NOT NULL THEN 'normal' ELSE 'Беном' END
                )
                ON CONFLICT (track_code) DO UPDATE
                SET
                    admin_owner_name = COALESCE(EXCLUDED.admin_owner_name, tracks.admin_owner_name),
                    admin_owner_phone = COALESCE(EXCLUDED.admin_owner_phone, tracks.admin_owner_phone),
                    status = EXCLUDED.status,
                    category = CASE
                        WHEN (COALESCE(EXCLUDED.admin_owner_name, tracks.admin_owner_name) IS NOT NULL)
                             AND (COALESCE(EXCLUDED.admin_owner_phone, tracks.admin_owner_phone) IS NOT NULL)
                        THEN 'normal'
                        WHEN (tracks.user_id IS NOT NULL AND tracks.user_phone IS NOT NULL)
                        THEN 'normal'
                        ELSE 'Беном' END
            """, track, new_name, new_phone, final_status)
            if old_status != final_status:
                await conn.execute("""
                    INSERT INTO track_history (track_code, old_status, new_status)
                    VALUES ($1::TEXT, $2::TEXT, $3::TEXT)
                """, track, old_status, final_status)
                # 🆕 Тағйирот: Агар статус ба "Душанбе" ё "Супорида шуд" иваз шавад, ҷамъ мекунем
                if final_status in ["Душанбе", "Супорида шуд"] and user_id:
                    if user_id not in user_notifications:
                        user_notifications[user_id] = {"Душанбе": [], "Супорида шуд": []}
                    user_notifications[user_id][final_status].append(f'"{track}"')
            added_count += 1
    kb_back = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сабт ва ба ақиб", callback_data="bulk:back_to_statuses")]
    ])

    report = f"✅ Навсозӣ анҷом ёфт!\n\n"
    report += f"📦 Қабул шуд/Нав шуд: <b>{added_count}</b>\n"

    if skipped_count > 0:
        report += f"⚠️ Радшуда (статус нодуруст): <b>{skipped_count}</b>\n"
        report += f"<i>Треккодҳои радшуда: {', '.join(skipped_tracks[:10])}</i>"
        if skipped_count > 10: report += "..."
    await message.answer(report, parse_mode="HTML", reply_markup=kb_back)
    # 6. 🆕 Тағйирот: ФИРИСТОДАНИ ПАЁМ БА КОРБАРОН
    for u_id, statuses in user_notifications.items():
        user_name = "муштарӣ" 
        async with pg_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT user_full_name FROM tracks WHERE user_id = $1 LIMIT 1", u_id)
            if row and row['user_full_name']:
                user_name = row['user_full_name']
            else:
                row_users = await conn.fetchrow("SELECT full_name FROM users WHERE user_id = $1 LIMIT 1", u_id)
                if row_users and row_users['full_name']:
                    user_name = row_users['full_name']
        for status, tracks in statuses.items():
            if not tracks: continue
            formatted_tracks = []
            for track in tracks:
                clean_track = track.replace('"', '') # Тоза кардани нохунакҳо
                formatted_tracks.append(f"\n📦<code>{clean_track}</code>")
            tracks_str = ",".join(formatted_tracks)

            if status == "Душанбе":
                text = f"Салом, <b>{user_name}</b>!\n\nБорҳои шумо бо треккоди {tracks_str} аллакай дар Душанбе аст, хоҳиш омада борҳоятонро гиред!\n\n<b>Бо эҳтиром Cargo-и боэътимоди шумо PAIGHOM CARGO❤️</b>"
            elif status == "Супорида шуд":
                text = f"Салом, <b>{user_name}</b>!\n\n Борҳои шумо бо треккоди {tracks_str} супорида шуд!\n\n<b>Бо эҳтиром Cargo-и боэътимоди шумо PAIGHOM CARGO❤️</b>"
            elif status =="Статусинав":
                text = f"Салом, {user_name}! Ҳолати борҳои шумо ({tracks_str}) ба '{status}' иваз шуд."
            try:
                await bot.send_message(chat_id=u_id, text=text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
                if status == "Супорида шуд":


                # 3. Фиристодани паём барои фикру мулоҳиза (агар супорида шуда бошад)
                    kb_feedback = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="❌ Инкор кардан", callback_data="decline_feedback")]
                    ])
                
                    await bot.send_message(
                        chat_id=u_id,
                        text="<b>Ассалому алейкум муштарии муҳтарам.\nКаме пеш шумо борҳои худро аз ширкати мо қабул кардед, аз шумо хоҳиш акс ё матн равон кунед.🤩❤️</b>",
                        parse_mode="HTML",
                        reply_markup=kb_feedback
                    )
                
                # 4. Танзими FSM
                    key = StorageKey(
                        bot_id=bot.id,
                        user_id=u_id,
                        chat_id=u_id
                    )
                    await dp.storage.set_state(key=key, state=FeedbackState.waiting_for_feedback)
                    await dp.storage.update_data(key=key, data={"target_user_id": u_id})

            except Exception as e:
                print(f"Хатогӣ дар фиристодани паём ба {u_id}: {e}")

######
# А) Коркарди тугмаи "Инкор кардан"
@dp.callback_query(F.data == "decline_feedback", FeedbackState.waiting_for_feedback)
async def process_decline(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("<b>Сарбаланди ва хонаободиро ба шумо тамано мекунем❤️</b>", parse_mode="HTML")
    await state.clear() # Тоза кардани state

# Б) Қабули акс ё матн аз корбар ва переслат ба канал
# ... (Handler-и process_decline бетағйир мемонад) ...

# Б) Қабули акс ё матн аз корбар ва переслат ба канал
@dp.message(FeedbackState.waiting_for_feedback, F.content_type.in_({'photo', 'text', 'document', 'video'}))
async def get_feedback(message: types.Message, state: FSMContext):
    CHANNEL_ID = "@itcodertajikistan" 
    
    try:
        await bot.forward_message(
            chat_id=CHANNEL_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
        
        # Иловатан метавонед паёми хурд барои администраторҳо илова кунед
#        await bot.send_message(
 #           CHANNEL_ID,
  #          f"🆕 <b>Фикру мулоҳиза аз корбар:</b>\n"
   #         f"ID: <code>{message.from_user.id}</code>\n"
    #        f"Ном: {message.from_user.full_name}",
     #       parse_mode="HTML"
      #  )
        
        await message.answer("<b>Раҳмат, ки хоҳиши моро иҷро кардед\nМо шуморо қадр хоҳем кард\n\n🤩❤️</b>", parse_mode="HTML")
        
    except Exception as e:
        await message.answer("Хатогӣ дар фиристодани маълумот: {e}")
        print(f"Error forwarding message: {e}")
        
    await state.clear() # Тоза кардани state

############################@@ пайёмрасон
@dp.message(F.text == "Ба корбарон пайём равон кардан")
async def broadcast_menu(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    async with pg_pool.acquire() as conn:
        count_china = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM tracks WHERE status = 'Дар анбор'")
        count_road = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM tracks WHERE status = 'Дар роҳ'")
        count_dushanbe = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM tracks WHERE status = 'Душанбе'")
        count_received = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM tracks WHERE status = 'Супорида шуд'")
        count_problem = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM tracks WHERE status = 'Мушкилдор'")
        count_all = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM tracks")
        count_allusers = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM users")
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🇨🇳 Анбори Хитой ({count_china})", callback_data="bc_china")],
        [InlineKeyboardButton(text=f"🚚 Дар роҳ ({count_road})", callback_data="bc_road")],
        [InlineKeyboardButton(text=f"🇹🇯 Дар Душанбе ({count_dushanbe})", callback_data="bc_dushanbe")],
        [InlineKeyboardButton(text=f"✅ Қабулшуда ({count_received})", callback_data="bc_received")],
        [InlineKeyboardButton(text=f"⚠️ Мушкилидошта ({count_problem})", callback_data="bc_problem")],
        [InlineKeyboardButton(text=f"👥 Ба Ҳама (Tracks) ({count_all})", callback_data="bc_all")],
        [InlineKeyboardButton(text=f"👥 Ба Ҳама (Users) ({count_allusers})", callback_data="bc_allusers")]
    ])

    await message.answer("Кадоме аз <b>статус</b> ё <b>категорияро</b> интихоб мекунед?", reply_markup=keyboard, parse_mode="HTML")
@dp.callback_query(F.data.startswith("bc_"))
async def process_broadcast_selection(callback: types.CallbackQuery, state: FSMContext):
    target_group = callback.data.split("_")[1]
    await state.update_data(target_group=target_group)
    cancel_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Менюи асосӣ")]],
        resize_keyboard=True
    )
    await callback.message.answer(
        "Лутфан, пайёми худро равон кунед (матн, акс бо матн ё танҳо акс).\n"
        "Ин пайём ба гурӯҳи интихобшуда фиристода мешавад.", reply_markup=cancel_keyboard)
    await state.set_state(AdminBroadcast.waiting_for_message)
    await callback.answer()
@dp.message(AdminBroadcast.waiting_for_message, F.content_type.in_({'text', 'photo'}))
async def send_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    if message.text == "🏠 Менюи асосӣ":
        await open_admin_panel(message)
        await state.clear()
        return
    data = await state.get_data()
    target_group = data.get("target_group")
    udalit = await message.answer("🚀 Раванди фиристодан оғоз шуд...")
    
    users = []
    async with pg_pool.acquire() as conn:
        if target_group == "china":
            users = await conn.fetch("SELECT DISTINCT user_id, user_phone, user_full_name FROM tracks WHERE status = 'Дар анбор' AND user_id IS NOT NULL")
        elif target_group == "road":
            users = await conn.fetch("SELECT DISTINCT user_id, user_phone, user_full_name FROM tracks WHERE status = 'Дар роҳ' AND user_id IS NOT NULL")
        elif target_group == "dushanbe":
            users = await conn.fetch("SELECT DISTINCT user_id, user_phone, user_full_name FROM tracks WHERE status = 'Душанбе' AND user_id IS NOT NULL")
        elif target_group == "received":
            users = await conn.fetch("SELECT DISTINCT user_id, user_phone, user_full_name FROM tracks WHERE status = 'Супорида шуд' AND user_id IS NOT NULL")
        elif target_group == "problem":
            users = await conn.fetch("SELECT DISTINCT user_id, user_phone, user_full_name FROM tracks WHERE status = 'Мушкилдор' AND user_id IS NOT NULL")
        elif target_group == "all":
            users = await conn.fetch("SELECT DISTINCT user_id, user_phone, user_full_name FROM tracks WHERE user_id IS NOT NULL")
        elif target_group == "allusers":
            users = await conn.fetch("SELECT DISTINCT user_id, phone_number, full_name FROM users WHERE user_id IS NOT NULL")
    success = 0
    failed = 0
    total = len(users)
    failed_users = []
    for user in users:
        try:
            if message.photo:
                await bot.send_photo(
                    chat_id=user['user_id'],
                    photo=message.photo[-1].file_id,
                    caption=message.caption
                )
            else:
                await bot.send_message(
                    chat_id=user['user_id'],
                    text=message.text
                )
            success += 1
        except Exception:
            failed += 1
            phone = user.get('user_phone') or user.get('phone_number') or 'N/A'
            name = user.get('user_full_name') or user.get('full_name') or 'N/A'
            
            failed_users.append(
                f"🆔: <code>{user['user_id']}</code> "
                f"○ <code>{phone}</code> "
                f"○ <code>{name}</code>"
            )

    result_text = (
        f"📊 Натиҷаи фиристодан:\n"
        f"✅ Муваффақ: {success}\n"
        f"❌ Ирсолнашуда: {failed}\n"
        f"Умуми: {total}"
    )
    
    if failed_users:
        result_text += "\n\n❌ Шояд мизоҷ телеграмашро пок кардааст\nРӯйхати шахсоне ки ба онҳо пайём равон карда нашуд!!!:\n" + "\n".join(failed_users)
    
    # Тақсим кардани паём агар хеле дароз бошад
    if len(result_text) > 4096:
        for i in range(0, len(result_text), 4096):
            await message.answer(result_text[i:i+4096])
    else:
        await message.answer(result_text, parse_mode='HTML')
    await udalit.delete()
    await open_admin_panel(message)
    await state.clear()
######################
@dp.message(F.text == "📊 Статистика")
async def show_statistics(message: types.Message):
    if message.from_user.id != ADMIN_ID: return

    # 1. SQL дархост барои гирифтани статистика
    sql = """
        SELECT 
            TO_CHAR(created_at, 'DD.MM.YY') as date,
            status,                
            COUNT(*) as count
        FROM tracks
        GROUP BY date, status
        ORDER BY date DESC;
    """

    async with pg_pool.acquire() as conn:
        rows = await conn.fetch(sql)

    if not rows:
        await message.answer("📊 Дар база ҳеҷ маълумот нест.")
        return

    # 2. Ташкил додани маълумот дар шакли дилхоҳ
    stats_dict = {}
    total_by_date = {}

    for row in rows:
        date = row['date']
        status = row['status']
        count = row['count']

        if date not in stats_dict:
            stats_dict[date] = []
            total_by_date[date] = 0
        
        stats_dict[date].append(f"<b>{status}</b> ({count})")
        total_by_date[date] += count

    # 3. Сохтани матни ҷавоб
    response_text = "📊 <b>Статистикаи умумӣ:</b>\n\n"
    for date, statuses in stats_dict.items():
        statuses_str = " ○ ".join(statuses)
        response_text += f"📅 {date} ​○ {statuses_str}​ ○ 🏁 Ҳамагӣ: {total_by_date[date]}\n\n"

    await message.answer(response_text, parse_mode="HTML")

#####
@dp.message(F.text == "Маълумоти ботро Excel кардан")
async def export_to_csv(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    await message.answer("⏳ Маълумот омода шуда истодааст...")

    # 1. Гирифтани маълумот аз база
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM tracks")
    
    if not rows:
        await message.answer("📊 Базаи додаҳо холӣ аст.")
        return

    # 2. Сохтани файли CSV дар хотира
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';') # Аломати ҷудокунанда ";" беҳтар аст барои Excel-и русиву тоҷикӣ

    # Навиштани сарлавҳаи сутунҳо
    writer.writerow([
        'Track_code', 'admin_owner_name', 'admin_owner_phone', 
        'status', 'category', 'user_id', 'user_full_name', 
        'user_phone', 'user_address', 'created_at'
    ])

    # Навиштани маълумот
    for row in rows:
        writer.writerow(row)
    
    output.seek(0)
    
    # 3. Фиристодани файл
    csv_file = BufferedInputFile(output.read().encode('utf-8-sig'), filename="paighomcargotracks.csv")
    await message.answer_document(document=csv_file, caption="📊 Маълумоти ҷадвали tracks (CSV)")

################### Statistika
def суроғаинлайнтугма():
    тугма = InlineKeyboardBuilder()
    тугма.add(InlineKeyboardButton(text="Суроғаи Хитой", callback_data="суроғахитой")),
    тугма.add(InlineKeyboardButton(text="Суроғаи Тоҷикистон", callback_data="суроғатоҷикистон"))
    тугма.adjust(1)
    return тугма.as_markup()

def суроғаинлайнтугмахитой():
    тугма = InlineKeyboardBuilder()
    тугма.add(InlineKeyboardButton(text="Авиа", callback_data="суроғаавиа")),
    тугма.add(InlineKeyboardButton(text="Авто", callback_data="суроғаавто"))
    тугма.adjust(1)
    return тугма.as_markup()
def суроғаинлайнтугмаавто():
    тугма = InlineKeyboardBuilder()
    тугма.add(InlineKeyboardButton(text="Суроғаи Иву", callback_data="суроғаиву"))
    return тугма.as_markup()
def суроғаинлайнтугмаавиа():
    тугма = InlineKeyboardBuilder()
    тугма.add(InlineKeyboardButton(text="Суроғаи Гуандҷоу", callback_data="суроғагуандҷоу"))
    return тугма.as_markup()

def get_cabinet_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=_('Профили ман')), KeyboardButton(text=_('Фармоишҳои ман'))],
        [KeyboardButton(text=_('⬅️ Бозгашт ба менюи асосӣ'))]
    ], resize_keyboard=True)
def get_orders_inline_kb(counts: dict = None):
    if counts is None:
        counts = {}

    # Функсияи ёрирасон барои формат кардани матни тугма
    def format_label(label, key):
        count = counts.get(key, 0)
        # Агар count аз 0 калон бошад, (N)-ро илова мекунем, вагарна холӣ
        return f"{label} ({count})" if count > 0 else label

    builder = InlineKeyboardBuilder()

    # Истифодаи форматкунӣ барои ҳар як тугма
    builder.row(InlineKeyboardButton(
        text=format_label("🇨🇳 Дар склади Хитой", "Дар анбор"), 
        callback_data="my_orders:Дар анбор"
    ))
    builder.row(InlineKeyboardButton(
        text=format_label("🚚 Дар роҳ", "Дар роҳ"), 
        callback_data="my_orders:Дар роҳ"
    ))
    builder.row(InlineKeyboardButton(
        text=format_label("🏢 Расид", "Душанбе"), 
        callback_data="my_orders:Душанбе"
    ))
    builder.row(InlineKeyboardButton(
        text=format_label("✅ Супорида шуд", "Супорида шуд"), 
        callback_data="my_orders:Супорида шуд"
    ))
    builder.row(InlineKeyboardButton(
        text=format_label("🚨 Молҳои мушкилдор", "Мушкилдор"), 
        callback_data="my_orders:Мушкилдор"
    ))

    builder.row(InlineKeyboardButton(text="🔍 Тафтиши треккод", callback_data="check_new_track"))
    builder.row(InlineKeyboardButton(text=_("🏠 Асоси"), callback_data="ба_менюи_асоси"))

    return builder.as_markup()

@dp.message(F.text == _('Фармоишҳои ман'))
async def show_orders_menu(message: Message, pg_pool):
    temp_msg = await message.answer("Коркард шудаистодааст...", reply_markup=ReplyKeyboardRemove())
    await temp_msg.delete()
    counts = await get_user_order_counts(message.from_user.id, pg_pool)

    # 2. Сохтани клавиатура бо миқдорҳо
    kb = get_orders_inline_kb(counts)

    await message.answer("📦 Категорияи борҳоро интихоб кунед:", reply_markup=kb)

async def get_user_order_counts(user_id: int, pg_pool):
    async with pg_pool.acquire() as conn:
        # Дархост барои ҳисоб кардани миқдори борҳо аз рӯи статус
        rows = await conn.fetch("""
            SELECT status, COUNT(*) as count 
            FROM tracks 
            WHERE user_id = $1 
            GROUP BY status
        """, user_id)
        # Натиҷаро ба шакли луғат мегардонем: {'Дар роҳ': 5, 'Душанбе': 10}
        return {row['status']: row['count'] for row in rows}

@dp.callback_query(F.data == "check_new_track")
async def start_tracking(call: CallbackQuery, state: FSMContext):
#    await call.message.answer("Лутфан треккодро ворид кунед:")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_("Ба кафо"), callback_data="ба_менюи_фармоишхо"),
         InlineKeyboardButton(text=_("Ба асоси"), callback_data="ба_менюи_асоси")]])
    await call.message.edit_text("Лутфан треккодро ворид кунед:", reply_markup=kb)
    await state.set_state("waiting_user_track")
    await call.answer()

@dp.message(StateFilter("waiting_user_track"))
async def process_track_check(message: Message, state: FSMContext):
    track_codes = message.text.strip().split()
    user_id = message.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_("Ба кафо"), callback_data="ба_менюи_фармоишхо"),
         InlineKeyboardButton(text=_("Ба асоси"), callback_data="ба_менюи_асоси")]])

    async with pg_pool.acquire() as conn:
        u_info = await conn.fetchrow("SELECT full_name, phone_number, address FROM users WHERE user_id = $1", user_id)

        if not u_info:
            await message.answer("🚫 Бори шумо дар склади Хитой қабул нашудааст.", reply_markup=kb)
            return

        # СИКЛ БАРОИ ҲАР ЯК ТРЕККОД
        for track_code in track_codes:
            # Ҳарфҳоро калон мекунем барои ҷустуҷӯи дуруст дар база
            code_upper = track_code.upper()
            track = await conn.fetchrow("SELECT * FROM tracks WHERE track_code = $1", track_code)

            if not track:
                await message.answer(f"Бор бо треккоди <b>{track_code}</b> то ҳол дар анбори Cargo дар ш. Иву наомадааст.", reply_markup=kb, parse_mode="HTML")
                continue

            # Гирифтани сана ва статус аз база
            sana = track['created_at'].strftime('%d.%m.%Y %H:%M')   # ё track['created_at'] вобаста ба номи сутун дар базаи шумо
            current_status = track['status']

            if track['user_id'] == user_id:
                await message.answer(
                    f"📦 Бори шумо бо треккоди <b>{track_code}</b> санаи {sana} дар склади Хитой қабул шудааст.\n\n"
                    f"📍 Ҳолати кунунӣ: <b>{current_status}</b>\n"
                    f"Шумо метавонед навсозии ҳолати борҳоятонро дар тугмаи 'Фармоишҳои ман' аз назар гузаронед", reply_markup=kb, parse_mode="HTML")
            else:
                # Навсозӣ ва пайваст кардани бор ба корбар
                await conn.execute("""
                    UPDATE tracks SET user_id = $1, user_full_name = $2, user_phone = $3, user_address = $4,
                        category = CASE WHEN category = 'Беном' THEN 'normal' ELSE category END
                    WHERE track_code = $5
                """, user_id, u_info['full_name'], u_info['phone_number'], u_info['address'], track_code)

                # Паёми ниҳоӣ бо сана ва статус
                await message.answer(
                    f"📦 Бори шумо бо треккоди <b>{track_code}</b> санаи {sana} дар склади Хитой қабул шудааст.\n\n"
                    f"📍 Ҳолати кунунии бор: <b>{current_status}</b>\n"
                    f"📦 Ба рӯйхати фармоишҳои шумо илова шуд.\n"
                    f"Шумо метавонед навсозии ҳолати борҳоятонро дар тугмаи 'Фармоишҳои ман' аз назар гузаронед", reply_markup=kb, parse_mode="HTML")
######
# Вақте корбар пайём мефиристад: "10 0.8 1.0 2.0"
# (вазн, дарозӣ, бар, баландӣ)
def get_back_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⬅️ Бозгашт ба менюи асосӣ")]
        ],
        resize_keyboard=True
    )
    return keyboard

@dp.message(F.text == 'Ҳисоб кардани нархи бор')
async def ask_dimensions(message: types.Message):
    await message.answer("Лутфан маълумоти борро чунин вазн(кг) дарозӣ(м) бар(м) баландӣ(м) бо пробел ҷудо намуда равон кунед!\n\n"
                         "Мисол:<b>10 1 1.2 0.8</b>", parse_mode="HTML", reply_markup=get_back_menu())

@dp.message(F.text.regexp(r'^\d+(\.\d+)? \d+(\.\d+)? \d+(\.\d+)? \d+(\.\d+)?$'))
async def calculate_cargo(message: types.Message):
    try:
        data = message.text.split()
        weight = float(data[0])
        length = float(data[1])
        width = float(data[2])
        height = float(data[3])

        volume = length * width * height
        volumetric_weight = volume * 167 

        cost = 0
        method = ""
        if weight > volumetric_weight:
            cost = weight * 23 # Нарх барои кг
            method = f"кг ({weight} кг)"
        else:
            cost = volume * 2500 # Нарх барои куб
            method = f"кӯб {volume:.2f}м³"

        await message.answer(f"📦<b> Натиҷаи ҳисоб</b>:\n\n"
                             f"⚖️ Вазни воқеӣ: {weight} кг\n"
                             f"📏 Кӯб: {volume:.2f} м³\n\n"
                             f" Бори шумо ҳамчун {method} <b>{cost:.2f}</b> сомонӣ", reply_markup=get_back_menu(), parse_mode="HTML")

    except Exception as e:
        await message.answer("Хатогӣ дар формат. Лутфан бори дигар кӯшиш кунед.")

# --- Ҳандлер барои тугмаи "Омӯзиши ройгон" ---
@dp.message(F.text == 'Омӯзиши ройгон')
async def show_free_lessons(message: types.Message):
    
    # 1. Сохтани тугмаҳои инлайнӣ
    button1 = InlineKeyboardButton(text="Тарзи адрес дохил кардан дар Pinduoduo ", url="https://t.me/payghomobucheniya/6")
    button2 = InlineKeyboardButton(text="Тарзи бор заказ кардан", url="https://t.me/payghomobucheniya/7")
    button3 = InlineKeyboardButton(text="Тарзи дохил кардани бор дар корзина", url="https://t.me/payghomobucheniya/8")
    button4 = InlineKeyboardButton(text="Зеркашӣ кардани барномаи Pinduoduo", url="https://t.me/payghomobucheniya/11")
    button5 = InlineKeyboardButton(text="Тарзи вазврат кардани пул", url="https://t.me/payghomobucheniya/12")
    button6 = InlineKeyboardButton(text="Хатогие ки бори шумо дар 15 рӯз ба склад мерасад", url="https://t.me/payghomobucheniya/13")
    button7 = InlineKeyboardButton(text="Борҳои 1 юана дар Pinduoduo ", url="https://t.me/payghomobucheniya/14")
    button8 = InlineKeyboardButton(text="Борҳои бепул", url="https://t.me/payghomobucheniya/15")
    button9 = InlineKeyboardButton(text="Тарзи дуруст интихоб кардани размери либос", url="https://t.me/payghomobucheniya/17")
    button10 = InlineKeyboardButton(text="Тарзи дуруст заказ кардани чизҳои шишагӣ", url="https://t.me/payghomobucheniya/18")
    button11 = InlineKeyboardButton(text="Фишкаи Pinduoduo", url="https://t.me/payghomobucheniya/19")
    button12 = InlineKeyboardButton(text="Хатогӣ | Молҳои б/у", url="https://t.me/payghomobucheniya/20")
    button13 = InlineKeyboardButton(text="Муайян кардани вазни бор", url="https://t.me/payghomobucheniya/21")






    # 2. Ҷойгир кардани тугмаҳо дар клавиатура
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [button1],
        [button2],
        [button3],
        [button4],
        [button5],
        [button6],
        [button7],
        [button8],
        [button9],
        [button10],
        [button11],
        [button12],
        [button13]
    ])

    # 3. Фиристодани паём бо тугмаҳо
    await message.answer("📚 <b> Қисми омӯзиширо интихоб карда маълумотро дастрас кунед!</b>",
                         reply_markup=inline_kb,
                         parse_mode="HTML")


#########
@dp.message(lambda message: message.text == _('Пайгирии треккод'))
async def ask_for_track1(message: Message, state: FSMContext):

    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚫 Бекор кардан")]],
        resize_keyboard=True
    )
    await message.answer("Лутфан, треккоди худро ворид кунед:", reply_markup=cancel_kb)
    # Мо ҳолати ботро ба "waiting_user_track" иваз мекунем
    await state.set_state("waiting_user_track1")

@dp.message(StateFilter("waiting_user_track1"))
@dp.message(F.text == "🚫 Бекор кардан")
async def process_track_check1(message: Message, state: FSMContext):
    if message.text == _('🚫 Бекор кардан'):
        await state.clear()
        await асоси(message)
        return

    # МАТНРО БА РӮЙХАТ ТАҚСИМ МЕКУНЕМ
    track_codes = message.text.strip().split()
    user_id = message.from_user.id

    async with pg_pool.acquire() as conn:
        u_info = await conn.fetchrow("SELECT full_name, phone_number, address FROM users WHERE user_id = $1", user_id)

        if not u_info:
            await message.answer("❌ Хатогӣ: Маълумоти шумо ёфт нашуд.")
            return

        # СИКЛ БАРОИ ҲАР ЯК ТРЕККОД
        for track_code in track_codes:
            # Ҳарфҳоро калон мекунем барои ҷустуҷӯи дуруст дар база
            code_upper = track_code.upper()
            track = await conn.fetchrow("SELECT * FROM tracks WHERE track_code = $1", track_code)

            if not track:
                await message.answer(f"Бор бо треккоди <b>{track_code}</b> то ҳол дар анбори Cargo дар ш. Иву наомадааст.", parse_mode="HTML")
                continue

            # Гирифтани сана ва статус аз база
            sana = track['created_at'].strftime('%d.%m.%Y %H:%M')   # ё track['created_at'] вобаста ба номи сутун дар базаи шумо
            current_status = track['status']

            if track['user_id'] == user_id:
                await message.answer(
                    f"📦 Бори шумо бо треккоди <b>{track_code}</b> санаи {sana} дар склади Хитой қабул шудааст.\n\n"
                    f"📍 Ҳолати кунунӣ: <b>{current_status}</b>\n"
                    f"Шумо метавонед навсозии ҳолати борҳоятонро дар тугмаи 'Фармоишҳои ман' аз назар гузаронед",
                    parse_mode="HTML"
                )
            else:
                # Навсозӣ ва пайваст кардани бор ба корбар
                await conn.execute("""
                    UPDATE tracks SET user_id = $1, user_full_name = $2, user_phone = $3, user_address = $4,
                        category = CASE WHEN category = 'Беном' THEN 'normal' ELSE category END
                    WHERE track_code = $5
                """, user_id, u_info['full_name'], u_info['phone_number'], u_info['address'], track_code)

                # Паёми ниҳоӣ бо сана ва статус
                await message.answer(
                    f"📦 Бори шумо бо треккоди <b>{track_code}</b> санаи {sana} дар склади Хитой қабул шудааст.\n\n"
                    f"📍 Ҳолати кунунии бор: <b>{current_status}</b>\n"
                    f"📦 Ба рӯйхати фармоишҳои шумо илова шуд.\n"
                    f"Шумо метавонед навсозии ҳолати борҳоятонро дар тугмаи 'Фармоишҳои ман' аз назар гузаронед",
                    parse_mode="HTML"
                )


#
@dp.callback_query(F.data.startswith("my_orders:"))
async def show_my_orders(call: CallbackQuery):
    status_filter = call.data.split(":")[1]
    user_id = call.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_("Ба кафо"), callback_data="ба_менюи_фармоишхо"),
         InlineKeyboardButton(text=_("Ба асоси"), callback_data="ба_менюи_асоси")]
    ])
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT t.track_code, 
                   (SELECT json_agg(h) FROM (
                       SELECT new_status, TO_CHAR(changed_at, 'DD.MM.YY HH24:MI') as dt 
                       FROM track_history WHERE track_code = t.track_code ORDER BY changed_at DESC
                   ) h) as history
            FROM tracks t 
            WHERE t.user_id = $1 AND t.status = $2
        """, user_id, status_filter)

    if not rows:
        await call.message.edit_text(f"📭 Шумо дар статуси '{status_filter}' бор надоред.", reply_markup=kb)
    else:
        icons = {
            "Дар анбор": "🏢🇨🇳",
            "Дар роҳ": "🚚",
            "Душанбе": "🏢🇹🇯",
            "Супорида шуд": "✅",
            "Мушкилот": "📥"
        }

        text = f"📋 <b>Борҳои шумо ({status_filter}):</b>\n\n"
#
                # 1. Аввал тамоми матнро ҷамъ мекунем
        all_texts = []
        current_chunk = f"📋 <b>Борҳои шумо ({status_filter}):</b>\n\n"

        for row in rows:
            row_text = f"📦 <b>{row['track_code']}</b>\n"
            if row['history']:
                history_data = json.loads(row['history'])
                for i, h in enumerate(history_data):
                    icon = "🔹"
                    for key, value in icons.items():
                        if key in h['new_status']:
                            icon = value
                            break
                    prefix = " └" if i == len(history_data) - 1 else " ├"
                    row_text += f"{prefix} {icon} {h['new_status']} — <i>{h['dt']}</i>\n"
            row_text += "\n"

            # 2. Тафтиш мекунем: агар илова кардани ин бор аз лимит гузарад, қисми ҳозираро захира мекунем
            if len(current_chunk) + len(row_text) > 4000:
                all_texts.append(current_chunk)
                current_chunk = row_text # Қисми навро оғоз мекунем
            else:
                current_chunk += row_text

        all_texts.append(current_chunk) # Қисми охиринро илова мекунем

        # 3. Фиристодани қисмҳо
        for index, chunk in enumerate(all_texts):
            if index == 0:
                # Паёми аввалро таҳрир мекунем
                await call.message.edit_text(chunk, reply_markup=kb, parse_mode="HTML")
            else:
                # Қисмҳои боқимондаро ҳамчун паёми нав мефиристем
                await call.message.answer(chunk, reply_markup=kb, parse_mode="HTML")

    await call.answer()

def get_profile_edit_inline():
    return InlineKeyboardMarkup(inline_keyboard=[ [InlineKeyboardButton(text=_("Иваз кардани маълумот"), callback_data="ивазкарданимаълумот")],
        [InlineKeyboardButton(text=_("Ба кафо баргаштан"), callback_data="ба_кафо_баргаштан")]
    ])
def get_profile_edit_inline1():
    kb = InlineKeyboardBuilder()
    kb.button(text=_("👤Ном"), callback_data="edit_full_name")
    kb.button(text=_("📞Телефон"), callback_data="edit_phone_number")
    kb.button(text=_("📍Сурога"), callback_data="edit_address")
    kb.adjust(2)  # 👈 ин ҷои row_width
    kb.row(
        InlineKeyboardButton(text=_("⬅️Ба кафо"), callback_data="ба_кафо_баргаштан"),
        InlineKeyboardButton(text=_("🏠Асоси"), callback_data="ба_менюи_асоси"),
    )
    return kb.as_markup()
@dp.callback_query(F.data.startswith("edit_"))
async def start_edit_process(call: types.CallbackQuery, state: FSMContext):
    field = call.data.replace("edit_", "")
    await state.update_data(editing_field=field)
    prompts = {
        "full_name": _("Лутфан ному насаби навро ворид кунед:\n Бо чунин формат <b>Salimov Bahrom</b>"),
        "phone_number": _("Лутфан рақами телефони навро ворид кунед:\n Бо чунин формат <b>+992XXXXXXXXX</b>"),
        "address": _("Лутфан суроғаи навро ворид кунед:")}
    text_to_show = prompts.get(field, _("Маълумоти навро ворид кунед:"))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_("Бекор кардан"), callback_data="Ба_кафо_профил"),
     InlineKeyboardButton(text=_("Ба асоси"), callback_data="ба_менюи_асоси")] # 4. ТАҲРИР КАРДАНИ ПАЁМ (ба ҷои паёми нав)
    ])
    await call.message.edit_text(text=text_to_show, reply_markup=kb, parse_mode="HTML")
    await state.set_state(RegState.waiting_for_edit) # 5. Ҳолати интизориро фаъол мекунем
    await call.answer()
@dp.message(RegState.waiting_for_edit)
async def process_edit_save(пайём: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data.get("editing_field")
    user_id = пайём.from_user.id
    new_value = пайём.text
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_("Бекор кардан"), callback_data="Ба_кафо_профил")]])
    if field == "phone_number":
        pattern = r"^\+992\d{9}$"
        if not re.match(pattern, new_value):
            await пайём.answer(
                _("❌ Формати рақам нодуруст аст.\n"
                  "Лутфан рақамро дар формати: <b>+992XXXXXXXXX</b> ворид кунед."), reply_markup=kb, parse_mode="HTML")
            return # Функсияро тамом мекунем, то база нав нашавад
    elif field == "full_name":
        pattern = r"^[A-Za-z]{3,}\s+[A-Za-z]{3,}$"
        if not re.match(pattern, new_value):
            await пайём.answer(
                _("❌ Формати ному насаб нодуруст аст.\n"
                  "Лутфан ном ва насабро бо <b>ҳарфҳои лотинӣ</b> ворид кунед (масалан: Ali Valiev).\n"
                  "Ҳар кадомаш бояд зиёда аз 3 ҳарф бошад."), reply_markup=kb, parse_mode="HTML")
            return
    async with pg_pool.acquire() as conn:
        query = f"UPDATE users SET {field} = $1 WHERE user_id = $2"
        await conn.execute(query, new_value, user_id)
    await пайём.answer(_("Маълумот бомуваффақият нав карда шуд! ✅"))
    await state.clear()  # 1. Ҳолатро тоза мекунем, то бот дигар мунтазири матн набошад
    await show_profile_logic(пайём, state)
@dp.message(F.text)
async def сис_пайём(пайём: types.Message, state: FSMContext):
    user_id = пайём.from_user.id
    text = пайём.text
    if user_id == ADMIN_ID:
        if text == "Пок кардани маълумоти редис":
            await redis_db.flushdb()
            await пайём.answer("Хама маълумоти редис пок шуд!")
        return
    if text in ['Тоҷикӣ', 'Русский', 'English']:
        l_code = {'Тоҷикӣ': 'tj', 'Русский': 'ru', 'English': 'en'}[text]
        await redis_db.set(f"user:{user_id}:lang", l_code)
        i18n.ctx_locale.set(l_code)
        await оғоз(пайём, state)
        return
    if not await тафтиш_ва_пурсиши_обуна(пайём): return
    if text == _('Иваз кардани забон/Chouse language/ Изменить язык'):
        await redis_db.delete(f"user:{user_id}:lang")
        await оғоз(пайём, state)
    elif text == _('Суроға'):
        await пайём.answer(_("Суроғаро интихоб кунед!"), reply_markup=суроғаинлайнтугма())
    elif text == _('Мӯҳлати даставка'):
        await пайём.answer(_("""МУҲЛАТИ РАСИДАНИ БОРҲОИ ШУМО 15 то 20 ШАБОНА РУЗ, БА ҒАЙР АЗ ҲОЛАТҲОИ 
ФОРС-МАЖОР ( махкам шудани роҳҳо идҳои Давлати назорати гумрук дар ЧИН ва ҳолатҳое,ки  аз чониби ГУМРУКИ ТОЧИКИСТОН  вобастаги дорад )📦🚛\n\n<b>Диққат: Мӯҳлат аз рӯзи ба анбор расидани бор ба инобат гирифта шудааст</b>"""), parse_mode="HTML")
    elif text == _('Ҳуҷраи инфироди(утоқи шахси)'):
        await пайём.answer(_("Шумо дар менюи утоқи шахсӣ ҳастед:"), reply_markup=get_cabinet_kb())
    elif text == _('Маълумот оиди карго'):
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Instagram", url="https://www.instagram.com/paighom_cargo?igsh=aXdtZmhudm5idWVp")],
               [InlineKeyboardButton(text="Telegram-омӯзиши ройгон", url="https://t.me/payghomobucheniya")],
               [InlineKeyboardButton(text="WhatsApp", url="https://wa.me/8615024564470")]
        ])
        message_text = ("""<b>СУРОГАИ МО ДАР ШАХРИ ДУШАНБЕ</b>\n Н. ИСМОИЛИ СОМОНИ КУЧАИ МЕХНАТ № 5 ОШЁНАИ ЯКУМ ХУЧРАИ № 2  КАРОРГОҲ ДАР БАРИ БОЗОРИ МЕХРГОН.\n
<b>РЕҶАӢ КОРИ</b>👩‍💻\nРУЗҲОИ КОРИ АЗ РУЗИ ДУШАНБЕ ТО РУЗИ ШАНБЕ АЗ СОАТИ 09:00 то 18:00
РУЗИ ЯКШАНБЕ РУЗИ ИСТИРОҲАТИ МЕБОШАД.\nРақамҳр барои тамос: <code>116670614</code>👩‍💻"""
        )
        await пайём.answer(message_text, reply_markup=keyboard, parse_mode="HTML")
    elif text ==_('Молҳои манъшуда'):
        await пайём.answer("""<b>Молҳои манъшуда дар каргои мо:</b>
<pre>- ❌ Доруҳо (порошок, хаб, доруҳои моеъ)
- ❌ Ҳамаи навъҳои моддаҳои моеъ (атр, хушбӯйҳо ва ғ.)
- ❌ Ҳамаи навъҳои яроқи сард (корд, шокер, бита ва ғ.)
- ❌ Сигаретҳои электронӣ, калянҳо ва дигар молҳои монанд
- ❌ Молҳои бо аломати 18+
- ❌ Смартфонҳо (телефонҳо) Ноутбукҳо
- ❌ Растения 🌱, гулҳо
- ❌ Батареяҳо ва повер банкҳо
- ❌ Зеварату ҷавоҳирот (зар)
- ❌ Меваҳои хушк
- ❌ Оташгирак</pre>
Диққат: Агар касе ин молҳоро фармоиш диҳад, барои интиқол мо масъул нестем.""", parse_mode="HTML")
    elif text == _('Нархнома'):
        keyboard1 = InlineKeyboardMarkup(inline_keyboard=[
               [InlineKeyboardButton(text="Instagram", url="https://www.instagram.com/paighom_cargo?igsh=aXdtZmhudm5idWVp")],
               [InlineKeyboardButton(text="WhatsApp", url="https://wa.me/8615024564470")]])
        await пайём.answer("""<b>Нархномаи Мо:</b>
КУБ - 250$ 💰КИЛОГРАММ 2.3$ 💰\n
Мухлати доставка 12-25 руз аз рузи дар склад кабул кардан.
Барои борхои калон ба <b>Whatsapp</b> ё <b>Instagram</b>-и  мо мурочиат намоед.""", reply_markup=keyboard1, parse_mode="HTML")
    elif text == _('Профили ман'):
        async with pg_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT full_name, phone_number, address FROM users WHERE user_id = $1", user_id)
        if user:
            profile_text = (
                f"👤 <b>{_('Маълумоти шахсӣ')}:</b>\n\n"
                f"📝 <b>{_('Ном')}:</b> {user['full_name']}\n"
                f"📞 <b>{_('Телефон')}:</b> {user['phone_number']}\n"
                f"🏠 <b>{_('Суроға')}:</b> {user['address']}"
            )
            temp_msg = await пайём.answer("Коркард шудаистодааст...", reply_markup=ReplyKeyboardRemove()) # 2. Паёмро фавран нест мекунем (дар экран чизе намемонад)
            await пайём.answer(profile_text, reply_markup=get_profile_edit_inline(), parse_mode="HTML")
            await temp_msg.delete()
        else:
            await пайём.answer(_("Маълумот ёфт нашуд. /start -ро пахш кунед."))
            return
    elif text == _('⬅️ Бозгашт ба менюи асосӣ'):
        await асоси(пайём) # Даъвати функсияи менюи асосӣ, ки қаблан доштед
@dp.callback_query(F.data == "ивазкарданимаълумот")
#@dp.message(F.text == _("👤 Профили ман")) 
#@dp.callback_query(F.data == "view_profile")
@dp.callback_query(F.data == "Ба_кафо_профил") 
async def show_profile_logic(пайём: Union[types.Message, types.CallbackQuery], state: FSMContext):
    user_id = пайём.from_user.id
    async with pg_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT full_name, phone_number, address FROM users WHERE user_id = $1",
            user_id
        )
    if user:
        profile_text = (
            f"👤 <b>{_('Маълумоти шахсӣ')}:</b>\n\n"
            f"📝 <b>{_('Ном')}:</b> {user['full_name']}\n"
            f"📞 <b>{_('Телефон')}:</b> {user['phone_number']}\n"
            f"🏠 <b>{_('Суроға')}:</b> {user['address']}"
        )
        if isinstance(пайём, types.Message):
            await пайём.answer(profile_text, reply_markup=get_profile_edit_inline1(), parse_mode="HTML")
            await state.clear()
        elif isinstance(пайём, types.CallbackQuery):
            await пайём.message.edit_text(profile_text, reply_markup=get_profile_edit_inline1(), parse_mode="HTML")
            await state.clear()
            await пайём.answer() # Барои callback ҳатмӣ аст
    else:
        if isinstance(пайём, types.Message):
            await пайём.answer(_("Маълумот ёфт нашуд!"))
        else:
            await пайём.answer(_("Маълумот ёфт нашуд!"), show_alert=True)
@dp.message(F.text == "Менguюи асоg7сӣ")
@dp.message(F.text == "Репли")
@dp.callback_query(F.data == "Ба_кафо_суроға")
@dp.callback_query(F.data == "Ба_кафо_суроға1")
@dp.callback_query(F.data == "суроғагуандҷоу")
@dp.callback_query(F.data == "суроғаиву")
@dp.callback_query(F.data == "суроғахитой")
@dp.callback_query(F.data == "суроғаавиа")
@dp.callback_query(F.data == "суроғаавто")
@dp.callback_query(F.data == "суроғатоҷикистон")
@dp.callback_query(F.data == "ба_кафо_баргаштан")
@dp.callback_query(F.data == "ба_менюи_асоси")
@dp.callback_query(F.data == "ба_менюи_фармоишхо")
async def сис_пайём1(пайём: Union[types.Message, types.CallbackQuery], state: FSMContext):
    user_id = пайём.from_user.id
    if isinstance(пайём, types.Message): # ================= MESSAGE =================
        if пайём.from_user.id == ADMIN_ID:
            if пайём.text == "llllМеtнюи асhосӣ":
                await state.clear()
                await open_admin_panel(пайём)
            return
    elif isinstance(пайём, types.CallbackQuery):
        data = пайём.data
        if data == "ба_кафо_баргаштан":  # Ин ҳамон 'callback_data'-ест, ки дар тугма сохтаед
            await пайём.message.answer(_("Шумо дар менюи утоқи шахсӣ ҳастед:"), reply_markup=get_cabinet_kb())
        elif data == "ба_менюи_асоси":
            await асоси(пайём.message)
            await state.clear()
        elif data == "ба_менюи_фармоишхо":
            counts = await get_user_order_counts(user_id, pg_pool)
            await пайём.message.edit_text("📊 Рӯйхати фармоишҳои шумо:", reply_markup=get_orders_inline_kb(counts), parse_mode="HTML")
            await state.clear()
        elif data == "Ба_кафо_суроға":
            await пайём.message.delete()
            await пайём.message.answer("Суроғаро интихоб кунед!", reply_markup=суроғаинлайнтугма())
        elif data == "Ба_кафо_суроға1":
            await пайём.message.edit_text("Суроғаро интихоб кунед!", reply_markup=суроғаинлайнтугма())
        elif data == "суроғахитой":
            await пайём.message.edit_text("Интихоб кунед:", reply_markup=суроғаинлайнтугмахитой())
        elif data == "суроғаавиа":
            await пайём.message.edit_text("Суроғаҳои Авиа:", reply_markup=суроғаинлайнтугмаавиа())
        elif data == "суроғаавто":
            await пайём.message.edit_text("Суроғаҳои Авто:", reply_markup=суроғаинлайнтугмаавто())
        elif data == "суроғагуандҷоу":
            тугмабақафо = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Ба қафо", callback_data="Ба_кафо_суроға1")]])
#            await пайём.message.delete()
            await пайём.message.edit_text("Ба наздикӣ дастрас мешавад!!!", reply_markup=тугмабақафо)
        elif data == "суроғаиву":
            user_id = пайём.from_user.id # ID-и корбаре, ки тугмаро пахш кард
            async with pg_pool.acquire() as conn:
                user_data = await conn.fetchrow(
                    "SELECT full_name, phone_number FROM users WHERE user_id = $1", 
                    user_id
                )
            if user_data and user_data['full_name']:
                user_name = user_data['full_name'].split()[0]
            else:
                user_name = "номи шумо"
            raw_phone = user_data['phone_number'] if user_data else "телефони шумо"
            clean_phone = raw_phone.replace("+992", "") if raw_phone else ""
            base_text1 = "🏭 <b>Суроға дар шаҳри Иву</b>"
            base_text = "\n收货人: PAIGHOM CARGO\n手机号: 15057946854 \n浙江省金华市义乌市 义乌市北苑街道厚富小区20栋二单元"
            final_text = f"{base_text1} \n<code>{base_text} {user_name} {clean_phone}</code>"
            тугмабақафо = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Ба қафо", callback_data="Ба_кафо_суроға")]
            ])
            await пайём.message.delete()
            await пайём.message.answer_photo(photo=FSInputFile("surogaivu.jpg"), caption=final_text, reply_markup=тугмабақафо, parse_mode="HTML")
        if data == "суроғатоҷикистон":
            тугмабақафо = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Ба қафо", callback_data="Ба_кафо_суроға")]])
            await пайём.message.delete()
            await пайём.message.answer_photo(photo=FSInputFile("surogatojikiston.jpg"), caption="""🇹🇯 <b>СУРОҒАИ МО ДАР ШАХРИ ДУШАНБЕ\n Н. ИСМОИЛИ СОМОНИ КУЧАИ МЕХНАТ №5 ОШЁНАИ ЯКУМ ХУЧРАИ № 2\n КАРОРГОҲ ДАР БАРИ БОЗОРИ МЕХРГОН\n\nРЕЧАИ КОРИ АЗ СОАТИ  09:00 то 18:00\nРақамҳо барои тамос:</b> <code>116670614</code>🇨🇳🤝🇹🇯""", reply_markup=тугмабақафо, parse_mode="HTML")
        await пайём.answer()
@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: types.CallbackQuery, state: FSMContext):
    if await тафтиш_ва_пурсиши_обуна(call, send_message=False):  # send_message=False мегузорем, то паёми такрорӣ наояд
        try:
            await call.message.delete() # Кӯшиши нест кардани паёми кӯҳна
        except:
            pass
        await оғоз(call, state)   # Акнун танҳо объектро мефиристем, бе тағйир додани from_user
    else:
        await call.answer(_("Шумо ҳанӯз обуна нашудаед! ❌"), show_alert=True)
#sabti id korbat
@dp.message()  # Ягон филтр надорад, яъне ҳама чизро мегирад
async def echo_with_id(message: types.Message):
    # Гирифтани маълумот
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    text = message.text

    # Чоп кардан дар консоли Termux
    print(f"--- Паёми нав ---")
    print(f"Ном: {user_name}")
    print(f"ID: {user_id}")
    print(f"Матн: {text}")
#sabti id korbar
async def main():
    global pg_pool, redis_db
    pg_pool = await asyncpg.create_pool(user='u0_a135', database='botdb', host='127.0.0.1', port=5432)
    redis_db = redis.Redis(host='127.0.0.1', port=6379, decode_responses=True)
    dp.update.middleware(ЗабонMiddleware(i18n))
    dp.message.middleware(TypingMiddleware())
    dp.callback_query.middleware(TypingMiddleware())
    dp.message.outer_middleware(LoggerMiddleware())  #in sabti id 
    await dp.start_polling(bot, pg_pool=pg_pool, redis_db=redis_db)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот хомӯш шуд")
