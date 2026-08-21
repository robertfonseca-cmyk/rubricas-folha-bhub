# Contabilização de Rubricas de Folha — BHub

App Streamlit para gerar arquivos de importação do Domínio (EVENTO/INTEGRA/
Históricos) a partir do plano de contas e rubricas de folha de uma empresa fora
do padrão contábil BHub.

Esta pasta é uma cópia **só do código** (sem os arquivos de teste de clientes
reais, que ficam em `projetos/rubricas-folha/` no workspace principal) — feita
especificamente pra publicar num repositório e hospedar, sem levar dados
sensíveis de nenhuma empresa junto.

## Rodar localmente

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Colocar online pra outras pessoas testarem (Streamlit Community Cloud, grátis)

1. **Criar um repositório PRIVADO no GitHub** (github.com → New repository →
   marque "Private"). Se ainda não tem conta GitHub, crie uma primeiro
   (github.com/signup) — é grátis.
2. **Subir esta pasta pra esse repositório.** No terminal, dentro desta pasta:
   ```
   git remote add origin https://github.com/<seu-usuario>/<nome-do-repo>.git
   git branch -M main
   git push -u origin main
   ```
   (o `git init` e o primeiro commit já foram feitos — só falta apontar pro
   repositório do GitHub e enviar.)
3. **Criar a conta no Streamlit Community Cloud**: share.streamlit.io → "Sign
   up" ou "Continue with GitHub" (login com a mesma conta do GitHub — assim ele
   já pede acesso aos seus repositórios, incluindo o privado).
4. **Criar o app**: "Create app" → escolha o repositório e branch (`main`) →
   no campo "Main file path", coloque `streamlit_app.py` → "Deploy".
5. **Configurar a senha de acesso** (importante — sem isso, qualquer pessoa
   com o link consegue abrir e subir arquivos): no painel do app, vá em
   *Settings → Secrets* e cole:
   ```toml
   app_password = "escolha-uma-senha-aqui"
   ```
   Salve — o app reinicia sozinho. A partir daí, quem abrir o link precisa
   digitar essa senha antes de ver a tela.
6. Pronto: compartilhe o link (algo como
   `https://<nome-do-app>.streamlit.app`) e a senha com as pessoas da BHub que
   vão testar.

**Sobre privacidade:** o repositório é privado (só quem você convidar no
GitHub o vê), mas o link do app publicado funciona pra qualquer um que o
tenha — por isso a senha do passo 5 não é opcional aqui. Não é recomendado
subir, junto com o código, nenhum arquivo real de uma empresa/cliente
específico — os arquivos da empresa (plano de contas, relação de rubricas)
são enviados pela própria tela do app a cada uso, nunca ficam salvos no
repositório.

## Atualizar depois de mudar o código

Sempre que quiser publicar uma mudança nova: copie os arquivos atualizados de
`projetos/rubricas-folha/app/` pra esta pasta, `git add`, `git commit`,
`git push` — o Streamlit Community Cloud redeploya automaticamente a cada push
na branch `main`.
