import discord
from discord.ext import commands
import aiohttp
import asyncio
import json
import os
import base64
from datetime import datetime, timedelta
import uuid

# ============================================================

# CONFIGURATION

# ============================================================

DISCORD_TOKEN = “MTUwMzgxNTkzNDM1ODMyMzMzMg.G0xOt_.B2BH2G0G1KyUMDMzfMk6Ht8mHmoDyJ-S4ZmDOI”
PAYPAL_CLIENT_ID = “AQa5nklUWybhwQdJz_T2zauEm59gHO6SpjeEQIjnZHUG0IOzPOtXPfUaBP6al3hVrrviFIlfrGv3WJwF”
PAYPAL_CLIENT_SECRET = “EF9nGxAukPjZ84t1_e6OHbMRJLhKB41RqPL8o59AZuVQqss4BqcE4y9S-KBTpw9nCbvPzb6HfAo9146D”
GUILD_ID = 1503817221162406001
TRADE_URL = “https://trade.clicker2026.com”
PRICE = 3.50
PAYPAL_EMAIL = “minwass04@gmail.com”

# ============================================================

# FICHIERS DE DONNÉES

# ============================================================

CODES_FILE = “codes.json”
PAYMENTS_FILE = “payments.json”

def load_json(file):
if os.path.exists(file):
with open(file, “r”) as f:
return json.load(f)
return {}

def save_json(file, data):
with open(file, “w”) as f:
json.dump(data, f, indent=2)

# ============================================================

# BOT SETUP

# ============================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=”!”, intents=intents)

# ============================================================

# PAYPAL API

# ============================================================

async def get_paypal_token():
credentials = base64.b64encode(f”{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}”.encode()).decode()
async with aiohttp.ClientSession() as session:
async with session.post(
“https://api-m.paypal.com/v1/oauth2/token”,
headers={
“Authorization”: f”Basic {credentials}”,
“Content-Type”: “application/x-www-form-urlencoded”
},
data=“grant_type=client_credentials”
) as resp:
data = await resp.json()
return data.get(“access_token”)

async def verify_paypal_payment(order_id):
token = await get_paypal_token()
async with aiohttp.ClientSession() as session:
async with session.get(
f”https://api-m.paypal.com/v2/checkout/orders/{order_id}”,
headers={“Authorization”: f”Bearer {token}”}
) as resp:
data = await resp.json()
if data.get(“status”) == “COMPLETED”:
amount = float(data[“purchase_units”][0][“amount”][“value”])
if amount >= PRICE:
return True
return False

async def create_paypal_order():
token = await get_paypal_token()
async with aiohttp.ClientSession() as session:
async with session.post(
“https://api-m.paypal.com/v2/checkout/orders”,
headers={
“Authorization”: f”Bearer {token}”,
“Content-Type”: “application/json”
},
json={
“intent”: “CAPTURE”,
“purchase_units”: [{
“amount”: {
“currency_code”: “EUR”,
“value”: str(PRICE)
},
“description”: “Accès échange carte Pokémon TCG Pocket”
}]
}
) as resp:
data = await resp.json()
order_id = data[“id”]
approve_link = next(l[“href”] for l in data[“links”] if l[“rel”] == “approve”)
return order_id, approve_link

# ============================================================

# GESTION DES CODES

# ============================================================

def get_available_code():
codes = load_json(CODES_FILE)
for code, info in codes.items():
if not info.get(“used”):
expiry = datetime.fromisoformat(info[“expiry”])
if datetime.now() < expiry:
return code
return None

def mark_code_used(code, user_id):
codes = load_json(CODES_FILE)
if code in codes:
codes[code][“used”] = True
codes[code][“used_by”] = str(user_id)
codes[code][“used_at”] = datetime.now().isoformat()
save_json(CODES_FILE, codes)

def add_codes(new_codes: list):
codes = load_json(CODES_FILE)
for code in new_codes:
expiry = (datetime.now() + timedelta(days=7)).isoformat()
codes[code] = {“used”: False, “expiry”: expiry, “added_at”: datetime.now().isoformat()}
save_json(CODES_FILE, codes)

# ============================================================

# EVENTS

# ============================================================

@bot.event
async def on_ready():
guild = bot.get_guild(GUILD_ID)
print(f”✅ Bot connecté : {bot.user}”)
print(f”✅ Serveur : {guild.name if guild else ‘Non trouvé’}”)
await setup_server()

@bot.event
async def on_member_join(member):
guild = bot.get_guild(GUILD_ID)
verify_channel = discord.utils.get(guild.text_channels, name=“✅・vérification”)
if verify_channel:
embed = discord.Embed(
title=“🎴 Bienvenue sur le serveur d’échange Pokémon TCG Pocket !”,
description=(
f”Salut {member.mention} ! 👋\n\n”
“Pour accéder aux échanges de cartes, voici comment ça marche :\n\n”
“**📋 Étapes :**\n”
“1️⃣ Lis le règlement dans 📜・règlement\n”
“2️⃣ Tape `!payer` ici pour commencer\n”
“3️⃣ Paie **3,50€** via PayPal\n”
“4️⃣ Confirme ton paiement avec `!confirmer [ID_commande]`\n”
“5️⃣ Reçois ton code d’accès et fais ton échange ! 🎉\n\n”
f”🌐 Site d’échange : {TRADE_URL}”
),
color=0xFFCC00
)
embed.set_thumbnail(url=“https://upload.wikimedia.org/wikipedia/commons/thumb/5/53/Pok%C3%A9_Ball_icon.svg/256px-Pok%C3%A9_Ball_icon.svg.png”)
await verify_channel.send(embed=embed)

# ============================================================

# COMMANDES

# ============================================================

@bot.command()
async def payer(ctx):
“”“Lance le processus de paiement”””
payments = load_json(PAYMENTS_FILE)
user_id = str(ctx.author.id)

```
# Vérifier si déjà acheté
if user_id in payments and payments[user_id].get("completed"):
    await ctx.send("✅ Tu as déjà effectué un achat ! Utilise `!moncode` pour voir ton code.")
    return

try:
    order_id, approve_link = await create_paypal_order()
    payments[user_id] = {"order_id": order_id, "completed": False, "created_at": datetime.now().isoformat()}
    save_json(PAYMENTS_FILE, payments)

    embed = discord.Embed(
        title="💳 Paiement PayPal",
        description=(
            f"**Prix : 3,50 €**\n\n"
            f"1️⃣ Clique sur le lien ci-dessous pour payer\n"
            f"2️⃣ Une fois le paiement effectué, reviens ici\n"
            f"3️⃣ Tape : `!confirmer {order_id}`\n\n"
            f"🔗 [**Cliquez ici pour payer**]({approve_link})\n\n"
            f"⏰ Ce lien expire dans 3 heures"
        ),
        color=0x003087
    )
    await ctx.author.send(embed=embed)
    await ctx.send(f"📩 {ctx.author.mention} Je t'ai envoyé les instructions en message privé !")
except Exception as e:
    await ctx.send("❌ Erreur lors de la création du paiement. Réessaie plus tard.")
    print(f"Erreur PayPal: {e}")
```

@bot.command()
async def confirmer(ctx, order_id: str = None):
“”“Confirme le paiement avec l’ID de commande PayPal”””
if not order_id:
await ctx.send(“❌ Utilise : `!confirmer [ID_commande]`”)
return

```
payments = load_json(PAYMENTS_FILE)
user_id = str(ctx.author.id)

if user_id not in payments:
    await ctx.send("❌ Aucun paiement en attente. Commence par `!payer`")
    return

if payments[user_id].get("completed"):
    await ctx.send("✅ Ton paiement a déjà été validé ! Utilise `!moncode`")
    return

await ctx.send("⏳ Vérification du paiement en cours...")

try:
    verified = await verify_paypal_payment(order_id)
    if verified:
        code = get_available_code()
        if not code:
            await ctx.send("❌ Plus de codes disponibles pour le moment. Contacte un admin !")
            return

        mark_code_used(code, ctx.author.id)
        payments[user_id]["completed"] = True
        payments[user_id]["code"] = code
        payments[user_id]["validated_at"] = datetime.now().isoformat()
        save_json(PAYMENTS_FILE, payments)

        # Donner le rôle "Acheteur"
        guild = bot.get_guild(GUILD_ID)
        role = discord.utils.get(guild.roles, name="🎴 Acheteur")
        if role:
            member = guild.get_member(ctx.author.id)
            await member.add_roles(role)

        embed = discord.Embed(
            title="✅ Paiement validé !",
            description=(
                f"🎉 Félicitations {ctx.author.mention} !\n\n"
                f"**Ton code d'accès :**\n```{code}```\n\n"
                f"**Instructions :**\n"
                f"1️⃣ Va sur {TRADE_URL}\n"
                f"2️⃣ Entre ton code d'accès\n"
                f"3️⃣ Choisis ta carte\n"
                f"4️⃣ Entre ton code ami en jeu\n"
                f"5️⃣ Suis les instructions à l'écran\n\n"
                f"⚠️ Code usage unique - valide 7 jours\n"
                f"💬 Problème ? Contacte un admin"
            ),
            color=0x00FF00
        )
        await ctx.author.send(embed=embed)
        await ctx.send(f"✅ {ctx.author.mention} Paiement validé ! Je t'ai envoyé ton code en MP 🎉")
    else:
        await ctx.send("❌ Paiement non trouvé ou incomplet. Vérifie que tu as bien payé et réessaie.")
except Exception as e:
    await ctx.send("❌ Erreur lors de la vérification. Contacte un admin.")
    print(f"Erreur vérification: {e}")
```

@bot.command()
async def moncode(ctx):
“”“Affiche le code de l’utilisateur”””
payments = load_json(PAYMENTS_FILE)
user_id = str(ctx.author.id)

```
if user_id in payments and payments[user_id].get("completed"):
    code = payments[user_id].get("code")
    embed = discord.Embed(
        title="🔑 Ton code d'accès",
        description=f"```{code}```\n\n🌐 {TRADE_URL}",
        color=0xFFCC00
    )
    await ctx.author.send(embed=embed)
    await ctx.send(f"📩 {ctx.author.mention} Je t'ai envoyé ton code en MP !")
else:
    await ctx.send("❌ Aucun code trouvé. Utilise `!payer` pour commencer.")
```

@bot.command()
@commands.has_permissions(administrator=True)
async def ajoutercodes(ctx, *, codes_text: str):
“””[ADMIN] Ajoute des codes (un par ligne)”””
new_codes = [c.strip() for c in codes_text.strip().split(”\n”) if c.strip()]
add_codes(new_codes)
await ctx.send(f”✅ {len(new_codes)} code(s) ajouté(s) avec succès !”)

@bot.command()
@commands.has_permissions(administrator=True)
async def stats(ctx):
“””[ADMIN] Affiche les statistiques”””
codes = load_json(CODES_FILE)
payments = load_json(PAYMENTS_FILE)

```
total_codes = len(codes)
used_codes = sum(1 for c in codes.values() if c.get("used"))
available_codes = total_codes - used_codes
total_payments = sum(1 for p in payments.values() if p.get("completed"))

embed = discord.Embed(title="📊 Statistiques", color=0x7289DA)
embed.add_field(name="🔑 Codes total", value=total_codes, inline=True)
embed.add_field(name="✅ Codes utilisés", value=used_codes, inline=True)
embed.add_field(name="📦 Codes disponibles", value=available_codes, inline=True)
embed.add_field(name="💳 Paiements validés", value=total_payments, inline=True)
embed.add_field(name="💰 Revenus estimés", value=f"{total_payments * 3.5}€", inline=True)
await ctx.send(embed=embed)
```

# ============================================================

# SETUP SERVEUR

# ============================================================

async def setup_server():
guild = bot.get_guild(GUILD_ID)
if not guild:
print(“❌ Serveur non trouvé”)
return

```
print("🔧 Configuration du serveur...")

# Créer les rôles
roles_to_create = [
    ("👑 Admin", 0xFF0000, True),
    ("🛡️ Modérateur", 0xFF6600, True),
    ("🎴 Acheteur", 0xFFCC00, False),
    ("👤 Membre", 0x7289DA, False),
]

existing_roles = [r.name for r in guild.roles]
for role_name, color, hoist in roles_to_create:
    if role_name not in existing_roles:
        await guild.create_role(name=role_name, color=discord.Color(color), hoist=hoist)
        print(f"✅ Rôle créé : {role_name}")

# Créer les catégories et channels
channels_structure = {
    "📋 INFORMATIONS": ["📢・annonces", "📜・règlement", "❓・faq"],
    "🎴 ÉCHANGES": ["✅・vérification", "💳・paiement", "🎁・mes-échanges"],
    "💬 COMMUNAUTÉ": ["💬・général", "🤝・présentation"],
    "🔧 ADMINISTRATION": ["📊・logs-admin", "⚙️・commandes-admin"],
}

existing_channels = [c.name for c in guild.channels]

for category_name, channels in channels_structure.items():
    # Créer catégorie si elle n'existe pas
    category = discord.utils.get(guild.categories, name=category_name)
    if not category:
        category = await guild.create_category(category_name)
        print(f"✅ Catégorie créée : {category_name}")

    for channel_name in channels:
        if channel_name not in existing_channels:
            await guild.create_text_channel(channel_name, category=category)
            print(f"✅ Channel créé : {channel_name}")

# Poster le règlement
rules_channel = discord.utils.get(guild.text_channels, name="📜・règlement")
if rules_channel:
    history = [msg async for msg in rules_channel.history(limit=1)]
    if not history:
        embed = discord.Embed(
            title="📜 Règlement du serveur",
            description=(
                "Bienvenue sur le serveur d'échange **Pokémon TCG Pocket** !\n\n"
                "**📋 Règles générales :**\n"
                "1️⃣ Sois respectueux envers tous les membres\n"
                "2️⃣ Pas de spam ni de publicité non autorisée\n"
                "3️⃣ Utilise les bons channels pour chaque sujet\n\n"
                "**💳 Règles des échanges :**\n"
                "4️⃣ Le paiement de 3,50€ est obligatoire avant tout échange\n"
                "5️⃣ Les codes sont à usage unique et valides 7 jours\n"
                "6️⃣ Aucun remboursement après utilisation du code\n"
                "7️⃣ En cas de problème, contacte un admin\n\n"
                "**⚠️ Sanctions :**\n"
                "• Avertissement → Mute → Bannissement\n\n"
                "En rejoignant ce serveur, tu acceptes ces règles. ✅"
            ),
            color=0xFFCC00
        )
        await rules_channel.send(embed=embed)

# Poster la FAQ
faq_channel = discord.utils.get(guild.text_channels, name="❓・faq")
if faq_channel:
    history = [msg async for msg in faq_channel.history(limit=1)]
    if not history:
        embed = discord.Embed(
            title="❓ FAQ - Questions fréquentes",
            description=(
                "**Comment faire un échange ?**\n"
                f"Tape `!payer` dans ✅・vérification et suis les instructions.\n\n"
                "**Combien ça coûte ?**\n"
                "3,50€ par échange via PayPal.\n\n"
                "**Mon code ne fonctionne pas ?**\n"
                "Contacte un admin avec une capture d'écran.\n\n"
                "**Le code est valide combien de temps ?**\n"
                "7 jours à partir de l'achat.\n\n"
                f"**Site d'échange :** {TRADE_URL}"
            ),
            color=0x7289DA
        )
        await faq_channel.send(embed=embed)

print("✅ Serveur configuré avec succès !")
```

# ============================================================

# LANCEMENT

# ============================================================

bot.run(DISCORD_TOKEN)
