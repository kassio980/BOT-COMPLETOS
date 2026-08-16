import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, Select, InputText
import sqlite3
import os
import asyncio
from datetime import datetime

# ============================================================
# 🔧 CONFIGURAÇÕES
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN_CLONAGEM", "SEU_TOKEN_AQUI")
PORT = int(os.environ.get("PORT", 5002))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)

# ============================================================
# 💾 BANCO DE DADOS
# ============================================================
DB_PATH = os.environ.get("DB_PATH_CLONAGEM", "bot_clonagem.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS clone_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        destination_guild_id INTEGER,
        source_guild_id INTEGER,
        source_guild_name TEXT,
        status TEXT DEFAULT 'pending',
        roles_cloned INTEGER DEFAULT 0,
        categories_cloned INTEGER DEFAULT 0,
        text_channels_cloned INTEGER DEFAULT 0,
        voice_channels_cloned INTEGER DEFAULT 0,
        emojis_cloned INTEGER DEFAULT 0,
        started_at TIMESTAMP,
        finished_at TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

def add_clone_log(dest_guild_id, source_guild_id, source_guild_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO clone_logs (destination_guild_id, source_guild_id, source_guild_name, started_at) VALUES (?, ?, ?, ?)",
              (dest_guild_id, source_guild_id, source_guild_name, datetime.now().isoformat()))
    log_id = c.lastrowid
    conn.commit()
    conn.close()
    return log_id

def update_clone_log(log_id, **kwargs):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
    values = list(kwargs.values()) + [log_id]
    c.execute(f"UPDATE clone_logs SET {fields} WHERE id = ?", values)
    conn.commit()
    conn.close()

# ============================================================
# 🎨 VIEWS E MODAIS
# ============================================================

# --- Modal ID Servidor de Origem ---
class SourceServerModal(Modal):
    def __init__(self, clone_options):
        super().__init__(title="Clonar Servidor")
        self.clone_options = clone_options
        self.add_item(InputText(
            label="ID do Servidor de Origem",
            placeholder="Cole o ID do servidor que deseja clonar",
            custom_id="source_id"
        ))
    
    async def callback(self, interaction: discord.Interaction):
        try:
            source_id = int(self.children[0].value)
        except:
            await interaction.response.send_message("❌ ID inválido! Use apenas números.", ephemeral=True)
            return
        
        source_guild = bot.get_guild(source_id)
        
        if not source_guild:
            await interaction.response.send_message(
                "❌ Não encontrei esse servidor!\n\n"
                "⚠️ O bot precisa estar **nos dois servidores** (origem e destino).\n"
                "Adicione o bot no servidor de origem primeiro e tente novamente.",
                ephemeral=True
            )
            return
        
        # Confirmar e iniciar clonagem
        embed = discord.Embed(title="🔍 Servidor Encontrado!", color=discord.Color.green())
        embed.add_field(name="Nome", value=source_guild.name, inline=True)
        embed.add_field(name="ID", value=str(source_guild.id), inline=True)
        embed.add_field(name="Membros", value=str(source_guild.member_count), inline=True)
        embed.add_field(name="Cargos", value=str(len(source_guild.roles)), inline=True)
        embed.add_field(name="Canais", value=str(len(source_guild.channels)), inline=True)
        embed.add_field(name="Emojis", value=str(len(source_guild.emojis)), inline=True)
        
        if source_guild.icon:
            embed.set_thumbnail(url=source_guild.icon.url)
        
        embed.add_field(
            name="📋 O que será clonado:",
            value="\n".join([f"✅ {opt}" for opt, val in self.clone_options.items() if val]),
            inline=False
        )
        
        view = ConfirmCloneView(source_guild, self.clone_options)
        await interaction.response.edit_message(embed=embed, view=view)

# --- View de Confirmação ---
class ConfirmCloneView(View):
    def __init__(self, source_guild, clone_options):
        super().__init__(timeout=120)
        self.source_guild = source_guild
        self.clone_options = clone_options
    
    @discord.ui.button(label="✅ Confirmar e Clonar", style=discord.ButtonStyle.green)
    async def confirm(self, button, interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Iniciar clonagem
        log_id = add_clone_log(interaction.guild.id, self.source_guild.id, self.source_guild.name)
        
        status_embed = discord.Embed(title="🔄 Clonagem em Andamento...", color=discord.Color.orange())
        status_embed.add_field(name="Origem", value=self.source_guild.name, inline=True)
        status_embed.add_field(name="Destino", value=interaction.guild.name, inline=True)
        status_embed.add_field(name="Status", value="⏳ Iniciando...", inline=False)
        
        status_msg = await interaction.followup.send(embed=status_embed, ephemeral=True)
        
        # Executar clonagem
        await executar_clonagem(
            interaction.guild,
            self.source_guild,
            self.clone_options,
            status_msg,
            log_id
        )
    
    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.red)
    async def cancel(self, button, interaction):
        embed = discord.Embed(title="❌ Clonagem Cancelada", color=discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=None)

# --- View Principal de Opções ---
class ClonePanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.options = {
            "Cargos": True,
            "Categorias": True,
            "Canais de Texto": True,
            "Canais de Voz": True,
            "Permissões": True,
            "Emojis": False
        }
    
    def atualizar_botoes(self):
        for child in self.children:
            if isinstance(child, Button) and child.custom_id and child.custom_id.startswith("opt_"):
                opt_name = child.custom_id.replace("opt_", "").replace("_", " ").title()
                opt_key = opt_name
                # Ajustar mapeamento
                mapeamento = {
                    "Cargos": "Cargos",
                    "Categorias": "Categorias",
                    "Canais De Texto": "Canais de Texto",
                    "Canais De Voz": "Canais de Voz",
                    "Permissoes": "Permissões",
                    "Emojis": "Emojis"
                }
                chave = mapeamento.get(opt_name, opt_name)
                
                if chave in self.options:
                    if self.options[chave]:
                        child.style = discord.ButtonStyle.green
                        child.label = f"✅ {chave}"
                    else:
                        child.style = discord.ButtonStyle.grey
                        child.label = f"⬜ {chave}"
    
    @discord.ui.button(label="✅ Cargos", style=discord.ButtonStyle.green, custom_id="opt_cargos")
    async def opt_cargos(self, button, interaction):
        self.options["Cargos"] = not self.options["Cargos"]
        self.atualizar_botoes()
        await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label="✅ Categorias", style=discord.ButtonStyle.green, custom_id="opt_categorias")
    async def opt_categorias(self, button, interaction):
        self.options["Categorias"] = not self.options["Categorias"]
        self.atualizar_botoes()
        await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label="✅ Canais de Texto", style=discord.ButtonStyle.green, custom_id="opt_canais_de_texto")
    async def opt_text(self, button, interaction):
        self.options["Canais de Texto"] = not self.options["Canais de Texto"]
        self.atualizar_botoes()
        await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label="✅ Canais de Voz", style=discord.ButtonStyle.green, custom_id="opt_canais_de_voz")
    async def opt_voice(self, button, interaction):
        self.options["Canais de Voz"] = not self.options["Canais de Voz"]
        self.atualizar_botoes()
        await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label="✅ Permissões", style=discord.ButtonStyle.green, custom_id="opt_permissoes")
    async def opt_perms(self, button, interaction):
        self.options["Permissões"] = not self.options["Permissões"]
        self.atualizar_botoes()
        await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label="⬜ Emojis", style=discord.ButtonStyle.grey, custom_id="opt_emojis")
    async def opt_emojis(self, button, interaction):
        self.options["Emojis"] = not self.options["Emojis"]
        self.atualizar_botoes()
        await interaction.response.edit_message(view=self)
    
    @discord.ui.button(label="🚀 Iniciar Clonagem", style=discord.ButtonStyle.blurple, custom_id="start_clone", emoji="🚀", row=2)
    async def start_clone(self, button, interaction):
        if not any(self.options.values()):
            await interaction.response.send_message("❌ Selecione pelo menos uma opção para clonar!", ephemeral=True)
            return
        
        modal = SourceServerModal(self.options.copy())
        await interaction.response.send_modal(modal)

# ============================================================
# 🔄 FUNÇÃO PRINCIPAL DE CLONAGEM
# ============================================================

async def executar_clonagem(dest_guild, source_guild, options, status_msg, log_id):
    stats = {"roles": 0, "categories": 0, "text": 0, "voice": 0, "emojis": 0}
    role_map = {}  # Mapear cargos antigos para novos
    category_map = {}  # Mapear categorias antigas para novas
    
    async def atualizar_status(etapa, detalhe=""):
        embed = discord.Embed(title="🔄 Clonagem em Andamento...", color=discord.Color.orange())
        embed.add_field(name="Origem", value=source_guild.name, inline=True)
        embed.add_field(name="Destino", value=dest_guild.name, inline=True)
        embed.add_field(name="📊 Progresso", value=f"Cargos: {stats['roles']} | Categorias: {stats['categories']}\nTexto: {stats['text']} | Voz: {stats['voice']} | Emojis: {stats['emojis']}", inline=False)
        embed.add_field(name="📍 Etapa Atual", value=f"**{etapa}**\n{detalhe}", inline=False)
        try:
            await status_msg.edit(embed=embed)
        except:
            pass
    
    try:
        # 1. Clonar Cargos
        if options.get("Cargos"):
            await atualizar_status("Clonando Cargos...")
            # Clonar de baixo para cima (evitar @everyone e bots primeiro)
            roles_to_clone = [r for r in source_guild.roles if not r.is_bot_managed() and r.name != "@everyone"]
            roles_to_clone.sort(key=lambda r: r.position)
            
            for role in roles_to_clone:
                try:
                    new_role = await dest_guild.create_role(
                        name=role.name,
                        permissions=role.permissions if options.get("Permissões") else discord.Permissions.none(),
                        colour=role.colour,
                        hoist=role.hoist,
                        mentionable=role.mentionable,
                        reason=f"Clonado de {source_guild.name}"
                    )
                    role_map[role.id] = new_role
                    stats["roles"] += 1
                    if stats["roles"] % 5 == 0:
                        await atualizar_status("Clonando Cargos...", f"{stats['roles']}/{len(roles_to_clone)} cargos")
                except Exception as e:
                    print(f"Erro ao clonar cargo {role.name}: {e}")
            
            await atualizar_status("Cargos Concluídos!", f"{stats['roles']} cargos clonados")
        
        # 2. Clonar Categorias
        if options.get("Categorias"):
            await atualizar_status("Clonando Categorias...")
            source_categories = sorted(source_guild.categories, key=lambda c: c.position)
            
            for cat in source_categories:
                try:
                    overwrites = {}
                    if options.get("Permissões"):
                        for target, perm in cat.overwrites.items():
                            if isinstance(target, discord.Role):
                                new_role = role_map.get(target.id)
                                if new_role:
                                    overwrites[new_role] = perm
                    
                    new_cat = await dest_guild.create_category(
                        name=cat.name,
                        overwrites=overwrites if overwrites else None,
                        reason=f"Clonado de {source_guild.name}"
                    )
                    category_map[cat.id] = new_cat
                    stats["categories"] += 1
                except Exception as e:
                    print(f"Erro ao clonar categoria {cat.name}: {e}")
            
            await atualizar_status("Categorias Concluídas!", f"{stats['categories']} categorias clonadas")
        
        # 3. Clonar Canais de Texto
        if options.get("Canais de Texto"):
            await atualizar_status("Clonando Canais de Texto...")
            text_channels = sorted(
                [c for c in source_guild.text_channels if not c.category],
                key=lambda c: c.position
            )
            # Primeiro canais fora de categoria
            for channel in text_channels:
                try:
                    overwrites = {}
                    if options.get("Permissões"):
                        for target, perm in channel.overwrites.items():
                            if isinstance(target, discord.Role):
                                new_role = role_map.get(target.id)
                                if new_role:
                                    overwrites[new_role] = perm
                    
                    await dest_guild.create_text_channel(
                        name=channel.name,
                        topic=channel.topic,
                        slowmode_delay=channel.slowmode_delay,
                        nsfw=channel.nsfw,
                        overwrites=overwrites if overwrites else None,
                        reason=f"Clonado de {source_guild.name}"
                    )
                    stats["text"] += 1
                except Exception as e:
                    print(f"Erro ao clonar canal {channel.name}: {e}")
            
            # Depois canais dentro de categorias
            for cat_id, new_cat in category_map.items():
                old_cat = source_guild.get_channel(cat_id)
                if old_cat:
                    cat_text_channels = sorted(old_cat.text_channels, key=lambda c: c.position)
                    for channel in cat_text_channels:
                        try:
                            overwrites = {}
                            if options.get("Permissões"):
                                for target, perm in channel.overwrites.items():
                                    if isinstance(target, discord.Role):
                                        new_role = role_map.get(target.id)
                                        if new_role:
                                            overwrites[new_role] = perm
                            
                            await new_cat.create_text_channel(
                                name=channel.name,
                                topic=channel.topic,
                                slowmode_delay=channel.slowmode_delay,
                                nsfw=channel.nsfw,
                                overwrites=overwrites if overwrites else None,
                                reason=f"Clonado de {source_guild.name}"
                            )
                            stats["text"] += 1
                        except Exception as e:
                            print(f"Erro ao clonar canal {channel.name}: {e}")
            
            await atualizar_status("Canais de Texto Concluídos!", f"{stats['text']} canais clonados")
        
        # 4. Clonar Canais de Voz
        if options.get("Canais de Voz"):
            await atualizar_status("Clonando Canais de Voz...")
            voice_channels = sorted(
                [c for c in source_guild.voice_channels if not c.category],
                key=lambda c: c.position
            )
            
            for channel in voice_channels:
                try:
                    overwrites = {}
                    if options.get("Permissões"):
                        for target, perm in channel.overwrites.items():
                            if isinstance(target, discord.Role):
                                new_role = role_map.get(target.id)
                                if new_role:
                                    overwrites[new_role] = perm
                    
                    await dest_guild.create_voice_channel(
                        name=channel.name,
                        bitrate=channel.bitrate,
                        user_limit=channel.user_limit,
                        overwrites=overwrites if overwrites else None,
                        reason=f"Clonado de {source_guild.name}"
                    )
                    stats["voice"] += 1
                except Exception as e:
                    print(f"Erro ao clonar voz {channel.name}: {e}")
            
            for cat_id, new_cat in category_map.items():
                old_cat = source_guild.get_channel(cat_id)
                if old_cat:
                    cat_voice_channels = sorted(old_cat.voice_channels, key=lambda c: c.position)
                    for channel in cat_voice_channels:
                        try:
                            overwrites = {}
                            if options.get("Permissões"):
                                for target, perm in channel.overwrites.items():
                                    if isinstance(target, discord.Role):
                                        new_role = role_map.get(target.id)
                                        if new_role:
                                            overwrites[new_role] = perm
                            
                            await new_cat.create_voice_channel(
                                name=channel.name,
                                bitrate=channel.bitrate,
                                user_limit=channel.user_limit,
                                overwrites=overwrites if overwrites else None,
                                reason=f"Clonado de {source_guild.name}"
                            )
                            stats["voice"] += 1
                        except Exception as e:
                            print(f"Erro ao clonar voz {channel.name}: {e}")
            
            await atualizar_status("Canais de Voz Concluídos!", f"{stats['voice']} canais clonados")
        
        # 5. Clonar Emojis
        if options.get("Emojis"):
            await atualizar_status("Clonando Emojis...")
            for emoji in source_guild.emojis:
                try:
                    emoji_bytes = await emoji.read()
                    await dest_guild.create_custom_emoji(
                        name=emoji.name,
                        image=emoji_bytes,
                        reason=f"Clonado de {source_guild.name}"
                    )
                    stats["emojis"] += 1
                    if stats["emojis"] % 10 == 0:
                        await atualizar_status("Clonando Emojis...", f"{stats['emojis']}/{len(source_guild.emojis)} emojis")
                except Exception as e:
                    print(f"Erro ao clonar emoji {emoji.name}: {e}")
            
            await atualizar_status("Emojis Concluídos!", f"{stats['emojis']} emojis clonados")
        
        # Finalizar
        update_clone_log(
            log_id,
            status="completed",
            roles_cloned=stats["roles"],
            categories_cloned=stats["categories"],
            text_channels_cloned=stats["text"],
            voice_channels_cloned=stats["voice"],
            emojis_cloned=stats["emojis"],
            finished_at=datetime.now().isoformat()
        )
        
        final_embed = discord.Embed(title="✅ Clonagem Concluída!", color=discord.Color.green())
        final_embed.add_field(name="Origem", value=source_guild.name, inline=True)
        final_embed.add_field(name="Destino", value=dest_guild.name, inline=True)
        final_embed.add_field(name="📊 Resultado", value=(
            f"👥 Cargos: **{stats['roles']}**\n"
            f"📁 Categorias: **{stats['categories']}**\n"
            f"💬 Canais de Texto: **{stats['text']}**\n"
            f"🔊 Canais de Voz: **{stats['voice']}**\n"
            f"😀 Emojis: **{stats['emojis']}**"
        ), inline=False)
        
        try:
            await status_msg.edit(embed=final_embed, view=None)
        except:
            pass
    
    except Exception as e:
        update_clone_log(log_id, status=f"error: {str(e)[:100]}", finished_at=datetime.now().isoformat())
        error_embed = discord.Embed(title="❌ Erro na Clonagem", color=discord.Color.red())
        error_embed.description = f"Ocorreu um erro durante a clonagem:\n```\n{str(e)[:500]}\n```"
        try:
            await status_msg.edit(embed=error_embed, view=None)
        except:
            pass

# ============================================================
# ⚡ COMANDOS SLASH
# ============================================================

@bot.slash_command(name="clonar", description="Abre o painel para clonar um servidor")
@commands.has_permissions(administrator=True)
async def clonar(ctx):
    embed = discord.Embed(title="🔄 Painel de Clonagem de Servidor", color=discord.Color.blue())
    embed.description = (
        "Selecione o que deseja clonar e depois clique em **Iniciar Clonagem**.\n\n"
        "⚠️ **Avisos importantes:**\n"
        "• O bot precisa estar **nos dois servidores** (origem e destino)\n"
        "• O bot precisa de permissão de **Administrador** no servidor de destino\n"
        "• Cargos, canais e permissões serão criados no servidor atual\n"
        "• Este bot opera **apenas a partir do servidor de destino**"
    )
    embed.add_field(name="📋 Opções Disponíveis", value="Marque/desmarque as opções abaixo:", inline=False)
    
    view = ClonePanelView()
    await ctx.respond(embed=embed, view=view, ephemeral=True)

@bot.slash_command(name="clone-historico", description="Mostra o histórico de clonagens deste servidor")
@commands.has_permissions(administrator=True)
async def clone_historico(ctx, limite: discord.Option(int, "Quantos mostrar", default=5, min_value=1, max_value=20)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM clone_logs WHERE destination_guild_id = ? ORDER BY id DESC LIMIT ?", (ctx.guild.id, limite))
    rows = c.fetchall()
    conn.close()
    
    embed = discord.Embed(title="📜 Histórico de Clonagens", color=discord.Color.blue())
    
    if not rows:
        embed.description = "Nenhuma clonagem registrada ainda."
    else:
        for row in rows:
            status_icon = "✅" if row[3] == "completed" else "❌" if row[3].startswith("error") else "⏳"
            texto = (
                f"**Origem:** {row[2]}\n"
                f"**Status:** {status_icon} {row[3]}\n"
                f"**Itens:** Cargos: {row[4]} | Cat: {row[5]} | Texto: {row[6]} | Voz: {row[7]} | Emojis: {row[8]}\n"
                f"**Data:** {row[9][:16] if row[9] else 'Desconhecida'}"
            )
            embed.add_field(name=f"#{row[0]}", value=texto, inline=False)
    
    await ctx.respond(embed=embed, ephemeral=True)

# ============================================================
# 🎉 EVENTOS
# ============================================================

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"🔄 Bot de Clonagem conectado!")
    print(f"🆔 {bot.user}")
    print(f"📍 Servidores: {len(bot.guilds)}")
    print("=" * 60)
    print("\n✅ Bot pronto! Use /clonar no servidor de destino")
    print("=" * 60)

# ============================================================
# 🚀 INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":
    init_db()
    print("💾 Banco de dados inicializado...")
    bot.run(BOT_TOKEN)
