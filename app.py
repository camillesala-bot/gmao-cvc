import os
import streamlit as st
from supabase import create_client, Client
from groq import Groq

# Configuration de la page
st.set_page_config(page_title="GMAO CVC Communale", page_icon="🔧", layout="centered")

# Initialisation des connexions via secrets Streamlit
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

@st.cache_resource
def init_groq() -> Groq:
    return Groq(api_key=st.secrets["GROQ_API_KEY"])

try:
    supabase = init_supabase()
    groq_client = init_groq()
except Exception as e:
    st.error("Erreur de configuration des clés API dans .streamlit/secrets.toml")
    st.stop()

# Navigation principale
st.sidebar.title("🛠️ GMAO CVC")
menu = st.sidebar.radio("Navigation", ["📱 Espace Technicien", "🏢 Fiches Bâtiments", "🖥️ Espace Responsable"])

# -----------------------------------------------------------------------------
# 1. ESPACE TECHNICIEN
# -----------------------------------------------------------------------------
if menu == "📱 Espace Technicien":
    st.title("📱 Espace Technicien")

    techs_data = supabase.table("techniciens").select("id, nom, prenom").execute().data

    if not techs_data:
        st.warning("⚠️ Aucun technicien trouvé dans Supabase. Veuillez exécuter le script SQL dans Supabase pour insérer les données de test.")
        st.stop()

    tech_options = {f"{t['prenom']} {t['nom']}": t['id'] for t in techs_data}
    selected_tech = st.selectbox("👤 Technicien connecté :", list(tech_options.keys()))
    tech_id = tech_options[selected_tech]

    # Récupération des OT assignés
    ots_data = supabase.table("ordres_travail") \
        .select("*, equipements(nom, locaux_techniques(nom, batiments(nom, adresse, notes_acces)))") \
        .eq("technicien_id", tech_id) \
        .in_("statut", ["ASSIGNE", "EN_COURS"]) \
        .execute().data

    if not ots_data:
        st.info("🎉 Aucun ordre de travail en attente pour vous.")
    else:
        ot_dict = {f"[{ot['priorite']}] {ot['code_ot']} - {ot['equipements']['locaux_techniques']['batiments']['nom']}": ot for ot in ots_data}
        selected_ot_label = st.selectbox("📋 Sélectionner votre intervention :", list(ot_dict.keys()))
        ot = ot_dict[selected_ot_label]

        batiment = ot['equipements']['locaux_techniques']['batiments']
        local = ot['equipements']['locaux_techniques']

        with st.container(border=True):
            st.subheader(f"{ot['code_ot']} — {batiment['nom']}")
            st.write(f"📍 **Adresse :** {batiment['adresse']}")
            st.write(f"🔑 **Accès :** {batiment['notes_acces']}")
            st.write(f"⚙️ **Équipement :** {ot['equipements']['nom']} (Local : {local['nom']})")
            st.warning(f"**Problème :** {ot['titre_anomalie']}\n\n_{ot['description_initiale']}_")

        st.subheader("🎙️ Dictée du compte-rendu")
        audio_file = st.audio_input("Enregistrer votre bilan vocal :")

        if "transcription" not in st.session_state:
            st.session_state.transcription = ""
            st.session_state.rapport_ia = ""

        if audio_file and st.button("🚀 Structurer le rapport via IA", type="secondary"):
            with st.spinner("Analyse par Whisper & Llama 3.1..."):
                audio_bytes = audio_file.read()
                
                # Transcription Whisper via Groq
                transcription = groq_client.audio.transcriptions.create(
                    file=("dictation.wav", audio_bytes),
                    model="whisper-large-v3",
                    language="fr"
                ).text
                
                # Rédaction du rapport via Llama 3.1
                prompt = f"""
                Tu es un assistant d'exploitation CVC.
                Transforme la dictée vocale suivante en un rapport structuré :
                "{transcription}"
                
                Format attendu (Markdown) :
                - **Diagnostic / Constat**
                - **Actions effectuées**
                - **Recommandations**
                """
                response = groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model="llama-3.3-70b-versatile"
           
                )
                
                st.session_state.transcription = transcription
                st.session_state.rapport_ia = response.choices[0].message.content

        if st.session_state.rapport_ia:
            st.markdown(st.session_state.rapport_ia)

        st.subheader("📊 Relevés de mesures")
        col1, col2 = st.columns(2)
        pression = col1.number_input("Pression réseau (bar)", value=1.5, step=0.1)
        temp_dep = col1.number_input("T° Départ (°C)", value=50.0, step=0.5)
        temp_ret = col2.number_input("T° Retour (°C)", value=40.0, step=0.5)
        duree = col2.number_input("Temps passé (minutes)", value=30, step=5)

        if st.button("✅ Clôturer l'intervention", type="primary"):
            if not st.session_state.rapport_ia:
                st.error("Veuillez d'abord enregistrer et analyser un compte-rendu vocal.")
            else:
                supabase.table("ordres_travail").update({
                    "statut": "TERMINE",
                    "dictee_vocale_raw": st.session_state.transcription,
                    "rapport_ia_structure": st.session_state.rapport_ia,
                    "pression_bar": pression,
                    "temperature_depart_c": temp_dep,
                    "temperature_retour_c": temp_ret,
                    "temps_passe_minutes": duree
                }).eq("id", ot["id"]).execute()
                
                st.success("Intervention clôturée avec succès !")
                st.session_state.transcription = ""
                st.session_state.rapport_ia = ""
                st.rerun()

# -----------------------------------------------------------------------------
# 2. FICHES BÂTIMENTS
# -----------------------------------------------------------------------------
elif menu == "🏢 Fiches Bâtiments":
    st.title("🏢 Fiches Bâtiments")

    batiments_data = supabase.table("batiments").select("*").execute().data
    if not batiments_data:
        st.info("Aucun bâtiment enregistré.")
    else:
        bat_options = {b['nom']: b for b in batiments_data}
        selected_bat_nom = st.selectbox("Sélectionner un bâtiment :", list(bat_options.keys()))
        bat = bat_options[selected_bat_nom]

        st.markdown(f"**📍 Adresse :** {bat['adresse']}")
        st.markdown(f"**👤 Contact sur place :** {bat['contact_nom']} ({bat['contact_telephone']})")
        st.info(f"**🔑 Accès :** {bat['notes_acces']}")

        st.subheader("📜 5 Dernières interventions réalisées")
        historique = supabase.table("ordres_travail") \
            .select("code_ot, titre_anomalie, rapport_ia_structure, date_fin, equipements!inner(locaux_techniques!inner(batiment_id))") \
            .eq("equipements.locaux_techniques.batiment_id", bat["id"]) \
            .eq("statut", "TERMINE") \
            .order("date_fin", desc=True) \
            .limit(5) \
            .execute().data

        if not historique:
            st.write("Aucun historique disponible pour ce bâtiment.")
        else:
            for h in historique:
                with st.expander(f"🛠️ {h['code_ot']} — {h['titre_anomalie']}"):
                    st.write(h['rapport_ia_structure'])

# -----------------------------------------------------------------------------
# 3. ESPACE RESPONSABLE
# -----------------------------------------------------------------------------
elif menu == "🖥️ Espace Responsable":
    st.title("🖥️ Espace Responsable")
    st.subheader("➕ Créer un Ordre de Travail")

    eq_data = supabase.table("equipements").select("id, nom, code_equipement, locaux_techniques(batiments(nom))").execute().data
    if not eq_data:
        st.warning("Aucun équipement disponible.")
    else:
        eq_options = {f"{e['locaux_techniques']['batiments']['nom']} - {e['nom']} ({e['code_equipement']})": e['id'] for e in eq_data}
        selected_eq = st.selectbox("Équipement concerné :", list(eq_options.keys()))

        techs_data = supabase.table("techniciens").select("id, nom, prenom").execute().data
        tech_options = {f"{t['prenom']} {t['nom']}": t['id'] for t in techs_data}
        selected_tech = st.selectbox("Attribuer au technicien :", list(tech_options.keys()))

        code_ot = st.text_input("Code OT (ex: OT-2026-003)", value="OT-2026-003")
        priorite = st.selectbox("Priorité :", ["P1_URGENT", "P2_HAUTE", "P3_NORMALE"])
        titre = st.text_input("Titre de l anomalie :", value="Bruit anormal sur régulation")
        description = st.text_area("Description :", value="Signalé par le gardien ce matin.")

        if st.button("🚀 Créer et attribuer l OT", type="primary"):
            supabase.table("ordres_travail").insert({
                "code_ot": code_ot,
                "equipement_id": eq_options[selected_eq],
                "technicien_id": tech_options[selected_tech],
                "priorite": priorite,
                "statut": "ASSIGNE",
                "titre_anomalie": titre,
                "description_initiale": description
            }).execute()
            st.success("Ordre de travail créé et disponible sur l application du technicien !")
                
