# ViralCut AI v2.0 + Agente Dark Autônomo — Manual Completo

O sistema trabalha em piloto automático para você: o **PC Windows** pesquisa tendências virais, escreve o roteiro com Gemini, narra com voz neural gratuita (Edge-TTS), monta o vídeo 9:16 com legendas dinâmicas e posta no YouTube Shorts. O **APK Android** é o seu controle remoto com aprovação em 1 clique.

---

## Conteúdo do Pacote

```
ViralCut-AI/
├── MANUAL_INSTALACAO.md
├── videos/
│   ├── 01_DEMO_FUNCIONAMENTO_APP.mp4      -> demonstração visual do app completo
│   └── 02_VIDEO_INSTRUCAO_INSTALACAO.mp4  -> vídeo passo a passo de instalação
├── servidor/                              -> copie para C:\ViralCut-Server
│   ├── server.py                          API principal (Cortes + Agente Dark)
│   ├── agente_dark.py                     Agente pesquisador, roteirista e editor
│   ├── youtube_uploader.py                Upload automático no YouTube Shorts
│   ├── iniciar.bat                        Liga o servidor (coloque sua chave Gemini)
│   ├── instalar_dependencias.bat          Instala tudo com 2 cliques
│   ├── conectar_youtube.bat               Autoriza seu canal do YouTube (1 única vez)
│   ├── requirements.txt                   Lista de bibliotecas Python
│   └── musicas/                           Coloque MP3s de fundo aqui (opcional)
└── viralcut-android/                      -> suba para o GitHub para gerar o APK
    ├── www/index.html                     Interface do app (4 abas + Agente Dark)
    ├── package.json                       Capacitor 6
    ├── capacitor.config.json              HTTP local liberado
    └── .github/workflows/build-apk.yml    Compila o APK automaticamente na nuvem
```

---

## PASSO 1 — Instalar o Servidor no Windows

1. **Instale o Python 3.10+** em `python.org` (marque **"Add python.exe to PATH"**).
2. **Instale o FFmpeg** abrindo o Prompt de Comando (CMD):
   ```cmd
   winget install Gyan.FFmpeg
   ```
   Feche e abra o terminal novamente.
3. **Copie a pasta `servidor`** para `C:\ViralCut-Server`.
4. **Dê dois cliques em `instalar_dependencias.bat`** e aguarde concluir.
5. **Crie sua chave gratuita do Gemini** em `aistudio.google.com` (*Get API key > Create API key*).
6. **Edite `iniciar.bat`** no Bloco de Notas e substitua `AIzaSy_SUA_CHAVE_AQUI` pela sua chave.
   - *(Opcional)* Para vídeos reais de fundo em vez do fundo cinematográfico Dark, crie uma chave grátis em `pexels.com/api` e cole em `PEXELS_API_KEY=` (ou direto dentro do app).
7. **Libere a porta 8000 no Firewall** (PowerShell como Administrador):
   ```powershell
   New-NetFirewallRule -DisplayName "ViralCut Server" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
   ```
8. **Descubra o IP do PC** rodando `ipconfig` no CMD (anote o **Endereço IPv4**, ex.: `192.168.1.15`).
9. **Dê dois cliques em `iniciar.bat`**. O servidor estará online em `http://SEU_IP:8000`.

---

## PASSO 2 — Gerar e Instalar o APK no Android (via GitHub Actions)

1. Crie um repositório no GitHub (ex: `viralcut-dark`).
2. Suba **todo o conteúdo** da pasta `viralcut-android` para a branch `main` (incluindo a pasta oculta `.github`).
   - Dica: se usar Termux no celular, basta entrar na pasta e dar `git push -u origin main`.
3. Acesse a aba **Actions** do repositório no GitHub. O workflow **Build ViralCut APK** compila o APK em ~3 minutos.
4. Ao ficar verde, clique na execução, role até **Artifacts** e baixe **ViralCut-AI-APK**.
5. Extraia o `.zip` no celular e instale o `app-debug.apk`.

---

## PASSO 3 — Conectar o App ao PC

1. Com o servidor ligado (`iniciar.bat`) e celular no **mesmo Wi-Fi**:
2. Abra o app -> aba **AJUSTES**.
3. Digite `http://SEU_IPV4:8000` (ex.: `http://192.168.1.15:8000`).
4. Desative **Modo demonstração**.
5. Toque em **Testar conexão (/health)** e depois em **Salvar configurações**.

---

## PASSO 4 — Ativar Postagem Automática no YouTube Shorts (Opcional, mas recomendado)

Para o botão **"Aprovar e Postar"** (e o Piloto Automático) subir os vídeos direto para o seu canal:

1. Acesse `console.cloud.google.com` e crie um projeto novo (ex: `ViralCut-Shorts`).
2. No menu **APIs e Serviços > Biblioteca**, pesquise **YouTube Data API v3** e clique em **Ativar**.
3. Em **Tela de permissão OAuth**, escolha **Externo**, preencha o nome do app e adicione o seu e-mail em **Usuários de teste**.
4. Em **Credenciais > Criar credenciais > ID do cliente OAuth**, escolha **App para computador (Desktop app)**.
5. Baixe o arquivo JSON, renomeie para **`client_secrets.json`** e coloque dentro de `C:\ViralCut-Server`.
6. Dê dois cliques em **`conectar_youtube.bat`**, faça login na conta do seu canal e autorize.
7. Pronto! O arquivo `youtube_token.json` será salvo e o app poderá postar com 1 clique (ou sozinho no Piloto Automático).


---

## PASSO 5 — Ativar Postagem Automática no Instagram Reels

O Instagram exige uma conta **Profissional (Criador ou Comercial)** vinculada a uma Página do Facebook:

1. Acesse `developers.facebook.com`, crie um app do tipo **Empresa** e adicione o produto **Instagram Graph API**.
2. Gere um **Token de Acesso** com as permissões `instagram_basic`, `instagram_content_publish` e `pages_show_list`.
3. Copie o seu **Instagram User ID** (número que começa com `1784...`) e o **Access Token**.
4. No app Android -> aba **AGENTE** -> **Configurar Agente Automático**:
   - Ative o switch **Instagram Reels**.
   - Cole o **Instagram User ID** e o **Access Token** e toque em **Salvar Configurações**.
5. O servidor cuida sozinho de gerar o link HTTPS temporário exigido pela Meta e publicar o Reel automaticamente.

---

## PASSO 6 — Ativar Postagem Automática no TikTok Studio

O sistema usa automação real no **TikTok Studio** (`tiktok.com/tiktokstudio/upload`) com sessão salva no seu PC:

1. Certifique-se de ter rodado `instalar_dependencias.bat` (ele instala o Playwright + Chromium automaticamente).
2. Na pasta `C:\ViralCut-Server`, dê dois cliques em **`conectar_tiktok.bat`**.
3. Uma janela do navegador vai abrir direto no **TikTok Studio**. Faça login na sua conta normalmente (QR Code, Google ou e-mail).
4. Assim que a tela de upload do TikTok Studio carregar, **feche a janela do navegador** (sua sessão ficará salva em `tiktok_profile/`).
5. No app Android -> aba **AGENTE** -> **Configurar Agente Automático**:
   - Ative o switch **TikTok Studio**.
   - Escolha entre **Publicar direto no feed** ou **Salvar em Rascunhos** e toque em **Salvar Configurações**.


---

## NOVIDADES v2.4 — Nova interface "Fábrica" + Gerador de Thumbnails

**Interface do app:** layout amarelo/preto com mascote, linha de produção (Pauta, Roteiro, Narração, Cenas, Montagem), fila de aprovação e ajustes. Veja `videos/03_DEMO_NOVA_UI_FABRICA.mp4`.

**Thumbnails com a logo do canal (aba THUMBS):**
1. Rode `instalar_dependencias.bat` de novo (instala o Pillow) e reinicie o servidor.
2. No app, abra a aba **THUMBS** e envie a logo do canal (PNG com fundo transparente). Ela é salva em `logo_canal.png` na pasta do servidor.
3. Escolha o vídeo da fila, edite o título, escolha o formato (9:16 ou 16:9) e o momento do frame.
4. Toque em **Gerar thumbnail** e depois em **Baixar**. A logo aparece no canto inferior direito.

Dica: como as legendas ficam gravadas no vídeo, mova o controle de "momento do frame" para um instante de pausa na fala.
Exemplos prontos na pasta `exemplos/`.
