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

## Arquivos
- `app.py` — aplicação e banco de dados
- `itf_scraper.py` — leitor do ranking na ITF (adaptável)
- `templates/`, `static/` — telas e estilo
- `render.yaml`, `requirements.txt` — configuração de deploy
