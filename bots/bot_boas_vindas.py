import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, Select, InputText
import sqlite3
import os
from datetime import datetime

# ============================================================
# 🔧 CONFIGURAÇÕES
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN_BOAS_VINDAS", "SEU_TOKEN_AQUI")
PORT = int(os.environ.get("PORT", 5001))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)

# ============================================================
# 💾 BANCO DE DADOS
# ============================================================
DB_PATH = os.environ.get("DB_PATH_BOAS_VINDAS", "bot_boas_vindas.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS config (
        guild_id INTEGER PRIMARY KEY,
        welcome_channel_id INTEGER,
        leave_channel_id INTEGER,
        welcome_message TEXT,
        leave_message TEXT,
        welcome_image TEXT,
        leave_image TEXT,
        ping_user INTEGER DEFAULT 1,
        ping_role_id INTEGER
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS invites (
        code TEXT PRIMARY KEY,
        guild_id INTEGER,
        inviter_id INTEGER,
        uses INTEGER DEFAULT 0,
        max_uses INTEGER DEFAULT 0,
        created_at TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS members (
        member_id INTEGER,
        guild_id INTEGER,
        inviter_id INTEGER,
        invite_code TEXT,
        joined_at TIMESTAMP,
        left_at TIMESTAMP,
        is_fake INTEGER DEFAULT 0,
        is_left INTEGER DEFAULT 0,
        PRIMARY KEY (member_id, guild_id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS invite_cache (
        guild_id INTEGER PRIMARY KEY,
        invites_data TEXT
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
            "welcome_channel_id": row[1],
            "leave_channel_id": row[2],
            "welcome_message": row[3],
            "leave_message": row[4],
            "welcome_image": row[5],
            "leave_image": row[6],
            "ping_user": row[7],
            "ping_role_id": row[8]
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

def cache_invites(guild_id, invites_data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    import json
    c.execute("INSERT OR REPLACE INTO invite_cache (guild_id, invites_data) VALUES (?, ?)",
              (guild_id, json.dumps(invites_data)))
    conn.commit()
    conn.close()

def get_cached_invites(guild_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT invites_data FROM invite_cache WHERE guild_id = ?", (guild_id,))
    row = c.fetchone()
    conn.close()
    if row:
        import json
        return json.loads(row[0])
    return {}

def add_member(member_id, guild_id, inviter_id, invite_code):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Verificar se já entrou antes
    c.execute("SELECT * FROM members WHERE member_id = ? AND guild_id = ?", (member_id, guild_id))
    existing = c.fetchone()
    
    if existing:
        # Já entrou antes - marcar como não saiu mais, NÃO contar como novo invite válido
        c.execute("UPDATE members SET left_at = NULL, is_left = 0, invite_code = ?, inviter_id = ?, joined_at = ? WHERE member_id = ? AND guild_id = ?",
                  (invite_code, inviter_id, datetime.now().isoformat(), member_id, guild_id))
        is_returning = True
    else:
        c.execute("INSERT INTO members (member_id, guild_id, inviter_id, invite_code, joined_at) VALUES (?, ?, ?, ?, ?)",
                  (member_id, guild_id, inviter_id, invite_code, datetime.now().isoformat()))
        is_returning = False
    
    conn.commit()
    conn.close()
    return is_returning

def mark_member_left(member_id, guild_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE members SET left_at = ?, is_left = 1 WHERE member_id = ? AND guild_id = ?",
              (datetime.now().isoformat(), member_id, guild_id))
    conn.commit()
    conn.close()

def get_member_info(member_id, guild_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM members WHERE member_id = ? AND guild_id = ?", (member_id, guild_id))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "member_id": row[0],
            "guild_id": row[1],
            "inviter_id": row[2],
            "invite_code": row[3],
            "joined_at": row[4],
            "left_at": row[5],
            "is_fake": row[6],
            "is_left": row[7]
        }
    return None

def get_invites_stats(inviter_id, guild_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Total de pessoas convidadas
    c.execute("SELECT COUNT(*) FROM members WHERE inviter_id = ? AND guild_id = ? AND is_fake = 0", (inviter_id, guild_id))
    total = c.fetchone()[0]
    
    # Pessoas que saíram
    c.execute("SELECT COUNT(*) FROM members WHERE inviter_id = ? AND guild_id = ? AND is_left = 1 AND is_fake = 0", (inviter_id, guild_id))
    left = c.fetchone()[0]
    
    # Contas falsas
    c.execute("SELECT COUNT(*) FROM members WHERE inviter_id = ? AND guild_id = ? AND is_fake = 1", (inviter_id, guild_id))
    fake = c.fetchone()[0]
    
    # Válidos (não saíram e não são falsos)
    c.execute("SELECT COUNT(*) FROM members WHERE inviter_id = ? AND guild_id = ? AND is_left = 0 AND is_fake = 0", (inviter_id, guild_id))
    valid = c.fetchone()[0]
    
    conn.close()
    
    return {
        "total": total,
        "left": left,
        "fake": fake,
        "valid": valid
    }

def reset_invites(inviter_id, guild_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Marcar todos os invites dessa pessoa como fake para resetar as estatísticas
    c.execute("UPDATE members SET is_fake = 1 WHERE inviter_id = ? AND guild_id = ?", (inviter_id, guild_id))
    conn.commit()
    conn.close()

# ============================================================
# 🎨 VIEWS E MODAIS
# ============================================================

# --- Painel Principal de Configuração ---
class ConfigPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="📨 Canal de Boas Vindas", style=discord.ButtonStyle.green, custom_id="cfg_welcome_channel")
    async def welcome_channel(self, button, interaction):
        view = ChannelSelectView("welcome")
        await interaction.response.send_message("Escolha o canal de boas vindas:", view=view, ephemeral=True)
    
    @discord.ui.button(label="👋 Canal de Saída", style=discord.ButtonStyle.red, custom_id="cfg_leave_channel")
    async def leave_channel(self, button, interaction):
        view = ChannelSelectView("leave")
        await interaction.response.send_message("Escolha o canal de saída:", view=view, ephemeral=True)
    
    @discord.ui.button(label="✏️ Mensagem de Boas Vindas", style=discord.ButtonStyle.blurple, custom_id="cfg_welcome_msg")
    async def welcome_msg(self, button, interaction):
        modal = WelcomeMessageModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="✏️ Mensagem de Saída", style=discord.ButtonStyle.blurple, custom_id="cfg_leave_msg")
    async def leave_msg(self, button, interaction):
        modal = LeaveMessageModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🖼️ Imagem de Boas Vindas", style=discord.ButtonStyle.secondary, custom_id="cfg_welcome_img")
    async def welcome_img(self, button, interaction):
        modal = WelcomeImageModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="🖼️ Imagem de Saída", style=discord.ButtonStyle.secondary, custom_id="cfg_leave_img")
    async def leave_img(self, button, interaction):
        modal = LeaveImageModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⚙️ Outras Opções", style=discord.ButtonStyle.grey, custom_id="cfg_other")
    async def other_options(self, button, interaction):
        view = OtherOptionsView()
        await interaction.response.send_message("Outras opções de configuração:", view=view, ephemeral=True)

# --- Select de Canal ---
class ChannelSelect(Select):
    def __init__(self, config_type):
        self.config_type = config_type
        super().__init__(placeholder="Selecione um canal...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        channel = interaction.guild.get_channel(channel_id)
        
        if self.config_type == "welcome":
            save_config(interaction.guild_id, welcome_channel_id=channel_id)
            await interaction.response.send_message(f"✅ Canal de boas vindas configurado: {channel.mention}", ephemeral=True)
        elif self.config_type == "leave":
            save_config(interaction.guild_id, leave_channel_id=channel_id)
            await interaction.response.send_message(f"✅ Canal de saída configurado: {channel.mention}", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = []
        for channel in interaction.guild.text_channels:
            if len(options) < 25:
                options.append(discord.SelectOption(label=f"#{channel.name}", value=str(channel.id)))
        self.options = options

class ChannelSelectView(View):
    def __init__(self, config_type):
        super().__init__(timeout=120)
        self.add_item(ChannelSelect(config_type))

# --- Modais de Mensagem ---
class WelcomeMessageModal(Modal):
    def __init__(self):
        super().__init__(title="Mensagem de Boas Vindas")
        self.add_item(InputText(
            label="Mensagem",
            placeholder="Use {user} para mencionar, {server} para nome do servidor, {inviter} para quem convidou",
            style=discord.InputTextStyle.long,
            custom_id="msg",
            value="Olá {user}! Bem-vindo(a) ao **{server}**!\n\nConvidado por: {inviter}"
        ))
    
    async def callback(self, interaction: discord.Interaction):
        msg = self.children[0].value
        save_config(interaction.guild_id, welcome_message=msg)
        await interaction.response.send_message("✅ Mensagem de boas vindas configurada!", ephemeral=True)

class LeaveMessageModal(Modal):
    def __init__(self):
        super().__init__(title="Mensagem de Saída")
        self.add_item(InputText(
            label="Mensagem",
            placeholder="Use {user} para nome, {server} para nome do servidor",
            style=discord.InputTextStyle.long,
            custom_id="msg",
            value="**{user}** saiu do servidor **{server}**. Até logo! 👋"
        ))
    
    async def callback(self, interaction: discord.Interaction):
        msg = self.children[0].value
        save_config(interaction.guild_id, leave_message=msg)
        await interaction.response.send_message("✅ Mensagem de saída configurada!", ephemeral=True)

# --- Modais de Imagem ---
class WelcomeImageModal(Modal):
    def __init__(self):
        super().__init__(title="Imagem de Boas Vindas")
        self.add_item(InputText(
            label="URL da Imagem",
            placeholder="https://exemplo.com/imagem.png",
            custom_id="url"
        ))
    
    async def callback(self, interaction: discord.Interaction):
        url = self.children[0].value
        save_config(interaction.guild_id, welcome_image=url)
        await interaction.response.send_message("✅ Imagem de boas vindas configurada!", ephemeral=True)

class LeaveImageModal(Modal):
    def __init__(self):
        super().__init__(title="Imagem de Saída")
        self.add_item(InputText(
            label="URL da Imagem",
            placeholder="https://exemplo.com/imagem.png",
            custom_id="url"
        ))
    
    async def callback(self, interaction: discord.Interaction):
        url = self.children[0].value
        save_config(interaction.guild_id, leave_image=url)
        await interaction.response.send_message("✅ Imagem de saída configurada!", ephemeral=True)

# --- Outras Opções ---
class OtherOptionsView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="🔔 Pingar Usuário: SIM", style=discord.ButtonStyle.green, custom_id="toggle_ping")
    async def toggle_ping(self, button, interaction):
        config = get_config(interaction.guild_id)
        current = config.get('ping_user', 1) if config else 1
        new_value = 0 if current == 1 else 1
        save_config(interaction.guild_id, ping_user=new_value)
        
        if new_value == 1:
            button.label = "🔔 Pingar Usuário: SIM"
            button.style = discord.ButtonStyle.green
        else:
            button.label = "🔕 Pingar Usuário: NÃO"
            button.style = discord.ButtonStyle.red
        
        await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label="👑 Cargo de Ping", style=discord.ButtonStyle.blurple, custom_id="ping_role")
    async def ping_role(self, button, interaction):
        view = RoleSelectView()
        await interaction.response.send_message("Escolha um cargo para pingar (ou nenhum):", view=view, ephemeral=True)
    
    @discord.ui.button(label="👁️ Ver Configurações", style=discord.ButtonStyle.secondary, custom_id="view_config")
    async def view_config(self, button, interaction):
        config = get_config(interaction.guild_id)
        
        if not config:
            await interaction.response.send_message("Nenhuma configuração salva ainda.", ephemeral=True)
            return
        
        embed = discord.Embed(title="⚙️ Configurações Atuais", color=discord.Color.blue())
        
        welcome_ch = interaction.guild.get_channel(config['welcome_channel_id']) if config['welcome_channel_id'] else None
        leave_ch = interaction.guild.get_channel(config['leave_channel_id']) if config['leave_channel_id'] else None
        ping_role = interaction.guild.get_role(config['ping_role_id']) if config['ping_role_id'] else None
        
        embed.add_field(name="📨 Canal Boas Vindas", value=welcome_ch.mention if welcome_ch else "Não configurado", inline=True)
        embed.add_field(name="👋 Canal Saída", value=leave_ch.mention if leave_ch else "Não configurado", inline=True)
        embed.add_field(name="🔔 Pingar Usuário", value="✅ Sim" if config.get('ping_user', 1) else "❌ Não", inline=True)
        embed.add_field(name="👑 Cargo Ping", value=ping_role.mention if ping_role else "Nenhum", inline=True)
        embed.add_field(name="🖼️ Imagem Boas Vindas", value="✅ Configurada" if config.get('welcome_image') else "❌ Não", inline=True)
        embed.add_field(name="🖼️ Imagem Saída", value="✅ Configurada" if config.get('leave_image') else "❌ Não", inline=True)
        
        if config.get('welcome_message'):
            embed.add_field(name="✏️ Mensagem Boas Vindas", value=config['welcome_message'][:1024], inline=False)
        if config.get('leave_message'):
            embed.add_field(name="✏️ Mensagem Saída", value=config['leave_message'][:1024], inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# --- Select de Cargo ---
class RoleSelect(Select):
    def __init__(self):
        super().__init__(placeholder="Selecione um cargo...", min_values=1, max_values=1, options=[])
    
    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.values[0])
        save_config(interaction.guild_id, ping_role_id=role_id)
        role = interaction.guild.get_role(role_id)
        await interaction.response.send_message(f"✅ Cargo de ping configurado: {role.mention}", ephemeral=True)
    
    async def before_invocation(self, interaction: discord.Interaction):
        options = [discord.SelectOption(label="❌ Nenhum cargo", value="0")]
        for role in interaction.guild.roles:
            if not role.is_bot_managed() and role != interaction.guild.default_role and len(options) < 25:
                options.append(discord.SelectOption(label=role.name, value=str(role.id)))
        self.options = options

class RoleSelectView(View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(RoleSelect())

# ============================================================
# ⚡ COMANDOS SLASH
# ============================================================

@bot.slash_command(name="boasvindas", description="Painel de configuração do sistema de boas vindas")
@commands.has_permissions(administrator=True)
async def painel_boas_vindas(ctx):
    embed = discord.Embed(title="🎛️ Painel - Boas Vindas & Invites", color=discord.Color.blue())
    embed.description = "Configure todas as opções do sistema de boas vindas abaixo:"
    embed.add_field(name="📨 Canais", value="Configure os canais de entrada e saída", inline=False)
    embed.add_field(name="✏️ Mensagens", value="Personalize as mensagens de boas vindas e saída", inline=False)
    embed.add_field(name="🖼️ Imagens", value="Adicione imagens/banners às mensagens", inline=False)
    
    view = ConfigPanelView()
    await ctx.respond(embed=embed, view=view, ephemeral=True)

@bot.slash_command(name="invites", description="Mostra estatísticas de invites de um usuário")
async def invites(ctx, usuario: discord.Option(discord.Member, "Escolha o usuário", required=False)):
    member = usuario or ctx.author
    
    stats = get_invites_stats(member.id, ctx.guild.id)
    member_info = get_member_info(member.id, ctx.guild.id)
    
    inviter_mention = "Desconhecido"
    if member_info and member_info.get('inviter_id'):
        inviter = ctx.guild.get_member(member_info['inviter_id'])
        if inviter:
            inviter_mention = inviter.mention
    
    embed = discord.Embed(title=f"📊 Convites de {member.display_name}", color=discord.Color.blue())
    embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
    
    embed.add_field(name="✅ Válidos", value=str(stats['valid']), inline=True)
    embed.add_field(name="👋 Saíram", value=str(stats['left']), inline=True)
    embed.add_field(name="⚠️ Falsos/Resetados", value=str(stats['fake']), inline=True)
    embed.add_field(name="📊 Total Geral", value=f"**{stats['total']}**", inline=True)
    
    if member_info:
        embed.add_field(name="👤 Convidado por", value=inviter_mention, inline=False)
        embed.add_field(name="📅 Entrou em", value=member_info.get('joined_at', 'Desconhecido')[:10] if member_info.get('joined_at') else 'Desconhecido', inline=True)
    
    embed.set_footer(text=f"ID: {member.id}")
    
    await ctx.respond(embed=embed)

@bot.slash_command(name="reseta", description="Reseta os invites de um usuário")
@commands.has_permissions(administrator=True)
async def reseta_invites(ctx, usuario: discord.Option(discord.Member, "Escolha o usuário")):
    stats_before = get_invites_stats(usuario.id, ctx.guild.id)
    reset_invites(usuario.id, ctx.guild.id)
    stats_after = get_invites_stats(usuario.id, ctx.guild.id)
    
    embed = discord.Embed(title="🔄 Invites Resetados", color=discord.Color.orange())
    embed.add_field(name="👤 Usuário", value=usuario.mention, inline=False)
    embed.add_field(name="📊 Antes", value=f"Válidos: {stats_before['valid']} | Total: {stats_before['total']}", inline=True)
    embed.add_field(name="📊 Depois", value=f"Válidos: {stats_after['valid']} | Total: {stats_after['total']}", inline=True)
    
    await ctx.respond(embed=embed)

@bot.slash_command(name="topinvites", description="Mostra o ranking de invites do servidor")
async def top_invites(ctx, limite: discord.Option(int, "Quantos mostrar", default=10, min_value=1, max_value=20)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""
        SELECT inviter_id, COUNT(*) as total 
        FROM members 
        WHERE guild_id = ? AND is_left = 0 AND is_fake = 0 AND inviter_id IS NOT NULL
        GROUP BY inviter_id 
        ORDER BY total DESC 
        LIMIT ?
    """, (ctx.guild.id, limite))
    
    rows = c.fetchall()
    conn.close()
    
    embed = discord.Embed(title=f"🏆 Top {limite} Convites", color=discord.Color.gold())
    
    if not rows:
        embed.description = "Nenhum invite registrado ainda."
    else:
        texto = ""
        medals = ["🥇", "🥈", "🥉"]
        for i, (inviter_id, total) in enumerate(rows):
            member = ctx.guild.get_member(inviter_id)
            nome = member.display_name if member else f"ID: {inviter_id}"
            medal = medals[i] if i < 3 else f"`#{i+1}`"
            texto += f"{medal} **{nome}** — {total} invites\n"
        
        embed.description = texto
    
    await ctx.respond(embed=embed)

# ============================================================
# 🎉 EVENTOS - BOAS VINDAS E SAÍDA
# ============================================================

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"👋 Bot Boas Vindas & Invites conectado!")
    print(f"🆔 {bot.user}")
    print("=" * 60)
    
    # Cachear invites de todos os servidores
    for guild in bot.guilds:
        try:
            invites = await guild.invites()
            invites_data = {inv.code: inv.uses for inv in invites}
            cache_invites(guild.id, invites_data)
            print(f"  📥 Invites cacheados para: {guild.name}")
        except:
            pass
    
    print("\n✅ Bot pronto!")
    print("=" * 60)

@bot.event
async def on_guild_join(guild):
    try:
        invites = await guild.invites()
        invites_data = {inv.code: inv.uses for inv in invites}
        cache_invites(guild.id, invites_data)
    except:
        pass

@bot.event
async def on_invite_create(invite):
    cached = get_cached_invites(invite.guild.id)
    cached[invite.code] = invite.uses
    cache_invites(invite.guild.id, cached)

@bot.event
async def on_invite_delete(invite):
    cached = get_cached_invites(invite.guild.id)
    if invite.code in cached:
        del cached[invite.code]
        cache_invites(invite.guild.id, cached)

@bot.event
async def on_member_join(member):
    if member.bot:
        return
    
    guild = member.guild
    config = get_config(guild.id)
    
    # Descobrir qual invite foi usado
    inviter = None
    invite_code = None
    is_returning = False
    
    try:
        new_invites = await guild.invites()
        new_invites_data = {inv.code: inv.uses for inv in new_invites}
        old_invites_data = get_cached_invites(guild.id)
        
        for code, uses in new_invites_data.items():
            old_uses = old_invites_data.get(code, 0)
            if uses > old_uses:
                for inv in new_invites:
                    if inv.code == code and inv.inviter:
                        inviter = inv.inviter
                        invite_code = code
                        break
                break
        
        # Atualizar cache
        cache_invites(guild.id, new_invites_data)
    except:
        pass
    
    # Registrar entrada
    if inviter:
        is_returning = add_member(member.id, guild.id, inviter.id, invite_code)
    else:
        add_member(member.id, guild.id, None, None)
    
    # Enviar mensagem de boas vindas
    if config and config.get('welcome_channel_id'):
        channel = guild.get_channel(config['welcome_channel_id'])
        if channel:
            msg_template = config.get('welcome_message') or "Olá {user}! Bem-vindo(a) ao **{server}**!"
            
            inviter_mention = inviter.mention if inviter else "Desconhecido"
            mensagem = msg_template.replace("{user}", member.mention).replace("{server}", guild.name).replace("{inviter}", inviter_mention)
            
            embed = discord.Embed(color=discord.Color.green())
            
            if config.get('ping_user', 1):
                embed.description = mensagem
            else:
                embed.description = mensagem.replace(member.mention, f"**{member.display_name}**")
            
            embed.set_author(name=f"{member.display_name} entrou no servidor!", icon_url=member.avatar.url if member.avatar else None)
            
            if config.get('welcome_image'):
                embed.set_image(url=config['welcome_image'])
            
            embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
            embed.set_footer(text=f"ID: {member.id} | Membro #{guild.member_count}")
            
            content = ""
            if config.get('ping_user', 1):
                content = member.mention
            if config.get('ping_role_id'):
                role = guild.get_role(config['ping_role_id'])
                if role:
                    content += f" {role.mention}"
            
            if is_returning:
                embed.add_field(name="ℹ️ Observação", value="Este usuário já esteve no servidor antes. Convite não contabilizado como novo.", inline=False)
            
            await channel.send(content=content.strip() if content.strip() else None, embed=embed)

@bot.event
async def on_member_remove(member):
    if member.bot:
        return
    
    guild = member.guild
    config = get_config(guild.id)
    
    # Marcar como saiu
    mark_member_left(member.id, guild.id)
    
    # Enviar mensagem de saída
    if config and config.get('leave_channel_id'):
        channel = guild.get_channel(config['leave_channel_id'])
        if channel:
            msg_template = config.get('leave_message') or "**{user}** saiu do servidor **{server}**. 👋"
            mensagem = msg_template.replace("{user}", member.display_name).replace("{server}", guild.name)
            
            embed = discord.Embed(color=discord.Color.red())
            embed.description = mensagem
            embed.set_author(name=f"{member.display_name} saiu do servidor", icon_url=member.avatar.url if member.avatar else None)
            
            if config.get('leave_image'):
                embed.set_image(url=config['leave_image'])
            
            embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
            
            # Verificar quem convidou
            member_info = get_member_info(member.id, guild.id)
            if member_info and member_info.get('inviter_id'):
                inviter = guild.get_member(member_info['inviter_id'])
                if inviter:
                    embed.add_field(name="👤 Convidado por", value=inviter.mention, inline=True)
            
            await channel.send(embed=embed)

# ============================================================
# 🚀 INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":
    init_db()
    print("💾 Banco de dados inicializado...")
    bot.run(BOT_TOKEN)
