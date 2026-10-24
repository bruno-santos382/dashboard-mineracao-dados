# Dashboard: repositórios populares do GitHub

Script em Python que carrega dados do Kaggle e gera um **dashboard em um único arquivo HTML**, com 7 gráficos interativos (Plotly). Cada gráfico responde a uma pergunta escrita no próprio card, e o texto "O que os dados mostram" é calculado a partir dos dados.

Base de dados: [GitHub Repos (Kaggle, donbarbos)](https://www.kaggle.com/datasets/donbarbos/github-repos) - carregada automaticamente via kagglehub

## O que o dashboard responde

| Pergunta | Gráfico |
|---|---|
| Quantos repositórios foram criados em cada ano? | Linha |
| Repositórios mais antigos têm mais estrelas? | Barras verticais |
| Quais são as 10 linguagens com mais repositórios? | Barras horizontais |
| Qual licença os repositórios populares usam? | Rosca (5 fatias) |
| Alguma linguagem concentra repositórios com mais estrelas? | Boxplot |
| Como as estrelas se distribuem? | Histograma |
| Repositórios com mais estrelas também têm mais forks? | Dispersão |

## Arquivos

- `gerar_dashboard.py`: carrega os dados do Kaggle, cria os gráficos e monta o HTML.
- `template.html`: layout e estilo da página (os gráficos entram nos marcadores `{{...}}`).
- `requirements.txt`: dependências do projeto.

## Como rodar

1. Instale as dependências (Python 3.9 ou mais novo):

   ```powershell
   pip install -r requirements.txt
   ```

2. Gere o dashboard:

   ```powershell
   python gerar_dashboard.py
   ```

3. Abra o `dashboard.html` gerado em qualquer navegador. Não precisa de internet nem de instalar nada: a biblioteca Plotly vai embutida no arquivo (por isso ele tem cerca de 20 MB).

## Colunas usadas do dataset

`Name`, `Created At`, `Updated At`, `Stars`, `Forks`, `Language` e `License`. Se alguma faltar, o script avisa e para.

## Observações

- O último ano é tratado como **parcial** quando a base foi atualizada antes de 31/12; ele aparece tracejado e com legenda.
- Repositórios sem linguagem ficam fora do ranking de linguagens. Os com zero estrelas ou forks ficam fora dos gráficos em escala logarítmica. Os textos do dashboard avisam quando isso acontece.