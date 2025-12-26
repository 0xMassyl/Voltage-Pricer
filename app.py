import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io

# Imports des modules internes
from src.ingestion.curve_generator import LoadCurveGenerator
from src.ingestion.market_data import MarketDataManager
from src.domain.pricing_models import ElectricityPricingEngine
from src.domain.risk_models import RiskEngine
from src.domain.ppa_valuation import price_renewable_ppa
from src.core.settings import SETTINGS
from src.reporting.excel_export import export_pricing_to_excel

# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Voltage Pricer | Dark Mode",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 2. NEON DARK DESIGN SYSTEM 
# -----------------------------------------------------------------------------
st.markdown("""
    <style>
        /* Main Background - Pure Black */
        .stApp {
            background-color: #000000;
        }
        
        /* Sidebar - Very Dark Grey */
        [data-testid="stSidebar"] {
            background-color: #0b0b0b;
            border-right: 1px solid #333;
        }
        
        /* Text Colors - Modern Font Update */
        h1, h2, h3, h4, p, span, div, label {
            color: #E0E0E0 !important;
            font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', sans-serif !important; /* Modern Sans-Serif */
        }
        
        /* Metrics Cards */
        div[data-testid="stMetric"] {
            background-color: #111111;
            padding: 10px;
            border-radius: 4px;
            border: 1px solid #333;
            transition: all 0.3s ease;
        }
        div[data-testid="stMetric"]:hover {
            border-color: #00FF00; /* Neon Green on Hover */
            box-shadow: 0 0 10px rgba(0, 255, 0, 0.2);
        }
        [data-testid="stMetricLabel"] {
            color: #888 !important;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            font-family: 'Segoe UI', sans-serif !important;
        }
        [data-testid="stMetricValue"] {
            color: #00FF00 !important; /* Neon Green Values */
            font-size: 24px;
            font-weight: 300;
            font-family: 'Segoe UI', sans-serif !important;
        }
        
        /* Inputs styling */
        .stTextInput input, .stNumberInput input, .stSelectbox div {
            background-color: #111111 !important;
            color: #00FF00 !important;
            border: 1px solid #333 !important;
            font-family: 'Segoe UI', sans-serif !important;
        }
        
        /* Buttons - Neon Style */
        .stButton > button {
            background-color: transparent !important;
            color: #00FF00 !important;
            border: 1px solid #00FF00 !important;
            border-radius: 0px;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 2px;
            transition: all 0.3s;
            font-family: 'Segoe UI', sans-serif !important;
        }
        .stButton > button:hover {
            background-color: #00FF00 !important;
            color: black !important;
            box-shadow: 0 0 15px #00FF00;
        }

        /* Dataframes - Dark Terminal Style */
        [data-testid="stDataFrame"] {
            background-color: #111111;
            border: 1px solid #333;
        }
        
        /* Plotly Backgrounds */
        .js-plotly-plot .plotly .main-svg {
            background: rgba(0,0,0,0) !important;
        }
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. HEADER
# -----------------------------------------------------------------------------
col_logo, col_title = st.columns([1, 20])
with col_title:
    st.markdown("# ⚡ VOLTAGE <span style='color:#00FF00'>PRICER</span>", unsafe_allow_html=True)
    st.markdown("<div style='color:#666; font-size:12px; letter-spacing:2px; font-family:\"Segoe UI\", sans-serif;'>QUANTITATIVE ENERGY ENGINE</div>", unsafe_allow_html=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# 4. INITIALIZATION
# -----------------------------------------------------------------------------
if 'market_data' not in st.session_state:
    with st.spinner("Connecting to Market Feeds..."):
        manager = MarketDataManager()
        st.session_state['market_data'] = manager.get_forward_prices()

MARKET_PRICES = st.session_state['market_data']

# -----------------------------------------------------------------------------
# 5. SIDEBAR
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### /// SYSTEM CONFIG")
    
    client_name = st.text_input("CLIENT_ID", "INDUSTRIE_NORD")
    annual_volume = st.number_input("VOL_MWH", min_value=100, max_value=1000000, value=15000, step=1000)
    profile_type = st.selectbox(
        "PROFILE_TYPE", 
        ["INDUSTRY_24_7", "OFFICE_BUILDING", "SOLAR_PPA"],
        index=0
    )

    st.markdown("---")
    st.markdown("### /// MARKET DATA")
    
    base_price = st.number_input(
        "FWD_BASE (€/MWh)", 
        value=MARKET_PRICES.get('CAL_BASE', 95.5),
        step=0.5
    )
    MARKET_PRICES['CAL_BASE'] = base_price
    
    st.markdown("---")
    run_btn = st.button(">>> EXECUTE PRICING")

# -----------------------------------------------------------------------------
# 6. MAIN ENGINE EXECUTION
# -----------------------------------------------------------------------------
if run_btn:
    try:
        # A. DATA GENERATION & ML FORECASTING
        with st.spinner("COMPUTING..."):
            generator = LoadCurveGenerator(year=2026)
            load_curve = generator.generate_profile(profile_type, annual_volume)
            
            pricing_engine = ElectricityPricingEngine(MARKET_PRICES)
            pricing_result = pricing_engine.compute_sourcing_cost(load_curve)
            
            # --- AJOUT: RECUPERATION DES METRIQUES ML ---
            # On récupère les stats d'apprentissage (RMSE, Overfit)
            ml_metrics = pricing_engine.forecaster.get_metrics()
            
            hpfc = pricing_engine.generate_hpfc(load_curve.index)
            risk_engine = RiskEngine(SETTINGS, MARKET_PRICES.get('SPOT_VOLATILITY', 0.25))
            
            profiling_cost = risk_engine.calculate_profiling_cost(load_curve, hpfc)
            volume_risk = risk_engine.calculate_volume_risk_premium(pricing_result.total_volume_mwh)
            
            ppa_data = None
            if profile_type == "SOLAR_PPA":
                ppa_data = price_renewable_ppa("SOLAR", base_price)

        # B. COST STACK
        grid_fees = SETTINGS.ELIA_GRID_FEE + SETTINGS.DISTRIBUTION_GRID_FEE
        taxes = SETTINGS.TAXES_AND_LEVIES + SETTINGS.GREEN_CERT_COST
        margin = 2.50
        
        final_price = (
            pricing_result.weighted_average_price + 
            profiling_cost + 
            volume_risk + 
            grid_fees + 
            taxes + 
            margin
        )
        
        # --- AJOUT DU BADGE DE SOURCE ---
        load_name_str = str(load_curve.name) if load_curve.name is not None else ""
        if "Real" in load_name_str:
            st.markdown("<div style='background:#111; color:#00FF00; border:1px solid #00FF00; padding:5px; text-align:center; font-size:12px; font-family:\"Segoe UI\", sans-serif;'>📡 REAL DATA FEED: ELIA API CONNECTED</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='background:#111; color:#FF00FF; border:1px solid #FF00FF; padding:5px; text-align:center; font-size:12px; font-family:\"Segoe UI\", sans-serif;'>📊 SYNTHETIC DATA MODE</div>", unsafe_allow_html=True)
        st.write("")

        # ---------------------------------------------------------------------
        # 7. DASHBOARD DISPLAY
        # ---------------------------------------------------------------------
        
        # --- ROW 1: KEY METRICS ---
        st.markdown("### /// EXECUTIVE SUMMARY")
        m1, m2, m3, m4 = st.columns(4)
        
        with m1: st.metric("TOTAL VOL (MWh)", f"{pricing_result.total_volume_mwh:,.0f}")
        with m2: st.metric("COMMODITY (€)", f"{pricing_result.weighted_average_price:.2f}")
        with m3: st.metric("RISK PREM (€)", f"{profiling_cost + volume_risk:.2f}")
        with m4: st.metric("FINAL PRICE (€)", f"{final_price:.2f}")
        
        st.markdown("---")

        # --- TABS: NAVIGATION PRINCIPALE ---
        tab1, tab2, tab3, tab4 = st.tabs(["📊 QUOTE DETAIL", "📈 ADVANCED ANALYTICS", "🤖 ML INTELLIGENCE", "💾 EXPORT"])

        # TAB 1: QUOTE DETAIL (MODIFIÉ AVEC FLÈCHES ET DESIGN)
        with tab1:
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown("#### /// LOAD vs PRICE DYNAMICS")
                viz_df = pd.DataFrame({"Load": load_curve, "Price": hpfc})
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=viz_df.index[:168], y=viz_df["Load"][:168], name="Load (MW)", line=dict(color='#00FF00', width=1), fill='tozeroy', fillcolor='rgba(0, 255, 0, 0.1)'))
                fig.add_trace(go.Scatter(x=viz_df.index[:168], y=viz_df["Price"][:168], name="Price (€/MWh)", line=dict(color='#FF00FF', width=2), yaxis="y2"))
                fig.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#888', family="Segoe UI"), yaxis=dict(title="Load", showgrid=True, gridcolor='#222'), yaxis2=dict(title="Price", overlaying="y", side="right", showgrid=False), xaxis=dict(showgrid=False), legend=dict(orientation="h", y=1.1, font=dict(color='#fff')), height=350, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig, use_container_width=True)

                # NOUVEAUX KPIS
                max_load = load_curve.max()
                avg_load = load_curve.mean()
                load_factor = (avg_load / max_load) * 100 if max_load > 0 else 0
                peak_hours = load_curve.between_time('08:00', '20:00').sum()
                peak_share = (peak_hours / load_curve.sum()) * 100 if load_curve.sum() > 0 else 0

                k1, k2, k3 = st.columns(3)
                with k1: st.metric("Load Factor", f"{load_factor:.1f}%")
                with k2: st.metric("Peak Share", f"{peak_share:.1f}%")
                with k3: st.metric("Max Power", f"{max_load:.2f} MW")

            with c2:
                st.markdown("#### /// COST STACK")
                cost_items = [
                    {"Item": "Commodity", "Value": pricing_result.weighted_average_price},
                    {"Item": "Profiling", "Value": profiling_cost},
                    {"Item": "Vol. Risk", "Value": volume_risk},
                    {"Item": "Grid/Tax", "Value": grid_fees + taxes},
                    {"Item": "Margin", "Value": margin},
                ]
                df_costs = pd.DataFrame(cost_items)
                neon_colors = ['#00FF00', '#CCFF00', '#FFFF00', '#FF00FF', '#00FFFF']
                fig_pie = px.pie(df_costs, values='Value', names='Item', hole=0.7, color_discrete_sequence=neon_colors)
                fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#d1d4dc', family="Segoe UI"), showlegend=False, margin=dict(l=0, r=0, t=0, b=0), height=200)
                fig_pie.add_annotation(text=f"<b>€{final_price:.0f}</b>", x=0.5, y=0.5, showarrow=False, font_size=24, font_color="white")
                st.plotly_chart(fig_pie, use_container_width=True)

            # --- ANALYSE DE SENSIBILITÉ (CORRIGÉE AVEC EMOJIS) ---
            st.markdown("---")
            with st.expander("📊 Market Sensitivity Analysis (Stress Test)", expanded=True):
                st.markdown("Impact of Forward Market moves on Final Price.")
                
                sens_data = []
                base_comm = pricing_result.weighted_average_price
                
                for shock in [-0.20, -0.10, 0.0, 0.10, 0.20]:
                    shocked_comm = base_comm * (1 + shock)
                    shocked_final = shocked_comm + profiling_cost + volume_risk + grid_fees + taxes + margin
                    delta = shocked_final - final_price
                    
                    # Logique flèches : Monte = Vert, Descend = Rouge
                    move_icon = "🟢 UP" if shock > 0 else "🔴 DOWN" if shock < 0 else "⚪ FLAT"
                    impact_icon = "🟢" if delta > 0 else "🔴" if delta < 0 else "⚪"
                    
                    sens_data.append({
                        "Market Move": f"{move_icon} {shock:+.0%}",
                        "New Commodity": f"€{shocked_comm:.2f}",
                        "New Final Price": f"€{shocked_final:.2f}",
                        "Impact": f"{impact_icon} {delta:+.2f} €/MWh"
                    })
                
                # Affichage Pleine Largeur
                st.dataframe(pd.DataFrame(sens_data), use_container_width=True, hide_index=True)

        with tab2:
            st.markdown("#### /// ADVANCED MARKET ANALYTICS")
            ana1, ana2 = st.columns(2)
            with ana1:
                st.markdown("#### A. LOAD DURATION CURVE (RISK VIEW)")
                ldc = load_curve.sort_values(ascending=False).reset_index(drop=True)
                ldc_df = pd.DataFrame({"Hours": ldc.index, "Load (MW)": ldc.values})
                fig_ldc = px.area(ldc_df, x="Hours", y="Load (MW)")
                fig_ldc.update_traces(line_color='#00FF00', fillcolor='rgba(0, 255, 0, 0.2)')
                fig_ldc.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#888', family="Segoe UI"),
                    yaxis=dict(showgrid=True, gridcolor='#333'), xaxis=dict(title="Hours (Sorted)"),
                    height=300, margin=dict(l=0, r=0, t=10, b=0)
                )
                st.plotly_chart(fig_ldc, use_container_width=True)
                st.caption("Visualise l'intensité d'utilisation (Flat = Ruban, Steep = Pointe).")

            with ana2:
                st.markdown("#### B. SEASONAL HEATMAP (CONSUMPTION)")
                df_heat = load_curve.to_frame(name="Load")
                idx_dt = pd.to_datetime(df_heat.index)
                df_heat["Hour"] = idx_dt.hour
                df_heat["Month"] = idx_dt.strftime('%b')
                heatmap_data = df_heat.pivot_table(index="Hour", columns="Month", values="Load", aggfunc="mean")
                months_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                heatmap_data = heatmap_data[months_order]
                fig_heat = px.imshow(heatmap_data, color_continuous_scale="Viridis", aspect="auto")
                fig_heat.update_layout(
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    font=dict(color='#888', family="Segoe UI"),
                    height=300, margin=dict(l=0, r=0, t=10, b=0)
                )
                st.plotly_chart(fig_heat, use_container_width=True)
                st.caption("Intensité horaire par mois (Rouge/Jaune = Forte consommation).")
            
            # Graphique Combiné Budget
            st.markdown("#### C. MONTHLY BUDGET FORECAST")
            monthly_df = pd.DataFrame({"Load": load_curve, "Price": hpfc})
            monthly_df["Cost"] = monthly_df["Load"] * monthly_df["Price"]
            monthly_agg = monthly_df.resample("ME").sum()
            monthly_agg["Avg Price"] = monthly_agg["Cost"] / monthly_agg["Load"]
            monthly_idx_dt = pd.to_datetime(monthly_agg.index)
            monthly_agg["Month"] = monthly_idx_dt.strftime("%Y-%m")
            
            fig_mix = make_subplots(specs=[[{"secondary_y": True}]])
            fig_mix.add_trace(go.Bar(x=monthly_agg["Month"], y=monthly_agg["Load"], name="Volume (MWh)", marker_color='#333', marker_line_color='#00FF00', marker_line_width=1, opacity=0.8), secondary_y=False)
            fig_mix.add_trace(go.Scatter(x=monthly_agg["Month"], y=monthly_agg["Avg Price"], name="Avg Price (€/MWh)", line=dict(color='#FF00FF', width=3), mode='lines+markers'), secondary_y=True)
            fig_mix.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#888', family="Segoe UI"), legend=dict(orientation="h", y=1.1, font=dict(color='#fff')), height=350)
            fig_mix.update_yaxes(title_text="Volume (MWh)", showgrid=False, secondary_y=False)
            fig_mix.update_yaxes(title_text="Price (€/MWh)", showgrid=True, gridcolor='#222', secondary_y=True)
            st.plotly_chart(fig_mix, use_container_width=True)

        # --- ONGLET 3 : DIAGNOSTIC ML (L'AJOUT QUE VOUS ATTENDIEZ) ---
# TAB 3: ML INTELLIGENCE
        with tab3:
            st.markdown("### 🤖 XGBoost Model Diagnostics (25-Year Training)")
            
            if ml_metrics:
                col_ml1, col_ml2, col_ml3 = st.columns(3)
                
                rmse_train = ml_metrics.get('RMSE_Train', 0.0)
                rmse_test = ml_metrics.get('RMSE_Test', 0.0)
                overfit_ratio = ml_metrics.get('Overfitting_Ratio', 0.0)
                
                with col_ml1:
                    st.metric("Training Error (RMSE)", f"€{rmse_train}")
                with col_ml2:
                    delta_val = rmse_test - rmse_train
                    st.metric("Testing Error (RMSE)", f"€{rmse_test}", delta=f"{delta_val:.2f} vs Train", delta_color="inverse")
                with col_ml3:
                    color = "normal" if overfit_ratio < 1.3 else "inverse"
                    st.metric("Overfitting Ratio", f"{overfit_ratio}x", delta="Target < 1.3", delta_color=color)
                
                st.markdown("---")
                
                # --- NOUVEAU : GRAPHES ML ---
                col_viz1, col_viz2 = st.columns(2)
                
                with col_viz1:
                    st.markdown("#### 📉 Learned Seasonality (Daily Profile)")
                    df_season = pd.DataFrame({"Price": hpfc})
                    
                    # FIX PYLANCE: Conversion index
                    idx_season = pd.to_datetime(df_season.index)
                    df_season["Hour"] = idx_season.hour
                    
                    daily_profile = df_season.groupby("Hour").mean()
                    
                    fig_fit = px.line(daily_profile, x=daily_profile.index, y="Price", title="Average Daily Price Shape (ML Prediction)", markers=True)
                    fig_fit.update_traces(line_color='#00FF00', line_width=3)
                    fig_fit.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#d1d4dc', family="Segoe UI"), xaxis_title="Hour of Day", yaxis_title="Price (€/MWh)", height=350)
                    st.plotly_chart(fig_fit, use_container_width=True)
                    st.caption("Montre que le modèle a 'compris' la Duck Curve : prix bas la nuit, pics le matin et le soir.")

                with col_viz2:
                    st.markdown("#### 🧩 Risk Clustering (Load vs Price)")
                    df_cluster = pd.DataFrame({"Load": load_curve, "Price": hpfc})
                    
                    # FIX PYLANCE: Conversion index pour np.where
                    idx_cluster = pd.to_datetime(df_cluster.index)
                    
                    df_cluster["Cluster"] = np.where((idx_cluster.hour >= 8) & (idx_cluster.hour < 20), "Peak Hours", "Off-Peak")
                    
                    fig_clust = px.scatter(df_cluster, x="Load", y="Price", color="Cluster", color_discrete_map={"Peak Hours": "#FF00FF", "Off-Peak": "#00FF00"}, opacity=0.6)
                    fig_clust.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='#d1d4dc', family="Segoe UI"), xaxis_title="Load (MW)", yaxis_title="Price (€/MWh)", legend=dict(orientation="h", y=1.1), height=350)
                    st.plotly_chart(fig_clust, use_container_width=True)
                    st.caption("Visualisation de la corrélation : Si les points roses (Peak) sont en haut à droite (Forte Conso), le coût de profilage explose.")
            else:
                st.warning("Metrics unavailable.")



        with tab4:
            # FIX: Définition des colonnes pour l'export et le PPA
            col_export, col_ppa = st.columns([1, 2])
            
            with col_export:
                st.markdown("#### /// EXPORT")
                excel_file = export_pricing_to_excel(df_costs, load_curve, annual_volume, MARKET_PRICES, final_price)
                st.download_button(
                    label="[.XLSX] DOWNLOAD QUOTE",
                    data=excel_file,
                    file_name=f"Quote_{client_name}_2026.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            with col_ppa:
                if ppa_data:
                    st.info(
                        f"☀️ PPA VALUATION: FAIR PRICE = €{ppa_data.fair_price:.2f}/MWh "
                        f"(Cannibalization: -€{ppa_data.cannibalization_impact:.2f})"
                    )

    except Exception as e:
        st.error(f"SYSTEM ERROR: {e}")

else:
    # État initial
    st.markdown("<div style='text-align: center; color: #333; margin-top: 50px; font-family:\"Segoe UI\", sans-serif;'>WAITING FOR INPUT...</div>", unsafe_allow_html=True)
    
    