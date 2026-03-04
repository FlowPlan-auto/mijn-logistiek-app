import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import openrouteservice
from ortools.constraint_solver import routing_enums_pb2, pywrapcp
import time

# --- CONFIGURATIE ---
ORS_API_KEY = 'eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjlhZTJlMzRmYTg5MDRmMDk5MGU4NGIyNjgyMTZjMTNlIiwiaCI6Im11cm11cjY0In0='
client = openrouteservice.Client(key=ORS_API_KEY)

st.set_page_config(page_title="LogiPlan Pro | Business Edition", layout="wide")

# Initialiseer het geheugen (session_state)
if 'route_results' not in st.session_state:
    st.session_state.route_results = None

st.title("🚚 LogiPlan Pro")
st.subheader("Route Optimalisatie Prototype")

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
        adressen = df.iloc[:, 0].dropna().tolist()

# --- BEREKENING ---
if st.sidebar.button("🚀 Optimaliseer Route"):
    if len(adressen) > 1:
        with st.spinner('Bezig met Geocoding en Route-berekening...'):
            coords, valid_addr = [], []
            for a in adressen:
                try:
                    res = client.pelias_search(text=a, size=1)
                    if res['features']:
                        lon, lat = res['features'][0]['geometry']['coordinates']
                        coords.append([lat, lon])
                        valid_addr.append(a)
                    time.sleep(0.1)
                except:
                    continue

            if len(coords) > 1:
                ors_coords = [[c[1], c[0]] for c in coords]
                matrix = client.distance_matrix(locations=ors_coords, profile='driving-car', metrics=['distance'])
                dist_matrix = matrix['distances']

                num_loc = len(coords)
                manager = pywrapcp.RoutingIndexManager(num_loc, 1, 0)
                routing = pywrapcp.RoutingModel(manager)
                def d_cb(f, t): return int(dist_matrix[manager.IndexToNode(f)][manager.IndexToNode(t)])
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
                    
                    # Sla ALLES op in het geheugen
                    st.session_state.route_results = {
                        'dist': solution.ObjectiveValue() / 1000,
                        'order': route_idx,
                        'coords': coords,
                        'addr': valid_addr
                    }

# --- WEERGAVE (UIT HET GEHEUGEN) ---
if st.session_state.route_results:
    res = st.session_state.route_results
    st.success(f"Route succesvol geoptimaliseerd!")
    
    col_m1, col_m2 = st.columns(2)
    col_m1.metric("Totale Afstand", f"{round(res['dist'], 1)} km")
    col_m2.metric("Aantal Stops", f"{len(res['order'])}")

    c1, c2 = st.columns([2, 1])
    with c1:
        # We maken de kaart uniek met een 'key' zodat hij niet herlaadt
        m = folium.Map(location=res['coords'][0], zoom_start=11)
        pts = [res['coords'][i] for i in res['order']]
        folium.PolyLine(pts, color="#2E86C1", weight=5).add_to(m)
        for i, idx in enumerate(res['order']):
            color = 'green' if i == 0 else 'blue'
            folium.Marker(res['coords'][idx], popup=f"Stop {i}: {res['addr'][idx]}").add_to(m)
        
        st_folium(m, width=800, height=500, key="main_map")

    with c2:
        st.write("### 📋 Rijvolgorde")
        for i, idx in enumerate(res['order']):
            st.info(f"**{i}.** {res['addr'][idx]}")
            maps_url = f"https://www.google.com/maps/dir/?api=1&destination={res['addr'][idx].replace(' ', '+')}"
            st.link_button(f"🧭 Navigeer naar stop {i}", maps_url)
else:
    st.info("👋 Upload een Excel of voer adressen in en klik op 'Optimaliseer'.")
