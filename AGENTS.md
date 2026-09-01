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
`style.css`, `app.js`, `manifest.webmanifest`, `sw.js` e os ícones `icon-*.png` de lá.
Rotas explícitas `/manifest.webmanifest` e `/sw.js` em `app.py` garantem mimetype e
Cache-Control corretos para o PWA. `app.py` concentra configuração, modelos (Match, Training,
RankingSnapshot, Profile, TournamentCache etc.; **FPT**: `FptTournamentCache`,
`FptRankingCache`, `FptRankingSnapshot` totalmente separados do ITF), rotas e as APIs de
gráfico (`/api/...`). `itf_scraper.py` lê o ranking do perfil público da ITF.
`itf_calendar.py` busca o calendário Masters via endpoint `tennis/api/TournamentApi/GetCalendar`
(circuitCode VT) com cache no banco. `fpt_source.py` busca dados da FPT (SisFPT) com
endpoints próprios e cache separado. Configuração de deploy em `render.yaml`,
`requirements.txt` e `.python-version`.

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

## Torneios — calendário Masters ITF (fonte independente)

Aba `Torneios` (menu principal) exibe dentro do app os torneios do World Tennis Masters Tour vindos da ITF.
Fonte: `GET https://www.itftennis.com/tennis/api/TournamentApi/GetCalendar` com params
`circuitCode=VT`, `dateFrom`, `dateTo`, `skip`, `take`, `nationCodes` etc (ver
`itf_calendar.py:57` — `ITF_CALENDAR_BASE_URL` e `DEFAULT_PARAMS`). Headers mínimos:
`User-Agent`, `Accept: application/json`, `Referer`. Sem auth. Resposta `{items, totalItems}`
com campos `tournamentName`, `dates`, `location/venue`, `category` (MT100 a MT1000),
`surfaceDesc`, `hostNation/hostNationCode`, `startDate/endDate`, `tournamentLink`.

Detalhe: `GET https://www.itftennis.com/en/tournament/<slug>/<key>/` é raspado com
`BeautifulSoup` em `itf_calendar.fetch_tournament_detail()` para exibir dentro do app
sede, endereço, telefone, diretor, bola oficial, tamanho do quadro e links para
Fact Sheet/Acceptance List. Fact Sheet completo exige login no Tour Zone; se
`ITF_TOUR_ZONE_EMAIL`/`ITF_TOUR_ZONE_PASSWORD` estiverem definidos (env vars no Render,
nunca no código), o app indica que requer login e guarda hook para futura autenticacao.

Cache ITF: `TournamentCache` (id 1) guarda último JSON + `fetched_at`. `TournamentDetailCache`
guarda detalhes por `tournamentKey`. Ao abrir a aba, se o cache tem mais de 24h
(`CACHE_TTL_HOURS`), busca da ITF e atualiza; senão serve cache. Botão `Atualizar agora`
força busca. Se a busca falhar (Incapsula/HTML ou timeout), serve último cache com aviso
discreto e link pro calendário oficial; sem cache, usa `torneios_seed.json`. Filtros:
região (Brasil, América do Sul, Mundo) e período (próximos torneios por padrão).
Histórico: `TournamentChange` registra diff entre snapshots e a lista é mostrada no topo da aba
e na página de detalhe `torneio_detalhe.html`. Cada torneio Masters tem várias faixas etárias;
não filtrar por idade. Esta fonte é totalmente separada da FPT.

## Federação Paulista de Tênis — FPT (fonte independente)

Bloco `FPT` no menu (grupo com `Torneios FPT` e `Ranking FPT`), totalmente separado do ITF:
módulo próprio `fpt_source.py`, tabelas próprias `FptTournamentCache`, `FptRankingCache` e
`FptRankingSnapshot` (histórico manual), páginas `fpt_torneios.html` e `fpt_ranking.html`.
Nunca mistura dados do ITF.

Torneios FPT: `GET https://sisfpt.com.br/area-publica/torneios/abertos?code=&year=&half=&month=&name=&match=&club=`
onde `match` filtra classe/categoria (ex: `2M1`, `2M2` para 2ª classe; `40M`, `45M` para idade) e
`club` identifica cidade/clube (ex: `ECP`). Se a tabela não vier de forma confiável sem JS,
o app serve último cache com aviso e link para o site oficial e reporta a limitação.

Ranking FPT: `GET .../rankings/tenistas/ajax/data/{year}` e `.../ajax/categoria/{year}` para
popular datas/categorias, e `GET /rankings/tenistas?year=&date=&category=` para a tabela.
Por padrão usa ano e data mais recentes e categorias `2M1`, `2M2`, `40M` (com `45M` opcional).
Como o usuário ainda não pontua, o modo principal é registro manual com histórico e gráfico
próprio da FPT (`FptRankingSnapshot` + `/api/fpt-ranking-series`), separado do ITF; a consulta
oficial fica pronta para o futuro sem bloquear a tela. Cache próprio com TTL 24h e botão
`Atualizar agora`, com fallback e aviso.

## Pendência conhecida — leitor da ITF

O perfil ITF do usuário só existe a partir de 2027, então `itf_scraper._extract_rank()` usa uma
leitura genérica por regex (procura "ranking", "pts", "45+"). Quando a página real existir, troque
os seletores por `soup.select(...)` apontando para os elementos certos. Enquanto isso, o usuário
registra o ranking manualmente na aba Ranking ITF e o gráfico funciona igual. Não invente a
estrutura do HTML sem ter a página real em mãos.

## PWA instalável (iPhone/Safari)

O app é um PWA instalável sem loja. Raiz contém `manifest.webmanifest` (name `Meu Tênis`,
`start_url` `/`, `display` `standalone`, cores `#10243B`, ícones 192/256/384/512 e 512 maskable
com bola `#C6F24E` sobre fundo `#10243B`, mais `apple-touch-icon.png` 180), `sw.js` com
cache do app shell (cache-first para estáticos, network-first para páginas autenticadas com
fallback offline) e `base.html` com `link rel=manifest`, `theme-color` e tags
`apple-mobile-web-app-capable`/`apple-touch-icon`. O service worker só registra se
`serviceWorker` existir (iOS/Safari) e não cacheia POST de login. Para (re)gerar ícones:
`python3 /tmp/gen_icons.py` (gera PNGs quadrados navy/bola) e referencie no manifest.

## Deploy (produção)

Push na branch principal do GitHub dispara deploy automático no Render (via `render.yaml`).
Migrações não são necessárias: `db.create_all()` cria as tabelas que faltam no boot. Se você
alterar um modelo de forma incompatível, avise o usuário — não apague dados.
