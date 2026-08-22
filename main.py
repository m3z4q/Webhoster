import os, json, secrets, threading, logging, datetime, shutil, zipfile, io, re
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
    return {"users": {}, "sites": {}, "banned": [], "premium": []}

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

# ─── Keyboards ──────────────────────────────────────────────────
def user_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📤 Upload Website")],
        [KeyboardButton("🌐 My Website"), KeyboardButton("🗑 Delete My Site")],
        [KeyboardButton("❓ Help"), KeyboardButton("📊 Status")]
    ], resize_keyboard=True)

def owner_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📤 Upload Website")],
        [KeyboardButton("🌐 My Website"), KeyboardButton("🗑 Delete My Site")],
        [KeyboardButton("❓ Help"), KeyboardButton("📊 Status")],
        [KeyboardButton("⚙️ Admin Panel")]
    ], resize_keyboard=True)

# ─── Force Sub Check ──────────────────────────────────────────
async def check_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    force_data = load_force_sub()
    channel = force_data.get("channel")
    if not channel:
        return True  # No force sub configured
    user_id = update.effective_user.id
    if user_id == OWNER_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{channel}", user_id=user_id)
        if member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
            return True
        await update.message.reply_text(
            f"╔══════════════════════╗\n"
            f"     ❌ JOIN REQUIRED ❌\n"
            f"╚══════════════════════╝\n\n"
            f"✨ Please join @{channel} first!\n\n"
            f"👉 [🔗 Join Channel](https://t.me/{channel})\n\n"
            f"Then send /start again.",
            parse_mode="Markdown", disable_web_page_preview=True
        )
        return False
    except:
        # Can't check — bot might not be admin in channel
        await update.message.reply_text(
            "⚠️ Could not verify channel membership.\n"
            "If the channel is private, please make sure the bot is admin there."
        )
        return True

def is_banned(user_id):
    db = load_data()
    return str(user_id) in db.get("banned", [])

def is_premium(user_id):
    db = load_data()
    return str(user_id) in db.get("premium", [])

def can_upload_more(user_id):
    """Owner/premium = unlimited, normal user = max 1"""
    if user_id == OWNER_ID or is_premium(user_id):
        return True
    db = load_data()
    user_sites = [s for s in db["sites"].values() if s.get("user_id") == str(user_id)]
    return len(user_sites) < 1

def get_kb(user_id):
    return owner_keyboard() if user_id == OWNER_ID else user_keyboard()

def stylish_box(title, emoji="📌"):
    return f"╔══════════════════════╗\n   {emoji} {title}\n╚══════════════════════╝\n"

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

# ─── START ──────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = load_data()
    uid = str(user.id)

    # Check ban
    if is_banned(user.id):
        await update.message.reply_text("❌ You are banned from using this bot.")
        return

    if not await check_force_sub(update, context):
        return

    # New user
    if uid not in db["users"]:
        db["users"][uid] = {
            "name": user.full_name,
            "username": user.username or "N/A",
            "joined": datetime.datetime.now().isoformat()
        }
        save_data(db)
        # Notify owner
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

    user_sites = get_user_sites_count(uid)
    limit_text = ""
    if user.id != OWNER_ID and not is_premium(user.id):
        limit_text = "📌 *1 website limit*"
    else:
        limit_text = "⭐ *Unlimited websites* (Premium)"

    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"    👋 WELCOME BACK\n" if uid in db["sites"] else
        f"    🚀 WELCOME\n"
        f"╚══════════════════════╝\n\n"
        f"Hey *{user.first_name}!*\n\n"
        f"📤 Send me an HTML file or ZIP file\n"
        f"🌐 I'll host it live on the web!\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"{limit_text}\n"
        f"📊 Your sites: {user_sites}\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"👇 Use buttons below:",
        parse_mode="Markdown",
        reply_markup=get_kb(user.id)
    )

def get_user_sites_count(uid):
    db = load_data()
    return len([s for s in db["sites"].values() if s.get("user_id") == uid])

# ─── UPLOAD BUTTON ────────────────────────────────────────────
async def upload_website(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        return await update.message.reply_text("❌ You are banned!")
    if not await check_force_sub(update, context):
        return

    uid = str(user.id)

    if not can_upload_more(user.id):
        await update.message.reply_text(
            f"{stylish_box('LIMIT REACHED', '⚠️')}\n\n"
            f"❌ You already have a website!\n\n"
            f"Use *🗑 Delete My Site* first,\n"
            f"then upload a new one.\n\n"
            f"Or contact admin for premium upgrade!",
            parse_mode="Markdown"
        )
        return

    context.user_data["awaiting_file"] = "website"
    await update.message.reply_text(
        f"{stylish_box('SEND FILE', '📤')}\n\n"
        f"Send me your website file(s):\n\n"
        f"━━━ *Option 1: HTML File* ━━━\n"
        f"📄 Just send `index.html` file\n\n"
        f"━━━ *Option 2: ZIP File* ━━━\n"
        f"📦 Send a `.zip` containing:\n"
        f"  • `index.html` (required)\n"
        f"  • `style.css` (optional)\n"
        f"  • `script.js` (optional)\n"
        f"  • images/ (optional)\n\n"
        f"❌ Tap Cancel to abort",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("❌ Cancel")]], resize_keyboard=True
        )
    )

# ─── FILE HANDLER ──────────────────────────────────────────────
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

    file_name = document.file_name.lower()
    msg = await update.message.reply_text("⏳ *Deploying your website...*", parse_mode="Markdown")

    try:
        if not can_upload_more(user.id):
            await msg.edit_text("❌ Limit reached! Delete your old site first.")
            context.user_data["awaiting_file"] = False
            return

        # Download file
        file = await context.bot.get_file(document.file_id)
        file_bytes = io.BytesIO()
        await file.download_to_memory(file_bytes)
        file_bytes.seek(0)

        site_id = secrets.token_hex(12)
        site_dir = os.path.join(SITES_DIR, site_id)
        os.makedirs(site_dir, exist_ok=True)

        # ─── ZIP FILE ───────────────────────────────────────
        if file_name.endswith(".zip"):
            try:
                with zipfile.ZipFile(file_bytes, 'r') as zf:
                    if zf.testzip():
                        await msg.edit_text("❌ ZIP is corrupted!")
                        return
                    files = zf.namelist()
                    if "index.html" not in files:
                        await msg.edit_text("❌ ZIP mein `index.html` hona chahiye!")
                        return
                    zf.extractall(site_dir)
            except zipfile.BadZipFile:
                await msg.edit_text("❌ Invalid ZIP file!")
                return

            file_count = len(files)

        # ─── HTML FILE ──────────────────────────────────────
        elif file_name.endswith((".html", ".htm")):
            content = file_bytes.read().decode("utf-8", errors="replace")
            with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
                f.write(content)
            file_count = 1

        else:
            await msg.edit_text("❌ Only `.html` or `.zip` files allowed!")
            context.user_data["awaiting_file"] = False
            return

        # Build URL
        base_url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{os.environ.get('PORT', 8080)}")
        site_url = f"{base_url}/{site_id}"

        # Save to DB
        db = load_data()
        db["sites"][site_id] = {
            "user_id": uid,
            "url": site_url,
            "created": datetime.datetime.now().isoformat(),
            "user_name": user.full_name,
            "type": "zip" if file_name.endswith(".zip") else "html"
        }
        save_data(db)
        context.user_data["awaiting_file"] = False

        # Notify owner
        if OWNER_ID and user.id != OWNER_ID:
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"╔══════════════════════╗\n"
                    f"   📤 NEW SITE\n"
                    f"╚══════════════════════╝\n\n"
                    f"👤 {user.full_name}\n"
                    f"🆔 `{user.id}`\n"
                    f"📦 {file_count} file(s)\n"
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
            f"💡 Forms, CSS, JS — sab kaam karega!",
            parse_mode="Markdown",
            disable_web_page_preview=False
        )
        await update.message.reply_text("👇 *Use buttons below*", parse_mode="Markdown", reply_markup=get_kb(user.id))

    except Exception as e:
        logger.exception("Deploy error")
        await msg.edit_text(f"❌ Error: `{str(e)[:200]}`", parse_mode="Markdown")

# ─── MY WEBSITE ────────────────────────────────────────────────
async def my_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        return await update.message.reply_text("❌ You are banned!")
    if not await check_force_sub(update, context):
        return

    uid = str(user.id)
    db = load_data()
    user_sites = {sid: sinfo for sid, sinfo in db["sites"].items() if sinfo.get("user_id") == uid}

    if not user_sites:
        await update.message.reply_text(
            f"{stylish_box('NO WEBSITE', '❌')}\n\n"
            f"You haven't uploaded anything yet!\n\n"
            f"Tap *📤 Upload Website* to start!",
            parse_mode="Markdown"
        )
        return

    text = f"{stylish_box(f'YOUR SITES ({len(user_sites)})', '🌐')}\n\n"
    for sid, sinfo in user_sites.items():
        text += f"━━━━━━━━━━━━━━━━━━━\n"
        text += f"🔗 [Open →]({sinfo['url']})\n"
        text += f"📋 `{sinfo['url']}`\n"
        text += f"📅 {sinfo['created'][:10]} | 📦 {sinfo.get('type','html')}\n"

    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000], parse_mode="Markdown", disable_web_page_preview=False)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=False)

# ─── DELETE SITE ───────────────────────────────────────────────
async def delete_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        return await update.message.reply_text("❌ You are banned!")

    uid = str(user.id)
    db = load_data()
    user_sites = {sid: sinfo for sid, sinfo in db["sites"].items() if sinfo.get("user_id") == uid}

    if not user_sites:
        return await update.message.reply_text("❌ You have no sites to delete!")

    for sid in list(user_sites.keys()):
        site_dir = os.path.join(SITES_DIR, sid)
        if os.path.exists(site_dir):
            shutil.rmtree(site_dir)
        del db["sites"][sid]

    save_data(db)

    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"    ✅  SITE DELETED\n"
        f"╚══════════════════════╝\n\n"
        f"Your website has been deleted successfully!\n\n"
        f"You can now upload a new one 👆",
        parse_mode="Markdown"
    )

# ─── HELP ──────────────────────────────────────────────────────
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    if not await check_force_sub(update, context):
        return

    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"   📖  HOW TO USE\n"
        f"╚══════════════════════╝\n\n"
        f"━━━ *Upload Website* ━━━\n"
        f"1️⃣ Tap *📤 Upload Website*\n"
        f"2️⃣ Send `index.html` file\n"
        f"   OR send a `.zip` file\n"
        f"3️⃣ Get live URL ✅\n\n"
        f"━━━ *Manage* ━━━\n"
        f"🌐 View your site(s)\n"
        f"🗑 Delete old site to upload new\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Normal user: 1 site\n"
        f"⭐ Premium user: Unlimited\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"Contact admin for premium upgrade!",
        parse_mode="Markdown"
    )

# ─── STATUS ────────────────────────────────────────────────────
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_banned(update.effective_user.id):
        return
    if not await check_force_sub(update, context):
        return

    db = load_data()
    force_data = load_force_sub()
    channel = force_data.get("channel") or "Not set"

    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"    📊  BOT STATUS\n"
        f"╚══════════════════════╝\n\n"
        f"👥 *Users:* `{len(db['users'])}`\n"
        f"🌐 *Sites:* `{len(db['sites'])}`\n"
        f"🚫 *Banned:* `{len(db.get('banned',[]))}`\n"
        f"⭐ *Premium:* `{len(db.get('premium',[]))}`\n"
        f"📢 *Force Sub:* @{channel}\n"
        f"⚡ *Status:* ✅ Online",
        parse_mode="Markdown"
    )

# ─── CANCEL ────────────────────────────────────────────────────
async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["awaiting_file"] = False
    await update.message.reply_text(
        f"{stylish_box('CANCELLED', '❌')}",
        parse_mode="Markdown",
        reply_markup=get_kb(update.effective_user.id)
    )

# ─── BUTTON ROUTER ─────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    mapping = {
        "📤 Upload Website": upload_website,
        "🌐 My Website": my_site,
        "🗑 Delete My Site": delete_site,
        "❓ Help": help_cmd,
        "📊 Status": status,
        "❌ Cancel": cancel_handler,
        "⚙️ Admin Panel": admin_panel,
    }

    handler = mapping.get(text)
    if handler:
        return await handler(update, context)

    await update.message.reply_text("👇 *Use buttons below!*", parse_mode="Markdown", reply_markup=get_kb(uid))

# ─── ADMIN PANEL ───────────────────────────────────────────────
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    db = load_data()
    force_data = load_force_sub()
    channel = force_data.get("channel") or "Not set"

    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"     👑 ADMIN PANEL\n"
        f"╚══════════════════════╝\n\n"
        f"━━━ *Stats* ━━━\n"
        f"👥 Users: `{len(db['users'])}`\n"
        f"🌐 Sites: `{len(db['sites'])}`\n"
        f"🚫 Banned: `{len(db.get('banned',[]))}`\n"
        f"⭐ Premium: `{len(db.get('premium',[]))}`\n"
        f"📢 Force Sub: @{channel}\n\n"
        f"━━━ *Commands* ━━━\n\n"
        f"`/addch @channel` — Set force sub\n"
        f"`/delch` — Remove force sub\n"
        f"`/ban user_id` — Ban a user\n"
        f"`/unban user_id` — Unban a user\n"
        f"`/premium user_id` — Make premium\n"
        f"`/unpremium user_id` — Remove premium\n"
        f"`/sites` — List all sites\n"
        f"`/delsite site_id` — Delete any site\n"
        f"`/broadcast msg` — DM all users\n"
        f"`/stats` — Detailed stats + reset\n"
        f"`/users` — List all users",
        parse_mode="Markdown"
    )

# ─── ADMIN COMMANDS ────────────────────────────────────────────
async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: `/addch @channel`", parse_mode="Markdown")
    channel = context.args[0].lstrip("@")
    force_data = load_force_sub()
    force_data["channel"] = channel
    save_force_sub(force_data)
    await update.message.reply_text(
        f"╔══════════════════════╗\n"
        f"     ✅ FORCE SUB SET\n"
        f"╚══════════════════════╝\n\n"
        f"📢 Channel: @{channel}\n\n"
        f"⚠️ Make sure bot is admin in channel!",
        parse_mode="Markdown"
    )

async def del_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    force_data = load_force_sub()
    force_data["channel"] = None
    save_force_sub(force_data)
    await update.message.reply_text("✅ *Force sub removed!*", parse_mode="Markdown")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: `/ban user_id`", parse_mode="Markdown")
    target = context.args[0]
    db = load_data()
    if "banned" not in db:
        db["banned"] = []
    if target not in db["banned"]:
        db["banned"].append(target)
        # Also delete their sites
        to_delete = [sid for sid, sinfo in db["sites"].items() if sinfo.get("user_id") == target]
        for sid in to_delete:
            sdir = os.path.join(SITES_DIR, sid)
            if os.path.exists(sdir):
                shutil.rmtree(sdir)
            del db["sites"][sid]
        save_data(db)
        # Notify user
        try:
            await context.bot.send_message(int(target), "❌ You have been banned from the bot.")
        except:
            pass
        await update.message.reply_text(f"✅ User `{target}` banned! Sites deleted.", parse_mode="Markdown")
    else:
        await update.message.reply_text("User already banned.")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: `/unban user_id`", parse_mode="Markdown")
    target = context.args[0]
    db = load_data()
    if "banned" in db and target in db["banned"]:
        db["banned"].remove(target)
        save_data(db)
        try:
            await context.bot.send_message(int(target), "✅ You have been unbanned! Use /start")
        except:
            pass
        await update.message.reply_text(f"✅ User `{target}` unbanned!", parse_mode="Markdown")
    else:
        await update.message.reply_text("User is not banned.")

async def premium_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: `/premium user_id`", parse_mode="Markdown")
    target = context.args[0]
    db = load_data()
    if "premium" not in db:
        db["premium"] = []
    if target not in db["premium"]:
        db["premium"].append(target)
        save_data(db)
        try:
            await context.bot.send_message(int(target), "⭐ *Congratulations!* You are now a **Premium** user! Unlimited websites! 🚀", parse_mode="Markdown")
        except:
            pass
        await update.message.reply_text(f"✅ User `{target}` is now PREMIUM! Unlimited sites!", parse_mode="Markdown")
    else:
        await update.message.reply_text("User is already premium.")

async def unpremium_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: `/unpremium user_id`", parse_mode="Markdown")
    target = context.args[0]
    db = load_data()
    if "premium" in db and target in db["premium"]:
        db["premium"].remove(target)
        # Don't delete their sites, just no more new ones
        save_data(db)
        try:
            await context.bot.send_message(int(target), "Your premium membership has ended.")
        except:
            pass
        await update.message.reply_text(f"✅ User `{target}` premium removed.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Not a premium user.")

async def list_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    db = load_data()
    if not db["sites"]:
        return await update.message.reply_text("No sites yet.")
    text = f"╔══════════════════════╗\n   🌐 ALL SITES ({len(db['sites'])})\n╚══════════════════════╝\n\n"
    for sid, sinfo in db["sites"].items():
        text += f"━━━━━━━━━━━━━━━━━━━\n"
        text += f"🆔 `{sid[:16]}...`\n"
        text += f"👤 {sinfo.get('user_name','?')} (`{sinfo.get('user_id','?')}`)\n"
        text += f"🔗 {sinfo['url']}\n"
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i+4000], parse_mode="Markdown", disable_web_page_preview=True)

async def del_site(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: `/delsite site_id`", parse_mode="Markdown")
    target_site = context.args[0]
    db = load_data()
    if target_site in db["sites"]:
        sdir = os.path.join(SITES_DIR, target_site)
        if os.path.exists(sdir):
            shutil.rmtree(sdir)
        del db["sites"][target_site]
        save_data(db)
        await update.message.reply_text(f"✅ Site `{target_site[:16]}...` deleted!", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Site ID not found. Use `/sites` to see all.", parse_mode="Markdown")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    db = load_data()
    text = f"╔══════════════════════╗\n   👑 FULL STATS\n╚══════════════════════╝\n\n"
    text += f"━━━ *Users ({len(db['users'])}):* ━━━\n\n"
    for uid, uinfo in db["users"].items():
        site_count = len([s for s in db["sites"].values() if s.get("user_id") == uid])
        banned = "🚫" if uid in db.get("banned", []) else ""
        prem = "⭐" if uid in db.get("premium", []) else ""
        text += f"├ {prem}{banned} `{uid}` {uinfo['name']} ({site_count})\n"
    text += f"\n━━━ *Sites ({len(db['sites'])}):* ━━━\n\n"
    for sid, sinfo in db["sites"].items():
        text += f"├ `{sid[:12]}..` → {sinfo['url']}\n"
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i+4000], parse_mode="Markdown")

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    db = load_data()
    if not db["users"]:
        return await update.message.reply_text("No users yet.")
    text = f"👥 *Users ({len(db['users'])}):*\n\n"
    for uid, uinfo in db["users"].items():
        banned = "🚫" if uid in db.get("banned", []) else ""
        prem = "⭐" if uid in db.get("premium", []) else ""
        text += f"├ {prem}{banned} `{uid}` — {uinfo['name']}\n"
    for i in range(0, len(text), 4000):
        await update.message.reply_text(text[i:i+4000], parse_mode="Markdown")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return await update.message.reply_text("Usage: `/broadcast msg`", parse_mode="Markdown")
    msg_text = " ".join(context.args)
    db = load_data()
    success = failed = 0
    await update.message.reply_text(f"📤 Broadcasting to {len(db['users'])} users...")
    for uid in db["users"]:
        if uid in db.get("banned", []):
            continue
        try:
            await context.bot.send_message(
                int(uid),
                f"📢 *Broadcast:*\n\n{msg_text}",
                parse_mode="Markdown"
            )
            success += 1
        except:
            failed += 1
    await update.message.reply_text(f"✅ Sent: {success} | ❌ Failed: {failed}")

# ─── ERROR HANDLER ─────────────────────────────────────────────
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# ─── MAIN ──────────────────────────────────────────────────────
def main():
    threading.Thread(target=run_flask, daemon=True).start()

    app_tele = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app_tele.add_handler(CommandHandler("start", start))
    app_tele.add_handler(CommandHandler("help", help_cmd))
    app_tele.add_handler(CommandHandler("addch", add_channel))
    app_tele.add_handler(CommandHandler("delch", del_channel))
    app_tele.add_handler(CommandHandler("ban", ban_user))
    app_tele.add_handler(CommandHandler("unban", unban_user))
    app_tele.add_handler(CommandHandler("premium", premium_user))
    app_tele.add_handler(CommandHandler("unpremium", unpremium_user))
    app_tele.add_handler(CommandHandler("sites", list_sites))
    app_tele.add_handler(CommandHandler("delsite", del_site))
    app_tele.add_handler(CommandHandler("stats", stats_cmd))
    app_tele.add_handler(CommandHandler("users", users_cmd))
    app_tele.add_handler(CommandHandler("broadcast", broadcast))

    # Button text handlers
    btn_pattern = r'^(📤 Upload Website|🌐 My Website|🗑 Delete My Site|❓ Help|📊 Status|⚙️ Admin Panel|❌ Cancel)$'
    app_tele.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(btn_pattern), button_handler))

    # Document handler (HTML or ZIP files)
    app_tele.add_handler(MessageHandler(
        filters.Document.FileExtension("html") |
        filters.Document.FileExtension("htm") |
        filters.Document.FileExtension("zip"),
        handle_document
    ))

    # Fallback text
    app_tele.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: u.message.reply_text("👇 Use buttons below!", reply_markup=get_kb(u.effective_user.id))))

    # Error
    app_tele.add_error_handler(error_handler)

    logger.info("🤖 Bot + Web Server running...")
    app_tele.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
