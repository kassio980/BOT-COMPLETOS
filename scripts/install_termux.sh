#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# 📱 INSTALADOR TERMUX - 4 BOTS EM 1 SERVIÇO
# ============================================================

clear
echo "============================================"
echo "  🤖 INSTALADOR - 4 BOTS EM 1 SERVIÇO"
echo "============================================"
echo ""

# Atualizar sistema
echo "[1/5] Atualizando pacotes do Termux..."
pkg update -y && pkg upgrade -y

# Instalar dependências do sistema
echo ""
echo "[2/5] Instalando ferramentas do sistema..."
pkg install python git libjpeg-turbo libpng clang make openssh -y

# Atualizar pip
echo ""
echo "[3/5] Atualizando pip..."
pip install --upgrade pip

# Instalar dependências Python
echo ""
echo "[4/5] Instalando todas as dependências..."
pip install py-cord==2.5.0 requests==2.31.0 aiohttp==3.9.1 qrcode==7.4.2 Pillow==10.1.0

# Criar .env se não existir
echo ""
echo "[5/5] Preparando configurações..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "   ✅ Arquivo .env criado"
else
    echo "   ℹ️ Arquivo .env já existe"
fi

echo ""
echo "============================================"
echo "  ✅ INSTALAÇÃO CONCLUÍDA!"
echo "============================================"
echo ""
echo "📝 PRÓXIMOS PASSOS:"
echo ""
echo "1. Edite o arquivo .env com os tokens dos bots que deseja rodar:"
echo "   nano .env"
echo ""
echo "2. Inicie todos os bots:"
echo "   python main.py"
echo ""
echo "💡 Dica: Use 'tmux' para manter rodando em segundo plano"
echo "   pkg install tmux -y"
echo "   tmux new -s bots"
echo "   python main.py"
echo "   (CTRL+B depois D para sair sem fechar)"
echo "============================================"
