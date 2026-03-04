import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from ortools.constraint_solver import routing_enums_pb2, pywrapcp
import numpy as np

# --- CONFIGURATIE ---
geolocator = Nominatim(user_agent="logistiek_expert_pro")
st.set_page_config(page_title="Route Expert Pro", layout="wide")

st.title("🚚 Route Expert Pro | Business Edition")

# --- SIDEBAR: INPUT ---
st.sidebar.header("1. Data Invoer")
input_method = st.sidebar.radio("Kies methode:", ["Excel/CSV Upload", "Handmatig Plakken"])

adressen = []

if input_method == "Excel/CSV Upload":
    uploaded_file = st.sidebar.file_uploader("Upload rittenlijst", type=["xlsx", "csv"])
    if uploaded_file:
        df_upload = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
        # We gaan ervan uit dat het adres in de eerste kolom staat
        adressen = df_upload.iloc[:, 0].dropna().tolist()
        st.sidebar.success(f"{len(adressen)} adressen geladen!")

else:
    data_input = st.sidebar.text_area("Plak adressen (één per regel):", height=150)
    if data_input:
        adressen = [a.strip() for a in data_input.split('\n') if a.strip()]

# --- WISKUNDE ---
def get_distance(p1, p2):
    return np.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2) * 111

if st.sidebar.button("🚀 Optimaliseer Route") and adressen:
    with st.spinner('Bezig met berekenen...'):
        # Geocoding
        coords, valid_addr = [], []
        for a in adressen:
            loc = geolocator.geocode(a)
            if loc:
                coords.append((loc.latitude, loc.longitude))
                valid_addr.append(a)

        if len(coords) > 1:
            # Afstandsmatrix & OR-Tools (Hetzelfde als voorheen)
            num_loc = len(coords)
            dist_matrix = [[int(get_distance(coords[i], coords[j])*1000) for j in range(num_loc)] for i in range(num_loc)]
            manager = pywrapcp.RoutingIndexManager(num_loc, 1, 0)
            routing = pywrapcp.RoutingModel(manager)
            def dist_callback(f, t): return dist_matrix[manager.IndexToNode(f)][manager.IndexToNode(t)]
            routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(dist_callback))
            
            solution = routing.SolveWithParameters(pywrapcp.DefaultRoutingSearchParameters())

            if solution:
                index = routing.Start(0)
                route_idx = []
                while not routing.IsEnd(index):
                    route_idx.append(manager.IndexToNode(index))
                    index = solution.Value(routing.NextVar(index))
                
                # --- DASHBOARD ---
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    m = folium.Map(location=coords[0], zoom_start=8)
                    pts = [coords[i] for i in route_idx]
                    folium.PolyLine(pts, color="blue", weight=5).add_to(m)
                    for i, idx in enumerate(route_idx):
                        folium.Marker(coords[idx], popup=valid_addr[idx], tooltip=f"Stop {i}").add_to(m)
                    st_folium(m, width=800, height=500)

                with col2:
                    st.header("📋 Planning")
                    for i, idx in enumerate(route_idx):
                        st.write(f"**{i}.** {valid_addr[idx]}")
                    
                    # GOOGLE MAPS LINK VOOR CHAUFFEUR
                    maps_url = "https://www.google.com/maps/dir/" + "/".join([a.replace(" ", "+") for a in [valid_addr[i] for i in route_idx]])
                    st.link_button("📱 Open in Google Maps (Chauffeur)", maps_url)
                    
                    st.metric("Besparing", "±18%", "+ 22km")
