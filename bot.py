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
PAYPAL_EMAIL = "minwass04@gmail.com"

CODES_FILE = "codes.json"
PAYMENTS_FILE = "payments.json"

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
            json={"intent": "CAPTURE", "purchase_units": [{"amount": {"currency_code": "EUR", "value": str(PRICE)}, "description": "Pokemon TCG Pocket Card Trade Access"}]}
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
    verify_channel = discord.utils.get(guild.text_channels, name="verification")
    if verify_channel:
        embed = discord.Embed(
            title="Welcome to the Pokemon TCG Pocket Trading Server!",
            description=(
                f"Hey {member.mention}, welcome!\n\n"
                "We offer a premium card trading service for Pokemon TCG Pocket.\n\n"
                "HOW IT WORKS\n"
                "1. Read the rules in rules\n"
                "2. Type !pay to start your order\n"
                "3. Pay 3.50 EUR via PayPal\n"
                "4. Type !confirm [ORDER_ID] after payment\n"
                "5. Receive your access code and trade!\n\n"
                f"Trading site: {TRADE_URL}\n\n"
                "Any questions? Open a ticket in support!"
            ),
            color=0xFFCC00
        )
        await verify_channel.send(embed=embed)

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
            title="PayPal Payment",
            description=(
                f"Price: 3.50 EUR\n\n"
                f"1. Click the link below to pay\n"
                f"2. Come back here after payment\n"
                f"3. Type: !confirm {order_id}\n\n"
                f"Payment link: {approve_link}\n\n"
                f"This link expires in 3 hours.\n"
                f"Do not share this link with anyone."
            ),
            color=0x003087
        )
        await ctx.author.send(embed=embed)
        await ctx.send(f"I sent you the payment instructions via DM, {ctx.author.mention}!")
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
        await ctx.send("No pending payment found. Start with !pay")
        return
    if payments[user_id].get("completed"):
        await ctx.send("Your payment is already validated! Use !mycode")
        return
    await ctx.send("Verifying your payment, please wait...")
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
                    f"Instructions:\n"
                    f"1. Go to {TRADE_URL}\n"
                    f"2. Enter your access code\n"
                    f"3. Choose your card\n"
                    f"4. Enter your in-game friend code\n"
                    f"5. Follow the on-screen instructions\n\n"
                    f"Code is single-use and valid for 7 days.\n"
                    f"Need help? Contact an admin."
                ),
                color=0x00FF00
            )
            await ctx.author.send(embed=embed)
            await ctx.send(f"Payment confirmed! Code sent via DM, {ctx.author.mention}")
        else:
            await ctx.send("Payment not found or incomplete. Make sure you completed the payment and try again.")
    except Exception as e:
        await ctx.send("Error verifying payment. Please contact an admin.")
        print(f"Verification error: {e}")

@bot.command()
async def mycode(ctx):
    payments = load_json(PAYMENTS_FILE)
    user_id = str(ctx.author.id)
    if user_id in payments and payments[user_id].get("completed"):
        code = payments[user_id].get("code")
        embed = discord.Embed(
            title="Your Access Code",
            description=f"{code}\n\nTrading site: {TRADE_URL}",
            color=0xFFCC00
        )
        await ctx.author.send(embed=embed)
        await ctx.send(f"Code sent via DM, {ctx.author.mention}!")
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
    embed.add_field(name="Confirmed Payments", value=total_payments, inline=True)
    embed.add_field(name="Estimated Revenue", value=f"{total_payments * 3.5} EUR", inline=True)
    await ctx.send(embed=embed)

async def setup_server():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("Server not found")
        return

    roles_to_create = [
        ("Owner", 0xFF0000, True),
        ("Admin", 0xFF4400, True),
        ("Moderator", 0xFF6600, True),
        ("Buyer", 0xFFCC00, True),
        ("Member", 0x7289DA, False),
    ]
    existing_roles = [r.name for r in guild.roles]
    for role_name, color, hoist in roles_to_create:
        if role_name not in existing_roles:
            await guild.create_role(name=role_name, color=discord.Color(color), hoist=hoist)

    channels_structure = {
        "WELCOME HUB": ["rules", "announcements", "partners", "roles", "news", "giveaway"],
        "TRADING HUB": ["how-it-works", "verification", "payment", "my-trades", "trade-shiny", "trade-star", "trade-diamond", "friend-codes"],
        "SOCIAL HUB": ["general-chat", "pokemon-universe", "off-topic", "openings", "failed-openings", "battles"],
        "GAME HUB": ["guides", "decks", "deck-building", "help", "leaks"],
        "VOICE HUB": [],
        "ADMINISTRATION": ["logs-admin", "admin-commands"],
    }

    voice_channels = ["Discussion 1", "Discussion 2", "Discussion 3", "Discussion 4", "Discussion 5", "AFK"]

    existing_channels = [c.name for c in guild.channels]

    for category_name, channels in channels_structure.items():
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            category = await guild.create_category(category_name)
        for channel_name in channels:
            if channel_name not in existing_channels:
                await guild.create_text_channel(channel_name, category=category)

    voice_category = discord.utils.get(guild.categories, name="VOICE HUB")
    if not voice_category:
        voice_category = await guild.create_category("VOICE HUB")
    for vc_name in voice_channels:
        if vc_name not in existing_channels:
            await guild.create_voice_channel(vc_name, category=voice_category)

    rules_channel = discord.utils.get(guild.text_channels, name="rules")
    if rules_channel:
        history = [msg async for msg in rules_channel.history(limit=1)]
        if not history:
            embed = discord.Embed(
                title="Server Rules",
                description=(
                    "Welcome to the Pokemon TCG Pocket Trading Server!\n\n"
                    "GENERAL RULES\n"
                    "1. Respect Discord Terms of Service at all times.\n"
                    "2. No harassment, hate speech, racism, or discrimination.\n"
                    "3. No explicit, NSFW, or controversial content.\n"
                    "4. No spam, self-promotion, or unauthorized advertising.\n"
                    "5. Be respectful to all members and staff.\n"
                    "6. No sharing of personal information without consent.\n"
                    "7. Use the correct channels for each topic.\n\n"
                    "TRADING RULES\n"
                    "8. A payment of 3.50 EUR is required before any trade.\n"
                    "9. Access codes are single-use and valid for 7 days.\n"
                    "10. No refunds after code has been used.\n"
                    "11. Do not share your access code with anyone.\n"
                    "12. Any attempt to scam or cheat will result in a permanent ban.\n\n"
                    "MODERATION\n"
                    "Warning - Mute - Kick - Permanent Ban\n\n"
                    "By joining this server, you agree to these rules."
                ),
                color=0xFFCC00
            )
            await rules_channel.send(embed=embed)

    how_channel = discord.utils.get(guild.text_channels, name="how-it-works")
    if how_channel:
        history = [msg async for msg in how_channel.history(limit=1)]
        if not history:
            embed = discord.Embed(
                title="How to Get Your Pokemon TCG Pocket Card",
                description=(
                    "Welcome! Here is everything you need to know about our trading service.\n\n"
                    "WHAT WE OFFER\n"
                    "We provide a fast and secure card trading service for Pokemon TCG Pocket.\n"
                    "You choose the card you want, we handle the trade.\n"
                    "All cards available: Shiny, Star, Diamond, and more!\n\n"
                    "PRICE\n"
                    "3.50 EUR per trade via PayPal\n\n"
                    "STEP BY STEP\n"
                    "Step 1 - Read the rules in rules\n"
                    "Step 2 - Go to verification and type !pay\n"
                    "Step 3 - Pay 3.50 EUR via the PayPal link sent to your DMs\n"
                    "Step 4 - Type !confirm [ORDER_ID] after payment\n"
                    "Step 5 - Receive your unique access code via DM\n"
                    "Step 6 - Go to our trading site and enter your code\n"
                    "Step 7 - Choose your card and enter your friend code\n"
                    "Step 8 - Follow the on-screen instructions to complete the trade\n\n"
                    "IMPORTANT\n"
                    "Each code is single-use and valid for 7 days.\n"
                    "Do not share your code with anyone.\n"
                    "No refunds after the code has been used.\n\n"
                    f"Trading site: {TRADE_URL}\n\n"
                    "Questions? Open a ticket in support!"
                ),
                color=0xFF5500
            )
            await how_channel.send(embed=embed)

    faq_channel = discord.utils.get(guild.text_channels, name="help")
    if faq_channel:
        history = [msg async for msg in faq_channel.history(limit=1)]
        if not history:
            embed = discord.Embed(
                title="FAQ - Frequently Asked Questions",
                description=(
                    "How do I get a card?\n"
                    "Go to verification and type !pay, then follow the steps.\n\n"
                    "How much does it cost?\n"
                    "3.50 EUR per trade via PayPal.\n\n"
                    "Which cards are available?\n"
                    "All rarities: Shiny, Star, Diamond, and more!\n\n"
                    "How long does the trade take?\n"
                    "Usually within a few minutes after payment confirmation.\n\n"
                    "My code does not work?\n"
                    "Contact an admin with a screenshot.\n\n"
                    "How long is my code valid?\n"
                    "7 days from the date of purchase.\n\n"
                    "Can I get a refund?\n"
                    "No refunds once the code has been used.\n\n"
                    f"Trading site: {TRADE_URL}"
                ),
                color=0x7289DA
            )
            await faq_channel.send(embed=embed)

    print("Server setup complete!")

bot.run(DISCORD_TOKEN)
