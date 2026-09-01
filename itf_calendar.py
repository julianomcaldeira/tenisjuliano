"""
itf_calendar.py — Fonte de dados do World Tennis Masters Tour.

Descoberta (playwright stealth, 2026-09-01):
  A página https://www.itftennis.com/en/tournament-calendar/world-tennis-masters-tour-calendar/
  carrega via XHR:
    GET https://www.itftennis.com/tennis/api/TournamentApi/GetCalendar
    ?circuitCode=VT
    &searchString=
    &skip=0
    &take=100
    &nationCodes=
    &zoneCodes=
    &dateFrom=2026-08-01
    &dateTo=2026-08-31
    &indoorOutdoor=
    &categories=
    &isOrderAscending=true
    &orderField=startDate
    &surfaceCodes=
    &singlesDrawFormat=

  Headers mínimos: User-Agent, Accept: application/json, Referer.
  Sem autenticação. Resposta JSON: {url, items:[...], totalItems}
  Cada item: tournamentName, dates, location/venue, category (MT100..MT1000),
  surfaceDesc/surfaceCode, indoorOrOutDoor, hostNation/hostNationCode,
  startDate/endDate (ISO), tournamentKey, tournamentLink (relativo), year.

  Exemplo (trecho):
    {"tournamentName":"MT200 Tours","dates":"26 Jul to 01 Aug 2026","location":"Tours",
     "category":"MT200","surfaceDesc":"Clay","indoorOrOutDoor":"Outdoor",
     "hostNation":"France","hostNationCode":"FRA","venue":"Tours",
     "startDate":"2026-07-26T00:00:00","endDate":"2026-08-01T00:00:00",
     "tournamentKey":"S-MT200-FRA-2026-002",
     "tournamentLink":"/en/tournament/mt200-tours/fra/2026/s-mt200-fra-2026-002/"}

Mapeamento usado:
  nome -> tournamentName / promotionalName
  datas -> startDate, endDate, dates
  cidade -> location / venue
  país -> hostNation, hostNationCode
  categoria/grade -> category (MT100 a MT1000, Grade C1 etc)
  superfície -> surfaceDesc + indoorOrOutDoor
  prazo de inscrição -> NÃO vem neste endpoint (omitido com aviso)
  link -> https://www.itftennis.com + tournamentLink

Se a ITF mudar o endpoint, ajuste ITF_CALENDAR_BASE_URL e DEFAULT_PARAMS abaixo.
"""

import json
import os
import re
import requests
from datetime import datetime, date, timedelta

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# ---------------------------------------------------------------------------
# Config — fácil de ajustar se a ITF mudar
# ---------------------------------------------------------------------------
ITF_CALENDAR_BASE_URL = "https://www.itftennis.com/tennis/api/TournamentApi/GetCalendar"
ITF_CALENDAR_OFFICIAL_URL = "https://www.itftennis.com/en/tournament-calendar/world-tennis-masters-tour-calendar/"

# Filtro padrão: VT = Veterans/Masters
DEFAULT_PARAMS = {
    "circuitCode": "VT",
    "searchString": "",
    "skip": "0",
    "take": "200",
    "nationCodes": "",
    "zoneCodes": "",
    "indoorOutdoor": "",
    "categories": "",
    "isOrderAscending": "true",
    "orderField": "startDate",
    "surfaceCodes": "",
    "singlesDrawFormat": "",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": ITF_CALENDAR_OFFICIAL_URL,
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
}

SOUTH_AMERICA_CODES = {"BRA", "ARG", "CHI", "COL", "PER", "URU", "PAR", "VEN", "ECU", "BOL", "GUY", "SUR", "GUF"}

CACHE_TTL_HOURS = 24

# Detalhe: página pública do torneio contém sede, diretor, bola, quadro etc.
# Fact sheet completo exige login; se ITF_TOUR_ZONE_EMAIL/PASSWORD estiverem definidos, tenta buscar.
ITF_TOUR_ZONE_EMAIL = os.environ.get("ITF_TOUR_ZONE_EMAIL") or os.environ.get("ITF_EMAIL")
ITF_TOUR_ZONE_PASSWORD = os.environ.get("ITF_TOUR_ZONE_PASSWORD") or os.environ.get("ITF_PASSWORD")

# ---------------------------------------------------------------------------
# Helpers de data
# ---------------------------------------------------------------------------

def _default_date_range():
    """Próximos 6 meses por padrão, alinhado ao que o usuário vê na ITF."""
    today = date.today()
    # começa hoje, termina 6 meses depois (cobrir take=200)
    end = today + timedelta(days=180)
    return today.isoformat(), end.isoformat()

def _safe_parse_iso(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "")).date()
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Busca direta na ITF (sem cache)
# ---------------------------------------------------------------------------

def fetch_from_itf(date_from=None, date_to=None, nation_codes="", take=200):
    """
    Chama o endpoint real com requests. Não usa navegador.
    Retorna dict {items, totalItems, fetched_at} ou levanta.
    Detecta bloqueio do Incapsula (HTML em vez de JSON) e levanta.
    """
    if date_from is None or date_to is None:
        df, dt = _default_date_range()
        date_from = date_from or df
        date_to = date_to or dt

    params = dict(DEFAULT_PARAMS)
    params["dateFrom"] = date_from
    params["dateTo"] = date_to
    params["take"] = str(take)
    params["skip"] = "0"
    params["nationCodes"] = nation_codes or ""

    resp = requests.get(ITF_CALENDAR_BASE_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    # Incapsula às vezes retorna HTML com 200 mas content-type text/html
    ctype = resp.headers.get("content-type", "")
    if "text/html" in ctype or resp.text.lstrip().startswith("<html"):
        raise RuntimeError(f"ITF bloqueou com HTML (Incapsula) — content-type {ctype}")
    data = resp.json()
    items = data.get("items", [])
    # normaliza cada item para campos estáveis
    norm = []
    for it in items:
        norm.append({
            "tournamentName": it.get("tournamentName") or it.get("name") or "",
            "promotionalName": it.get("promotionalName") or "",
            "dates": it.get("dates") or "",
            "location": it.get("location") or it.get("venue") or "",
            "venue": it.get("venue") or "",
            "category": it.get("category") or "",
            "surfaceDesc": it.get("surfaceDesc") or "",
            "surfaceCode": it.get("surfaceCode") or "",
            "indoorOrOutDoor": it.get("indoorOrOutDoor") or "",
            "hostNation": it.get("hostNation") or "",
            "hostNationCode": it.get("hostNationCode") or "",
            "startDate": it.get("startDate") or "",
            "endDate": it.get("endDate") or "",
            "tournamentKey": it.get("tournamentKey") or "",
            "tournamentLink": it.get("tournamentLink") or "",
            "year": it.get("year") or "",
        })
    return {
        "items": norm,
        "totalItems": data.get("totalItems", len(norm)),
        "fetched_at": datetime.utcnow().isoformat(),
        "dateFrom": date_from,
        "dateTo": date_to,
    }

# ---------------------------------------------------------------------------
# Detalhe do torneio — busca HTML público + parsing
# ---------------------------------------------------------------------------
DETAIL_HEADERS = {
    "User-Agent": HEADERS["User-Agent"],
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": ITF_CALENDAR_OFFICIAL_URL,
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8",
}

def fetch_tournament_detail(tournament_link):
    """
    Busca a página de detalhe do torneio e extrai campos públicos.
    tournament_link: ex /en/tournament/mt200-pinhais/bra/2026/s-mt200-bra-2026-005/
    Retorna dict com venue, director, ball, drawSizes, factSheet link etc.
    Se o WAF bloquear, levanta RuntimeError.
    Se o HTML indicar login necessário para fact sheet, marca factSheetRequiresLogin=True.
    """
    if not tournament_link:
        return {}
    if tournament_link.startswith("/"):
        url = "https://www.itftennis.com" + tournament_link
    else:
        url = tournament_link
    resp = requests.get(url, headers=DETAIL_HEADERS, timeout=15)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if resp.text.lstrip().startswith("<html") and "Incapsula" in resp.text[:2000] and "ROBOTS" in resp.text[:2000]:
        # Incapsula block tem <html> com robots noindex
        if len(resp.text) < 500:
            raise RuntimeError("ITF bloqueou detalhe com Incapsula (HTML curto)")
    if not BeautifulSoup:
        return {"raw_html": resp.text[:5000], "url": url}
    soup = BeautifulSoup(resp.text, "html.parser")
    for s in soup(["script", "style"]):
        s.decompose()
    text = soup.get_text(separator="\n", strip=True)

    out = {"url": url, "factSheetRequiresLogin": False}

    # Diretor
    m = re.search(r"Tournament Director name:\s*([^\n]+)", text)
    if m:
        out["directorName"] = m.group(1).strip()
    m = re.search(r"Tournament Director email:\s*([^\n]+)", text)
    if m:
        out["directorEmail"] = m.group(1).strip()
    # Bola
    m = re.search(r"Official ball:\s*([^\n]+)", text)
    if m:
        out["officialBall"] = m.group(1).strip()
    # Sede
    m = re.search(r"Venue Name:\s*([^\n]+)", text)
    if m:
        out["venueName"] = m.group(1).strip()
    m = re.search(r"Venue Address:[^\n]*\n*([^\n]+)", text)
    if m:
        # pega linha do endereço
        addr = m.group(1).strip()
        # tenta pegar endereço completo até telefone
        # já temos via regex anterior, mas pega mais contexto
        out["venueAddress"] = addr
        # tenta endereço completo com Google Maps link
        # procura AV ... Brazil
        m2 = re.search(r"AV[^\n]*Brazil[^\n]*", text)
        if m2:
            out["venueAddressFull"] = m2.group(0).strip()
    m = re.search(r"Venue Telephone:\s*([^\n]+)", text)
    if m:
        out["venuePhone"] = m.group(1).strip()
    # Chave
    m = re.search(r"Tournament key:\s*([^\n]+)", text)
    if m:
        out["tournamentKeyDetail"] = m.group(1).strip()
    # Fact sheet link
    fact = soup.find("a", href=lambda h: h and "fact-sheet" in h)
    if fact:
        out["factSheetLink"] = fact.get("href")
        if out["factSheetLink"] and out["factSheetLink"].startswith("/"):
            out["factSheetLink"] = "https://www.itftennis.com" + out["factSheetLink"]
    # Acceptance List, Draws etc
    for key in ["acceptance-list", "draws-and-results", "order-of-play"]:
        a = soup.find("a", href=lambda h: h and key in h)
        if a:
            href = a.get("href")
            if href and href.startswith("/"):
                href = "https://www.itftennis.com" + href
            out[key.replace("-", "_")] = href

    # Draw sizes
    # Procura "Provisional draw size" e linhas seguintes
    draw_sizes = []
    # o HTML tem "Provisional draw size" seguido de "Singles main draw" e número
    for match in re.finditer(r"Singles main draw\s*\n\s*(\d+)", text):
        draw_sizes.append({"type": "Singles main draw", "size": match.group(1)})
    if draw_sizes:
        out["drawSizes"] = draw_sizes

    # Verifica se fact sheet exige login
    if "Login to World Tennis Tour Zone for full fact sheet" in text:
        out["factSheetRequiresLogin"] = True

    # Guarda texto cru curto para debug
    out["_text_snippet"] = text[:2000]

    return out


def fetch_fact_sheet_if_authed(tournament_link):
    """
    Se ITF_TOUR_ZONE_EMAIL/PASSWORD estiverem definidos, tenta buscar fact sheet autenticado.
    Por enquanto retorna None e indica que requer login; a implementação completa
    exigiria fluxo de login no Tour Zone (PIN) que varia por ambiente.
    Mantido como hook para futura expansão sem quebrar produção.
    """
    if not (ITF_TOUR_ZONE_EMAIL and ITF_TOUR_ZONE_PASSWORD):
        return None
    # Placeholder: logar via Tour Zone exigiria mapear endpoint de autenticação
    # que não é público. Por segurança, não tenta login automático sem mapear.
    # Retorna indicação para configurar manualmente.
    return {"requires_manual": True, "email": ITF_TOUR_ZONE_EMAIL}


# ---------------------------------------------------------------------------
# Diff de mudanças entre snapshots
# ---------------------------------------------------------------------------
TRACKED_FIELDS = ["tournamentName", "dates", "startDate", "endDate", "location", "venue", "category", "surfaceDesc", "indoorOrOutDoor", "hostNation", "hostNationCode"]

def diff_torneios(old_items, new_items):
    """
    Compara lista antiga e nova por tournamentKey.
    Retorna lista de mudanças: {tournamentKey, tournamentName, field, old, new, type}
    type: added, removed, changed
    """
    old_map = {x.get("tournamentKey"): x for x in (old_items or []) if x.get("tournamentKey")}
    new_map = {x.get("tournamentKey"): x for x in (new_items or []) if x.get("tournamentKey")}
    changes = []
    for key, new in new_map.items():
        if key not in old_map:
            changes.append({"tournamentKey": key, "tournamentName": new.get("tournamentName"), "field": "_all", "old": None, "new": new, "type": "added"})
        else:
            old = old_map[key]
            for field in TRACKED_FIELDS:
                ov = old.get(field) or ""
                nv = new.get(field) or ""
                if ov != nv:
                    changes.append({"tournamentKey": key, "tournamentName": new.get("tournamentName"), "field": field, "old": ov, "new": nv, "type": "changed"})
    for key, old in old_map.items():
        if key not in new_map:
            changes.append({"tournamentKey": key, "tournamentName": old.get("tournamentName"), "field": "_all", "old": old, "new": None, "type": "removed"})
    return changes


# ---------------------------------------------------------------------------
# Impressão de diagnóstico (Parte 1 exigência)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"ENDPOINT: GET {ITF_CALENDAR_BASE_URL}")
    print(f"PARAMS: {DEFAULT_PARAMS} + dateFrom/dateTo")
    print(f"HEADERS: {HEADERS}")
    try:
        ex = fetch_from_itf(take=2)
        print("EXEMPLO JSON (2 itens):")
        print(json.dumps(ex["items"][:2], ensure_ascii=False, indent=2)[:4000])
        print(f"totalItems: {ex['totalItems']}")
    except Exception as e:
        print(f"Erro ao buscar exemplo: {e}")
