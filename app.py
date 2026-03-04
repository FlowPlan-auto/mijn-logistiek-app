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

st.set_page_config(page_title="LogiPlan | Fleet Control Center", layout="wide", initial_sidebar_state="collapsed")

# Geavanceerde CSS voor Custom WebApp Layout (Verbergt Sidebar & Styling)
st.markdown("""
    <style>
    /* Verberg de standaard Streamlit sidebar volledig */
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stSidebarNav"] { display: none; }
    
    /* Hoofdpagina styling */
    .main { background-color: #ffffff; padding-top: 0px; }
    .block-container { padding-top: 1rem; max-width: 95%; }
    
    /* Enterprise Header */
    .nav-bar {
        background-color: #0f172a;
        padding: 1.5rem;
        border-radius: 8px;
        color: white;
        margin-bottom: 2rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    /* Kaart & Kaarten styling */
    .stMetric { border: 1px solid #e2e8f0; padding: 20px; border-radius: 8px; background: #f8fafc; }
    .stButton>button { 
        background-color: #2563eb; 
        color: white; 
        border-radius: 6px; 
        border: none; 
        font-weight: 600;
        padding: 0.75rem 2rem;
        margin-top: 10px;
    }
    .stButton>button:hover { background-color: #1d4ed8; }
    
    /* Input Sectie */
    .config-box {
        background-color: #f1f5f9;
        padding: 2rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        border: 1px solid #e2e8f0;
    }
    </style>
    
    <div class="nav-bar">
        <div style="font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">LOGIPLAN <span style="font-weight: 300; color: #94a3b8;">| ENTERPRISE</span></div>
        <div style="font-size: 14px; color: #94a3b8;">Fleet Management System v2.5</div>
    </div>
    """, unsafe_allow_html=True)

if 'fleet_results' not in st.session_state:
    st.session_state.fleet_results = None

# --- HOOFD INPUT SECTIE (In plaats van Sidebar) ---
st.markdown("### 1. Planning Configuratie")
with st.container():
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        num_vehicles = st.number_input("Voertuigen", min_value=1, max_value=15, value=2)
    with col2:
        max_capacity = st.number_input("Max stops p/v", min_value=1, max_value=50, value=15)
    with col3:
        input_method = st.selectbox("Data Source", ["Excel/CSV Upload", "Manual Entry"])

    col_data, col_btn = st.columns([3, 1])
    with col_data:
        if input_method == "Manual Entry":
            adressen_input = st.text_area("Adressen (Eerste regel = Depot)", height=100, placeholder="Adres 1\nAdres 2...")
            adressen = [a.strip() for a in adressen_input.split('\n') if a.strip()]
        else:
            uploaded_file = st.file_uploader("Sleep bestanden hierheen", type=["xlsx", "csv"])
            if uploaded_file:
                df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
                adressen = df.iloc[:, 0].dropna().tolist()
            else:
                adressen = []
    
    with col_btn:
        st.write("") # Spacing
        st.write("")
        run_btn = st.button("RUN OPTIMIZATION ENGINE")

# --- ENGINE LOGICA ---
if run_btn:
    if len(adressen) > 1:
        with st.status("Logistieke data analyseren...", expanded=False) as status:
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
                        route, route_dist = [], 0
                        while not routing.IsEnd(index):
                            previous_index = index
                            route.append(manager.IndexToNode(index))
                            index = solution.Value(routing.NextVar(index))
                            route_dist += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
                        if len(route) > 1:
                            fleet_data.append({'vehicle': vehicle_id + 1, 'path': route, 'distance': route_dist / 1000})
                            total_dist += route_dist / 1000
                    
                    st.session_state.fleet_results = {'fleet': fleet_data, 'total_distance': total_dist, 'coords': coords, 'addr': valid_addr}
                    status.update(label="Analyse Voltooid", state="complete")

# --- DASHBOARD OUTPUT (ZOALS HET WAS) ---
if st.session_state.fleet_results:
    res = st.session_state.fleet_results
    st.markdown("### 2. Operational Intelligence")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Totale Afstand", f"{round(res['total_distance'], 1)} KM")
    m2.metric("Vloot Bezetting", f"{len(res['fleet'])} Units")
    m3.metric("Besparing (Projectie)", f"€ {round(res['total_distance'] * 0.15 * 1.50, 2)}")
    m4.metric("CO2 Impact", f"-{round(res['total_distance'] * 0.12, 1)} KG")

    col_map, col_details = st.columns([2, 1])
    
    with col_map:
        m = folium.Map(location=res['coords'][0], zoom_start=10, tiles='cartodbpositron')
        colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']
        for i, v in enumerate(res['fleet']):
            v_color = colors[i % len(colors)]
            pts = [res['coords'][idx] for idx in v['path']]
            folium.PolyLine(pts, color=v_color, weight=4).add_to(m)
            for s_idx in v['path']:
                folium.CircleMarker(res['coords'][s_idx], radius=5, color=v_color, fill=True).add_to(m)
        st_folium(m, width=1000, height=500, key="main_dispatch_map")

    with col_details:
        st.write("#### Fleet Dispatch List")
        for v in res['fleet']:
            with st.expander(f"UNIT {v['vehicle']} - {round(v['distance'],1)} KM"):
                v_addr = [res['addr'][i] for i in v['path']]
                # Google Maps link
                origin, dest = v_addr[0].replace(' ', '+'), v_addr[-1].replace(' ', '+')
                waypts = "|".join([s.replace(' ', '+') for s in v_addr[1:-1]])
                url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}&waypoints={waypts}&travelmode=driving"
                st.link_button("OPEN GPS ROUTE", url)
                st.table(pd.DataFrame({"Stop": range(len(v_addr)), "Location": v_addr}))
