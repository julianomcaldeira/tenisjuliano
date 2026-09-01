"""
fpt_source.py — Fonte de dados da Federação Paulista de Tênis (FPT), TOTALMENTE SEPARADA do ITF.

Área pública SisFPT em https://sisfpt.com.br/area-publica
- Torneios abertos: https://sisfpt.com.br/area-publica/torneios/abertos
  Filtros via GET: ?code=&year=&half=&month=&name=&match=&club=
  Ex: ?year=2024&match=2M2&club=ECP
  Onde match filtra por classe/categoria (ex: 2M1, 2M2 para 2ª classe; 40M, 45M para idade),
  club identifica cidade/clube (ex: ECP = Esporte Clube Pinheiros - São Paulo).
  A página é Laravel e renderiza o HTML direto (não SPA). A tabela, quando há resultados,
  vem no HTML após o form. Se não houver resultados, mostra ícone de pasta vazia.
  Não há bloqueio anti-bot; basta GET com User-Agent.

- Ranking tenistas: https://sisfpt.com.br/area-publica/rankings/tenistas
  Fluxo:
    GET tenistas/ajax/data/{year}       -> JSON lista de datas {key: timestamp, value: dd/mm/yyyy}
    GET tenistas/ajax/categoria/{year}  -> JSON lista de categorias {key: "2M2", value: "2M2"} etc.
    GET rankings/tenistas?year=&date=&category= -> HTML com tabela do ranking
  Ex: ?year=2024&date=1734404400&category=2M2 (onde date é o key do primeiro endpoint)
  Tabela colunas: Pos, Foto, Nome (ex: "25113 - JACK BLANC"), Clube (ECP), Idade, Classe, Pontos.

Se a FPT mudar o endpoint, ajuste FPT_TORNEIOS_URL, FPT_RANKING_URL, FPT_RANKING_DATA_URL abaixo.

Descoberta: curl + playwright em 2026-09-01 confirmou HTML renderizado e AJAX para ranking.
Exemplo torneio: ainda sem exemplo real pois /torneios/abertos com ?year=2024 não retornou linhas
(possível que não haja abertos para esse filtro no momento); fallback para link oficial.
Exemplo ranking: 2024, 17/12/2024, 2M2 retorna 62 linhas, ex: 34 - 25113 - JACK BLANC - AV - 50 - 3 - 327,00
"""

import re
import requests
from datetime import datetime, date, timedelta

FPT_TORNEIOS_URL = "https://sisfpt.com.br/area-publica/torneios/abertos"
FPT_RANKING_URL = "https://sisfpt.com.br/area-publica/rankings/tenistas"
FPT_RANKING_DATA_URL = "https://sisfpt.com.br/area-publica/rankings/tenistas/ajax/data/{year}"
FPT_RANKING_CATEGORIA_URL = "https://sisfpt.com.br/area-publica/rankings/tenistas/ajax/categoria/{year}"
FPT_OFFICIAL_TORNEIOS = "https://sisfpt.com.br/area-publica/torneios/abertos"
FPT_OFFICIAL_RANKING = "https://sisfpt.com.br/area-publica/rankings/tenistas"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

CACHE_TTL_HOURS = 24

# Categorias padrão para o usuário (2ª classe: 2M1/2M2, 40+ e 45+)
DEFAULT_RANKING_CATEGORIES = ["2M1", "2M2", "40M"]
ALL_RANKING_CATEGORIES = ["2M1", "2M2", "40M", "45M"]

def _get_with_headers(url, params=None, headers=None, timeout=15):
    h = headers or HEADERS
    resp = requests.get(url, params=params, headers=h, timeout=timeout)
    resp.raise_for_status()
    return resp

def fetch_torneios_fpt(filters=None):
    """
    Busca torneios abertos via GET com query params.
    filters: dict com keys: code, year, half, month, name, match, club
    Ex: {"year":"2024", "match":"2M2", "club":"ECP"}
    Retorna dict {items: [...], total, fetched_at, url}
    Cada item: {codigo, nome, datas, clube, cidade, categoria, link}
    Se não houver tabela, retorna lista vazia (fallback).
    """
    if filters is None:
        filters = {}
    # Normaliza filtros para query string que o Laravel espera
    params = {}
    for k in ["code", "year", "half", "month", "name", "match", "club"]:
        v = filters.get(k)
        if v:
            params[k] = str(v).strip()

    resp = _get_with_headers(FPT_TORNEIOS_URL, params=params)
    html = resp.text
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        items = []
        # A página usa divs com class ibox para cada torneio; estrutura real:
        # <div class="ibox"><div class="ibox-title">G2 | R$ 190,00</div><div class="ibox-content">2024-25 - COPA ... | YACHT CLUB ... | ESTRADA ... | SÃO PAULO - SP | Inscritos | Chaves ... | 22 | Previsão de Início | 08/03/2024</div></div>
        # O primeiro ibox é o filtro (sem torneio), e há um ibox pai que contém todos juntos; filtramos apenas os que têm título curto e 2 filhos.
        iboxes = soup.find_all("div", class_="ibox")
        for box in iboxes:
            # Só considera ibox que tem exatamente um title e um content (torneio individual)
            title = box.find("div", class_="ibox-title")
            content = box.find("div", class_="ibox-content")
            if not title or not content:
                continue
            title_txt = title.get_text(separator=" | ", strip=True)
            content_txt = content.get_text(separator=" | ", strip=True)
            # Título deve ser curto tipo "G2 | R$ 190,00" e content deve ter COPA
            if "COPA" not in content_txt and "CIRCUITO" not in content_txt and "TORNEIO" not in content_txt:
                continue
            if len(title_txt) > 20:  # filtro tem texto longo, torneio tem curto
                continue
            txt = title_txt + " | " + content_txt
            parts = [p.strip() for p in txt.split("|") if p.strip()]
            nome = ""
            clube = ""
            endereco = ""
            cidade = ""
            categoria = ""
            codigo = ""
            datas = ""
            for p in parts:
                if "COPA" in p or "CIRCUITO" in p or "TORNEIO" in p:
                    nome = p
                    m = re.search(r"(\d{4}-\d+)", p)
                    if m:
                        codigo = m.group(1)
                    break
            if nome:
                idx = parts.index(nome)
                if idx + 1 < len(parts):
                    clube = parts[idx + 1]
                if idx + 2 < len(parts):
                    endereco = parts[idx + 2]
                if idx + 3 < len(parts):
                    cidade = parts[idx + 3]
            for i, p in enumerate(parts):
                if "Previsão de Início" in p and i + 1 < len(parts):
                    datas = parts[i + 1]
                    break
            for p in parts:
                if p in ["G1", "G2", "G3", "G4"]:
                    categoria = p
                    break
            links = {}
            for a in box.find_all("a", href=True):
                href = a.get("href")
                if href and href.startswith("/"):
                    href = "https://sisfpt.com.br" + href
                txt_link = a.get_text(strip=True)
                if "Inscritos" in txt_link:
                    links["inscritos"] = href
                elif "Chaves" in txt_link:
                    links["chaves"] = href
                elif "Chamadas" in txt_link:
                    links["chamadas"] = href
            items.append({
                "codigo": codigo,
                "nome": nome,
                "clube": clube,
                "endereco": endereco,
                "cidade": cidade,
                "categoria": categoria,
                "datas": datas,
                "links": links,
                "raw_text": txt[:1000],
                "html": str(box)[:2000]
            })
        return {
            "items": items,
            "total": len(items),
            "fetched_at": datetime.utcnow().isoformat(),
            "url": resp.url,
            "html_snippet": html[:2000]
        }
    except Exception as e:
        raise RuntimeError(f"Falha ao parsear HTML de torneios FPT: {e}")

def fetch_ranking_categorias(year):
    """GET tenistas/ajax/categoria/{year} -> lista de categorias"""
    url = FPT_RANKING_CATEGORIA_URL.format(year=str(year))
    h = {**HEADERS, "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
    resp = _get_with_headers(url, headers=h)
    # Resposta é JSON com dict de {index: {key, value}}
    data = resp.json()
    # Pode ser dict ou list
    if isinstance(data, dict):
        # Converte para lista de dicts
        items = list(data.values())
    elif isinstance(data, list):
        items = data
    else:
        items = []
    return items

def fetch_ranking_datas(year):
    """GET tenistas/ajax/data/{year} -> lista de datas"""
    url = FPT_RANKING_DATA_URL.format(year=str(year))
    h = {**HEADERS, "X-Requested-With": "XMLHttpRequest", "Accept": "application/json"}
    resp = _get_with_headers(url, headers=h)
    data = resp.json()
    if isinstance(data, dict):
        items = list(data.values())
    elif isinstance(data, list):
        items = data
    else:
        items = []
    return items

def fetch_ranking_fpt(year, date_key, category):
    """
    Busca ranking tenistas via GET rankings/tenistas?year=&date=&category=
    Retorna dict {items: [...], total, fetched_at, url}
    Cada item: {pos, nome, codigo, clube, idade, classe, pontos, link_ficha}
    """
    params = {"year": str(year), "date": str(date_key), "category": str(category)}
    resp = _get_with_headers(FPT_RANKING_URL, params=params)
    html = resp.text
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # Procura tabela de ranking
        tables = soup.find_all("table")
        items = []
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 5:
                    continue
                # Estrutura esperada: pos, foto, nome, clube, idade, classe, pontos
                # cols[0] = pos, cols[2] = nome com código, cols[3]=clube, cols[4]=idade, cols[5]=classe, cols[6]=pontos
                try:
                    pos = cols[0].get_text(strip=True)
                    # Nome vem como "24112 - PAULO MOURA" + link
                    nome_cell = cols[2]
                    nome_text = nome_cell.get_text(separator=" ", strip=True)
                    # Extrai código e nome
                    m = re.search(r"(\d+)\s*-\s*(.+)", nome_text)
                    if m:
                        codigo = m.group(1)
                        nome = m.group(2).split("Ficha")[0].strip()
                    else:
                        codigo = ""
                        nome = nome_text.split("Ficha")[0].strip()
                    # Link ficha
                    link = None
                    a = nome_cell.find("a")
                    if a and a.get("href"):
                        link = a.get("href")
                    clube = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                    idade = cols[4].get_text(strip=True) if len(cols) > 4 else ""
                    # As colunas podem variar; tenta pegar pontos na última
                    pontos = cols[-1].get_text(strip=True) if len(cols) > 5 else ""
                    # Classe não está explícita na tabela, mas vem do filtro category
                    items.append({
                        "pos": pos,
                        "codigo": codigo,
                        "nome": nome,
                        "clube": clube,
                        "idade": idade,
                        "classe": category,
                        "pontos": pontos,
                        "link_ficha": link,
                        "raw": str(row)[:1000]
                    })
                except Exception:
                    continue
        # Se não achou tabela, tenta procurar por divs
        if not items:
            # Pode ser que a tabela esteja em outro formato
            pass

        return {
            "items": items,
            "total": len(items),
            "fetched_at": datetime.utcnow().isoformat(),
            "url": resp.url,
            "year": year,
            "date": date_key,
            "category": category
        }
    except Exception as e:
        raise RuntimeError(f"Falha ao parsear HTML de ranking FPT: {e}")

if __name__ == "__main__":
    print("ENDPOINTS FPT:")
    print(f"Torneios: GET {FPT_TORNEIOS_URL}?code=&year=&half=&month=&name=&match=&club=")
    print(f"Ranking datas: GET {FPT_RANKING_DATA_URL.format(year='2024')}")
    print(f"Ranking categorias: GET {FPT_RANKING_CATEGORIA_URL.format(year='2024')}")
    print(f"Ranking tabela: GET {FPT_RANKING_URL}?year=&date=&category=")
    try:
        print("\n--- Exemplo Torneio (year=2024, match=2M2) ---")
        ex = fetch_torneios_fpt({"year": "2024", "match": "2M2"})
        print(f"total {ex['total']} url {ex['url']}")
        print(f"items preview {str(ex['items'][:2])[:2000]}")
    except Exception as e:
        print(f"Erro torneios: {e}")

    try:
        print("\n--- Exemplo Ranking (2024, 17/12/2024, 2M2) ---")
        ex2 = fetch_ranking_fpt(2024, "1734404400", "2M2")
        print(f"total {ex2['total']} url {ex2['url']}")
        if ex2["items"]:
            print(f"primeira linha {ex2['items'][0]}")
        else:
            print("sem itens")
    except Exception as e:
        print(f"Erro ranking: {e}")
