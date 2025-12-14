import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
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
    page_title="Voltage Pricer | Corporate Engine",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 2. CORPORATE DESIGN SYSTEM (CSS)
# Style: TotalEnergies inspired (Light, Clean, Professional)
# -----------------------------------------------------------------------------
st.markdown("""
    <style>
        /* Main Background - Light Corporate Grey */
        .stApp {
            background-color: #F5F7FA;
        }
        
        /* Sidebar - Deep Blue */
        [data-testid="stSidebar"] {
            background-color: #003249;
        }
        [data-testid="stSidebar"] * {
            color: #FFFFFF !important;
        }
        
        /* Headers & Text - Energy Blue */
        h1, h2, h3, h4 {
            color: #0E3A5D !important;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-weight: 700;
        }
        
        /* Metrics Cards */
        div[data-testid="stMetric"] {
            background-color: #FFFFFF;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            border-left: 5px solid #FF6B00; /* Orange Accent */
        }
        [data-testid="stMetricLabel"] {
            color: #6C757D !important;
            font-size: 14px;
        }
        [data-testid="stMetricValue"] {
            color: #0E3A5D !important;
            font-size: 28px;
            font-weight: bold;
        }
        
        /* Buttons - Call to Action Orange */
        .stButton > button {
            background-color: #FF6B00 !important;
            color: white !important;
            border-radius: 6px;
            border: none;
            padding: 0.5rem 1rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            width: 100%;
        }
        .stButton > button:hover {
            background-color: #E65100 !important;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }

        /* Dataframes - Clean White */
        [data-testid="stDataFrame"] {
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        
        /* Charts */
        .js-plotly-plot .plotly .main-svg {
            background: rgba(255,255,255,0.5) !important;
            border-radius: 8px;
        }
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. HEADER
# -----------------------------------------------------------------------------
col_logo, col_title = st.columns([1, 20])
with col_title:
    st.markdown("# ⚡ VOLTAGE PRICER <span style='font-size:18px; color:#FF6B00; background:#fff; padding:2px 8px; border-radius:4px; border:1px solid #FF6B00'>ENTERPRISE</span>", unsafe_allow_html=True)
    st.markdown("**B2B Electricity Quoting Engine • Powered by XGBoost Forecasting**")

st.markdown("---")

# -----------------------------------------------------------------------------
# 4. INITIALIZATION & STATE
# -----------------------------------------------------------------------------
# Initialisation du gestionnaire de marché (une seule fois si possible)
if 'market_data' not in st.session_state:
    with st.spinner("Connecting to Market Data Feeds..."):
        manager = MarketDataManager()
        st.session_state['market_data'] = manager.get_forward_prices()

MARKET_PRICES = st.session_state['market_data']

# -----------------------------------------------------------------------------
# 5. SIDEBAR CONFIGURATION
# -----------------------------------------------------------------------------
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/9/9d/TotalEnergies_logo.svg/2560px-TotalEnergies_logo.svg.png", width=150)
    st.markdown("### 👤 CLIENT PROFILE")
    
    client_name = st.text_input("Account Name", "Industrie du Nord SA")
    annual_volume = st.number_input("Annual Vol. (MWh)", min_value=100, max_value=1000000, value=15000, step=1000)
    profile_type = st.selectbox(
        "Load Profile Type", 
        ["INDUSTRY_24_7", "OFFICE_BUILDING", "SOLAR_PPA"],
        index=0,
        help="Determines the shape of consumption."
    )

    st.markdown("---")
    st.markdown("### 💰 MARKET PARAMETERS")
    
    base_price = st.number_input(
        "Cal-26 BASE (€/MWh)", 
        value=MARKET_PRICES.get('CAL_BASE', 95.5),
        step=0.5
    )
    # Update local market view
    MARKET_PRICES['CAL_BASE'] = base_price
    
    st.markdown("---")
    run_btn = st.button("GENERATE QUOTE")

# -----------------------------------------------------------------------------
# 6. MAIN ENGINE EXECUTION
# -----------------------------------------------------------------------------
if run_btn:
    try:
        # A. DATA GENERATION & ML FORECASTING
        with st.status("⚙️ Running Calculation Engine...", expanded=True) as status:
            
            st.write("🔹 Generating synthetic hourly load profile...")
            generator = LoadCurveGenerator(year=2026)
            load_curve = generator.generate_profile(profile_type, annual_volume)
            
            st.write("🔹 Training XGBoost model on 25 years of history...")
            pricing_engine = ElectricityPricingEngine(MARKET_PRICES)
            # Cette étape déclenche le training ML si nécessaire
            pricing_result = pricing_engine.compute_sourcing_cost(load_curve)
            
            st.write("🔹 Computing Risk Premiums (Profiling & Volume)...")
            # Récupération de la courbe de prix horaire générée par le ML pour le risque
            hpfc = pricing_engine.generate_hpfc(load_curve.index)
            risk_engine = RiskEngine(SETTINGS, MARKET_PRICES.get('SPOT_VOLATILITY', 0.25))
            
            profiling_cost = risk_engine.calculate_profiling_cost(load_curve, hpfc)
            volume_risk = risk_engine.calculate_volume_risk_premium(pricing_result.total_volume_mwh)
            
            # Calcul PPA Bonus si applicable
            ppa_data = None
            if profile_type == "SOLAR_PPA":
                st.write("🔹 Valuing Renewable Assets (Cannibalization)...")
                ppa_data = price_renewable_ppa("SOLAR", base_price)

            status.update(label="✅ Calculation Complete", state="complete", expanded=False)

        # B. COST STACK (Aggrégation)
        # Taxes et Marges
        grid_fees = SETTINGS.ELIA_GRID_FEE + SETTINGS.DISTRIBUTION_GRID_FEE
        taxes = SETTINGS.TAXES_AND_LEVIES + SETTINGS.GREEN_CERT_COST
        margin = 2.50 # Marge commerciale cible
        
        # Prix Final
        final_price = (
            pricing_result.weighted_average_price + 
            profiling_cost + 
            volume_risk + 
            grid_fees + 
            taxes + 
            margin
        )

        # ---------------------------------------------------------------------
        # 7. DASHBOARD DISPLAY
        # ---------------------------------------------------------------------
        
        # --- ROW 1: KEY METRICS ---
        st.markdown("### 📊 Executive Summary")
        m1, m2, m3, m4 = st.columns(4)
        
        with m1: st.metric("Total Volume", f"{pricing_result.total_volume_mwh:,.0f} MWh")
        with m2: st.metric("Commodity Cost", f"€{pricing_result.weighted_average_price:.2f}", delta="Base + Peak")
        with m3: st.metric("Risk Premium", f"€{profiling_cost + volume_risk:.2f}", delta="Profiling + Swing", delta_color="inverse")
        with m4: st.metric("FINAL PRICE", f"€{final_price:.2f}/MWh", delta="All Taxes Included")
        
        st.markdown("---")

        # --- ROW 2: VISUALIZATION & BREAKDOWN ---
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.markdown("#### 📈 Load vs Price Dynamics (Week 1)")
            # On affiche une semaine type pour voir la corrélation Conso / Prix
            viz_df = pd.DataFrame({
                "Consumption (MW)": load_curve,
                "Market Price (€/MWh)": hpfc
            })
            # Graphique double axe avec Plotly
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=viz_df.index[:168], y=viz_df["Consumption (MW)"][:168], name="Load (MW)", line=dict(color='#0E3A5D', width=2), fill='tozeroy'))
            fig.add_trace(go.Scatter(x=viz_df.index[:168], y=viz_df["Market Price (€/MWh)"][:168], name="Price (€/MWh)", line=dict(color='#FF6B00', width=2), yaxis="y2"))
            
            fig.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                yaxis=dict(title="Load (MW)", showgrid=False),
                yaxis2=dict(title="Price (€/MWh)", overlaying="y", side="right", showgrid=False),
                legend=dict(orientation="h", y=1.1),
                height=350,
                margin=dict(l=0, r=0, t=0, b=0)
            )
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("#### 📑 Cost Structure")
            cost_items = [
                {"Item": "Commodity (Base)", "Value": pricing_result.weighted_average_price},
                {"Item": "Profiling Risk", "Value": profiling_cost},
                {"Item": "Volume Risk", "Value": volume_risk},
                {"Item": "Grid Fees", "Value": grid_fees},
                {"Item": "Taxes & Levies", "Value": taxes},
                {"Item": "Margin", "Value": margin},
            ]
            df_costs = pd.DataFrame(cost_items)
            
            # Donut Chart pour la structure de coûts
            fig_pie = px.pie(df_costs, values='Value', names='Item', hole=0.7, color_discrete_sequence=px.colors.sequential.Blues_r)
            fig_pie.update_layout(showlegend=False, margin=dict(l=0, r=0, t=0, b=0), height=200)
            # Ajout du prix au centre
            fig_pie.add_annotation(text=f"<b>€{final_price:.0f}</b>", x=0.5, y=0.5, showarrow=False, font_size=20)
            
            st.plotly_chart(fig_pie, use_container_width=True)
            
            # Petit tableau récap
            st.dataframe(
                df_costs.style.format({"Value": "€{:.2f}"}), 
                hide_index=True, 
                use_container_width=True
            )

        # --- ROW 3: EXPORT & PPA ---
        col_export, col_ppa = st.columns([1, 2])
        
        with col_export:
            st.markdown("#### 💾 Deliverable")
            # Génération Excel
            excel_file = export_pricing_to_excel(
                df_costs, load_curve, annual_volume, MARKET_PRICES, final_price
            )
            st.download_button(
                label="DOWNLOAD EXCEL QUOTE",
                data=excel_file,
                file_name=f"Quote_{client_name.replace(' ', '_')}_2026.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        with col_ppa:
            if ppa_data:
                st.info(
                    f"**SOLAR PPA INSIGHT:** Based on the Capture Rate ({ppa_data.capture_rate}%), "
                    f"the fair fixed price for this asset is **€{ppa_data.fair_price:.2f}/MWh**. "
                    f"(Cannibalization Impact: -€{ppa_data.cannibalization_impact:.2f}/MWh)"
                )

    except Exception as e:
        st.error(f"⚠️ Calculation Error: {e}")
        st.error("Please check the logs or try different parameters.")

else:
    # État initial (Welcome screen)
    st.info("👈 Please configure the Client Profile in the sidebar and click 'GENERATE QUOTE'.")