# 🤖 4 BOTS EM 1 ÚNICO SERVIÇO - Discord

Pacote com **4 bots completos** para Discord, **todos rodando em um ÚNICO serviço** no Render, GitHub ou Termux.

---

## ✅ Vantagens desta estrutura:

- **Apenas 1 hospedagem** no Render (economia)
- **Cada bot separado** e organizado em sua própria pasta
- **Fácil manutenção** - edite apenas o arquivo do bot desejado
- **Health check único** para todos os bots
- **Variáveis de ambiente separadas** para cada token

---

## 📦 Bots Inclusos (cada um em seu arquivo):

| Bot | Arquivo | Funcionalidades |
|-----|---------|----------------|
| 🎫 **Tickets Premium** | `bots/bot_tickets.py` | Atendimento por tickets, Select Menu, transcript por DM |
| 👋 **Boas Vindas & Invites** | `bots/bot_boas_vindas.py` | Mensagens de entrada/saída, sistema de invites |
| 🔄 **Clonagem** | `bots/bot_clonagem.py` | Clonar servidores (apenas do destino) |
| 💰 **Vendas** | `bots/bot_vendas.py` | Vendas via Pix real com API Assas |

---

## 🚀 Deploy no Render (1 ÚNICO SERVIÇO!)

1. Acesse https://render.com → **New** → **Web Service**
2. Conecte o repositório: `https://github.com/kassio980/BOT-COMPLETOS.git`
3. Configure:
   - **Name**: `4-bots-discord` (ou o nome que quiser)
   - **Root Directory**: `deixe vazio` (ou seja, a raiz)
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Plan**: Free ou Basic

4. Em **Environment Variables**, adicione os tokens dos bots que deseja rodar:

| Key | Value | Obrigatório? |
|-----|-------|-------------|
| `BOT_TOKEN_TICKETS` | token do bot de tickets | Não (se não colocar, este bot não inicia) |
| `BOT_TOKEN_BOAS_VINDAS` | token do bot de boas vindas | Não |
| `BOT_TOKEN_CLONAGEM` | token do bot de clonagem | Não |
| `BOT_TOKEN` | token do bot de vendas | Não |
| `WEBHOOK_URL` | url webhook do bot de vendas | Apenas para bot de vendas |

💡 **Você pode rodar apenas os bots que quiser!** Basta não adicionar a variável do bot que não quer usar.

---

## 📱 Rodar no Termux (Android)

```bash
# Extraia o ZIP e execute:
cd 4-BOTS-1-SERVICO
bash scripts/install_termux.sh
```

Ou manualmente:
```bash
# Edite o arquivo .env com os tokens dos bots que deseja rodar
pip install -r requirements.txt
python main.py
```

---

## 🐙 Subir para o GitHub

```bash
cd 4-BOTS-1-SERVICO
bash scripts/deploy_github.sh
```

Repositório alvo: `https://github.com/kassio980/BOT-COMPLETOS.git`

---

## ⚡ Comandos de Cada Bot

| Bot | Comando |
|-----|---------|
| 🎫 Tickets | `/tickets` |
| 👋 Boas Vindas | `/boasvindas` |
| 🔄 Clonagem | `/clonar` |
| 💰 Vendas | `/painel vendas` |

---

## 📁 Estrutura Completa

```
4-BOTS-1-SERVICO/
├── main.py                  # 🚀 Arquivo principal (executa os 4 bots + web server)
├── requirements.txt         # 📦 Dependências únicas
├── Procfile                 # 🎯 Comando inicialização Render
├── runtime.txt              # 🐍 Versão Python
├── .env.example             # 🔧 Exemplo de variáveis de ambiente
├── .gitignore               # 🙈 Arquivos ignorados
├── bots/                    # � Cada bot separado aqui
│   ├── __init__.py
│   ├── bot_tickets.py       # 🎫 Tickets Premium
│   ├── bot_boas_vindas.py   # 👋 Boas Vindas & Invites
│   ├── bot_clonagem.py      # 🔄 Clonagem de Servidor
│   └── bot_vendas.py        # 💰 Bot de Vendas
├── scripts/
│   ├── install_termux.sh    # 📱 Instalador Termux
│   └── deploy_github.sh     # 🐙 Deploy GitHub
└── README.md                # 📖 Este arquivo
```

---

## ⚙️ Como funciona o `main.py`?

1. Cria um **servidor web** na porta fornecida pelo Render (para health check)
2. Cria uma **thread separada** para cada bot
3. Cada bot roda independentemente dos outros
4. Se um bot cair, os outros continuam funcionando
5. Bots sem token configurado simplesmente não iniciam (sem erros)

---

## ⚠️ Avisos Importantes

1. **Cada bot precisa de seu próprio token** no Discord Developers
2. **Bot de Vendas** precisa de conta na Assas + webhook
3. **Bot de Clonagem** precisa estar nos dois servidores (origem e destino)
4. Plano Free do Render dorme após 15min → use cron-job.org para fazer ping em `/health`
5. Todos os bots usam **py-cord**
