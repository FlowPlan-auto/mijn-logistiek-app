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

# Geavanceerde CSS voor Enterprise Look
st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none; }
    .main { background-color: #ffffff; }
    .block-container { padding-top: 1rem; max-width: 95%; }
    .nav-bar {
        background-color: #0f172a;
        padding: 1.5rem;
        border-radius: 8px;
        color: white;
        margin-bottom: 1.5rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .stMetric { border: 1px solid #e2e8f0; padding: 15px; border-radius: 8px; background: #f8fafc; }
    .stButton>button { 
        background-color: #2563eb; 
        color: white; 
        border-radius: 4px; 
        font-weight: 600;
        height: 3rem;
        width: 100%;
    }
    .config-card {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        padding: 20px;
        border-radius: 8px;
        margin-bottom: 20px;
    }
    </style>
    
    <div class="nav-bar">
        <div style="font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">LOGIPLAN <span style="font-weight: 300; color: #94a3b8;">| ENTERPRISE CONTROL</span></div>
        <div style="font-size: 14px; color: #94a3b8;">v2.6 Commercial Edition</div>
    </div>
    """, unsafe_allow_html=True)

if 'fleet_results' not in st.session_state:
    st.session_state.fleet_results = None

# --- STAP 1: CONFIGURATIE GRID ---
st.markdown("### 1. Operationele & Financiële Parameters")
with st.container():
    # We verdelen de invoer in Fleet, Capaciteit en Kosten
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1:
        num_vehicles = st.number_input("Aantal Voertuigen", min_value=1, max_value=20, value=2)
    with c2:
        max_capacity = st.number_input("Max Stops p/v", min_value=1, max_value=100, value=15)
    with c3:
        cost_per_km = st.number_input("Kosten p/km (€)", min_value=0.10, max_value=5.00, value=1.50, step=0.05, help="Inclusief brandstof, chauffeur en onderhoud.")
    with c4:
        est_efficiency = st.slider("Huidige Inefficiëntie (%)", 5, 40, 15, help="Hoeveel % rijdt de vloot momenteel 'om' zonder software?")

    # Data Source & Actie
    col_input, col_action = st.columns([3, 1])
    with col_input:
        input_method = st.radio("Invoermethode", ["Excel Upload", "Handmatige Lijst"], horizontal=True)
        if input_method == "Handmatige Lijst":
            adressen_input = st.text_area("Adressen (Eerste regel = Depot)", height=70, placeholder="Seattleweg 7, Rotterdam\n...")
            adressen = [a.strip() for a in adressen_input.split('\n') if a.strip()]
        else:
            uploaded_file = st.file_uploader("Upload Fleet Manifest", type=["xlsx", "csv"])
            if uploaded_file:
                df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('xlsx') else pd.read_csv(uploaded_file)
                adressen = df.iloc[:, 0].dropna().tolist()
            else:
                adressen = []

    with col_action:
        st.write("") # Padding
        st.write("")
        run_btn = st.button("START ROUTE OPTIMALISATIE")

# --- OPTIMALISATIE ENGINE ---
if run_btn and len(adressen) > 1:
    with st.status("Engine berekent meest efficiënte vloot-verdeling...", expanded=False) as status:
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
            routing.SetArcCostEvaluatorOfAllVehicles(routing.RegisterTransitCallback(d_cb))
            
            def demand_callback(from_index): return 1
            routing.AddDimension(routing.RegisterUnaryTransitCallback(demand_callback), 0, max_capacity, True, 'Capacity')

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
                
                st.session_state.fleet_results = {
                    'fleet': fleet_data, 
                    'total_distance': total_dist, 
                    'coords': coords, 
                    'addr': valid_addr,
                    'cost_km': cost_per_km,
                    'efficiency': est_efficiency
                }
                status.update(label="Analyse Succesvol", state="complete")

# --- STAP 2: DASHBOARD ---
if st.session_state.fleet_results:
    res = st.session_state.fleet_results
    st.markdown("### 2. Financiële & Operationele Impact")
    
    # Berekening Business Case
    total_km = res['total_distance']
    # Besparing = (Afstand / (1 - inefficiëntie)) - Afstand * kosten
    # Simpeler: we rekenen de besparing op de huidige kms
    savings_euro = (total_km * (res['efficiency']/100)) * res['cost_km']
    co2_saved = (total_km * (res['efficiency']/100)) * 0.12 # 120g per km bespaard

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Totale Vloot Afstand", f"{round(total_km, 1)} KM")
    m2.metric("Ingezette Units", f"{len(res['fleet'])}")
    m3.metric("Besparing per Rit", f"€ {round(savings_euro, 2)}", f"{res['efficiency']}% winst")
    m4.metric("CO2 Reductie", f"{round(co2_saved, 1)} KG", "Milieu-impact")

    st.markdown("---")
    
    col_map, col_details = st.columns([2, 1])
    
    with col_map:
        m = folium.Map(location=res['coords'][0], zoom_start=11, tiles='cartodbpositron')
        colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6']
        for i, v in enumerate(res['fleet']):
            v_color = colors[i % len(colors)]
            pts = [res['coords'][idx] for idx in v['path']]
            folium.PolyLine(pts, color=v_color, weight=5, opacity=0.8).add_to(m)
            for s_idx in v['path']:
                folium.CircleMarker(res['coords'][s_idx], radius=6, color=v_color, fill=True).add_to(m)
        st_folium(m, width=1000, height=550, key="enterprise_map_v26")

    with col_details:
        st.write("#### Fleet Dispatch Manifest")
        for v in res['fleet']:
            with st.expander(f"UNIT {v['vehicle']} - {round(v['distance'], 1)} KM"):
                v_addr = [res['addr'][i] for i in v['path']]
                # Google Maps Multi-stop
                origin, dest = v_addr[0].replace(' ', '+'), v_addr[-1].replace(' ', '+')
                waypts = "|".join([s.replace(' ', '+') for s in v_addr[1:-1]])
                url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}&waypoints={waypts}&travelmode=driving"
                
                st.link_button(f"STUUR ROUTE NAAR UNIT {v['vehicle']}", url)
                st.dataframe(pd.DataFrame({"Stop": range(len(v_addr)), "Adres": v_addr}), use_container_width=True, hide_index=True)
