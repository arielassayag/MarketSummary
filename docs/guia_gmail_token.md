# Guia Completo: Como Exportar e Configurar o Token do Gmail para Envio Automatizado

Este guia ensina os dois métodos oficiais e seguros para automatizar o envio de e-mails via Gmail:
1. **Método OAuth 2.0 Oficial (Google Cloud API)** — recomendado para aplicações profissionais.
2. **Método Senhas de App (SMTP com 2FA)** — rápido e direto para scripts locais.

---

## Método 1: OAuth 2.0 Oficial (Recomendado)

Gera um arquivo de credenciais e um token de acesso renovável (`token.json`) com escopo restrito exclusivamente a envio (`gmail.send`).

### Passo 1: Criar o Projeto no Google Cloud Console
1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie um novo projeto (ex: `fechamento-mercado-notificacoes`).
3. No menu lateral, acesse **APIs e Serviços > Biblioteca**.
4. Pesquise por **Gmail API** e clique em **Ativar** (Enable).

### Passo 2: Configurar a Tela de Permissão OAuth
1. No menu lateral, clique em **Tela de permissão OAuth** (OAuth consent screen).
2. Escolha **Externo** (External) e clique em Criar.
3. Preencha o nome do app (ex: `Fechamento AI Notes`) e seu e-mail de suporte.
4. Na etapa de **Escopos** (Scopes), adicione apenas o escopo mínimo necessário:
   - `https://www.googleapis.com/auth/gmail.send` (permite apenas enviar, sem ler sua caixa de entrada).
5. Na etapa de **Usuários de teste** (Test users), adicione o seu próprio e-mail Gmail.

### Passo 3: Criar as Credenciais do Cliente
1. Acesse **Credenciais > Criar Credenciais > ID do cliente OAuth**.
2. Em **Tipo de aplicativo**, selecione **App para computador** (Desktop app).
3. Clique em **Criar** e depois em **Fazer download do JSON**.
4. Renomeie o arquivo baixado para `credentials.json` e coloque-o na pasta do seu projeto.

### Passo 4: Script Python para Autenticar e Exportar o `token.json`
Execute o script abaixo uma única vez para abrir o navegador, autorizar e gerar o `token.json`:

```python
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def export_gmail_token():
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    # Abre o navegador para autenticação do usuário
    creds = flow.run_local_server(port=0)
    
    # Salva o token gerado em token.json
    with open('token.json', 'w') as token_file:
        token_file.write(creds.to_json())
    print("Sucesso! O arquivo 'token.json' foi exportado com segurança.")

if __name__ == '__main__':
    export_gmail_token()
```

### Passo 5: Enviando E-mails com o `token.json`
Com o `token.json` gerado, a aplicação envia mensagens sem necessidade de nova intervenção humana no navegador:

```python
import base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def send_closing_email(to_address: str, subject: str, html_content: str):
    creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/gmail.send'])
    service = build('gmail', 'v1', credentials=creds)

    message = MIMEText(html_content, 'html')
    message['to'] = to_address
    message['subject'] = subject
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    sent = service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
    print(f"E-mail enviado com sucesso! Message ID: {sent['id']}")
```

---

## Método 2: Senhas de App do Google (SMTP Direto)

Ideal para quem deseja envio rápido sem configurar o Google Cloud Console:

1. Acesse sua [Conta Google > Segurança](https://myaccount.google.com/security).
2. Verifique se a **Verificação em duas etapas (2FA)** está ativada.
3. Na barra de pesquisa de segurança, digite **Senhas de app** (App Passwords).
4. Crie uma nova senha de app com o nome `Fechamento Mercado`.
5. O Google gerará uma senha de 16 caracteres (ex: `abcd efgh ijkl mnop`).
6. Utilize no Python com `smtplib`:
   ```python
   import smtplib
   from email.mime.text import MIMEText

   smtp_server = "smtp.gmail.com"
   port = 587
   sender_email = "seu_email@gmail.com"
   app_password = "abcd efgh ijkl mnop"  # Nunca comite no git!

   msg = MIMEText("Comentário aprovado em anexo", "html")
   msg["Subject"] = "Fechamento de Mercado — AI Notes #8"
   msg["From"] = sender_email
   msg["To"] = "destinatario@empresa.com"

   with smtplib.SMTP(smtp_server, port) as server:
       server.starttls()
       server.login(sender_email, app_password)
       server.send_message(msg)
   ```

---

## Regras de Ouro de Segurança

1. **Nunca comite credenciais no Git:** Adicione `credentials.json`, `token.json` e senhas ao seu `.gitignore`:
   ```gitignore
   credentials.json
   token.json
   .env
   ```
2. **Princípio do Menor Privilégio:** Utilize estritamente o escopo `gmail.send`. Nunca autorize escopos de leitura (`gmail.readonly`) se sua aplicação apenas envia relatórios.
3. **Revogação Imediata:** Caso suspeite de vazamento, revogue as credenciais imediatamente no Google Cloud Console ou na página de senhas de app da Conta Google.
