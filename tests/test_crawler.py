"""Testes locais sem acessar a internet."""
import unittest
from unittest.mock import Mock, patch

import requests
from crawler_arxiv import extrair_artigos, coletar_artigos, obter_html


def html_de_teste(inicio: int, quantidade: int) -> str:
    itens = []
    for i in range(inicio, inicio + quantidade):
        codigo = f"2610.{i:05d}"
        itens.append(
            f'<dt><a href="/abs/{codigo}" title="Abstract">arXiv:{codigo}</a></dt>'
            f'<dd><div class="meta">'
            f'<div class="mathjax list-title">Title:   Artigo   de teste {i}</div>'
            f'<div class="list-authors"><a>Autor {i}</a></div>'
            f'<div class="list-subjects">Subjects: Artificial Intelligence (cs.AI); Testes</div>'
            f'</div></dd>'
        )
    return '<div id="dlpage"><dl>' + "".join(itens) + '</dl></div>'


class TestesCrawler(unittest.TestCase):
    def test_extracao_e_classes_multiplas(self):
        dados = extrair_artigos(html_de_teste(1, 2), pagina=1, data_coleta="2026-10-27")
        self.assertEqual(len(dados), 2)
        self.assertEqual(dados[0]["id_arxiv"], "2610.00001")
        self.assertEqual(dados[0]["titulo"], "Artigo de teste 1")
        self.assertEqual(dados[0]["primeiro_autor"], "Autor 1")
        self.assertEqual(dados[0]["area_principal"], "Artificial Intelligence (cs.AI)")
        self.assertEqual(dados[0]["url"], "https://arxiv.org/abs/2610.00001")

    def test_ignora_entradas_sem_metadados(self):
        html = ("<dl><dt><a href='/abs/2610.00001'>x</a></dt><dd></dd>"
                "<dt><a href='/abs/2610.00002'>y</a></dt>"
                "<dd><div class='list-title'>Title: Válido</div></dd></dl>")
        dados = extrair_artigos(html, 1, "2026-10-27")
        self.assertEqual(len(dados), 1)
        self.assertEqual(dados[0]["titulo"], "Válido")
        self.assertEqual(dados[0]["primeiro_autor"], "Não informado")

    def test_nao_associa_metadados_ao_artigo_errado(self):
        """Se um <dt> não tiver <dd>, não reutilizar o <dd> do próximo artigo."""
        html = (
            '<dl>'
            '<dt><a href="/abs/2610.00001" title="Abstract">Primeiro</a></dt>'
            '<dt><a href="/abs/2610.00002" title="Abstract">Segundo</a></dt>'
            '<dd><div class="list-title">Title: Artigo correto</div></dd>'
            '</dl>'
        )
        dados = extrair_artigos(html, pagina=1, data_coleta="2026-10-28")
        self.assertEqual(len(dados), 1)
        self.assertEqual(dados[0]["id_arxiv"], "2610.00002")
        self.assertEqual(dados[0]["titulo"], "Artigo correto")

    def test_paginacao_ate_35_registros(self):
        with patch("crawler_arxiv.obter_html", side_effect=[
            html_de_teste(1, 25), html_de_teste(26, 25)
        ]) as mock:
            df = coletar_artigos(limite=35, por_pagina=25, atraso=0)
        self.assertEqual(len(df), 35)
        self.assertEqual(df["id_arxiv"].nunique(), 35)
        self.assertEqual(df["pagina"].value_counts().to_dict(), {1: 25, 2: 10})
        self.assertEqual(mock.call_count, 2)

    def test_parametros_get_da_segunda_pagina(self):
        """A página 2 com show=25 precisa solicitar skip=25."""
        sessao = Mock()
        resposta = sessao.get.return_value
        resposta.text = "<html>Teste</html>"
        resposta.apparent_encoding = "utf-8"

        html = obter_html(sessao, pagina=2, por_pagina=25)

        self.assertEqual(html, "<html>Teste</html>")
        sessao.get.assert_called_once_with(
            "https://arxiv.org/list/cs.AI/recent",
            params={"skip": 25, "show": 25},
            timeout=30,
        )
        resposta.raise_for_status.assert_called_once_with()

    def test_erro_http_nao_e_ignorado(self):
        """Falhas HTTP devem ser expostas, e não gerar CSV incompleto."""
        sessao = Mock()
        sessao.get.return_value.raise_for_status.side_effect = requests.HTTPError(
            "429 Too Many Requests"
        )
        with self.assertRaises(requests.HTTPError):
            obter_html(sessao, pagina=1, por_pagina=25)

    def test_nao_aceita_coleta_parcial_acima_de_30(self):
        """Solicitar 50 registros não pode retornar apenas 35 silenciosamente."""
        with patch("crawler_arxiv.obter_html", side_effect=[
            html_de_teste(1, 25),
            html_de_teste(26, 10),
            "<div id='dlpage'><dl></dl></div>",
        ]) as buscar:
            with self.assertRaisesRegex(RuntimeError, "35 de 50 registros solicitados"):
                coletar_artigos(limite=50, por_pagina=25, atraso=0)
        self.assertEqual(buscar.call_count, 3)

    def test_exige_no_minimo_30(self):
        with self.assertRaisesRegex(ValueError, "30 registros"):
            coletar_artigos(limite=20)


if __name__ == "__main__":
    unittest.main()
