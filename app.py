import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import openrouteservice
from ortools.constraint_solver import routing_enums_pb2, pywrapcp
import time
import hashlib

# --- ENTERPRISE CONFIGURATIE ---
ORS_API_KEY = 'eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjlhZTJlMzRmYTg5MDRmMDk5MGU4NGIyNjgyMTZjMTNlIiwiaCI6Im11cm11cjY0In0='
client = openrouteservice.Client(key=ORS_API_KEY)

st.set_page_config(page_title="LogiPlan | Enterprise Control", layout="wide", initial_sidebar_state="collapsed")

# --- AUTHENTICATIE LOGICA ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

if 'user_db' not in st.session_state:
    st.session_state.user_db = {"admin": make_hashes("demo2024")} 
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'fleet_results' not in st.session_state:
    st.session_state.fleet_results = None
# Nieuwe state om de lijst met voertuigen te onthouden
if 'vehicles_list' not in st.session_state:
    st.session_state.vehicles_list = [{"name": "Bus 1", "capacity": 15}]

# --- CUSTOM CSS ---
st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none; }
    .main { background-color: #f8fafc; }
    .nav-bar {
        background-color: #0f172a; padding: 1.5rem; border-radius: 8px;
        color: white; margin-bottom: 1.5rem; display: flex;
        justify-content: space-between; align-items: center;
    }
    .stMetric { border: 1px solid #e2e8f0; padding: 15px; border-radius: 8px; background: #ffffff; }
    .stButton>button { 
        background-color: #2563eb; color: white; border-radius: 4px; 
        font-weight: 600; height: 3rem; width: 100%; border: none;
    }
    .login-box {
        background-color: white; padding: 40px; border-radius: 12px;
        border: 1px solid #e2e8f0; max-width: 450px; margin: 50px auto;
    }
    </style>
    """, unsafe_allow_html=True)

# --- INLOGSCHERM ---
if not st.session_state.logged_in:
    st.markdown("<div style='text-align: center; margin-top: 50px;'>", unsafe_allow_html=True)
    st.title("LogiPlan Enterprise")
    tab_login, tab_signup = st.tabs(["Inloggen", "Account Aanmaken"])
    with tab_login:
        st.markdown("<div class='login-box'>", unsafe_allow_html=True)
        u = st.text_input("Gebruikersnaam")
        p = st.text_input("Wachtwoord", type='password')
        if st.button("Toegang Verlenen"):
            if u in st.session_state.user_db and check_hashes(p, st.session_state.user_db[u]):
                st.session_state.logged_in = True
                st.rerun()
            else: st.error("Ongeldige inloggegevens.")
        st.markdown("</div>", unsafe_allow_html=True)
    with tab_signup:
        st.markdown("<div class='login-box'>", unsafe_allow_html=True)
        new_u = st.text_input("Nieuwe Gebruikersnaam")
        new_p = st.text_input("Nieuw Wachtwoord", type='password')
        conf_p = st.text_input("Bevestig Wachtwoord", type='password')
        if st.button("Account Registreren"):
            if new_p == conf_p and new_u:
                st.session_state.user_db[new_u] = make_hashes(new_p)
                st.success("Account aangemaakt!")
            else: st.error("Check gegevens.")
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

else:
    st.markdown(f"""
        <div class="nav-bar">
            <div style="font-size: 24px; font-weight: 800;">LOGIPLAN <span style="font-weight: 300; color: #94a3b8;">| ENTERPRISE CONTROL</span></div>
            <div style="font-size: 14px; background: #1e293b; padding: 5px 15px; border-radius: 20px;">Sessie Actief</div>
        </div>
        """, unsafe_allow_html=True)
    
    if st.button("Uitloggen", use_container_width=False):
        st.session_state.logged_in = False
        st.rerun()

    st.markdown("### 1. Vloot & Parameters")
    
    # --- VOERTUIG CONFIGURATIE SECTIE ---
    col_v1, col_v2 = st.columns([2, 1])
    
    with col_v1:
        st.write("**Voertuigen Beheren**")
        for i, veh in enumerate(st.session_state.vehicles_list):
            c_name, c_cap, c_del = st.columns([2, 2, 1])
            veh['name'] = c_name.text_input(f"Naam Voertuig {i+1}", value=veh['name'], key=f"name_{i}")
            veh['capacity'] = c_cap.number_input(f"Max Stops", min_value=1, value=veh['capacity'], key=f"cap_{i}")
            if c_del.button("❌", key=f"del_{i}"):
                st.session_state.vehicles_list.pop(i)
                st.rerun()
        
        if st.button("➕ Voertuig Toevoegen"):
            st.session_state.vehicles_list.append({"name": f"Bus {len(st.session_state.vehicles_list)+1}", "capacity": 15})
            st.rerun()

    with col_v2:
        st.write("**Financieel**")
        cost_per_km = st.number_input("Kosten p/km (€)", value=1.50, step=0.05)
        est_efficiency = st.slider("Huidige Inefficiëntie (%)", 5, 40, 15)

    st.markdown("---")
    
    # --- INPUT SECTIE ---
    col_input, col_action = st.columns([3, 1])
    with col_input:
        input_method = st.radio("Bronbestand", ["Excel Upload", "Handmatige Invoer"], horizontal=True)
        if input_method == "Handmatige Invoer":
            txt = st.text_area("Adressen (Regel 1 = Depot)", height=70)
            adressen = [a.strip() for a in txt.split('\n') if a.strip()]
        else:
            up = st.file_uploader("Drop fleet manifest", type=["xlsx", "csv"])
            if up:
                df = pd.read_excel(up) if up.name.endswith('xlsx') else pd.read_csv(up)
                adressen = df.iloc[:, 0].dropna().tolist()
            else: adressen = []

    with col_action:
        st.write("")
        st.write("")
        if st.button("RUN OPTIMIZATION ENGINE"):
            if len(adressen) > 1 and len(st.session_state.vehicles_list) > 0:
                with st.status("Engine berekent routes...", expanded=False) as status:
                    coords, valid_addr = [], []
                    for a in adressen:
                        try:
                            res = client.pelias_search(text=a, size=1)
                            if res['features']:
                                lon, lat = res['features'][0]['geometry']['coordinates']
                                coords.append([lat, lon]); valid_addr.append(a)
                            time.sleep(0.05)
                        except: continue

                    if len(coords) > 1:
                        ors_coords = [[c[1], c[0]] for c in coords]
                        matrix = client.distance_matrix(locations=ors_coords, profile='driving-car', metrics=['distance'])
                        dist_matrix = matrix['distances']
                        
                        num_vehicles = len(st.session_state.vehicles_list)
                        manager = pywrapcp.RoutingIndexManager(len(coords), num_vehicles, 0)
                        routing = pywrapcp.RoutingModel(manager)
                        
                        def d_cb(f, t): return int(dist_matrix[manager.IndexToNode(f)][manager.IndexToNode(t)])
                        transit_callback_index = routing.RegisterTransitCallback(d_cb)
                        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
                        
                        # SPECIFIEKE CAPACITEIT PER VOERTUIG
                        capacities = [v['capacity'] for v in st.session_state.vehicles_list]
                        routing.AddDimensionWithVehicleCapacity(
                            routing.RegisterUnaryTransitCallback(lambda x: 1),
                            0, capacities, True, 'Capacity'
                        )
                        
                        search_params = pywrapcp.DefaultRoutingSearchParameters()
                        search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
                        solution = routing.SolveWithParameters(search_params)

                        if solution:
                            fleet_data, total_dist = [], 0
                            for v_id in range(num_vehicles):
                                index = routing.Start(v_id)
                                route, route_dist = [], 0
                                while not routing.IsEnd(index):
                                    prev = index
                                    route.append(manager.IndexToNode(index))
                                    index = solution.Value(routing.NextVar(index))
                                    route_dist += routing.GetArcCostForVehicle(prev, index, v_id)
                                if len(route) > 1:
                                    # Gebruik de eigen naam van het voertuig
                                    v_name = st.session_state.vehicles_list[v_id]['name']
                                    fleet_data.append({'vehicle': v_name, 'path': route, 'distance': route_dist / 1000})
                                    total_dist += route_dist / 1000
                            st.session_state.fleet_results = {'fleet': fleet_data, 'total_distance': total_dist, 'coords': coords, 'addr': valid_addr, 'cost': cost_per_km, 'eff': est_efficiency}
                            status.update(label="Analyse Succesvol", state="complete")

    # --- OUTPUT SECTIE ---
    if st.session_state.fleet_results:
        res = st.session_state.fleet_results
        st.markdown("### 2. Operational & Financial Impact")
        savings = (res['total_distance'] * (res['eff']/100)) * res['cost']
        co2 = (res['total_distance'] * (res['eff']/100)) * 0.12

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Gereden Afstand", f"{round(res['total_distance'], 1)} KM")
        m2.metric("Inzet Vloot", f"{len(res['fleet'])} Voertuigen")
        m3.metric("Besparing p/Rit", f"€ {round(savings, 2)}", f"{res['eff']}% winst")
        m4.metric("CO2 Reductie", f"{round(co2, 1)} KG")

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
            st_folium(m, width=900, height=550, key="enterprise_map")

        with col_details:
            st.write("#### Dispatch Manifest")
            for v in res['fleet']:
                with st.expander(f"🚛 {v['vehicle']} - {round(v['distance'], 1)} KM"):
                    v_addr = [res['addr'][i] for i in v['path']]
                    st.write(f"**Navigatie Links:**")
                    MAX_STOPS = 10
                    for i in range(0, len(v_addr) - 1, MAX_STOPS - 1):
                        segment = v_addr[i:i + MAX_STOPS]
                        if len(segment) > 1:
                            origin = segment[0].replace(' ', '+')
                            dest = segment[-1].replace(' ', '+')
                            waypts = "|".join([s.replace(' ', '+') for s in segment[1:-1]])
                            url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={dest}&waypoints={waypts}&travelmode=driving"
                            deel_nr = (i // (MAX_STOPS - 1)) + 1
                            st.link_button(f"🧭 {v['vehicle']} Deel {deel_nr}", url)
                    st.dataframe(pd.DataFrame({"Stop": range(len(v_addr)), "Adres": v_addr}), hide_index=True)
