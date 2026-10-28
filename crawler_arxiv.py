"""Coletor educacional de artigos públicos do arXiv (cs.AI).

Atividade: Construção de um Crawler com Parser e Análise de Editais Públicos.
Foi escolhida a alternativa de preprints científicos do enunciado.

Uso:
    pip install -r requirements.txt
    python crawler_arxiv.py
    python crawler_arxiv.py --limite 40 --por-pagina 25
"""
from __future__ import annotations

import argparse
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

URL_BASE = "https://arxiv.org/list/cs.AI/recent"
URL_ARTIGO = "https://arxiv.org/abs/"
ARQUIVO_SAIDA = "editais_extraidos.csv"  # Nome conforme o enunciado; registros são artigos.
COLUNAS = [
    "id_arxiv", "titulo", "primeiro_autor", "area_principal", "url", "coletado_em", "pagina"
]


def limpar_texto(texto: str) -> str:
    """Remove espaços duplicados e quebras de linha do HTML."""
    return " ".join(texto.split())


def criar_sessao() -> requests.Session:
    """Prepara HTTP com identificador e tentativas moderadas para erros transitórios."""
    sessao = requests.Session()
    sessao.headers.update({
        "User-Agent": "CrawlerAcademico/1.0 (pesquisa educacional; requests + BeautifulSoup)",
        "Accept-Language": "en-US,en;q=0.9",
    })
    politica = Retry(
        total=2,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    sessao.mount("https://", HTTPAdapter(max_retries=politica))
    return sessao


def obter_html(sessao: requests.Session, pagina: int, por_pagina: int) -> str:
    """Busca uma página usando parâmetros GET `skip` e `show`."""
    parametros = {"skip": (pagina - 1) * por_pagina, "show": por_pagina}
    resposta = sessao.get(URL_BASE, params=parametros, timeout=30)
    resposta.raise_for_status()
    resposta.encoding = resposta.apparent_encoding or "utf-8"
    return resposta.text


def analisar_artigo(dt: Tag, dd: Tag, pagina: int, data_coleta: str) -> dict | None:
    """Converte o par <dt>/<dd> de um artigo em um dicionário estruturado.

    Seletores de classe procuram apenas a classe estável; por exemplo,
    `div.list-title` continua válido se o site adicionar a classe `mathjax`.
    Se um campo opcional não existir, ele não interrompe a coleta.
    """
    ancora = dt.select_one("a[title='Abstract']")
    if ancora is None:
        # Fallback caso o arXiv altere o atributo title.
        ancora = dt.find("a", href=re.compile(r"/abs/"))
    titulo_elemento = dd.select_one("div.list-title")
    if ancora is None or titulo_elemento is None:
        return None

    caminho = ancora.get("href", "")
    codigo = caminho.split("/abs/")[-1].split("?")[0].strip("/")
    if not codigo or not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", codigo):
        return None
    titulo = limpar_texto(titulo_elemento.get_text(" ", strip=True))
    titulo = re.sub(r"^Title\s*:\s*", "", titulo, flags=re.IGNORECASE)
    if not titulo:
        return None

    autores_elemento = dd.select_one("div.list-authors")
    primeiro_autor = "Não informado"
    if autores_elemento is not None:
        primeiro_link = autores_elemento.select_one("a")
        texto_autor = primeiro_link.get_text(" ", strip=True) if primeiro_link else autores_elemento.get_text(" ", strip=True)
        primeiro_autor = limpar_texto(re.sub(r"^Authors\s*:\s*", "", texto_autor)) or "Não informado"

    assuntos_elemento = dd.select_one("div.list-subjects")
    area = "Não informado"
    if assuntos_elemento is not None:
        texto_assuntos = limpar_texto(assuntos_elemento.get_text(" ", strip=True))
        texto_assuntos = re.sub(r"^Subjects\s*:\s*", "", texto_assuntos)
        area = texto_assuntos.split(";")[0].strip() or area

    return {
        "id_arxiv": codigo,
        "titulo": titulo,
        "primeiro_autor": primeiro_autor,
        "area_principal": area,
        "url": urljoin(URL_ARTIGO, codigo),
        "coletado_em": data_coleta,
        "pagina": pagina,
    }


def extrair_artigos(html: str, pagina: int, data_coleta: str) -> list[dict]:
    """Percorre as entradas HTML e ignora registros incompletos sem quebrar.

    O site organiza cada artigo como um <dt> (identificador/link) seguido
    por <dd> (metadados). Não dependemos de posições fixas nem de listas
    separadas de títulos e autores que poderiam ficar desalinhadas.
    """
    soup = BeautifulSoup(html, "html.parser")
    itens = soup.select("#dlpage dl dt") or soup.select("dl dt")
    resultados = []
    for dt in itens:
        # O <dd> deve ser o próximo elemento irmão do <dt>.
        # Procurar qualquer <dd> posterior pode associar dados de outro artigo.
        dd = dt.find_next_sibling()
        if dd is None or dd.name != "dd":
            continue
        artigo = analisar_artigo(dt, dd, pagina, data_coleta)
        if artigo:
            resultados.append(artigo)
    return resultados


def coletar_artigos(limite: int = 35, por_pagina: int = 25, atraso: float = 3.0,
                    sessao: requests.Session | None = None) -> pd.DataFrame:
    """Percorre páginas até reunir ao menos `limite` registros únicos."""
    if limite < 30:
        raise ValueError("A atividade exige, no mínimo, 30 registros.")
    if por_pagina not in (25, 50, 100):
        raise ValueError("Use 25, 50 ou 100 resultados por página.")
    if atraso < 0:
        raise ValueError("O atraso não pode ser negativo.")

    sessao = sessao or criar_sessao()
    vistos = set()
    registros = []
    pagina = 1
    hoje = date.today().isoformat()
    paginas_sem_novos = 0
    max_paginas = max(10, (limite // por_pagina) + 8)

    while len(registros) < limite and pagina <= max_paginas:
        print(f"Lendo página {pagina} | skip={(pagina-1)*por_pagina} | show={por_pagina}")
        html = obter_html(sessao, pagina, por_pagina)
        artigos = extrair_artigos(html, pagina, hoje)
        if not artigos:
            print("A página não apresentou artigos reconhecíveis; encerrando.")
            break

        novos = 0
        for artigo in artigos:
            if artigo["id_arxiv"] in vistos:
                continue
            vistos.add(artigo["id_arxiv"])
            registros.append(artigo)
            novos += 1
            if len(registros) >= limite:
                break

        print(f"  -> {novos} novos; total: {len(registros)}")
        paginas_sem_novos = paginas_sem_novos + 1 if novos == 0 else 0
        if paginas_sem_novos >= 2:
            print("Duas páginas sem registros novos; evitando loop infinito.")
            break
        pagina += 1
        if len(registros) < limite and atraso:
            time.sleep(atraso)

    df = pd.DataFrame(registros, columns=COLUNAS)
    if len(df) < limite:
        raise RuntimeError(
            f"Coleta insuficiente: {len(df)} de {limite} registros solicitados. "
            "Verifique sua conexão, o bloqueio temporário do site e os seletores CSS."
        )
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Coleta artigos recentes de Inteligência Artificial do arXiv.")
    parser.add_argument("--limite", type=int, default=35, help="Registros desejados (mínimo 30).")
    parser.add_argument("--por-pagina", type=int, default=25, choices=[25, 50, 100],
                        help="Quantidade por página (GET show; padrão: 25).")
    parser.add_argument("--atraso", type=float, default=3.0, help="Pausa entre solicitações, em segundos.")
    parser.add_argument("--saida", default=ARQUIVO_SAIDA, help="Nome do CSV de saída.")
    parser.add_argument("--json", action="store_true", help="Também exporta JSON.")
    args = parser.parse_args()
    df = coletar_artigos(args.limite, args.por_pagina, args.atraso)
    arquivo = Path(args.saida)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(arquivo, sep=",", encoding="utf-8-sig", index=False)
    print(f"\nArquivo gerado: {arquivo.resolve()} ({len(df)} artigos)")
    print(df[["id_arxiv", "titulo", "pagina"]].head().to_string(index=False))
    if args.json:
        arquivo_json = arquivo.with_suffix(".json")
        df.to_json(arquivo_json, orient="records", force_ascii=False, indent=2)
        print(f"JSON gerado: {arquivo_json.resolve()}")


if __name__ == "__main__":
    main()