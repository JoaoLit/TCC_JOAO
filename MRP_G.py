import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from scipy import stats
import plotly
import plotly.express as px
import sys
import subprocess
import pkg_resources

required = {'plotly', 'pandas', 'streamlit'}
installed = {pkg.key for pkg in pkg_resources.working_set}
missing = required - installed

if missing:
    print(f"Instalando pacotes faltantes: {missing}")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', *missing])

import plotly.express as px

try:
    from langchain.chat_models import ChatOpenAI
    from langchain.agents import create_pandas_dataframe_agent
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False

st.set_page_config(page_title="MRP Varejo Inteligente", layout="wide")

st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2.5rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 10px 25px rgba(102, 126, 234, 0.3);
    }
    .main-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: 700;
    }
    .main-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.95;
        font-size: 1.1rem;
    }
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        border-left: 5px solid #667eea;
        transition: transform 0.2s;
    }
    .metric-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.12);
    }
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }
    .month-section {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        padding: 2rem;
        border-radius: 12px;
        margin: 1.5rem 0;
        border-left: 5px solid #764ba2;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    }
    .month-section h3 {
        margin: 0;
        color: #495057;
        font-weight: 600;
    }
    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
    }
    div[data-testid="stSidebar"] * {
        color: white !important;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #f8f9fa;
        border-radius: 8px 8px 0 0;
        padding: 10px 20px;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white !important;
    }
    div[data-testid="metric-container"] {
        background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #667eea;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    .stDownloadButton button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        font-weight: 500;
        box-shadow: 0 4px 10px rgba(102, 126, 234, 0.3);
        transition: all 0.2s;
    }
    .stDownloadButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 15px rgba(102, 126, 234, 0.4);
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header"><h1>📦 Sistema MRP - Planejamento de Estoque Varejo</h1><p>Planejamento mensal estratégico baseado em histórico de vendas</p></div>', unsafe_allow_html=True)


st.sidebar.header("⚙️ Parâmetros do MRP")

meses_planejamento = st.sidebar.slider(
    "Meses de Planejamento", 
    min_value=1, max_value=12, value=12, step=1,
    help="Quantos meses à frente você deseja planejar"
)

nivel_servico = st.sidebar.slider(
    "Nível de Serviço Desejado (%)", 
    min_value=50, max_value=99, value=95, step=1,
    help="Probabilidade de NÃO ter ruptura de estoque durante o ciclo."
)

lead_time_dias = st.sidebar.number_input(
    "Lead Time de Fornecedores (Dias)", 
    min_value=1, value=15, 
    help="Tempo entre fazer o pedido e a mercadoria chegar na loja."
)

st.sidebar.header("📂 Importação")
uploaded_file = st.sidebar.file_uploader("Carregar planilha (Excel/CSV)", type=["xlsx", "csv"])

def limpar_numero(valor):
    """Função robusta para converter moeda/texto em float"""
    if pd.isna(valor) or valor == '':
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    
    # Tratamento de string
    valor = str(valor).upper().replace('R$', '').strip()
    # Remove separador de milhar (.) e troca decimal (,) por ponto
    valor = valor.replace('.', '').replace(',', '.')
    try:
        return float(valor)
    except:
        return 0.0

@st.cache_data(show_spinner="Carregando dados...")
def carregar_dados(file_content, file_name):
    """Lê o arquivo e padroniza colunas - OTIMIZADO COM CACHE"""
    import io
    try:
        if file_name.endswith('.csv'):
            df = pd.read_csv(
                io.BytesIO(file_content), 
                sep=';', 
                encoding='latin-1',
                dtype={'ITEM': str, 'GRUPO': str}
            )
        else:
            df = pd.read_excel(
                io.BytesIO(file_content),
                dtype={'ITEM': str, 'GRUPO': str}
            )
            
        df.columns = [c.strip().upper() for c in df.columns]
        
        cols_necessarias = ['EMISSÃO', 'CONTAGEM', 'ITEM', 'GRUPO', 'QUANTIDADE', 'VALOR', 'CUSTO']
        colunas_faltantes = [col for col in cols_necessarias if col not in df.columns]
        
        if colunas_faltantes:
            st.error(f"Erro: Colunas faltando na planilha: {', '.join(colunas_faltantes)}")
            return None
                
        df['EMISSÃO'] = pd.to_datetime(df['EMISSÃO'], errors='coerce', dayfirst=True)
        df.dropna(subset=['EMISSÃO'], inplace=True)
        
        df['MES'] = df['EMISSÃO'].dt.month
        df['ANO'] = df['EMISSÃO'].dt.year
        
        # Usar função limpar_numero original que já funciona
        for col in ['VALOR', 'CUSTO', 'QUANTIDADE']:
            df[col] = df[col].apply(limpar_numero)
        
        df = df[df['CUSTO'] > 0].copy()
                
        return df
    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")
        return None

@st.cache_data(show_spinner="Calculando MRP...")
def calcular_mrp(df, service_level, lead_time):
    """Core do cálculo MRP - OTIMIZADO COM CACHE"""
    
    df_agrupado = df.groupby(['ITEM', 'GRUPO', 'ANO', 'MES'])['QUANTIDADE'].sum().reset_index()
    
    stats_item = df_agrupado.groupby(['ITEM', 'GRUPO']).agg(
        DEMANDA_MEDIA_MENSAL=('QUANTIDADE', 'mean'),
        DESVIO_PADRAO=('QUANTIDADE', 'std'),
        TOTAL_VENDIDO=('QUANTIDADE', 'sum'),
        MESES_COM_VENDA=('MES', 'count')
    ).reset_index()
    
    stats_item['DESVIO_PADRAO'] = stats_item.apply(
        lambda x: x['DEMANDA_MEDIA_MENSAL'] * 0.3 if pd.isna(x['DESVIO_PADRAO']) else x['DESVIO_PADRAO'], axis=1
    )
    
   
    def calcular_z_score(nivel_servico_percentual):
        
        p = nivel_servico_percentual / 100.0
        
        if p <= 0 or p >= 1:
            return 0
        
        # Aproximação para a função de distribuição normal inversa
        # Fórmula de Abramowitz e Stegun, 26.2.23
        if p < 0.5:
            # Para p < 0.5, usar a simetria da distribuição
            p = 1 - p
            sinal = -1
        else:
            sinal = 1
        
        t = np.sqrt(-2.0 * np.log(1 - p))
        
        c0 = 2.515517
        c1 = 0.802853
        c2 = 0.010328
        d1 = 1.432788
        d2 = 0.189269
        d3 = 0.001308
        
        z = sinal * (t - ((c0 + c1*t + c2*t*t) / (1 + d1*t + d2*t*t + d3*t*t*t)))
        
        return z

    # No seu código, substitua:
    # z_score = stats.norm.ppf(service_level / 100)
    # por:
    z_score = calcular_z_score(nivel_servico)
    lead_time_mes = lead_time / 30
    
    stats_item['ESTOQUE_SEGURANCA'] = (z_score * stats_item['DESVIO_PADRAO'] * np.sqrt(lead_time_mes))
    stats_item['ESTOQUE_CICLO'] = stats_item['DEMANDA_MEDIA_MENSAL'] * lead_time_mes
    stats_item['PONTO_PEDIDO'] = stats_item['ESTOQUE_CICLO'] + stats_item['ESTOQUE_SEGURANCA']
    stats_item['SUGESTAO_COMPRA'] = stats_item['DEMANDA_MEDIA_MENSAL'] + stats_item['ESTOQUE_SEGURANCA']
    
    cols_round = ['DEMANDA_MEDIA_MENSAL', 'ESTOQUE_SEGURANCA', 'SUGESTAO_COMPRA']
    stats_item[cols_round] = np.ceil(stats_item[cols_round])
    
    return stats_item

@st.cache_data(show_spinner=False)
def calcular_investimento_por_mes(_df_raw, _df_mrp, mes_especifico):
    """
    Calcula investimento apenas para produtos vendidos no mês específico.
    Filtra apenas produtos que tiveram vendas em todos os anos do histórico.
    mes_especifico: número do mês (1-12)
    OTIMIZADO COM CACHE
    """
    df_raw = _df_raw
    df_mrp = _df_mrp
    anos_unicos = df_raw['ANO'].unique()
    anos_disponiveis = len(anos_unicos)
    
    # Agrupar por item e contar em quantos anos diferentes cada produto foi vendido
    df_produtos_por_ano = df_raw.groupby('ITEM')['ANO'].nunique().reset_index()
    df_produtos_por_ano.columns = ['ITEM', 'ANOS_COM_VENDA']
    
    # Filtrar apenas produtos vendidos em TODOS os anos
    produtos_todos_anos = df_produtos_por_ano[
        df_produtos_por_ano['ANOS_COM_VENDA'] == anos_disponiveis
    ]['ITEM'].unique()
    
    # Filtrar vendas do mês específico no histórico
    df_mes_historico = df_raw[
        (df_raw['MES'] == mes_especifico) & 
        (df_raw['ITEM'].isin(produtos_todos_anos))
    ].copy()
    
    df_mes_historico['CUSTO_UNITARIO'] = df_mes_historico['CUSTO'] / df_mes_historico['QUANTIDADE']
    df_mes_historico = df_mes_historico[df_mes_historico['CUSTO_UNITARIO'] > 0]
    
    # Agrupar por item para calcular custo unitário médio daquele mês
    df_investimento_mes = df_mes_historico.groupby('ITEM').agg(
        CUSTO_UNITARIO_MEDIO=('CUSTO_UNITARIO', 'mean'),
        QTD_VENDIDA_MES=('QUANTIDADE', 'sum')
    ).reset_index()
    
    # Merge com MRP para pegar a sugestão de compra e desvio padrao
    df_resultado = pd.merge(
        df_mrp[['ITEM', 'GRUPO', 'DEMANDA_MEDIA_MENSAL', 'DESVIO_PADRAO', 'ESTOQUE_SEGURANCA', 'SUGESTAO_COMPRA']], 
        df_investimento_mes[['ITEM', 'CUSTO_UNITARIO_MEDIO']], 
        on='ITEM', 
        how='inner'  # Inner join para pegar apenas produtos vendidos nesse mês
    )
    
    df_resultado['INVESTIMENTO_ESTIMADO'] = df_resultado['SUGESTAO_COMPRA'] * df_resultado['CUSTO_UNITARIO_MEDIO']
    df_resultado = df_resultado.rename(columns={'CUSTO_UNITARIO_MEDIO': 'CUSTO'})
    
    return df_resultado


if uploaded_file:
    # Usar cache com bytes do arquivo para evitar recarregamento
    file_content = uploaded_file.getvalue()
    df_raw = carregar_dados(file_content, uploaded_file.name)
    
    if df_raw is not None:
        total_vendas = df_raw['VALOR'].sum()
        total_itens = df_raw['QUANTIDADE'].sum()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Faturamento Total Analisado", f"R$ {total_vendas:,.2f}")
        col2.metric("📦 Itens Vendidos", f"{int(total_itens):,}")
        col3.metric("🏷️ SKUs Únicos", df_raw['ITEM'].nunique())
        
        st.markdown("---")
        
        df_mrp = calcular_mrp(df_raw, nivel_servico, lead_time_dias)
        
        st.subheader("📊 Resultado do Planejamento")
        
        col_filtro1, col_filtro2 = st.columns(2)
        with col_filtro1:
            filtro_grupo = st.multiselect("🔍 Filtrar por Grupo", options=sorted(df_mrp['GRUPO'].unique()))
        with col_filtro2:
            investimento_minimo = st.number_input("💵 Investimento Mínimo (R$)", min_value=0.0, value=0.0, step=100.0)
        
        meses_nomes = {
            1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril',
            5: 'Maio', 6: 'Junho', 7: 'Julho', 8: 'Agosto',
            9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'
        }
        
        mes_atual = datetime.now().month
        ano_atual = datetime.now().year
        
        tabs = st.tabs(
            ["📋 Consolidado", "📊 Dashboard Estrategico", "📖 Documentacao", "🤖 Analise IA"] + 
            [f"📅 Mes {i+1} - {meses_nomes[(mes_atual + i - 1) % 12 + 1]}" for i in range(meses_planejamento)]
        )
        
        with tabs[0]:
            st.markdown('<div class="month-section"><h3>📊 Visão Consolidada de Todos os Meses</h3></div>', unsafe_allow_html=True)
            
            # Calcular consolidado somando todos os meses
            investimento_total = 0
            qtd_total = 0
            
            for i in range(meses_planejamento):
                mes_projecao = (mes_atual + i - 1) % 12 + 1
                df_mes_temp = calcular_investimento_por_mes(df_raw, df_mrp, mes_projecao)
                
                if filtro_grupo:
                    df_mes_temp = df_mes_temp[df_mes_temp['GRUPO'].isin(filtro_grupo)]
                if investimento_minimo > 0:
                    df_mes_temp = df_mes_temp[df_mes_temp['INVESTIMENTO_ESTIMADO'] >= investimento_minimo]
                    
                investimento_total += df_mes_temp['INVESTIMENTO_ESTIMADO'].sum()
                qtd_total += df_mes_temp['SUGESTAO_COMPRA'].sum()
            
            # Mostrar todos os produtos únicos
            df_consolidado = calcular_investimento_por_mes(df_raw, df_mrp, mes_atual)
            if filtro_grupo:
                df_consolidado = df_consolidado[df_consolidado['GRUPO'].isin(filtro_grupo)]
            if investimento_minimo > 0:
                df_consolidado = df_consolidado[df_consolidado['INVESTIMENTO_ESTIMADO'] >= investimento_minimo]
            df_consolidado = df_consolidado.sort_values(by='INVESTIMENTO_ESTIMADO', ascending=False)
            
            col_t1, col_t2, col_t3 = st.columns(3)
            col_t1.metric("💰 Investimento Total (Todos os Meses)", f"R$ {investimento_total:,.2f}")
            col_t2.metric("📦 Quantidade Total (Todos os Meses)", f"{int(qtd_total):,} unidades")
            col_t3.metric("📅 Período de Planejamento", f"{meses_planejamento} meses")
            
            st.dataframe(
                df_consolidado[[
                    'ITEM', 'GRUPO', 'DEMANDA_MEDIA_MENSAL', 'DESVIO_PADRAO',
                    'ESTOQUE_SEGURANCA', 'SUGESTAO_COMPRA', 
                    'CUSTO', 'INVESTIMENTO_ESTIMADO'
                ]].style.format({
                    'DEMANDA_MEDIA_MENSAL': '{:.0f}',
                    'DESVIO_PADRAO': '{:.2f}',
                    'ESTOQUE_SEGURANCA': '{:.0f}',
                    'SUGESTAO_COMPRA': '{:.0f}',
                    'CUSTO': 'R$ {:.2f}',
                    'INVESTIMENTO_ESTIMADO': 'R$ {:.2f}'
                }).background_gradient(subset=['INVESTIMENTO_ESTIMADO'], cmap='Blues'),
                use_container_width=True,
                height=500
            )
            
            # Gerar arquivo Excel
            import io
            buffer_consolidado = io.BytesIO()
            with pd.ExcelWriter(buffer_consolidado, engine='openpyxl') as writer:
                df_consolidado.to_excel(writer, sheet_name='Consolidado', index=False)
            buffer_consolidado.seek(0)
            
            st.download_button(
                "📥 Baixar Relatório Consolidado (Excel)",
                data=buffer_consolidado,
                file_name='mrp_consolidado.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

        with tabs[1]:
            st.markdown('<div class="month-section"><h3>📊 Dashboard Estrategico - Curva ABC e Analise por Ano</h3></div>', unsafe_allow_html=True)
            
            # ===== CURVA ABC =====
            st.subheader("📈 Curva ABC de Produtos")
            st.markdown("Classificacao dos produtos por importancia no faturamento (Principio de Pareto)")
            
            # Calcular faturamento por produto
            df_abc = df_raw.groupby('ITEM').agg(
                FATURAMENTO_TOTAL=('VALOR', 'sum'),
                QUANTIDADE_TOTAL=('QUANTIDADE', 'sum'),
                GRUPO=('GRUPO', 'first')
            ).reset_index()
            
            df_abc = df_abc.sort_values('FATURAMENTO_TOTAL', ascending=False)
            df_abc['FATURAMENTO_ACUMULADO'] = df_abc['FATURAMENTO_TOTAL'].cumsum()
            df_abc['PERCENTUAL_ACUMULADO'] = (df_abc['FATURAMENTO_ACUMULADO'] / df_abc['FATURAMENTO_TOTAL'].sum()) * 100
            
            # Classificar ABC
            def classificar_abc(percentual):
                if percentual <= 80:
                    return 'A'
                elif percentual <= 95:
                    return 'B'
                else:
                    return 'C'
            
            df_abc['CLASSE_ABC'] = df_abc['PERCENTUAL_ACUMULADO'].apply(classificar_abc)
            
            # Metricas ABC
            col_abc1, col_abc2, col_abc3 = st.columns(3)
            
            qtd_classe_a = len(df_abc[df_abc['CLASSE_ABC'] == 'A'])
            qtd_classe_b = len(df_abc[df_abc['CLASSE_ABC'] == 'B'])
            qtd_classe_c = len(df_abc[df_abc['CLASSE_ABC'] == 'C'])
            
            fat_classe_a = df_abc[df_abc['CLASSE_ABC'] == 'A']['FATURAMENTO_TOTAL'].sum()
            fat_classe_b = df_abc[df_abc['CLASSE_ABC'] == 'B']['FATURAMENTO_TOTAL'].sum()
            fat_classe_c = df_abc[df_abc['CLASSE_ABC'] == 'C']['FATURAMENTO_TOTAL'].sum()
            
            col_abc1.metric(f"Classe A ({qtd_classe_a} produtos)", f"R$ {fat_classe_a:,.2f}", "80% do faturamento")
            col_abc2.metric(f"Classe B ({qtd_classe_b} produtos)", f"R$ {fat_classe_b:,.2f}", "15% do faturamento")
            col_abc3.metric(f"Classe C ({qtd_classe_c} produtos)", f"R$ {fat_classe_c:,.2f}", "5% do faturamento")
            
            # Grafico Curva ABC
            fig_abc = px.bar(
                df_abc.head(50),
                x='ITEM',
                y='FATURAMENTO_TOTAL',
                color='CLASSE_ABC',
                color_discrete_map={'A': '#2ecc71', 'B': '#f39c12', 'C': '#e74c3c'},
                title='Top 50 Produtos - Curva ABC',
                labels={'FATURAMENTO_TOTAL': 'Faturamento (R$)', 'ITEM': 'Produto', 'CLASSE_ABC': 'Classe'}
            )
            fig_abc.update_layout(xaxis_tickangle=-45, height=500)
            st.plotly_chart(fig_abc, use_container_width=True, key="grafico_abc")
            
            # Tabela ABC
            with st.expander("Ver Tabela Completa da Curva ABC"):
                st.dataframe(
                    df_abc[['ITEM', 'GRUPO', 'FATURAMENTO_TOTAL', 'QUANTIDADE_TOTAL', 'PERCENTUAL_ACUMULADO', 'CLASSE_ABC']].style.format({
                        'FATURAMENTO_TOTAL': 'R$ {:.2f}',
                        'QUANTIDADE_TOTAL': '{:.0f}',
                        'PERCENTUAL_ACUMULADO': '{:.2f}%'
                    }),
                    use_container_width=True,
                    height=400
                )
                
                # Download ABC Excel
                buffer_abc = io.BytesIO()
                with pd.ExcelWriter(buffer_abc, engine='openpyxl') as writer:
                    df_abc.to_excel(writer, sheet_name='Curva_ABC', index=False)
                buffer_abc.seek(0)
                
                st.download_button(
                    "Baixar Curva ABC (Excel)",
                    data=buffer_abc,
                    file_name='curva_abc.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    key='download_abc'
                )
            
            st.markdown("---")
            
            # ===== ANALISE POR ANO =====
            st.subheader("📅 Analise de Faturamento por Ano")
            st.markdown("Compare o desempenho da empresa ao longo dos anos")
            
            anos_disponiveis = sorted(df_raw['ANO'].unique())
            
            # Selector de ano
            ano_selecionado = st.selectbox(
                "Selecione o ano para analise detalhada:",
                options=anos_disponiveis,
                index=len(anos_disponiveis)-1,
                key='ano_selecionado'
            )
            
            # Metricas do ano selecionado
            df_ano = df_raw[df_raw['ANO'] == ano_selecionado]
            
            col_ano1, col_ano2, col_ano3, col_ano4 = st.columns(4)
            col_ano1.metric(f"Faturamento {ano_selecionado}", f"R$ {df_ano['VALOR'].sum():,.2f}")
            col_ano2.metric(f"Itens Vendidos {ano_selecionado}", f"{int(df_ano['QUANTIDADE'].sum()):,}")
            col_ano3.metric(f"SKUs Ativos {ano_selecionado}", f"{df_ano['ITEM'].nunique():,}")
            col_ano4.metric(f"Ticket Medio {ano_selecionado}", f"R$ {df_ano['VALOR'].sum() / df_ano['CONTAGEM'].sum():,.2f}")
            
            # Faturamento mensal do ano selecionado
            df_ano_mensal = df_ano.groupby('MES').agg(
                FATURAMENTO=('VALOR', 'sum'),
                QUANTIDADE=('QUANTIDADE', 'sum')
            ).reset_index()
            df_ano_mensal['MES_NOME'] = df_ano_mensal['MES'].map(meses_nomes)
            
            fig_ano_mensal = px.bar(
                df_ano_mensal,
                x='MES_NOME',
                y='FATURAMENTO',
                title=f'Faturamento Mensal - {ano_selecionado}',
                labels={'MES_NOME': 'Mes', 'FATURAMENTO': 'Faturamento (R$)'},
                color='FATURAMENTO',
                color_continuous_scale='Blues'
            )
            fig_ano_mensal.update_layout(height=400)
            st.plotly_chart(fig_ano_mensal, use_container_width=True, key="grafico_ano_mensal")
            
            # Comparativo entre anos
            st.subheader("📊 Comparativo Entre Anos")
            
            df_comparativo = df_raw.groupby('ANO').agg(
                FATURAMENTO=('VALOR', 'sum'),
                QUANTIDADE=('QUANTIDADE', 'sum'),
                SKUS=('ITEM', 'nunique')
            ).reset_index()
            
            fig_comparativo = px.bar(
                df_comparativo,
                x='ANO',
                y='FATURAMENTO',
                title='Evolucao do Faturamento por Ano',
                labels={'ANO': 'Ano', 'FATURAMENTO': 'Faturamento (R$)'},
                color='FATURAMENTO',
                color_continuous_scale='Viridis',
                text_auto='.2s'
            )
            fig_comparativo.update_layout(height=400)
            st.plotly_chart(fig_comparativo, use_container_width=True, key="grafico_comparativo_anos")
            
            # Tabela comparativa
            with st.expander("Ver Tabela Comparativa de Anos"):
                st.dataframe(
                    df_comparativo.style.format({
                        'FATURAMENTO': 'R$ {:.2f}',
                        'QUANTIDADE': '{:.0f}',
                        'SKUS': '{:.0f}'
                    }),
                    use_container_width=True
                )
                
                # Download comparativo Excel
                buffer_comp = io.BytesIO()
                with pd.ExcelWriter(buffer_comp, engine='openpyxl') as writer:
                    df_comparativo.to_excel(writer, sheet_name='Comparativo_Anos', index=False)
                buffer_comp.seek(0)
                
                st.download_button(
                    "Baixar Comparativo de Anos (Excel)",
                    data=buffer_comp,
                    file_name='comparativo_anos.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    key='download_comparativo'
                )
            
            # Top produtos do ano selecionado
            st.subheader(f"🏆 Top 20 Produtos - {ano_selecionado}")
            
            df_top_ano = df_ano.groupby(['ITEM', 'GRUPO']).agg(
                FATURAMENTO=('VALOR', 'sum'),
                QUANTIDADE=('QUANTIDADE', 'sum')
            ).reset_index().sort_values('FATURAMENTO', ascending=False).head(20)
            
            fig_top = px.bar(
                df_top_ano,
                x='FATURAMENTO',
                y='ITEM',
                orientation='h',
                color='GRUPO',
                title=f'Top 20 Produtos por Faturamento - {ano_selecionado}',
                labels={'FATURAMENTO': 'Faturamento (R$)', 'ITEM': 'Produto'}
            )
            fig_top.update_layout(height=600, yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig_top, use_container_width=True, key="grafico_top_produtos_ano")

        with tabs[2]:
            st.markdown('<div class="month-section"><h3>📖 Documentacao Completa do Sistema MRP</h3></div>', unsafe_allow_html=True)
            
            st.markdown("""
            ## 📊 Visão Geral do Sistema
            
            Este sistema de MRP (Material Requirements Planning) foi desenvolvido para auxiliar no planejamento estratégico
            de estoque baseado em histórico real de vendas. Ele analisa padrões de demanda e sugere quantidades ideais
            de compra para cada produto, considerando variações sazonais e riscos de ruptura.
            """)
            
            st.markdown("---")
            
            # Seção 1: Cálculos e Fórmulas
            with st.expander("📐 Cálculos e Fórmulas Utilizadas", expanded=True):
                st.markdown(r"""
                ### 1. Demanda Média Mensal
                
                Calculamos a média de vendas de cada produto baseada no histórico completo:
                
                $$\bar{D} = \frac{\sum \text{Quantidade Vendida}}{\text{Número de Meses com Venda}}$$
                
                **Exemplo:** Um produto vendeu 100 unidades em 12 meses = 8,33 unidades/mês em média
                
                ---
                
                ### 2. Desvio Padrão da Demanda
                
                Mede a variabilidade das vendas ao longo do tempo:
                
                $$\sigma_D = \sqrt{\frac{\sum (x_i - \bar{D})^2}{n-1}}$$
                
                **Interpretação:** 
                - Desvio baixo = vendas estáveis e previsíveis
                - Desvio alto = vendas voláteis, maior risco de ruptura
                
                ---
                
                ### 3. Fator Z (Nível de Serviço)
                
                Baseado na distribuição normal, define a probabilidade de não ter falta:
                
                | Nível de Serviço | Z-Score | Significado |
                |-----------------|---------|-------------|
                | 90% | 1.28 | 10% chance de ruptura |
                | 95% | 1.65 | 5% chance de ruptura |
                | 99% | 2.33 | 1% chance de ruptura |
                
                ---
                
                ### 4. Estoque de Segurança
                
                Quantidade extra para proteger contra incertezas durante o lead time:
                
                $$SS = Z \times \sigma_D \times \sqrt{\frac{LT}{30}}$$
                
                Onde:
                - $Z$ = Fator de nível de serviço
                - $\sigma_D$ = Desvio padrão da demanda
                - $LT$ = Lead time em dias (dividido por 30 para converter em meses)
                
                **Exemplo:** Para nível 95%, desvio 10 unidades e lead time 15 dias:
                
                $$SS = 1.65 \times 10 \times \sqrt{\frac{15}{30}} = 11.67 \approx 12 \text{ unidades}$$
                
                ---
                
                ### 5. Sugestão de Compra
                
                Quantidade recomendada para o próximo período:
                
                $$\text{Sugestão} = \bar{D} + SS$$
                
                **Exemplo:** Demanda média 100 unidades + Estoque segurança 12 = **112 unidades para comprar**
                
                ---
                
                ### 6. Investimento Estimado
                
                Valor financeiro necessário para executar a compra:
                
                $$\text{Investimento} = \text{Sugestão de Compra} \times \text{Custo Unitário Médio}$$
                
                **Importante:** O custo unitário é calculado dividindo o custo total pela quantidade vendida,
                pois a planilha importada contém custos totais por transação.
                """)
            
            # Seção 2: Interpretação dos Resultados
            with st.expander("🎯 Como Interpretar os Resultados"):
                st.markdown("""
                ### Entendendo as Colunas da Tabela
                
                #### ITEM
                Nome ou código do produto analisado.
                
                #### GRUPO
                Categoria à qual o produto pertence (ex: Tubos, Conexões, etc.)
                
                #### DEMANDA_MEDIA_MENSAL
                Quantidade média vendida por mês baseada no histórico completo.
                - **Valor alto:** Produto de giro rápido, requer reposição frequente
                - **Valor baixo:** Produto de giro lento, comprar em menor quantidade
                
                #### ESTOQUE_SEGURANCA
                Quantidade extra para cobrir variações inesperadas durante o lead time.
                - **Valor alto:** Produto com vendas muito variáveis ou lead time longo
                - **Valor baixo:** Produto estável e previsível
                
                #### SUGESTAO_COMPRA
                **Esta é a quantidade que você deve comprar!**
                Já inclui a demanda esperada + margem de segurança.
                
                #### CUSTO
                Custo unitário médio do produto baseado no histórico de compras.
                
                #### INVESTIMENTO_ESTIMADO
                **Valor total em reais necessário para comprar a quantidade sugerida.**
                - Use este valor para planejamento financeiro e orçamento de compras
                
                ---
                
                ### Interpretando as Métricas Mensais
                
                #### Investimento Total - [Mês]
                Soma de todos os investimentos estimados para aquele mês específico.
                - Compare com seu orçamento disponível
                - Se ultrapassar, use os filtros para priorizar produtos ou grupos
                
                #### Quantidade Total - [Mês]
                Total de unidades a serem compradas naquele mês.
                - Útil para dimensionar espaço de armazenamento
                - Planeje logística e recebimento
                
                ---
                
                ### Usando os Filtros
                
                #### Filtrar por Grupo
                Selecione categorias específicas quando:
                - Quiser focar em uma linha de produtos
                - Tiver orçamentos separados por categoria
                - Precisar fazer compras escalonadas
                
                #### Investimento Mínimo
                Defina um valor mínimo para ver apenas:
                - Produtos de alto valor (compras estratégicas)
                - Eliminar produtos de baixo impacto financeiro
                - Priorizar itens mais importantes
                """)
            
            # Seção 3: Guia de Implementação da IA
            with st.expander("🤖 Guia Completo: Como Usar a Análise com IA"):
                st.markdown("""
                ### Passo a Passo para Configurar a IA
                
                #### 1. Criar Conta na OpenAI
                
                1. Acesse: [https://platform.openai.com/signup](https://platform.openai.com/signup)
                2. Clique em "Sign up" (ou "Get started")
                3. Cadastre-se usando:
                   - E-mail e senha
                   - Ou conta Google/Microsoft
                4. Confirme seu e-mail
                
                #### 2. Obter a Chave API
                
                1. Faça login em: [https://platform.openai.com](https://platform.openai.com)
                2. No menu lateral, clique em "API Keys"
                3. Clique no botão verde "Create new secret key"
                4. Dê um nome para sua chave (ex: "Sistema MRP")
                5. **IMPORTANTE:** Copie a chave agora! Ela começa com `sk-...`
                6. Guarde em local seguro (não compartilhe!)
                
                #### 3. Adicionar Créditos (Se Necessário)
                
                - Contas novas podem ter alguns créditos grátis
                - Para uso contínuo, você precisará adicionar um cartão de crédito
                - Vá em "Billing" → "Payment methods" → "Add payment method"
                
                **Custos aproximados:**
                - GPT-4o-mini: ~$0.15 por 1 milhão de tokens de entrada
                - GPT-4o: ~$2.50 por 1 milhão de tokens de entrada
                - Cada pergunta ao chatbot custa entre $0.001 e $0.01 (centavos!)
                
                #### 4. Usar no Sistema
                
                1. Vá para a aba "🤖 Análise IA"
                2. Cole sua chave API no campo "Chave API OpenAI"
                3. Escolha o modelo:
                   - **gpt-4o-mini:** Mais barato e rápido (recomendado)
                   - **gpt-4o:** Mais poderoso e preciso
                   - **gpt-3.5-turbo:** Mais antigo, menos preciso
                
                ---
                
                ### Exemplos de Perguntas para Fazer à IA
                
                #### Análises Financeiras
                - "Quais são os 10 produtos que exigem maior investimento?"
                - "Qual é o investimento total necessário para o grupo TUBOS?"
                - "Mostre produtos com investimento entre R$ 1.000 e R$ 5.000"
                - "Qual grupo tem o maior investimento médio por produto?"
                
                #### Análises de Demanda
                - "Quais produtos têm demanda média acima de 100 unidades/mês?"
                - "Liste os 5 produtos com maior variação nas vendas"
                - "Quais produtos têm estoque de segurança acima de 50 unidades?"
                - "Mostre produtos com alta demanda mas baixo custo"
                
                #### Análises Comparativas
                - "Compare o investimento necessário entre os grupos"
                - "Qual grupo tem mais produtos acima de R$ 10.000 de investimento?"
                - "Mostre a distribuição de produtos por faixa de investimento"
                
                #### Análises Estratégicas
                - "Quais produtos devo priorizar se meu orçamento for R$ 50.000?"
                - "Liste produtos de alto giro (demanda > 50) e baixo estoque de segurança"
                - "Sugira produtos para compra imediata baseado no investimento"
                
                ---
                
                ### Botões de Análise Rápida
                
                O sistema também oferece análises prontas sem precisar digitar:
                
                #### 📊 Top 10 Maiores Investimentos
                Mostra os produtos que exigem mais capital de giro
                
                #### 📈 Investimento por Grupo
                Gráfico visual da distribuição de investimento por categoria
                
                #### 🎯 Produtos Alta Demanda
                Lista produtos com maior média de vendas mensais
                
                #### 🔍 Estatísticas Gerais
                Resumo geral: total de produtos, investimentos médios, etc.
                
                ---
                
                ### Solução de Problemas
                
                **Erro: "Invalid API Key"**
                - Verifique se copiou a chave completa (começa com `sk-`)
                - Confirme que a chave está ativa na plataforma OpenAI
                - Tente gerar uma nova chave
                
                **Erro: "You exceeded your current quota"**
                - Seus créditos acabaram
                - Adicione créditos em: [https://platform.openai.com/account/billing](https://platform.openai.com/account/billing)
                
                **Erro: "Rate limit exceeded"**
                - Você fez muitas requisições em pouco tempo
                - Aguarde 1 minuto e tente novamente
                
                **A resposta não faz sentido**
                - Tente reformular a pergunta de forma mais clara
                - Use perguntas específicas e diretas
                - Mencione nomes de colunas exatas (ITEM, GRUPO, etc.)
                """)
            
            # Seção 4: Boas Práticas
            with st.expander("✅ Boas Práticas e Recomendações"):
                st.markdown("""
                ### Planejamento Eficiente
                
                #### 1. Revisite Periodicamente
                - Atualize o histórico de vendas mensalmente
                - Recalcule o MRP com dados novos
                - Ajuste o nível de serviço conforme necessidade
                
                #### 2. Ajuste o Nível de Serviço
                - **95%:** Padrão recomendado para maioria dos produtos
                - **99%:** Para produtos críticos ou estratégicos
                - **90%:** Para produtos de baixo valor ou fácil substituição
                
                #### 3. Considere Sazonalidade
                - Use os filtros mensais para ver padrões sazonais
                - Produtos que só vendem em certos meses aparecem apenas neles
                - Planeje compras antecipadas para alta temporada
                
                #### 4. Gestão de Orçamento
                - Baixe os relatórios mensais para apresentar à gestão
                - Use o investimento total como base para negociação de crédito
                - Priorize grupos mais rentáveis se orçamento limitado
                
                #### 5. Qualidade dos Dados
                - O sistema já filtra produtos com problemas
                - Mas revise seu cadastro de produtos regularmente
                - Mantenha custos atualizados no sistema fonte
                
                ---
                
                ### Integração com Processos
                
                #### Compras
                - Use a "Sugestão de Compra" como base para pedidos
                - Compartilhe relatórios com fornecedores
                - Negocie melhores preços com base em volume planejado
                
                #### Financeiro
                - Use "Investimento Total" para planejamento de caixa
                - Distribua compras ao longo dos meses conforme fluxo
                - Identifique necessidade de capital de giro antecipadamente
                
                #### Logística
                - Use "Quantidade Total" para planejar espaço de armazém
                - Programe recebimentos com antecedência
                - Considere lead time na data dos pedidos
                
                ---
                
                ### Limitações e Considerações
                
                ⚠️ **O sistema assume:**
                - Estoque atual = 0 (sugere quantidade total ideal)
                - Padrões de demanda do passado se repetem
                - Custos históricos médios continuarão válidos
                
                ⚠️ **Não considera:**
                - Estoque atual real (precisa ajustar manualmente)
                - Promoções ou eventos especiais futuros
                - Mudanças de mercado ou tendências
                - Lote mínimo de compra dos fornecedores
                
                💡 **Dica:** Use o MRP como guia estratégico, mas sempre aplique seu conhecimento
                de negócio na decisão final!
                """)

        with tabs[3]:
            st.markdown('<div class="month-section"><h3>🤖 Analise Inteligente com IA</h3></div>', unsafe_allow_html=True)
            
            if not LANGCHAIN_AVAILABLE:
                st.error("⚠️ Biblioteca LangChain não está instalada. Execute: `pip install langchain langchain-openai`")
            else:
                st.markdown("""
                ### Faça perguntas sobre seus dados de MRP
                
                Use este assistente de IA para obter insights rápidos e análises personalizadas dos seus dados de planejamento.
                """)
                
                openai_api_key = st.text_input("Insira sua API Key da OpenAI", type="password", help="Sua chave API será usada apenas durante esta sessão")
                
                if openai_api_key:
                    try:
                        llm = ChatOpenAI(temperature=0, model="gpt-3.5-turbo", openai_api_key=openai_api_key)
                        # Use df_mrp for general analysis, as it contains aggregated data
                        agent = create_pandas_dataframe_agent(llm, df_mrp, verbose=True, allow_dangerous_code=True)
                        
                        st.success("✅ Agente de IA conectado com sucesso!")
                        
                        col_a1, col_a2, col_a3 = st.columns(3)
                        
                        with col_a1:
                            if st.button("🔝 Top 10 Maiores Investimentos"):
                                with st.spinner("Analisando..."):
                                    # Adjusting the prompt for the agent to understand 'INVESTIMENTO_ESTIMADO'
                                    resposta = agent.run("Liste os 10 produtos com maior 'INVESTIMENTO_ESTIMADO', mostrando 'ITEM', 'GRUPO' e 'INVESTIMENTO_ESTIMADO'")
                                    st.write(resposta)
                        
                        with col_a2:
                            if st.button("📊 Investimento por Grupo"):
                                with st.spinner("Analisando..."):
                                    # Prompting to group by 'GRUPO' and sum 'INVESTIMENTO_ESTIMADO'
                                    resposta = agent.run("Agrupe por 'GRUPO' e some o 'INVESTIMENTO_ESTIMADO' para cada grupo. Mostre o resultado.")
                                    st.write(resposta)
                        
                        with col_a3:
                            if st.button("📈 Estatísticas Gerais"):
                                with st.spinner("Analisando..."):
                                    # Prompting for descriptive statistics on relevant columns
                                    resposta = agent.run("Forneça estatísticas descritivas (média, std, min, max) sobre 'DEMANDA_MEDIA_MENSAL', 'ESTOQUE_SEGURANCA' e 'INVESTIMENTO_ESTIMADO'")
                                    st.write(resposta)
                        
                        st.markdown("---")
                        
                        pergunta_customizada = st.text_area("💬 Faça sua pergunta personalizada:", 
                                                           placeholder="Exemplo: Quais produtos têm demanda média acima de 100 unidades?")
                        
                        if st.button("🔍 Analisar"):
                            if pergunta_customizada:
                                with st.spinner("Processando sua pergunta..."):
                                    resposta = agent.run(pergunta_customizada)
                                    st.markdown("### 📝 Resposta:")
                                    st.write(resposta)
                            else:
                                st.warning("Por favor, digite uma pergunta antes de analisar.")
                    
                    except Exception as e:
                        st.error(f"❌ Erro ao conectar com OpenAI: {str(e)}")
                        st.info("Verifique se sua chave API está correta e tem créditos disponíveis.")
                else:
                    st.info("👆 Insira sua chave API da OpenAI acima para começar a usar o assistente de IA")

        for i in range(meses_planejamento):
            with tabs[4 + i]:
                mes_projecao = (mes_atual + i - 1) % 12 + 1
                ano_projecao = ano_atual + ((mes_atual + i - 1) // 12)
                nome_mes = meses_nomes[mes_projecao]
                
                st.markdown(f'<div class="month-section"><h3>📆 {nome_mes}/{ano_projecao}</h3></div>', unsafe_allow_html=True)
                
                # Calcular dados específicos deste mês
                df_mes = calcular_investimento_por_mes(df_raw, df_mrp, mes_projecao)
                
                # Aplicar filtros
                if filtro_grupo:
                    df_mes = df_mes[df_mes['GRUPO'].isin(filtro_grupo)]
                if investimento_minimo > 0:
                    df_mes = df_mes[df_mes['INVESTIMENTO_ESTIMADO'] >= investimento_minimo]
                    
                df_mes = df_mes.sort_values(by='INVESTIMENTO_ESTIMADO', ascending=False)
                
                investimento_mes = df_mes['INVESTIMENTO_ESTIMADO'].sum()
                qtd_itens_mes = df_mes['SUGESTAO_COMPRA'].sum()
                
                col_m1, col_m2 = st.columns(2)
                col_m1.metric(f"💰 Investimento Total - {nome_mes}", f"R$ {investimento_mes:,.2f}")
                col_m2.metric(f"📦 Quantidade Total - {nome_mes}", f"{int(qtd_itens_mes):,} unidades")
                
                st.dataframe(
                    df_mes[[
                        'ITEM', 'GRUPO', 'DEMANDA_MEDIA_MENSAL', 'DESVIO_PADRAO',
                        'ESTOQUE_SEGURANCA', 'SUGESTAO_COMPRA', 
                        'CUSTO', 'INVESTIMENTO_ESTIMADO'
                    ]].style.format({
                        'DEMANDA_MEDIA_MENSAL': '{:.0f}',
                        'DESVIO_PADRAO': '{:.2f}',
                        'ESTOQUE_SEGURANCA': '{:.0f}',
                        'SUGESTAO_COMPRA': '{:.0f}',
                        'CUSTO': 'R$ {:.2f}',
                        'INVESTIMENTO_ESTIMADO': 'R$ {:.2f}'
                    }).background_gradient(subset=['INVESTIMENTO_ESTIMADO'], cmap='RdYlGn_r'),
                    use_container_width=True,
                    height=400
                )
                
                # Gerar arquivo Excel mensal
                buffer_mes = io.BytesIO()
                with pd.ExcelWriter(buffer_mes, engine='openpyxl') as writer:
                    df_mes.to_excel(writer, sheet_name=nome_mes, index=False)
                buffer_mes.seek(0)
                
                st.download_button(
                    f"📥 Baixar Relatório {nome_mes}/{ano_projecao} (Excel)",
                    data=buffer_mes,
                    file_name=f'mrp_{nome_mes}_{ano_projecao}.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    key=f'download_mes_{i}'
                )
                
                st.markdown("---")
                st.markdown("### 📈 Análise de Comportamento do Produto")
                
                if len(df_mes) > 0:
                    produto_selecionado = st.selectbox(
                        "Selecione um produto para visualizar seu histórico de vendas:",
                        options=sorted(df_mes['ITEM'].unique()),
                        key=f'produto_select_{i}'
                    )
                    
                    if produto_selecionado:
                        # Filtrar histórico do produto selecionado
                        df_produto_historico = df_raw[df_raw['ITEM'] == produto_selecionado].copy()
                        
                        # Agrupar por ano e mês
                        df_produto_tempo = df_produto_historico.groupby(['ANO', 'MES']).agg(
                            QUANTIDADE_VENDIDA=('QUANTIDADE', 'sum'),
                            FATURAMENTO=('VALOR', 'sum')
                        ).reset_index()
                        
                        # Criar coluna de data para melhor visualização
                        df_produto_tempo['DATA'] = pd.to_datetime(
                            df_produto_tempo['ANO'].astype(str) + '-' + 
                            df_produto_tempo['MES'].astype(str) + '-01'
                        )
                        df_produto_tempo = df_produto_tempo.sort_values('DATA')
                        
                        # Métricas do produto
                        col_p1, col_p2, col_p3 = st.columns(3)
                        col_p1.metric("📦 Total Vendido", f"{int(df_produto_tempo['QUANTIDADE_VENDIDA'].sum()):,} unidades")
                        col_p2.metric("💰 Faturamento Total", f"R$ {df_produto_tempo['FATURAMENTO'].sum():,.2f}")
                        col_p3.metric("📊 Média Mensal", f"{df_produto_tempo['QUANTIDADE_VENDIDA'].mean():.1f} unidades")
                        
                        # Gráfico de linha com evolução temporal
                        fig = px.line(
                            df_produto_tempo,
                            x='DATA',
                            y='QUANTIDADE_VENDIDA',
                            title=f'Evolução de Vendas - {produto_selecionado}',
                            labels={'DATA': 'Período', 'QUANTIDADE_VENDIDA': 'Quantidade Vendida'},
                            markers=True
                        )
                        
                        fig.update_layout(
                            hovermode='x unified',
                            plot_bgcolor='rgba(0,0,0,0)',
                            paper_bgcolor='rgba(0,0,0,0)',
                            font=dict(size=12),
                            height=400
                        )
                        
                        fig.update_traces(
                            line=dict(color='#667eea', width=3),
                            marker=dict(size=8, color='#764ba2')
                        )
                        
                        st.plotly_chart(fig, use_container_width=True, key=f"grafico_produto_mes_{i+1}_{produto_selecionado}")
                        
                        # Informações adicionais
                        grupo_produto = df_mes[df_mes['ITEM'] == produto_selecionado]['GRUPO'].iloc[0]
                        st.info(f"**Grupo:** {grupo_produto} | **Meses com venda no histórico:** {len(df_produto_tempo)}")
                else:
                    st.warning("Nenhum produto disponível para análise com os filtros aplicados.")

else:
    st.info("Por favor, faca o upload da planilha de vendas na barra lateral para iniciar.")
    st.markdown("""
    **Formato esperado da planilha:**
    - **EMISSAO**: Data da venda
    - **CONTAGEM**: Indicador (0 ou 1)
    - **ITEM**: Nome/Codigo do produto
    - **GRUPO**: Categoria
    - **QUANTIDADE**: Qtd vendida
    - **VALOR**: Valor total da venda
    - **CUSTO**: Custo total da transacao
    """)
