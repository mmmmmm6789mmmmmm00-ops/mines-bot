import time
import random
import sqlite3
import requests
from datetime import datetime, date, timedelta


# ═══════════════════════════════════════════════════════════
#                      ⚙️ КОНФИГ
# ═══════════════════════════════════════════════════════════

BOT_TOKEN = "8914262534:AAEiHbiFr2nRtjXO-qe8X2o0QggkRbaGOws"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

START_BALANCE = 10_000
MIN_BET = 100

GRID_SIZE = 5
MINES_COUNT = 3

DAILY_BONUS = 5_000
HOUR_BONUS = 500
REF_BONUS = 25_000
STREAK_BONUS_5 = 50_000
STREAK_BONUS_10 = 500_000

DB_PATH = "mines.db"


# ═══════════════════════════════════════════════════════════
#                    💎 ЭКОНОМИКА
# ═══════════════════════════════════════════════════════════

MULTIPLIERS = {
    1: 1.14,   2: 1.30,   3: 1.48,   4: 1.72,
    5: 2.03,   6: 2.43,   7: 2.96,   8: 3.65,
    9: 4.60,  10: 5.90,  11: 7.73,  12: 10.35,
   13: 14.20, 14: 19.98, 15: 28.96, 16: 43.44,
   17: 67.91, 18: 111.38, 19: 194.93, 20: 372.6,
   21: 800.0, 22: 2300.0,
}


def get_max_bet(balance):
    return min(max(1000, int(balance * 0.5)), 10_000_000)


def format_num(n):
    if n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.2f}K"
    return str(n)


# ═══════════════════════════════════════════════════════════
#                      💾 БАЗА
# ═══════════════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 10000,
            games_played INTEGER DEFAULT 0,
            games_won INTEGER DEFAULT 0,
            max_win INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0,
            total_lost INTEGER DEFAULT 0,
            best_streak INTEGER DEFAULT 0,
            current_streak INTEGER DEFAULT 0,
            last_bonus TEXT DEFAULT '',
            last_hour_bonus REAL DEFAULT 0,
            referrer_id INTEGER DEFAULT 0,
            ref_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


def get_user(user_id, username=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO users (user_id, username, balance, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username or "anon", START_BALANCE, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        return {
            "user_id": user_id, "username": username or "anon",
            "balance": START_BALANCE, "games_played": 0, "games_won": 0,
            "max_win": 0, "total_won": 0, "total_lost": 0,
            "best_streak": 0, "current_streak": 0, "last_bonus": "",
            "last_hour_bonus": 0, "referrer_id": 0, "ref_count": 0,
            "created_at": datetime.now().isoformat()
        }
    user = dict(row)
    conn.close()
    return user


def update_balance(user_id, delta):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
    conn.commit()
    conn.close()


def inc_stat(user_id, field, value=1):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"UPDATE users SET {field} = {field} + ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()


def set_field(user_id, field, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()


def set_max_win(user_id, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE users SET max_win = ? WHERE user_id = ? AND max_win < ?",
                 (value, user_id, value))
    conn.commit()
    conn.close()


def get_top(limit=10):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT username, balance, games_won FROM users ORDER BY balance DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return rows


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT COUNT(*), SUM(games_played), SUM(games_won) FROM users"
    ).fetchone()
    conn.close()
    return row


# ═══════════════════════════════════════════════════════════
#                      📡 API
# ═══════════════════════════════════════════════════════════

def api(method, **params):
    try:
        r = requests.post(f"{API_URL}/{method}", json=params, timeout=15)
        return r.json()
    except Exception as e:
        print(f"API error: {e}")
        return {"ok": False}


def send_message(chat_id, text, keyboard=None):
    p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
         "disable_web_page_preview": True}
    if keyboard:
        p["reply_markup"] = keyboard
    return api("sendMessage", **p)


def edit_message(chat_id, message_id, text, keyboard=None):
    p = {"chat_id": chat_id, "message_id": message_id, "text": text,
         "parse_mode": "HTML", "disable_web_page_preview": True}
    if keyboard:
        p["reply_markup"] = keyboard
    return api("editMessageText", **p)


def answer_callback(callback_id, text=None, alert=False):
    p = {"callback_query_id": callback_id}
    if text:
        p["text"] = text
        p["show_alert"] = alert
    return api("answerCallbackQuery", **p)


# ═══════════════════════════════════════════════════════════
#                      ⌨️ КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════

def main_menu_kb():
    return {"inline_keyboard": [
        [{"text": "🎮 ИГРАТЬ", "callback_data": "play"}],
        [{"text": "🎁 Бонусы", "callback_data": "bonuses"},
         {"text": "👥 Друзья", "callback_data": "friends"}],
        [{"text": "👤 Профиль", "callback_data": "profile"},
         {"text": "🏆 Топ", "callback_data": "top"}],
        [{"text": "📖 Правила", "callback_data": "rules"},
         {"text": "📊 Стата", "callback_data": "global_stats"}],
    ]}


def bet_kb(balance):
    max_bet = get_max_bet(balance)
    suggestions = sorted(set([
        100, 500, 1000, 5000,
        int(max_bet * 0.10),
        int(max_bet * 0.25),
        int(max_bet * 0.50),
        int(max_bet * 0.75),
        max_bet,
    ]))
    suggestions = [s for s in suggestions if MIN_BET <= s <= max_bet]

    rows = []
    row = []
    for b in suggestions:
        row.append({"text": f"💰 {format_num(b)}", "callback_data": f"bet_{b}"})
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)

    rows.append([
        {"text": "🔥 ВСЁ", "callback_data": f"bet_{min(balance, max_bet)}"},
        {"text": "✏️ Своя", "callback_data": "bet_custom"},
    ])
    rows.append([{"text": "🔙 Назад", "callback_data": "main_menu"}])
    return {"inline_keyboard": rows}


def game_kb(game):
    opened = game["opened"]
    boom = game.get("boom")
    total = GRID_SIZE * GRID_SIZE
    rows, row = [], []
    for i in range(total):
        if i in opened:
            t, cb = "💎", "noop"
        elif boom is not None and i == boom:
            t, cb = "💥", "noop"
        elif boom is not None and i in game["mines"]:
            t, cb = "💣", "noop"
        else:
            t, cb = "⬜", f"open_{i}"
        row.append({"text": t, "callback_data": cb})
        if len(row) == GRID_SIZE:
            rows.append(row); row = []

    if boom is None and game["opened"]:
        win = int(game["bet"] * game["multiplier"])
        rows.append([{"text": f"💸 ЗАБРАТЬ {format_num(win)}", "callback_data": "cashout"}])
        rows.append([{"text": "🎲 Открыть ещё", "callback_data": "noop"}])
    return {"inline_keyboard": rows}


# ═══════════════════════════════════════════════════════════
#                      🎨 ТЕКСТ
# ═══════════════════════════════════════════════════════════

def render_game(game):
    opened = len(game["opened"])
    mult = game["multiplier"]
    safe_total = GRID_SIZE**2 - MINES_COUNT

    if game.get("boom") is not None:
        return (f"💥 <b>БУМ! Мина!</b>\n"
                f"━━━━━━━━━━━━━━━━━\n"
                f"Ставка: <b>{format_num(game['bet'])}</b> 🪙\n"
                f"Открыто: <b>{opened}</b>\n"
                f"Потеряно: <b>{format_num(game['bet'])}</b> 🪙")

    left = safe_total - opened
    next_mult = MULTIPLIERS.get(opened + 1, mult)

    return (f"🎮 <b>МИНЫ {GRID_SIZE}x{GRID_SIZE}</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"💣 Мин: <b>{MINES_COUNT}</b> · 💎 Открыто: <b>{opened}/{safe_total}</b>\n"
            f"🎯 Осталось: <b>{left}</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"📈 Множитель: <b>x{mult:.2f}</b>\n"
            f"⏭ Следующий: <b>x{next_mult:.2f}</b>\n"
            f"💰 Ставка: <b>{format_num(game['bet'])}</b> 🪙\n"
            f"🏆 Забрать: <b>{format_num(int(game['bet']*mult))}</b> 🪙")


# ═══════════════════════════════════════════════════════════
#                      🎮 ИГРА
# ═══════════════════════════════════════════════════════════

active_games = {}
waiting_bet = set()


def start_game(chat_id, msg_id, user, bet):
    uid = user["id"]
    u = get_user(uid, user.get("username"))
    max_bet = get_max_bet(u["balance"])

    if bet < MIN_BET:
        edit_message(chat_id, msg_id, f"❌ Минимум {format_num(MIN_BET)} 🪙", main_menu_kb()); return
    if bet > max_bet:
        edit_message(chat_id, msg_id,
            f"❌ Максимум: <b>{format_num(max_bet)}</b> 🪙\n"
            f"(50% от баланса {format_num(u['balance'])} 🪙)",
            main_menu_kb()); return
    if bet > u["balance"]:
        edit_message(chat_id, msg_id, "❌ Мало денег!", main_menu_kb()); return

    update_balance(uid, -bet)
    inc_stat(uid, "games_played")

    mines = set(random.sample(range(GRID_SIZE**2), MINES_COUNT))
    game = {"bet": bet, "mines": mines, "opened": set(),
            "multiplier": 1.0, "boom": None}
    active_games[uid] = game
    edit_message(chat_id, msg_id, render_game(game), game_kb(game))


def do_open(chat_id, msg_id, user, idx, cb_id):
    uid = user["id"]
    game = active_games.get(uid)
    if not game or game.get("boom") is not None:
        answer_callback(cb_id, "Игра окончена", True); return
    if idx in game["opened"]:
        answer_callback(cb_id, "Уже открыта"); return
    if len(game["opened"]) >= GRID_SIZE**2 - MINES_COUNT:
        answer_callback(cb_id, "Все безопасные открыты!", True); return

    if idx in game["mines"]:
        game["boom"] = idx
        answer_callback(cb_id, "💥 БУМ!")
        edit_message(chat_id, msg_id, render_game(game), game_kb(game))
        time.sleep(2)
        inc_stat(uid, "total_lost", game["bet"])
        set_field(uid, "current_streak", 0)
        u = get_user(uid, user.get("username"))
        edit_message(chat_id, msg_id,
            f"💥 <b>Мина!</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"Потеряно: <b>{format_num(game['bet'])}</b> 🪙\n"
            f"Баланс: <b>{format_num(u['balance'])}</b> 🪙\n"
            f"🔥 Серия сброшена",
            {"inline_keyboard": [
                [{"text": "🎮 Ещё", "callback_data": "play"}],
                [{"text": "🏠 Меню", "callback_data": "main_menu"}]]})
        active_games.pop(uid, None)
        return

    game["opened"].add(idx)
    step = len(game["opened"])
    game["multiplier"] = MULTIPLIERS.get(step, game["multiplier"])

    if step == GRID_SIZE**2 - MINES_COUNT:
        win = int(game["bet"] * game["multiplier"])
        update_balance(uid, win)
        inc_stat(uid, "games_won")
        inc_stat(uid, "total_won", win)
        set_max_win(uid, win)

        u = get_user(uid, user.get("username"))
        new_streak = u["current_streak"] + 1
        set_field(uid, "current_streak", new_streak)
        if new_streak > u["best_streak"]:
            set_field(uid, "best_streak", new_streak)

        bonus_text = ""
        if new_streak == 5:
            update_balance(uid, STREAK_BONUS_5)
            bonus_text = f"\n🎁 <b>+{format_num(STREAK_BONUS_5)}</b> за 5 побед!"
        elif new_streak == 10:
            update_balance(uid, STREAK_BONUS_10)
            bonus_text = f"\n🎁 <b>+{format_num(STREAK_BONUS_10)}</b> за 10 побед!"

        answer_callback(cb_id, "🎉 МАКСИМУМ!")
        edit_message(chat_id, msg_id,
            f"🎉 <b>ПОЛНАЯ ПОБЕДА!</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"Выигрыш: <b>+{format_num(win)}</b> 🪙\n"
            f"Множитель: <b>x{game['multiplier']:.2f}</b>\n"
            f"🔥 Серия: <b>{new_streak}</b>{bonus_text}",
            {"inline_keyboard": [
                [{"text": "🎮 Ещё", "callback_data": "play"}],
                [{"text": "🏠 Меню", "callback_data": "main_menu"}]]})
        active_games.pop(uid, None)
        return

    answer_callback(cb_id, f"💎 x{game['multiplier']:.2f}")
    edit_message(chat_id, msg_id, render_game(game), game_kb(game))


def do_cashout(chat_id, msg_id, user, cb_id):
    uid = user["id"]
    game = active_games.get(uid)
    if not game or game.get("boom") is not None:
        answer_callback(cb_id, "Не активна", True); return
    if not game["opened"]:
        answer_callback(cb_id, "Открой клетку!", True); return

    win = int(game["bet"] * game["multiplier"])
    profit = win - game["bet"]
    update_balance(uid, win)
    inc_stat(uid, "games_won")
    inc_stat(uid, "total_won", win)
    set_max_win(uid, win)

    u = get_user(uid, user.get("username"))
    new_streak = u["current_streak"] + 1
    set_field(uid, "current_streak", new_streak)
    if new_streak > u["best_streak"]:
        set_field(uid, "best_streak", new_streak)

    bonus_text = ""
    if new_streak == 5:
        update_balance(uid, STREAK_BONUS_5)
        bonus_text = f"\n🎁 <b>+{format_num(STREAK_BONUS_5)}</b> за 5 побед!"
    elif new_streak == 10:
        update_balance(uid, STREAK_BONUS_10)
        bonus_text = f"\n🎁 <b>+{format_num(STREAK_BONUS_10)}</b> за 10 побед!"

    answer_callback(cb_id, f"💸 +{format_num(win)}")
    edit_message(chat_id, msg_id,
        f"💸 <b>Забрал!</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Ставка: <b>{format_num(game['bet'])}</b> 🪙\n"
        f"Множитель: <b>x{game['multiplier']:.2f}</b>\n"
        f"Выигрыш: <b>+{format_num(win)}</b> 🪙\n"
        f"Профит: <b>{'+' if profit >= 0 else ''}{format_num(profit)}</b> 🪙\n"
        f"Баланс: <b>{format_num(u['balance'] + win)}</b> 🪙\n"
        f"🔥 Серия: <b>{new_streak}</b>{bonus_text}",
        {"inline_keyboard": [
            [{"text": "🎮 Ещё", "callback_data": "play"}],
            [{"text": "🏠 Меню", "callback_data": "main_menu"}]]})
    active_games.pop(uid, None)


# ═══════════════════════════════════════════════════════════
#                      📥 ОБРАБОТКА
# ═══════════════════════════════════════════════════════════

def handle_message(m):
    chat_id = m["chat"]["id"]; user = m["from"]; uid = user["id"]
    text = m.get("text", "")

    if text.startswith("/start"):
        parts = text.split()
        referrer = 0
        if len(parts) > 1 and parts[1].startswith("ref_"):
            try:
                referrer = int(parts[1].replace("ref_", ""))
            except ValueError:
                referrer = 0

        u = get_user(uid, user.get("username"))

        if referrer and referrer != uid and u["referrer_id"] == 0:
            ref_user = get_user(referrer)
            if ref_user["user_id"] == referrer:
                set_field(uid, "referrer_id", referrer)
                update_balance(uid, REF_BONUS)
                update_balance(referrer, REF_BONUS)
                inc_stat(referrer, "ref_count")
                send_message(referrer,
                    f"👥 <b>Новый друг по твоей ссылке!</b>\n"
                    f"Бонус: <b>+{format_num(REF_BONUS)}</b> 🪙")

        send_message(chat_id,
            f"👋 <b>{user.get('first_name','игрок')}</b>, привет!\n\n"
            f"🎮 Игра <b>«Мины»</b> — лютые вирты\n"
            f"💰 Баланс: <b>{format_num(u['balance'])}</b> 🪙\n"
            f"🔥 Серия: <b>{u['current_streak']}</b>\n\n"
            f"Забирай бонусы, играй, фарми миллионы 💎",
            main_menu_kb()); return

    if uid in waiting_bet and text.isdigit():
        waiting_bet.discard(uid)
        res = send_message(chat_id, "🎮 Создаю...")
        if res.get("ok"):
            start_game(chat_id, res["result"]["message_id"], user, int(text))


def handle_callback(c):
    chat_id = c["message"]["chat"]["id"]
    msg_id = c["message"]["message_id"]
    user = c["from"]; uid = user["id"]
    data = c["data"]; cb_id = c["id"]

    if data == "main_menu":
        answer_callback(cb_id)
        u = get_user(uid, user.get("username"))
        edit_message(chat_id, msg_id,
            f"🏠 <b>Меню</b>\n\n💰 Баланс: <b>{format_num(u['balance'])}</b> 🪙",
            main_menu_kb())

    elif data == "rules":
        answer_callback(cb_id)
        edit_message(chat_id, msg_id,
            f"📖 <b>Правила</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"• Поле <b>{GRID_SIZE}x{GRID_SIZE}</b>, <b>{MINES_COUNT} мины</b> 💣\n"
            f"• Открывай клетки — растёт множитель 📈\n"
            f"• Забирай в любой момент 💸\n"
            f"• Мина — теряешь ставку 💥\n"
            f"• Открыл всё поле — x2300 🎉\n\n"
            f"🎁 <b>Бонусы:</b>\n"
            f"• Ежедневный: +{format_num(DAILY_BONUS)} 🪙\n"
            f"• Часовой: +{format_num(HOUR_BONUS)} 🪙\n"
            f"• За друга: +{format_num(REF_BONUS)} 🪙\n"
            f"• За 5 побед: +{format_num(STREAK_BONUS_5)} 🪙\n"
            f"• За 10 побед: +{format_num(STREAK_BONUS_10)} 🪙",
            {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "main_menu"}]]})

    elif data == "profile":
        answer_callback(cb_id)
        u = get_user(uid, user.get("username"))
        wr = (u["games_won"] / u["games_played"] * 100) if u["games_played"] else 0
        net = u["total_won"] - u["total_lost"]
        edit_message(chat_id, msg_id,
            f"👤 <b>Профиль</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"💰 Баланс: <b>{format_num(u['balance'])}</b> 🪙\n"
            f"🎮 Игр: <b>{u['games_played']}</b> · 🏆 Побед: <b>{u['games_won']}</b>\n"
            f"📊 Винрейт: <b>{wr:.1f}%</b>\n"
            f"💎 Макс. выигрыш: <b>{format_num(u['max_win'])}</b> 🪙\n"
            f"📈 Выиграно: <b>{format_num(u['total_won'])}</b> 🪙\n"
            f"📉 Проиграно: <b>{format_num(u['total_lost'])}</b> 🪙\n"
            f"💵 Итог: <b>{'+' if net >= 0 else ''}{format_num(net)}</b> 🪙\n"
            f"🔥 Серия: <b>{u['current_streak']}</b> (лучшая: <b>{u['best_streak']}</b>)\n"
            f"👥 Друзей: <b>{u['ref_count']}</b>",
            {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "main_menu"}]]})

    elif data == "top":
        answer_callback(cb_id)
        rows = get_top(10)
        medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
        lines = ["🏆 <b>ТОП-10</b>\n━━━━━━━━━━━━━━━━━\n"]
        for i, (name, bal, wins) in enumerate(rows):
            lines.append(f"{medals[i]} <b>{name or 'anon'}</b> — {format_num(bal)} 🪙")
        edit_message(chat_id, msg_id, "\n".join(lines),
            {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "main_menu"}]]})

    elif data == "global_stats":
        answer_callback(cb_id)
        tu, tg, tw = get_stats()
        tg = tg or 0; tw = tw or 0
        wr = (tw / tg * 100) if tg else 0
        edit_message(chat_id, msg_id,
            f"📊 <b>Глобальная стата</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"👥 Игроков: <b>{tu or 0}</b>\n"
            f"🎮 Игр: <b>{tg}</b>\n"
            f"🏆 Побед: <b>{tw}</b>\n"
            f"📈 Винрейт: <b>{wr:.1f}%</b>",
            {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "main_menu"}]]})

    elif data == "bonuses":
        answer_callback(cb_id)
        u = get_user(uid, user.get("username"))
        today = date.today().isoformat()
        now = time.time()
        daily_ready = u["last_bonus"] != today
        hour_ready = now - u["last_hour_bonus"] >= 3600

        edit_message(chat_id, msg_id,
            f"🎁 <b>Бонусы</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{'✅' if daily_ready else '⏳'} Ежедневный: <b>+{format_num(DAILY_BONUS)}</b> 🪙\n"
            f"{'✅' if hour_ready else '⏳'} Часовой: <b>+{format_num(HOUR_BONUS)}</b> 🪙",
            {"inline_keyboard": [
                [{"text": "🎁 Забрать всё", "callback_data": "claim_bonus"}],
                [{"text": "🔙 Назад", "callback_data": "main_menu"}]]})

    elif data == "claim_bonus":
        u = get_user(uid, user.get("username"))
        today = date.today().isoformat()
        now = time.time()
        total = 0
        msgs = []

        if u["last_bonus"] != today:
            total += DAILY_BONUS
            set_field(uid, "last_bonus", today)
            msgs.append(f"🎁 Ежедневный: +{format_num(DAILY_BONUS)}")

        if now - u["last_hour_bonus"] >= 3600:
            total += HOUR_BONUS
            set_field(uid, "last_hour_bonus", now)
            msgs.append(f"⏰ Часовой: +{format_num(HOUR_BONUS)}")

        if total == 0:
            answer_callback(cb_id, "❌ Всё уже забрано. Приходи позже!", True)
            return

        update_balance(uid, total)
        answer_callback(cb_id, f"✅ +{format_num(total)} 🪙", True)
        u2 = get_user(uid, user.get("username"))
        edit_message(chat_id, msg_id,
            f"✅ <b>Бонусы получены!</b>\n"
            f"━━━━━━━━━━━━━━━━━\n" + "\n".join(msgs) +
            f"\n\n💰 Баланс: <b>{format_num(u2['balance'])}</b> 🪙",
            {"inline_keyboard": [[{"text": "🎮 Играть", "callback_data": "play"}]]})

    elif data == "friends":
        answer_callback(cb_id)
        u = get_user(uid, user.get("username"))
        bot_info = api("getMe").get("result", {})
        bot_username = bot_info.get("username", "your_bot")
        link = f"https://t.me/{bot_username}?start=ref_{uid}"
        edit_message(chat_id, msg_id,
            f"👥 <b>Друзья</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"Приглашай друзей — получай <b>{format_num(REF_BONUS)}</b> 🪙 за каждого!\n\n"
            f"👥 Приглашено: <b>{u['ref_count']}</b>\n"
            f"💰 Заработано: <b>{format_num(u['ref_count'] * REF_BONUS)}</b> 🪙\n\n"
            f"🔗 Твоя ссылка:\n<code>{link}</code>",
            {"inline_keyboard": [
                [{"text": "🔙 Назад", "callback_data": "main_menu"}]]})

    elif data == "play":
        answer_callback(cb_id)
        u = get_user(uid, user.get("username"))
        max_bet = get_max_bet(u["balance"])
        edit_message(chat_id, msg_id,
            f"💰 Баланс: <b>{format_num(u['balance'])}</b> 🪙\n"
            f"📊 Лимит: <b>{format_num(max_bet)}</b> 🪙\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"Выбери ставку:",
            bet_kb(u["balance"]))

    elif data.startswith("bet_"):
        answer_callback(cb_id)
        try:
            bet = int(data.split("_")[1])
        except (ValueError, IndexError):
            return
        start_game(chat_id, msg_id, user, bet)

    elif data == "bet_custom":
        answer_callback(cb_id)
        waiting_bet.add(uid)
        u = get_user(uid, user.get("username"))
        max_bet = get_max_bet(u["balance"])
        edit_message(chat_id, msg_id,
            f"✏️ Напиши сумму от <b>{format_num(MIN_BET)}</b> до <b>{format_num(max_bet)}</b> 🪙",
            {"inline_keyboard": [[{"text": "🔙 Отмена", "callback_data": "play"}]]})

    elif data.startswith("open_"):
        do_open(chat_id, msg_id, user, int(data.split("_")[1]), cb_id)

    elif data == "cashout":
        do_cashout(chat_id, msg_id, user, cb_id)

    elif data == "noop":
        answer_callback(cb_id)


# ═══════════════════════════════════════════════════════════
#                      🚀 ЗАПУСК
# ═══════════════════════════════════════════════════════════

def main():
    init_db()
    print("🔍 Проверяю Telegram...")
    try:
        r = requests.post(f"{API_URL}/getMe", timeout=15).json()
        if not r.get("ok"):
            print(f"❌ Ошибка: {r}"); return
        b = r["result"]
        print(f"✅ Подключено: @{b['username']} ({b['first_name']})")
    except Exception as e:
        print(f"❌ Нет связи: {e}")
        print("💡 Включи VPN и запусти снова.")
        return

    api("deleteWebhook")
    print("✅ Бот запущен\n")

    offset = 0
    while True:
        try:
            r = requests.get(f"{API_URL}/getUpdates",
                params={"offset": offset, "timeout": 30}, timeout=40).json()
            if not r.get("ok"):
                time.sleep(3); continue
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                try:
                    if "message" in u: handle_message(u["message"])
                    elif "callback_query" in u: handle_callback(u["callback_query"])
                except Exception as e:
                    print(f"Ошибка: {e}")
        except requests.exceptions.Timeout:
            continue
        except KeyboardInterrupt:
            print("\n👋 Стоп"); break
        except Exception as e:
            print(f"Ошибка: {e}"); time.sleep(3)


if __name__ == "__main__":
    main()