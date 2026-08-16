import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, Select, InputText
import sqlite3
import os
import asyncio
import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import requests
import json
from datetime import datetime

# ============================================================
# 🔧 CONFIGURAÇÕES
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "SEU_TOKEN_AQUI")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", 5000))
DB_PATH = os.environ.get("DB_PATH", "bot_vendas.db")

# IDs autorizados a configurar cargo admin
AUTHORIZED_IDS = [1495523007798706197, 1504181533353705675]

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)

# ============================================================
# 💾 BANCO DE DADOS
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        guild_id INTEGER PRIMARY KEY,
        log_channel_id INTEGER,
        customer_role_id INTEGER,
        admin_role_id INTEGER,
        voice_channel_id INTEGER,
        assas_api_key TEXT,
        wallet_balance REAL DEFAULT 0.0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        title TEXT,
        description TEXT,
        price REAL,
        delivery_type TEXT,
        delivery_content TEXT,
        stock INTEGER DEFAULT 999,
        created_at TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        buyer_id INTEGER,
        buyer_name TEXT,
        product_id INTEGER,
        product_name TEXT,
        quantity INTEGER DEFAULT 1,
        total_price REAL,
        status TEXT DEFAULT 'pending',
        payment_id TEXT,
        pix_qr_code TEXT,
        pix_copy_paste TEXT,
        ticket_channel_id INTEGER,
        created_at TIMESTAMP,
        paid_at TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS panels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        channel_id INTEGER,
        message_id INTEGER,
        title TEXT,
        description TEXT,
        banner TEXT
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
            "customer_role_id": row[2],
            "admin_role_id": row[3],
            "voice_channel_id": row[4],
            "assas_api_key": row[5],
            "wallet_balance": row[6]
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

def add_product(guild_id, title, description, price, delivery_type, delivery_content, stock=999):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO products (guild_id, title, description, price, delivery_type, delivery_content, stock, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (guild_id, title, description, price, delivery_type, delivery_content, stock, datetime.now().isoformat()))
    pid = c.lastrowid
    conn.commit()
    conn.close()
    return pid

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
            "delivery_type": row[5],
            "delivery_content": row[6],
            "stock": row[7],
            "created_at": row[8]
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
            "delivery_type": row[5],
            "delivery_content": row[6],
            "stock": row[7],
            "created_at": row[8]
        }
    return None

def update_product(product_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [product_id]
    c.execute(f"UPDATE products SET {fields} WHERE id = ?", values)
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

def decrease_stock(product_id, quantity=1):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (quantity, product_id))
    conn.commit()
    conn.close()

def add_sale(**kwargs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    fields = ", ".join(kwargs.keys())
    placeholders = ", ".join(["?" for _ in kwargs])
    values = list(kwargs.values())
    c.execute(f"INSERT INTO sales ({fields}) VALUES ({placeholders})", values)
    sid = c.lastrowid
    conn.commit()
    conn.close()
    return sid

def update_sale(sale_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [sale_id]
    c.execute(f"UPDATE sales SET {fields} WHERE id = ?", values)
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
            "buyer_id": row[2],
            "buyer_name": row[3],
            "product_id": row[4],
            "product_name": row[5],
            "quantity": row[6],
            "total_price": row[7],
            "status": row[8],
            "payment_id": row[9],
            "pix_qr_code": row[10],
            "pix_copy_paste": row[11],
            "ticket_channel_id": row[12],
            "created_at": row[13],
            "paid_at": row[14]
        }
    return None

# ============================================================
# 🖼️ GERAÇÃO DE IMAGEM DE VENDA - ESTILO PRETO "DEJA FORN"
# ============================================================
def gerar_imagem_venda(buyer_name, buyer_avatar_url, product_name, price, quantity=1):
    # Criar imagem com fundo PRETO NEGRO
    img = Image.new('RGB', (800, 400), color='#0a0a0a')
    draw = ImageDraw.Draw(img)
    
    # Borda preta com detalhe dourado
    draw.rectangle([(0, 0), (799, 399)], outline='#1a1a1a', width=3)
    draw.rectangle([(5, 5), (794, 394)], outline='#c9a227', width=1)
    
    # Linha decorativa superior
    draw.line([(50, 70), (750, 70)], fill='#c9a227', width=2)
    
    # TÍTULO PRINCIPAL: DEJA FORN
    try:
        font_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except:
        font_titulo = ImageFont.load_default()
    
    # Calcular posição centralizada para "DEJA FORN"
    titulo = "DEJA FORN"
    bbox = draw.textbbox((0, 0), titulo, font=font_titulo)
    w = bbox[2] - bbox[0]
    draw.text(((800 - w) // 2, 15), titulo, font=font_titulo, fill='#c9a227')
    
    # Linha decorativa inferior ao título
    draw.line([(50, 75), (750, 75)], fill='#c9a227', width=2)
    
    # Subtítulo: NOVA VENDA
    try:
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    except:
        font_sub = ImageFont.load_default()
    
    subtitulo = "✦ NOVA VENDA REALIZADA ✦"
    bbox = draw.textbbox((0, 0), subtitulo, font=font_sub)
    w = bbox[2] - bbox[0]
    draw.text(((800 - w) // 2, 90), subtitulo, font=font_sub, fill='#888888')
    
    # Avatar do comprador
    try:
        response = requests.get(buyer_avatar_url, timeout=10)
        avatar = Image.open(BytesIO(response.content)).resize((100, 100))
        # Máscara circular
        mask = Image.new('L', (100, 100), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, 100, 100), fill=255)
        img.paste(avatar, (60, 130), mask)
        # Borda dourada no avatar
        draw.ellipse([(58, 128), (162, 232)], outline='#c9a227', width=2)
    except:
        pass
    
    # Informações da venda
    try:
        font_info = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except:
        font_info = ImageFont.load_default()
        font_bold = ImageFont.load_default()
    
    y_offset = 140
    x_info = 190
    
    # Comprador
    draw.text((x_info, y_offset), "👤 COMPRADOR:", font=font_info, fill='#888888')
    draw.text((x_info + 160, y_offset), buyer_name, font=font_bold, fill='#ffffff')
    y_offset += 45
    
    # Produto
    draw.text((x_info, y_offset), "📦 PRODUTO:", font=font_info, fill='#888888')
    draw.text((x_info + 140, y_offset), product_name, font=font_bold, fill='#ffffff')
    y_offset += 45
    
    # Quantidade
    if quantity > 1:
        draw.text((x_info, y_offset), "🔢 QUANTIDADE:", font=font_info, fill='#888888')
        draw.text((x_info + 180, y_offset), str(quantity), font=font_bold, fill='#ffffff')
        y_offset += 45
    
    # Valor
    draw.text((x_info, y_offset), "💎 VALOR:", font=font_info, fill='#888888')
    draw.text((x_info + 120, y_offset), f"R$ {price:.2f}", font=font_bold, fill='#c9a227')
    
    # Linha inferior
    draw.line([(50, 330), (750, 330)], fill='#333333', width=1)
    
    # Rodapé
    try:
        font_footer = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        font_footer = ImageFont.load_default()
    
    data_hora = datetime.now().strftime("%d/%m/%Y %H:%M")
    draw.text((60, 355), f"📅 {data_hora}", font=font_footer, fill='#555555')
    
    marca = "DEJA FORN ©"
    bbox = draw.textbbox((0, 0), marca, font=font_footer)
    w = bbox[2] - bbox[0]
    draw.text((800 - w - 60, 355), marca, font=font_footer, fill='#c9a227')
    
    # Salvar em buffer
    buffer = BytesIO()
    img.save(buffer, format='PNG', quality=95)
    buffer.seek(0)
    
    return discord.File(buffer, filename=f"venda_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")

# ============================================================
# 🎨 VIEWS E MODAIS
# ============================================================

# --- Painel Admin Principal ---
class AdminPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    async def is_authorized(self, interaction):
        config = get_config(interaction.guild_id)
        if interaction.user.id in AUTHORIZED_IDS:
            return True
        if config and config.get('admin_role_id'):
            role = interaction.guild.get_role(config['admin_role_id'])
            if role and role in interaction.user.roles:
                return True
        return False
    
    @discord.ui.button(label="📦 Cria Painel", style=discord.ButtonStyle.green, custom_id="admin_create_panel")
    async def create_panel(self, button, interaction):
        if not await self.is_authorized(interaction):
            await interaction.response.send_message("❌ Você não tem permissão!", ephemeral=True)
            return
        modal = CreateProductModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔊 Conectar Voz", style=discord.ButtonStyle.blurple, custom_id="admin_voice")
    async def connect_voice(self, button, interaction):
        if not await self.is_authorized(interaction):
            await interaction.response.send_message("❌ Você não tem permissão!", ephemeral=True)
            return
        view = VoiceChannelSelectView()
        await interaction.response.send_message("Escolha o canal de voz:", view=view, ephemeral=True)
    
    @discord.ui.button(label="📋 Canal de Logs", style=discord.ButtonStyle.secondary, custom_id="admin_logs")
    async def log_channel(self, button, interaction):
        if not await self.is_authorized(interaction):
            await interaction.response.send_message("❌ Você não tem permissão!", ephemeral=True)
            return
        view = LogChannelSelectView()
        await interaction.response.send_message("Escolha o canal de logs:", view=view, ephemeral=True)
    
    @discord.ui.button(label="👤 Cargo Cliente", style=discord.ButtonStyle.secondary, custom_id="admin_customer")
    async def customer_role(self, button, interaction):
        if not await self.is_authorized(interaction):
            await interaction.response.send_message("❌ Você não tem permissão!", ephemeral=True)
            return
        view = CustomerRoleSelectView()
        await interaction.response.send_message("Escolha o cargo de cliente:", view=view, ephemeral=True)
    
    @discord.ui.button(label="🔑 API Pagamento", style=discord.ButtonStyle.secondary, custom_id="admin_api")
    async def api_key(self, button, interaction):
        if not await self.is_authorized(interaction):
            await interaction.response.send_message("❌ Você não tem permissão!", ephemeral=True)
            return
        modal = ApiKeyModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🛡️ Cargo Admin", style=discord.ButtonStyle.red, custom_id="admin_role")
    async def admin_role(self, button, interaction):
        if interaction.user.id not in AUTHORIZED_IDS:
            await interaction.response.send_message("❌ Apenas IDs autorizados podem configurar isso!", ephemeral=True)
            return
        view = AdminRoleSelectView()
        await interaction.response.send_message("Escolha o cargo administrador:", view=view, ephemeral=True)
    
    @discord.ui.button(label="💼 Carteira", style=discord.ButtonStyle.gold, custom_id="admin_wallet", row=2)
    async def wallet(self, button, interaction):
        if not await self.is_authorized(interaction):
            await interaction.response.send_message("❌ Você não tem permissão!", ephemeral=True)
            return
        config = get_config(interaction.guild_id)
        balance = config.get('wallet_balance', 0.0) if config else 0.0
        
        embed = discord.Embed(title="💼 Carteira Administrativa", color=0xc9a227)
        embed.description = f"# R$ {balance:.2f}"
        embed.set_footer(text="DEJA FORN")
        
        view = WalletView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# --- Modal de Criar Produto com ESTOQUE ---
class CreateProductModal(Modal):
    def __init__(self):
        super().__init__(title="Criar Produto")
        self.add_item(InputText(label="Título do Produto", placeholder="Ex: VIP Discord", custom_id="title"))
        self.add_item(InputText(label="Descrição", placeholder="Descrição do produto...", style=discord.InputTextStyle.long, custom_id="description"))
        self.add_item(InputText(label="Valor (R$)", placeholder="Ex: 29.90", custom_id="price"))
        self.add_item(InputText(label="Quantidade em Estoque", placeholder="Ex: 50 (deixe vazio para ilimitado)", required=False, custom_id="stock"))
        self.add_item(InputText(label="Entrega (link/texto)", placeholder="Conteúdo da entrega automática", style=discord.InputTextStyle.long, custom_id="delivery"))
    
    async def callback(self, interaction: discord.Interaction):
        try:
            price = float(self.children[2].value.replace(',', '.'))
        except:
            await interaction.response.send_message("❌ Valor inválido!", ephemeral=True)
            return
        
        stock_text = self.children[3].value.strip() if self.children[3].value else ""
        try:
            stock = int(stock_text) if stock_text else 999
        except:
            stock = 999
        
        pid = add_product(
            guild_id=interaction.guild_id,
            title=self.children[0].value,
            description=self.children[1].value,
            price=price,
            delivery_type="text",
            delivery_content=self.children[4].value,
            stock=stock
        )
        
        stock_text = f"Estoque: {stock}" if stock < 999 else "Estoque: Ilimitado"
        await interaction.response.send_message(
            f"✅ Produto criado!\n\n"
            f"**{self.children[0].value}**\n"
            f"R$ {price:.2f}\n"
            f"{stock_text}\n\n"
            f"Agora envie o painel para um canal usando o botão abaixo.",
            view=SendPanelView(pid),
            ephemeral=True
        )

# --- View para enviar painel ---
class SendPanelView(View):
    def __init__(self, product_id):
        super().__init__(timeout=120)
        self.product_id = product_id
    
    @discord.ui.button(label="📤 Enviar Painel para Canal", style=discord.ButtonStyle.green)
    async def send_panel(self, button, interaction):
        view = PanelChannelSelectView(self.product_id)
        await interaction.response.send_message("Escolha o canal para enviar o painel:", view=view, ephemeral=True)

# --- Select de canal para painel ---
class PanelChannelSelect(Select):
    def __init__(self, product_id):
        self.product_id = product_id
        super().__init__(placeholder="Selecione um canal...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        channel = interaction.guild.get_channel(channel_id)
        
        if not channel:
            await interaction.response.send_message("Canal não encontrado!", ephemeral=True)
            return
        
        product = get_product(self.product_id)
        if not product:
            await interaction.response.send_message("Produto não encontrado!", ephemeral=True)
            return
        
        embed = discord.Embed(title="🛒 LOJA - DEJA FORN", color=0x0a0a0a)
        embed.description = f"**{product['title']}**\n\n{product['description']}\n\n💎 **R$ {product['price']:.2f}**"
        
        stock = product.get('stock', 999)
        if stock < 999:
            embed.add_field(name="📦 Estoque", value=f"{stock} unidades", inline=True)
        
        embed.set_footer(text="DEJA FORN • Clique abaixo para ver opções")
        
        view = PublicPanelView()
        msg = await channel.send(embed=embed, view=view)
        
        await interaction.response.send_message(f"✅ Painel enviado para {channel.mention}!", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for channel in interaction.guild.text_channels:
            if len(options) < 25:
                options.append(discord.SelectOption(label=f"#{channel.name}", value=str(channel.id)))
        self.options = options

class PanelChannelSelectView(View):
    def __init__(self, product_id):
        super().__init__(timeout=120)
        self.add_item(PanelChannelSelect(product_id))

# --- Painel Público ---
class PublicPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🛒 Ver Opções", style=discord.ButtonStyle.blurple, custom_id="public_buy")
    async def buy(self, button, interaction):
        products = get_products(interaction.guild_id)
        if not products:
            await interaction.response.send_message("⚠️ Nenhum produto disponível no momento.", ephemeral=True)
            return
        
        try:
            await interaction.user.send("Selecione um produto abaixo:")
            view = ProductSelectView(interaction.guild, interaction.user)
            await interaction.user.send(view=view)
            await interaction.response.send_message("📨 Verifique sua mensagem privada!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Não consigo enviar DM. Habilite mensagens de membros do servidor!", ephemeral=True)

# --- Select de Produtos na DM ---
class ProductSelect(Select):
    def __init__(self, guild, user):
        self.guild = guild
        self.user = user
        options = []
        products = get_products(guild.id)
        
        for p in products:
            stock = p.get('stock', 999)
            if stock <= 0:
                label = f"❌ ESGOTADO - {p['title']}"
                description = "Produto esgotado"
            else:
                label = f"{p['title']} - R$ {p['price']:.2f}"
                stock_text = f" | Estoque: {stock}" if stock < 999 else ""
                description = (p.get('description', '')[:80] or "Sem descrição") + stock_text
            
            options.append(discord.SelectOption(
                label=label[:100],
                value=str(p['id']),
                description=description[:100]
            ))
        
        if not options:
            options.append(discord.SelectOption(label="Nenhum produto disponível", value="none"))
        
        super().__init__(placeholder="Selecione um produto...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("Nenhum produto disponível.", ephemeral=True)
            return
        
        product_id = int(self.values[0])
        product = get_product(product_id)
        
        if not product:
            await interaction.response.send_message("Produto não encontrado!", ephemeral=True)
            return
        
        if product.get('stock', 999) <= 0:
            await interaction.response.send_message("❌ Este produto está esgotado!", ephemeral=True)
            return
        
        # Criar canal de atendimento
        config = get_config(self.guild.id)
        
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            self.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            self.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        if config and config.get('admin_role_id'):
            admin_role = self.guild.get_role(config['admin_role_id'])
            if admin_role:
                overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        ticket_channel = await self.guild.create_text_channel(
            name=f"compra-{self.user.display_name[:15]}",
            overwrites=overwrites
        )
        
        embed = discord.Embed(title=f"🛒 Compra: {product['title']}", color=0x0a0a0a)
        embed.add_field(name="💎 Valor Unitário", value=f"R$ {product['price']:.2f}", inline=True)
        embed.add_field(name="🔢 Quantidade", value="1", inline=True)
        embed.add_field(name="💰 Total", value=f"R$ {product['price']:.2f}", inline=True)
        
        if product.get('stock', 999) < 999:
            embed.add_field(name="📦 Estoque disponível", value=str(product['stock']), inline=True)
        
        embed.set_footer(text="DEJA FORN")
        
        view = TicketView(product, self.user, ticket_channel, 1)
        await ticket_channel.send(content=self.user.mention, embed=embed, view=view)
        
        await interaction.response.send_message(f"✅ Canal de compra criado: {ticket_channel.mention}", ephemeral=True)

class ProductSelectView(View):
    def __init__(self, guild, user):
        super().__init__(timeout=300)
        self.add_item(ProductSelect(guild, user))

# --- View dentro do Ticket de Compra ---
class TicketView(View):
    def __init__(self, product, buyer, channel, quantity):
        super().__init__(timeout=None)
        self.product = product
        self.buyer = buyer
        self.channel = channel
        self.quantity = quantity
        self.total = product['price'] * quantity
    
    def atualizar_total(self):
        self.total = self.product['price'] * self.quantity
    
    @discord.ui.button(label="💳 Comprar", style=discord.ButtonStyle.green, custom_id="ticket_buy")
    async def buy(self, button, interaction):
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("❌ Apenas o comprador pode fazer isso!", ephemeral=True)
            return
        
        config = get_config(interaction.guild_id)
        api_key = config.get('assas_api_key') if config else None
        
        if not api_key:
            await interaction.response.send_message("⚠️ API de pagamento não configurada. Contate um administrador.", ephemeral=True)
            return
        
        if self.product.get('stock', 999) < self.quantity:
            await interaction.response.send_message(f"❌ Estoque insuficiente! Disponível: {self.product.get('stock', 0)}", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Gerar pagamento Pix via API Assas
        try:
            headers = {
                "access_token": api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "customer": self.buyer.name,
                "billingType": "PIX",
                "value": round(self.total, 2),
                "dueDate": datetime.now().strftime("%Y-%m-%d"),
                "description": f"Compra: {self.product['title']} (x{self.quantity})"
            }
            
            response = requests.post("https://www.asaas.com/api/v3/payments", headers=headers, json=payload)
            data = response.json()
            
            if response.status_code in [200, 201]:
                pix_info = data.get('pixTransaction', {})
                qr_code = pix_info.get('encodedImage', '')
                copy_paste = pix_info.get('payload', '')
                
                # Registrar venda
                sale_id = add_sale(
                    guild_id=interaction.guild_id,
                    buyer_id=self.buyer.id,
                    buyer_name=self.buyer.name,
                    product_id=self.product['id'],
                    product_name=self.product['title'],
                    quantity=self.quantity,
                    total_price=self.total,
                    status='pending',
                    payment_id=data.get('id', ''),
                    pix_qr_code=qr_code,
                    pix_copy_paste=copy_paste,
                    ticket_channel_id=self.channel.id,
                    created_at=datetime.now().isoformat()
                )
                
                # Mostrar QR Code
                embed = discord.Embed(title="💳 Pagamento Pix", color=0xc9a227)
                embed.description = f"**Total: R$ {self.total:.2f}**\n\nEscaneie o QR Code ou use o Copia e Cola"
                
                if qr_code:
                    qr_img = qrcode.make(copy_paste)
                    buffer = BytesIO()
                    qr_img.save(buffer, format='PNG')
                    buffer.seek(0)
                    file = discord.File(buffer, filename="qrcode.png")
                    embed.set_image(url="attachment://qrcode.png")
                    await self.channel.send(embed=embed, file=file)
                else:
                    await self.channel.send(embed=embed)
                
                if copy_paste:
                    copy_view = CopyPixView(copy_paste)
                    await self.channel.send(f"**Copia e Cola:**\n```\n{copy_paste[:1000]}\n```", view=copy_view)
                
                await interaction.followup.send("✅ Pagamento gerado! Efetue o Pix para receber o produto.", ephemeral=True)
                
            else:
                await interaction.followup.send(f"❌ Erro ao gerar pagamento: {data.get('errors', str(data))}", ephemeral=True)
        
        except Exception as e:
            await interaction.followup.send(f"❌ Erro: {str(e)[:200]}", ephemeral=True)
    
    @discord.ui.button(label="🔢 Alterar Quantidade", style=discord.ButtonStyle.secondary, custom_id="ticket_qty")
    async def change_qty(self, button, interaction):
        if interaction.user.id != self.buyer.id:
            await interaction.response.send_message("❌ Apenas o comprador pode fazer isso!", ephemeral=True)
            return
        modal = QuantityModal(self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="✅ Confirmar Pagamento", style=discord.ButtonStyle.blurple, custom_id="ticket_confirm")
    async def confirm(self, button, interaction):
        config = get_config(interaction.guild_id)
        is_admin = False
        if config and config.get('admin_role_id'):
            role = interaction.guild.get_role(config['admin_role_id'])
            if role and role in interaction.user.roles:
                is_admin = True
        if interaction.user.id in AUTHORIZED_IDS:
            is_admin = True
        
        if not is_admin:
            await interaction.response.send_message("❌ Apenas administradores podem confirmar!", ephemeral=True)
            return
        
        await confirmar_entrega(self.channel, self.product, self.buyer, self.quantity)
        await interaction.response.defer()
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.red, custom_id="ticket_cancel")
    async def cancel(self, button, interaction):
        if interaction.user.id != self.buyer.id:
            config = get_config(interaction.guild_id)
            is_admin = False
            if config and config.get('admin_role_id'):
                role = interaction.guild.get_role(config['admin_role_id'])
                if role and role in interaction.user.roles:
                    is_admin = True
            if interaction.user.id not in AUTHORIZED_IDS and not is_admin:
                await interaction.response.send_message("❌ Sem permissão!", ephemeral=True)
                return
        
        await self.channel.edit(name=f"❌-cancelado-{self.buyer.display_name[:10]}")
        await interaction.response.send_message("❌ Compra cancelada. Canal será deletado em 2 minutos...")
        await asyncio.sleep(120)
        try:
            await self.channel.delete()
        except:
            pass

class QuantityModal(Modal):
    def __init__(self, ticket_view):
        super().__init__(title="Alterar Quantidade")
        self.ticket_view = ticket_view
        self.add_item(InputText(
            label="Quantidade (1-100)",
            placeholder="Digite a quantidade",
            value=str(ticket_view.quantity),
            custom_id="qty"
        ))
    
    async def callback(self, interaction: discord.Interaction):
        try:
            qty = int(self.children[0].value)
            if qty < 1 or qty > 100:
                await interaction.response.send_message("❌ Quantidade deve ser entre 1 e 100!", ephemeral=True)
                return
        except:
            await interaction.response.send_message("❌ Valor inválido!", ephemeral=True)
            return
        
        if self.ticket_view.product.get('stock', 999) < qty:
            await interaction.response.send_message(f"❌ Estoque insuficiente! Disponível: {self.ticket_view.product.get('stock', 0)}", ephemeral=True)
            return
        
        self.ticket_view.quantity = qty
        self.ticket_view.atualizar_total()
        
        embed = discord.Embed(title=f"🛒 Compra: {self.ticket_view.product['title']}", color=0x0a0a0a)
        embed.add_field(name="💎 Valor Unitário", value=f"R$ {self.ticket_view.product['price']:.2f}", inline=True)
        embed.add_field(name="🔢 Quantidade", value=str(qty), inline=True)
        embed.add_field(name="💰 Total", value=f"R$ {self.ticket_view.total:.2f}", inline=True)
        
        if self.ticket_view.product.get('stock', 999) < 999:
            embed.add_field(name="📦 Estoque disponível", value=str(self.ticket_view.product['stock']), inline=True)
        
        embed.set_footer(text="DEJA FORN")
        
        await interaction.response.edit_message(embed=embed)
        await interaction.followup.send(f"✅ Quantidade atualizada para {qty}! Total: R$ {self.ticket_view.total:.2f}", ephemeral=True)

class CopyPixView(View):
    def __init__(self, copy_paste):
        super().__init__(timeout=None)
        self.copy_paste = copy_paste
    
    @discord.ui.button(label="📋 Copiar Pix", style=discord.ButtonStyle.secondary)
    async def copy(self, button, interaction):
        await interaction.response.send_message(f"Pix copiado:\n```\n{self.copy_paste[:1900]}\n```", ephemeral=True)

# --- Outras Views (Voz, Logs, Cargos, API, Carteira) ---
class VoiceChannelSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione um canal de voz...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        voice_channel = interaction.guild.get_channel(channel_id)
        
        if voice_channel and isinstance(voice_channel, discord.VoiceChannel):
            save_config(interaction.guild_id, voice_channel_id=channel_id)
            
            try:
                await voice_channel.connect()
            except:
                pass
            
            # Iniciar task de reconexão
            if not reconnect_voice.is_running():
                reconnect_voice.start()
            
            await interaction.response.send_message(f"✅ Conectado em: {voice_channel.name}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Canal inválido!", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for channel in interaction.guild.voice_channels:
            if len(options) < 25:
                options.append(discord.SelectOption(label=f"🔊 {channel.name}", value=str(channel.id)))
        if not options:
            options.append(discord.SelectOption(label="Nenhum canal de voz", value="0"))
        self.options = options

class VoiceChannelSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(VoiceChannelSelect())

class LogChannelSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione um canal...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        save_config(interaction.guild_id, log_channel_id=channel_id)
        channel = interaction.guild.get_channel(channel_id)
        await interaction.response.send_message(f"✅ Canal de logs: {channel.mention}", ephemeral=True)
    
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

class CustomerRoleSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione um cargo...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        save_config(interaction.guild_id, customer_role_id=role_id)
        role = interaction.guild.get_role(role_id)
        await interaction.response.send_message(f"✅ Cargo cliente: {role.mention}", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for role in interaction.guild.roles:
            if not role.is_bot_managed() and role != interaction.guild.default_role and len(options) < 25:
                options.append(discord.SelectOption(label=role.name, value=str(role.id)))
        self.options = options

class CustomerRoleSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(CustomerRoleSelect())

class AdminRoleSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione um cargo...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        save_config(interaction.guild_id, admin_role_id=role_id)
        role = interaction.guild.get_role(role_id)
        await interaction.response.send_message(f"✅ Cargo admin: {role.mention}", ephemeral=True)
    
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

class ApiKeyModal(Modal):
    def __init__(self):
        super().__init__(title="Configurar API Assas")
        self.add_item(InputText(label="API Key da Assas", placeholder="Cole sua API Key", custom_id="api_key"))
    
    async def callback(self, interaction: discord.Interaction):
        save_config(interaction.guild_id, assas_api_key=self.children[0].value)
        await interaction.response.send_message("✅ API Key configurada!", ephemeral=True)

class WalletView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="💸 Sacar via Pix", style=discord.ButtonStyle.green)
    async def withdraw(self, button, interaction):
        modal = WithdrawModal()
        await interaction.response.send_modal(modal)

class WithdrawModal(Modal):
    def __init__(self):
        super().__init__(title="Saque via Pix")
        self.add_item(InputText(label="Nome completo", placeholder="Seu nome", custom_id="name"))
        self.add_item(InputText(label="Chave Pix", placeholder="CPF/CNPJ/Email/Telefone/Aleatória", custom_id="pix_key"))
        self.add_item(InputText(label="Valor (R$)", placeholder="Ex: 50.00", custom_id="amount"))
    
    async def callback(self, interaction: discord.Interaction):
        try:
            amount = float(self.children[2].value.replace(',', '.'))
        except:
            await interaction.response.send_message("❌ Valor inválido!", ephemeral=True)
            return
        
        config = get_config(interaction.guild_id)
        balance = config.get('wallet_balance', 0.0) if config else 0.0
        
        if amount > balance:
            await interaction.response.send_message(f"❌ Saldo insuficiente! Saldo: R$ {balance:.2f}", ephemeral=True)
            return
        
        if amount < 1:
            await interaction.response.send_message("❌ Valor mínimo para saque: R$ 1.00", ephemeral=True)
            return
        
        # Deduzir saldo
        new_balance = balance - amount
        save_config(interaction.guild_id, wallet_balance=new_balance)
        
        await interaction.response.send_message(
            f"✅ Saque solicitado!\n\n"
            f"**Nome:** {self.children[0].value}\n"
            f"**Chave Pix:** {self.children[1].value}\n"
            f"**Valor:** R$ {amount:.2f}\n\n"
            f"O saque será processado em até 24h.\n"
            f"Novo saldo: R$ {new_balance:.2f}",
            ephemeral=True
        )

# --- View de Confirmação ---
class ConfirmView(View):
    def __init__(self, confirm_callback):
        super().__init__(timeout=60)
        self.confirm_callback = confirm_callback
    
    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.green)
    async def confirm_yes(self, button, interaction):
        await self.confirm_callback(interaction)
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.red)
    async def confirm_no(self, button, interaction):
        await interaction.response.edit_message(content="❌ Cancelado.", view=None)

# ============================================================
# ✅ FUNÇÃO DE CONFIRMAR ENTREGA E ENVIAR LOG
# ============================================================

async def confirmar_entrega(channel, product, buyer, quantity):
    # Diminuir estoque
    decrease_stock(product['id'], quantity)
    
    # Atualizar venda
    config = get_config(channel.guild.id)
    if config and config.get('customer_role_id'):
        role = channel.guild.get_role(config['customer_role_id'])
        if role:
            try:
                await buyer.add_roles(role)
            except:
                pass
    
    # Adicionar saldo na carteira
    if config:
        current = config.get('wallet_balance', 0.0)
        save_config(channel.guild.id, wallet_balance=current + (product['price'] * quantity))
    
    # Entrega automática na DM
    try:
        delivery_embed = discord.Embed(title="✅ ENTREGA REALIZADA - DEJA FORN", color=0xc9a227)
        delivery_embed.add_field(name="📦 Produto", value=product['title'], inline=True)
        delivery_embed.add_field(name="🔢 Quantidade", value=str(quantity), inline=True)
        delivery_embed.add_field(name="💎 Valor", value=f"R$ {product['price'] * quantity:.2f}", inline=True)
        delivery_embed.add_field(name="📄 Conteúdo", value=product.get('delivery_content', 'Conteúdo entregue pelo admin')[:1024], inline=False)
        delivery_embed.set_footer(text="DEJA FORN - Obrigado pela compra!")
        
        delivery_view = DeliveryView(product)
        await buyer.send(embed=delivery_embed, view=delivery_view)
    except Exception as e:
        print(f"Erro ao enviar DM: {e}")
    
    # Enviar log com imagem
    if config and config.get('log_channel_id'):
        log_channel = channel.guild.get_channel(config['log_channel_id'])
        if log_channel:
            avatar_url = buyer.avatar.url if buyer.avatar else buyer.default_avatar.url
            img_file = gerar_imagem_venda(
                buyer_name=buyer.display_name,
                buyer_avatar_url=avatar_url,
                product_name=product['title'],
                price=product['price'] * quantity,
                quantity=quantity
            )
            
            log_embed = discord.Embed(color=0x0a0a0a)
            log_embed.description = f"📢 + 1 vendas pessoal corre e compre antes que acabe @everyone @here"
            log_embed.set_image(url=f"attachment://{img_file.filename}")
            
            log_view = LogBuyView()
            await log_channel.send(content="@everyone @here", embed=log_embed, file=img_file, view=log_view)
    
    # Fechar canal
    await channel.edit(name=f"✔️-concluido-{buyer.display_name[:10]}")
    await channel.send("✅ Compra concluída! Canal será deletado em 2 minutos...")
    await asyncio.sleep(120)
    try:
        await channel.delete()
    except:
        pass

class DeliveryView(View):
    def __init__(self, product):
        super().__init__(timeout=None)
        self.product = product
    
    @discord.ui.button(label="🛒 Comprar Novamente", style=discord.ButtonStyle.green)
    async def buy_again(self, button, interaction):
        await interaction.response.send_message("Volte ao servidor e abra um novo ticket de compra!", ephemeral=True)
    
    @discord.ui.button(label="📋 Copiar Produto", style=discord.ButtonStyle.secondary)
    async def copy_product(self, button, interaction):
        await interaction.response.send_message(f"```\n{self.product.get('delivery_content', '')[:1900]}\n```", ephemeral=True)

class LogBuyView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🛒 Comprar", style=discord.ButtonStyle.blurple)
    async def buy(self, button, interaction):
        products = get_products(interaction.guild_id)
        if not products:
            await interaction.response.send_message("⚠️ Nenhum produto disponível.", ephemeral=True)
            return
        
        try:
            await interaction.user.send("Selecione um produto:")
            view = ProductSelectView(interaction.guild, interaction.user)
            await interaction.user.send(view=view)
            await interaction.response.send_message("📨 Verifique sua DM!", ephemeral=True)
        except:
            await interaction.response.send_message("❌ Não consigo enviar DM!", ephemeral=True)

# ============================================================
# 🔊 TASK DE RECONEXÃO DE VOZ
# ============================================================

@tasks.loop(minutes=5)
async def reconnect_voice():
    for guild in bot.guilds:
        config = get_config(guild.id)
        if config and config.get('voice_channel_id'):
            voice_client = guild.voice_client
            if not voice_client or not voice_client.is_connected():
                channel = guild.get_channel(config['voice_channel_id'])
                if channel and isinstance(channel, discord.VoiceChannel):
                    try:
                        await channel.connect()
                        print(f"🔊 Reconectado em voz: {guild.name}")
                    except Exception as e:
                        print(f"Erro ao reconectar voz: {e}")

# ============================================================
# 🌐 WEBHOOK SERVER PARA CONFIRMAÇÃO DE PAGAMENTO
# ============================================================

async def webhook_handler(request):
    try:
        data = await request.json()
        payment_id = data.get('payment', {}).get('id') or data.get('id')
        
        if payment_id and data.get('status') == 'RECEIVED':
            sale = get_sale_by_payment(payment_id)
            if sale and sale['status'] == 'pending':
                guild = bot.get_guild(sale['guild_id'])
                if guild:
                    channel = guild.get_channel(sale['ticket_channel_id'])
                    buyer = guild.get_member(sale['buyer_id'])
                    product = get_product(sale['product_id'])
                    
                    if channel and buyer and product:
                        update_sale(sale['id'], status='paid', paid_at=datetime.now().isoformat())
                        await confirmar_entrega(channel, product, buyer, sale.get('quantity', 1))
        
        return web.Response(text="OK", status=200)
    except Exception as e:
        print(f"Erro webhook: {e}")
        return web.Response(text="Error", status=500)

async def health_check(request):
    return web.Response(text="✅ Bot Vendas Online!", status=200)

async def start_web_server():
    from aiohttp import web as aio_web
    app = aio_web.Application()
    app.router.add_post('/webhook', webhook_handler)
    app.router.add_get('/health', health_check)
    
    runner = aio_web.AppRunner(app)
    await runner.setup()
    site = aio_web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"🌐 Webhook server na porta {PORT}")

# ============================================================
# ⚡ COMANDO SLASH
# ============================================================

@bot.slash_command(name="painel", description="Painel administrativo")
async def painel_admin(ctx, opcao: discord.Option(str, "Opção", choices=["vendas"])):
    embed = discord.Embed(title="🎛️ Painel Admin - DEJA FORN", color=0x0a0a0a)
    embed.description = "Configure todas as opções do sistema de vendas:"
    embed.add_field(name="📦 Produtos e Painéis", value="Criar produtos e enviar painéis para canais", inline=False)
    embed.add_field(name="🔊 Voz", value="Conectar em canal de voz permanentemente", inline=False)
    embed.add_field(name="📋 Logs", value="Configurar canal de logs de vendas", inline=False)
    embed.add_field(name="👤 Cargos", value="Configurar cargos de cliente e administrador", inline=False)
    embed.add_field(name="🔑 API", value="Configurar chave da API Assas para pagamentos Pix", inline=False)
    embed.add_field(name="💼 Carteira", value="Ver saldo e sacar via Pix", inline=False)
    embed.set_footer(text="DEJA FORN • Sistema de Vendas")
    
    view = AdminPanelView()
    await ctx.respond(embed=embed, view=view, ephemeral=True)

# ============================================================
# 🎉 EVENTOS
# ============================================================

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"💰 Bot de Vendas conectado!")
    print(f"🆔 {bot.user}")
    print(f"📍 Servidores: {len(bot.guilds)}")
    print("=" * 60)
    
    # Iniciar servidor web
    bot.loop.create_task(start_web_server())
    
    # Iniciar reconexão de voz
    reconnect_voice.start()
    
    print("\n✅ Bot pronto! Use /painel vendas")
    print("=" * 60)

# ============================================================
# 🚀 INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":
    init_db()
    print("💾 Banco de dados inicializado...")
    bot.run(BOT_TOKEN)
