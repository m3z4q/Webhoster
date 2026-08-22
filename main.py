import os, json, uuid, secrets, threading, logging, datetime, shutil, zipfile, io, base64
from flask import Flask, send_from_directory
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ─── CONFIG ────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
DATA_FILE = "data.json"
SITES_DIR = "sites"
FORCE_SUB_FILE = "force_sub.json"
# ──────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

os.makedirs(SITES_DIR, exist_ok=True)

# ─── JSON Database ─────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"users": {}, "sites": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_force_sub():
    if os.path.exists(FORCE_SUB_FILE):
        with open(FORCE_SUB_FILE, "r") as f:
            return json.load(f)
    return {"channel": None}

def save_force_sub(data):
    with open(FORCE_SUB_FILE, "w") as f:
        json.dump(data, f)

# ─── Stylish Keyboard ──────────────────────────────────────────
def user_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📤 Upload HTML"), KeyboardButton("📦 Upload ZIP")],
        [KeyboardButton("🌐 My Website"), KeyboardButton("❓ Help")],
        [KeyboardButton("📊 Status")]
    ], resize_keyboard=True)

def owner_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📤 Upload HTML"), KeyboardButton("📦 Upload ZIP")],
        [KeyboardButton("🌐 My Website"), KeyboardButton("❓ Help")],
        [KeyboardButton("📊 Status")],
        [KeyboardButton("⚙️ Admin Panel")]
    ], resize_keyboard=True)

# ─── Force Sub Check ──────────────────────────────────────────
async def check_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    force_data = load_force_sub()
    channel = force_data.get("channel")
    if not channel:
        return True
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{channel}", user_id=user_id)
        if member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            return True
        await update.message.reply_text(
            f"╔══════════════════════╗\n"
            f"     ❌ FORCE JOIN ❌\n"
            f"╚══════════════════════╝\n\n"
            f"✨ *Join our channel first!*\n"
            f"👇 Tap below to join\n\n"
            f"👉 [🔗 Join @{channel}](https://t.me/{channel})\n\n"
            f"After joining, type /start again ✅",
            parse_mode="Markdown", disable_web_page_preview=True
        )
        return False
    except:
        return True

# ─── Flask Web Server ─────────────────────────────────────────
app = Flask(__name__)

@app.route("/")
def home():
    return "<h2 style='font-family:sans-serif;color:#2ecc71;text-align:center;padding-top:40px'>🤖 Website Hoster Bot is Alive!</h2>"

@app.route("/<site_id>")
def serve_site(site_id):
    site_path = os.path.join(SITES_DIR, site_id)
    index_path = os.path.join(site_path, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(site_path, "index.html")
    return "<h2 style='font-family:sans-serif;color:#e74c3c;text-align:center'>❌ Site not found</h2>", 404

@app.route("/<site_id>/<path:subpath>")
def serve_file(site_id, subpath):
    site_path = os.path.join(SITES_DIR, site_id)
    file_path = os.path.join(site_path, subpath)
    real_sites = os.path.realpath(SITES_DIR)
    real_file = os.path.realpath(file_path)
    if not real_file.startswith(real_sites):
        return "403 Forbidden", 403
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path))
    return "404 Not Found", 404

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ─── Helpers ───────────────────────────────────────────────────
def get_kb(user_id):
    return owner_keyboard() if user_id == OWNER_ID else user_keyboard()

def stylish_header(title, emoji="🚀"):
    return (
        f"╔══════════════════════╗\n"
        f"   {emoji} {title}\n"
        f"╚══════════════════════╝\n"
    )

# ─── Start ─────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = load_data()

    if not await check_force_sub(update, context):
        return

    # New user?
    if str(user.id) not in db["users"]:
        db["users"][str(user.id)] = {
            "name": user.full_name,
            "username": user.username or "N/A",
            "joined": datetime.datetime.now().isoformat()
        }
        save_data(db)
        if OWNER_ID and user.id != OWNER_ID:
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"╔══════════════════════╗\n"
                    f"     🆕 NEW USER\n"
                    f"╚══════════════════════╝\n\n"
                    f"👤 *Name:* {user.full_name}\n"
                    f"📛 *Username:* @{user.username or 'N/A'}\n"
                    f"🆔 *ID:* `{user.id}`\n"
                    f"👥 *Total:* {len(db['users'])}",
                    parse_mode="Markdown"
                )
            except:
                pass

    text = (
        f"{stylish_header('WELCOME BACK' if str(user.id) in db['sites'] else 'WELCOME')}\n\n"
        f"👋 *Hey {user.first_name}!*\n\n"
        f"📤 Send me HTML code or a ZIP file\n"
        f"🌐 I'll host it live on the web!\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💡 *Each user = 1 website*\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"👇 *Use the buttons below:*"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_kb(user.id))

# ─── Upload: HTML ──────────────────────────────────────────────
async def upload_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return

    user_id = str(update.effective_user.id)
    db = load_data()

    if user_id in db["sites"]:
        site = db["sites"][user_id]
        await update.message.reply_text(
            f"{stylish_header('LIMIT REACHED', '⚠️')}\n\n"
            f"❌ You *already* have a website!\n\n"
            f"🔗 {site['url']}\n\n"
            f"📌 *One user = one website only.*",
            parse_mode="Markdown"
        )
        return

    context.user_data["awaiting_html"] = True
    context.user_data["awaiting_zip"] = False

    await update.message.reply_text(
        f"{stylish_header('SEND HTML', '📝')}\n\n"
        f"Paste your HTML code below:\n\n"
        f"```html\n"
        f"<!DOCTYPE html>\n"
        f"<html>\n"
        f"<head>\n"
        f"  <title>My Site</title>\n"
        f"</head>\n"
        f"<body>\n"
        f"  <h1>Hello!</h1>\n"
        f"</body>\n"
        f"</html>\n"
        f"```\n\n"
        f"❌ Tap *Cancel* to abort",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Cancel")]], resize_keyboard=True
        )
    )

# ─── Upload: ZIP ───────────────────────────────────────────────
async def upload_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return

    user_id = str(update.effective_user.id)
    db = load_data()

    if user_id in db["sites"]:
        site = db["sites"][user_id]
        await update.message.reply_text(
            f"{stylish_header('LIMIT REACHED', '⚠️')}\n\n"
            f"❌ You *already* have a website!\n\n"
            f"🔗 {site['url']}\n\n"
            f"📌 *One user = one website only.*",
            parse_mode="Markdown"
        )
        return

    context.user_data["awaiting_zip"] = True
    context.user_data["awaiting_html"] = False

    await update.message.reply_text(
        f"{stylish_header('SEND ZIP', '📦')}\n\n"
        f"Send me a `.zip` file containing:\n\n"
        f"📄 `index.html` *(required)*\n"
        f"🎨 `style.css` *(optional)*\n"
        f"⚡ `script.js` *(optional)*\n"
        f"🖼️ images/ *(optional)*\n\n"
        f"✅ *Everything will work together!*\n\n"
        f"❌ Tap *Cancel* to abort",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Cancel")]], resize_keyboard=True
        )
    )

# ─── Handle HTML Text ──────────────────────────────────────────
async def handle_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_html"):
        return

    html = update.message.text.strip()

    if html == "❌ Cancel":
        context.user_data["awaiting_html"] = False
        context.user_data["awaiting_zip"] = False
        await update.message.reply_text(
            f"{stylish_header('CANCELLED', '❌')}",
            parse_mode="Markdown", reply_markup=get_kb(update.effective_user.id)
        )
        return

    if not html.startswith(("<", "<!")):
        await update.message.reply_text("❌ That's not HTML! Code should start with `<` or `<!DOCTYPE`")
        return

    msg = await update.message.reply_text("⏳ *Deploying your website...*", parse_mode="Markdown")

    try:
        user_id = str(update.effective_user.id)
        db = load_data()

        if user_id in db["sites"]:
            await msg.edit_text("❌ You already have a site!")
            context.user_data["awaiting_html"] = False
            return

        site_id = secrets.token_hex(12)
        site_dir = os.path.join(SITES_DIR, site_id)
        os.makedirs(site_dir, exist_ok=True)

        with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

        base_url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{os.environ.get('PORT', 8080)}")
        site_url = f"{base_url}/{site_id}"

        db["sites"][user_id] = {
            "site_id": site_id, "url": site_url,
            "created": datetime.datetime.now().isoformat(),
            "user_name": update.effective_user.full_name,
            "type": "html"
        }
        save_data(db)
        context.user_data["awaiting_html"] = False

        if OWNER_ID and update.effective_user.id != OWNER_ID:
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"╔══════════════════════╗\n"
                    f"   📤 NEW SITE (HTML)\n"
                    f"╚══════════════════════╝\n\n"
                    f"👤 {update.effective_user.full_name}\n"
                    f"🆔 `{update.effective_user.id}`\n"
                    f"🔗 {site_url}",
                    parse_mode="Markdown"
                )
            except:
                pass

        await msg.edit_text(
            f"╔══════════════════════╗\n"
            f"    ✅  D E P L O Y E D\n"
            f"╚══════════════════════╝\n\n"
            f"🌐 *Your website is LIVE!*\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 [Open Website →]({site_url})\n"
            f"📋 `{site_url}`\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 *Forms, links, everything works!*",
            parse_mode="Markdown",
            disable_web_page_preview=False
        )
        await update.message.reply_text("👇 *Use buttons below*", parse_mode="Markdown", reply_markup=get_kb(update.effective_user.id))

    except Exception as e:
        logger.exception("HTML deploy error")
        await msg.edit_text(f"❌ *Error:* `{str(e)[:200]}`", parse_mode="Markdown")

# ─── Handle ZIP Files ──────────────────────────────────────────
async def handle_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_zip"):
        return

    document = update.message.document
    if not document or not document.file_name or not document.file_name.lower().endswith(".zip"):
        await update.message.reply_text("❌ Please send a valid `.zip` file!")
        return

    msg = await update.message.reply_text("⏳ *Extracting & deploying ZIP...*", parse_mode="Markdown")

    try:
        user_id = str(update.effective_user.id)
        db = load_data()

        if user_id in db["sites"]:
            await msg.edit_text("❌ You already have a site!")
            context.user_data["awaiting_zip"] = False
            return

        # Download ZIP
        file = await context.bot.get_file(document.file_id)
        zip_bytes = io.BytesIO()
        await file.download_to_memory(zip_bytes)
        zip_bytes.seek(0)

        # Validate ZIP
        try:
            with zipfile.ZipFile(zip_bytes, 'r') as zf:
                if zf.testzip():
                    await msg.edit_text("❌ ZIP file is corrupted!")
                    return
                file_list = zf.namelist()
                if "index.html" not in file_list and "./index.html" not in file_list:
                    await msg.edit_text("❌ ZIP must contain `index.html` at root level!", parse_mode="Markdown")
                    return
        except zipfile.BadZipFile:
            await msg.edit_text("❌ Not a valid ZIP file!")
            return

        zip_bytes.seek(0)

        # Deploy
        site_id = secrets.token_hex(12)
        site_dir = os.path.join(SITES_DIR, site_id)
        os.makedirs(site_dir, exist_ok=True)

        with zipfile.ZipFile(zip_bytes, 'r') as zf:
            zf.extractall(site_dir)

        base_url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{os.environ.get('PORT', 8080)}")
        site_url = f"{base_url}/{site_id}"

        db["sites"][user_id] = {
            "site_id": site_id, "url": site_url,
            "created": datetime.datetime.now().isoformat(),
            "user_name": update.effective_user.full_name,
            "type": "zip"
        }
        save_data(db)
        context.user_data["awaiting_zip"] = False

        # Notify owner
        if OWNER_ID and update.effective_user.id != OWNER_ID:
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"╔══════════════════════╗\n"
                    f"   📤 NEW SITE (ZIP)\n"
                    f"╚══════════════════════╝\n\n"
                    f"👤 {update.effective_user.full_name}\n"
                    f"🆔 `{update.effective_user.id}`\n"
                    f"📦 Files: {len(file_list)}\n"
                    f"🔗 {site_url}",
                    parse_mode="Markdown"
                )
            except:
                pass

        await msg.edit_text(
            f"╔══════════════════════╗\n"
            f"    ✅  D E P L O Y E D\n"
            f"╚══════════════════════╝\n\n"
            f"🌐 *Your ZIP website is LIVE!*\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 [Open Website →]({site_url})\n"
            f"📋 `{site_url}`\n"
            f"📦 `{len(file_list)}` files extracted\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 *HTML + CSS + JS sab kaam karega!*",
            parse_mode="Markdown",
            disable_web_page_preview=False
        )
        await update.message.reply_text("👇 *Use buttons below*", parse_mode="Markdown", reply_markup=get_kb(update.effective_user.id))

    except Exception as e:
        logger.exception("ZIP deploy error")
        await msg.edit_text(f"❌ *Error:* `{str(e)[:200]}`", parse_mode="Markdown")

# ─── My Website ────────────────────────────────────────────────
async def my_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return

    user_id = str(update.effective_user.id)
    db = load_data()

    if user_id in db["sites"]:
        site = db["sites"][user_id]
        await update.message.reply_text(
            f"╔══════════════════════╗\n"
            f"     🌐  MY WEBSITE\n"
            f"╚══════════════════════╝\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 [Open Website →]({site['url']})\n"
            f"📋 `{site['url']}`\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"📅 Created: `{site['created'][:10]}`\n"
            f"📦 Type: `{site.get('type','html')}`",
            parse_mode="Markdown",
            disable_web_page_preview=False
        )
    else:
        await update.message.reply_text(
            f"╔══════════════════════╗\n"
            f"    ❌ NO WEBSITE\n"
            f"╚══════════════════════╝\n\n"
            f"You haven't uploaded anything yet!\n\n"
            f"👇 Tap *📤 Upload HTML* or *📦 Upload ZIP* to get started!",
            parse_mode="Markdown"
        )

# ─── Help ──────────────────────────────────────────────────────
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return

    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"   📖  H O W  T O\n"
        f"╚══════════════════════╝\n\n"
        f"━━━ *Upload HTML* ━━━\n"
        f"1️⃣ Tap *📤 Upload HTML*\n"
        f"2️⃣ Paste your HTML code\n"
        f"3️⃣ Get your live URL ✅\n\n"
        f"━━━ *Upload ZIP* ━━━\n"
        f"1️⃣ Tap *📦 Upload ZIP*\n"
        f"2️⃣ Send a .zip file\n"
        f"   (index.html + CSS + JS)\n"
        f"3️⃣ Get your live URL ✅\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *1 website per user*\n"
        f"📌 *24/7 online (bot chal raha hai tab tak)*\n"
        f"━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

# ─── Status ────────────────────────────────────────────────────
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_force_sub(update, context):
        return
    db = load_data()
    total_users = len(db["users"])
    total_sites = len(db["sites"])
    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"    📊  BOT  STATUS\n"
        f"╚══════════════════════╝\n\n"
        f"👥 *Total Users:* `{total_users}`\n"
        f"🌐 *Total Sites:* `{total_sites}`\n"
        f"⚡ *Status:* ✅ Online\n\n"
        f"━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

# ─── Button Router ─────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    handlers = {
        "📤 Upload HTML": upload_html,
        "📦 Upload ZIP": upload_zip,
        "🌐 My Website": my_site,
        "❓ Help": help_cmd,
        "📊 Status": status,
        "❌ Cancel": lambda u, c: cancel_handler(u, c),
    }

    if text in handlers:
        return await handlers[text](update, context)

    if text == "⚙️ Admin Panel" and uid == OWNER_ID:
        return await admin_panel(update, context)

    await update.message.reply_text("👇 *Use the buttons below!*", parse_mode="Markdown", reply_markup=get_kb(uid))

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_html"] = False
    context.user_data["awaiting_zip"] = False
    await update.message.reply_text(
        f"{stylish_header('CANCELLED', '❌')}",
        parse_mode="Markdown", reply_markup=get_kb(update.effective_user.id)
    )

# ─── Admin Panel ───────────────────────────────────────────────
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    db = load_data()
    force_data = load_force_sub()
    channel = force_data.get("channel", "Not set")

    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"     👑 ADMIN PANEL\n"
        f"╚══════════════════════╝\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📢 *Force Sub:* @{channel}\n"
        f"👥 *Users:* `{len(db['users'])}`\n"
        f"🌐 *Sites:* `{len(db['sites'])}`\n"
        f"🆔 *Your ID:* `{OWNER_ID}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"━━━ *Commands* ━━━\n\n"
        f"`/addch @channel` — Set force sub\n"
        f"`/delch` — Remove force sub\n"
        f"`/stats` — List all users & sites\n"
        f"`/broadcast msg` — DM everyone\n"
        f"`/deluser id` — Delete user's site\n"
        f"━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

# ─── Admin Commands ────────────────────────────────────────────
async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: `/addch @channelusername`", parse_mode="Markdown")
    channel = context.args[0].lstrip("@")
    force_data = load_force_sub()
    force_data["channel"] = channel
    save_force_sub(force_data)
    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"     ✅ FORCE SUB SET\n"
        f"╚══════════════════════╝\n\n"
        f"📢 Channel: @{channel}\n\n"
        f"Users must now join to use bot!",
        parse_mode="Markdown"
    )

async def del_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    force_data = load_force_sub()
    force_data["channel"] = None
    save_force_sub(force_data)
    await update.message.reply_text("✅ *Force sub removed!*", parse_mode="Markdown")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    db = load_data()
    text = (
        f"╔══════════════════════╗\n"
        f"   👑 FULL STATS\n"
        f"╚══════════════════════╝\n\n"
        f"━━━ *Users ({len(db['users'])}):* ━━━\n\n"
    )
    for uid, uinfo in db["users"].items():
        has = "✅" if uid in db["sites"] else "❌"
        text += f"├ `{uid}` {uinfo['name']} {has}\n"
    text += "\n━━━ *Sites:* ━━━\n\n"
    for uid, sinfo in db["sites"].items():
        text += f"├ `{uid[:8]}..` → {sinfo['url']}\n"

    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i+4000], parse_mode="Markdown")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: `/broadcast Your message`", parse_mode="Markdown")
    msg_text = " ".join(context.args)
    db = load_data()
    success = failed = 0
    await update.message.reply_text(f"📤 Broadcasting to {len(db['users'])} users...")
    for uid in db["users"]:
        try:
            await context.bot.send_message(
                int(uid),
                f"📢 *Broadcast from Admin:*\n\n{msg_text}",
                parse_mode="Markdown"
            )
            success += 1
        except:
            failed += 1
    await update.message.reply_text(f"✅ Sent: {success}  ❌ Failed: {failed}")

async def del_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: `/deluser user_id`", parse_mode="Markdown")
    target = context.args[0]
    db = load_data()
    if target in db["sites"]:
        site_id = db["sites"][target]["site_id"]
        site_dir = os.path.join(SITES_DIR, site_id)
        if os.path.exists(site_dir):
            shutil.rmtree(site_dir)
        del db["sites"][target]
        save_data(db)
        await update.message.reply_text(f"✅ User `{target}`'s site deleted!", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ User has no site.", parse_mode="Markdown")

# ─── Error Handler ─────────────────────────────────────────────
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# ─── MAIN ──────────────────────────────────────────────────────
def main():
    threading.Thread(target=run_flask, daemon=True).start()

    app_tele = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app_tele.add_handler(CommandHandler("start", start))
    app_tele.add_handler(CommandHandler("addch", add_channel))
    app_tele.add_handler(CommandHandler("delch", del_channel))
    app_tele.add_handler(CommandHandler("stats", stats_cmd))
    app_tele.add_handler(CommandHandler("broadcast", broadcast))
    app_tele.add_handler(CommandHandler("deluser", del_user))
    app_tele.add_handler(CommandHandler("help", help_cmd))

    # Button text handler
    app_tele.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Regex(
            r'^(📤 Upload HTML|📦 Upload ZIP|🌐 My Website|❓ Help|📊 Status|⚙️ Admin Panel|❌ Cancel)$'
        ), button_handler
    ))

    # HTML text handler
    app_tele.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Document.Category("text"),
        handle_html
    ))

    # ZIP document handler
    app_tele.add_handler(MessageHandler(
        filters.Document.FileExtension("zip"),
        handle_zip
    ))

    # Fallback text handler
    app_tele.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_html))

    # Errors
    app_tele.add_error_handler(error_handler)

    logger.info("🤖 Bot + Web Server running...")
    app_tele.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
