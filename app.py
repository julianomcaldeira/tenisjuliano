"""
Meu Tênis — diário pessoal de progresso (ITF Masters + treinos e partidas).
App único em Flask. Roda no Render de graça.
"""
import os
import base64
from datetime import datetime, date, timedelta
from functools import wraps

# Em desenvolvimento local, carrega variáveis do arquivo .env (se existir).
# Em produção (Render) as variáveis vêm do painel, e python-dotenv é ignorado.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort, Response, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import json as _json

import itf_calendar
import itf_scraper

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder=os.path.dirname(os.path.abspath(__file__)),
    static_folder=os.path.dirname(os.path.abspath(__file__)),
    static_url_path="",
)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-no-render")

# Banco: usa Postgres (Neon) se DATABASE_URL existir; senão SQLite local.
db_url = os.environ.get("DATABASE_URL", "sqlite:///tennis.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB para foto

db = SQLAlchemy(app)

# Senha de acesso (o app fica público no Render, então protegemos com senha).
APP_PASSWORD = os.environ.get("APP_PASSWORD", "trocar")
# Token para a captura automática do ranking via cron externo.
CAPTURE_TOKEN = os.environ.get("CAPTURE_TOKEN", "trocar-token")
ITF_PROFILE_URL = os.environ.get("ITF_PROFILE_URL", "")


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    opponent = db.Column(db.String(120), default="")
    is_win = db.Column(db.Boolean, default=True)
    score = db.Column(db.String(60), default="")
    surface = db.Column(db.String(40), default="")       # Saibro, Rápida, Grama...
    category = db.Column(db.String(40), default="Amistoso")  # Torneio ITF / Amistoso / Jogo-treino
    notes = db.Column(db.Text, default="")


class Training(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    duration_min = db.Column(db.Integer, default=60)
    focus = db.Column(db.String(60), default="")         # Técnico, Físico, Tático, Saque...
    intensity = db.Column(db.Integer, default=3)         # 1 a 5
    notes = db.Column(db.Text, default="")


class RankingSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    rank = db.Column(db.Integer, nullable=False)
    points = db.Column(db.Float, nullable=True)
    category = db.Column(db.String(20), default="45+")
    source = db.Column(db.String(20), default="manual")  # manual / itf
    notes = db.Column(db.String(200), default="")


class Profile(db.Model):
    """Foto de perfil + senha do usuário único — guardada no banco (Neon/Postgres)
    para persistir no Render (filesystem é efêmero)."""
    id = db.Column(db.Integer, primary_key=True)
    photo_b64 = db.Column(db.Text, nullable=True)
    photo_mime = db.Column(db.String(50), nullable=True)
    password_hash = db.Column(db.Text, nullable=True)  # se preenchido, sobrepõe APP_PASSWORD
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TournamentCache(db.Model):
    """Cache do calendário Masters — último JSON da ITF + data da coleta."""
    id = db.Column(db.Integer, primary_key=True)
    data_json = db.Column(db.Text, nullable=True)
    fetched_at = db.Column(db.DateTime, nullable=True)
    total_items = db.Column(db.Integer, default=0)


class TournamentDetailCache(db.Model):
    """Detalhes por torneio (página pública) — para exibir dentro do app."""
    id = db.Column(db.Integer, primary_key=True)
    tournament_key = db.Column(db.String(80), unique=True, nullable=False)
    data_json = db.Column(db.Text, nullable=True)
    fetched_at = db.Column(db.DateTime, nullable=True)


class TournamentChange(db.Model):
    """Histórico de mudanças detectadas entre snapshots do calendário."""
    id = db.Column(db.Integer, primary_key=True)
    tournament_key = db.Column(db.String(80), nullable=False)
    tournament_name = db.Column(db.String(200), default="")
    field = db.Column(db.String(50), nullable=False)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    change_type = db.Column(db.String(20), nullable=False)  # added, removed, changed
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)


def get_profile():
    p = Profile.query.get(1)
    if not p:
        p = Profile(id=1)
        db.session.add(p)
        db.session.commit()
    return p


def get_photo_data_uri():
    p = Profile.query.get(1)
    if p and p.photo_b64 and p.photo_mime:
        return f"data:{p.photo_mime};base64,{p.photo_b64}"
    return None


def check_password(plain):
    """Verifica senha: usa hash do banco se existir, senão APP_PASSWORD do env."""
    p = Profile.query.get(1)
    if p and p.password_hash:
        try:
            return check_password_hash(p.password_hash, plain)
        except Exception:
            return False
    return plain == APP_PASSWORD


# ---------------------------------------------------------------------------
# Torneios — helpers de cache
# ---------------------------------------------------------------------------
def _load_torneios_seed():
    try:
        with open(os.path.join(os.path.dirname(__file__), "torneios_seed.json"), "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {"items": [], "totalItems": 0}


def _get_torneios_cache_row():
    row = TournamentCache.query.get(1)
    if not row:
        row = TournamentCache(id=1)
        db.session.add(row)
        db.session.commit()
    return row


def _save_torneios_cache(items, total_items):
    row = _get_torneios_cache_row()
    row.data_json = _json.dumps({"items": items, "totalItems": total_items}, ensure_ascii=False)
    row.fetched_at = datetime.utcnow()
    row.total_items = total_items
    db.session.commit()


def _get_torneios_cached():
    row = TournamentCache.query.get(1)
    if row and row.data_json:
        try:
            data = _json.loads(row.data_json)
            return data.get("items", []), row.fetched_at, row.total_items
        except Exception:
            return [], None, 0
    return [], None, 0


def _is_cache_stale(fetched_at):
    if not fetched_at:
        return True
    age = datetime.utcnow() - fetched_at
    return age.total_seconds() > itf_calendar.CACHE_TTL_HOURS * 3600


def _fetch_and_cache_torneios(force=False):
    """
    Tenta buscar da ITF e atualizar cache. Se falhar, mantém cache antigo.
    Detecta mudanças e grava em TournamentChange.
    Retorna (items, fetched_at, warning_msg)
    """
    items, fetched_at, total = _get_torneios_cached()
    stale = _is_cache_stale(fetched_at)
    should_fetch = force or stale or not items

    if not should_fetch:
        return items, fetched_at, None

    try:
        df, dt = itf_calendar._default_date_range()
        result = itf_calendar.fetch_from_itf(date_from=df, date_to=dt, take=200)
        fresh = result["items"]
        # detecta mudanças antes de salvar
        try:
            changes = itf_calendar.diff_torneios(items, fresh)
            for ch in changes:
                db.session.add(TournamentChange(
                    tournament_key=ch["tournamentKey"],
                    tournament_name=ch.get("tournamentName") or "",
                    field=ch["field"],
                    old_value=_json.dumps(ch["old"], ensure_ascii=False) if isinstance(ch["old"], dict) else (str(ch["old"]) if ch["old"] is not None else None),
                    new_value=_json.dumps(ch["new"], ensure_ascii=False) if isinstance(ch["new"], dict) else (str(ch["new"]) if ch["new"] is not None else None),
                    change_type=ch["type"],
                ))
            if changes:
                db.session.commit()
        except Exception:
            db.session.rollback()
        _save_torneios_cache(fresh, result.get("totalItems", len(fresh)))
        return fresh, datetime.utcnow(), None
    except Exception as e:
        if items:
            return items, fetched_at, f"Não foi possível atualizar da ITF agora ({e}); mostrando dados de {fetched_at.strftime('%d/%m/%Y %H:%M') if fetched_at else 'cache'}."
        seed = _load_torneios_seed()
        seed_items = seed.get("items", [])
        if seed_items:
            _save_torneios_cache(seed_items, seed.get("totalItems", len(seed_items)))
            return seed_items, datetime.utcnow(), "Calendário da ITF temporariamente indisponível; mostrando dados de exemplo salvos. Tente Atualizar agora mais tarde."
        return [], None, f"Calendário indisponível e sem cache: {e}"


def _get_recent_changes(limit=20):
    try:
        return TournamentChange.query.order_by(TournamentChange.detected_at.desc()).limit(limit).all()
    except Exception:
        return []


def _get_detail_cached(tournament_key):
    try:
        row = TournamentDetailCache.query.filter_by(tournament_key=tournament_key).first()
        if row and row.data_json:
            return _json.loads(row.data_json), row.fetched_at
    except Exception:
        pass
    return None, None


def _save_detail_cached(tournament_key, data):
    try:
        row = TournamentDetailCache.query.filter_by(tournament_key=tournament_key).first()
        if not row:
            row = TournamentDetailCache(tournament_key=tournament_key)
            db.session.add(row)
        row.data_json = _json.dumps(data, ensure_ascii=False)
        row.fetched_at = datetime.utcnow()
        db.session.commit()
    except Exception:
        db.session.rollback()


def _filter_torneios(items, regiao="mundo", periodo="180", pais_busca=""):
    now = date.today()
    try:
        dias = int(periodo)
    except Exception:
        dias = 180
    # período padrão: próximos N dias; se 0 ou vazio, mostra tudo
    if dias > 0:
        limite = now + timedelta(days=dias)
    else:
        limite = None

    filtered = []
    pais_busca = (pais_busca or "").strip().lower()
    for it in items:
        # filtro de país/região
        code = (it.get("hostNationCode") or "").upper()
        if regiao == "brasil" and code != "BRA":
            continue
        if regiao == "sul" and code not in itf_calendar.SOUTH_AMERICA_CODES:
            continue
        # filtro por busca de país (texto)
        if pais_busca and pais_busca not in it.get("hostNation", "").lower() and pais_busca not in code.lower() and pais_busca not in it.get("location", "").lower():
            continue
        # filtro por período
        sd = it.get("startDate") or ""
        try:
            d = datetime.fromisoformat(sd.replace("Z", "")).date()
        except Exception:
            d = None
        if d and limite:
            if d < now or d > limite:
                continue
        # 45+ já está implícito: VT traz todos Masters, não filtramos idade para não esconder torneios
        filtered.append(it)

    # ordena por data
    def _k(x):
        try:
            return datetime.fromisoformat((x.get("startDate") or "").replace("Z", ""))
        except Exception:
            return datetime.max
    filtered.sort(key=_k)
    return filtered


with app.app_context():
    db.create_all()
    # Migração suave: adiciona colunas novas se a tabela já existia (Neon/Postgres)
    # db.create_all() não altera colunas existentes, então verificamos e fazemos ALTER
    try:
        from sqlalchemy import inspect as _sa_inspect, text as _sa_text
        insp = _sa_inspect(db.engine)
        try:
            cols = [c["name"] for c in insp.get_columns("profile")]
        except Exception:
            cols = []
        if "password_hash" not in cols:
            db.session.execute(_sa_text("ALTER TABLE profile ADD COLUMN password_hash TEXT"))
            db.session.commit()
        if "photo_b64" not in cols:
            db.session.execute(_sa_text("ALTER TABLE profile ADD COLUMN photo_b64 TEXT"))
            db.session.commit()
        if "photo_mime" not in cols:
            db.session.execute(_sa_text("ALTER TABLE profile ADD COLUMN photo_mime VARCHAR(50)"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        # fallback para Postgres com IF NOT EXISTS
        try:
            from sqlalchemy import text as _sa_text2
            db.session.execute(_sa_text2("ALTER TABLE profile ADD COLUMN IF NOT EXISTS password_hash TEXT"))
            db.session.execute(_sa_text2("ALTER TABLE profile ADD COLUMN IF NOT EXISTS photo_b64 TEXT"))
            db.session.execute(_sa_text2("ALTER TABLE profile ADD COLUMN IF NOT EXISTS photo_mime VARCHAR(50)"))
            db.session.commit()
        except Exception:
            db.session.rollback()
    # garante linha única de perfil
    try:
        if not Profile.query.get(1):
            db.session.add(Profile(id=1))
            db.session.commit()
    except Exception:
        db.session.rollback()
    # garante cache de torneios
    try:
        if not TournamentCache.query.get(1):
            db.session.add(TournamentCache(id=1))
            db.session.commit()
    except Exception:
        db.session.rollback()


# ---------------------------------------------------------------------------
# Autenticação simples
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("auth"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if check_password(request.form.get("password") or ""):
            session["auth"] = True
            return redirect(url_for("dashboard"))
        flash("Senha incorreta. Tente de novo.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Helpers de datas
# ---------------------------------------------------------------------------
def parse_date(raw, fallback=None):
    if not raw:
        return fallback or date.today()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return fallback or date.today()


def month_start(d):
    return d.replace(day=1)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    today = date.today()
    m_start = month_start(today)

    matches = Match.query.order_by(Match.date.desc()).all()
    trainings = Training.query.order_by(Training.date.desc()).all()
    snaps = RankingSnapshot.query.order_by(RankingSnapshot.date.asc()).all()

    wins = sum(1 for m in matches if m.is_win)
    losses = len(matches) - wins
    win_rate = round(100 * wins / len(matches)) if matches else 0

    matches_month = [m for m in matches if m.date >= m_start]
    trainings_month = [t for t in trainings if t.date >= m_start]
    minutes_month = sum(t.duration_min for t in trainings_month)

    # Sequência atual de vitórias (partidas mais recentes primeiro).
    streak = 0
    for m in matches:  # já está desc
        if m.is_win:
            streak += 1
        else:
            break

    current_rank = snaps[-1].rank if snaps else None
    rank_trend = None
    if len(snaps) >= 2:
        rank_trend = snaps[-2].rank - snaps[-1].rank  # positivo = subiu (número menor)

    stats = {
        "current_rank": current_rank,
        "rank_trend": rank_trend,
        "rank_category": snaps[-1].category if snaps else "45+",
        "total_matches": len(matches),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "matches_month": len(matches_month),
        "trainings_month": len(trainings_month),
        "minutes_month": minutes_month,
        "streak": streak,
        "has_ranking": bool(snaps),
    }
    return render_template(
        "dashboard.html",
        stats=stats,
        recent_matches=matches[:6],
        recent_trainings=trainings[:6],
        photo_data_uri=get_photo_data_uri(),
    )


# ---------------------------------------------------------------------------
# Partidas
# ---------------------------------------------------------------------------
@app.route("/partidas", methods=["GET", "POST"])
@login_required
def matches_view():
    if request.method == "POST":
        m = Match(
            date=parse_date(request.form.get("date")),
            opponent=request.form.get("opponent", "").strip(),
            is_win=request.form.get("result") == "win",
            score=request.form.get("score", "").strip(),
            surface=request.form.get("surface", "").strip(),
            category=request.form.get("category", "Amistoso"),
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(m)
        db.session.commit()
        flash("Partida registrada.")
        return redirect(url_for("matches_view"))

    matches = Match.query.order_by(Match.date.desc()).all()
    return render_template("matches.html", matches=matches, today=date.today().isoformat())


@app.route("/partidas/<int:mid>/apagar", methods=["POST"])
@login_required
def delete_match(mid):
    m = Match.query.get_or_404(mid)
    db.session.delete(m)
    db.session.commit()
    flash("Partida apagada.")
    return redirect(url_for("matches_view"))


# ---------------------------------------------------------------------------
# Treinos
# ---------------------------------------------------------------------------
@app.route("/treinos", methods=["GET", "POST"])
@login_required
def trainings_view():
    if request.method == "POST":
        t = Training(
            date=parse_date(request.form.get("date")),
            duration_min=int(request.form.get("duration_min") or 60),
            focus=request.form.get("focus", "").strip(),
            intensity=int(request.form.get("intensity") or 3),
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(t)
        db.session.commit()
        flash("Treino registrado.")
        return redirect(url_for("trainings_view"))

    trainings = Training.query.order_by(Training.date.desc()).all()
    return render_template("trainings.html", trainings=trainings, today=date.today().isoformat())


@app.route("/treinos/<int:tid>/apagar", methods=["POST"])
@login_required
def delete_training(tid):
    t = Training.query.get_or_404(tid)
    db.session.delete(t)
    db.session.commit()
    flash("Treino apagado.")
    return redirect(url_for("trainings_view"))


# ---------------------------------------------------------------------------
# Ranking ITF
# ---------------------------------------------------------------------------
@app.route("/ranking", methods=["GET", "POST"])
@login_required
def ranking_view():
    if request.method == "POST":
        s = RankingSnapshot(
            date=parse_date(request.form.get("date")),
            rank=int(request.form.get("rank")),
            points=float(request.form["points"]) if request.form.get("points") else None,
            category=request.form.get("category", "45+").strip(),
            source="manual",
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(s)
        db.session.commit()
        flash("Posição registrada.")
        return redirect(url_for("ranking_view"))

    snaps = RankingSnapshot.query.order_by(RankingSnapshot.date.desc()).all()
    return render_template(
        "ranking.html",
        snaps=snaps,
        today=date.today().isoformat(),
        itf_url=ITF_PROFILE_URL,
    )


@app.route("/ranking/<int:sid>/apagar", methods=["POST"])
@login_required
def delete_snapshot(sid):
    s = RankingSnapshot.query.get_or_404(sid)
    db.session.delete(s)
    db.session.commit()
    flash("Registro apagado.")
    return redirect(url_for("ranking_view"))


@app.route("/ranking/capturar", methods=["POST"])
@login_required
def capture_now():
    """Botão 'Capturar agora' — tenta ler o ranking direto do perfil ITF."""
    if not ITF_PROFILE_URL:
        flash("Configure a variável ITF_PROFILE_URL no Render com o link do seu perfil.")
        return redirect(url_for("ranking_view"))
    result = itf_scraper.fetch_ranking(ITF_PROFILE_URL)
    if result and result.get("rank"):
        _save_itf_snapshot(result)
        flash(f"Capturado: posição {result['rank']} ({result.get('category','')}).")
    else:
        flash("Não consegui ler o ranking automaticamente. Registre manualmente por enquanto "
              "(o leitor precisa de um ajuste fino quando seu perfil estiver ativo).")
    return redirect(url_for("ranking_view"))


@app.route("/api/capturar-itf")
def capture_cron():
    """Endpoint para um cron externo gratuito chamar toda semana.
    Uso: /api/capturar-itf?token=SEU_TOKEN"""
    if request.args.get("token") != CAPTURE_TOKEN:
        abort(403)
    if not ITF_PROFILE_URL:
        return jsonify({"ok": False, "erro": "ITF_PROFILE_URL não configurada"}), 400
    result = itf_scraper.fetch_ranking(ITF_PROFILE_URL)
    if result and result.get("rank"):
        _save_itf_snapshot(result)
        return jsonify({"ok": True, "rank": result["rank"]})
    return jsonify({"ok": False, "erro": "ranking não encontrado"}), 200


def _save_itf_snapshot(result):
    """Salva no máximo um snapshot ITF por dia (evita duplicar em capturas repetidas)."""
    today = date.today()
    existing = RankingSnapshot.query.filter_by(date=today, source="itf").first()
    if existing:
        existing.rank = result["rank"]
        existing.points = result.get("points")
        existing.category = result.get("category", existing.category)
    else:
        db.session.add(RankingSnapshot(
            date=today, rank=result["rank"], points=result.get("points"),
            category=result.get("category", "45+"), source="itf",
        ))
    db.session.commit()


# ---------------------------------------------------------------------------
# Perfil / Foto
# ---------------------------------------------------------------------------
ALLOWED_PHOTO_MIMES = {"image/jpeg", "image/png", "image/webp", "image/jpg"}


@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil_view():
    profile = get_profile()
    if request.method == "POST":
        action = request.form.get("action") or ""

        # Remover foto
        if action == "remover":
            profile.photo_b64 = None
            profile.photo_mime = None
            db.session.commit()
            flash("Foto removida.")
            return redirect(url_for("perfil_view"))

        # Trocar senha
        if action == "trocar_senha":
            atual = request.form.get("senha_atual") or ""
            nova = request.form.get("senha_nova") or ""
            confirma = request.form.get("senha_confirma") or ""
            if not check_password(atual):
                flash("Senha atual incorreta.")
                return redirect(url_for("perfil_view"))
            if len(nova) < 4:
                flash("Nova senha muito curta (mínimo 4 caracteres).")
                return redirect(url_for("perfil_view"))
            if nova != confirma:
                flash("Confirmação não confere com a nova senha.")
                return redirect(url_for("perfil_view"))
            profile.password_hash = generate_password_hash(nova, method="pbkdf2:sha256")
            db.session.commit()
            flash("Senha alterada com sucesso!")
            return redirect(url_for("perfil_view"))

        # Upload de foto (action vazio ou foto presente)
        f = request.files.get("foto")
        if f and f.filename:
            mime = f.mimetype or ""
            if mime not in ALLOWED_PHOTO_MIMES:
                ext = os.path.splitext(f.filename)[1].lower()
                mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
                mime = mime_map.get(ext, mime)
            if mime not in ALLOWED_PHOTO_MIMES:
                flash("Formato inválido. Use JPG, PNG ou WEBP.")
                return redirect(url_for("perfil_view"))
            data = f.read()
            if len(data) > 5 * 1024 * 1024:
                flash("Imagem muito grande. Máximo 5 MB.")
                return redirect(url_for("perfil_view"))
            if len(data) == 0:
                flash("Arquivo vazio.")
                return redirect(url_for("perfil_view"))
            profile.photo_b64 = base64.b64encode(data).decode("ascii")
            profile.photo_mime = mime
            db.session.commit()
            flash("Foto atualizada!")
            return redirect(url_for("perfil_view"))

        flash("Nenhuma alteração enviada.")
        return redirect(url_for("perfil_view"))

    # GET — indica se senha já foi personalizada
    has_custom_password = bool(profile.password_hash)
    return render_template("perfil.html", photo_data_uri=get_photo_data_uri(), has_custom_password=has_custom_password)


@app.route("/foto")
@login_required
def foto():
    p = Profile.query.get(1)
    if not p or not p.photo_b64:
        abort(404)
    try:
        raw = base64.b64decode(p.photo_b64)
    except Exception:
        abort(404)
    return Response(raw, mimetype=p.photo_mime or "image/jpeg")


# ---------------------------------------------------------------------------
# Torneios — calendário Masters ITF
# ---------------------------------------------------------------------------
@app.route("/torneios", methods=["GET"])
@login_required
def torneios_view():
    regiao = request.args.get("regiao", "mundo")
    if regiao not in ("brasil", "sul", "mundo"):
        regiao = "mundo"
    periodo = request.args.get("periodo", "180")
    if periodo not in ("30", "90", "180", "360"):
        periodo = "180"
    pais_busca = request.args.get("pais", "")

    items, fetched_at, warning = _fetch_and_cache_torneios(force=False)
    filtrados = _filter_torneios(items, regiao=regiao, periodo=periodo, pais_busca=pais_busca)

    cache_info = None
    if fetched_at:
        try:
            cache_info = fetched_at.strftime("%d/%m/%Y %H:%M UTC")
        except Exception:
            cache_info = str(fetched_at)

    # mudanças recentes para aviso
    changes = _get_recent_changes(limit=10)
    # marca quais torneios filtrados têm mudança recente
    changed_keys = {c.tournament_key for c in changes}

    return render_template(
        "torneios.html",
        torneios=filtrados,
        total=len(filtrados),
        total_all=len(items),
        regiao=regiao,
        periodo=periodo,
        pais_busca=pais_busca,
        fetched_at=cache_info,
        warning=warning,
        official_url=itf_calendar.ITF_CALENDAR_OFFICIAL_URL,
        changes=changes,
        changed_keys=changed_keys,
    )


@app.route("/torneios/atualizar", methods=["POST"])
@login_required
def torneios_atualizar():
    items, fetched_at, warning = _fetch_and_cache_torneios(force=True)
    if warning and "Não foi possível" in warning:
        flash(warning)
    elif warning:
        flash(warning)
    else:
        # mostra resumo de mudanças
        recent = _get_recent_changes(limit=5)
        if recent:
            flash(f"Calendário atualizado: {len(items)} torneios. {len(recent)} mudança(s) detectada(s).")
        else:
            flash(f"Calendário atualizado: {len(items)} torneios. Nenhuma mudança relevante.")
    regiao = request.form.get("regiao") or request.args.get("regiao") or "mundo"
    periodo = request.form.get("periodo") or request.args.get("periodo") or "180"
    pais = request.form.get("pais") or request.args.get("pais") or ""
    return redirect(url_for("torneios_view", regiao=regiao, periodo=periodo, pais=pais))


@app.route("/torneios/<path:tournament_key>", methods=["GET"])
@login_required
def torneio_detalhe(tournament_key):
    # tournament_key vem como S-MT200-BRA-2026-005 — precisa reconstruir
    # Busca no cache principal
    items, fetched_at, _ = _get_torneios_cached()
    torneio = next((x for x in items if x.get("tournamentKey") == tournament_key), None)
    if not torneio:
        # tenta buscar sem cache (seed)
        seed = _load_torneios_seed()
        torneio = next((x for x in seed.get("items", []) if x.get("tournamentKey") == tournament_key), None)
    if not torneio:
        flash("Torneio não encontrado no cache.")
        return redirect(url_for("torneios_view"))

    # detalhe enriquecido: tenta cache, senão busca HTML público
    detail, detail_fetched = _get_detail_cached(tournament_key)
    detail_warning = None
    if not detail:
        link = torneio.get("tournamentLink")
        if link:
            try:
                detail = itf_calendar.fetch_tournament_detail(link)
                _save_detail_cached(tournament_key, detail)
                detail_fetched = datetime.utcnow()
            except Exception as e:
                detail_warning = f"Não foi possível carregar detalhes extras da ITF agora ({e}). Mostrando dados do calendário."
                detail = {}
        else:
            detail = {}

    # mudanças específicas deste torneio
    try:
        changes = TournamentChange.query.filter_by(tournament_key=tournament_key).order_by(TournamentChange.detected_at.desc()).limit(10).all()
    except Exception:
        changes = []

    # fact sheet auth hint
    fact_auth = itf_calendar.fetch_fact_sheet_if_authed(torneio.get("tournamentLink"))

    return render_template(
        "torneio_detalhe.html",
        t=torneio,
        detail=detail or {},
        detail_fetched=detail_fetched.strftime("%d/%m/%Y %H:%M UTC") if detail_fetched else None,
        detail_warning=detail_warning,
        changes=changes,
        official_url="https://www.itftennis.com" + (torneio.get("tournamentLink") or ""),
        fact_auth=fact_auth,
    )


# ---------------------------------------------------------------------------
# APIs para os gráficos
# ---------------------------------------------------------------------------
@app.route("/api/ranking-series")
@login_required
def api_ranking_series():
    snaps = RankingSnapshot.query.order_by(RankingSnapshot.date.asc()).all()
    return jsonify([{"date": s.date.isoformat(), "rank": s.rank} for s in snaps])


@app.route("/api/partidas-series")
@login_required
def api_matches_series():
    """Vitórias e derrotas agrupadas por mês (últimos 12 meses com dados)."""
    matches = Match.query.order_by(Match.date.asc()).all()
    buckets = {}
    for m in matches:
        key = m.date.strftime("%Y-%m")
        b = buckets.setdefault(key, {"wins": 0, "losses": 0})
        if m.is_win:
            b["wins"] += 1
        else:
            b["losses"] += 1
    labels = sorted(buckets.keys())
    return jsonify({
        "labels": labels,
        "wins": [buckets[k]["wins"] for k in labels],
        "losses": [buckets[k]["losses"] for k in labels],
    })


@app.route("/api/treinos-series")
@login_required
def api_trainings_series():
    """Minutos de treino por semana (segunda-feira como âncora)."""
    trainings = Training.query.order_by(Training.date.asc()).all()
    buckets = {}
    for t in trainings:
        monday = t.date - timedelta(days=t.date.weekday())
        buckets[monday.isoformat()] = buckets.get(monday.isoformat(), 0) + t.duration_min
    labels = sorted(buckets.keys())
    return jsonify({"labels": labels, "minutes": [buckets[k] for k in labels]})


# ---------------------------------------------------------------------------
# PWA — manifest e service worker (flat, raiz)
# ---------------------------------------------------------------------------
@app.route("/manifest.webmanifest")
def manifest_webmanifest():
    resp = send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


if __name__ == "__main__":
    app.run(debug=True, port=5000)
