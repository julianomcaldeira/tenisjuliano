# AGENTS.md

Contexto para agentes de IA (opencode, etc.) que forem editar este projeto.
Leia antes de mexer no código.

## O que é

"Meu Tênis": diário pessoal de progresso no tênis de um único usuário (Juliano, categoria
Masters 45+ da ITF). Guarda ao longo do tempo três coisas: posições no ranking da ITF,
partidas e treinos. O valor central é o histórico de evolução — a ITF só mostra a foto do
momento, aqui a gente acumula as fotos e desenha a linha do tempo.

É um app pequeno e proposital. Não transforme em algo grande sem o usuário pedir. Mantenha
simples, de um usuário só, sem dependências desnecessárias.

## Stack

Python + Flask + SQLAlchemy. Banco Postgres em produção (Neon), SQLite no local. Templates
Jinja2, CSS puro, gráficos com Chart.js via CDN no navegador. Servidor de produção: gunicorn.
Roda no Render (plano free) com deploy automático a cada push no GitHub.

## Estrutura

Repositório FLAT: todos os arquivos ficam na raiz, sem pastas `templates/` ou `static/`.
`app.py` usa `template_folder` e `static_folder` apontando para a raiz e carrega os `.html`,
`style.css` e `app.js` de lá. `app.py` concentra configuração, modelos (Match, Training,
RankingSnapshot, Profile, TournamentCache), rotas e as APIs de gráfico (`/api/...`).
`itf_scraper.py` lê o ranking do perfil público da ITF. `itf_calendar.py` busca o
calendário Masters via endpoint `tennis/api/TournamentApi/GetCalendar` (circuitCode VT) com
cache no banco. Configuração de deploy em `render.yaml`, `requirements.txt` e `.python-version`.

## Rodar local

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # e preencha APP_PASSWORD e SECRET_KEY
python app.py               # http://localhost:5000
```

Sem `DATABASE_URL` no `.env`, usa SQLite (arquivo `tennis.db`) — ideal para testar.

## Variáveis de ambiente

| Variável | Papel |
|---|---|
| `APP_PASSWORD` | senha de acesso ao app |
| `SECRET_KEY` | chave de sessão do Flask |
| `DATABASE_URL` | Postgres do Neon em produção; vazio = SQLite local |
| `CAPTURE_TOKEN` | protege o endpoint `/api/capturar-itf` chamado por cron externo |
| `ITF_PROFILE_URL` | link do perfil ITF; vazio desliga a captura automática |

## Convenções

O texto da interface é em português (pt-BR). A paleta é "quadra": navy `#10243B`, verde-bola
`#C6F24E`, branco-quadra `#EDF1F0`; fontes Archivo (títulos e números) e Inter (corpo). Mantenha
esse visual ao criar telas novas. Ranking: número menor é melhor, então o eixo Y do gráfico de
evolução é invertido — não "conserte" isso.

## Torneios — calendário Masters ITF

Aba `Torneios` exibe dentro do app os torneios do World Tennis Masters Tour vindos da ITF.
Fonte: `GET https://www.itftennis.com/tennis/api/TournamentApi/GetCalendar` com params
`circuitCode=VT`, `dateFrom`, `dateTo`, `skip`, `take`, `nationCodes` etc (ver
`itf_calendar.py:57` — `ITF_CALENDAR_BASE_URL` e `DEFAULT_PARAMS`). Headers mínimos:
`User-Agent`, `Accept: application/json`, `Referer`. Sem auth. Resposta `{items, totalItems}`
com campos `tournamentName`, `dates`, `location/venue`, `category` (MT100 a MT1000),
`surfaceDesc`, `hostNation/hostNationCode`, `startDate/endDate`, `tournamentLink`.

Cache: tabela `TournamentCache` (id 1) guarda último JSON + `fetched_at`. Ao abrir a aba,
se o cache tem mais de 24h (`CACHE_TTL_HOURS`), busca da ITF e atualiza; senão serve cache.
Botão `Atualizar agora` força busca. Se a busca falhar (Incapsula/HTML ou timeout), serve
último cache com aviso discreto e link pro calendário oficial; sem cache, mostra mensagem
amigável e link. Seed em `torneios_seed.json` garante primeira visita mesmo offline.
Filtros na tela: região (Brasil, América do Sul, Mundo) e período (próximos torneios por
padrão). Por torneio: nome, datas, cidade/país, categoria/grade, superfície, prazo de
inscrição (não vem no endpoint, então exibe aviso), link pro torneio. Cada torneio tem
várias faixas etárias; não filtrar por idade.

## Pendência conhecida — leitor da ITF

O perfil ITF do usuário só existe a partir de 2027, então `itf_scraper._extract_rank()` usa uma
leitura genérica por regex (procura "ranking", "pts", "45+"). Quando a página real existir, troque
os seletores por `soup.select(...)` apontando para os elementos certos. Enquanto isso, o usuário
registra o ranking manualmente na aba Ranking ITF e o gráfico funciona igual. Não invente a
estrutura do HTML sem ter a página real em mãos.

## Deploy (produção)

Push na branch principal do GitHub dispara deploy automático no Render (via `render.yaml`).
Migrações não são necessárias: `db.create_all()` cria as tabelas que faltam no boot. Se você
alterar um modelo de forma incompatível, avise o usuário — não apague dados.
