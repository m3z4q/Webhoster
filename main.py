import os, json, secrets, threading, logging, datetime, shutil, zipfile, io, time, requests as http_requests
from flask import Flask, send_from_directory
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

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

# ─── Database ─────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"users": {}, "sites": {}, "banned": [], "premium": [], "limits": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_force_sub():
    if os.path.exists(FORCE_SUB_FILE):
        with open(FORCE_SUB_FILE, "r") as f:
            return json.load(f)
    return {"channel": None, "enabled": True}

def save_force_sub(data):
    with open(FORCE_SUB_FILE, "w") as f:
        json.dump(data, f)

# ─── Helper Functions ─────────────────────────────────────────
def stylish_box(title, emoji="📌"):
    return f"╔══════════════════════╗\n   {emoji} {title}\n╚══════════════════════╝\n"

def get_user_sites(uid):
    db = load_data()
    return {sid: sinfo for sid, sinfo in db["sites"].items() if sinfo.get("user_id") == str(uid)}

def user_site_count(uid):
    return len(get_user_sites(uid))

def get_user_limit(uid):
    db = load_data()
    uid_str = str(uid)
    if uid == OWNER_ID:
        return -1
    if uid_str in db.get("premium", []):
        return -1
    if uid_str in db.get("limits", {}):
        return db["limits"][uid_str]
    return 1

def can_upload(uid):
    limit = get_user_limit(uid)
    if limit == -1:
        return True
    count = user_site_count(uid)
    return count < limit

def is_banned(uid):
    db = load_data()
    return str(uid) in db.get("banned", [])

# ─── Keyboard ──────────────────────────────────────────────────
def user_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📤 Upload Website")],
        [KeyboardButton("🌐 My Websites"), KeyboardButton("❓ Help")],
        [KeyboardButton("📊 Status")]
    ], resize_keyboard=True)

def owner_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📤 Upload Website")],
        [KeyboardButton("🌐 My Websites"), KeyboardButton("❓ Help")],
        [KeyboardButton("📊 Status")],
        [KeyboardButton("⚙️ Admin Panel")]
    ], resize_keyboard=True)

def get_kb(uid):
    return owner_keyboard() if uid == OWNER_ID else user_keyboard()

def get_base_url():
    return os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{os.environ.get('PORT', 8080)}")

# ─── Flask Web Server ─────────────────────────────────────────
app_flask = Flask(__name__)

@app_flask.route("/")
def home():
    return "<h2 style='font-family:sans-serif;color:#2ecc71;text-align:center;padding-top:40px'>🤖 Website Hoster Bot — Online ✅</h2>"

@app_flask.route("/ping")
def ping():
    return "pong"

@app_flask.route("/<site_id>")
def serve_site(site_id):
    site_path = os.path.join(SITES_DIR, site_id)
    index_path = os.path.join(site_path, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(site_path, "index.html")
    return "<h2 style='font-family:sans-serif;color:#e74c3c;text-align:center'>❌ Site not found</h2>", 404

@app_flask.route("/<site_id>/<path:subpath>")
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
    app_flask.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ─── AUTO PING SYSTEM ─────────────────────────────────────────
def auto_ping():
    base_url = get_base_url()

    def ping_task():
        while True:
            time.sleep(300)
            try:
                if base_url:
                    http_requests.get(f"{base_url}/ping", timeout=10)
                db = load_data()
                for sid, sinfo in db["sites"].items():
                    try:
                        http_requests.get(sinfo["url"], timeout=5)
                    except:
                        pass
                logger.info("🔄 Auto-ping cycle complete")
            except:
                pass

    thread = threading.Thread(target=ping_task, daemon=True)
    thread.start()
    logger.info("⏰ Auto-ping started (every 5 minutes)")

# ─── Force Sub Check ──────────────────────────────────────────
async def check_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    force_data = load_force_sub()
    channel = force_data.get("channel")
    enabled = force_data.get("enabled", True)
    if not channel or not enabled:
        return True
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{channel}", user_id=user_id)
        if member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            return True
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Join Channel", url=f"https://t.me/{channel}")],
            [InlineKeyboardButton("✅ Joined", callback_data="check_fsub")]
        ])
        await update.message.reply_text(
            f"❌ *Join Required!*\n\nPlease join @{channel} to use the bot.",
            parse_mode="Markdown", reply_markup=btn
        )
        return False
    except:
        return True

async def check_fsub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    force_data = load_force_sub()
    channel = force_data.get("channel")
    if not channel:
        await query.edit_message_text("No force sub. Send /start")
        return
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{channel}", user_id=user_id)
        if member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            await query.edit_message_text("✅ Thanks! Send /start to continue.")
        else:
            await query.answer("❌ Not joined yet!", show_alert=True)
    except:
        await query.edit_message_text("❌ Could not verify.")

# ─── Start ─────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = load_data()
    uid = str(user.id)

    if is_banned(user.id):
        await update.message.reply_text("❌ You are banned from using this bot.")
        return

    if not await check_force_sub(update, context):
        return

    if uid not in db["users"]:
        db["users"][uid] = {
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
                    f"👤 {user.full_name}\n"
                    f"📛 @{user.username or 'N/A'}\n"
                    f"🆔 `{user.id}`\n"
                    f"👥 Total: {len(db['users'])}",
                    parse_mode="Markdown"
                )
            except:
                pass

    limit_info = ""
    limit = get_user_limit(user.id)
    if limit == -1:
        limit_info = "⭐ *Unlimited* websites"
    else:
        count = user_site_count(uid)
        limit_info = f"📌 *{count}/{limit}* websites used"

    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"    {'👋 WELCOME BACK' if user_site_count(uid) > 0 else '🚀 WELCOME'}\n"
        f"╚══════════════════════╝\n\n"
        f"Hey *{user.first_name}!*\n\n"
        f"📤 Send HTML file or ZIP file\n"
        f"🌐 I'll host it live on the web!\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"{limit_info}\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"👇 Use buttons below:",
        parse_mode="Markdown",
        reply_markup=get_kb(user.id)
    )

# ─── Upload Website ────────────────────────────────────────────
async def upload_website(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        return await update.message.reply_text("❌ You are banned!")
    if not await check_force_sub(update, context):
        return

    if not can_upload(user.id):
        limit = get_user_limit(user.id)
        await update.message.reply_text(
            f"{stylish_box('LIMIT REACHED', '⚠️')}\n\n"
            f"❌ You've used all your slots!\n\n"
            f"📊 Limit: {limit if limit > 0 else 'Unknown'}\n"
            f"📍 Current: {user_site_count(str(user.id))}\n\n"
            f"Delete a site first or contact admin!",
            parse_mode="Markdown"
        )
        return

    context.user_data["awaiting_file"] = "website"
    await update.message.reply_text(
        f"{stylish_box('SEND FILE', '📤')}\n\n"
        f"Send me your website file:\n\n"
        f"━━━ *Option 1:* ━━━\n"
        f"📄 `index.html` file\n\n"
        f"━━━ *Option 2:* ━━━\n"
        f"📦 `.zip` file (HTML+CSS+JS)\n\n"
        f"❌ Or tap Cancel",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Cancel")]], resize_keyboard=True
        )
    )

# ─── File Handler ──────────────────────────────────────────────
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_file"):
        await update.message.reply_text("First tap *📤 Upload Website*!", reply_markup=get_kb(update.effective_user.id))
        return

    user = update.effective_user
    if is_banned(user.id):
        return await update.message.reply_text("❌ You are banned!")

    uid = str(user.id)
    document = update.message.document
    if not document:
        return await update.message.reply_text("❌ Please send a file!")

    file_name = document.file_name
    base_name = os.path.splitext(file_name)[0]
    msg = await update.message.reply_text("⏳ *Deploying...*", parse_mode="Markdown")

    try:
        if not can_upload(user.id):
            await msg.edit_text("❌ Limit reached! Delete old site first.")
            context.user_data["awaiting_file"] = False
            return

        file = await context.bot.get_file(document.file_id)
        file_bytes = io.BytesIO()
        await file.download_to_memory(file_bytes)
        file_bytes.seek(0)

        site_id = secrets.token_hex(12)
        site_dir = os.path.join(SITES_DIR, site_id)
        os.makedirs(site_dir, exist_ok=True)

        fname_lower = file_name.lower()

        if fname_lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(file_bytes, 'r') as zf:
                    if zf.testzip():
                        await msg.edit_text("❌ ZIP is corrupted!")
                        return
                    files = zf.namelist()
                    if "index.html" not in files and "./index.html" not in files:
                        await msg.edit_text("❌ ZIP must contain `index.html`!")
                        return
                    zf.extractall(site_dir)
            except zipfile.BadZipFile:
                await msg.edit_text("❌ Invalid ZIP!")
                return
            file_count = len(files)
        elif fname_lower.endswith((".html", ".htm")):
            content = file_bytes.read().decode("utf-8", errors="replace")
            with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
                f.write(content)
            file_count = 1
        else:
            await msg.edit_text("❌ Only `.html` or `.zip` files allowed!")
            context.user_data["awaiting_file"] = False
            return

        base_url = get_base_url()
        site_url = f"{base_url}/{site_id}"

        db = load_data()
        db["sites"][site_id] = {
            "user_id": uid, "url": site_url, "name": base_name,
            "created": datetime.datetime.now().isoformat(),
            "user_name": user.full_name,
            "type": "zip" if fname_lower.endswith(".zip") else "html",
            "files": file_count
        }
        save_data(db)
        context.user_data["awaiting_file"] = False

        if OWNER_ID and user.id != OWNER_ID:
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"╔══════════════════════╗\n   📤 NEW SITE\n╚══════════════════════╝\n\n"
                    f"👤 {user.full_name}\n🆔 `{user.id}`\n📦 {base_name}\n🔗 {site_url}",
                    parse_mode="Markdown"
                )
            except:
                pass

        inline_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Open Website", url=site_url)],
            [InlineKeyboardButton("🗑 Delete", callback_data=f"del_{site_id}"),
             InlineKeyboardButton("🔄 Re-deploy", callback_data=f"restart_{site_id}")]
        ])

        await msg.edit_text(
            f"╔══════════════════════╗\n    ✅  D E P L O Y E D\n╚══════════════════════╝\n\n"
            f"🌐 *{base_name}* is LIVE!\n\n━━━━━━━━━━━━━━━━━━━\n📋 `{site_url}`\n━━━━━━━━━━━━━━━━━━━",
            parse_mode="Markdown", reply_markup=inline_kb
        )
        await update.message.reply_text("👇 Use buttons below", parse_mode="Markdown", reply_markup=get_kb(user.id))

    except Exception as e:
        logger.exception("Deploy error")
        await msg.edit_text(f"❌ Error: `{str(e)[:200]}`", parse_mode="Markdown")

# ─── MY WEBSITES (Inline Buttons) ─────────────────────────────
async def my_websites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        return await update.message.reply_text("❌ You are banned!")
    if user.id != OWNER_ID and not await check_force_sub(update, context):
        return

    uid = str(user.id)
    user_sites = get_user_sites(uid)

    if not user_sites:
        await update.message.reply_text(
            f"{stylish_box('No Websites', '❌')}\n\nYou haven't uploaded anything yet!\n\nTap *📤 Upload Website* to start!",
            parse_mode="Markdown"
        )
        return

    buttons = []
    for sid, sinfo in user_sites.items():
        name = sinfo.get("name", "Website")[:20]
        buttons.append([InlineKeyboardButton(f"🌐 {name}", callback_data=f"view_{sid}")])
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close_mywebsites")])

    await update.message.reply_text(
        f"╔══════════════════════╗\n   🌐 YOUR WEBSITES ({len(user_sites)})\n╚══════════════════════╝",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )

async def my_websites_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "close_mywebsites":
        await query.message.delete()
        return

    if data == "check_fsub":
        user_id = query.from_user.id
        force_data = load_force_sub()
        channel = force_data.get("channel")
        if not channel:
            await query.edit_message_text("No force sub. Send /start")
            return
        try:
            member = await context.bot.get_chat_member(chat_id=f"@{channel}", user_id=user_id)
            if member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
                await query.edit_message_text("✅ Thanks! Send /start to continue.")
            else:
                await query.answer("❌ Not joined!", show_alert=True)
        except:
            await query.edit_message_text("❌ Could not verify.")

    if data.startswith("view_"):
        site_id = data.replace("view_", "")
        db = load_data()
        if site_id in db["sites"]:
            sinfo = db["sites"][site_id]
            name = sinfo.get("name", "Website")
            inline_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Open Website", url=sinfo["url"])],
                [InlineKeyboardButton("🗑 Delete", callback_data=f"del_{site_id}"),
                 InlineKeyboardButton("🔄 Re-deploy", callback_data=f"restart_{site_id}")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_mywebsites")]
            ])
            await query.edit_message_text(
                f"╔══════════════════════╗\n   🌐 {name}\n╚══════════════════════╝\n\n"
                f"🔗 {sinfo['url']}\n📦 Type: {sinfo.get('type','html')}\n📅 Created: {sinfo['created'][:10]}\n📄 Files: {sinfo.get('files',1)}\n\nSelect an action:",
                parse_mode="Markdown", reply_markup=inline_kb
            )
        else:
            await query.edit_message_text("❌ Site not found!")

    elif data == "back_to_mywebsites":
        user_id = query.from_user.id
        uid = str(user_id)
        user_sites = get_user_sites(uid)
        if not user_sites:
            await query.edit_message_text("❌ No websites found.")
            return
        buttons = []
        for sid, sinfo in user_sites.items():
            name = sinfo.get("name", "Website")[:20]
            buttons.append([InlineKeyboardButton(f"🌐 {name}", callback_data=f"view_{sid}")])
        buttons.append([InlineKeyboardButton("❌ Close", callback_data="close_mywebsites")])
        await query.edit_message_text(
            f"╔══════════════════════╗\n   🌐 YOUR WEBSITES ({len(user_sites)})\n╚══════════════════════╝",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data.startswith("del_"):
        site_id = data.replace("del_", "")
        db = load_data()
        if site_id in db["sites"]:
            sdir = os.path.join(SITES_DIR, site_id)
            if os.path.exists(sdir):
                shutil.rmtree(sdir)
            del db["sites"][site_id]
            save_data(db)
            await query.edit_message_text("✅ *Website deleted successfully!*", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Site not found!")

    elif data.startswith("restart_"):
        await query.edit_message_text("ℹ️ Delete this site first, then upload again using *📤 Upload Website* button.", parse_mode="Markdown")

# ─── Help ──────────────────────────────────────────────────────
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    if update.effective_user.id != OWNER_ID and not await check_force_sub(update, context):
        return

    await update.message.reply_text(
        f"╔══════════════════════╗\n   📖  HOW TO USE\n╚══════════════════════╝\n\n"
        f"━━━ *Upload* ━━━\n1️⃣ Tap *📤 Upload Website*\n2️⃣ Send `index.html` or `.zip`\n3️⃣ Get live URL ✅\n\n"
        f"━━━ *Manage* ━━━\n🌐 View & manage all your sites\n🗑 Delete to upload new ones\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n📌 Default: 1 site\n⭐ Premium: Unlimited\n━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown"
    )

# ─── Status ────────────────────────────────────────────────────
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    if update.effective_user.id != OWNER_ID and not await check_force_sub(update, context):
        return

    db = load_data()
    force_data = load_force_sub()
    channel = force_data.get("channel") or "Not set"
    fsub_enabled = force_data.get("enabled", True) and bool(force_data.get("channel"))

    await update.message.reply_text(
        f"╔══════════════════════╗\n    📊  BOT STATUS\n╚══════════════════════╝\n\n"
        f"👥 *Users:* `{len(db['users'])}`\n🌐 *Sites:* `{len(db['sites'])}`\n"
        f"🚫 *Banned:* `{len(db.get('banned',[]))}`\n⭐ *Premium:* `{len(db.get('premium',[]))}`\n"
        f"🎯 *Limits:* `{len(db.get('limits',{}))}`\n📢 *Force Sub:* {'✅ @' + channel if fsub_enabled else '❌ Off'}\n"
        f"⚡ *Auto-Ping:* ✅ Every 5 min\n🟢 *Status:* Online",
        parse_mode="Markdown"
    )

# ─── Cancel ────────────────────────────────────────────────────
async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_file"] = False
    context.user_data["admin_action"] = None
    context.user_data["setlimit_target"] = None
    await update.message.reply_text(
        f"{stylish_box('CANCELLED', '❌')}", parse_mode="Markdown",
        reply_markup=get_kb(update.effective_user.id)
    )

# ─── Button Router ─────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    mapping = {
        "📤 Upload Website": upload_website,
        "🌐 My Websites": my_websites,
        "❓ Help": help_cmd,
        "📊 Status": status,
        "❌ Cancel": cancel_handler,
        "⚙️ Admin Panel": admin_panel_handler,
    }
    handler = mapping.get(text)
    if handler:
        return await handler(update, context)
    await update.message.reply_text("👇 Use buttons below!", reply_markup=get_kb(uid))

# ═════════════════════════════════════════════════════════════════
#  👑  A D M I N   P A N E L
# ═════════════════════════════════════════════════════════════════

async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    db = load_data()
    force_data = load_force_sub()
    channel = force_data.get("channel") or "Not set"
    fsub_status = "✅ On" if force_data.get("channel") else "❌ Off"

    text = (
        f"╔══════════════════════╗\n     👑 ADMIN PANEL\n╚══════════════════════╝\n\n"
        f"━━━ *Stats* ━━━\n👥 Users: {len(db['users'])}\n🌐 Sites: {len(db['sites'])}\n"
        f"🚫 Banned: {len(db.get('banned',[]))}\n⭐ Premium: {len(db.get('premium',[]))}\n"
        f"🎯 Limits: {len(db.get('limits',{}))}\n📢 Force Sub: {fsub_status} @{channel}"
    )

    buttons = [
        [InlineKeyboardButton("👥 Users", callback_data="admin_users"),
         InlineKeyboardButton("🌐 Sites", callback_data="admin_sites")],
        [InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban"),
         InlineKeyboardButton("✅ Unban User", callback_data="admin_unban")],
        [InlineKeyboardButton("⭐ Make Premium", callback_data="admin_premium"),
         InlineKeyboardButton("💔 Un-Premium", callback_data="admin_unpremium")],
        [InlineKeyboardButton("🎯 Set Limit", callback_data="admin_setlimit")],
        [InlineKeyboardButton("📢 Force Sub Setup", callback_data="admin_fsub")],
        [InlineKeyboardButton("📤 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton("📊 Full Stats", callback_data="admin_fullstats")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if user_id != OWNER_ID:
        await query.edit_message_text("❌ Admin only!")
        return

    db = load_data()

    if data == "admin_close":
        await query.message.delete()
        return

    if data == "admin_users":
        text = f"👥 *Users ({len(db['users'])}):*\n\n"
        for uid, uinfo in db["users"].items():
            banned = "🚫" if uid in db.get("banned", []) else ""
            prem = "⭐" if uid in db.get("premium", []) else ""
            limit = db.get("limits", {}).get(uid, "1")
            text += f"├ {prem}{banned} `{uid}` {uinfo['name']} (limit:{limit})\n"
        for i in range(0, len(text), 4000):
            await query.message.edit_text(text[i:i+4000], parse_mode="Markdown")

    elif data == "admin_sites":
        # FIXED: Now shows interactive buttons for each site
        if not db["sites"]:
            await query.edit_message_text("❌ No sites found.")
            return
        buttons = []
        for sid, sinfo in db["sites"].items():
            name = sinfo.get("name", "Website")[:15]
            uname = sinfo.get("user_name", "?")[:12]
            buttons.append([InlineKeyboardButton(f"🌐 {name} — {uname}", callback_data=f"admin_viewsite_{sid}")])
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back")])
        await query.edit_message_text(
            f"🌐 *All Sites ({len(db['sites'])}):*\n\n👇 Tap a site to manage:",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
        )

    # FIXED: Admin site view with action buttons
    elif data.startswith("admin_viewsite_"):
        site_id = data.replace("admin_viewsite_", "")
        if site_id in db["sites"]:
            sinfo = db["sites"][site_id]
            name = sinfo.get("name", "Website")
            inline_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Open Website", url=sinfo["url"])],
                [InlineKeyboardButton("🗑 Delete", callback_data=f"admin_del_{site_id}"),
                 InlineKeyboardButton("🔄 Re-deploy", callback_data=f"restart_{site_id}")],
                [InlineKeyboardButton("🔙 Back to Sites", callback_data="admin_sites")]
            ])
            await query.edit_message_text(
                f"🌐 *{name}*\n\n"
                f"👤 Owner: `{sinfo.get('user_name','?')}`\n"
                f"🆔 UserID: `{sinfo.get('user_id','?')}`\n"
                f"🔗 {sinfo['url']}\n"
                f"📦 Type: {sinfo.get('type','html')}\n"
                f"📅 Created: {sinfo['created'][:10]}\n"
                f"📄 Files: {sinfo.get('files',1)}\n\n"
                f"Select an action:",
                parse_mode="Markdown", reply_markup=inline_kb
            )
        else:
            await query.edit_message_text("❌ Site not found!")

    # FIXED: Admin delete site
    elif data.startswith("admin_del_"):
        site_id = data.replace("admin_del_", "")
        if site_id in db["sites"]:
            sdir = os.path.join(SITES_DIR, site_id)
            if os.path.exists(sdir):
                shutil.rmtree(sdir)
            del db["sites"][site_id]
            save_data(db)
            await query.edit_message_text("✅ *Website deleted by admin!*", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Site not found!")

    elif data == "admin_ban":
        context.user_data["admin_action"] = "ban"
        await query.edit_message_text(
            "🚫 *Ban User*\n\nSend me the user's Telegram ID:\n\nExample: `123456789`\n\nOr tap Cancel",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
        )

    elif data == "admin_unban":
        context.user_data["admin_action"] = "unban"
        await query.edit_message_text(
            "✅ *Unban User*\n\nSend me the user's Telegram ID:", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
        )

    elif data == "admin_premium":
        context.user_data["admin_action"] = "premium"
        await query.edit_message_text(
            "⭐ *Make Premium*\n\nSend me the user's Telegram ID:", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
        )

    elif data == "admin_unpremium":
        context.user_data["admin_action"] = "unpremium"
        await query.edit_message_text(
            "💔 *Remove Premium*\n\nSend me the user's Telegram ID:", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
        )

    elif data == "admin_setlimit":
        context.user_data["admin_action"] = "setlimit_user"
        await query.edit_message_text(
            "🎯 *Set Custom Limit*\n\nStep 1: Send me the user's Telegram ID:\n\nExample: `123456789`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
        )

    elif data == "admin_fsub":
        force_data = load_force_sub()
        channel = force_data.get("channel") or "Not set"
        enabled = force_data.get("enabled", True)
        status = "✅ Enabled" if enabled and force_data.get("channel") else "❌ Disabled"
        buttons = [
            [InlineKeyboardButton("📢 Set Channel", callback_data="fsub_set")],
            [InlineKeyboardButton("🗑 Remove Channel", callback_data="fsub_remove")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
        ]
        await query.edit_message_text(
            f"📢 *Force Sub Settings*\n\nCurrent: @{channel}\nStatus: {status}\n\nMake sure bot is admin!",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
        )

    elif data == "fsub_set":
        context.user_data["admin_action"] = "fsub_set"
        await query.edit_message_text(
            "📢 *Set Force Sub Channel*\n\nSend the channel username:\n\nExample: `@my_channel`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
        )

    elif data == "fsub_remove":
        force_data = load_force_sub()
        force_data["channel"] = None
        save_force_sub(force_data)
        await query.edit_message_text("✅ Force sub channel removed!")

    elif data == "admin_broadcast":
        context.user_data["admin_action"] = "broadcast"
        await query.edit_message_text(
            "📤 *Broadcast Message*\n\nSend the message to broadcast to all users:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel")]])
        )

    elif data == "admin_fullstats":
        text = f"╔══════════════════════╗\n   📊 FULL STATS\n╚══════════════════════╝\n\n"
        text += f"👥 *Users ({len(db['users'])}):*\n\n"
        for uid, uinfo in db["users"].items():
            sc = len([s for s in db["sites"].values() if s.get("user_id") == uid])
            banned = "🚫" if uid in db.get("banned", []) else ""
            prem = "⭐" if uid in db.get("premium", []) else ""
            lim = db.get("limits", {}).get(uid, "1")
            text += f"├ {prem}{banned} `{uid}` {uinfo['name']} ({sc}/{lim})\n"
        for i in range(0, len(text), 4000):
            await query.message.edit_text(text[i:i+4000], parse_mode="Markdown")

    elif data == "admin_back":
        await admin_panel_handler(update, context)

    elif data == "admin_cancel":
        context.user_data["admin_action"] = None
        context.user_data["setlimit_target"] = None
        await query.message.delete()

# ─── Universal Text Handler ────────────────────────────────────
async def universal_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    # ─── Check Cancel first ───
    if text == "❌ Cancel":
        return await cancel_handler(update, context)

    # ─── Admin action mode ───
    if user.id == OWNER_ID and context.user_data.get("admin_action"):
        action = context.user_data["admin_action"]
        db = load_data()

        if action == "ban":
            if text in db.get("banned", []):
                await update.message.reply_text("Already banned!")
            else:
                if "banned" not in db: db["banned"] = []
                db["banned"].append(text)
                to_del = [sid for sid, sinfo in db["sites"].items() if sinfo.get("user_id") == text]
                for sid in to_del:
                    sdir = os.path.join(SITES_DIR, sid)
                    if os.path.exists(sdir): shutil.rmtree(sdir)
                    del db["sites"][sid]
                save_data(db)
                try:
                    await context.bot.send_message(int(text), "❌ You have been banned.")
                except: pass
                await update.message.reply_text(f"✅ User `{text}` banned + sites deleted!", parse_mode="Markdown")

        elif action == "unban":
            if text in db.get("banned", []):
                db["banned"].remove(text)
                save_data(db)
                try:
                    await context.bot.send_message(int(text), "✅ You have been unbanned! Use /start")
                except: pass
                await update.message.reply_text(f"✅ User `{text}` unbanned!", parse_mode="Markdown")
            else:
                await update.message.reply_text("Not banned.")

        elif action == "premium":
            if "premium" not in db: db["premium"] = []
            if text not in db["premium"]:
                db["premium"].append(text)
                save_data(db)
                try:
                    await context.bot.send_message(int(text), "⭐ *Congratulations!* You are now **Premium** with unlimited websites! 🚀", parse_mode="Markdown")
                except: pass
                await update.message.reply_text(f"✅ User `{text}` is now PREMIUM!", parse_mode="Markdown")
            else:
                await update.message.reply_text("Already premium.")

        elif action == "unpremium":
            if text in db.get("premium", []):
                db["premium"].remove(text)
                save_data(db)
                try:
                    await context.bot.send_message(int(text), "Your premium membership has ended.")
                except: pass
                await update.message.reply_text(f"✅ Premium removed for `{text}`", parse_mode="Markdown")
            else:
                await update.message.reply_text("Not premium.")

        elif action == "setlimit_user":
            context.user_data["setlimit_target"] = text
            context.user_data["admin_action"] = "setlimit_value"
            await update.message.reply_text(
                f"🎯 Target user: `{text}`\n\nNow send the limit number:\n"
                f"• `2` = 2 sites\n• `5` = 5 sites\n• `0` = Default (1)\n• `-1` = Unlimited",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel")]], resize_keyboard=True)
            )
            return

        elif action == "setlimit_value":
            target = context.user_data.get("setlimit_target", "")
            try:
                limit = int(text)
                if "limits" not in db: db["limits"] = {}
                db["limits"][target] = limit
                save_data(db)
                await update.message.reply_text(
                    f"✅ *Limit Set!*\n\n👤 User: `{target}`\n🎯 Limit: {limit if limit >= 0 else 'Unlimited'} websites",
                    parse_mode="Markdown", reply_markup=get_kb(OWNER_ID)
                )
            except ValueError:
                await update.message.reply_text("❌ Please send a valid number!", reply_markup=get_kb(OWNER_ID))

        elif action == "fsub_set":
            channel = text.lstrip("@")
            force_data = load_force_sub()
            force_data["channel"] = channel
            save_force_sub(force_data)
            await update.message.reply_text(f"✅ *Force sub set!*\n\n📢 @{channel}\n\n⚠️ Make sure bot is admin!", parse_mode="Markdown")

        elif action == "broadcast":
            success = failed = 0
            sent_msg = await update.message.reply_text(f"📤 Broadcasting to {len(db['users'])} users...")
            for uid in db["users"]:
                if uid in db.get("banned", []): continue
                try:
                    await context.bot.send_message(int(uid), f"📢 *Broadcast:*\n\n{text}", parse_mode="Markdown")
                    success += 1
                except:
                    failed += 1
            await sent_msg.edit_text(f"✅ Sent: {success} | ❌ Failed: {failed}")

        context.user_data["admin_action"] = None
        context.user_data["setlimit_target"] = None
        return

    # ─── Check if it's a button text ───
    button_texts = ["📤 Upload Website", "🌐 My Websites", "❓ Help", "📊 Status", "⚙️ Admin Panel", "❌ Cancel"]
    if text in button_texts:
        return await button_handler(update, context)

    # ─── Otherwise: fallback ───
    await update.message.reply_text("👇 Use buttons below!", reply_markup=get_kb(user.id))

# ─── Error Handler ─────────────────────────────────────────────
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# ─── MAIN ──────────────────────────────────────────────────────
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    auto_ping()

    app_tele = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app_tele.add_handler(CommandHandler("start", start))
    app_tele.add_handler(CommandHandler("help", help_cmd))

    # ===== FIXED: Callback handlers =====
    # My Websites callbacks — uses prefix matching (no $ at end) for view_, del_, restart_
    app_tele.add_handler(CallbackQueryHandler(my_websites_callback, pattern=r'^(view_|del_|restart_)'))
    # Exact match callbacks
    app_tele.add_handler(CallbackQueryHandler(my_websites_callback, pattern=r'^(back_to_mywebsites|close_mywebsites|check_fsub)$'))

    # Admin callbacks
    app_tele.add_handler(CallbackQueryHandler(admin_callback_handler, pattern=r'^admin_|^fsub_'))

    # Document handler (HTML or ZIP files)
    app_tele.add_handler(MessageHandler(
        filters.Document.FileExtension("html") |
        filters.Document.FileExtension("htm") |
        filters.Document.FileExtension("zip"),
        handle_document
    ))

    # Universal text handler
    app_tele.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, universal_text_handler))

    # Error
    app_tele.add_error_handler(error_handler)

    logger.info("🤖 Bot + Web Server + Auto-Ping running...")
    app_tele.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
