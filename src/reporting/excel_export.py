import pandas as pd
import numpy as np
import io
import xlsxwriter
from typing import Dict, Any, cast
from xlsxwriter.workbook import Workbook
from xlsxwriter.chart import Chart # <--- Import nécessaire pour le typage

def export_pricing_to_excel(df_costs: pd.DataFrame, load_curve: pd.Series, volume: float, market_prices: Dict[str, float], final_price: float) -> io.BytesIO:
    """
    Génère un export Excel sophistiqué avec onglets de synthèse, détail des coûts et graphique.
    Utilise XlsxWriter pour un rendu professionnel "TotalEnergies Style".
    """
    output = io.BytesIO()
    
    # Utilisation de XlsxWriter comme moteur
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        
        # FIX TYPAGE 1: On force le type Workbook
        workbook = cast(Workbook, writer.book)
        
        # --- FORMATS ---
        header_format = workbook.add_format({'bold': True, 'bg_color': '#0E3A5D', 'font_color': 'white', 'border': 1})
        currency_format = workbook.add_format({'num_format': '€#,##0.00'})
        bold_currency = workbook.add_format({'bold': True, 'num_format': '€#,##0.00', 'font_color': '#FF6B00'})
        
        # ==========================================
        # ONGLET 1: SYNTHÈSE DU DEVIS
        # ==========================================
        df_summary = pd.DataFrame({
            "Indicateur Clé": [
                "Volume Annuel (MWh)", 
                "Prix Base (Cal-26)", 
                "Prix Peak (Cal-26)", 
                "",
                "PRIX VENTE FINAL (€/MWh)",
                "Budget Total Estimé (€)"
            ],
            "Valeur": [
                volume, 
                market_prices.get('CAL_BASE', 0), 
                market_prices.get('CAL_PEAK', 0), 
                np.nan,
                final_price,
                final_price * volume
            ]
        })
        
        df_summary.to_excel(writer, sheet_name='Synthèse Commerciale', index=False, startrow=1)
        worksheet_sum = writer.sheets['Synthèse Commerciale']
        
        worksheet_sum.write(0, 0, "OFFRE DE FOURNITURE D'ÉLECTRICITÉ - SYNTHÈSE", header_format)
        worksheet_sum.set_column('A:A', 30)
        worksheet_sum.set_column('B:B', 20, currency_format)
        
        worksheet_sum.write(6, 1, final_price, bold_currency)
        worksheet_sum.write(7, 1, final_price * volume, bold_currency)

        # ==========================================
        # ONGLET 2: DÉTAIL DES COÛTS
        # ==========================================
        df_costs.to_excel(writer, sheet_name='Décomposition Coûts', index=False, startrow=1)
        worksheet_cost = writer.sheets['Décomposition Coûts']
        
        worksheet_cost.write(0, 0, "DÉTAIL DE LA STRUCTURE DE PRIX (€/MWh)", header_format)
        worksheet_cost.set_column('A:A', 35)
        worksheet_cost.set_column('B:B', 20, currency_format)
        
        # ==========================================
        # ONGLET 3: COURBE DE CHARGE (DATA + GRAPH)
        # ==========================================
        df_load = load_curve.to_frame(name="Puissance (MW)")
        df_load.index.name = "Horodatage"
        
        df_load.to_excel(writer, sheet_name='Données Horaires')
        worksheet_load = writer.sheets['Données Horaires']
        worksheet_load.set_column('A:A', 20)
        
        # FIX TYPAGE 2: On force le type Chart pour accéder aux méthodes (add_series, etc.)
        chart = cast(Chart, workbook.add_chart({'type': 'line'}))
        
        # Maintenant Pylance reconnaît ces méthodes
        chart.add_series({
            'name':       '=Données Horaires!$B$1',
            'categories': '=Données Horaires!$A$2:$A$169', # Axe X: Dates (168 points)
            'values':     '=Données Horaires!$B$2:$B$169', # Axe Y: Puissance (168 points)
            'line':       {'color': '#0E3A5D'},
        })
        
        chart.set_title({'name': 'Profil de Consommation (Semaine Type)'})
        chart.set_x_axis({'name': 'Heure'})
        chart.set_y_axis({'name': 'MW'})
        chart.set_size({'width': 720, 'height': 400})
        
        worksheet_load.insert_chart('D2', chart)
        
    output.seek(0)
    return output