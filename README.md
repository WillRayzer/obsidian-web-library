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

## Como gerar

```bash
python3 build.py
```

## Atualizar as notas do vault

Se voce alterou as notas no Obsidian e quer refletir isso no site, substitua o conteudo da pasta `vault/` pela versao mais nova do seu cofre e gere novamente:

```bash
python3 build.py
```

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
  "site_name": "Biblioteca Luanda"
}
```

## Arquivos importantes

- `build.py`: gerador do site
- `config.json`: caminho do vault e nome da biblioteca
- `netlify.toml`: deploy pronto no Netlify
- `.github/workflows/deploy-gh-pages.yml`: deploy automatico no GitHub Pages
