# Obsidian Web Library

Versao web estatica do vault do Obsidian armazenado dentro da pasta `vault/`.

## O que faz

- Le os arquivos `.md` do vault
- Mantem uma copia publicavel das notas dentro de `vault/`
- Gera uma homepage em formato de biblioteca
- Cria uma pagina HTML para cada nota
- Mantem links internos `[[...]]` quando a nota existe
- Permite publicar fora de casa em qualquer host de site estatico
- Gera `404.html` e `.nojekyll` para publicacao simples no GitHub Pages
- Inclui configuracao pronta para Netlify
- Inclui `Graph View` web inspirado no grafo do Obsidian
- Inclui publicacao automatica a partir do vault local
- Inclui uma pagina de captura de links com processamento local no seu computador

## Como gerar

```bash
python3 build.py
```

## Atualizar as notas do vault

Se voce alterou as notas no Obsidian e quer refletir isso no site, substitua o conteudo da pasta `vault/` pela versao mais nova do seu cofre e gere novamente:

```bash
python3 build.py
```

## Publicar a partir do seu vault local

O `config.json` aponta para o seu vault original em `source_vault_path`.

Publicar uma vez:

```bash
python3 publish.py
```

Modo automatico, monitorando o vault e publicando quando houver mudanca:

```bash
python3 publish.py --watch --interval 30
```

Atalhos no Windows:

- `publish.cmd`
- `watch-publish.cmd`

Observacao: a atualizacao online nao acontece sozinha no GitHub. Ela acontece quando esta maquina roda o `publish.py` ou o modo `--watch`.

## Captura de links via Tailscale

Se voce quer enviar uma URL pela web, mas manter todo o processamento neste computador, use a pagina `clip.html` e o mini servidor local:

```bash
python3 clip_server.py --host 127.0.0.1 --port 8787
```

Depois exponha a porta de forma privada no seu tailnet:

```bash
tailscale serve --bg --yes localhost:8787
```

No dashboard, abra `clip.html` e informe a URL HTTPS do seu tailnet no campo `API local via Tailscale`, por exemplo:

```text
https://seu-device.seu-tailnet.ts.net
```

O servidor salva os arquivos em `00-Inbox/Web Clips/` dentro do vault original. O pipeline atual continua responsavel por normalizar, enriquecer e publicar.

Se voce quiser que os clips em ingles sejam traduzidos automaticamente antes de entrarem no vault final, defina a variavel de ambiente `OPENAI_API_KEY` e, opcionalmente, `OPENAI_MODEL` e `OPENAI_BASE_URL`. Sem isso, os clips ficam na fila `Pending` e nao sobem para o site publicado.

Atalhos incluidos no projeto:

- `clip-server.cmd` ou `clip-server.vbs`: inicia a API local no WSL
- `clip-expose.cmd`: expõe a porta 8787 via Tailscale Serve
- `clip-autostart.vbs`: inicia servidor e exposicao juntos
- `register-clip-task.ps1`: registra a tarefa de inicio no Windows

Tarefa criada no Windows:

- `ObsidianClipServer`: executa no logon e inicia o servidor local mais a exposicao via Tailscale

## Como testar localmente

```bash
python3 build.py
cd dist
python3 -m http.server 8080
```

Abra `http://localhost:8080`.

## GitHub Pages

1. Crie um repositorio no GitHub e envie o conteudo desta pasta.
2. O workflow em `.github/workflows/deploy-gh-pages.yml` vai gerar o site e publicar automaticamente.
3. No GitHub, deixe `Settings > Pages` usando `GitHub Actions`.

## Netlify

1. Crie um novo site no Netlify apontando para este repositorio.
2. O arquivo `netlify.toml` ja define:
   - comando de build: `python3 build.py`
   - pasta publicada: `dist`
3. Em deploy manual, voce tambem pode enviar apenas a pasta `dist/`.

## Ajustar o nome do site

Edite `config.json`:

```json
{
  "vault_path": "vault",
  "source_vault_path": "/mnt/c/Users/negoc/Documents/geral .md/luanda/Bem",
  "site_name": "Biblioteca Luanda"
}
```

## Arquivos importantes

- `build.py`: gerador do site
- `clip_server.py`: mini servidor que transforma URLs em notas `.md`
- `publish.py`: sincroniza o vault local, gera o site e faz commit/push
- `config.json`: caminho do vault e nome da biblioteca
- `netlify.toml`: deploy pronto no Netlify
- `.github/workflows/deploy-gh-pages.yml`: deploy automatico no GitHub Pages
