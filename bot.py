import discord
from discord.ext import commands
import aiohttp
import json
import os
import base64
from datetime import datetime, timedelta

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
GUILD_ID = int(os.getenv("GUILD_ID", "1503817221162406001"))
TRADE_URL = "https://trade.clicker2026.com"
PRICE = 3.50

CODES_FILE = "codes.json"
PAYMENTS_FILE = "payments.json"
RULES_MESSAGE_FILE = "rules_message.json"

def load_json(file):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def get_paypal_token():
    credentials = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()).decode()
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api-m.paypal.com/v1/oauth2/token",
            headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
            data="grant_type=client_credentials"
        ) as resp:
            data = await resp.json()
            return data.get("access_token")

async def verify_paypal_payment(order_id):
    token = await get_paypal_token()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api-m.paypal.com/v2/checkout/orders/{order_id}",
            headers={"Authorization": f"Bearer {token}"}
        ) as resp:
            data = await resp.json()
            if data.get("status") == "COMPLETED":
                amount = float(data["purchase_units"][0]["amount"]["value"])
                if amount >= PRICE:
                    return True
    return False

async def create_paypal_order():
    token = await get_paypal_token()
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api-m.paypal.com/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"intent": "CAPTURE", "purchase_units": [{"amount": {"currency_code": "EUR", "value": str(PRICE)}, "description": "Pokemon TCG Pocket Card Trade"}]}
        ) as resp:
            data = await resp.json()
            order_id = data["id"]
            approve_link = next(l["href"] for l in data["links"] if l["rel"] == "approve")
            return order_id, approve_link

def get_available_code():
    codes = load_json(CODES_FILE)
    for code, info in codes.items():
        if not info.get("used"):
            expiry = datetime.fromisoformat(info["expiry"])
            if datetime.now() < expiry:
                return code
    return None

def mark_code_used(code, user_id):
    codes = load_json(CODES_FILE)
    if code in codes:
        codes[code]["used"] = True
        codes[code]["used_by"] = str(user_id)
        codes[code]["used_at"] = datetime.now().isoformat()
        save_json(CODES_FILE, codes)

def add_codes(new_codes: list):
    codes = load_json(CODES_FILE)
    for code in new_codes:
        expiry = (datetime.now() + timedelta(days=7)).isoformat()
        codes[code] = {"used": False, "expiry": expiry, "added_at": datetime.now().isoformat()}
    save_json(CODES_FILE, codes)

@bot.event
async def on_ready():
    guild = bot.get_guild(GUILD_ID)
    print(f"Bot connected: {bot.user}")
    print(f"Server: {guild.name if guild else 'Not found'}")
    await setup_server()

@bot.event
async def on_member_join(member):
    guild = bot.get_guild(GUILD_ID)
    rules_channel = discord.utils.get(guild.text_channels, name="rules")
    if rules_channel:
        embed = discord.Embed(
            title="Welcome to Pokemon TCGP Trade!",
            description=(
                f"Hey {member.mention}!\n\n"
                "To access the server, please read the rules in rules and react with the checkmark.\n\n"
                "We offer a premium Pokemon TCG Pocket card trading service.\n"
                f"Price: 3.50 EUR per trade\n"
                f"Site: {TRADE_URL}"
            ),
            color=0xFFCC00
        )
        await rules_channel.send(embed=embed, delete_after=30)

@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.emoji) != "checkmark":
        return
    data = load_json(RULES_MESSAGE_FILE)
    if str(payload.message_id) != str(data.get("message_id")):
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return
    role = discord.utils.get(guild.roles, name="Member")
    if role and role not in member.roles:
        await member.add_roles(role)
        print(f"Role Member given to {member.name}")

@bot.event
async def on_raw_reaction_remove(payload):
    if str(payload.emoji) != "checkmark":
        return
    data = load_json(RULES_MESSAGE_FILE)
    if str(payload.message_id) != str(data.get("message_id")):
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    member = guild.get_member(payload.user_id)
    if not member or member.bot:
        return
    role = discord.utils.get(guild.roles, name="Member")
    if role and role in member.roles:
        await member.remove_roles(role)

@bot.command()
async def pay(ctx):
    payments = load_json(PAYMENTS_FILE)
    user_id = str(ctx.author.id)
    if user_id in payments and payments[user_id].get("completed"):
        await ctx.send("You already made a purchase! Use !mycode to get your code.")
        return
    try:
        order_id, approve_link = await create_paypal_order()
        payments[user_id] = {"order_id": order_id, "completed": False, "created_at": datetime.now().isoformat()}
        save_json(PAYMENTS_FILE, payments)
        embed = discord.Embed(
            title="PayPal Payment - Pokemon TCGP Trade",
            description=(
                f"Price: 3.50 EUR\n\n"
                f"Step 1: Click the payment link below\n"
                f"Step 2: Complete the PayPal payment\n"
                f"Step 3: Come back and type !confirm {order_id}\n\n"
                f"Payment link: {approve_link}\n\n"
                f"This link expires in 3 hours.\n"
                f"Keep your Order ID safe!"
            ),
            color=0x003087
        )
        await ctx.author.send(embed=embed)
        await ctx.send(f"Payment instructions sent to your DMs, {ctx.author.mention}!")
    except Exception as e:
        await ctx.send("Error creating payment. Please try again later.")
        print(f"PayPal error: {e}")

@bot.command()
async def confirm(ctx, order_id: str = None):
    if not order_id:
        await ctx.send("Usage: !confirm [ORDER_ID]")
        return
    payments = load_json(PAYMENTS_FILE)
    user_id = str(ctx.author.id)
    if user_id not in payments:
        await ctx.send("No pending payment found. Use !pay first.")
        return
    if payments[user_id].get("completed"):
        await ctx.send("Payment already validated! Use !mycode to get your code.")
        return
    await ctx.send("Verifying your payment...")
    try:
        verified = await verify_paypal_payment(order_id)
        if verified:
            code = get_available_code()
            if not code:
                await ctx.send("No codes available right now. Please contact an admin!")
                return
            mark_code_used(code, ctx.author.id)
            payments[user_id]["completed"] = True
            payments[user_id]["code"] = code
            payments[user_id]["validated_at"] = datetime.now().isoformat()
            save_json(PAYMENTS_FILE, payments)
            guild = bot.get_guild(GUILD_ID)
            role = discord.utils.get(guild.roles, name="Buyer")
            if role:
                member = guild.get_member(ctx.author.id)
                await member.add_roles(role)
            embed = discord.Embed(
                title="Payment Confirmed!",
                description=(
                    f"Congratulations {ctx.author.mention}!\n\n"
                    f"Your access code:\n{code}\n\n"
                    f"How to use it:\n"
                    f"1. Go to {TRADE_URL}\n"
                    f"2. Enter your access code\n"
                    f"3. Select your card\n"
                    f"4. Enter your in-game friend code\n"
                    f"5. Follow on-screen instructions\n\n"
                    f"Code is single-use, valid for 7 days.\n"
                    f"Need help? Contact an admin."
                ),
                color=0x00FF00
            )
            await ctx.author.send(embed=embed)
            await ctx.send(f"Payment confirmed! Code sent to your DMs, {ctx.author.mention}!")
        else:
            await ctx.send("Payment not found or incomplete. Please verify and try again.")
    except Exception as e:
        await ctx.send("Error verifying payment. Contact an admin.")
        print(f"Verification error: {e}")

@bot.command()
async def mycode(ctx):
    payments = load_json(PAYMENTS_FILE)
    user_id = str(ctx.author.id)
    if user_id in payments and payments[user_id].get("completed"):
        code = payments[user_id].get("code")
        embed = discord.Embed(
            title="Your Access Code",
            description=f"Code: {code}\n\nSite: {TRADE_URL}",
            color=0xFFCC00
        )
        await ctx.author.send(embed=embed)
        await ctx.send(f"Code sent to your DMs, {ctx.author.mention}!")
    else:
        await ctx.send("No code found. Use !pay to get started.")

@bot.command()
@commands.has_permissions(administrator=True)
async def addcodes(ctx, *, codes_text: str):
    new_codes = [c.strip() for c in codes_text.strip().split("\n") if c.strip()]
    add_codes(new_codes)
    await ctx.send(f"{len(new_codes)} code(s) added successfully!")

@bot.command()
@commands.has_permissions(administrator=True)
async def stats(ctx):
    codes = load_json(CODES_FILE)
    payments = load_json(PAYMENTS_FILE)
    total_codes = len(codes)
    used_codes = sum(1 for c in codes.values() if c.get("used"))
    total_payments = sum(1 for p in payments.values() if p.get("completed"))
    embed = discord.Embed(title="Server Statistics", color=0x7289DA)
    embed.add_field(name="Total Codes", value=total_codes, inline=True)
    embed.add_field(name="Used Codes", value=used_codes, inline=True)
    embed.add_field(name="Available Codes", value=total_codes - used_codes, inline=True)
    embed.add_field(name="Confirmed Sales", value=total_payments, inline=True)
    embed.add_field(name="Total Revenue", value=f"{total_payments * 3.5} EUR", inline=True)
    await ctx.send(embed=embed)

async def setup_server():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("Server not found")
        return

    member_role = discord.utils.get(guild.roles, name="Member")
    if not member_role:
        member_role = await guild.create_role(name="Member", color=discord.Color(0x7289DA), hoist=False)

    buyer_role = discord.utils.get(guild.roles, name="Buyer")
    if not buyer_role:
        buyer_role = await guild.create_role(name="Buyer", color=discord.Color(0xFFCC00), hoist=True)

    mod_role = discord.utils.get(guild.roles, name="Moderator")
    if not mod_role:
        mod_role = await guild.create_role(name="Moderator", color=discord.Color(0xFF6600), hoist=True)

    admin_role = discord.utils.get(guild.roles, name="Admin")
    if not admin_role:
        admin_role = await guild.create_role(name="Admin", color=discord.Color(0xFF0000), hoist=True)

    everyone = guild.default_role

    no_access = {
        everyone: discord.PermissionOverwrite(read_messages=False),
        member_role: discord.PermissionOverwrite(read_messages=True),
    }

    rules_access = {
        everyone: discord.PermissionOverwrite(read_messages=True),
        member_role: discord.PermissionOverwrite(read_messages=True),
    }

    admin_only = {
        everyone: discord.PermissionOverwrite(read_messages=False),
        admin_role: discord.PermissionOverwrite(read_messages=True),
        mod_role: discord.PermissionOverwrite(read_messages=True),
    }

    channels_setup = [
        ("WELCOME", [
            ("rules", rules_access),
            ("announcements", no_access),
        ]),
        ("TRADING", [
            ("how-it-works", no_access),
            ("verification", no_access),
            ("my-trades", no_access),
            ("friend-codes", no_access),
        ]),
        ("COMMUNITY", [
            ("general", no_access),
            ("pokemon-universe", no_access),
            ("off-topic", no_access),
        ]),
        ("ADMINISTRATION", []),
    ]

    for category_name, channels in channels_setup:
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            category = await guild.create_category(category_name)

        for channel_name, overwrites in channels:
            existing = discord.utils.get(guild.text_channels, name=channel_name)
            if not existing:
                await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

    admin_category = discord.utils.get(guild.categories, name="ADMINISTRATION")
    if not admin_category:
        admin_category = await guild.create_category("ADMINISTRATION")
    for ch_name in ["admin-commands", "logs"]:
        if not discord.utils.get(guild.text_channels, name=ch_name):
            await guild.create_text_channel(ch_name, category=admin_category, overwrites=admin_only)

    voice_category = discord.utils.get(guild.categories, name="VOICE")
    if not voice_category:
        voice_category = await guild.create_category("VOICE")
    for vc_name in ["Lounge", "Trading Room", "AFK"]:
        if not discord.utils.get(guild.voice_channels, name=vc_name):
            await guild.create_voice_channel(vc_name, category=voice_category)

    rules_channel = discord.utils.get(guild.text_channels, name="rules")
    if rules_channel:
        history = [msg async for msg in rules_channel.history(limit=5)]
        bot_messages = [m for m in history if m.author == guild.me]
        if not bot_messages:
            embed = discord.Embed(
                title="Pokemon TCGP Trade - Server Rules",
                description=(
                    "Welcome to the #1 Pokemon TCG Pocket card trading server!\n\n"
                    "GENERAL RULES\n"
                    "1. Respect Discord Terms of Service at all times.\n"
                    "2. No harassment, hate speech, racism or discrimination.\n"
                    "3. No NSFW or explicit content.\n"
                    "4. No spam, self-promotion or unauthorized advertising.\n"
                    "5. Be respectful to all members and staff.\n"
                    "6. Do not share personal information without consent.\n"
                    "7. Use the correct channels for each topic.\n\n"
                    "TRADING RULES\n"
                    "8. A payment of 3.50 EUR is required before any trade.\n"
                    "9. Access codes are single-use and valid for 7 days.\n"
                    "10. No refunds after the code has been used.\n"
                    "11. Do not share your access code with anyone.\n"
                    "12. Any scam attempt results in a permanent ban.\n\n"
                    "HOW TO TRADE\n"
                    "1. React with the checkmark below to access the server.\n"
                    "2. Go to how-it-works for full instructions.\n"
                    "3. Type !pay in verification to start your order.\n\n"
                    "SANCTIONS\n"
                    "Warning - Mute - Kick - Permanent Ban\n\n"
                    "React with the checkmark below to accept the rules and access the server!"
                ),
                color=0xFFCC00
            )
            msg = await rules_channel.send(embed=embed)
            await msg.add_reaction("checkmark")
            save_json(RULES_MESSAGE_FILE, {"message_id": msg.id})

    how_channel = discord.utils.get(guild.text_channels, name="how-it-works")
    if how_channel:
        history = [msg async for msg in how_channel.history(limit=5)]
        bot_messages = [m for m in history if m.author == guild.me]
        if not bot_messages:
            embed = discord.Embed(
                title="How to Get Your Pokemon TCG Pocket Card",
                description=(
                    "We offer a fast, secure and reliable card trading service.\n"
                    "You pick the card, we handle the rest!\n\n"
                    "AVAILABLE CARDS\n"
                    "All rarities available:\n"
                    "Shiny cards, 2-Star cards, 1-Star cards, Diamond cards and more!\n\n"
                    "PRICE\n"
                    "3.50 EUR per trade via PayPal\n"
                    "Fast delivery, usually within minutes!\n\n"
                    "HOW IT WORKS\n"
                    "Step 1 - Go to verification and type !pay\n"
                    "Step 2 - Pay 3.50 EUR via the PayPal link sent to your DMs\n"
                    "Step 3 - Type !confirm [ORDER_ID] after payment\n"
                    "Step 4 - Receive your unique access code via DM\n"
                    f"Step 5 - Go to {TRADE_URL}\n"
                    "Step 6 - Enter your access code and select your card\n"
                    "Step 7 - Enter your in-game friend code\n"
                    "Step 8 - Complete the trade in-game!\n\n"
                    "IMPORTANT INFO\n"
                    "Each code is single-use and valid for 7 days.\n"
                    "Never share your code with anyone.\n"
                    "No refunds after the code has been used.\n\n"
                    "Questions? Contact an admin!"
                ),
                color=0xFF5500
            )
            await how_channel.send(embed=embed)

    print("Server setup complete!")

bot.run(DISCORD_TOKEN)
