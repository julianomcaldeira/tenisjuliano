"""
Leitor do ranking no perfil público da ITF (Masters Tour).

IMPORTANTE — precisa de UM ajuste quando o perfil do Juliano estiver ativo em 2027.
Hoje ainda não existe a página real, então não dá para saber a estrutura exata do HTML.
Quando o perfil existir, abra a página no navegador, veja onde aparece o número do
ranking (clicar com o botão direito > Inspecionar) e ajuste os seletores em
_extract_rank(). Enquanto isso, dá para registrar o ranking manualmente no app —
o gráfico de evolução funciona igual.
"""
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def fetch_ranking(profile_url):
    """Baixa a página do perfil e tenta extrair posição, pontos e categoria.
    Retorna dict {rank, points, category} ou None."""
    try:
        resp = requests.get(profile_url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return None
    return _extract_rank(resp.text)


def _extract_rank(html):
    """Heurística tolerante. AJUSTE AQUI quando conhecer o HTML real do perfil.

    Estratégia atual: procura por padrões de texto como 'Ranking 1234' ou
    'Rank: 1234' e por 'pts'/'points'. É um ponto de partida seguro; o ideal,
    com a página real em mãos, é trocar por soup.select('...') apontando para
    o elemento certo.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = " ".join(soup.get_text(" ").split())

    rank = None
    m = re.search(r"(?:rank(?:ing)?)\D{0,15}(\d{1,6})", text, re.IGNORECASE)
    if m:
        rank = int(m.group(1))

    points = None
    p = re.search(r"(\d[\d.,]*)\s*(?:pts|points|pontos)", text, re.IGNORECASE)
    if p:
        raw = p.group(1).replace(".", "").replace(",", ".")
        try:
            points = float(raw)
        except ValueError:
            points = None

    category = "45+"
    c = re.search(r"\b(30|35|40|45|50|55|60|65|70)\s*\+", text)
    if c:
        category = c.group(1) + "+"

    if rank is None:
        return None
    return {"rank": rank, "points": points, "category": category}
