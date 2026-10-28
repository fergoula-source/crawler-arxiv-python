Esse projeto é da atividade de web scraping em Python.

Escolhi buscar artigos de inteligência artificial no arXiv: https://arxiv.org/list/cs.AI/recent

Usei requests para acessar as páginas, BeautifulSoup para pegar as informações do HTML e pandas para salvar tudo em CSV. O programa busca título, autor, área e link dos artigos. Para passar de página ele usa os parâmetros skip e show, e também evita registros repetidos.

No HTML usei #dlpage dl dt para achar os artigos, e div.list-title, div.list-authors e div.list-subjects para pegar os dados. Se tiver classe extra ou algum campo faltando, o código tenta tratar isso sem misturar os artigos.

Para rodar no computador, abra o terminal na pasta do projeto e execute:

python -m pip install -r requirements.txt

python crawler_arxiv.py

O resultado fica no arquivo editais_extraidos.csv. Deixei 35 artigos como exemplo, mas rodando o código com internet ele faz uma coleta nova.

Também tem um notebook com o exemplo e alguns testes. Para testar:

python -m unittest discover -s tests -v

Me baseei no exemplo de books.toscrape.com da aula, só adaptei para buscar os artigos do arXiv.
