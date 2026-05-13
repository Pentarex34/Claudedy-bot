import discord
from discord.ext import commands
import aiohttp
import asyncio
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
            json={"intent": "CAPTURE", "purchase_units": [{"amount": {"currency_code": "EUR", "value": str(PRICE)}, "description": "Acces echange carte Pokemon TCG Pocket"}]}
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
    print(f"Bot connecte : {bot.user}")
    print(f"Serveur : {guild.name if guild else 'Non trouve'}")
    await setup_server()

@bot.event
async def on_member_join(member):
    guild = bot.get_guild(GUILD_ID)
    verify_channel = discord.utils.get(guild.text_channels, name="verification")
    if verify_channel:
        embed = discord.Embed(
            title="Bienvenue sur le serveur Pokemon TCG Pocket !",
            description=f"Salut {member.mention} !\n\n1. Lis le reglement\n2. Tape !payer pour commencer\n3. Paie 3,50 EUR via PayPal\n4. Tape !confirmer [ID] apres paiement\n5. Recois ton code et fais ton echange !\n\nSite : {TRADE_URL}",
            color=0xFFCC00
        )
        await verify_channel.send(embed=embed)

@bot.command()
async def payer(ctx):
    payments = load_json(PAYMENTS_FILE)
    user_id = str(ctx.author.id)
    if user_id in payments and payments[user_id].get("completed"):
        await ctx.send("Tu as deja effectue un achat ! Utilise !moncode")
        return
    try:
        order_id, approve_link = await create_paypal_order()
        payments[user_id] = {"order_id": order_id, "completed": False, "created_at": datetime.now().isoformat()}
        save_json(PAYMENTS_FILE, payments)
        embed = discord.Embed(
            title="Paiement PayPal",
            description=f"Prix : 3,50 EUR\n\n1. Clique sur le lien pour payer\n2. Reviens ici apres\n3. Tape : !confirmer {order_id}\n\nLien : {approve_link}\n\nLien expire dans 3 heures",
            color=0x003087
        )
        await ctx.author.send(embed=embed)
        await ctx.send(f"Je t'ai envoye les instructions en MP {ctx.author.mention} !")
    except Exception as e:
        await ctx.send("Erreur lors de la creation du paiement. Reessaie plus tard.")
        print(f"Erreur PayPal: {e}")

@bot.command()
async def confirmer(ctx, order_id: str = None):
    if not order_id:
        await ctx.send("Utilise : !confirmer [ID_commande]")
        return
    payments = load_json(PAYMENTS_FILE)
    user_id = str(ctx.author.id)
    if user_id not in payments:
        await ctx.send("Aucun paiement en attente. Commence par !payer")
        return
    if payments[user_id].get("completed"):
        await ctx.send("Ton paiement a deja ete valide ! Utilise !moncode")
        return
    await ctx.send("Verification du paiement en cours...")
    try:
        verified = await verify_paypal_payment(order_id)
        if verified:
            code = get_available_code()
            if not code:
                await ctx.send("Plus de codes disponibles. Contacte un admin !")
                return
            mark_code_used(code, ctx.author.id)
            payments[user_id]["completed"] = True
            payments[user_id]["code"] = code
            payments[user_id]["validated_at"] = datetime.now().isoformat()
            save_json(PAYMENTS_FILE, payments)
            guild = bot.get_guild(GUILD_ID)
            role = discord.utils.get(guild.roles, name="Acheteur")
            if role:
                member = guild.get_member(ctx.author.id)
                await member.add_roles(role)
            embed = discord.Embed(
                title="Paiement valide !",
                description=f"Felicitations {ctx.author.mention} !\n\nTon code : {code}\n\n1. Va sur {TRADE_URL}\n2. Entre ton code\n3. Choisis ta carte\n4. Entre ton code ami\n5. Suis les instructions\n\nCode usage unique - valide 7 jours",
                color=0x00FF00
            )
            await ctx.author.send(embed=embed)
            await ctx.send(f"Paiement valide ! Code envoye en MP {ctx.author.mention}")
        else:
            await ctx.send("Paiement non trouve. Verifie que tu as bien paye et reessaie.")
    except Exception as e:
        await ctx.send("Erreur lors de la verification. Contacte un admin.")
        print(f"Erreur verification: {e}")

@bot.command()
async def moncode(ctx):
    payments = load_json(PAYMENTS_FILE)
    user_id = str(ctx.author.id)
    if user_id in payments and payments[user_id].get("completed"):
        code = payments[user_id].get("code")
        embed = discord.Embed(title="Ton code d'acces", description=f"{code}\n\nSite : {TRADE_URL}", color=0xFFCC00)
        await ctx.author.send(embed=embed)
        await ctx.send(f"Code envoye en MP {ctx.author.mention} !")
    else:
        await ctx.send("Aucun code trouve. Utilise !payer pour commencer.")

@bot.command()
@commands.has_permissions(administrator=True)
async def ajoutercodes(ctx, *, codes_text: str):
    new_codes = [c.strip() for c in codes_text.strip().split("\n") if c.strip()]
    add_codes(new_codes)
    await ctx.send(f"{len(new_codes)} code(s) ajoute(s) !")

@bot.command()
@commands.has_permissions(administrator=True)
async def stats(ctx):
    codes = load_json(CODES_FILE)
    payments = load_json(PAYMENTS_FILE)
    total_codes = len(codes)
    used_codes = sum(1 for c in codes.values() if c.get("used"))
    total_payments = sum(1 for p in payments.values() if p.get("completed"))
    embed = discord.Embed(title="Statistiques", color=0x7289DA)
    embed.add_field(name="Codes total", value=total_codes, inline=True)
    embed.add_field(name="Codes utilises", value=used_codes, inline=True)
    embed.add_field(name="Codes disponibles", value=total_codes - used_codes, inline=True)
    embed.add_field(name="Paiements valides", value=total_payments, inline=True)
    embed.add_field(name="Revenus estimes", value=f"{total_payments * 3.5} EUR", inline=True)
    await ctx.send(embed=embed)

async def setup_server():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print("Serveur non trouve")
        return
    roles_to_create = [
        ("Admin", 0xFF0000, True),
        ("Moderateur", 0xFF6600, True),
        ("Acheteur", 0xFFCC00, False),
        ("Membre", 0x7289DA, False),
    ]
    existing_roles = [r.name for r in guild.roles]
    for role_name, color, hoist in roles_to_create:
        if role_name not in existing_roles:
            await guild.create_role(name=role_name, color=discord.Color(color), hoist=hoist)
    channels_structure = {
        "INFORMATIONS": ["annonces", "reglement", "faq"],
        "ECHANGES": ["verification", "paiement", "mes-echanges"],
        "COMMUNAUTE": ["general", "presentation"],
        "ADMINISTRATION": ["logs-admin", "commandes-admin"],
    }
    existing_channels = [c.name for c in guild.channels]
    for category_name, channels in channels_structure.items():
        category = discord.utils.get(guild.categories, name=category_name)
        if not category:
            category = await guild.create_category(category_name)
        for channel_name in channels:
            if channel_name not in existing_channels:
                await guild.create_text_channel(channel_name, category=category)
    rules_channel = discord.utils.get(guild.text_channels, name="reglement")
    if rules_channel:
        history = [msg async for msg in rules_channel.history(limit=1)]
        if not history:
            embed = discord.Embed(
                title="Reglement du serveur",
                description=f"1. Sois respectueux\n2. Pas de spam\n3. Paiement de 3,50 EUR obligatoire\n4. Codes a usage unique valides 7 jours\n5. Aucun remboursement apres utilisation\n6. En cas de probleme contacte un admin",
                color=0xFFCC00
            )
            await rules_channel.send(embed=embed)
    faq_channel = discord.utils.get(guild.text_channels, name="faq")
    if faq_channel:
        history = [msg async for msg in faq_channel.history(limit=1)]
        if not history:
            embed = discord.Embed(
                title="FAQ",
                description=f"Comment faire un echange ?\nTape !payer dans verification.\n\nCombien ca coute ?\n3,50 EUR par echange via PayPal.\n\nMon code ne fonctionne pas ?\nContacte un admin.\n\nDuree de validite du code ?\n7 jours.\n\nSite : {TRADE_URL}",
                color=0x7289DA
            )
            await faq_channel.send(embed=embed)
    print("Serveur configure !")

bot.run(DISCORD_TOKEN)
