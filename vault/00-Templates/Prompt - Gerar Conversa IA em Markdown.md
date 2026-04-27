# Prompt - Gerar Conversa IA em Markdown

Use este prompt em qualquer IA quando quiser que ela devolva uma nota `.md` pronta para o meu vault do Obsidian.

## Prompt

```text
Gere a saída final como um único arquivo Markdown para Obsidian, sem explicações fora do arquivo.

Objetivo:
- Criar uma nota `.md` já pronta para meu vault.
- Seguir exatamente a estrutura abaixo.
- Identificar automaticamente os temas centrais do documento.
- Gerar tags úteis e específicas com base no conteúdo.
- Inferir a área principal e a pasta lógica mais adequada.
- Criar links `[[...]]` e campo `related:` com notas conceitualmente compatíveis quando fizer sentido.
- Se não houver notas relacionadas conhecidas, incluir pelo menos `[[00-Dashboard - Biblioteca]]`.

Regras:
- Responder apenas com o conteúdo do arquivo `.md`.
- Usar frontmatter YAML válido.
- Usar `.md` com seções na ordem exata abaixo.
- O campo `summary` deve ter 2 ou 3 frases.
- O campo `topic` deve resumir o assunto central em 1 frase.
- O campo `tags` deve ser automático, coerente com o documento, em minúsculas e com hífen.
- O campo `area` deve escolher a melhor categoria, por exemplo: `Studies`, `Business`, `System`.
- O campo `folder` deve refletir a organização lógica do tema.
- O corpo deve preservar o conteúdo principal da conversa/documento.
- Se houver perguntas e respostas, manter isso dentro de `## Conversation`.

Estrutura obrigatória:

---
title: "Titulo da conversa"
date: AAAA-MM-DD
ia: "Nome da IA"
model: "Modelo usado"
source: "Origem"
conversation_type: "chat"
area: "Studies"
folder: "04-Studies/tema"
tags:
  - ia
  - conversa
  - obsidian
  - tag-tematica
topic: "Resumo curto do assunto central."
summary: >
  Resumo em 2 ou 3 frases do conteúdo, contexto e resultado.
status: complete
related:
  - "[[00-Dashboard - Biblioteca]]"
---

## Objective

Descreva em 1 parágrafo o objetivo da conversa ou documento.

## Conversation

Coloque aqui a conversa, perguntas, respostas, blocos explicativos ou conteúdo principal.

## Conclusions & Deliverables

- Liste os principais pontos finais.
- Liste entregáveis, definições, sínteses ou resultados.

## Next Steps

- [ ] Liste próximos passos úteis
- [ ] Relacione com outras notas

Agora gere a nota `.md` com base no conteúdo abaixo:

[COLE AQUI O CONTEÚDO BRUTO]
```

