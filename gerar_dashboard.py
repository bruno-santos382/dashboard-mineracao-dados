#!/usr/bin/env python3
"""
Gera o dashboard "Repositórios populares do GitHub" em um único arquivo HTML.

Uso (com os três arquivos na mesma pasta):
    python gerar_dashboard.py

Dependências: pandas, numpy e plotly  ->  pip install -r requirements.txt

O HTML final leva a biblioteca Plotly embutida, então abre em qualquer
navegador, mesmo sem internet e sem instalar nada.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

PASTA_DO_SCRIPT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Identidade visual (a mesma paleta em todos os gráficos)
#   - azul-petróleo: cor padrão de qualquer dado
#   - âmbar: usado SEMPRE e somente para destacar o valor máximo / os destaques
#   - cinza: referência (linha de tendência, categoria "demais")
# Nenhuma escala contínua em arco-íris: só tons de uma cor.
# ---------------------------------------------------------------------------
COR_PRINCIPAL = "#1F6F8B"
COR_DESTAQUE = "#D98E04"
COR_NEUTRA = "#9AA7AF"
COR_TEXTO = "#16252D"
COR_GRADE = "#E3E8EB"
COR_PREENCHIMENTO = "rgba(31, 111, 139, 0.22)"
TONS_PETROLEO = ["#14516A", "#1F6F8B", "#5A9DB5", "#A5C8D6"]  # fatias de composição

FONTE = "'Segoe UI Variable', 'Segoe UI', system-ui, -apple-system, Roboto, 'Helvetica Neue', Arial, sans-serif"

CONFIG_PLOTLY = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
}

MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

COLUNAS_ORIGINAIS = {
    "Name": "nome",
    "Created At": "criado_em",
    "Updated At": "atualizado_em",
    "Stars": "estrelas",
    "Forks": "forks",
    "Language": "linguagem",
    "License": "licenca",
}


# ---------------------------------------------------------------------------
# Formatação de números no padrão brasileiro
# ---------------------------------------------------------------------------
def fmt_int(n: float) -> str:
    """12345 -> '12.345'"""
    return f"{int(round(n)):,}".replace(",", ".")


def _casas(v: float, casas: int) -> str:
    s = f"{v:.{casas}f}".replace(".", ",")
    return s.rstrip("0").rstrip(",") if "," in s else s


def fmt_compacto(n: float) -> str:
    """66680 -> '66,7 mil' | 1250000 -> '1,25 mi' | 80 -> '80'"""
    n = float(n)
    if n >= 1e6:
        return f"{_casas(n / 1e6, 2)} mi"
    if n >= 1e3:
        return f"{_casas(n / 1e3, 1)} mil"
    return fmt_int(n)


def fmt_mil(n: float) -> str:
    """Rótulo em duas linhas para barras estreitas: 162499 -> '162<br>mil'"""
    if 1e3 <= n < 1e4:
        return f"{_casas(n / 1e3, 1)}<br>mil"
    if 1e4 <= n < 1e6:
        return f"{round(n / 1e3)}<br>mil"
    return fmt_compacto(n).replace(" ", "<br>")


def fmt_pct(p: float) -> str:
    return f"{_casas(p, 1)}%"


def fmt_dec(v: float, casas: int = 2) -> str:
    return f"{v:.{casas}f}".replace(".", ",")


def esc(texto: str) -> str:
    return html.escape(str(texto), quote=False)


# ---------------------------------------------------------------------------
# Leitura e preparo dos dados
# ---------------------------------------------------------------------------
def carregar_dados(caminho: Path) -> pd.DataFrame:
    if not caminho.exists():
        sys.exit(f"Erro: não encontrei o arquivo de dados em '{caminho}'.")

    df = pd.read_csv(caminho, encoding="utf-8-sig")

    faltando = [c for c in COLUNAS_ORIGINAIS if c not in df.columns]
    if faltando:
        sys.exit(f"Erro: o CSV não tem as colunas esperadas: {', '.join(faltando)}")

    df = df[list(COLUNAS_ORIGINAIS)].rename(columns=COLUNAS_ORIGINAIS)
    df["criado_em"] = pd.to_datetime(df["criado_em"], utc=True, errors="coerce")
    df["atualizado_em"] = pd.to_datetime(df["atualizado_em"], utc=True, errors="coerce")
    df["estrelas"] = pd.to_numeric(df["estrelas"], errors="coerce")
    df["forks"] = pd.to_numeric(df["forks"], errors="coerce")

    antes = len(df)
    df = df.dropna(subset=["criado_em", "estrelas", "forks"]).copy()
    if len(df) < antes:
        print(f"Aviso: {antes - len(df)} linha(s) ignorada(s) por data ou número inválido.")
    if df.empty:
        sys.exit("Erro: nenhuma linha válida no CSV.")

    df["ano"] = df["criado_em"].dt.year
    return df


# ---------------------------------------------------------------------------
# Utilidades de layout
# ---------------------------------------------------------------------------
def ticks_log(log_min: float, log_max: float) -> tuple[list[float], list[str]]:
    """Marcas "redondas" (1, 2, 5 x 10^k) para um eixo logarítmico.

    Recebe o intervalo em log10 e devolve valores reais + rótulos em pt-BR.
    Usa poucas marcas quando o intervalo é longo e mais marcas quando é curto.
    """
    k_ini, k_fim = int(np.floor(log_min)) - 1, int(np.ceil(log_max)) + 1
    for multiplicadores in ([1], [1, 2, 5], [1, 2, 3, 4, 5, 6, 8]):
        valores = [
            m * 10.0 ** k
            for k in range(k_ini, k_fim + 1)
            for m in multiplicadores
            if log_min <= np.log10(m * 10.0 ** k) <= log_max
        ]
        if len(valores) >= 3:
            break
    return valores, [fmt_compacto(v) for v in valores]


def aplicar_layout(fig: go.Figure, titulo: str, titulo_x: str | None, titulo_y: str | None,
                   altura: int = 400, margem: dict | None = None) -> go.Figure:
    fig.update_layout(
        title=dict(text=f"<b>{titulo}</b>", x=0, xanchor="left", font=dict(size=15, color=COR_TEXTO)),
        font=dict(family=FONTE, size=13, color=COR_TEXTO),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=margem or dict(l=72, r=24, t=56, b=64),
        height=altura,
        separators=",.",  # decimal com vírgula, milhar com ponto
        showlegend=False,
        hoverlabel=dict(font=dict(family=FONTE, color=COR_TEXTO), bgcolor="white", bordercolor=COR_GRADE),
    )
    fig.update_xaxes(
        title=dict(text=titulo_x, standoff=10, font=dict(size=13, color=COR_TEXTO)) if titulo_x else None,
        tickfont=dict(size=12, color=COR_TEXTO),
        showgrid=False, linecolor=COR_NEUTRA, ticks="outside", tickcolor=COR_NEUTRA,
    )
    fig.update_yaxes(
        title=dict(text=titulo_y, standoff=10, font=dict(size=13, color=COR_TEXTO)) if titulo_y else None,
        tickfont=dict(size=12, color=COR_TEXTO),
        gridcolor=COR_GRADE, zeroline=False, ticks="", automargin=True,
    )
    return fig


def ajustar_eixo_anos(fig: go.Figure, anos: list[int]) -> None:
    """Eixo X de anos: um rótulo por ano (ou a cada 2, se forem muitos) e sem sobras nas pontas."""
    fig.update_xaxes(dtick=1 if len(anos) <= 20 else 2, tickformat="d",
                     tickangle=-45 if len(anos) > 10 else 0,
                     range=[min(anos) - 0.6, max(anos) + 0.6])


def para_html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config=CONFIG_PLOTLY,
                       default_width="100%", default_height=f"{fig.layout.height}px")


# ---------------------------------------------------------------------------
# Gráfico 1: linha do tempo (série temporal)
# ---------------------------------------------------------------------------
def grafico_repos_por_ano(df: pd.DataFrame) -> tuple[go.Figure, str, dict]:
    anual = df.groupby("ano").size()
    anual = anual.reindex(range(int(anual.index.min()), int(anual.index.max()) + 1), fill_value=0)
    anos, valores = list(anual.index), [int(v) for v in anual.values]

    # O último ano é parcial se a base foi atualizada antes de 31/12 desse ano.
    data_ref = df["atualizado_em"].max()
    parcial = bool(pd.notna(data_ref) and anos[-1] == data_ref.year and (data_ref.month, data_ref.day) < (12, 31))
    nota_ref = f"{MESES[data_ref.month - 1]}/{data_ref.year}" if pd.notna(data_ref) else ""

    i_pico = int(np.argmax(valores))
    cores = [COR_PRINCIPAL] * len(anos)
    cores[i_pico] = COR_DESTAQUE
    tamanhos = [8] * len(anos)
    tamanhos[i_pico] = 12

    n_solido = len(anos) - 1 if (parcial and len(anos) > 1) else len(anos)
    hover = "<b>%{x}</b><br>%{y} repositórios<extra></extra>"

    # Com muitos anos os rótulos se atropelam: nesse caso, só primeiro, pico e último ponto.
    if len(anos) <= 12:
        rotulos = [fmt_int(v) for v in valores]
    else:
        chaves = {0, i_pico, len(anos) - 1}
        rotulos = [fmt_int(v) if i in chaves else "" for i, v in enumerate(valores)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=anos[:n_solido], y=valores[:n_solido], mode="lines+markers+text", name="Ano completo",
        text=rotulos[:n_solido], textposition="top center",
        line=dict(color=COR_PRINCIPAL, width=2.5),
        marker=dict(color=cores[:n_solido], size=tamanhos[:n_solido]),
        hovertemplate=hover,
    ))
    if n_solido < len(anos):  # trecho tracejado = ano incompleto
        fig.add_trace(go.Scatter(
            x=anos[-2:], y=valores[-2:], mode="lines+markers+text", name=f"Ano parcial (dados até {nota_ref})",
            text=["", rotulos[-1]], textposition="top center",
            line=dict(color=COR_PRINCIPAL, width=2.5, dash="dot"),
            marker=dict(color=[COR_PRINCIPAL, cores[-1]], size=[0, tamanhos[-1]],
                        symbol=["circle", "circle-open"], line=dict(width=2, color=cores[-1])),
            hovertemplate="<b>%{x} (parcial)</b><br>%{y} repositórios até " + nota_ref + "<extra></extra>",
        ))

    aplicar_layout(fig, "Repositórios criados por ano (quantidade)", "Ano de criação", "Repositórios criados (quantidade)",
                   altura=450 if parcial else 400,
                   margem=dict(l=72, r=24, t=56, b=140 if parcial else 70))
    fig.update_yaxes(range=[0, max(valores) * 1.22], rangemode="tozero", tickformat=",d")
    if parcial:  # legenda explica a linha pontilhada (aplicada depois do layout base, que a desliga)
        fig.update_layout(showlegend=True, legend=dict(orientation="h", x=0, y=-0.36, font=dict(size=13, color=COR_TEXTO)))
    ajustar_eixo_anos(fig, anos)

    total = sum(valores)
    texto = (f"O ano com mais criações foi <strong>{anos[i_pico]}</strong>, com "
             f"<strong>{fmt_int(valores[i_pico])}</strong> repositórios ({fmt_pct(100 * valores[i_pico] / total)} do total).")
    if parcial:
        texto += f" O último ponto (tracejado) é parcial: os dados vão só até {nota_ref}, então ele tende a subir."
    return fig, texto, {"parcial": parcial}


# ---------------------------------------------------------------------------
# Gráfico 2: ranking de linguagens (barras horizontais, eixo em zero)
# ---------------------------------------------------------------------------
def grafico_top_linguagens(df: pd.DataFrame) -> tuple[go.Figure, str]:
    com_ling = df.dropna(subset=["linguagem"])
    contagem = com_ling["linguagem"].value_counts().head(10)
    nomes, valores = list(contagem.index), [int(v) for v in contagem.values]
    pct = [100 * v / len(com_ling) for v in valores]
    cores = [COR_DESTAQUE] + [COR_PRINCIPAL] * (len(nomes) - 1)

    fig = go.Figure(go.Bar(
        x=valores, y=nomes, orientation="h", marker_color=cores,
        text=[f"{fmt_int(v)}  ({fmt_pct(p)})" for v, p in zip(valores, pct)], textposition="outside",
        cliponaxis=False, textfont=dict(size=12, color=COR_TEXTO),
        hovertemplate="<b>%{y}</b><br>%{x} repositórios<extra></extra>",
    ))
    aplicar_layout(fig, "As 10 linguagens com mais repositórios (quantidade)",
                   "Repositórios (quantidade)", "Linguagem principal",
                   margem=dict(l=90, r=90, t=56, b=64))
    fig.update_xaxes(range=[0, max(valores) * 1.05], showgrid=True, gridcolor=COR_GRADE)
    fig.update_yaxes(autorange="reversed", showgrid=False)

    sem_ling = len(df) - len(com_ling)
    soma10 = 100 * sum(valores) / len(com_ling)
    texto = (f"<strong>{esc(nomes[0])}</strong> lidera, com {fmt_int(valores[0])} repositórios. "
             f"As 10 linguagens juntas reúnem {fmt_pct(soma10)} dos repositórios que têm linguagem identificada.")
    if sem_ling:
        texto += f" Não entram na conta {fmt_int(sem_ling)} repositórios sem linguagem principal (listas, documentação etc.)."
    return fig, texto


# ---------------------------------------------------------------------------
# Gráfico 3: composição por licença (pizza/rosca com no máximo 5 fatias)
# ---------------------------------------------------------------------------
def grafico_licencas(df: pd.DataFrame) -> tuple[go.Figure, str]:
    def categoria(lic):
        # "NOASSERTION" é como o GitHub marca licenças que não reconhece
        return "Não identificada" if pd.isna(lic) or lic == "NOASSERTION" else str(lic)

    contagem = df["licenca"].map(categoria).value_counts()
    maiores = contagem.head(4)
    nomes, valores = list(maiores.index), [int(v) for v in maiores.values]
    cores = TONS_PETROLEO[: len(nomes)]
    resto = int(contagem.iloc[4:].sum())
    if resto > 0:
        nomes.append("Demais licenças")
        valores.append(resto)
        cores = cores + [COR_NEUTRA]

    total = sum(valores)
    textos = [f"<b>{n}</b><br>{fmt_int(v)} · {fmt_pct(100 * v / total)}" for n, v in zip(nomes, valores)]

    fig = go.Figure(go.Pie(
        labels=nomes, values=valores, hole=0.55, sort=False, direction="clockwise",
        marker=dict(colors=cores, line=dict(color="white", width=2)),
        text=textos, textinfo="text", textposition="outside", textfont=dict(size=12, color=COR_TEXTO),
        hovertemplate="<b>%{label}</b><br>%{value} repositórios (%{percent})<extra></extra>",
    ))
    aplicar_layout(fig, "Participação de cada licença (% dos repositórios)", None, None,
                   margem=dict(l=70, r=70, t=56, b=30))
    fig.add_annotation(text=f"<b>{fmt_int(total)}</b><br>repositórios", showarrow=False,
                       font=dict(size=13, color=COR_TEXTO))

    texto = (f"<strong>{esc(nomes[0])}</strong> é o tipo mais comum, presente em "
             f"{fmt_pct(100 * valores[0] / total)} dos repositórios. ")
    nao_id = contagem.get("Não identificada", 0)
    if nao_id:
        texto += (f"{fmt_pct(100 * nao_id / total)} não têm licença reconhecida pelo GitHub "
                  f"(sem licença ou com texto personalizado).")
    return fig, texto


# ---------------------------------------------------------------------------
# Gráfico 4: estrelas por linguagem (boxplot, escala log)
# ---------------------------------------------------------------------------
def grafico_estrelas_por_linguagem(df: pd.DataFrame) -> tuple[go.Figure, str]:
    com_ling = df.dropna(subset=["linguagem"])
    top5 = list(com_ling["linguagem"].value_counts().head(5).index)

    fig = go.Figure()
    medianas = {}
    for lg in top5:
        est = com_ling.loc[com_ling["linguagem"] == lg, "estrelas"]
        medianas[lg] = float(est.median())
        rotulo = f"<b>{lg}</b><br>n = {fmt_int(len(est))}<br>mediana: {fmt_compacto(medianas[lg])}"
        fig.add_trace(go.Box(
            y=est, x=[rotulo] * len(est), name=lg, boxpoints="outliers",
            marker=dict(color=COR_PRINCIPAL, size=4, opacity=0.55),
            line=dict(color=COR_PRINCIPAL, width=1.6), fillcolor=COR_PREENCHIMENTO,
            hovertemplate="%{y:,} estrelas<extra>" + lg + "</extra>",
        ))

    # pontos isolados acima da haste superior (limite de Tukey: Q3 + 1,5 x IQR)
    n_isolados = 0
    for lg in top5:
        est = com_ling.loc[com_ling["linguagem"] == lg, "estrelas"]
        q1, q3 = est.quantile([0.25, 0.75])
        n_isolados += int((est > q3 + 1.5 * (q3 - q1)).sum())

    todos = com_ling.loc[com_ling["linguagem"].isin(top5), "estrelas"]
    lmin, lmax = np.log10(todos.min()) - 0.1, np.log10(todos.max()) + 0.1
    vals, txt = ticks_log(lmin, lmax)
    aplicar_layout(fig, "Distribuição de estrelas nas 5 linguagens mais frequentes", "Linguagem principal",
                   "Estrelas (escala logarítmica)", altura=440, margem=dict(l=80, r=24, t=56, b=110))
    fig.update_yaxes(type="log", range=[lmin, lmax], tickvals=vals, ticktext=txt)

    melhor = max(medianas, key=medianas.get)
    texto = (f"Entre as 5 linguagens, <strong>{esc(melhor)}</strong> tem a maior mediana "
             f"({fmt_int(medianas[melhor])} estrelas), mas as caixas se sobrepõem bastante: a linguagem "
             f"diz pouco sobre a popularidade do repositório.")
    if n_isolados:
        if n_isolados == 1:
            texto += " 1 repositório aparece como ponto isolado acima da haste, um campeão de estrelas."
        else:
            texto += (f" {fmt_int(n_isolados)} repositórios aparecem como pontos isolados acima das hastes, "
                      f"os campeões de estrelas.")
    return fig, texto


# ---------------------------------------------------------------------------
# Gráfico 5: distribuição de estrelas (histograma, escala log)
# ---------------------------------------------------------------------------
def grafico_histograma_estrelas(df: pd.DataFrame) -> tuple[go.Figure, str]:
    est = df.loc[df["estrelas"] > 0, "estrelas"]
    logs = np.log10(est.values)
    amplitude = logs.max() - logs.min()
    largura = 0.05 if amplitude < 1.2 else 0.1
    inicio = np.floor(logs.min() / largura) * largura
    bordas = np.arange(inicio, logs.max() + largura, largura)
    if len(bordas) < 2:
        bordas = np.array([inicio, inicio + largura])
    contagem, bordas = np.histogram(logs, bins=bordas)
    centros = (bordas[:-1] + bordas[1:]) / 2
    de, ate = 10 ** bordas[:-1], 10 ** bordas[1:]
    faixas = [f"{fmt_int(a)} a {fmt_int(b)}" for a, b in zip(de, ate)]

    fig = go.Figure(go.Bar(
        x=centros, y=contagem, width=largura * 0.92, marker_color=COR_PRINCIPAL,
        customdata=np.column_stack([faixas]),
        hovertemplate="Entre %{customdata[0]} estrelas<br><b>%{y} repositórios</b><extra></extra>",
    ))
    mediana = float(est.median())
    fig.add_vline(x=np.log10(mediana), line=dict(color=COR_TEXTO, width=1.5, dash="dash"),
                  annotation_text=f"Mediana: {fmt_int(mediana)}", annotation_position="top",
                  annotation_font=dict(size=12, color=COR_TEXTO))

    vals, txt = ticks_log(bordas[0], bordas[-1])
    aplicar_layout(fig, "Distribuição do número de estrelas (repositórios por faixa)",
                   "Estrelas por repositório (escala logarítmica)", "Repositórios (quantidade)")
    fig.update_xaxes(tickvals=np.log10(vals), ticktext=txt, range=[bordas[0] - largura, bordas[-1] + largura])
    fig.update_yaxes(range=[0, max(contagem) * 1.25])

    p90 = float(est.quantile(0.9))
    texto = (f"A metade dos repositórios tem até <strong>{fmt_int(mediana)}</strong> estrelas, mas os 10% mais "
             f"populares passam de {fmt_int(p90)} e o maior chega a {fmt_int(est.max())}. "
             f"A distribuição é muito assimétrica: muitos repositórios no começo e uma cauda longa de campeões.")
    return fig, texto


# ---------------------------------------------------------------------------
# Gráfico 6: estrelas x forks (dispersão, escala log nos dois eixos)
# ---------------------------------------------------------------------------
def grafico_estrelas_vs_forks(df: pd.DataFrame) -> tuple[go.Figure, str]:
    d = df[(df["estrelas"] > 0) & (df["forks"] > 0)]
    excluidos = len(df) - len(d)
    lx, ly = np.log10(d["forks"].values), np.log10(d["estrelas"].values)
    rho = float(d["estrelas"].rank().corr(d["forks"].rank()))  # correlação de Spearman

    Scatter = go.Scattergl if len(d) > 2000 else go.Scatter
    opac = 0.75 if len(d) < 500 else 0.3
    fig = go.Figure()
    fig.add_trace(Scatter(
        x=d["forks"], y=d["estrelas"], mode="markers", name="Repositório",
        marker=dict(color=COR_PRINCIPAL, size=7, opacity=opac), hovertext=d["nome"],
        hovertemplate="<b>%{hovertext}</b><br>Forks: %{x:,}<br>Estrelas: %{y:,}<extra></extra>",
    ))

    if len(d) >= 3:  # linha de tendência ajustada no espaço logarítmico
        b, a = np.polyfit(lx, ly, 1)
        xs = np.linspace(lx.min(), lx.max(), 50)
        fig.add_trace(go.Scatter(x=10 ** xs, y=10 ** (a + b * xs), mode="lines", name="Tendência",
                                 line=dict(color=COR_TEXTO, width=2, dash="dash"), hoverinfo="skip"))

    top3 = d.nlargest(3, "estrelas")
    fig.add_trace(go.Scatter(
        x=top3["forks"], y=top3["estrelas"], mode="markers+text", name="3 mais estrelados",
        text=top3["nome"], textposition="middle left", textfont=dict(size=12, color=COR_TEXTO),
        marker=dict(color=COR_DESTAQUE, size=10, line=dict(color="white", width=1)),
        hovertemplate="<b>%{text}</b><br>Forks: %{x:,}<br>Estrelas: %{y:,}<extra></extra>",
    ))

    rx, ry = (lx.min() - 0.1, lx.max() + 0.25), (ly.min() - 0.1, ly.max() + 0.1)
    vx, tx = ticks_log(*rx)
    vy, ty = ticks_log(*ry)
    aplicar_layout(fig, "Estrelas x forks por repositório (um ponto = um repositório)",
                   "Forks (quantidade, escala logarítmica)", "Estrelas (quantidade, escala logarítmica)",
                   altura=440, margem=dict(l=80, r=24, t=56, b=90))
    fig.update_layout(showlegend=True, legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=13, color=COR_TEXTO)))
    fig.update_xaxes(type="log", range=list(rx), tickvals=vx, ticktext=tx, showgrid=True, gridcolor=COR_GRADE)
    fig.update_yaxes(type="log", range=list(ry), tickvals=vy, ticktext=ty)

    if rho >= 0.7:
        veredito = f"Sim, de forma clara: a correlação de Spearman é <strong>{fmt_dec(rho)}</strong> (forte)."
    elif rho >= 0.4:
        veredito = f"Em parte: a correlação de Spearman é <strong>{fmt_dec(rho)}</strong> (moderada)."
    else:
        veredito = f"Pouco: a correlação de Spearman é <strong>{fmt_dec(rho)}</strong> (fraca)."
    texto = veredito + " Mostra que as duas medidas andam juntas, não que uma cause a outra."
    if excluidos:
        texto += f" {fmt_int(excluidos)} repositórios com zero forks ou estrelas ficam de fora da escala logarítmica."
    return fig, texto


# ---------------------------------------------------------------------------
# Gráfico 7: mediana de estrelas por ano de criação (barras verticais, eixo em zero)
# ---------------------------------------------------------------------------
def grafico_mediana_por_ano(df: pd.DataFrame, parcial: bool) -> tuple[go.Figure, str]:
    g = df.groupby("ano")["estrelas"].agg(["median", "size"])
    anos = list(g.index)
    med = [float(v) for v in g["median"]]
    n = [int(v) for v in g["size"]]
    i_max = int(np.argmax(med))
    cores = [COR_PRINCIPAL] * len(anos)
    cores[i_max] = COR_DESTAQUE

    fig = go.Figure(go.Bar(
        x=anos, y=med, marker_color=cores, customdata=n,
        text=[fmt_mil(v) for v in med], textposition="outside", cliponaxis=False,
        textfont=dict(size=12, color=COR_TEXTO), textangle=0,
        hovertemplate="<b>%{x}</b><br>Mediana: %{y:,.0f} estrelas<br>%{customdata} repositórios no ano<extra></extra>",
    ))
    aplicar_layout(fig, "Mediana de estrelas por ano de criação (estrelas)", "Ano de criação",
                   "Mediana de estrelas (quantidade)")
    fig.update_yaxes(range=[0, max(med) * 1.25], rangemode="tozero", tickformat=",d")
    ajustar_eixo_anos(fig, anos)

    texto = (f"Os repositórios criados em <strong>{anos[i_max]}</strong> têm a maior mediana "
             f"({fmt_int(med[i_max])} estrelas). A mediana resume o repositório \"típico\" de cada ano "
             f"sem ser puxada pelos campeões.")
    if min(n) < 10:
        texto += " Anos com poucos repositórios oscilam mais."
    if parcial:
        texto += " O último ano é parcial."
    return fig, texto


# ---------------------------------------------------------------------------
# Montagem do HTML
# ---------------------------------------------------------------------------
def montar_html(template: str, valores: dict[str, str]) -> str:
    """Substitui {{CHAVE}} em uma única passada (o conteúdo inserido nunca é reprocessado)."""
    def troca(m: re.Match) -> str:
        chave = m.group(1)
        if chave not in valores:
            raise KeyError(f"Marcador {{{{{chave}}}}} do template não foi preenchido.")
        return valores[chave]
    return re.sub(r"\{\{(\w+)\}\}", troca, template)


def main() -> None:
    csv_path = PASTA_DO_SCRIPT / "repositories.csv"
    template_path = PASTA_DO_SCRIPT / "template.html"
    saida_path = PASTA_DO_SCRIPT / "dashboard.html"

    if not template_path.exists():
        sys.exit(f"Erro: template não encontrado em '{template_path}'.")

    df = carregar_dados(csv_path)
    print(f"{len(df)} repositórios carregados de '{csv_path.name}'.")

    fig1, txt1, info = grafico_repos_por_ano(df)
    fig2, txt2 = grafico_top_linguagens(df)
    fig3, txt3 = grafico_licencas(df)
    fig4, txt4 = grafico_estrelas_por_linguagem(df)
    fig5, txt5 = grafico_histograma_estrelas(df)
    fig6, txt6 = grafico_estrelas_vs_forks(df)
    fig7, txt7 = grafico_mediana_por_ano(df, info["parcial"])

    data_ref = df["atualizado_em"].max()
    data_ref_txt = f"{MESES[data_ref.month - 1]}/{data_ref.year}" if pd.notna(data_ref) else "data não informada"

    valores = {
        "TITULO_PAGINA": "Repositórios populares do GitHub",
        "KPI_REPOS": fmt_int(len(df)),
        "KPI_ESTRELAS": fmt_compacto(df["estrelas"].sum()),
        "KPI_LINGUAGENS": fmt_int(df["linguagem"].nunique()),
        "KPI_PERIODO": f"{int(df['ano'].min())}–{int(df['ano'].max())}",
        "DATA_REF": data_ref_txt,
        "GRAFICO_ANOS": para_html(fig1), "LEITURA_ANOS": txt1,
        "GRAFICO_LINGUAGENS": para_html(fig2), "LEITURA_LINGUAGENS": txt2,
        "GRAFICO_LICENCAS": para_html(fig3), "LEITURA_LICENCAS": txt3,
        "GRAFICO_BOXPLOT": para_html(fig4), "LEITURA_BOXPLOT": txt4,
        "GRAFICO_HISTOGRAMA": para_html(fig5), "LEITURA_HISTOGRAMA": txt5,
        "GRAFICO_DISPERSAO": para_html(fig6), "LEITURA_DISPERSAO": txt6,
        "GRAFICO_MEDIANA": para_html(fig7), "LEITURA_MEDIANA": txt7,
        "PLOTLY_JS": get_plotlyjs(),  # biblioteca embutida: o arquivo funciona offline
    }

    saida = montar_html(template_path.read_text(encoding="utf-8"), valores)
    saida_path.write_text(saida, encoding="utf-8")
    print(f"Dashboard salvo em '{saida_path}' ({saida_path.stat().st_size / 1e6:.1f} MB).")


if __name__ == "__main__":
    main()