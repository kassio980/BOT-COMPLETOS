import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, Select, InputText
import sqlite3
import os
import asyncio
import json
from datetime import datetime

# ============================================================
# 🔧 CONFIGURAÇÕES
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN_TICKETS", "SEU_TOKEN_AQUI")
PORT = int(os.environ.get("PORT", 5003))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)

# ============================================================
# 💾 BANCO DE DADOS
# ============================================================
DB_PATH = os.environ.get("DB_PATH_TICKETS", "bot_tickets.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        guild_id INTEGER PRIMARY KEY,
        panel_channel_id INTEGER,
        panel_message_id INTEGER,
        team_role_id INTEGER,
        ticket_name_format TEXT DEFAULT '🎫・{tipo}-{username}',
        ticket_limit INTEGER DEFAULT 1,
        inactivity_minutes INTEGER DEFAULT 0,
        transcript_enabled INTEGER DEFAULT 1,
        panel_config TEXT DEFAULT '{}',
        ticket_panel_config TEXT DEFAULT '{}',
        transcript_config TEXT DEFAULT '{}'
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS menu_options (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        name TEXT,
        emoji TEXT,
        description TEXT,
        category_id INTEGER,
        order_index INTEGER DEFAULT 0,
        custom_message TEXT DEFAULT ''
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS tickets (
        channel_id INTEGER PRIMARY KEY,
        guild_id INTEGER,
        opener_id INTEGER,
        opener_name TEXT,
        option_id INTEGER,
        option_name TEXT,
        assignee_id INTEGER,
        assignee_name TEXT,
        created_at TIMESTAMP,
        closed_at TIMESTAMP,
        status TEXT DEFAULT 'open',
        last_activity TIMESTAMP,
        notified_inactivity INTEGER DEFAULT 0
    )''')
    
    conn.commit()
    conn.close()

# --- Funções de Configuração ---
def get_config(guild_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM config WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "guild_id": row[0],
            "panel_channel_id": row[1],
            "panel_message_id": row[2],
            "team_role_id": row[3],
            "ticket_name_format": row[4],
            "ticket_limit": row[5],
            "inactivity_minutes": row[6],
            "transcript_enabled": row[7],
            "panel_config": json.loads(row[8]),
            "ticket_panel_config": json.loads(row[9]),
            "transcript_config": json.loads(row[10])
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

def save_json_config(guild_id, config_key, data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"UPDATE config SET {config_key} = ? WHERE guild_id = ?", (json.dumps(data), guild_id))
    if c.rowcount == 0:
        c.execute(f"INSERT INTO config (guild_id, {config_key}) VALUES (?, ?)", (guild_id, json.dumps(data)))
    conn.commit()
    conn.close()

# --- Funções de Opções do Menu ---
def get_menu_options(guild_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM menu_options WHERE guild_id = ? ORDER BY order_index ASC", (guild_id,))
    rows = c.fetchall()
    conn.close()
    options = []
    for row in rows:
        options.append({
            "id": row[0],
            "guild_id": row[1],
            "name": row[2],
            "emoji": row[3],
            "description": row[4],
            "category_id": row[5],
            "order_index": row[6],
            "custom_message": row[7]
        })
    return options

def add_menu_option(guild_id, name, emoji, description, category_id, order_index, custom_message=""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO menu_options (guild_id, name, emoji, description, category_id, order_index, custom_message) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (guild_id, name, emoji, description, category_id, order_index, custom_message))
    opt_id = c.lastrowid
    conn.commit()
    conn.close()
    return opt_id

def update_menu_option(opt_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [opt_id]
    c.execute(f"UPDATE menu_options SET {fields} WHERE id = ?", values)
    conn.commit()
    conn.close()

def delete_menu_option(opt_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM menu_options WHERE id = ?", (opt_id,))
    conn.commit()
    conn.close()

def get_menu_option(opt_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM menu_options WHERE id = ?", (opt_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "id": row[0],
            "guild_id": row[1],
            "name": row[2],
            "emoji": row[3],
            "description": row[4],
            "category_id": row[5],
            "order_index": row[6],
            "custom_message": row[7]
        }
    return None

# --- Funções de Tickets ---
def create_ticket(channel_id, guild_id, opener_id, opener_name, option_id, option_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("INSERT INTO tickets (channel_id, guild_id, opener_id, opener_name, option_id, option_name, created_at, status, last_activity) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?)",
              (channel_id, guild_id, opener_id, opener_name, option_id, option_name, now, now))
    conn.commit()
    conn.close()

def get_ticket(channel_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "channel_id": row[0],
            "guild_id": row[1],
            "opener_id": row[2],
            "opener_name": row[3],
            "option_id": row[4],
            "option_name": row[5],
            "assignee_id": row[6],
            "assignee_name": row[7],
            "created_at": row[8],
            "closed_at": row[9],
            "status": row[10],
            "last_activity": row[11],
            "notified_inactivity": row[12]
        }
    return None

def update_ticket(channel_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [channel_id]
    c.execute(f"UPDATE tickets SET {fields} WHERE channel_id = ?", values)
    conn.commit()
    conn.close()

def get_user_open_tickets(guild_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND opener_id = ? AND status = 'open'", (guild_id, user_id))
    count = c.fetchone()[0]
    conn.close()
    return count

def get_inactive_tickets(guild_id, minutes):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    cutoff = datetime.fromtimestamp(datetime.now().timestamp() - minutes * 60).isoformat()
    c.execute("SELECT * FROM tickets WHERE guild_id = ? AND status = 'open' AND last_activity < ? AND notified_inactivity = 0",
              (guild_id, cutoff))
    rows = c.fetchall()
    conn.close()
    tickets = []
    for row in rows:
        tickets.append({
            "channel_id": row[0],
            "guild_id": row[1],
            "opener_id": row[2],
            "opener_name": row[3],
            "option_id": row[4],
            "option_name": row[5],
            "assignee_id": row[6],
            "assignee_name": row[7],
            "created_at": row[8],
            "closed_at": row[9],
            "status": row[10],
            "last_activity": row[11],
            "notified_inactivity": row[12]
        })
    return tickets

# ============================================================
# 🎨 FUNÇÕES AUXILIARES DE UI
# ============================================================

def build_panel_embed(guild_id, panel_type="main"):
    config = get_config(guild_id)
    if not config:
        return None
    
    if panel_type == "main":
        cfg = config.get('panel_config', {})
    elif panel_type == "ticket":
        cfg = config.get('ticket_panel_config', {})
    else:
        cfg = config.get('transcript_config', {})
    
    embed = discord.Embed()
    
    if cfg.get('title'):
        embed.title = cfg['title']
    if cfg.get('description'):
        embed.description = cfg['description']
    if cfg.get('color'):
        try:
            embed.color = int(cfg['color'].replace('#', ''), 16)
        except:
            embed.color = discord.Color.blue()
    else:
        embed.color = discord.Color.blue()
    
    if cfg.get('banner'):
        embed.set_image(url=cfg['banner'])
    if cfg.get('thumbnail'):
        embed.set_thumbnail(url=cfg['thumbnail'])
    if cfg.get('footer') or cfg.get('footer_icon'):
        embed.set_footer(text=cfg.get('footer', ''), icon_url=cfg.get('footer_icon'))
    
    return embed

def replace_variables(text, user=None, ticket_channel=None, option_name="", guild=None):
    if not text:
        return ""
    if user:
        text = text.replace("{user}", user.mention)
        text = text.replace("{username}", user.display_name)
        text = text.replace("{userid}", str(user.id))
    if ticket_channel:
        text = text.replace("{ticket}", ticket_channel.mention)
        text = text.replace("{ticketname}", ticket_channel.name)
    text = text.replace("{tipo}", option_name)
    if guild:
        text = text.replace("{server}", guild.name)
    return text

# ============================================================
# 🎛️ PAINEL ADMINISTRATIVO
# ============================================================

class AdminPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📋 Gerenciar Select Menu", style=discord.ButtonStyle.primary, custom_id="admin_menu")
    async def manage_menu(self, button, interaction):
        view = MenuManagerView(interaction.guild_id)
        await view.update_message()
        await interaction.response.send_message("Gerenciamento do Select Menu:", view=view, ephemeral=True)
    
    @discord.ui.button(label="🎨 Painel Principal", style=discord.ButtonStyle.primary, custom_id="admin_panel_main")
    async def panel_main(self, button, interaction):
        view = PanelEditorView("main")
        await interaction.response.send_message("Editor do Painel Principal:", view=view, ephemeral=True)
    
    @discord.ui.button(label="🎟️ Painel do Ticket", style=discord.ButtonStyle.primary, custom_id="admin_panel_ticket")
    async def panel_ticket(self, button, interaction):
        view = PanelEditorView("ticket")
        await interaction.response.send_message("Editor do Painel Interno do Ticket:", view=view, ephemeral=True)
    
    @discord.ui.button(label="👥 Cargo da Equipe", style=discord.ButtonStyle.secondary, custom_id="admin_team_role")
    async def team_role(self, button, interaction):
        view = TeamRoleSelectView()
        await interaction.response.send_message("Selecione o cargo da equipe:", view=view, ephemeral=True)
    
    @discord.ui.button(label="📂 Destinos", style=discord.ButtonStyle.secondary, custom_id="admin_destinations")
    async def destinations(self, button, interaction):
        view = DestinationManagerView(interaction.guild_id)
        await view.update_message()
        await interaction.response.send_message("Configurar destinos das opções:", view=view, ephemeral=True)
    
    @discord.ui.button(label="📜 Mensagem do Transcript", style=discord.ButtonStyle.secondary, custom_id="admin_transcript")
    async def transcript_msg(self, button, interaction):
        view = PanelEditorView("transcript")
        await interaction.response.send_message("Editor da Mensagem do Transcript:", view=view, ephemeral=True)
    
    @discord.ui.button(label="⚙️ Configurações", style=discord.ButtonStyle.grey, custom_id="admin_settings")
    async def settings(self, button, interaction):
        view = SettingsView(interaction.guild_id)
        await view.update_message()
        await interaction.response.send_message("Configurações gerais:", view=view, ephemeral=True)
    
    @discord.ui.button(label="🔄 Atualizar Painel", style=discord.ButtonStyle.green, custom_id="admin_refresh")
    async def refresh_panel(self, button, interaction):
        await atualizar_painel_principal(interaction.guild)
        await interaction.response.send_message("✅ Painel principal atualizado com sucesso!", ephemeral=True)

# ============================================================
# 📋 GERENCIADOR DO SELECT MENU
# ============================================================

class MenuManagerView(View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
    
    async def update_message(self):
        options = get_menu_options(self.guild_id)
        if not options:
            for child in self.children:
                if child.custom_id in ["menu_edit", "menu_delete", "menu_up", "menu_down"]:
                    child.disabled = True
        else:
            for child in self.children:
                if child.custom_id in ["menu_edit", "menu_delete", "menu_up", "menu_down"]:
                    child.disabled = False
    
    def get_options_list(self):
        options = get_menu_options(self.guild_id)
        texto = ""
        for i, opt in enumerate(options):
            emoji = opt.get('emoji', '') or ''
            texto += f"`{i+1}.` {emoji} **{opt['name']}**"
            if opt.get('description'):
                texto += f" - _{opt['description'][:50]}_"
            texto += "\n"
        return texto or "Nenhuma opção cadastrada ainda."
    
    @discord.ui.select(placeholder="Selecione uma opção para gerenciar...", custom_id="menu_select", min_values=1, max_values=1)
    async def select_option(self, select, interaction):
        self.selected_id = int(select.values[0])
        await interaction.response.defer()
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = get_menu_options(interaction.guild_id)
        select = [c for c in self.children if c.custom_id == "menu_select"][0]
        select.options = []
        for opt in options:
            label = f"{opt.get('emoji', '')} {opt['name']}" if opt.get('emoji') else opt['name']
            select.options.append(discord.SelectOption(label=label[:90], value=str(opt['id']), description=opt.get('description', '')[:100]))
    
    @discord.ui.button(label="➕ Adicionar", style=discord.ButtonStyle.green, custom_id="menu_add")
    async def add(self, button, interaction):
        modal = AddOptionModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="✏️ Editar", style=discord.ButtonStyle.primary, custom_id="menu_edit")
    async def edit(self, button, interaction):
        if not hasattr(self, 'selected_id'):
            await interaction.response.send_message("Selecione uma opção primeiro!", ephemeral=True)
            return
        opt = get_menu_option(self.selected_id)
        if not opt:
            await interaction.response.send_message("Opção não encontrada!", ephemeral=True)
            return
        modal = EditOptionModal(opt)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🗑️ Excluir", style=discord.ButtonStyle.red, custom_id="menu_delete")
    async def delete(self, button, interaction):
        if not hasattr(self, 'selected_id'):
            await interaction.response.send_message("Selecione uma opção primeiro!", ephemeral=True)
            return
        opt = get_menu_option(self.selected_id)
        if not opt:
            await interaction.response.send_message("Opção não encontrada!", ephemeral=True)
            return
        
        view = ConfirmView(f"Deseja realmente excluir a opção **{opt['name']}**?", lambda i: self.confirm_delete(i))
        await interaction.response.send_message("Confirmação:", view=view, ephemeral=True)
    
    async def confirm_delete(self, interaction):
        delete_menu_option(self.selected_id)
        await interaction.response.send_message("✅ Opção excluída!", ephemeral=True)
        await atualizar_painel_principal(interaction.guild)
    
    @discord.ui.button(label="⬆️ Subir", style=discord.ButtonStyle.grey, custom_id="menu_up")
    async def up(self, button, interaction):
        if not hasattr(self, 'selected_id'):
            await interaction.response.send_message("Selecione uma opção primeiro!", ephemeral=True)
            return
        options = get_menu_options(interaction.guild_id)
        for i, opt in enumerate(options):
            if opt['id'] == self.selected_id and i > 0:
                prev = options[i-1]
                update_menu_option(opt['id'], order_index=prev['order_index'])
                update_menu_option(prev['id'], order_index=opt['order_index'])
                await interaction.response.send_message("✅ Ordem atualizada!", ephemeral=True)
                await atualizar_painel_principal(interaction.guild)
                return
        await interaction.response.send_message("Não é possível subir mais!", ephemeral=True)
    
    @discord.ui.button(label="⬇️ Descer", style=discord.ButtonStyle.grey, custom_id="menu_down")
    async def down(self, button, interaction):
        if not hasattr(self, 'selected_id'):
            await interaction.response.send_message("Selecione uma opção primeiro!", ephemeral=True)
            return
        options = get_menu_options(interaction.guild_id)
        for i, opt in enumerate(options):
            if opt['id'] == self.selected_id and i < len(options) - 1:
                nxt = options[i+1]
                update_menu_option(opt['id'], order_index=nxt['order_index'])
                update_menu_option(nxt['id'], order_index=opt['order_index'])
                await interaction.response.send_message("✅ Ordem atualizada!", ephemeral=True)
                await atualizar_painel_principal(interaction.guild)
                return
        await interaction.response.send_message("Não é possível descer mais!", ephemeral=True)

class AddOptionModal(Modal):
    def __init__(self):
        super().__init__(title="Adicionar Opção")
        self.add_item(InputText(label="Nome", placeholder="Ex: Ajuda", custom_id="name"))
        self.add_item(InputText(label="Emoji (opcional)", placeholder="🆘", required=False, custom_id="emoji"))
        self.add_item(InputText(label="Descrição (opcional)", placeholder="Precisa de ajuda?", required=False, custom_id="description"))
        self.add_item(InputText(label="Mensagem inicial (opcional)", placeholder="Mensagem específica...", required=False, style=discord.InputTextStyle.long, custom_id="message"))
    
    async def callback(self, interaction: discord.Interaction):
        options = get_menu_options(interaction.guild_id)
        order = len(options)
        add_menu_option(
            interaction.guild_id,
            self.children[0].value,
            self.children[1].value or "",
            self.children[2].value or "",
            0,
            order,
            self.children[3].value or ""
        )
        await interaction.response.send_message("✅ Opção adicionada! Agora configure o destino em 📂 Destinos.", ephemeral=True)
        await atualizar_painel_principal(interaction.guild)

class EditOptionModal(Modal):
    def __init__(self, opt):
        super().__init__(title=f"Editar: {opt['name']}")
        self.opt_id = opt['id']
        self.add_item(InputText(label="Nome", value=opt['name'], custom_id="name"))
        self.add_item(InputText(label="Emoji", value=opt.get('emoji', '') or "", required=False, custom_id="emoji"))
        self.add_item(InputText(label="Descrição", value=opt.get('description', '') or "", required=False, custom_id="description"))
        self.add_item(InputText(label="Mensagem inicial", value=opt.get('custom_message', '') or "", required=False, style=discord.InputTextStyle.long, custom_id="message"))
    
    async def callback(self, interaction: discord.Interaction):
        update_menu_option(
            self.opt_id,
            name=self.children[0].value,
            emoji=self.children[1].value or "",
            description=self.children[2].value or "",
            custom_message=self.children[3].value or ""
        )
        await interaction.response.send_message("✅ Opção atualizada!", ephemeral=True)
        await atualizar_painel_principal(interaction.guild)

# ============================================================
# 📂 GERENCIADOR DE DESTINOS
# ============================================================

class DestinationManagerView(View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
    
    async def update_message(self):
        pass
    
    @discord.ui.select(placeholder="Selecione uma opção para definir destino...", custom_id="dest_select", min_values=1, max_values=1)
    async def select_option(self, select, interaction):
        self.selected_id = int(select.values[0])
        opt = get_menu_option(self.selected_id)
        category = interaction.guild.get_channel(opt['category_id']) if opt.get('category_id') else None
        
        view = CategorySelectView(self.selected_id)
        texto = f"Opção: **{opt.get('emoji', '')} {opt['name']}**\n"
        texto += f"Destino atual: {category.mention if category else '❌ Não configurado'}"
        
        await interaction.response.send_message(texto, view=view, ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = get_menu_options(interaction.guild_id)
        select = [c for c in self.children if c.custom_id == "dest_select"][0]
        select.options = []
        for opt in options:
            label = f"{opt.get('emoji', '')} {opt['name']}" if opt.get('emoji') else opt['name']
            select.options.append(discord.SelectOption(label=label[:90], value=str(opt['id'])))

class CategorySelect(Select):
    def __init__(self, option_id):
        self.option_id = option_id
        super().__init__(placeholder="Selecione uma categoria...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        cat_id = int(self.values[0])
        update_menu_option(self.option_id, category_id=cat_id)
        cat = interaction.guild.get_channel(cat_id)
        await interaction.response.send_message(f"✅ Destino configurado: {cat.name}", ephemeral=True)
        await atualizar_painel_principal(interaction.guild)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for cat in interaction.guild.categories:
            options.append(discord.SelectOption(label=f"📁 {cat.name}", value=str(cat.id)))
        if not options:
            options.append(discord.SelectOption(label="Nenhuma categoria encontrada", value="0"))
        self.options = options

class CategorySelectView(View):
    def __init__(self, option_id):
        super().__init__(timeout=120)
        self.add_item(CategorySelect(option_id))

# ============================================================
# 👥 SELEÇÃO DE CARGO DA EQUIPE
# ============================================================

class TeamRoleSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione o cargo da equipe...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        save_config(interaction.guild_id, team_role_id=role_id)
        role = interaction.guild.get_role(role_id)
        await interaction.response.send_message(f"✅ Cargo da equipe configurado: {role.mention}", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for role in interaction.guild.roles:
            if not role.is_bot_managed() and role != interaction.guild.default_role and len(options) < 25:
                options.append(discord.SelectOption(label=role.name, value=str(role.id)))
        self.options = options

class TeamRoleSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(TeamRoleSelect())

# ============================================================
# 🎨 EDITOR DE PAINÉIS
# ============================================================

class PanelEditorView(View):
    def __init__(self, panel_type):
        super().__init__(timeout=None)
        self.panel_type = panel_type
    
    @discord.ui.button(label="✏️ Título", style=discord.ButtonStyle.secondary, custom_id="edit_title")
    async def edit_title(self, button, interaction):
        modal = SimpleTextModal("Editar Título", "Novo título", "title", self.panel_type)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📝 Descrição", style=discord.ButtonStyle.secondary, custom_id="edit_desc")
    async def edit_desc(self, button, interaction):
        modal = SimpleTextModal("Editar Descrição", "Nova descrição", "description", self.panel_type, long=True)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🎨 Cor (HEX)", style=discord.ButtonStyle.secondary, custom_id="edit_color")
    async def edit_color(self, button, interaction):
        modal = SimpleTextModal("Editar Cor", "Ex: #3498db", "color", self.panel_type)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🖼️ Banner/GIF", style=discord.ButtonStyle.secondary, custom_id="edit_banner")
    async def edit_banner(self, button, interaction):
        modal = SimpleTextModal("Banner/GIF", "URL da imagem ou GIF", "banner", self.panel_type)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🖼️ Thumbnail", style=discord.ButtonStyle.secondary, custom_id="edit_thumb")
    async def edit_thumb(self, button, interaction):
        modal = SimpleTextModal("Thumbnail", "URL da imagem", "thumbnail", self.panel_type)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📜 Rodapé", style=discord.ButtonStyle.secondary, custom_id="edit_footer", row=2)
    async def edit_footer(self, button, interaction):
        modal = SimpleTextModal("Texto do Rodapé", "Texto do rodapé", "footer", self.panel_type)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔗 Ícone Rodapé", style=discord.ButtonStyle.secondary, custom_id="edit_footer_icon", row=2)
    async def edit_footer_icon(self, button, interaction):
        modal = SimpleTextModal("Ícone do Rodapé", "URL da imagem", "footer_icon", self.panel_type)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="👁️ Visualizar", style=discord.ButtonStyle.green, custom_id="preview", row=2)
    async def preview(self, button, interaction):
        embed = build_panel_embed(interaction.guild_id, self.panel_type)
        if embed:
            await interaction.response.send_message("Pré-visualização:", embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message("Painel não configurado ainda.", ephemeral=True)
    
    @discord.ui.button(label="🔄 Atualizar Painel", style=discord.ButtonStyle.blurple, custom_id="refresh_panel", row=3)
    async def refresh(self, button, interaction):
        await atualizar_painel_principal(interaction.guild)
        await interaction.response.send_message("✅ Painel atualizado!", ephemeral=True)

class SimpleTextModal(Modal):
    def __init__(self, title, placeholder, field, panel_type, long=False):
        super().__init__(title=title)
        self.field = field
        self.panel_type = panel_type
        style = discord.InputTextStyle.long if long else discord.InputTextStyle.short
        self.add_item(InputText(label=title, placeholder=placeholder, style=style, custom_id="value", required=False))
    
    async def callback(self, interaction: discord.Interaction):
        value = self.children[0].value
        config = get_config(interaction.guild_id)
        
        config_key = {
            "main": "panel_config",
            "ticket": "ticket_panel_config",
            "transcript": "transcript_config"
        }.get(self.panel_type, "panel_config")
        
        current = config.get(config_key, {}) if config else {}
        current[self.field] = value
        save_json_config(interaction.guild_id, config_key, current)
        
        await interaction.response.send_message(f"✅ {self.title} atualizado(a)!", ephemeral=True)

# ============================================================
# ⚙️ CONFIGURAÇÕES GERAIS
# ============================================================

class SettingsView(View):
    def __init__(self, guild_id):
        super().__init__(timeout=None)
        self.guild_id = guild_id
    
    async def update_message(self):
        pass
    
    @discord.ui.button(label="📝 Formato Nome Ticket", style=discord.ButtonStyle.primary, custom_id="cfg_name_format")
    async def name_format(self, button, interaction):
        config = get_config(interaction.guild_id)
        current = config.get('ticket_name_format', '🎫・{tipo}-{username}') if config else '🎫・{tipo}-{username}'
        modal = NameFormatModal(current)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔢 Limite Tickets", style=discord.ButtonStyle.primary, custom_id="cfg_limit")
    async def ticket_limit(self, button, interaction):
        view = LimitSelectView()
        await interaction.response.send_message("Selecione o limite de tickets por usuário:", view=view, ephemeral=True)
    
    @discord.ui.button(label="🕐 Fechamento Inatividade", style=discord.ButtonStyle.primary, custom_id="cfg_inactivity")
    async def inactivity(self, button, interaction):
        view = InactivitySelectView()
        await interaction.response.send_message("Tempo para fechamento automático por inatividade:", view=view, ephemeral=True)
    
    @discord.ui.button(label="📜 Transcript", style=discord.ButtonStyle.primary, custom_id="cfg_transcript_toggle")
    async def transcript_toggle(self, button, interaction):
        config = get_config(interaction.guild_id)
        current = config.get('transcript_enabled', 1) if config else 1
        new_val = 0 if current == 1 else 1
        save_config(interaction.guild_id, transcript_enabled=new_val)
        
        status = "✅ ATIVADO" if new_val == 1 else "❌ DESATIVADO"
        await interaction.response.send_message(f"Transcript automático: **{status}**", ephemeral=True)
    
    @discord.ui.button(label="📤 Enviar Painel", style=discord.ButtonStyle.green, custom_id="cfg_send_panel")
    async def send_panel(self, button, interaction):
        view = PanelChannelSelectView()
        await interaction.response.send_message("Escolha o canal para enviar o painel de tickets:", view=view, ephemeral=True)

class NameFormatModal(Modal):
    def __init__(self, current):
        super().__init__(title="Formato do Nome do Ticket")
        self.add_item(InputText(
            label="Formato",
            placeholder="🎫・{tipo}-{username}",
            value=current,
            custom_id="format"
        ))
    
    async def callback(self, interaction: discord.Interaction):
        fmt = self.children[0].value
        save_config(interaction.guild_id, ticket_name_format=fmt)
        await interaction.response.send_message(f"✅ Formato atualizado: `{fmt}`\n\nVariáveis: `{{username}}`, `{{userid}}`, `{{tipo}}`", ephemeral=True)

class LimitSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1 ticket", value="1", description="Padrão"),
            discord.SelectOption(label="2 tickets", value="2"),
            discord.SelectOption(label="3 tickets", value="3"),
            discord.SelectOption(label="Ilimitado", value="999")
        ]
        super().__init__(placeholder="Selecione o limite...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        limit = int(self.values[0])
        save_config(interaction.guild_id, ticket_limit=limit)
        texto = "Ilimitado" if limit >= 999 else f"{limit} ticket(s)"
        await interaction.response.send_message(f"✅ Limite configurado: **{texto}** por usuário", ephemeral=True)

class LimitSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(LimitSelect())

class InactivitySelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="❌ Desativado", value="0"),
            discord.SelectOption(label="30 minutos", value="30"),
            discord.SelectOption(label="1 hora", value="60"),
            discord.SelectOption(label="6 horas", value="360"),
            discord.SelectOption(label="12 horas", value="720"),
            discord.SelectOption(label="24 horas", value="1440")
        ]
        super().__init__(placeholder="Selecione o tempo...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        minutes = int(self.values[0])
        save_config(interaction.guild_id, inactivity_minutes=minutes)
        texto = "Desativado" if minutes == 0 else f"{minutes} minutos"
        await interaction.response.send_message(f"✅ Fechamento por inatividade: **{texto}**", ephemeral=True)

class InactivitySelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(InactivitySelect())

class PanelChannelSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione um canal...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        channel = interaction.guild.get_channel(channel_id)
        
        if not channel:
            await interaction.response.send_message("Canal não encontrado!", ephemeral=True)
            return
        
        # Salvar configuração
        save_config(interaction.guild_id, panel_channel_id=channel_id)
        
        # Inicializar configs padrão se não existirem
        config = get_config(interaction.guild_id)
        if not config or not config.get('panel_config'):
            default_panel = {
                "title": "🎫 Central de Atendimento",
                "description": "Selecione abaixo o tipo de atendimento que deseja abrir.",
                "color": "#5865f2",
                "footer": "Selecione uma opção abaixo"
            }
            save_json_config(interaction.guild_id, "panel_config", default_panel)
        
        if not config or not config.get('ticket_panel_config'):
            default_ticket = {
                "title": "🎫 Atendimento iniciado",
                "description": "Olá {user}, seu atendimento foi criado com sucesso.\n\nAguarde um membro da equipe responder.",
                "color": "#2ecc71"
            }
            save_json_config(interaction.guild_id, "ticket_panel_config", default_ticket)
        
        if not config or not config.get('transcript_config'):
            default_transcript = {
                "title": "📜 Transcript do seu atendimento",
                "description": "Seu atendimento foi encerrado.\n\nAbaixo está o registro completo da conversa.\n\nObrigado por entrar em contato com nossa equipe.",
                "color": "#3498db"
            }
            save_json_config(interaction.guild_id, "transcript_config", default_transcript)
        
        # Enviar painel
        await enviar_painel_principal(channel)
        await interaction.response.send_message(f"✅ Painel enviado para {channel.mention}!", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for channel in interaction.guild.text_channels:
            if len(options) < 25:
                options.append(discord.SelectOption(label=f"#{channel.name}", value=str(channel.id)))
        self.options = options

class PanelChannelSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(PanelChannelSelect())

# ============================================================
# 🎯 PAINEL PRINCIPAL DE TICKETS (Select Menu)
# ============================================================

class TicketSelect(Select):
    def __init__(self, guild_id):
        self.guild_id = guild_id
        options = []
        menu_options = get_menu_options(guild_id)
        
        config = get_config(guild_id)
        panel_cfg = config.get('panel_config', {}) if config else {}
        
        placeholder = panel_cfg.get('placeholder', 'Selecione o tipo de atendimento...')
        
        for opt in menu_options:
            label = opt['name'][:90]
            emoji = opt.get('emoji') or None
            description = opt.get('description', '')[:100] or None
            
            select_opt = discord.SelectOption(label=label, value=str(opt['id']))
            if emoji:
                try:
                    select_opt.emoji = emoji.strip()
                except:
                    pass
            if description:
                select_opt.description = description
            options.append(select_opt)
        
        if not options:
            options.append(discord.SelectOption(label="Nenhuma opção disponível", value="none"))
        
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, custom_id="ticket_select")
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("Nenhuma opção de atendimento disponível no momento.", ephemeral=True)
            return
        
        option_id = int(self.values[0])
        opt = get_menu_option(option_id)
        
        if not opt:
            await interaction.response.send_message("Opção inválida!", ephemeral=True)
            return
        
        config = get_config(interaction.guild_id)
        if not config:
            await interaction.response.send_message("Sistema não configurado!", ephemeral=True)
            return
        
        # Verificar limite
        limit = config.get('ticket_limit', 1)
        open_tickets = get_user_open_tickets(interaction.guild_id, interaction.user.id)
        
        if limit < 999 and open_tickets >= limit:
            await interaction.response.send_message("⚠️ Você já possui um ticket aberto.", ephemeral=True)
            return
        
        # Verificar categoria destino
        category = interaction.guild.get_channel(opt.get('category_id', 0))
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message("⚠️ Esta opção não possui um destino configurado. Contate um administrador.", ephemeral=True)
            return
        
        # Verificar cargo da equipe
        team_role = None
        if config.get('team_role_id'):
            team_role = interaction.guild.get_role(config['team_role_id'])
        
        # Criar nome do canal
        name_format = config.get('ticket_name_format', '🎫・{tipo}-{username}')
        channel_name = name_format.replace('{username}', interaction.user.display_name.lower().replace(' ', '-')[:20])
        channel_name = channel_name.replace('{userid}', str(interaction.user.id))
        channel_name = channel_name.replace('{tipo}', opt['name'].lower().replace(' ', '-')[:15])
        
        # Permissões
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_permissions=True)
        }
        
        if team_role:
            overwrites[team_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        
        # Criar canal
        try:
            ticket_channel = await interaction.guild.create_text_channel(
                name=channel_name[:50],
                category=category,
                overwrites=overwrites
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Erro ao criar ticket: {str(e)[:100]}", ephemeral=True)
            return
        
        # Registrar ticket
        create_ticket(ticket_channel.id, interaction.guild_id, interaction.user.id, interaction.user.name, option_id, opt['name'])
        
        # Construir mensagem do ticket
        ticket_cfg = config.get('ticket_panel_config', {})
        embed = discord.Embed()
        
        if ticket_cfg.get('title'):
            embed.title = replace_variables(ticket_cfg['title'], user=interaction.user, ticket_channel=ticket_channel, option_name=opt['name'], guild=interaction.guild)
        
        desc = ticket_cfg.get('description', '') or ''
        if opt.get('custom_message'):
            desc += f"\n\n{opt['custom_message']}"
        
        embed.description = replace_variables(desc, user=interaction.user, ticket_channel=ticket_channel, option_name=opt['name'], guild=interaction.guild)
        
        if ticket_cfg.get('color'):
            try:
                embed.color = int(ticket_cfg['color'].replace('#', ''), 16)
            except:
                embed.color = discord.Color.green()
        else:
            embed.color = discord.Color.green()
        
        if ticket_cfg.get('banner'):
            embed.set_image(url=ticket_cfg['banner'])
        if ticket_cfg.get('thumbnail'):
            embed.set_thumbnail(url=ticket_cfg['thumbnail'])
        if ticket_cfg.get('footer') or ticket_cfg.get('footer_icon'):
            embed.set_footer(text=ticket_cfg.get('footer', ''), icon_url=ticket_cfg.get('footer_icon'))
        
        embed.add_field(name="👤 Usuário", value=interaction.user.mention, inline=True)
        embed.add_field(name="📋 Tipo", value=opt.get('emoji', '') + " " + opt['name'], inline=True)
        embed.add_field(name="🆔 ID", value=str(interaction.user.id), inline=True)
        
        view = TicketPanelView()
        
        content = interaction.user.mention
        if team_role:
            content += f" {team_role.mention}"
        
        await ticket_channel.send(content=content, embed=embed, view=view)
        await interaction.response.send_message(f"✅ Ticket criado: {ticket_channel.mention}", ephemeral=True)

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🔒 Fechar Ticket", style=discord.ButtonStyle.red, custom_id="ticket_close", emoji="🔒")
    async def close(self, button, interaction):
        config = get_config(interaction.guild_id)
        team_role_id = config.get('team_role_id') if config else None
        
        is_team = False
        if team_role_id:
            role = interaction.guild.get_role(team_role_id)
            if role and role in interaction.user.roles:
                is_team = True
        
        ticket = get_ticket(interaction.channel.id)
        if ticket and ticket['opener_id'] == interaction.user.id:
            is_team = True
        
        if not is_team:
            await interaction.response.send_message("❌ Apenas a equipe ou o dono do ticket podem fechar!", ephemeral=True)
            return
        
        view = ConfirmView(
            "⚠️ Deseja realmente fechar este ticket?\n\nAo confirmar, o atendimento será encerrado e o transcript será gerado automaticamente.",
            lambda i: confirmar_fechamento(i, interaction.channel)
        )
        await interaction.response.send_message("Confirmação:", view=view, ephemeral=True)
    
    @discord.ui.button(label="👤 Assumir Ticket", style=discord.ButtonStyle.primary, custom_id="ticket_claim", emoji="👤")
    async def claim(self, button, interaction):
        config = get_config(interaction.guild_id)
        team_role_id = config.get('team_role_id') if config else None
        
        if team_role_id:
            role = interaction.guild.get_role(team_role_id)
            if not role or role not in interaction.user.roles:
                await interaction.response.send_message("❌ Apenas a equipe pode assumir tickets!", ephemeral=True)
                return
        
        update_ticket(interaction.channel.id, assignee_id=interaction.user.id, assignee_name=interaction.user.display_name)
        
        embed = discord.Embed(
            description=f"👤 **Atendimento assumido por:** {interaction.user.mention}",
            color=discord.Color.blue()
        )
        await interaction.channel.send(embed=embed)
        await interaction.response.defer()
    
    @discord.ui.button(label="➕ Adicionar Usuário", style=discord.ButtonStyle.secondary, custom_id="ticket_add", emoji="➕")
    async def add_user(self, button, interaction):
        config = get_config(interaction.guild_id)
        team_role_id = config.get('team_role_id') if config else None
        
        if team_role_id:
            role = interaction.guild.get_role(team_role_id)
            if not role or role not in interaction.user.roles:
                await interaction.response.send_message("❌ Apenas a equipe pode adicionar usuários!", ephemeral=True)
                return
        
        view = AddUserSelectView(interaction.channel)
        await interaction.response.send_message("Selecione o usuário para adicionar:", view=view, ephemeral=True)
    
    @discord.ui.button(label="➖ Remover Usuário", style=discord.ButtonStyle.secondary, custom_id="ticket_remove", emoji="➖")
    async def remove_user(self, button, interaction):
        config = get_config(interaction.guild_id)
        team_role_id = config.get('team_role_id') if config else None
        
        if team_role_id:
            role = interaction.guild.get_role(team_role_id)
            if not role or role not in interaction.user.roles:
                await interaction.response.send_message("❌ Apenas a equipe pode remover usuários!", ephemeral=True)
                return
        
        view = RemoveUserSelectView(interaction.channel)
        await interaction.response.send_message("Selecione o usuário para remover:", view=view, ephemeral=True)
    
    @discord.ui.button(label="✏️ Renomear", style=discord.ButtonStyle.secondary, custom_id="ticket_rename", emoji="✏️", row=2)
    async def rename(self, button, interaction):
        config = get_config(interaction.guild_id)
        team_role_id = config.get('team_role_id') if config else None
        
        if team_role_id:
            role = interaction.guild.get_role(team_role_id)
            if not role or role not in interaction.user.roles:
                await interaction.response.send_message("❌ Apenas a equipe pode renomear!", ephemeral=True)
                return
        
        modal = RenameTicketModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🔔 Notificar Equipe", style=discord.ButtonStyle.blurple, custom_id="ticket_notify", emoji="🔔", row=2)
    async def notify(self, button, interaction):
        config = get_config(interaction.guild_id)
        team_role_id = config.get('team_role_id') if config else None
        
        if not team_role_id:
            await interaction.response.send_message("⚠️ Cargo da equipe não configurado!", ephemeral=True)
            return
        
        role = interaction.guild.get_role(team_role_id)
        if not role:
            await interaction.response.send_message("⚠️ Cargo da equipe não encontrado!", ephemeral=True)
            return
        
        ticket = get_ticket(interaction.channel.id)
        if ticket and ticket.get('assignee_id'):
            await interaction.response.send_message("⚠️ Este ticket já foi assumido!", ephemeral=True)
            return
        
        embed = discord.Embed(
            description=f"🔔 {interaction.user.mention} notificou a equipe!",
            color=discord.Color.orange()
        )
        await interaction.channel.send(content=role.mention, embed=embed)
        await interaction.response.defer()

# --- Views auxiliares do ticket ---

class AddUserSelect(Select):
    def __init__(self, channel):
        self.channel = channel
        super().__init__(placeholder="Digite para buscar um usuário...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        user_id = int(self.values[0])
        member = interaction.guild.get_member(user_id)
        
        if not member:
            await interaction.response.send_message("Usuário não encontrado!", ephemeral=True)
            return
        
        await self.channel.set_permissions(member, read_messages=True, send_messages=True)
        
        embed = discord.Embed(
            description=f"➕ **{member.mention}** foi adicionado ao ticket!",
            color=discord.Color.green()
        )
        await self.channel.send(embed=embed)
        await interaction.response.send_message(f"✅ {member.mention} adicionado!", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for member in interaction.guild.members:
            if not member.bot and len(options) < 25:
                options.append(discord.SelectOption(label=member.display_name[:90], value=str(member.id), description=f"@{member.name}"))
        self.options = options

class AddUserSelectView(View):
    def __init__(self, channel):
        super().__init__(timeout=120)
        self.add_item(AddUserSelect(channel))

class RemoveUserSelect(Select):
    def __init__(self, channel):
        self.channel = channel
        super().__init__(placeholder="Selecione um usuário para remover...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        user_id = int(self.values[0])
        member = interaction.guild.get_member(user_id)
        
        if not member:
            await interaction.response.send_message("Usuário não encontrado!", ephemeral=True)
            return
        
        ticket = get_ticket(self.channel.id)
        if ticket and ticket['opener_id'] == member.id:
            await interaction.response.send_message("❌ Não é possível remover o dono do ticket!", ephemeral=True)
            return
        
        await self.channel.set_permissions(member, overwrite=None)
        
        embed = discord.Embed(
            description=f"➖ **{member.mention}** foi removido do ticket!",
            color=discord.Color.red()
        )
        await self.channel.send(embed=embed)
        await interaction.response.send_message(f"✅ {member.mention} removido!", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        ticket = get_ticket(self.channel.id)
        for member in self.channel.members:
            if not member.bot and member.id != interaction.guild.me.id:
                if ticket and member.id != ticket.get('opener_id'):
                    if len(options) < 25:
                        options.append(discord.SelectOption(label=member.display_name[:90], value=str(member.id)))
        if not options:
            options.append(discord.SelectOption(label="Nenhum usuário para remover", value="0"))
        self.options = options

class RemoveUserSelectView(View):
    def __init__(self, channel):
        super().__init__(timeout=120)
        self.add_item(RemoveUserSelect(channel))

class RenameTicketModal(Modal):
    def __init__(self):
        super().__init__(title="Renomear Ticket")
        self.add_item(InputText(label="Novo nome", placeholder="Novo nome do canal", custom_id="name"))
    
    async def callback(self, interaction: discord.Interaction):
        new_name = self.children[0].value[:50]
        await interaction.channel.edit(name=new_name)
        await interaction.response.send_message(f"✅ Ticket renomeado para: `{new_name}`", ephemeral=True)

class ConfirmView(View):
    def __init__(self, message, confirm_callback):
        super().__init__(timeout=60)
        self.message = message
        self.confirm_callback = confirm_callback
        self.children[0].label = "✅ Confirmar"
        self.children[0].style = discord.ButtonStyle.green
        self.children[1].label = "❌ Cancelar"
        self.children[1].style = discord.ButtonStyle.red
    
    @discord.ui.button(custom_id="confirm_yes")
    async def confirm_yes(self, button, interaction):
        await self.confirm_callback(interaction)
    
    @discord.ui.button(custom_id="confirm_no")
    async def confirm_no(self, button, interaction):
        await interaction.response.edit_message(content="❌ Ação cancelada.", view=None, embed=None)

# ============================================================
# 📜 FUNÇÕES DE FECHAMENTO E TRANSCRIPT
# ============================================================

async def confirmar_fechamento(interaction, channel):
    ticket = get_ticket(channel.id)
    if not ticket:
        await interaction.response.edit_message(content="❌ Ticket não encontrado!", view=None)
        return
    
    config = get_config(channel.guild.id)
    transcript_enabled = config.get('transcript_enabled', 1) if config else 1
    
    await interaction.response.edit_message(content="🔄 Fechando ticket...", view=None)
    
    # Gerar e enviar transcript se habilitado
    if transcript_enabled:
        await gerar_e_enviar_transcript(channel, ticket, config)
    
    # Marcar como fechado
    update_ticket(channel.id, status='closed', closed_at=datetime.now().isoformat())
    
    # Aviso e fechar
    close_embed = discord.Embed(
        title="🔒 Ticket Fechado",
        description="Este atendimento foi encerrado. O canal será deletado em alguns segundos.",
        color=discord.Color.red()
    )
    await channel.send(embed=close_embed)
    
    await asyncio.sleep(5)
    try:
        await channel.delete()
    except:
        pass

async def gerar_e_enviar_transcript(channel, ticket, config):
    try:
        # Coletar mensagens
        messages = []
        async for msg in channel.history(limit=500, oldest_first=True):
            if msg.author.bot and not msg.content:
                continue
            messages.append({
                "author": msg.author.display_name,
                "author_id": msg.author.id,
                "content": msg.content or "[Embed/Anexo]",
                "timestamp": msg.created_at.strftime("%d/%m/%Y %H:%M")
            })
        
        # Montar conteúdo do transcript
        transcript_lines = []
        transcript_lines.append("=" * 60)
        transcript_lines.append("📜 TRANSCRIPT DO ATENDIMENTO")
        transcript_lines.append("=" * 60)
        transcript_lines.append(f"Ticket: {channel.name}")
        transcript_lines.append(f"Usuário: {ticket['opener_name']} (ID: {ticket['opener_id']})")
        transcript_lines.append(f"Tipo: {ticket['option_name']}")
        
        if ticket.get('assignee_name'):
            transcript_lines.append(f"Atendente: {ticket['assignee_name']} (ID: {ticket['assignee_id']})")
        
        transcript_lines.append(f"Criado em: {ticket.get('created_at', 'Desconhecido')}")
        transcript_lines.append(f"Fechado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        transcript_lines.append("=" * 60)
        transcript_lines.append("")
        
        for msg in messages:
            transcript_lines.append(f"[{msg['timestamp']}] {msg['author']}:")
            transcript_lines.append(f"  {msg['content']}")
            transcript_lines.append("")
        
        transcript_text = "\n".join(transcript_lines)
        
        # Criar arquivo
        transcript_file = discord.File(
            io.BytesIO(transcript_text.encode('utf-8')),
            filename=f"transcript-{channel.name}.txt"
        )
        
        # Montar embed da mensagem do transcript
        transcript_cfg = config.get('transcript_config', {}) if config else {}
        
        opener = channel.guild.get_member(ticket['opener_id'])
        if not opener:
            opener = await bot.fetch_user(ticket['opener_id'])
        
        embed = discord.Embed()
        
        if transcript_cfg.get('title'):
            embed.title = replace_variables(transcript_cfg['title'], user=opener, ticket_channel=channel, option_name=ticket['option_name'], guild=channel.guild)
        
        if transcript_cfg.get('description'):
            embed.description = replace_variables(transcript_cfg['description'], user=opener, ticket_channel=channel, option_name=ticket['option_name'], guild=channel.guild)
        
        if transcript_cfg.get('color'):
            try:
                embed.color = int(transcript_cfg['color'].replace('#', ''), 16)
            except:
                embed.color = discord.Color.blue()
        else:
            embed.color = discord.Color.blue()
        
        if transcript_cfg.get('banner'):
            embed.set_image(url=transcript_cfg['banner'])
        if transcript_cfg.get('thumbnail'):
            embed.set_thumbnail(url=transcript_cfg['thumbnail'])
        if transcript_cfg.get('footer') or transcript_cfg.get('footer_icon'):
            embed.set_footer(text=transcript_cfg.get('footer', ''), icon_url=transcript_cfg.get('footer_icon'))
        
        embed.add_field(name="📋 Ticket", value=channel.name, inline=True)
        embed.add_field(name="📊 Tipo", value=ticket['option_name'], inline=True)
        
        # Enviar por DM
        try:
            await opener.send(embed=embed, file=transcript_file)
        except Exception as e:
            print(f"Não foi possível enviar DM: {e}")
            # Avisar no canal que DM não foi possível
            try:
                warn_embed = discord.Embed(
                    description="⚠️ Não foi possível enviar o transcript por DM (DM fechada).",
                    color=discord.Color.orange()
                )
                await channel.send(embed=warn_embed)
            except:
                pass
    
    except Exception as e:
        print(f"Erro ao gerar transcript: {e}")

# ============================================================
# 📤 FUNÇÕES DO PAINEL PRINCIPAL
# ============================================================

async def enviar_painel_principal(channel):
    guild = channel.guild
    config = get_config(guild.id)
    
    embed = build_panel_embed(guild.id, "main")
    if not embed:
        embed = discord.Embed(
            title="🎫 Central de Atendimento",
            description="Selecione abaixo o tipo de atendimento que deseja abrir.",
            color=discord.Color.blue()
        )
    
    view = View(timeout=None)
    view.add_item(TicketSelect(guild.id))
    
    message = await channel.send(embed=embed, view=view)
    
    save_config(guild.id, panel_message_id=message.id)

async def atualizar_painel_principal(guild):
    config = get_config(guild.id)
    if not config or not config.get('panel_channel_id') or not config.get('panel_message_id'):
        return
    
    channel = guild.get_channel(config['panel_channel_id'])
    if not channel:
        return
    
    try:
        message = await channel.fetch_message(config['panel_message_id'])
    except:
        return
    
    embed = build_panel_embed(guild.id, "main")
    if not embed:
        embed = discord.Embed(
            title="🎫 Central de Atendimento",
            description="Selecione abaixo o tipo de atendimento que deseja abrir.",
            color=discord.Color.blue()
        )
    
    view = View(timeout=None)
    view.add_item(TicketSelect(guild.id))
    
    await message.edit(embed=embed, view=view)

# ============================================================
# ⏰ TASK DE INATIVIDADE
# ============================================================

@tasks.loop(minutes=5)
async def check_inactivity():
    for guild in bot.guilds:
        config = get_config(guild.id)
        if not config:
            continue
        
        minutes = config.get('inactivity_minutes', 0)
        if minutes == 0:
            continue
        
        inactive_tickets = get_inactive_tickets(guild.id, minutes)
        
        for ticket in inactive_tickets:
            channel = guild.get_channel(ticket['channel_id'])
            if not channel:
                continue
            
            # Avisar
            warn_embed = discord.Embed(
                title="⚠️ Aviso de Inatividade",
                description=f"Este ticket está inativo há mais de {minutes} minutos e será fechado automaticamente em breve.",
                color=discord.Color.orange()
            )
            await channel.send(embed=warn_embed)
            
            update_ticket(channel.id, notified_inactivity=1)
            
            # Esperar mais 5 minutos e fechar
            await asyncio.sleep(300)
            
            ticket_check = get_ticket(channel.id)
            if ticket_check and ticket_check['status'] == 'open':
                await confirmar_fechamento(None, channel)

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    ticket = get_ticket(message.channel.id)
    if ticket and ticket['status'] == 'open':
        update_ticket(message.channel.id, last_activity=datetime.now().isoformat(), notified_inactivity=0)

# ============================================================
# ⚡ COMANDO SLASH PRINCIPAL
# ============================================================

@bot.slash_command(name="tickets", description="Painel administrativo do sistema de tickets")
@commands.has_permissions(administrator=True)
async def tickets_admin(ctx):
    embed = discord.Embed(title="🎫 Painel Administrativo - Tickets", color=discord.Color.blue())
    embed.description = "Configure todo o sistema de tickets através dos botões abaixo:"
    
    embed.add_field(name="📋 Select Menu", value="Gerenciar opções do menu de atendimento", inline=False)
    embed.add_field(name="🎨 Personalização", value="Editar painéis principal, interno e transcript", inline=False)
    embed.add_field(name="⚙️ Configurações", value="Cargo, destinos, limites, inatividade", inline=False)
    
    view = AdminPanelView()
    await ctx.respond(embed=embed, view=view, ephemeral=True)

# ============================================================
# 🎉 EVENTOS
# ============================================================

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"🎫 Bot de Tickets Premium conectado!")
    print(f"🆔 {bot.user}")
    print(f"📍 Servidores: {len(bot.guilds)}")
    print("=" * 60)
    
    check_inactivity.start()
    
    print("\n✅ Bot pronto! Use /tickets para configurar")
    print("=" * 60)

# ============================================================
# 🚀 INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":
    import io
    init_db()
    print("💾 Banco de dados inicializado...")
    bot.run(BOT_TOKEN)
