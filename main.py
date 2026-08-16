#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
========================================================================
        🚀 MAIN PRINCIPAL - 4 BOTS EM 1 ÚNICO SERVIÇO
========================================================================

Este arquivo executa os 4 bots simultaneamente em threads separadas
e também cria um servidor web para o health check do Render.

VARIÁVEIS DE AMBIENTE NECESSÁRIAS:
    BOT_TOKEN_TICKETS      = Token do Bot de Tickets
    BOT_TOKEN_BOAS_VINDAS  = Token do Bot de Boas Vindas
    BOT_TOKEN_CLONAGEM     = Token do Bot de Clonagem
    BOT_TOKEN              = Token do Bot de Vendas
    WEBHOOK_URL            = URL do webhook do Bot de Vendas
    PORT                   = Porta para o health check (fornecida pelo Render)

USO:
    python main.py
========================================================================
"""

import os
import sys
import threading
import asyncio
from aiohttp import web

print("=" * 70)
print("  🚀 INICIANDO 4 BOTS EM 1 ÚNICO SERVIÇO")
print("=" * 70)
print()

# ============================================================
# 🌐 SERVIDOR WEB PARA HEALTH CHECK DO RENDER
# ============================================================

async def health_check(request):
    return web.Response(text="✅ 4 Bots Online!", status=200, content_type="text/plain")

async def root_handler(request):
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>4 Bots Discord - Online</title></head>
    <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #2b2d31; color: white;">
        <h1>✅ 4 Bots Discord - Todos Online!</h1>
        <div style="margin-top: 30px; font-size: 18px;">
            <p>🎫 <strong>Bot Tickets</strong></p>
            <p>👋 <strong>Bot Boas Vindas</strong></p>
            <p>🔄 <strong>Bot Clonagem</strong></p>
            <p>💰 <strong>Bot Vendas</strong></p>
        </div>
        <p style="margin-top: 40px; color: #888;">Health check: /health</p>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")

async def start_web_server():
    PORT = int(os.environ.get("PORT", 5000))
    app = web.Application()
    app.router.add_get('/', root_handler)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"🌐 Servidor web rodando na porta {PORT}")
    print(f"   Health check: http://localhost:{PORT}/health")
    print()

# ============================================================
# 🤖 FUNÇÃO PARA EXECUTAR CADA BOT
# ============================================================

def run_bot_tickets():
    """Executa o Bot de Tickets Premium"""
    print("🎫 Iniciando Bot de Tickets...")
    token = os.environ.get("BOT_TOKEN_TICKETS", "")
    if not token or token == "SEU_TOKEN_AQUI":
        print("   ⚠️ BOT_TOKEN_TICKETS não configurado - Bot de Tickets NÃO iniciado")
        return
    
    # Modificar a variável de ambiente específica para este bot
    os.environ["BOT_TOKEN_TICKETS"] = token
    
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bots'))
    from bots import bot_tickets
    
    # Substituir o token no módulo
    bot_tickets.BOT_TOKEN = token
    
    try:
        bot_tickets.init_db()
        bot_tickets.bot.run(token)
    except Exception as e:
        print(f"   ❌ Erro Bot Tickets: {e}")

def run_bot_boas_vindas():
    """Executa o Bot de Boas Vindas & Invites"""
    print("👋 Iniciando Bot de Boas Vindas...")
    token = os.environ.get("BOT_TOKEN_BOAS_VINDAS", "")
    if not token or token == "SEU_TOKEN_AQUI":
        print("   ⚠️ BOT_TOKEN_BOAS_VINDAS não configurado - Bot Boas Vindas NÃO iniciado")
        return
    
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bots'))
    from bots import bot_boas_vindas
    
    bot_boas_vindas.BOT_TOKEN = token
    
    try:
        bot_boas_vindas.init_db()
        bot_boas_vindas.bot.run(token)
    except Exception as e:
        print(f"   ❌ Erro Bot Boas Vindas: {e}")

def run_bot_clonagem():
    """Executa o Bot de Clonagem"""
    print("🔄 Iniciando Bot de Clonagem...")
    token = os.environ.get("BOT_TOKEN_CLONAGEM", "")
    if not token or token == "SEU_TOKEN_AQUI":
        print("   ⚠️ BOT_TOKEN_CLONAGEM não configurado - Bot Clonagem NÃO iniciado")
        return
    
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bots'))
    from bots import bot_clonagem
    
    bot_clonagem.BOT_TOKEN = token
    
    try:
        bot_clonagem.init_db()
        bot_clonagem.bot.run(token)
    except Exception as e:
        print(f"   ❌ Erro Bot Clonagem: {e}")

def run_bot_vendas():
    """Executa o Bot de Vendas"""
    print("💰 Iniciando Bot de Vendas...")
    token = os.environ.get("BOT_TOKEN", "")
    if not token or token == "SEU_TOKEN_AQUI":
        print("   ⚠️ BOT_TOKEN não configurado - Bot de Vendas NÃO iniciado")
        return
    
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    os.environ["BOT_TOKEN"] = token
    if webhook_url:
        os.environ["WEBHOOK_URL"] = webhook_url
    
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bots'))
    from bots import bot_vendas
    
    bot_vendas.BOT_TOKEN = token
    
    try:
        bot_vendas.init_db()
        bot_vendas.bot.run(token)
    except Exception as e:
        print(f"   ❌ Erro Bot Vendas: {e}")

# ============================================================
# 🎬 EXECUÇÃO PRINCIPAL
# ============================================================

async def main():
    # Iniciar servidor web para health check
    await start_web_server()
    
    # Criar e iniciar threads para cada bot
    threads = [
        threading.Thread(target=run_bot_tickets, name="BotTickets", daemon=True),
        threading.Thread(target=run_bot_boas_vindas, name="BotBoasVindas", daemon=True),
        threading.Thread(target=run_bot_clonagem, name="BotClonagem", daemon=True),
        threading.Thread(target=run_bot_vendas, name="BotVendas", daemon=True),
    ]
    
    print()
    print("=" * 70)
    print("  🧵 Iniciando threads dos bots...")
    print("=" * 70)
    print()
    
    for t in threads:
        t.start()
        await asyncio.sleep(2)  # Pequeno intervalo entre cada inicialização
    
    print()
    print("=" * 70)
    print("  ✅ TODOS OS BOTS FORAM INICIADOS!")
    print("=" * 70)
    print()
    print("  📋 Bots configurados para iniciar:")
    print("     🎫 Bot Tickets")
    print("     👋 Bot Boas Vindas")
    print("     🔄 Bot Clonagem")
    print("     💰 Bot Vendas")
    print()
    print("  ⚠️  Bots sem token configurado não serão iniciados")
    print("  🌐 Servidor web de health check ativo na porta", os.environ.get("PORT", 5000))
    print("=" * 70)
    print()
    
    # Manter o main rodando
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Encerrando todos os bots...")
        sys.exit(0)
