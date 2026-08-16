import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, Select, InputText
import sqlite3
import json
import requests
import asyncio
import aiohttp
from aiohttp import web
import qrcode
import io
import base64
from PIL import Image, ImageDraw, ImageFont
import os
from datetime import datetime

# ============================================================
# 🔧 CONFIGURAÇÕES - Use variáveis de ambiente no Render!
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "SEU_TOKEN_AQUI")
WEBHOOK_PORT = int(os.environ.get("PORT", 5000))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", f"http://SEU_IP:{WEBHOOK_PORT}/webhook")

# IDs dos administradores autorizados
ADMIN_IDS = [1495523007798706197, 1504181533353705675]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="/", intents=intents)

# ============================================================
# 💾 BANCO DE DADOS
# ============================================================
DB_PATH = os.environ.get("DB_PATH", "bot_vendas.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        guild_id INTEGER PRIMARY KEY,
        log_channel_id INTEGER,
        client_role_id INTEGER,
        admin_role_id INTEGER,
        voice_channel_id INTEGER,
        assas_api_key TEXT,
        wallet_channel_id INTEGER,
        wallet_balance REAL DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        title TEXT,
        description TEXT,
        price REAL,
        auto_delivery TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        product_id INTEGER,
        buyer_id INTEGER,
        buyer_name TEXT,
        quantity INTEGER,
        total_price REAL,
        payment_id TEXT,
        status TEXT DEFAULT 'pending',
        channel_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        code TEXT UNIQUE,
        discount_percent REAL,
        max_uses INTEGER DEFAULT 1,
        used_count INTEGER DEFAULT 0
    )''')
    
    conn.commit()
    conn.close()

def get_config(guild_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM config WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "guild_id": row[0],
            "log_channel_id": row[1],
            "client_role_id": row[2],
            "admin_role_id": row[3],
            "voice_channel_id": row[4],
            "assas_api_key": row[5],
            "wallet_channel_id": row[6],
            "wallet_balance": row[7]
        }
    return None

def save_config(guild_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT guild_id FROM config WHERE guild_id = ?", (guild_id,))
    exists = c.fetchone()
    
    if exists:
        fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [guild_id]
        c.execute(f"UPDATE config SET {fields} WHERE guild_id = ?", values)
    else:
        fields = ", ".join(kwargs.keys())
        placeholders = ", ".join(["?" for _ in kwargs])
        values = [guild_id] + list(kwargs.values())
        c.execute(f"INSERT INTO config (guild_id, {fields}) VALUES (?, {placeholders})", values)
    
    conn.commit()
    conn.close()

def add_product(guild_id, title, description, price, auto_delivery):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO products (guild_id, title, description, price, auto_delivery) VALUES (?, ?, ?, ?, ?)",
              (guild_id, title, description, price, auto_delivery))
    product_id = c.lastrowid
    conn.commit()
    conn.close()
    return product_id

def get_products(guild_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE guild_id = ?", (guild_id,))
    rows = c.fetchall()
    conn.close()
    products = []
    for row in rows:
        products.append({
            "id": row[0],
            "guild_id": row[1],
            "title": row[2],
            "description": row[3],
            "price": row[4],
            "auto_delivery": row[5],
            "created_at": row[6]
        })
    return products

def get_product(product_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE id = ?", (product_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "guild_id": row[1],
            "title": row[2],
            "description": row[3],
            "price": row[4],
            "auto_delivery": row[5],
            "created_at": row[6]
        }
    return None

def add_sale(guild_id, product_id, buyer_id, buyer_name, quantity, total_price, channel_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO sales (guild_id, product_id, buyer_id, buyer_name, quantity, total_price, channel_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (guild_id, product_id, buyer_id, buyer_name, quantity, total_price, channel_id))
    sale_id = c.lastrowid
    conn.commit()
    conn.close()
    return sale_id

def update_sale_payment(sale_id, payment_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE sales SET payment_id = ?, status = ? WHERE id = ?", (payment_id, status, sale_id))
    conn.commit()
    conn.close()

def get_sale_by_payment(payment_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM sales WHERE payment_id = ?", (payment_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "guild_id": row[1],
            "product_id": row[2],
            "buyer_id": row[3],
            "buyer_name": row[4],
            "quantity": row[5],
            "total_price": row[6],
            "payment_id": row[7],
            "status": row[8],
            "channel_id": row[9],
            "created_at": row[10]
        }
    return None

def update_wallet_balance(guild_id, amount):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE config SET wallet_balance = wallet_balance + ? WHERE guild_id = ?", (amount, guild_id))
    conn.commit()
    conn.close()

# ============================================================
# 💳 INTEGRAÇÃO ASSAS API
# ============================================================
class AssasAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.assas.com.br/v3"
        self.headers = {
            "access_token": api_key,
            "Content-Type": "application/json"
        }
    
    def create_pix_payment(self, value, description="Compra"):
        payload = {
            "customer": "bot_vendas_cliente",
            "billingType": "PIX",
            "value": round(value, 2),
            "dueDate": datetime.now().strftime("%Y-%m-%d"),
            "description": description
        }
        
        response = requests.post(f"{self.base_url}/payments", json=payload, headers=self.headers)
        if response.status_code in [200, 201]:
            data = response.json()
            payment_id = data.get("id")
            
            qr_response = requests.get(f"{self.base_url}/payments/{payment_id}/pixQrCode", headers=self.headers)
            if qr_response.status_code == 200:
                qr_data = qr_response.json()
                return {
                    "success": True,
                    "payment_id": payment_id,
                    "qr_code": qr_data.get("encodedImage"),
                    "pix_copy": qr_data.get("payload"),
                    "value": value
                }
            return {"success": True, "payment_id": payment_id, "qr_code": None, "pix_copy": None, "value": value}
        return {"success": False, "error": response.text}
    
    def get_payment_status(self, payment_id):
        response = requests.get(f"{self.base_url}/payments/{payment_id}", headers=self.headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("status")
        return None
    
    def transfer(self, pix_key, pix_type, name, value):
        payload = {
            "type": "PIX",
            "pixKey": pix_key,
            "pixKeyType": pix_type,
            "name": name,
            "value": round(value, 2)
        }
        response = requests.post(f"{self.base_url}/transfers", json=payload, headers=self.headers)
        if response.status_code in [200, 201]:
            return {"success": True, "data": response.json()}
        return {"success": False, "error": response.text}

# ============================================================
# 🖼️ GERAÇÃO DE IMAGENS
# ============================================================
def generate_sale_image(product_title, product_price, buyer_name, buyer_avatar_url=None):
    img = Image.new('RGB', (800, 400), color='#2b2d31')
    draw = ImageDraw.Draw(img)
    
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except:
        try:
            font_large = ImageFont.truetype("/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans-Bold.ttf", 36)
            font_medium = ImageFont.truetype("/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans.ttf", 24)
            font_small = ImageFont.truetype("/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans.ttf", 18)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
    
    if buyer_avatar_url:
        try:
            avatar_response = requests.get(buyer_avatar_url)
            avatar = Image.open(io.BytesIO(avatar_response.content)).resize((100, 100))
            img.paste(avatar, (50, 50))
        except:
            pass
    
    draw.text((180, 60), "NOVA VENDA!", fill='#5865f2', font=font_large)
    draw.text((50, 180), f"Produto:", fill='#ffffff', font=font_medium)
    draw.text((160, 180), product_title, fill='#7289da', font=font_medium)
    draw.text((50, 230), f"Valor:", fill='#ffffff', font=font_medium)
    draw.text((130, 230), f"R$ {product_price:.2f}", fill='#43b581', font=font_medium)
    draw.text((50, 280), f"Comprador:", fill='#ffffff', font=font_medium)
    draw.text((180, 280), buyer_name, fill='#b9bbbe', font=font_medium)
    draw.text((50, 330), f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}", fill='#747f8d', font=font_small)
    
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer

# ============================================================
# 🎨 VIEWS E MODAIS
# ============================================================

class CreateProductModal(Modal):
    def __init__(self):
        super().__init__(title="Criar Novo Produto")
        self.add_item(InputText(label="Título do Produto", placeholder="Ex: VIP Mensal", custom_id="title"))
        self.add_item(InputText(label="Descrição", placeholder="Descreva o produto...", style=discord.InputTextStyle.long, custom_id="description"))
        self.add_item(InputText(label="Valor (R$)", placeholder="Ex: 29.90", custom_id="price"))
        self.add_item(InputText(label="Entrega Automática", placeholder="Link, arquivo ZIP, texto, etc...", style=discord.InputTextStyle.long, custom_id="auto_delivery"))
    
    async def callback(self, interaction: discord.Interaction):
        title = self.children[0].value
        description = self.children[1].value
        price_str = self.children[2].value
        auto_delivery = self.children[3].value
        
        try:
            price = float(price_str.replace(",", "."))
        except:
            await interaction.response.send_message("Valor inválido! Use números como: 29.90", ephemeral=True)
            return
        
        product_id = add_product(interaction.guild_id, title, description, price, auto_delivery)
        
        embed = discord.Embed(title="Produto Criado!", color=discord.Color.green())
        embed.add_field(name="ID", value=f"#{product_id}", inline=False)
        embed.add_field(name="Título", value=title, inline=False)
        embed.add_field(name="Valor", value=f"R$ {price:.2f}", inline=False)
        embed.add_field(name="Descrição", value=description[:1024], inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class SendPanelModal(Modal):
    def __init__(self):
        super().__init__(title="Configurar Painel de Vendas")
        self.add_item(InputText(label="Título do Painel", placeholder="Ex: Loja Oficial", custom_id="title"))
        self.add_item(InputText(label="Descrição", placeholder="Descrição da loja...", style=discord.InputTextStyle.long, custom_id="description"))
        self.add_item(InputText(label="URL do Banner (opcional)", placeholder="https://...", required=False, custom_id="banner"))
    
    async def callback(self, interaction: discord.Interaction):
        title_value = self.children[0].value
        description_value = self.children[1].value
        banner_value = self.children[2].value
        
        view = ChannelSelectView(title_value, description_value, banner_value)
        await interaction.response.send_message("Escolha o canal para enviar o painel:", view=view, ephemeral=True)

class ChannelSelectDynamic(Select):
    def __init__(self, title, description, banner):
        self.panel_title = title
        self.panel_description = description
        self.panel_banner = banner
        super().__init__(placeholder="Selecione um canal de texto...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        channel = interaction.guild.get_channel(channel_id)
        
        if not channel:
            await interaction.response.send_message("Canal não encontrado!", ephemeral=True)
            return
        
        embed = discord.Embed(title=self.panel_title, description=self.panel_description, color=discord.Color.blue())
        if self.panel_banner:
            embed.set_image(url=self.panel_banner)
        
        view = ViewOptionsView()
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"Painel enviado para {channel.mention}!", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for channel in interaction.guild.text_channels:
            if len(options) < 25:
                options.append(discord.SelectOption(label=f"#{channel.name}", value=str(channel.id), description=f"ID: {channel.id}"))
        self.options = options

class ChannelSelectView(View):
    def __init__(self, title, description, banner):
        super().__init__(timeout=120)
        self.add_item(ChannelSelectDynamic(title, description, banner))

class CreatePanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Criar Produto", style=discord.ButtonStyle.green, custom_id="create_product_btn", emoji="➕")
    async def create_product(self, button, interaction):
        modal = CreateProductModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Enviar Painel", style=discord.ButtonStyle.blue, custom_id="send_panel_btn", emoji="📤")
    async def send_panel(self, button, interaction):
        modal = SendPanelModal()
        await interaction.response.send_modal(modal)

class ViewOptionsView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Ver Opções", style=discord.ButtonStyle.primary, custom_id="view_options_btn", emoji="🛒")
    async def view_options(self, button, interaction):
        products = get_products(interaction.guild_id)
        
        if not products:
            await interaction.response.send_message("Nenhum produto disponível no momento.", ephemeral=True)
            return
        
        view = ProductSelectView(products, interaction.user)
        await interaction.response.send_message("Escolha um produto:", view=view, ephemeral=True)

class ProductSelect(Select):
    def __init__(self, products, user):
        self.user = user
        options = []
        for p in products:
            options.append(discord.SelectOption(
                label=f"{p['title']} - R$ {p['price']:.2f}",
                value=str(p['id']),
                description=p['description'][:100] if p['description'] else "Sem descrição"
            ))
        
        super().__init__(placeholder="Selecione um produto...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        product_id = int(self.values[0])
        product = get_product(product_id)
        
        if not product:
            await interaction.response.send_message("Produto não encontrado!", ephemeral=True)
            return
        
        guild = interaction.guild
        config = get_config(guild.id)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        if config and config.get('admin_role_id'):
            admin_role = guild.get_role(config['admin_role_id'])
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        channel_name = f"compra-{interaction.user.name}-{product['title'][:10]}".lower().replace(" ", "-")
        channel = await guild.create_text_channel(channel_name, overwrites=overwrites, category=None)
        
        sale_id = add_sale(guild.id, product_id, interaction.user.id, interaction.user.name, 1, product['price'], channel.id)
        
        embed = discord.Embed(title=f"🛒 {product['title']}", color=discord.Color.blue())
        embed.add_field(name="Descrição", value=product['description'][:1024] if product['description'] else "Sem descrição", inline=False)
        embed.add_field(name="Valor Unitário", value=f"R$ {product['price']:.2f}", inline=True)
        embed.add_field(name="Quantidade", value="1", inline=True)
        embed.add_field(name="Total", value=f"R$ {product['price']:.2f}", inline=True)
        embed.set_footer(text=f"Venda #{sale_id}")
        
        view = PurchaseChannelView(product, interaction.user, sale_id, 1)
        await channel.send(f"{interaction.user.mention}", embed=embed, view=view)
        await interaction.response.send_message(f"Canal de compra criado: {channel.mention}", ephemeral=True)

class ProductSelectView(View):
    def __init__(self, products, user):
        super().__init__(timeout=120)
        self.add_item(ProductSelect(products, user))

class PurchaseChannelView(View):
    def __init__(self, product, buyer, sale_id, quantity=1):
        super().__init__(timeout=None)
        self.product = product
        self.buyer = buyer
        self.sale_id = sale_id
        self.quantity = quantity
        self.total = product['price'] * quantity
    
    @discord.ui.button(label="Comprar", style=discord.ButtonStyle.green, custom_id="buy_btn", emoji="💳")
    async def buy(self, button, interaction):
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("Apenas o comprador pode usar este botão!", ephemeral=True)
            return
        
        embed = discord.Embed(title="Finalizar Compra", color=discord.Color.green())
        embed.add_field(name="Produto", value=self.product['title'], inline=False)
        embed.add_field(name="Quantidade", value=str(self.quantity), inline=True)
        embed.add_field(name="Total", value=f"R$ {self.total:.2f}", inline=True)
        
        view = PaymentView(self.product, self.buyer, self.sale_id, self.quantity, self.total)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="Confirmar Pagamento", style=discord.ButtonStyle.blurple, custom_id="confirm_payment_btn", emoji="✅")
    async def confirm_payment(self, button, interaction):
        config = get_config(interaction.guild_id)
        if config and config.get('admin_role_id'):
            admin_role = interaction.guild.get_role(config['admin_role_id'])
            if admin_role and admin_role not in interaction.user.roles:
                await interaction.response.send_message("Apenas administradores podem confirmar pagamentos!", ephemeral=True)
                return
        else:
            if interaction.user.id not in ADMIN_IDS:
                await interaction.response.send_message("Apenas administradores podem confirmar pagamentos!", ephemeral=True)
                return
        
        await process_delivery(interaction.guild_id, self.sale_id, self.product, self.buyer, self.quantity, self.total)
        await interaction.response.send_message("Pagamento confirmado e produto entregue!", ephemeral=True)
        
        channel = interaction.channel
        await channel.edit(name=f"✔️-{channel.name}")
        await asyncio.sleep(120)
        await channel.delete()
    
    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.red, custom_id="cancel_btn", emoji="❌")
    async def cancel(self, button, interaction):
        if interaction.user.id != self.buyer.id and interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("Você não tem permissão para cancelar!", ephemeral=True)
            return
        
        await interaction.channel.delete()

class PaymentView(View):
    def __init__(self, product, buyer, sale_id, quantity, total):
        super().__init__(timeout=None)
        self.product = product
        self.buyer = buyer
        self.sale_id = sale_id
        self.quantity = quantity
        self.total = total
    
    @discord.ui.button(label="Alterar Quantidade", style=discord.ButtonStyle.secondary, custom_id="change_qty_btn", emoji="🔢")
    async def change_quantity(self, button, interaction):
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("Apenas o comprador pode alterar!", ephemeral=True)
            return
        
        modal = QuantityModal(self.product, self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Pagar", style=discord.ButtonStyle.green, custom_id="pay_btn", emoji="💰")
    async def pay(self, button, interaction):
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("Apenas o comprador pode pagar!", ephemeral=True)
            return
        
        config = get_config(interaction.guild_id)
        if not config or not config.get('assas_api_key'):
            await interaction.response.send_message("API de pagamento não configurada!", ephemeral=True)
            return
        
        assas = AssasAPI(config['assas_api_key'])
        result = assas.create_pix_payment(self.total, f"Compra: {self.product['title']} x{self.quantity}")
        
        if not result['success']:
            await interaction.response.send_message(f"Erro ao gerar pagamento: {result.get('error', 'Erro desconhecido')}", ephemeral=True)
            return
        
        update_sale_payment(self.sale_id, result['payment_id'], 'pending')
        
        embed = discord.Embed(title="Pagamento via Pix", color=discord.Color.green())
        embed.add_field(name="Produto", value=self.product['title'], inline=False)
        embed.add_field(name="Quantidade", value=str(self.quantity), inline=True)
        embed.add_field(name="Total a Pagar", value=f"R$ {self.total:.2f}", inline=True)
        embed.set_footer(text="Após o pagamento, o produto será entregue automaticamente na sua DM")
        
        files = []
        if result.get('qr_code'):
            qr_img_data = base64.b64decode(result['qr_code'])
            qr_file = discord.File(io.BytesIO(qr_img_data), filename="qrcode.png")
            embed.set_image(url="attachment://qrcode.png")
            files.append(qr_file)
        
        view = PixCopyView(result.get('pix_copy', ''))
        
        if files:
            await interaction.response.send_message(embed=embed, files=files, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="Aplicar Cupom", style=discord.ButtonStyle.primary, custom_id="apply_coupon_btn", emoji="🎟️")
    async def apply_coupon(self, button, interaction):
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("Apenas o comprador pode usar!", ephemeral=True)
            return
        
        modal = CouponModal(self)
        await interaction.response.send_modal(modal)

class QuantityModal(Modal):
    def __init__(self, product, payment_view):
        super().__init__(title="Alterar Quantidade")
        self.product = product
        self.payment_view = payment_view
        self.add_item(InputText(label="Quantidade (1-100)", placeholder="Digite um número de 1 a 100", custom_id="qty"))
    
    async def callback(self, interaction: discord.Interaction):
        try:
            qty = int(self.children[0].value)
            if qty < 1 or qty > 100:
                await interaction.response.send_message("Quantidade deve ser entre 1 e 100!", ephemeral=True)
                return
        except:
            await interaction.response.send_message("Valor inválido!", ephemeral=True)
            return
        
        self.payment_view.quantity = qty
        self.payment_view.total = self.product['price'] * qty
        
        embed = discord.Embed(title="Finalizar Compra", color=discord.Color.green())
        embed.add_field(name="Produto", value=self.product['title'], inline=False)
        embed.add_field(name="Quantidade", value=str(qty), inline=True)
        embed.add_field(name="Total", value=f"R$ {self.payment_view.total:.2f}", inline=True)
        
        await interaction.response.edit_message(embed=embed)

class CouponModal(Modal):
    def __init__(self, payment_view):
        super().__init__(title="Aplicar Cupom")
        self.payment_view = payment_view
        self.add_item(InputText(label="Código do Cupom", placeholder="Digite o cupom", custom_id="coupon"))
    
    async def callback(self, interaction: discord.Interaction):
        code = self.children[0].value.strip().upper()
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM coupons WHERE code = ? AND guild_id = ?", (code, interaction.guild_id))
        coupon = c.fetchone()
        conn.close()
        
        if not coupon:
            await interaction.response.send_message("Cupom inválido!", ephemeral=True)
            return
        
        if coupon[5] >= coupon[4]:
            await interaction.response.send_message("Este cupom já foi utilizado!", ephemeral=True)
            return
        
        discount = coupon[3]
        self.payment_view.total = self.payment_view.total * (1 - discount / 100)
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE coupons SET used_count = used_count + 1 WHERE id = ?", (coupon[0],))
        conn.commit()
        conn.close()
        
        embed = discord.Embed(title="Finalizar Compra", color=discord.Color.green())
        embed.add_field(name="Produto", value=self.payment_view.product['title'], inline=False)
        embed.add_field(name="Quantidade", value=str(self.payment_view.quantity), inline=True)
        embed.add_field(name="Cupom Aplicado", value=f"{discount}% OFF", inline=True)
        embed.add_field(name="Total", value=f"R$ {self.payment_view.total:.2f}", inline=True)
        
        await interaction.response.edit_message(embed=embed)

class PixCopyView(View):
    def __init__(self, pix_code):
        super().__init__(timeout=None)
        self.pix_code = pix_code
    
    @discord.ui.button(label="Copiar Pix", style=discord.ButtonStyle.primary, custom_id="copy_pix_btn", emoji="📋")
    async def copy_pix(self, button, interaction):
        if not self.pix_code:
            await interaction.response.send_message("Pix não disponível no momento.", ephemeral=True)
            return
        await interaction.response.send_message(f"```\n{self.pix_code}\n```", ephemeral=True)

# ============================================================
# 🎛️ PAINEL ADMINISTRATIVO
# ============================================================

class AdminPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Cria Painel", style=discord.ButtonStyle.green, custom_id="admin_create_panel", emoji="📦")
    async def create_panel(self, button, interaction):
        view = CreatePanelView()
        embed = discord.Embed(title="Gerenciar Produtos e Painel", color=discord.Color.green())
        embed.add_field(name="Criar Produto", value="Clique para adicionar novos produtos à loja", inline=False)
        embed.add_field(name="Enviar Painel", value="Clique para enviar o painel de vendas para um canal", inline=False)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="Conectar em Canal de Voz", style=discord.ButtonStyle.blurple, custom_id="admin_connect_voice", emoji="🔊")
    async def connect_voice(self, button, interaction):
        view = VoiceChannelSelectView()
        await interaction.response.send_message("Escolha um canal de voz para conectar:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Escolher Canal de Logs", style=discord.ButtonStyle.blurple, custom_id="admin_log_channel", emoji="📋")
    async def log_channel(self, button, interaction):
        view = LogChannelSelectView()
        await interaction.response.send_message("Escolha o canal de logs de vendas:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Escolher Cargo Cliente", style=discord.ButtonStyle.blurple, custom_id="admin_client_role", emoji="👤")
    async def client_role(self, button, interaction):
        view = ClientRoleSelectView()
        await interaction.response.send_message("Escolha o cargo que clientes receberão após a compra:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Configurar API de Pagamento", style=discord.ButtonStyle.blurple, custom_id="admin_api_config", emoji="🔑")
    async def api_config(self, button, interaction):
        modal = APIConfigModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Configurar Cargo Administrador", style=discord.ButtonStyle.red, custom_id="admin_role_config", emoji="🛡️")
    async def admin_role(self, button, interaction):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("Apenas os administradores autorizados podem usar esta função!", ephemeral=True)
            return
        
        view = AdminRoleSelectView()
        await interaction.response.send_message("Escolha o cargo de administrador:", view=view, ephemeral=True)
    
    @discord.ui.button(label="Carteira Administrativa", style=discord.ButtonStyle.gold, custom_id="admin_wallet", emoji="💼")
    async def wallet(self, button, interaction):
        config = get_config(interaction.guild_id)
        
        if config and config.get('admin_role_id'):
            admin_role = interaction.guild.get_role(config['admin_role_id'])
            if admin_role and admin_role not in interaction.user.roles and interaction.user.id not in ADMIN_IDS:
                await interaction.response.send_message("Apenas administradores podem acessar a carteira!", ephemeral=True)
                return
        elif interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("Apenas administradores podem acessar a carteira!", ephemeral=True)
            return
        
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("Apenas os administradores autorizados podem enviar o painel carteira!", ephemeral=True)
            return
        
        view = WalletChannelSelectView()
        await interaction.response.send_message("Escolha o canal para enviar o painel da carteira:", view=view, ephemeral=True)

class VoiceChannelSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione um canal de voz...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        channel = interaction.guild.get_channel(channel_id)
        
        if not channel or not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Canal inválido!", ephemeral=True)
            return
        
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
        
        await channel.connect()
        save_config(interaction.guild_id, voice_channel_id=channel_id)
        
        await interaction.response.send_message(f"Bot conectado permanentemente em: {channel.name}", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for channel in interaction.guild.voice_channels:
            if len(options) < 25:
                options.append(discord.SelectOption(label=channel.name, value=str(channel.id)))
        self.options = options

class VoiceChannelSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(VoiceChannelSelect())

class LogChannelSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione um canal de texto...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        save_config(interaction.guild_id, log_channel_id=channel_id)
        channel = interaction.guild.get_channel(channel_id)
        await interaction.response.send_message(f"Canal de logs configurado: {channel.mention if channel else channel_id}", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for channel in interaction.guild.text_channels:
            if len(options) < 25:
                options.append(discord.SelectOption(label=f"#{channel.name}", value=str(channel.id)))
        self.options = options

class LogChannelSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(LogChannelSelect())

class ClientRoleSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione um cargo...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        save_config(interaction.guild_id, client_role_id=role_id)
        role = interaction.guild.get_role(role_id)
        await interaction.response.send_message(f"Cargo cliente configurado: {role.mention if role else role_id}", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for role in interaction.guild.roles:
            if not role.is_bot_managed() and role != interaction.guild.default_role and len(options) < 25:
                options.append(discord.SelectOption(label=role.name, value=str(role.id)))
        self.options = options

class ClientRoleSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(ClientRoleSelect())

class APIConfigModal(Modal):
    def __init__(self):
        super().__init__(title="Configurar API Assas")
        self.add_item(InputText(label="API Key da Assas", placeholder="sua_api_key_aqui", custom_id="api_key"))
    
    async def callback(self, interaction: discord.Interaction):
        api_key = self.children[0].value
        save_config(interaction.guild_id, assas_api_key=api_key)
        await interaction.response.send_message("API Key configurada com sucesso!", ephemeral=True)

class AdminRoleSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione um cargo...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        save_config(interaction.guild_id, admin_role_id=role_id)
        role = interaction.guild.get_role(role_id)
        await interaction.response.send_message(f"Cargo administrador configurado: {role.mention if role else role_id}", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for role in interaction.guild.roles:
            if not role.is_bot_managed() and role != interaction.guild.default_role and len(options) < 25:
                options.append(discord.SelectOption(label=role.name, value=str(role.id)))
        self.options = options

class AdminRoleSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(AdminRoleSelect())

class WalletChannelSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione um canal de texto...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        save_config(interaction.guild_id, wallet_channel_id=channel_id)
        
        config = get_config(interaction.guild_id)
        channel = interaction.guild.get_channel(channel_id)
        
        embed = discord.Embed(title="💼 Carteira Administrativa", color=discord.Color.gold())
        embed.add_field(name="Saldo Disponível", value=f"R$ {config.get('wallet_balance', 0):.2f}", inline=False)
        embed.set_footer(text="Painel de controle financeiro")
        
        view = WalletView()
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message(f"Painel da carteira enviado para: {channel.mention}", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for channel in interaction.guild.text_channels:
            if len(options) < 25:
                options.append(discord.SelectOption(label=f"#{channel.name}", value=str(channel.id)))
        self.options = options

class WalletChannelSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(WalletChannelSelect())

class WalletView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Sacar", style=discord.ButtonStyle.green, custom_id="withdraw_btn", emoji="💸")
    async def withdraw(self, button, interaction):
        config = get_config(interaction.guild_id)
        
        if config and config.get('admin_role_id'):
            admin_role = interaction.guild.get_role(config['admin_role_id'])
            if admin_role and admin_role not in interaction.user.roles and interaction.user.id not in ADMIN_IDS:
                await interaction.response.send_message("Apenas administradores podem sacar!", ephemeral=True)
                return
        elif interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("Apenas administradores podem sacar!", ephemeral=True)
            return
        
        modal = WithdrawModal()
        await interaction.response.send_modal(modal)

class WithdrawModal(Modal):
    def __init__(self):
        super().__init__(title="Solicitar Saque")
        self.add_item(InputText(label="Chave Pix", placeholder="Sua chave Pix", custom_id="pix_key"))
        self.add_item(InputText(label="Nome Completo", placeholder="Nome do titular da conta", custom_id="name"))
        self.add_item(InputText(label="Valor do Saque (R$)", placeholder="Ex: 100.00", custom_id="value"))
    
    async def callback(self, interaction: discord.Interaction):
        pix_key = self.children[0].value
        name = self.children[1].value
        value_str = self.children[2].value
        
        try:
            value = float(value_str.replace(",", "."))
        except:
            await interaction.response.send_message("Valor inválido!", ephemeral=True)
            return
        
        config = get_config(interaction.guild_id)
        
        if value > config.get('wallet_balance', 0):
            await interaction.response.send_message("Saldo insuficiente!", ephemeral=True)
            return
        
        if not config or not config.get('assas_api_key'):
            await interaction.response.send_message("API de pagamento não configurada!", ephemeral=True)
            return
        
        pix_type = "EVP"
        if "@" in pix_key:
            pix_type = "EMAIL"
        elif len(pix_key) == 11 and pix_key.isdigit():
            pix_type = "PHONE"
        elif len(pix_key) == 14 and pix_key.isdigit():
            pix_type = "CPF"
        
        assas = AssasAPI(config['assas_api_key'])
        result = assas.transfer(pix_key, pix_type, name, value)
        
        if result['success']:
            update_wallet_balance(interaction.guild_id, -value)
            
            new_balance = config.get('wallet_balance', 0) - value
            embed = discord.Embed(title="💼 Carteira Administrativa", color=discord.Color.gold())
            embed.add_field(name="Saldo Disponível", value=f"R$ {new_balance:.2f}", inline=False)
            embed.add_field(name="Última Operação", value=f"Saque de R$ {value:.2f} para {name}", inline=False)
            
            await interaction.response.edit_message(embed=embed)
            await interaction.followup.send(f"Saque de R$ {value:.2f} processado com sucesso!", ephemeral=True)
        else:
            await interaction.response.send_message(f"Erro no saque: {result.get('error', 'Erro desconhecido')}", ephemeral=True)

# ============================================================
# 📦 PROCESSAMENTO DE ENTREGA
# ============================================================

async def process_delivery(guild_id, sale_id, product, buyer, quantity, total):
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    
    config = get_config(guild_id)
    
    if config and config.get('client_role_id'):
        role = guild.get_role(config['client_role_id'])
        if role:
            try:
                member = guild.get_member(buyer.id)
                if member:
                    await member.add_roles(role)
            except:
                pass
    
    update_wallet_balance(guild_id, total)
    update_sale_payment(sale_id, None, 'completed')
    
    try:
        embed = discord.Embed(title=f"✅ Produto Entregue - {product['title']}", color=discord.Color.green())
        embed.add_field(name="Descrição", value=product['description'][:1024] if product['description'] else "Sem descrição", inline=False)
        embed.add_field(name="Quantidade", value=str(quantity), inline=True)
        embed.add_field(name="Valor Pago", value=f"R$ {total:.2f}", inline=True)
        
        view = DeliveryView(product, buyer)
        await buyer.send(embed=embed, view=view)
        
        delivery_content = product.get('auto_delivery', '')
        if delivery_content:
            await buyer.send(f"**Conteúdo da Entrega:**\n{delivery_content}")
    except:
        pass
    
    if config and config.get('log_channel_id'):
        log_channel = guild.get_channel(config['log_channel_id'])
        if log_channel:
            try:
                avatar_url = str(buyer.avatar.url) if buyer.avatar else None
                img_buffer = generate_sale_image(product['title'], total, buyer.name, avatar_url)
                img_file = discord.File(img_buffer, filename="venda.png")
                
                embed = discord.Embed(color=discord.Color.green())
                embed.set_image(url="attachment://venda.png")
                
                view = LogBuyAgainView(product)
                await log_channel.send(
                    f"+ 1 vendas pessoal corre e compre antes que acabe @everyone @here",
                    file=img_file,
                    embed=embed,
                    view=view
                )
            except Exception as e:
                print(f"Erro ao enviar log: {e}")

class DeliveryView(View):
    def __init__(self, product, buyer):
        super().__init__(timeout=None)
        self.product = product
        self.buyer = buyer
    
    @discord.ui.button(label="Comprar Novamente", style=discord.ButtonStyle.green, custom_id="buy_again_btn", emoji="🔄")
    async def buy_again(self, button, interaction):
        for guild in bot.guilds:
            member = guild.get_member(self.buyer.id)
            if member:
                products = get_products(guild.id)
                product_match = None
                for p in products:
                    if p['id'] == self.product['id']:
                        product_match = p
                        break
                
                if product_match:
                    config = get_config(guild.id)
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
                    }
                    
                    if config and config.get('admin_role_id'):
                        admin_role = guild.get_role(config['admin_role_id'])
                        if admin_role:
                            overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    
                    channel_name = f"compra-{member.name}-{product_match['title'][:10]}".lower().replace(" ", "-")
                    channel = await guild.create_text_channel(channel_name, overwrites=overwrites, category=None)
                    
                    sale_id = add_sale(guild.id, product_match['id'], member.id, member.name, 1, product_match['price'], channel.id)
                    
                    embed = discord.Embed(title=f"🛒 {product_match['title']}", color=discord.Color.blue())
                    embed.add_field(name="Descrição", value=product_match['description'][:1024] if product_match['description'] else "Sem descrição", inline=False)
                    embed.add_field(name="Valor Unitário", value=f"R$ {product_match['price']:.2f}", inline=True)
                    embed.add_field(name="Quantidade", value="1", inline=True)
                    embed.add_field(name="Total", value=f"R$ {product_match['price']:.2f}", inline=True)
                    embed.set_footer(text=f"Venda #{sale_id}")
                    
                    view = PurchaseChannelView(product_match, member, sale_id, 1)
                    await channel.send(f"{member.mention}", embed=embed, view=view)
                    await interaction.response.send_message(f"Novo canal de compra criado no servidor **{guild.name}**: {channel.mention}", ephemeral=True)
                    return
        
        await interaction.response.send_message("Não foi possível criar o canal de compra.", ephemeral=True)
    
    @discord.ui.button(label="Copiar Produto", style=discord.ButtonStyle.primary, custom_id="copy_product_btn", emoji="📋")
    async def copy_product(self, button, interaction):
        delivery_content = self.product.get('auto_delivery', '')
        if delivery_content:
            await interaction.response.send_message(f"```\n{delivery_content}\n```", ephemeral=True)
        else:
            await interaction.response.send_message("Nenhum conteúdo para copiar.", ephemeral=True)

class LogBuyAgainView(View):
    def __init__(self, product):
        super().__init__(timeout=None)
        self.product = product
    
    @discord.ui.button(label="Comprar", style=discord.ButtonStyle.green, custom_id="log_buy_btn", emoji="🛒")
    async def buy(self, button, interaction):
        guild = interaction.guild
        config = get_config(guild.id)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        if config and config.get('admin_role_id'):
            admin_role = guild.get_role(config['admin_role_id'])
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        channel_name = f"compra-{interaction.user.name}-{self.product['title'][:10]}".lower().replace(" ", "-")
        channel = await guild.create_text_channel(channel_name, overwrites=overwrites, category=None)
        
        sale_id = add_sale(guild.id, self.product['id'], interaction.user.id, interaction.user.name, 1, self.product['price'], channel.id)
        
        embed = discord.Embed(title=f"🛒 {self.product['title']}", color=discord.Color.blue())
        embed.add_field(name="Descrição", value=self.product['description'][:1024] if self.product['description'] else "Sem descrição", inline=False)
        embed.add_field(name="Valor Unitário", value=f"R$ {self.product['price']:.2f}", inline=True)
        embed.add_field(name="Quantidade", value="1", inline=True)
        embed.add_field(name="Total", value=f"R$ {self.product['price']:.2f}", inline=True)
        embed.set_footer(text=f"Venda #{sale_id}")
        
        view = PurchaseChannelView(self.product, interaction.user, sale_id, 1)
        await channel.send(f"{interaction.user.mention}", embed=embed, view=view)
        await interaction.response.send_message(f"Canal de compra criado: {channel.mention}", ephemeral=True)

# ============================================================
# 🔗 WEBHOOK
# ============================================================

async def webhook_handler(request):
    try:
        data = await request.json()
        payment_id = data.get("payment", {}).get("id")
        status = data.get("payment", {}).get("status")
        
        if payment_id and status == "RECEIVED":
            sale = get_sale_by_payment(payment_id)
            if sale and sale['status'] != 'completed':
                product = get_product(sale['product_id'])
                guild = bot.get_guild(sale['guild_id'])
                buyer = await bot.fetch_user(sale['buyer_id'])
                
                if product and buyer:
                    await process_delivery(
                        sale['guild_id'],
                        sale['id'],
                        product,
                        buyer,
                        sale['quantity'],
                        sale['total_price']
                    )
                    
                    if sale.get('channel_id'):
                        channel = guild.get_channel(sale['channel_id']) if guild else None
                        if channel:
                            try:
                                await channel.edit(name=f"✔️-{channel.name}")
                                await asyncio.sleep(120)
                                await channel.delete()
                            except:
                                pass
        
        return web.Response(text="OK", status=200)
    except Exception as e:
        print(f"Erro no webhook: {e}")
        return web.Response(text="Error", status=500)

async def start_webhook():
    app = web.Application()
    app.router.add_post('/webhook', webhook_handler)
    app.router.add_get('/', lambda request: web.Response(text="Bot Vendas Online!", status=200))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', WEBHOOK_PORT)
    await site.start()
    print(f"✅ Webhook rodando na porta {WEBHOOK_PORT}")

# ============================================================
# 🔊 VOZ PERMANENTE
# ============================================================

@tasks.loop(minutes=5)
async def maintain_voice_connection():
    for guild in bot.guilds:
        config = get_config(guild.id)
        if config and config.get('voice_channel_id'):
            if not guild.voice_client or not guild.voice_client.is_connected():
                channel = guild.get_channel(config['voice_channel_id'])
                if channel and isinstance(channel, discord.VoiceChannel):
                    try:
                        await channel.connect()
                        print(f"🔊 Reconectado ao canal de voz em {guild.name}")
                    except Exception as e:
                        print(f"Erro ao reconectar voz: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member == bot.user:
        return
    
    for guild in bot.guilds:
        config = get_config(guild.id)
        if config and config.get('voice_channel_id'):
            if not guild.voice_client or not guild.voice_client.is_connected():
                channel = guild.get_channel(config['voice_channel_id'])
                if channel and isinstance(channel, discord.VoiceChannel):
                    try:
                        await channel.connect()
                    except:
                        pass

# ============================================================
# ⚡ COMANDOS
# ============================================================

@bot.slash_command(name="painel", description="Painel de vendas administrativo")
async def painel(ctx, opcao: discord.Option(str, "Escolha a opção", choices=["vendas"])):
    if opcao == "vendas":
        embed = discord.Embed(title="🎛️ Painel Administrativo - Vendas", color=discord.Color.blue())
        embed.description = "Gerencie todas as configurações do seu bot de vendas abaixo:"
        embed.add_field(name="📦 Produtos", value="Crie produtos e envie painéis de venda", inline=False)
        embed.add_field(name="🔊 Voz", value="Conecte o bot permanentemente em canais de voz", inline=False)
        embed.add_field(name="⚙️ Configurações", value="Configure cargos, canais de log e API de pagamento", inline=False)
        embed.add_field(name="💼 Carteira", value="Gerencie seu saldo e saques", inline=False)
        
        view = AdminPanelView()
        await ctx.respond(embed=embed, view=view, ephemeral=True)

# ============================================================
# 🎉 EVENTOS
# ============================================================

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"🤖 Bot conectado como: {bot.user}")
    print(f"🆔 ID: {bot.user.id}")
    print("=" * 60)
    
    await start_webhook()
    maintain_voice_connection.start()
    
    for guild in bot.guilds:
        config = get_config(guild.id)
        if config and config.get('voice_channel_id'):
            channel = guild.get_channel(config['voice_channel_id'])
            if channel and isinstance(channel, discord.VoiceChannel):
                try:
                    await channel.connect()
                    print(f"🔊 Conectado ao canal de voz: {channel.name} em {guild.name}")
                except Exception as e:
                    print(f"⚠️  Não foi possível conectar ao canal de voz: {e}")
    
    print("\n✅ Bot pronto! Use /painel vendas no Discord")
    print("=" * 60)

# ============================================================
# 🚀 INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":
    init_db()
    print("💾 Banco de dados inicializado...")
    bot.run(BOT_TOKEN)
