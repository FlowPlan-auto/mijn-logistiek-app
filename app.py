import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import openrouteservice
from ortools.constraint_solver import routing_enums_pb2, pywrapcp
import time

# --- ENTERPRISE CONFIGURATIE ---
ORS_API_KEY = 'eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjlhZTJlMzRmYTg5MDRmMDk5MGU4NGIyNjgyMTZjMTNlIiwiaCI6Im11cm11cjY0In0='
client = openrouteservice.Client(key=ORS_API_KEY)

st.set_page_config(page_title="LogiPlan Enterprise | Route Optimization", layout="wide")

# CSS voor een strakke, zakelijke uitstraling
st.markdown("""
    <style>
    .reportview-container { background: #f0f2f6; }
    .stMetric { border: 1px solid #d1d5db; padding: 20px; border-radius: 4px; background: #ffffff; color: #111827; }
    div[data-testid="stExpander"] { border: 1px solid #d1d5db; border-radius: 4px; background: #ffffff; }
    .stButton>button { background-color: #1e40af; color: white; border-radius: 2px; width: 100%; border: none; height: 3em; font-weight: bold; }
    .stButton>button:hover { background-color: #1e3a8a; border: none; }
    h1, h2, h3 { color: #111827; font-family: 'Inter', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

if 'fleet_results' not in st.session_state:
    st.session_state.fleet_results = None

st.title("LogiPlan Enterprise")
st.caption("Advanced Fleet Dispatching & Route Optimization Engine")

# --- SIDEBAR: CONTROLS ---
st.sidebar.header("Configuration")
num_vehicles = st.sidebar.number_input("Aantal voertuigen", min_value=1, max_value=10, value=2)
max_capacity = st.sidebar.number_input("Maximale stops per voertuig", min_value=1, max_value=50, value=15)

st.sidebar.markdown("---")
input_method = st.sidebar.selectbox("Data Input", ["Excel/CSV Upload", "Manual Entry"])

adressen = []
if input_method == "Manual Entry":
    input_text = st.sidebar.text_area("Adressen (Startpunt op regel 1):", height=200)
    adressen = [a.strip() for a in input_text.split('\n') if a.strip()]
else:
    uploaded_file = st.sidebar.file_uploader("Upload Fleet Data", type=["xlsx", "csv"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
        adressen = df.iloc[:, 0].dropna().tolist()

# --- OPTIMIZATION ENGINE ---
if st.sidebar.button("RUN OPTIMIZATION"):
    if len(adressen) > 1:
        with st.spinner('Calculating optimal fleet distribution...'):
            coords, valid_addr = [], []
            for a in adressen:
                try:
                    res = client.pelias_search(text=a, size=1)
                    if res['features']:
                        lon, lat = res['features'][0]['geometry']['coordinates']
                        coords.append([lat, lon])
                        valid_addr.append(a)
                    time.sleep(0.05)
                except: continue

            if len(coords) > 1:
                ors_coords = [[c[1], c[0]] for c in coords]
                matrix = client.distance_matrix(locations=ors_coords, profile='driving-car', metrics=['distance'])
                dist_matrix = matrix['distances']

                # OR-Tools for VRP (Vehicle Routing Problem)
                num_loc = len(coords)
                manager = pywrapcp.RoutingIndexManager(num_loc, num_vehicles, 0)
                routing = pywrapcp.RoutingModel(manager)
                
                def d_cb(f, t): return int(dist_matrix[manager.IndexToNode(f)][manager.IndexToNode(t)])
                transit_callback_index = routing.RegisterTransitCallback(d_cb)
                routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
                
                # Capaciteit toevoegen
                def demand_callback(from_index): return 1
                demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
                routing.AddDimension(demand_callback_index, 0, max_capacity, True, 'Capacity')

                search_params = pywrapcp.DefaultRoutingSearchParameters()
                search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
                solution = routing.SolveWithParameters(search_params)

                if solution:
                    fleet_data = []
                    for vehicle_id in range(num_vehicles):
                        index = routing.Start(vehicle_id)
                        route = []
                        while not routing.IsEnd(index):
                            node_idx = manager.IndexToNode(index)
                            route.append(node_idx)
                            index = solution.Value(routing.NextVar(index))
                        if len(route) > 1: # Alleen wagens met stops
                            fleet_data.append({'vehicle': vehicle_id + 1, 'path': route})
                    
                    st.session_state.fleet_results = {
                        'fleet': fleet_data,
                        'coords': coords,
                        'addr': valid_addr
                    }

# --- DASHBOARD DISPLAY ---
if st.session_state.fleet_results:
    res = st.session_state.fleet_results
    
    m1, m2 = st.columns(2)
    m1.metric("Actieve Voertuigen", len(res['fleet']))
    m2.metric("Totaal Aantal Stops", len(res['addr']) - 1)

    st.markdown("### Operational Overview")
    
    c1, c2 = st.columns([2, 1])
    with c1:
        m = folium.Map(location=res['coords'][0], zoom_start=10, tiles='cartodbpositron')
        colors = ['#1e40af', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']
        
        for i, vehicle in enumerate(res['fleet']):
            color = colors[i % len(colors)]
            pts = [res['coords'][idx] for idx in vehicle['path']]
            folium.PolyLine(pts, color=color, weight=4, opacity=0.8, tooltip=f"Voertuig {vehicle['vehicle']}").add_to(m)
            for stop_idx in vehicle['path']:
                folium.CircleMarker(res['coords'][stop_idx], radius=5, color=color, fill=True).add_to(m)
        
        st_folium(m, width=800, height=500, key="enterprise_map")

    with c2:
        for vehicle in res['fleet']:
            with st.expander(f"VOERTUIG {vehicle['vehicle']} - DETAILS"):
                stops = [res['addr'][i] for i in vehicle['path']]
                st.write(f"Aantal stops: {len(stops) - 1}")
                
                # Gecombineerde Google Maps Link
                # Formaat: /dir/Origin/Stop1/Stop2/.../Destination
                origin = stops[0].replace(' ', '+')
                dest = stops[-1].replace(' ', '+')
                waypts = "|".join([s.replace(' ', '+') for s in stops[1:-1]])
                
                if waypts:
                    g_maps_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}&waypoints={waypts}&travelmode=driving"
                else:
                    g_maps_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}&travelmode=driving"
                
                st.link_button(f"OPEN ROUTE IN GOOGLE MAPS", g_maps_url)
                
                for step, s_name in enumerate(stops):
                    label = "START" if step == 0 else f"STOP {step}"
                    st.text(f"{label}: {s_name}")
else:
    st.info("Systeem gereed. Configureer fleet-instellingen en start optimalisatie.")
