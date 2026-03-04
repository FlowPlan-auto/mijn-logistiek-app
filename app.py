%%writefile app.py
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import numpy as np

# --- CONFIGURATIE ---
geolocator = Nominatim(user_agent="logistiek_expert_v1")

st.set_page_config(page_title="Route Expert Pro | Houthandel Optimalisatie", layout="wide")

st.title("🚚 Route Expert Pro")
st.markdown("### Bespaar op brandstof en tijd door slimme planning")

# --- SIDEBAR VOOR INPUT ---
st.sidebar.header("1. Voer Adressen In")
st.sidebar.info("Tip: Begin met het adres van je magazijn (Startpunt).")

data_input = st.sidebar.text_area(
    "Plak hier de adressen (één per regel):", 
    placeholder="Bedrijfsweg 1, Utrecht\nKerkstraat 5, Amsterdam\nCoolsingel 1, Rotterdam",
    height=200
)

# --- DE WISKUNDE FUNCTIES ---
def bereken_afstand(p1, p2):
    # Simpele berekening voor de demo (hemelsbreed)
    return np.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2) * 111 # Ongeveer km

if st.sidebar.button("🚀 Bereken Optimale Route"):
    if data_input:
        adressen = [a.strip() for a in data_input.split('\n') if a.strip()]
        
        if len(adressen) < 2:
            st.error("Voer minimaal 2 adressen in (Startpunt + 1 stop).")
        else:
            with st.spinner('Locaties worden gezocht en geoptimaliseerd...'):
                # 1. Geocoding (Adressen naar Coördinaten)
                coords = []
                valid_addresses = []
                for addr in adressen:
                    try:
                        loc = geolocator.geocode(addr)
                        if loc:
                            coords.append((loc.latitude, loc.longitude))
                            valid_addresses.append(addr)
                    except:
                        continue

                if len(coords) < 2:
                    st.error("Kon de locaties niet vinden. Controleer de spelling.")
                else:
                    # 2. Afstandsmatrix maken
                    num_locations = len(coords)
                    dist_matrix = np.zeros((num_locations, num_locations))
                    for i in range(num_locations):
                        for j in range(num_locations):
                            dist_matrix[i][j] = bereken_afstand(coords[i], coords[j]) * 1000 # In meters voor OR-Tools

                    # 3. OR-Tools Solver (Het 'Brein')
                    manager = pywrapcp.RoutingIndexManager(num_locations, 1, 0)
                    routing = pywrapcp.RoutingModel(manager)

                    def distance_callback(from_index, to_index):
                        return int(dist_matrix[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)])

                    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
                    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

                    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
                    search_parameters.first_solution_strategy = (
                        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
                    )

                    solution = routing.SolveWithParameters(search_parameters)

                    # 4. Resultaten Tonen
                    if solution:
                        index = routing.Start(0)
                        route_order = []
                        total_distance = 0
                        while not routing.IsEnd(index):
                            prev_index = index
                            route_order.append(manager.IndexToNode(index))
                            index = solution.Value(routing.NextVar(index))
                            total_distance += routing.GetArcCostForVehicle(prev_index, index, 0)

                        # Layout van de resultaten
                        st.success(f"Route geoptimaliseerd! Totaal geschatte afstand: {round(total_distance/1000, 1)} km")
                        
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            # Kaart met Folium
                            m = folium.Map(location=coords[0], zoom_start=8)
                            points = [coords[i] for i in route_order]
                            
                            folium.PolyLine(points, color="#2E86C1", weight=4, opacity=0.8).add_to(m)
                            
                            for i, idx in enumerate(route_order):
                                color = 'green' if i == 0 else 'blue'
                                folium.Marker(
                                    coords[idx], 
                                    popup=f"Stop {i}: {valid_addresses[idx]}",
                                    icon=folium.Icon(color=color, icon='info-sign')
                                ).add_to(m)
                            
                            st_folium(m, width=700, height=500)

                        with col2:
                            st.write("### 📋 Rijvolgorde")
                            for i, idx in enumerate(route_order):
                                icon = "🏠" if i == 0 else "📍"
                                st.write(f"{icon} **Stop {i}:** {valid_addresses[idx]}")
                            
                            st.download_button(
                                "Download Route (Tekst)", 
                                "\n".join([f"Stop {i}: {valid_addresses[idx]}" for i, idx in enumerate(route_order)]),
                                file_name="route_planning.txt"
                            )
    else:
        st.warning("Voer eerst adressen in de zijbalk in.")
else:
    st.info("👋 Welkom! Voer links de adressen in en klik op de knop om de meest efficiënte route te zien.")

# --- FOOTER ---
st.markdown("---")
st.caption("Route Expert Pro v1.0 - Gebouwd voor de houthandel sector.")
