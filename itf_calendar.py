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
import requests
from datetime import datetime, date, timedelta

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
