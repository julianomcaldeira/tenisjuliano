"""
Meu Tênis — diário pessoal de progresso (ITF Masters + treinos e partidas).
App único em Flask. Roda no Render de graça.
"""
import os
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
    session, flash, jsonify, abort
)
from flask_sqlalchemy import SQLAlchemy

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


with app.app_context():
    db.create_all()


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
        if request.form.get("password") == APP_PASSWORD:
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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
