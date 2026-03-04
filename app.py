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

st.set_page_config(page_title="LogiPlan Enterprise | Fleet Management", layout="wide")

# High-End Corporate Styling
st.markdown("""
    <style>
    .stApp { background-color: #fcfcfc; }
    div[data-testid="stMetricValue"] { font-size: 24px; color: #1e3a8a; font-weight: 700; }
    .stMetric { border: 1px solid #e5e7eb; padding: 15px; background: #ffffff; }
    .stButton>button { background-color: #0f172a; color: white; height: 3.5rem; border-radius: 4px; border: none; font-size: 16px; transition: 0.3s; }
    .stButton>button:hover { background-color: #334155; border: none; }
    .section-header { border-bottom: 2px solid #1e3a8a; padding-bottom: 5px; margin-bottom: 20px; color: #1e3a8a; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

if 'fleet_results' not in st.session_state:
    st.session_state.fleet_results = None

st.title("LogiPlan Enterprise")
st.caption("Fleet Optimization Engine v2.1 | Powered by ORS Business")

# --- SIDEBAR: CONTROLS ---
st.sidebar.header("Fleet Configuration")
num_vehicles = st.sidebar.number_input("Beschikbare Voertuigen", min_value=1, max_value=15, value=2)
max_capacity = st.sidebar.number_input("Maximale Stops per Voertuig", min_value=1, max_value=50, value=15)

st.sidebar.markdown("---")
input_method = st.sidebar.selectbox("Gegevensbron", ["Excel/CSV Upload", "Handmatige Invoer"])

adressen = []
if input_method == "Handmatige Invoer":
    input_text = st.sidebar.text_area("Adressenlijst (Eerste regel is Magazijn):", height=200)
    adressen = [a.strip() for a in input_text.split('\n') if a.strip()]
else:
    uploaded_file = st.sidebar.file_uploader("Upload Fleet Data", type=["xlsx", "csv"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
        adressen = df.iloc[:, 0].dropna().tolist()

# --- OPTIMIZATION ENGINE ---
if st.sidebar.button("OPTIMALISEER VLOOT"):
    if len(adressen) > 1:
        with st.status("Verwerken van logistieke data...", expanded=True) as status:
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

            st.write(f"✓ {len(valid_addr)} locaties gevalideerd.")
            
            if len(coords) > 1:
                ors_coords = [[c[1], c[0]] for c in coords]
                matrix = client.distance_matrix(locations=ors_coords, profile='driving-car', metrics=['distance'])
                dist_matrix = matrix['distances']

                num_loc = len(coords)
                manager = pywrapcp.RoutingIndexManager(num_loc, num_vehicles, 0)
                routing = pywrapcp.RoutingModel(manager)
                
                def d_cb(f, t): return int(dist_matrix[manager.IndexToNode(f)][manager.IndexToNode(t)])
                transit_callback_index = routing.RegisterTransitCallback(d_cb)
                routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
                
                def demand_callback(from_index): return 1
                demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
                routing.AddDimension(demand_callback_index, 0, max_capacity, True, 'Capacity')

                search_params = pywrapcp.DefaultRoutingSearchParameters()
                search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
                solution = routing.SolveWithParameters(search_params)

                if solution:
                    fleet_data = []
                    total_dist = 0
                    for vehicle_id in range(num_vehicles):
                        index = routing.Start(vehicle_id)
                        route = []
                        route_dist = 0
                        while not routing.IsEnd(index):
                            previous_index = index
                            node_idx = manager.IndexToNode(index)
                            route.append(node_idx)
                            index = solution.Value(routing.NextVar(index))
                            route_dist += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
                        
                        if len(route) > 1:
                            fleet_data.append({'vehicle': vehicle_id + 1, 'path': route, 'distance': route_dist / 1000})
                            total_dist += route_dist / 1000
                    
                    st.session_state.fleet_results = {
                        'fleet': fleet_data,
                        'total_distance': total_dist,
                        'coords': coords,
                        'addr': valid_addr
                    }
                    status.update(label="Optimalisatie Voltooid", state="complete", expanded=False)

# --- BUSINESS DASHBOARD ---
if st.session_state.fleet_results:
    res = st.session_state.fleet_results
    
    # Financial Impact Metrics
    c_m1, c_m2, c_m3, c_m4 = st.columns(4)
    c_m1.metric("Totale Afstand", f"{round(res['total_distance'], 1)} KM")
    c_m2.metric("Voertuigen", len(res['fleet']))
    # Business Case: Gemiddelde besparing simulatie (15% van 1.50 euro per km)
    savings = res['total_distance'] * 0.15 * 1.50
    c_m3.metric("Geschatte Besparing", f"€ {round(savings, 2)}")
    c_m4.metric("CO2 Reductie", f"{round(res['total_distance'] * 0.12, 1)} KG")

    st.markdown("<div class='section-header'>OPERATIONEEL OVERZICHT</div>", unsafe_allow_html=True)
    
    col_map, col_list = st.columns([2, 1])
    
    with col_map:
        m = folium.Map(location=res['coords'][0], zoom_start=10, tiles='cartodbpositron')
        colors = ['#1e40af', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']
        
        for i, vehicle in enumerate(res['fleet']):
            v_color = colors[i % len(colors)]
            v_coords = [res['coords'][idx] for idx in vehicle['path']]
            folium.PolyLine(v_coords, color=v_color, weight=5, opacity=0.7).add_to(m)
            for stop_idx in vehicle['path']:
                folium.CircleMarker(res['coords'][stop_idx], radius=6, color=v_color, fill=True, fill_opacity=1).add_to(m)
        
        st_folium(m, width=900, height=550, key="enterprise_map_final")

    with col_list:
        st.write("### Route Details")
        for vehicle in res['fleet']:
            with st.expander(f"VOERTUIG {vehicle['vehicle']} ({round(vehicle['distance'], 1)} km)"):
                stops = [res['addr'][i] for i in vehicle['path']]
                
                # Geoptimaliseerde Multi-Stop Link
                origin = stops[0].replace(' ', '+')
                dest = stops[-1].replace(' ', '+')
                waypts = "|".join([s.replace(' ', '+') for s in stops[1:-1]])
                g_maps_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}&waypoints={waypts}&travelmode=driving"
                
                st.link_button("OPEN IN NAVIGATIE", g_maps_url)
                
                # Tabel weergave voor professionele lijst
                df_stops = pd.DataFrame({"Volgorde": range(len(stops)), "Locatie": stops})
                st.table(df_stops)

else:
    st.info("Systeem gereed voor analyse. Configureer uw fleet-data in het linkerpaneel.")
