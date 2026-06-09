#
# Żeby to uruchumoić trzeba puścić tą komendę w terminalu : bokeh serve vis.py --address 0.0.0.0 --port 5006 --allow-websocket-origin=*
# I w yamlu dodać port "5006:5006"
import pandas as pd
import sqlite3
import numpy as np
import xyzservices.providers as xyz
from bokeh.io import curdoc
from bokeh.models import ColumnDataSource, DataTable, TableColumn, HTMLTemplateFormatter, Div, Toggle
from bokeh.plotting import figure
from bokeh.layouts import column, row

# Funkcja konwertująca GPS (WGS84) na współrzędne mapy (Web Mercator) wymagane przez Bokeh
def wgs84_to_web_mercator(df, lon="longitude", lat="latitude"):
    k = 6378137
    df["x"] = df[lon] * (k * np.pi/180.0)
    df["y"] = np.log(np.tan((90 + df[lat]) * np.pi/360.0)) * k
    return df

def load_data():
    try:
        conn = sqlite3.connect('flights.db')
        df_live = pd.read_sql_query("SELECT * FROM live_flights", conn)
        if 'velocity_pred' not in df_live.columns:
            df_live['velocity_pred'] = 0
        cursor = conn.cursor()
        cursor.execute("SELECT count(name) FROM sqlite_master WHERE type='table' AND name='alerts_log'")
        if cursor.fetchone()[0] == 1:
            df_alerts = pd.read_sql_query("SELECT * FROM alerts_log ORDER BY rowid DESC LIMIT 15", conn)
        else:
            df_alerts = pd.DataFrame(columns=['callsign', 'origin_country', 'is_military_takeoff', 'is_overspeed', 'altitude'])
        conn.close()
        
        if not df_live.empty:
            df_live = wgs84_to_web_mercator(df_live)            
            #dodane: różnica modelu
            if 'velocity_pred' in df_live.columns:
                df_live['model_diff'] = abs(df_live['velocity_pred'] - df_live['velocity'])
            else:
                df_live['model_diff'] = 0   
            if len(df_live) > 5:
                threshold = df_live['model_diff'].mean() + df_live['model_diff'].std()
            else:
                threshold = 50
            #oryginalne kolory
            df_live['color'] = np.where(df_live['is_military_takeoff'] | df_live['is_overspeed'], 'red', 'blue')
            #dodane: odchylenie od modelu
            df_live.loc[df_live['model_diff'] > threshold, 'color'] = 'yellow'
            # Rozmiar kropki: większy dla anomalii
            df_live['size'] = np.where(df_live['is_military_takeoff'] | df_live['is_overspeed'], 12, 6)
        else:
            df_live = pd.DataFrame(columns=['x', 'y', 'callsign', 'color', 'size'])
            
        return df_live, df_alerts
    except Exception as e:
        return pd.DataFrame(columns=['x', 'y', 'callsign', 'color', 'size']), pd.DataFrame()

# Inicjalizacja danych
df_live_init, df_alerts_init = load_data()
source_live = ColumnDataSource(df_live_init)
source_alerts = ColumnDataSource(df_alerts_init)

# --- BUDOWA INTERFEJSU BOKEH ---

# 1. Nagłówek
header = Div(text="<h1>🛰️ System Monitorowania Ruchu Lotniczego (Live)</h1>", width=1200)
threshold_div = Div(text="Próg anomalii: ładowanie...", width=400) #dodane
toggle = Toggle(label="Tylko anomalie", active=False) #dodane
legend_div = Div(text="""
<b>Legenda kolorów:</b><br>
<span style="color:blue;">●</span> Normalny lot<br>
<span style="color:red;">●</span> Alert (Start wojskowy/Przekroczenie prędkości)<br>
<span style="color:yellow;">●</span> Anomalia z modelu<br>
""", width=300) #dodana legenda
# 2. Mapa
p = figure(x_axis_type="mercator", y_axis_type="mercator", width=800, height=600, 
           title="Mapa Przestrzeni Powietrznej", tools="pan,wheel_zoom,reset",
           tooltips=[("Callsign", "@callsign"), ("Wysokość", "@altitude m"), ("Kraj", "@origin_country"), ("Prędkość", "@velocity"), ("Przewidziana prędkość", "@velocity_pred")])

# Dodanie podkładu mapy (OpenStreetMap) przy użyciu xyzservices
p.add_tile(xyz.OpenStreetMap.Mapnik)

# Rysowanie samolotów
p.circle(x='x', y='y', size='size', color='color', alpha=0.8, source=source_live)

# 3. Tabela Alertów
columns = [
    TableColumn(field="callsign", title="Callsign"),
    TableColumn(field="origin_country", title="Kraj"),
    TableColumn(field="is_military_takeoff", title="Start Wojskowy"),
    TableColumn(field="is_overspeed", title="Przekroczenie Prędkości"),
    TableColumn(field="altitude", title="Wysokość (m)"),
    TableColumn(field="velocity", title="Prędkość"),
    TableColumn(field="velocity_pred", title="Przewidziana prędkość")
]
data_table = DataTable(source=source_alerts, columns=columns, width=500, height=600)

# Ułożenie elementów na stronie
layout = column(header, toggle, threshold_div, legend_div, row(p, data_table))
curdoc().add_root(layout)
curdoc().title = "Radar Lotniczy"

# --- AKTUALIZACJA DANYCH W CZASIE RZECZYWISTYM ---
def update():
    df_live_new, df_alerts_new = load_data()
    #dodane: wyświetlenie progu
    if len(df_live_new) > 5:
        threshold_val = df_live_new['model_diff'].mean() + df_live_new['model_diff'].std()
    else:
        threshold_val = 50
    threshold_div.text = f"<b>Próg wykrycia anomalii z modelu:</b> {threshold_val:.2f}"
    #dodane: filtr anomalii
    if toggle.active:  
        df_live_new = df_live_new[
                    (df_live_new['is_military_takeoff']) |
                    (df_live_new['is_overspeed']) |
                    (df_live_new['model_diff'] > (df_live_new['model_diff'].mean() + df_live_new['model_diff'].std()))
        ]
    # Aktualizacja źródeł danych (Bokeh automatycznie odświeży mapę i tabelę w przeglądarce)
    source_live.data = dict(ColumnDataSource(df_live_new).data)
    source_alerts.data = dict(ColumnDataSource(df_alerts_new).data)

# Dodanie wywołania funkcji update() co 3000 milisekund (3 sekundy)
curdoc().add_periodic_callback(update, 3000)