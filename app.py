import pandas as pd
import streamlit as st
import json
import os
import collections
import urllib.parse
import altair as alt

st.set_page_config(page_title="Upper Lusatia F1 Fans League Statistics", layout="centered", page_icon="🏎️")
st.title("🏎️ F1 Fantasy Analytics")

history_file = 'data/liga_history.csv'
legacy_seasons = 'data/legacy_seasons.csv'

if not os.path.exists(history_file):
    st.warning("Noch keine vollständigen Daten vorhanden. Bitte führe update_data.py aus.")
    st.stop()

# --- DATEN LADEN ---
df_history = pd.read_csv(history_file)
df_legacy = pd.read_csv(legacy_seasons)

rennen_liste = df_history['Rennen'].unique()
letztes_rennen = rennen_liste[-1]

# --- FARBEN FESTLEGEN (Für kongruente Diagramme) ---
alle_manager = df_history['Manager'].unique().tolist()
farben_palette = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
                  '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
manager_farben = alt.Scale(domain=alle_manager, range=farben_palette[:len(alle_manager)])

# --- PUNKTE & SCORES BERECHNEN ---
df_history['Punkte_vorher'] = df_history.groupby('Manager')['Punkte'].shift(1).fillna(0)
df_history['Renn_Score'] = df_history['Punkte'] - df_history['Punkte_vorher']
df_history.loc[df_history['Rennen'] == rennen_liste[0], 'Renn_Score'] = df_history['Punkte']

df_aktuell = df_history[df_history['Rennen'] == letztes_rennen].copy()

# --- ABSTÄNDE & TRENDS BERECHNEN ---
df_aktuell = df_aktuell.sort_values('Punkte', ascending=False).reset_index(drop=True)
max_punkte = df_aktuell['Punkte'].max()

df_aktuell['Gap_P1'] = max_punkte - df_aktuell['Punkte']
df_aktuell['Gap_next_Manager'] = df_aktuell['Punkte'].shift(1) - df_aktuell['Punkte']
df_aktuell['Gap_next_Manager'] = df_aktuell['Gap_next_Manager'].fillna(0)

# Gap Trend ermitteln
if len(rennen_liste) > 1:
    vorletztes_rennen = rennen_liste[-2]
    df_vorher = df_history[df_history['Rennen'] == vorletztes_rennen].copy()
else:
    # Fallback, falls erst ein einziges Rennen in der Saison gefahren wurde
    df_vorher = df_aktuell.copy()
    df_vorher['Punkte'] = 0
    
df_vorher_sort = df_vorher.sort_values('Punkte', ascending=False).reset_index(drop=True)
max_punkte_vorher = df_vorher_sort['Punkte'].max()
df_vorher_sort['Gap_P1_alt'] = max_punkte_vorher - df_vorher_sort['Punkte']

df_aktuell = df_aktuell.merge(df_vorher_sort[['Manager', 'Gap_P1_alt']], on='Manager', how='left')
df_aktuell['Aufgeholt_auf_P1'] = df_aktuell['Gap_P1_alt'] - df_aktuell['Gap_P1']

def format_gap_trend(val):
    if pd.isna(val) or val == 0:
        return "➖"
    elif val > 0:
        return f"🔥 +{val:.1f}"
    else:
        return f"📉 {val:.1f}"

df_aktuell['Gap Trend (P1)'] = df_aktuell['Aufgeholt_auf_P1'].apply(format_gap_trend)

# Sparkline-Daten
# --- Form-Daten (Letzte 3 Rennen) ---
# Durchschnittlichen Renn-Score pro Rennen berechnen
df_history['Schnitt_Renn_Score'] = df_history.groupby('Rennen')['Renn_Score'].transform('mean')

# Pfeil-Logik anwenden
def get_form_symbol(row):
    if row['Renn_Score'] > row['Schnitt_Renn_Score']:
        return "⬆️"
    elif row['Renn_Score'] < row['Schnitt_Renn_Score']:
        return "⬇️"
    else:
        return "➡️"

df_history['Form_Symbol'] = df_history.apply(get_form_symbol, axis=1)

# Letzte 3 Symbole pro Manager zu einem Text verbinden (z.B. "⬆️⬇️⬆️")
trend_data = df_history.groupby('Manager').tail(3).groupby('Manager')['Form_Symbol'].apply(lambda x: "".join(x)).reset_index(name='Form (Letzte 3)')
df_aktuell = df_aktuell.merge(trend_data, on='Manager', how='left')

# --- EWIGE TABELLE BERECHNEN ---
if 'Manager' in df_legacy.columns and 'Platz' in df_legacy.columns:
    punkte_dict = {1: 50, 2: 30, 3: 20}
    df_ewig = df_legacy.copy()
    df_ewig['Platz'] = pd.to_numeric(df_ewig['Platz'], errors='coerce')
    df_ewig['Historische Punkte'] = df_ewig['Platz'].map(punkte_dict).fillna(0)
    df_permanent = df_ewig.groupby('Manager').agg(
        Punkte=('Historische Punkte', 'sum'),
        Meisterschaften=('Platz', lambda x: (x == 1).sum()),
        Podien=('Platz', lambda x: (x <= 3).sum())
    ).reset_index().sort_values('Punkte', ascending=False)
else:
    records = []
    for col in df_legacy.columns:
        col_str = str(col).lower()
        if '1' in col_str:
            pts = 50
        elif '2' in col_str:
            pts = 30
        elif '3' in col_str:
            pts = 20
        else:
            continue
            
        for manager in df_legacy[col].dropna():
            manager_str = str(manager).strip()
            if manager_str:
                records.append({'Manager': manager_str, 'Punkte': pts, 'Meisterschaften': 1 if pts==50 else 0, 'Podien': 1})
                
    if records:
        # Zukunftssicherer gemacht: numeric_only=True hinzugefügt
        df_permanent = pd.DataFrame(records).groupby('Manager').sum(numeric_only=True).reset_index().sort_values('Punkte', ascending=False)
    else:
        df_permanent = pd.DataFrame(columns=['Manager', 'Punkte', 'Meisterschaften', 'Podien'])

# Platzierung vergeben (mit Berücksichtigung von Gleichstand) und Emojis hinzufügen
def get_medal(rank):
    if rank == 1:
        return "🥇 1"
    elif rank == 2:
        return "🥈 2"
    elif rank == 3:
        return "🥉 3"
    else:
        return str(rank)

if not df_permanent.empty:
    df_permanent['Platz_Num'] = df_permanent['Punkte'].rank(method='min', ascending=False).astype(int)
    df_permanent['Platz'] = df_permanent['Platz_Num'].apply(get_medal)
    df_permanent = df_permanent[['Platz', 'Manager', 'Punkte', 'Meisterschaften', 'Podien']]
else:
    df_permanent['Platz'] = []

# ==========================================
# TABS AUFBAUEN
# ==========================================
tab1, tab2, tab3, tab4 = st.tabs(["📊 aktueller Stand", "📈 Saison-Verlauf", "🤓 Team-Statistiken", "🏆 ewige Tabelle"])

with tab1:
    st.subheader(f"Gesamtstand nach Rennen {letztes_rennen}")
    
    anzeige_spalten = ['Rang', 'Manager', 'Punkte', 'Gap_P1', 'Gap Trend (P1)', 'Gap_next_Manager', 'Form (Letzte 3)']
    df_anzeige = df_aktuell[anzeige_spalten].copy()
    
    st.dataframe(
        df_anzeige,
        column_config={
            "Rang": st.column_config.NumberColumn("Rang"),
            "Punkte": st.column_config.NumberColumn("Punkte", format="%.1f"),
            "Gap_P1": st.column_config.NumberColumn("Abstand P1", format="-%.1f"),
            "Gap_next_Manager": st.column_config.NumberColumn("Rückstand nächstbester Platz", format="-%.1f"),
            "Form (Letzte 3)": st.column_config.TextColumn(
                "Form (Letzte 3 Rennen)", 
                help="⬆️ Punkte über Liga-Durchschnitt\n⬇️ Punkte unter Liga-Durchschnitt"
            )
        },
        use_container_width=True,
        hide_index=True
    )

with tab2:
    st.subheader("Punkteentwicklung")
    st.markdown("Zeigt den Abstand zum Durchschnitt. Die Nulllinie ist der exakte Liga-Durchschnitt.")
    df_history['Schnitt'] = df_history.groupby('Rennen')['Punkte'].transform('mean')
    df_history['Delta_Schnitt'] = df_history['Punkte'] - df_history['Schnitt']
    
    chart_delta = alt.Chart(df_history).mark_line(
        point=alt.OverlayMarkDef(size=80, filled=True),
        strokeWidth=3
    ).encode(
        x=alt.X('Rennen:O', title='Rennen', sort=None, scale=alt.Scale(padding=0)),
        y=alt.Y('Delta_Schnitt:Q', title='Abstand zum Schnitt'),
        color=alt.Color('Manager:N', scale=manager_farben, legend=alt.Legend(title="Manager", orient='top')),
        tooltip=['Manager', 'Rennen', 'Punkte', 'Delta_Schnitt']
    ).properties(height=550).interactive()
    
    st.altair_chart(chart_delta, use_container_width=True)
    st.markdown("---")

    st.subheader("Entwicklung der Platzierung")
    st.markdown("Platzierungsverlauf über die Saison hinweg")
    
    max_rang = int(df_history['Rang'].max())
    chart_rang = alt.Chart(df_history).mark_line(
        point=alt.OverlayMarkDef(size=80, filled=True),
        strokeWidth=3
    ).encode(
        x=alt.X('Rennen:O', title='Rennen', sort=None, scale=alt.Scale(padding=0)),
        y=alt.Y('Rang:Q', title='Tabellenplatz', scale=alt.Scale(reverse=True, domain=[1, max_rang]), axis=alt.Axis(tickMinStep=1, format='d')),
        color=alt.Color('Manager:N', scale=manager_farben, legend=None),
        tooltip=['Manager', 'Rennen', 'Rang']
    ).properties(height=550).interactive()
    
    st.altair_chart(chart_rang, use_container_width=True)

    st.subheader("Rennsiege (Highest Score)")
    max_scores_per_race = df_history.groupby('Rennen')['Renn_Score'].transform('max')
    winners_df = df_history[df_history['Renn_Score'] == max_scores_per_race]
    
    winner_counts = winners_df['Manager'].value_counts().reset_index()
    winner_counts.columns = ['Manager', 'Tagessiege']
    
    chart_wins = alt.Chart(winner_counts).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
        x=alt.X('Manager:N', sort='-y', title='Manager', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('Tagessiege:Q', title='Anzahl Tagessiege', axis=alt.Axis(tickMinStep=1, format='d')),
        color=alt.Color('Manager:N', scale=manager_farben, legend=None),
        tooltip=['Manager', 'Tagessiege']
    ).properties(height=400)
    
    st.altair_chart(chart_wins, use_container_width=True)
    st.markdown("---")

with tab3:
    with open('data/list_1_726403_0_1.json', 'r') as f:
        liga_data = json.load(f)
    with open('data/driverconstructors_4.json', 'r') as f:
        stats_data = json.load(f)

    dnf_katalog = {}
    name_katalog = {}
    for cat in stats_data['Data']['driver'] + stats_data['Data']['constructor']:
        if cat['config']['key'] == 'fPoints':
            for p in cat['participants']:
                name_katalog[p['playerid']] = p.get('playername') or p.get('teamname')
        if cat['config']['key'] == 'mostDnf':
            for p in cat['participants']:
                dnf_katalog[p['playerid']] = p.get('statvalue', 0.0)

    manager_dnfs = []
    alle_picks = []
    total_managers = len(liga_data['Value']['leaderboard'])

    for team in liga_data['Value']['leaderboard']:
        manager_name = urllib.parse.unquote(team['team_name'])
        ids = team['user_team']
        alle_picks.extend(ids)
        team_dnf = sum([dnf_katalog.get(pid, 0.0) for pid in ids])
        manager_dnfs.append({'Teamname': manager_name, 'DNFs im Team': team_dnf})

    df_dnf = pd.DataFrame(manager_dnfs)
    df_dnf = df_dnf.merge(df_aktuell[['Teamname', 'Manager']], on='Teamname', how='inner')

    st.subheader(" Pechvögel (Gesamte DNFs in der Saison)")
    df_dnf_sort = df_dnf.sort_values('DNFs im Team', ascending=False)
    
    chart_dnfs = alt.Chart(df_dnf_sort).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
        x=alt.X('Manager:N', sort='-y', title='Manager', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('DNFs im Team:Q', title='Anzahl Ausfälle (DNFs)', axis=alt.Axis(tickMinStep=1, format='d')),
        color=alt.Color('Manager:N', scale=manager_farben, legend=None),
        tooltip=['Manager', 'DNFs im Team']
    ).properties(height=400)
    
    st.altair_chart(chart_dnfs, use_container_width=True)
    st.markdown("---")

    st.subheader("Liga-Meta: Pick-Raten (%)")
    st.markdown("Wie viel Prozent der Manager haben diesen Fahrer/Konstrukteur aktuell?")
    
    pick_anzahl = collections.Counter(alle_picks)
    df_beliebt = pd.DataFrame(pick_anzahl.items(), columns=['ID', 'Anzahl'])
    df_beliebt['Name'] = df_beliebt['ID'].apply(lambda x: name_katalog.get(x, 'Unbekannt'))
    df_beliebt['Pick-Rate (%)'] = (df_beliebt['Anzahl'] / total_managers) * 100
    df_beliebt = df_beliebt.sort_values(by='Pick-Rate (%)', ascending=False)

    st.dataframe(
        df_beliebt[['Name', 'Pick-Rate (%)']],
        column_config={
            "Pick-Rate (%)": st.column_config.ProgressColumn(
                "Pick-Rate (%)",
                format="%d %%",
                min_value=0,
                max_value=100
            )
        },
        use_container_width=True,
        hide_index=True
    )

with tab4:
    st.header("🏆 Hall of Fame")
    
    st.subheader("Ewige Tabelle")
    st.markdown("Punktevergabe: Platz 1 = 50 Pkt | Platz 2 = 30 Pkt | Platz 3 = 20 Pkt")
    
    st.dataframe(
        df_permanent,
        column_config={
            "Platz": st.column_config.TextColumn("Platz"),
            "Punkte": st.column_config.NumberColumn("Ewige Punkte", format="%d"),
            "Meisterschaften": st.column_config.NumberColumn("🥇 Meisterschaften"),
            "Podien": st.column_config.NumberColumn("🏆 Podien gesamt")
        },
        use_container_width=True,
        hide_index=True
    )
    
    st.markdown("---")
    
    st.subheader("Vergangene Ergebnisse")
    st.markdown("Ein Blick zurück auf die Top 3 der vergangenen Saisons.")
    
    st.dataframe(
        df_legacy,
        use_container_width=True,
        hide_index=True
    )