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
- `publish.py`: sincroniza o vault local, gera o site e faz commit/push
- `config.json`: caminho do vault e nome da biblioteca
- `netlify.toml`: deploy pronto no Netlify
- `.github/workflows/deploy-gh-pages.yml`: deploy automatico no GitHub Pages
