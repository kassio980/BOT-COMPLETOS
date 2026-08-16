#!/bin/bash
# ============================================================
# 🐙 DEPLOY PARA GITHUB - 4 BOTS EM 1 SERVIÇO
# Repositório: https://github.com/kassio980/BOT-COMPLETOS.git
# ============================================================

clear
echo "============================================"
echo "  🐙 DEPLOY PARA GITHUB"
echo "============================================"
echo ""

# Verificar se está na pasta correta
if [ ! -f "main.py" ] || [ ! -d "bots" ]; then
    echo "❌ Execute este script dentro da pasta 4-BOTS-1-SERVICO!"
    exit 1
fi

# Inicializar git se não existir
if [ ! -d ".git" ]; then
    echo "📥 Inicializando repositório Git..."
    git init
    git branch -M main
else
    echo "✅ Repositório Git já existe"
fi

# Adicionar arquivos
echo ""
echo "📤 Adicionando arquivos..."
git add .
git status

echo ""
read -p "Digite uma mensagem para o commit (ou enter para padrão): " COMMIT_MSG
COMMIT_MSG=${COMMIT_MSG:-"4 Bots em 1 serviço - Atualização"}

git commit -m "$COMMIT_MSG"

# Configurar remote
echo ""
echo "🔗 Configurando repositório remoto..."
REPO_URL="https://github.com/kassio980/BOT-COMPLETOS.git"

if git remote get-url origin 2>/dev/null; then
    echo "🔄 Remote já existe, atualizando..."
    git remote set-url origin "$REPO_URL"
else
    git remote add origin "$REPO_URL"
fi

echo ""
echo "🚀 Enviando para o GitHub..."
echo ""
echo "⚠️  Você precisará fazer login no GitHub"
echo "   Use seu Token de Acesso Pessoal como senha"
echo ""

git push -u origin main

echo ""
echo "============================================"
if [ $? -eq 0 ]; then
    echo "  ✅ DEPLOY CONCLUÍDO COM SUCESSO!"
    echo ""
    echo "  📦 Repositório: $REPO_URL"
    echo ""
    echo "  🌐 Para hospedar no Render (UM ÚNICO SERVIÇO!):"
    echo "  1. Acesse https://render.com"
    echo "  2. New → Web Service"
    echo "  3. Conecte: kassio980/BOT-COMPLETOS"
    echo "  4. Build Command: pip install -r requirements.txt"
    echo "  5. Start Command: python main.py"
    echo "  6. Environment Variables: adicione os tokens dos bots desejados"
else
    echo "  ❌ ERRO NO DEPLOY"
    echo "  Verifique suas credenciais e se o repositório existe"
fi
echo "============================================"
