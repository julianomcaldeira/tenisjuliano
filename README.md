# Meu Tênis — diário de progresso

Sistema pessoal para acompanhar sua evolução no tênis: posição no **Masters Tour da ITF**,
**partidas** e **treinos** do dia a dia. A ideia é guardar ao longo do tempo aquilo que a ITF
só mostra como "foto do momento" — assim você enxerga sua evolução de verdade.

Roda **de graça** no Render.

---

## O que ele faz

- **Painel** com sua posição atual no ranking, aproveitamento, sequência de vitórias e horas de treino no mês.
- **Partidas**: registra cada jogo (adversário, placar, piso, vitória/derrota, torneio ou amistoso).
- **Treinos**: registra duração, foco (técnico, físico, tático...) e intensidade.
- **Ranking ITF**: guarda cada posição ao longo do tempo e desenha o gráfico de evolução.
- **Torneios ITF**: calendário do World Tennis Masters Tour direto da ITF, com filtros por região e período, dentro do app.
- **FPT — Torneios e Ranking**: bloco totalmente separado da FPT (SisFPT) com torneios abertos e ranking por classe (2ª classe, 40M/45M) com histórico próprio.
- **PWA instalável**: instale no iPhone pelo Safari como app nativo (ícone na tela inicial, abre em tela cheia).
- Protegido por senha (o app fica público na internet, mas só você entra).

---

## Passo a passo do deploy (uns 15 min, uma vez só)

### 1. Suba os arquivos para o GitHub
Crie um repositório novo e suba **todos os arquivos deste projeto de uma vez**.

> ⚠️ Importante pra você: no GitHub web, use **Add file → Upload files** e **arraste TODA a
> pasta de uma vez** num único commit. Não suba arquivo por arquivo — quando faz um a um, o
> Render acaba fazendo deploy pela metade (mistura de arquivo velho e novo). Tudo junto, num
> commit só, resolve.

### 2. Crie um banco de dados grátis (Neon)
Isso garante que seus dados **não se percam** quando o app reinicia.
1. Entre em https://neon.tech e crie conta grátis.
2. Crie um projeto. Ele te dá uma **connection string** parecida com
   `postgresql://usuario:senha@host/banco`.
3. Guarde essa string — você vai colar no Render no passo 4.

(O Neon tem plano grátis que não expira. Sem esse passo o app até funciona, mas perde os dados a cada atualização.)

### 3. Crie o serviço no Render
1. Em https://render.com, **New → Blueprint** e conecte o repositório do GitHub.
   O Render lê o arquivo `render.yaml` e já configura tudo.
2. Se preferir manual: **New → Web Service**, runtime **Python**, build `pip install -r requirements.txt`,
   start `gunicorn app:app`, plano **Free**.

### 4. Preencha as variáveis de ambiente (no painel do Render)
| Variável | O que colocar |
|---|---|
| `APP_PASSWORD` | a senha que **você** vai usar pra entrar no app |
| `DATABASE_URL` | a connection string do Neon (passo 2) |
| `CAPTURE_TOKEN` | invente um texto qualquer (ex.: `raquete2027`) |
| `ITF_PROFILE_URL` | **deixe vazio por enquanto** — preenche quando seu perfil ITF estiver ativo |
| `SECRET_KEY` | o Render gera sozinho, não precisa mexer |

Salve. O Render publica e te dá um endereço tipo `https://meu-tenis.onrender.com`.
Abra, digite sua senha e comece a usar.

---

## Como usar no dia a dia

- Jogou uma partida? Aba **Partidas** → preenche → registrar. Vale para torneio ou amistoso.
- Treinou? Aba **Treinos** → duração, foco, intensidade.
- A cada atualização do ranking na ITF, aba **Ranking ITF** → registra a posição. Cada registro
  vira um ponto no gráfico de evolução do painel.
- Procurando torneio? Aba **Torneios ITF** traz o calendário oficial da ITF com atalhos Brasil, América do Sul e Mundo e filtro por período, além do botão Atualizar agora.
- Bloco **FPT**: `Torneios FPT` lista abertos da Federação Paulista com filtros por mês, classe e clube; `Ranking FPT` guarda seu histórico na 2ª classe/40M com gráfico próprio e permite consulta ao ranking oficial.

## Captura automática do ranking (quando seu perfil ITF existir, em 2027)

Hoje seu perfil ainda não existe, então **registre o ranking manualmente** — o gráfico funciona igual.

Quando o perfil estiver ativo:
1. Preencha `ITF_PROFILE_URL` no Render com o link do seu perfil público.
2. Use o botão **Capturar agora** na aba Ranking ITF.
3. Para capturar sozinho toda semana, crie um agendamento grátis em https://cron-job.org apontando para:
   `https://SEU-APP.onrender.com/api/capturar-itf?token=SEU_CAPTURE_TOKEN`

> **Um ajuste vai ser necessário:** como a página real do seu perfil ainda não existe, o leitor
> automático (`itf_scraper.py`) usa uma leitura genérica. Quando o perfil estiver no ar, é uma
> mexida rápida de 10 minutos nos seletores do arquivo — deixei tudo comentado explicando onde.
> Até lá, o registro manual cobre 100% da necessidade.

---

## Rodar no seu computador (opcional, para testar)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export APP_PASSWORD=teste SECRET_KEY=qualquercoisa
python app.py
# abre http://localhost:5000
```

## Editar depois com o opencode

O projeto já vem com o git iniciado e um primeiro commit feito. Para colocar no GitHub e
começar a editar com o opencode:

```bash
git remote add origin https://github.com/SEU-USUARIO/meu-tenis.git
git push -u origin main
```

Depois é só rodar o `opencode` dentro da pasta. Ele lê o arquivo `AGENTS.md`, que explica a
estrutura e as convenções do projeto, e já entende o que pode mexer. Fez uma alteração?
`git push` — o Render publica sozinho em segundos.

> Como agora você usa git de verdade (e não o upload manual do GitHub web), aquele problema de
> deploy pela metade não acontece mais: cada push envia tudo de uma vez.

## Torneios ITF — de onde vem e detalhes

A lista ITF vem direto sem navegador em produção: `GET https://www.itftennis.com/tennis/api/TournamentApi/GetCalendar?circuitCode=VT&dateFrom=...&dateTo=...&take=200` (ver `itf_calendar.py`). O app guarda o último resultado em cache no banco por 24 horas e só atualiza quando você abre a aba ou clica em Atualizar agora. Se a ITF estiver fora do ar, o app mostra o último cache com aviso e link pro calendário oficial.

Ao clicar em um torneio você vê os detalhes dentro do app (sede, endereço, diretor, bola, quadro) raspados da página pública do torneio. O Fact Sheet completo e o prazo de inscrição exigem login no Tour Zone; se configurar `ITF_TOUR_ZONE_EMAIL` e `ITF_TOUR_ZONE_PASSWORD` nas variáveis de ambiente do Render, o app indicará o acesso. O sistema também detecta mudanças entre atualizações e mostra no topo da aba e na página do torneio o que foi adicionado, removido ou alterado.

## Federação Paulista — FPT (fonte independente do ITF)

Bloco `FPT` totalmente separado no menu, com módulo próprio `fpt_source.py` e tabelas próprias `FptTournamentCache`, `FptRankingCache` e `FptRankingSnapshot` (histórico manual). Nunca mistura dados do ITF.

Torneios FPT: `GET https://sisfpt.com.br/area-publica/torneios/abertos?code=&year=&half=&month=&name=&match=&club=` onde `match` filtra `2M1`/`2M2` (2ª classe) e `40M`/`45M` (idade) e `club` filtra clube/cidade. Se a tabela não vier de forma confiável sem JS, o app serve o último cache com aviso e link para o site oficial e reporta a limitação.

Ranking FPT: `GET .../rankings/tenistas/ajax/data/{year}` e `.../ajax/categoria/{year}` para popular datas e categorias, e `GET .../rankings/tenistas?year=&date=&category=` para a tabela (ex: `2M2`, `40M`). Como você ainda não pontua, o modo principal é registro manual com histórico e gráfico próprio da FPT (separado do ITF); a consulta oficial fica pronta para o futuro.

## PWA instalável (iPhone)

O app já é instalável: `manifest.webmanifest` com ícones `icon-192/256/384/512` e `icon-512-maskable.png` (bola `#C6F24E` sobre fundo `#10243B`) mais `apple-touch-icon.png` 180, e `sw.js` com cache do app shell. No iPhone, abra o site no Safari, toque em Compartilhar → Adicionar à Tela de Início. Para (re)gerar ícones: `python3 /tmp/gen_icons.py`.

## Arquivos

Repositório flat, tudo na raiz, sem pastas `templates/` ou `static/`:

- `app.py` — aplicação, banco e rotas (usa `template_folder` e `static_folder` na raiz; rotas `/manifest.webmanifest` e `/sw.js` garantem mimetype)
- `itf_scraper.py` — leitor do ranking na ITF
- `itf_calendar.py` — busca do calendário Masters (endpoint, cache, filtros)
- `torneios_seed.json` — dados de exemplo para primeira carga offline
- `base.html`, `dashboard.html`, `matches.html`, `trainings.html`, `ranking.html`, `torneios.html`, `torneio_detalhe.html`, `perfil.html`, `login.html` — telas
- `style.css`, `app.js`, `manifest.webmanifest`, `sw.js`, `icon-*.png`, `apple-touch-icon.png` — estilo, gráficos e PWA
- `render.yaml`, `requirements.txt` — configuração de deploy
