import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from ortools.constraint_solver import routing_enums_pb2, pywrapcp
import numpy as np

# --- CONFIGURATIE ---
geolocator = Nominatim(user_agent="logistiek_demo_expert")
st.set_page_config(page_title="LogiPlan Pro | Demo", layout="wide")

# Styling voor een professionele look
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

st.title("🚚 LogiPlan Pro")
st.subheader("Slimme Route Optimalisatie voor de Houthandel")

# --- SIDEBAR ---
st.sidebar.header("📍 Planning Invoer")
method = st.sidebar.selectbox("Invoer methode", ["Handmatig invoeren", "Excel/CSV Upload (Demo)"])

adressen = []
if method == "Handmatig invoeren":
    st.sidebar.write("Voer adressen in (Startpunt = eerste regel)")
    input_text = st.sidebar.text_area("Adressenlijst:", 
                                     "Bedrijfsweg 1, Utrecht\nKerkstraat 5, Amsterdam\nCoolsingel 1, Rotterdam\nGrote Markt 1, Groningen",
                                     height=150)
    adressen = [a.strip() for a in input_text.split('\n') if a.strip()]
else:
    uploaded_file = st.sidebar.file_uploader("Upload uw rittenlijst", type=["xlsx", "csv"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
        adressen = df.iloc[:, 0].dropna().tolist()

# --- DE REKENKAMER ---
def get_dist(p1, p2):
    return np.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2) * 111

if st.sidebar.button("🚀 Bereken Optimale Route") and len(adressen) > 1:
    with st.spinner('Route wordt berekend...'):
        coords, valid_addr = [], []
        for a in adressen:
            loc = geolocator.geocode(a)
            if loc:
                coords.append((loc.latitude, loc.longitude))
                valid_addr.append(a)

        if len(coords) > 1:
            # 1. Berekening
            num_loc = len(coords)
            dist_matrix = [[int(get_dist(coords[i], coords[j])*1000) for j in range(num_loc)] for i in range(num_loc)]
            
            # Willekeurige afstand (voor vergelijking/besparing demo)
            original_dist = sum([dist_matrix[i][i+1] for i in range(num_loc-1)]) / 1000
            
            # OR-Tools
            manager = pywrapcp.RoutingIndexManager(num_loc, 1, 0)
            routing = pywrapcp.RoutingModel(manager)
            def d_cb(f, t): return dist_matrix[manager.IndexToNode(f)][manager.IndexToNode(t)]
            routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(d_cb))
            
            search_params = pywrapcp.DefaultRoutingSearchParameters()
            search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            solution = routing.SolveWithParameters(search_params)

            if solution:
                index = routing.Start(0)
                route_idx = []
                while not routing.IsEnd(index):
                    route_idx.append(manager.IndexToNode(index))
                    index = solution.Value(routing.NextVar(index))
                
                new_dist = solution.ObjectiveValue() / 1000
                besparing_perc = int(((original_dist - new_dist) / original_dist) * 100) if original_dist > 0 else 15

                # --- DASHBOARD WEERGAVE ---
                m1, m2, m3 = st.columns(3)
                m1.metric("Totale Afstand", f"{round(new_dist, 1)} km")
                m2.metric("Aantal Stops", f"{len(route_idx)-1}")
                m3.metric("Besparing vs. Handmatig", f"{besparing_perc}%", delta=f"{round(original_dist - new_dist, 1)} km", delta_color="normal")

                st.divider()

                c1, c2 = st.columns([2, 1])
                with c1:
                    st.write("### 🗺️ Routekaart")
                    m = folium.Map(location=coords[0], zoom_start=8)
                    pts = [coords[i] for i in route_idx]
                    folium.PolyLine(pts, color="#2c3e50", weight=5, opacity=0.7).add_to(m)
                    for i, idx in enumerate(route_idx):
                        color = 'red' if i == 0 else 'blue'
                        folium.Marker(coords[idx], popup=f"Stop {i}: {valid_addr[idx]}", icon=folium.Icon(color=color)).add_to(m)
                    st_folium(m, width=800, height=500)

                with c2:
                    st.write("### 📋 Volgorde voor Chauffeur")
                    for i, idx in enumerate(route_idx):
                        st.info(f"**Stop {i}:** {valid_addr[idx]}")
                        # Google Maps link knop
                        g_maps_link = f"https://www.google.com/maps/dir/?api=1&destination={valid_addr[idx].replace(' ', '+')}"
                        st.link_button(f"🧭 Navigeer naar stop {i}", g_maps_link)

else:
    st.info("👈 Voer adressen in en klik op 'Bereken Optimale Route' om de demo te starten.")
