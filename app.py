import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import openrouteservice
from ortools.constraint_solver import routing_enums_pb2, pywrapcp
import time

# --- CONFIGURATIE ---
# Je HeiGIT / OpenRouteService Key
ORS_API_KEY = 'eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjlhZTJlMzRmYTg5MDRmMDk5MGU4NGIyNjgyMTZjMTNlIiwiaCI6Im11cm11cjY0In0='
client = openrouteservice.Client(key=ORS_API_KEY)

st.set_page_config(page_title="LogiPlan Pro | Business Edition", layout="wide")

# Custom Styling
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { border: 1px solid #ddd; padding: 10px; border-radius: 5px; background: white; }
    </style>
    """, unsafe_allow_html=True)

st.title("🚚 LogiPlan Pro")
st.subheader("Route Optimalisatie Prototype (OpenRouteService Powered)")

# --- SIDEBAR ---
st.sidebar.header("📍 Data Invoer")
input_method = st.sidebar.selectbox("Kies methode", ["Handmatig", "Excel/CSV Upload"])

adressen = []
if input_method == "Handmatig":
    input_text = st.sidebar.text_area("Adressen (Startpunt = regel 1):", 
                                     "Seattleweg 7, Rotterdam\nThurledeweg 1, Rotterdam\nHoofdweg 100, Capelle aan den IJssel", 
                                     height=200)
    adressen = [a.strip() for a in input_text.split('\n') if a.strip()]
else:
    uploaded_file = st.sidebar.file_uploader("Upload rittenlijst", type=["xlsx", "csv"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
        # Pakt de eerste kolom
        adressen = df.iloc[:, 0].dropna().tolist()

# --- DE LOGICA ---
if st.sidebar.button("🚀 Optimaliseer 30+ Stops") and len(adressen) > 1:
    with st.spinner('Bezig met Geocoding en Route-berekening...'):
        coords = []
        valid_addr = []
        
        # 1. Geocoding (Adres -> Coördinaten)
        for a in adressen:
            try:
                # We gebruiken Pelias van ORS
                res = client.pelias_search(text=a, size=1)
                if res['features']:
                    lon, lat = res['features'][0]['geometry']['coordinates']
                    coords.append([lat, lon]) # Voor Folium
                    valid_addr.append(a)
                time.sleep(0.1) # Netjes blijven voor de API
            except Exception as e:
                st.warning(f"Kon adres niet vinden: {a}")

        if len(coords) > 1:
            # 2. Afstandsmatrix opvragen bij ORS (Wegkilometers)
            ors_coords = [[c[1], c[0]] for c in coords] # ORS wil [lon, lat]
            try:
                matrix = client.distance_matrix(
                    locations=ors_coords, 
                    profile='driving-car', 
                    metrics=['distance']
                )
                dist_matrix = matrix['distances']

                # 3. Google OR-Tools Solver
                num_loc = len(coords)
                manager = pywrapcp.RoutingIndexManager(num_loc, 1, 0)
                routing = pywrapcp.RoutingModel(manager)
                
                def d_cb(f, t): 
                    return int(dist_matrix[manager.IndexToNode(f)][manager.IndexToNode(t)])
                
                transit_callback_index = routing.RegisterTransitCallback(d_cb)
                routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
                
                search_params = pywrapcp.DefaultRoutingSearchParameters()
                search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
                
                solution = routing.SolveWithParameters(search_params)

                if solution:
                    index = routing.Start(0)
                    route_idx = []
                    while not routing.IsEnd(index):
                        route_idx.append(manager.IndexToNode(index))
                        index = solution.Value(routing.NextVar(index))
                    
                    total_dist_km = solution.ObjectiveValue() / 1000

                    # --- RESULTATEN ---
                    st.success(f"Route succesvol geoptimaliseerd!")
                    m1, m2 = st.columns(2)
                    m1.metric("Totale Afstand", f"{round(total_dist_km, 1)} km")
                    m2.metric("Aantal Stops", f"{len(route_idx)}")

                    c1, c2 = st.columns([2, 1])
                    with c1:
                        # Kaart
                        m = folium.Map(location=coords[0], zoom_start=11)
                        pts = [coords[i] for i in route_idx]
                        folium.PolyLine(pts, color="#2E86C1", weight=5, opacity=0.8).add_to(m)
                        
                        for i, idx in enumerate(route_idx):
                            color = 'green' if i == 0 else 'blue'
                            folium.Marker(coords[idx], 
                                          popup=f"Stop {i}: {valid_addr[idx]}",
                                          icon=folium.Icon(color=color)).add_to(m)
                        st_folium(m, width=800, height=500)

                    with c2:
                        st.write("### 📋 Rijvolgorde")
                        for i, idx in enumerate(route_idx):
                            st.write(f"**{i}.** {valid_addr[idx]}")
                            # Knop naar Google Maps voor chauffeur
                            maps_url = f"https://www.google.com/maps/dir/?api=1&destination={valid_addr[idx].replace(' ', '+')}"
                            st.link_button(f"🧭 Navigeer naar stop {i}", maps_url)

            except Exception as e:
                st.error(f"Matrix fout: {e}")
        else:
            st.error("Niet genoeg geldige locaties gevonden.")
else:
    st.info("👋 Upload een Excel of voer adressen in en klik op 'Optimaliseer'.")
