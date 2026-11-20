from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo
import difflib
import json
import os
import re
import time
import unicodedata

from fpdf import FPDF
from fpdf.enums import XPos, YPos
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from scipy.optimize import least_squares
from scipy.stats import poisson
import streamlit as st

try:
  import fonte_gratuita as fg   # storico e quote gratuiti, senza chiavi (file accanto ad app.py)
except ImportError:
  fg = None

st.set_page_config(
    page_title="Pronostici & Schedine", page_icon="⚽", layout="wide"
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 3.2rem; padding-bottom: 2.5rem; max-width: 1320px; }
    section[data-testid="stSidebar"] { border-right: 1px solid #E5E9F0; }
    section[data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }
    h4, h3 { font-weight: 650 !important; letter-spacing: -0.01em; }

    .app-title { font-size: 1.5rem; font-weight: 650; color: #1F2937; letter-spacing: -0.01em; }
    .app-sub { color: #6B7280; font-size: 0.9rem; margin: 0.1rem 0 1rem 0; }

    .mc-top { display: flex; gap: 0.6rem; align-items: center; color: #6B7280; font-size: 0.8rem; flex-wrap: wrap; }
    .mc-time { font-weight: 650; color: #374151; }
    .mc-teams { font-size: 1.08rem; font-weight: 650; color: #1F2937; margin: 0.2rem 0 0.15rem 0; }
    .mc-vs { color: #9CA3AF; font-weight: 400; font-size: 0.85rem; margin: 0 0.4rem; }
    .mc-hint { font-size: 0.8rem; color: #6B7280; margin: 0.1rem 0 0.4rem 0; }
    .mc-probs { font-size: 0.78rem; color: #6B7280; margin-bottom: 0.35rem; }
    .mc-probs b { color: #374151; font-weight: 600; margin-left: 0.15rem; }
    .mc-probs span { margin-right: 0.85rem; }

    .tag { display: inline-block; padding: 1px 9px; border-radius: 999px; font-size: 0.72rem; font-weight: 600; line-height: 1.5; }
    .tag-value { background: #E4F1EA; color: #2D6A4F; }
    .tag-warn { background: #FBF0DC; color: #8A5A12; }
    .tag-muted { background: #EDF0F4; color: #566070; }
    .tag-pick { background: #E3EBF5; color: #35598A; }

    .sl-match { font-weight: 600; color: #1F2937; font-size: 0.92rem; margin-top: 0.55rem; }
    .sl-meta { color: #6B7280; font-size: 0.76rem; margin-bottom: 0.25rem; }
    .sl-vuota { color: #6B7280; font-size: 0.88rem; line-height: 1.5; padding: 0.4rem 0 0.6rem 0; }

    div[data-testid="stColumn"]:has(#slip-marker), div[data-testid="column"]:has(#slip-marker) {
        position: sticky; top: 3.6rem; align-self: flex-start;
    }

    .kpi { background: #FFFFFF; border: 1px solid #E5E9F0; border-radius: 12px; padding: 14px 16px; height: 100%; }
    .kpi-l { font-size: 0.72rem; color: #6B7280; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }
    .kpi-v { font-size: 1.5rem; font-weight: 650; color: #1F2937; margin-top: 3px; }
    .kpi-n { font-size: 0.76rem; color: #6B7280; margin-top: 3px; }
    .kpi-pos .kpi-v { color: #2D6A4F; }
    .kpi-neg .kpi-v { color: #A8473F; }

    div[data-testid="stExpander"] { border-radius: 10px; }

    .steps { display: flex; gap: 0.6rem; flex-wrap: wrap; margin: 0.2rem 0 0.9rem 0; }
    .step { flex: 1 1 200px; background: #FFFFFF; border: 1px solid #E5E9F0; border-radius: 12px; padding: 10px 14px; font-size: 0.86rem; color: #374151; line-height: 1.4; }
    .step b { display: inline-block; width: 22px; height: 22px; line-height: 22px; text-align: center; border-radius: 50%; background: #4A6FA5; color: #fff; font-size: 0.78rem; margin-right: 8px; }
    .th { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #6B7280; font-weight: 650; text-align: center; padding-bottom: 2px; }
    .th-l { text-align: left; }
    .r-time { font-size: 0.78rem; color: #6B7280; }
    .r-time b { color: #374151; }
    .r-teams { font-size: 1.02rem; font-weight: 650; color: #1F2937; line-height: 1.3; margin: 1px 0 5px 0; }
    .r-teams span { color: #9CA3AF; font-weight: 400; font-size: 0.8rem; margin: 0 0.3rem; }
    .pbar { display: flex; height: 7px; border-radius: 999px; overflow: hidden; background: #EDF0F4; }
    .pbar i { display: block; height: 100%; }
    .plab { font-size: 0.74rem; color: #6B7280; margin-top: 2px; line-height: 1.3; }
    .plab.c { text-align: center; }
    .tag-bad { background: #F7E4E1; color: #9A3F37; }
    hr.rg { border: none; border-top: 1px solid #E9EDF3; margin: 0.35rem 0; }
    .vuoto { background: #FFFFFF; border: 1px dashed #C9D3E0; border-radius: 12px; padding: 1.4rem 1.2rem; color: #4B5563; line-height: 1.6; font-size: 0.95rem; }
    .giudizio { border-radius: 12px; padding: 14px 16px; margin-bottom: 0.7rem; border: 1px solid transparent; }
    .g-t { font-size: 1.15rem; font-weight: 650; }
    .g-d { font-size: 0.86rem; margin-top: 3px; line-height: 1.45; }
    .giudizio-value { background: #E9F4EE; border-color: #CFE3D6; color: #2D6A4F; }
    .giudizio-muted { background: #EEF2F7; border-color: #D9E0EA; color: #44546A; }
    .giudizio-bad { background: #FAECEA; border-color: #EBCFCB; color: #8E3B34; }
    .giudizio-warn { background: #FCF4E3; border-color: #EBDDB8; color: #7A5410; }
    </style>
    """,
    unsafe_allow_html=True,
)

TEMA_STREAMLIT = """[theme]
base = "light"
primaryColor = "#4A6FA5"
backgroundColor = "#F6F8FB"
secondaryBackgroundColor = "#FFFFFF"
textColor = "#1F2937"
font = "sans serif"
"""


def scrivi_tema_se_manca():
  """Crea .streamlit/config.toml con i colori soft. Streamlit lo legge all'avvio: vale dal prossimo riavvio."""
  try:
    cartella = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit")
    percorso = os.path.join(cartella, "config.toml")
    if not os.path.exists(percorso):
      os.makedirs(cartella, exist_ok=True)
      with open(percorso, "w", encoding="utf-8") as f:
        f.write(TEMA_STREAMLIT)
  except Exception:
    pass


scrivi_tema_se_manca()

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------
tz_roma = ZoneInfo("Europe/Rome")
oggi_dt = datetime.now(tz_roma)
oggi_date = oggi_dt.date()
DATA_MIN = oggi_date - timedelta(days=30)
DATA_MAX = oggi_date + timedelta(days=60)

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
ARCHIVIO_FILE = os.path.join(BASE_DIR, "archivio_scommesse.json")
FINANZA_FILE = os.path.join(BASE_DIR, "dati_finanza.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config_quote.json")
CACHE_QUOTE_FILE = os.path.join(BASE_DIR, "cache_quote.json")
CARTELLA_STORICO = os.path.join(BASE_DIR, "cache_storico")
FD_NOMI_VERIFICA = {"Serie A": "I1", "Serie B": "I2", "Premier League": "E0", "LaLiga": "SP1", "Bundesliga": "D1", "Ligue 1": "F1"}   # file scaricati da football-data e martj42

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

LEGHE_DA_INTERROGARE = [
    ("uefa.nations", "UEFA Nations League"),
    ("fifa.worldq.uefa", "Qualificazioni Mondiali UEFA"),
    ("fifa.worldq.conmebol", "Qualificazioni Mondiali CONMEBOL"),
    ("uefa.champions", "UEFA Champions League"),
    ("uefa.europa", "UEFA Europa League"),
    ("uefa.europa.conf", "UEFA Conference League"),
    ("ita.1", "Serie A"),
    ("ita.2", "Serie B"),
    ("eng.1", "Premier League"),
    ("esp.1", "LaLiga"),
    ("ger.1", "Bundesliga"),
    ("fra.1", "Ligue 1"),
    ("fifa.friendly", "Amichevoli Internazionali"),
]
SLUG_PER_COMPETIZIONE = {nome: slug for slug, nome in LEGHE_DA_INTERROGARE}

# Quote reali: The Odds API (https://the-odds-api.com, piano gratuito da 500 crediti al mese)
ODDS_BASE = "https://api.the-odds-api.com/v4"
TTL_QUOTE = 3 * 3600  # le quote scaricate restano valide 3 ore (ogni richiesta costa crediti)
SOGLIA_VALUE_BET = 0.03  # EV minimo per l'etichetta "VALUE BET"
ODDS_KEY_PER_SLUG = {  # lega ESPN -> competizione su The Odds API
    "uefa.nations": "soccer_uefa_nations_league",
    "uefa.champions": "soccer_uefa_champs_league",
    "uefa.europa": "soccer_uefa_europa_league",
    "uefa.europa.conf": "soccer_uefa_europa_conference_league",
    "ita.1": "soccer_italy_serie_a",
    "ita.2": "soccer_italy_serie_b",
    "eng.1": "soccer_epl",
    "esp.1": "soccer_spain_la_liga",
    "ger.1": "soccer_germany_bundesliga",
    "fra.1": "soccer_france_ligue_one",
}
# Seconda fonte: OddsPapi (https://oddspapi.io, piano gratuito da 250 richieste al mese)
OP_BASE = "https://api.oddspapi.io/v4"
OP_TTL = 6 * 3600          # quote e partite di OddsPapi riutilizzate per 6 ore
OP_MAX_RICHIESTE = 12      # partite scaricate per ogni pressione del pulsante
BOOK_SHARP = ("pinnacle",)  # bookmaker di riferimento per le probabilità
BOOK_ESCLUSI = ("-ex", "exchange", "matchbook", "smarkets")  # exchange: quote non confrontabili
STOPWORDS_SQUADRE = {"fc", "cf", "afc", "ac", "as", "sc", "fk", "bk", "if", "ssc", "us", "the", "club", "calcio"}
CAMPI_TECNICI = {"Kickoff", "Lega", "NomiCasa", "NomiOspite", "Mercati", "SoloModello", "Fonti"}  # non salvati nei ticket

# Nomi italiani delle partite già salvate in archivio -> nomi inglesi usati da ESPN
ALIAS_SQUADRE = {
    "danimarca": {"denmark"},
    "norvegia": {"norway"},
    "galles": {"wales"},
    "portogallo": {"portugal"},
    "bosnia-erzegovina": {"bosnia-herzegovina", "bosnia and herzegovina", "bosnia & herzegovina", "bosnia"},
    "romania": {"romania"},
    "irlanda": {"republic of ireland", "ireland"},
    "kosovo": {"kosovo"},
    "israele": {"israel"},
    "austria": {"austria"},
    "polonia": {"poland"},
    "svezia": {"sweden"},
    "ucraina": {"ukraine"},
    "georgia": {"georgia"},
    "ungheria": {"hungary"},
    "irlanda del nord": {"northern ireland"},
}


# ---------------------------------------------------------------------------
# Salvataggio / caricamento dati
# ---------------------------------------------------------------------------
def pulisci_tipi_numpy(obj):
  if isinstance(obj, list):
    return [pulisci_tipi_numpy(item) for item in obj]
  elif isinstance(obj, dict):
    return {str(key): pulisci_tipi_numpy(value) for key, value in obj.items()}
  elif isinstance(obj, (np.bool_, bool)):
    return bool(obj)
  elif isinstance(obj, (np.integer, int)):
    return int(obj)
  elif isinstance(obj, (np.floating, float)):
    return float(obj)
  return obj


def get_dati_iniziali_esatti():
  archivio_storico = [
      {
          "id_schedina": "schedina_storica_vinta_01",
          "data_salvataggio": "15/11/2026 20:00",
          "partite": [
              {
                  "Data": "15/11/2026",
                  "Ora": "20:45",
                  "Competizione": "UEFA Nations League",
                  "Match": "Storico Giocata #1",
                  "Consiglio": "1 (Vittoria Casa)",
                  "Quota": 1.42,
              }
          ],
          "quota_totale": 1.42,
          "importo_giocato": 10.0,
          "vincita_potenziale": 14.2,
          "stato_manuale": "vinto",
          "concluso": True,
      },
      {
          "id_schedina": "schedina_storica_persa_02",
          "data_salvataggio": "15/11/2026 21:00",
          "partite": [
              {
                  "Data": "15/11/2026",
                  "Ora": "21:00",
                  "Competizione": "UEFA Nations League",
                  "Match": "Storico Giocata #2",
                  "Consiglio": "2 (Vittoria Ospite)",
                  "Quota": 2.00,
              }
          ],
          "quota_totale": 2.00,
          "importo_giocato": 10.0,
          "vincita_potenziale": 20.0,
          "stato_manuale": "perso",
          "concluso": True,
      },
  ]
  finanza_storica = {"bankroll_iniziale": 35.80, "movimenti": []}
  return archivio_storico, finanza_storica


def _metti_da_parte_file_illeggibile(percorso):
  """Se il file esiste ma non è leggibile lo rinomina, così non viene sovrascritto."""
  try:
    if os.path.exists(percorso):
      os.replace(percorso, percorso + ".corrotto")
  except Exception:
    pass


def carica_archivio():
  if os.path.exists(ARCHIVIO_FILE):
    try:
      with open(ARCHIVIO_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
      # Una lista vuota è valida (l'utente può aver eliminato tutti i ticket)
      if isinstance(data, list):
        return pulisci_tipi_numpy(data)
    except Exception:
      pass
    _metti_da_parte_file_illeggibile(ARCHIVIO_FILE)

  archivio_default, _ = get_dati_iniziali_esatti()
  try:
    with open(ARCHIVIO_FILE, "w", encoding="utf-8") as f:
      json.dump(pulisci_tipi_numpy(archivio_default), f, ensure_ascii=False, indent=4)
  except Exception:
    pass
  return archivio_default


def salva_archivio(archivio):
  archivio_pulito = pulisci_tipi_numpy(archivio)
  st.session_state.archivio_scommesse = archivio_pulito
  try:
    with open(ARCHIVIO_FILE, "w", encoding="utf-8") as f:
      json.dump(archivio_pulito, f, ensure_ascii=False, indent=4)
  except Exception as e:
    st.error(f"Errore salvataggio archivio locale: {e}")


def carica_finanza():
  if os.path.exists(FINANZA_FILE):
    try:
      with open(FINANZA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
      if isinstance(data, dict) and "bankroll_iniziale" in data:
        data = pulisci_tipi_numpy(data)
        if not isinstance(data.get("movimenti"), list):
          data["movimenti"] = []
        return data
    except Exception:
      pass
    _metti_da_parte_file_illeggibile(FINANZA_FILE)

  _, finanza_default = get_dati_iniziali_esatti()
  try:
    with open(FINANZA_FILE, "w", encoding="utf-8") as f:
      json.dump(pulisci_tipi_numpy(finanza_default), f, ensure_ascii=False, indent=4)
  except Exception:
    pass
  return finanza_default


def salva_finanza(dati):
  dati_puliti = pulisci_tipi_numpy(dati)
  st.session_state.dati_finanza = dati_puliti
  try:
    with open(FINANZA_FILE, "w", encoding="utf-8") as f:
      json.dump(dati_puliti, f, ensure_ascii=False, indent=4)
  except Exception as e:
    st.error(f"Errore salvataggio finanza locale: {e}")


def vincita_ticket(schedina):
  """Vincita di un ticket: usa il valore salvato (calcolato sulla quota non arrotondata)."""
  try:
    v = float(schedina.get("vincita_potenziale"))
    if v > 0:
      return round(v, 2)
  except (TypeError, ValueError):
    pass
  importo = float(schedina.get("importo_giocato", 0) or 0)
  quota = float(schedina.get("quota_totale", 1.0) or 1.0)
  return round(importo * quota, 2)


def e_concluso(s):
  return bool(s.get("concluso", False)) and s.get("stato_manuale") in ("vinto", "perso")


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def pulisci_testo_pdf(txt):
  return (
      str(txt)
      .replace("—", "-")
      .replace("–", "-")
      .replace("✅", "[VINTA]")
      .replace("❌", "[PERSA]")
      .replace("⏳", "[IN ATTESA]")
      .replace("🟢", "")
      .replace("🔴", "")
      .encode("latin-1", "ignore")
      .decode("latin-1")
      .strip()
  )


def _a_capo(pdf, h, testo, **kw):
  pdf.cell(0, h, testo, new_x=XPos.LMARGIN, new_y=YPos.NEXT, **kw)


def genera_pdf_schedina(schedina, partite_verificate, etichetta_stato):
  pdf = FPDF()
  pdf.add_page()
  pdf.set_auto_page_break(auto=True, margin=15)

  pdf.set_fill_color(15, 32, 39)
  pdf.rect(10, 10, 190, 26, "F")
  pdf.set_text_color(255, 255, 255)
  pdf.set_font("Helvetica", "B", 15)
  pdf.set_xy(15, 14)
  _a_capo(pdf, 8, "RICEVUTA SCHEDINA - BETTING ANALYTICS PRO")
  pdf.set_font("Helvetica", "", 10)
  pdf.set_x(15)
  data_salv = pulisci_testo_pdf(schedina.get("data_salvataggio", "N/D"))
  stato_clean = pulisci_testo_pdf(etichetta_stato)
  _a_capo(pdf, 6, f"Data Emissione: {data_salv}   |   Stato Ticket: {stato_clean}")

  pdf.ln(10)
  pdf.set_text_color(33, 37, 41)
  pdf.set_font("Helvetica", "B", 11)
  _a_capo(pdf, 8, "DETTAGLIO EVENTI IN GIOCATA:")
  pdf.ln(2)

  pdf.set_fill_color(233, 236, 239)
  pdf.set_font("Helvetica", "B", 8.5)
  col_widths = [26, 38, 52, 36, 14, 24]
  headers = ["Data/Ora", "Campionato", "Match", "Esito Giocato", "Quota", "Risultato"]
  for w, h in zip(col_widths, headers):
    pdf.cell(w, 8, h, border=1, fill=True, align="C")
  pdf.ln()

  pdf.set_font("Helvetica", "", 8)
  for p in partite_verificate:
    data_ora = pulisci_testo_pdf(f"{p.get('Data', '')} {p.get('Ora', '')}")[:16]
    camp = pulisci_testo_pdf(p.get("Competizione", p.get("Campionato", "N/D")))[:22]
    match = pulisci_testo_pdf(p.get("Match", ""))[:30]
    esito = pulisci_testo_pdf(p.get("Consiglio", p.get("Esito", "N/D")))[:22]
    quota = pulisci_testo_pdf(f"{float(p.get('Quota', 1.0)):.2f}")
    ris = pulisci_testo_pdf(p.get("Risultato Reale", "In attesa"))[:14]

    pdf.cell(col_widths[0], 7, data_ora, border=1, align="C")
    pdf.cell(col_widths[1], 7, camp, border=1)
    pdf.cell(col_widths[2], 7, match, border=1)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(col_widths[3], 7, esito, border=1)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(col_widths[4], 7, quota, border=1, align="C")
    pdf.cell(col_widths[5], 7, ris, border=1, align="C")
    pdf.ln()

  pdf.ln(8)
  importo = float(schedina.get("importo_giocato", 0.0))
  quota_tot = float(schedina.get("quota_totale", 1.0))
  vincita = vincita_ticket(schedina)

  pdf.set_fill_color(248, 249, 250)
  pdf.set_draw_color(206, 212, 218)
  y_box = pdf.get_y()
  pdf.rect(10, y_box, 190, 28, "DF")

  pdf.set_xy(15, y_box + 4)
  pdf.set_font("Helvetica", "", 10)
  pdf.cell(90, 6, f"Importo Scommesso: EUR {importo:.2f}")
  _a_capo(pdf, 6, f"Quota Totale Combinata: {quota_tot:.2f}")

  pdf.set_xy(15, y_box + 14)
  pdf.set_font("Helvetica", "B", 12)
  pdf.set_text_color(25, 135, 84)
  _a_capo(pdf, 8, f"VINCITA POTENZIALE: EUR {vincita:.2f}")

  return bytes(pdf.output())


def genera_pdf_archivio_globale(archivio_lista):
  pdf = FPDF()
  pdf.add_page()
  pdf.set_auto_page_break(auto=True, margin=15)

  pdf.set_fill_color(15, 32, 39)
  pdf.rect(10, 10, 190, 26, "F")
  pdf.set_text_color(255, 255, 255)
  pdf.set_font("Helvetica", "B", 14)
  pdf.set_xy(15, 14)
  _a_capo(pdf, 8, "RIEPILOGO SCOMMESSE IN CORSO / IN ATTESA")
  pdf.set_font("Helvetica", "", 10)
  pdf.set_x(15)
  data_oggi = datetime.now(tz_roma).strftime("%d/%m/%Y %H:%M")
  _a_capo(pdf, 6, pulisci_testo_pdf(f"Data Generazione: {data_oggi}   |   Totale Ticket in Attesa: {len(archivio_lista)}"))

  pdf.ln(10)

  for idx, schedina in enumerate(archivio_lista):
    pdf.set_text_color(15, 32, 39)
    pdf.set_font("Helvetica", "B", 10)
    data_ticket = schedina.get("data_salvataggio", "N/D")
    q_tot = schedina.get("quota_totale", 1.0)
    puntata = float(schedina.get("importo_giocato", 0.0) or 0.0)

    titolo_ticket = pulisci_testo_pdf(f"TICKET #{len(archivio_lista) - idx} del {data_ticket} - Quota: {q_tot} - Puntata: EUR {puntata:.2f}")
    _a_capo(pdf, 6, titolo_ticket)
    pdf.ln(1)

    pdf.set_fill_color(233, 236, 239)
    pdf.set_font("Helvetica", "B", 8)
    col_widths = [26, 38, 56, 36, 14, 20]
    headers = ["Data/Ora", "Campionato", "Match", "Esito", "Quota", "Stato"]
    for w, h in zip(col_widths, headers):
      pdf.cell(w, 6, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 7.5)
    for p in schedina.get("partite", []):
      d_ora = pulisci_testo_pdf(f"{p.get('Data', '')} {p.get('Ora', '')}")[:16]
      camp = pulisci_testo_pdf(p.get("Competizione", p.get("Campionato", "N/D")))[:22]
      match = pulisci_testo_pdf(p.get("Match", ""))[:32]
      esito = pulisci_testo_pdf(p.get("Consiglio", p.get("Esito", "N/D")))[:22]
      q = pulisci_testo_pdf(f"{float(p.get('Quota', 1.0)):.2f}")

      manuale = schedina.get("stato_manuale")
      if manuale == "vinto":
        stato_p = "Vinta"
      elif manuale == "perso":
        stato_p = "Persa"
      else:
        _, _, fw = verifica_risultato_partita(
            p.get("Competizione", p.get("Campionato", "")),
            p.get("Match", ""),
            p.get("Consiglio", p.get("Esito", "")),
            p.get("Data", "")
        )
        stato_p = "In attesa" if fw is None else ("Vinta" if fw else "Persa")

      pdf.cell(col_widths[0], 6, d_ora, border=1, align="C")
      pdf.cell(col_widths[1], 6, camp, border=1)
      pdf.cell(col_widths[2], 6, match, border=1)
      pdf.cell(col_widths[3], 6, esito, border=1)
      pdf.cell(col_widths[4], 6, q, border=1, align="C")
      pdf.cell(col_widths[5], 6, stato_p, border=1, align="C")
      pdf.ln()

    pdf.ln(6)

  return bytes(pdf.output())


# ---------------------------------------------------------------------------
# Rete / ESPN
# ---------------------------------------------------------------------------
def scarica_json(url):
  """Scarica un JSON; restituisce None se la richiesta fallisce."""
  try:
    res = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
    if res.status_code == 200:
      return res.json()
  except Exception:
    pass
  return None


def nomi_equivalenti(nome):
  n = str(nome).strip().lower()
  return {n} | ALIAS_SQUADRE.get(n, set())


def _nomi_team(competitor):
  team = competitor.get("team", {})
  chiavi = ("name", "shortDisplayName", "displayName", "location")
  return {str(team[k]).strip().lower() for k in chiavi if team.get(k)}


def _slug_per_competizione(competizione):
  if competizione in SLUG_PER_COMPETIZIONE:
    return SLUG_PER_COMPETIZIONE[competizione]
  base = str(competizione).split(" - ")[0].strip()
  return SLUG_PER_COMPETIZIONE.get(base)


@st.cache_data(ttl=600, show_spinner=False)
def cerca_risultato(competizione, casa, ospite, data_yyyymmdd):
  """Cerca la partita su ESPN.

  Restituisce ("finale", gol_casa, gol_ospite), ("in_corso", 0, 0) oppure None.
  """
  casa_n = nomi_equivalenti(casa)
  ospite_n = nomi_equivalenti(ospite)

  slugs = []
  slug = _slug_per_competizione(competizione)
  if slug:
    slugs.append(slug)
  slugs.append("all")

  base = datetime.strptime(data_yyyymmdd, "%Y%m%d")
  # ESPN raggruppa per giorno UTC/USA: si controllano anche il giorno dopo e prima
  date_da_provare = [base + timedelta(days=d) for d in (0, 1, -1)]

  for slug in slugs:
    for d in date_da_provare:
      data = scarica_json(f"{ESPN_BASE}/{slug}/scoreboard?dates={d:%Y%m%d}&limit=300")
      if not data:
        continue
      for event in data.get("events", []):
        comps = event.get("competitions") or []
        if not comps:
          continue
        competitors = comps[0].get("competitors", [])
        if len(competitors) < 2:
          continue
        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
        if _nomi_team(home) & casa_n and _nomi_team(away) & ospite_n:
          tipo = event.get("status", {}).get("type", {})
          # Nel calcio ESPN usa STATUS_FULL_TIME (non STATUS_FINAL): si usa il flag "completed"
          if tipo.get("completed"):
            try:
              return ("finale", int(home.get("score", 0)), int(away.get("score", 0)))
            except (TypeError, ValueError):
              return ("in_corso", 0, 0)
          return ("in_corso", 0, 0)
  return None


def valuta_esito(esito, gol_casa, gol_ospite):
  tot_gol = gol_casa + gol_ospite
  if "1X" in esito:
    ok = gol_casa >= gol_ospite
    if "Under 3.5" in esito:
      ok = ok and tot_gol < 3.5
    return ok
  if "1 (Vittoria Casa)" in esito:
    return gol_casa > gol_ospite
  if "2 (Vittoria Ospite)" in esito:
    return gol_ospite > gol_casa
  if "Over 2.5" in esito:
    return tot_gol > 2.5
  if "Under 2.5" in esito:
    return tot_gol < 2.5
  if "Goal" in esito:
    return gol_casa > 0 and gol_ospite > 0
  return False


def verifica_risultato_partita(competizione, match_str, esito_consigliato, data_partita_str=None):
  if not match_str or " vs " not in match_str:
    return "⏳ In attesa", "N/D", None

  squadra_casa, squadra_ospite = match_str.split(" vs ", 1)
  data_ref = st.session_state.get("data_corrente", oggi_date)
  param_data = data_ref.strftime("%Y%m%d")
  if data_partita_str:
    try:
      param_data = datetime.strptime(data_partita_str.strip(), "%d/%m/%Y").strftime("%Y%m%d")
    except Exception:
      pass

  esito = cerca_risultato(competizione, squadra_casa.strip(), squadra_ospite.strip(), param_data)
  if esito is None:
    return "⏳ In attesa", "N/D", None
  if esito[0] == "finale":
    _, score_casa, score_ospite = esito
    vincente = valuta_esito(esito_consigliato, score_casa, score_ospite)
    return (
        f"{score_casa} - {score_ospite}",
        "✅ Vincente" if vincente else "❌ Perdente",
        vincente,
    )
  return "In corso / Programmata", "⏳ In attesa", None


# ---------------------------------------------------------------------------
# Quote reali (The Odds API)
# ---------------------------------------------------------------------------
def leggi_chiave(nome_env, nome_cfg):
  """Restituisce (chiave, origine). Ordine: variabile d'ambiente, st.secrets, file locale."""
  chiave = os.environ.get(nome_env, "").strip()
  if chiave:
    return chiave, "variabile d'ambiente"
  try:
    chiave = str(st.secrets.get(nome_env, "")).strip()
    if chiave:
      return chiave, "secrets di Streamlit"
  except Exception:
    pass
  try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
      chiave = str(json.load(f).get(nome_cfg, "")).strip()
    if chiave:
      return chiave, "file locale"
  except Exception:
    pass
  return "", ""


def salva_chiave(nome_cfg, chiave):
  """Salva una chiave nel file di configurazione senza toccare le altre."""
  cfg = {}
  try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
      letto = json.load(f)
    if isinstance(letto, dict):
      cfg = letto
  except Exception:
    pass
  cfg[nome_cfg] = chiave.strip()
  try:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
      json.dump(cfg, f, ensure_ascii=False, indent=4)
  except Exception as e:
    st.error(f"Impossibile salvare la chiave: {e}")


INTERRUTTORI = {"usa_oddsapi": True, "usa_oddspapi": True, "usa_gratis": True}


def leggi_interruttori():
  """Interruttori delle fonti salvati nel file di configurazione (tutti attivi se non c'è nulla)."""
  try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
      cfg = json.load(f)
    salvati = cfg.get("interruttori", {}) if isinstance(cfg, dict) else {}
  except Exception:
    salvati = {}
  return {k: bool(salvati.get(k, v)) for k, v in INTERRUTTORI.items()}


def salva_interruttori(valori):
  cfg = {}
  try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
      letto = json.load(f)
    if isinstance(letto, dict):
      cfg = letto
  except Exception:
    pass
  cfg["interruttori"] = {k: bool(valori[k]) for k in INTERRUTTORI}
  try:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
      json.dump(cfg, f, ensure_ascii=False, indent=4)
  except Exception as e:
    st.error(f"Impossibile salvare le impostazioni: {e}")


def carica_cache_quote():
  try:
    with open(CACHE_QUOTE_FILE, "r", encoding="utf-8") as f:
      data = json.load(f)
    if isinstance(data, dict):
      return data
  except Exception:
    pass
  return {}


def salva_cache_quote(cache):
  try:
    with open(CACHE_QUOTE_FILE, "w", encoding="utf-8") as f:
      json.dump(cache, f, ensure_ascii=False)
  except Exception:
    pass


def _norm_nome(nome):
  n = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode("ascii").lower()
  n = n.replace("&", " and ")
  token = [t for t in re.split(r"[^a-z0-9]+", n) if t]
  filtrati = [t for t in token if t not in STOPWORDS_SQUADRE]
  return " ".join(filtrati or token)


def _somiglianza(a, b):
  a, b = _norm_nome(a), _norm_nome(b)
  if not a or not b:
    return 0.0
  if a == b:
    return 1.0
  if a in b or b in a:
    return 0.9
  return difflib.SequenceMatcher(None, a, b).ratio()


def _somiglianza_varianti(varianti, nome_odds):
  return max((_somiglianza(v, nome_odds) for v in varianti), default=0.0)


def _parse_iso(testo):
  return datetime.fromisoformat(str(testo).replace("Z", "+00:00"))


def trova_evento_quote(match, eventi):
  """Abbina una partita ESPN a un evento di The Odds API (orario di inizio + somiglianza dei nomi)."""
  try:
    inizio = _parse_iso(match["Kickoff"])
  except Exception:
    return None
  migliore, punteggio = None, 0.0
  for ev in eventi:
    try:
      if abs((_parse_iso(ev["commence"]) - inizio).total_seconds()) > 3 * 3600:
        continue
    except Exception:
      continue
    s_casa = _somiglianza_varianti(match.get("NomiCasa", []), ev["home"])
    s_ospite = _somiglianza_varianti(match.get("NomiOspite", []), ev["away"])
    if min(s_casa, s_ospite) < 0.55:
      continue
    if s_casa + s_ospite > punteggio:
      migliore, punteggio = ev, s_casa + s_ospite
  return migliore if punteggio >= 1.3 else None


def riassumi_evento(ev):
  """Riduce un evento di The Odds API alle sole quote 1X2 e Over/Under 2.5 per bookmaker."""
  casa, ospite = ev.get("home_team", ""), ev.get("away_team", "")
  h2h, totals = [], []
  for b in ev.get("bookmakers", []):
    nome_book = b.get("title") or b.get("key") or "?"
    for mercato in b.get("markets", []):
      esiti = mercato.get("outcomes", [])
      if mercato.get("key") == "h2h":
        q = {o.get("name"): o.get("price") for o in esiti}
        if all(isinstance(q.get(k), (int, float)) and q.get(k) > 1 for k in (casa, "Draw", ospite)):
          h2h.append([nome_book, float(q[casa]), float(q["Draw"]), float(q[ospite])])
      elif mercato.get("key") == "totals":
        linea = [o for o in esiti if o.get("point") is not None and abs(float(o["point"]) - 2.5) < 1e-9]
        q = {o.get("name"): o.get("price") for o in linea}
        if all(isinstance(q.get(k), (int, float)) and q.get(k) > 1 for k in ("Over", "Under")):
          totals.append([nome_book, float(q["Over"]), float(q["Under"])])
  return {"home": casa, "away": ospite, "commence": ev.get("commence_time", ""), "h2h": h2h, "totals": totals}


def scarica_quote_lega(odds_key, chiave, forza=False):
  """Quote di una competizione. Usa la cache su disco (TTL_QUOTE) per risparmiare crediti.

  Restituisce (eventi, messaggio_errore_o_None)."""
  cache = carica_cache_quote()
  voce = cache.get("quote", {}).get(odds_key)
  ora = time.time()
  if voce and not forza and ora - voce.get("ts", 0) < TTL_QUOTE:
    return voce.get("eventi", []), None

  vecchi = voce.get("eventi", []) if voce else []
  try:
    res = requests.get(
        f"{ODDS_BASE}/sports/{odds_key}/odds",
        params={
            "apiKey": chiave,
            "regions": "eu",
            "markets": "h2h,totals",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        },
        timeout=15,
    )
  except Exception:
    return vecchi, "Impossibile contattare The Odds API."

  if res.status_code != 200:
    messaggi = {
        401: "Chiave API non valida.",
        404: f"Competizione '{odds_key}' non disponibile su The Odds API.",
        422: f"Richiesta non valida per '{odds_key}'.",
        429: "Crediti esauriti o troppe richieste a The Odds API.",
    }
    return vecchi, messaggi.get(res.status_code, f"The Odds API ha risposto con errore {res.status_code}.")

  try:
    eventi = [riassumi_evento(e) for e in res.json()]
  except Exception:
    return vecchi, "Risposta di The Odds API non leggibile."

  cache.setdefault("quote", {})[odds_key] = {"ts": ora, "eventi": eventi}
  rimasti = res.headers.get("x-requests-remaining")
  if rimasti is not None:
    cache["crediti_rimasti"] = rimasti
  salva_cache_quote(cache)
  return eventi, None


# ---------------------------------------------------------------------------
# Modello: probabilità di mercato, Poisson implicito, EV
# ---------------------------------------------------------------------------
def _matrice_poisson(lambda_casa, lambda_ospite, max_goals=11):
  k = np.arange(max_goals)
  # righe = gol della squadra di casa, colonne = gol della squadra ospite
  return np.outer(poisson.pmf(k, lambda_casa), poisson.pmf(k, lambda_ospite))


def calcola_probabilita_poisson(lambda_casa, lambda_ospite, max_goals=11):
  matrice = _matrice_poisson(lambda_casa, lambda_ospite, max_goals)
  i, j = np.indices(matrice.shape)
  valori = (
      matrice[i > j].sum(),                      # 1
      matrice[i == j].sum(),                     # X
      matrice[i < j].sum(),                      # 2
      matrice[(i + j) > 2.5].sum(),              # Over 2.5
      matrice[(i >= 1) & (j >= 1)].sum(),        # Goal
      matrice[(i >= j) & ((i + j) < 3.5)].sum(), # 1X + Under 3.5
  )
  return tuple(round(float(x) * 100, 1) for x in valori)


def stima_xg_da_mercato(p1, pX, p2, p_over=None):
  """Trova i gol attesi (Poisson) che riproducono le probabilità del mercato."""
  def residui(x):
    m = _matrice_poisson(x[0], x[1])
    i, j = np.indices(m.shape)
    r = [m[i > j].sum() - p1, m[i == j].sum() - pX, m[i < j].sum() - p2]
    if p_over is not None:
      r.append(m[(i + j) > 2.5].sum() - p_over)
    return r

  sol = least_squares(residui, x0=[1.4, 1.1], bounds=([0.05, 0.05], [6.0, 6.0]))
  return round(float(sol.x[0]), 2), round(float(sol.x[1]), 2)


def _prob_senza_margine(quote):
  """Probabilità implicite normalizzate (margine del bookmaker tolto) e margine."""
  inverse = [1.0 / q for q in quote]
  somma = sum(inverse)
  return [x / somma for x in inverse], somma - 1.0


def _migliore_quota(righe, idx):
  """Quota più alta tra i bookmaker, ignorando valori anomali (oltre +25% rispetto alla mediana)."""
  valori = sorted(r[idx] for r in righe)
  mediana = valori[len(valori) // 2]
  ammesse = [r for r in righe if r[idx] <= mediana * 1.25] or righe
  riga = max(ammesse, key=lambda r: r[idx])
  return riga[idx], riga[0]


def _mercato(nome, quota, bookmaker, prob):
  return {
      "Consiglio": nome,
      "Quota": round(float(quota), 2),
      "Bookmaker": bookmaker,
      "ValoreProb": round(float(prob) * 100, 1),
      "EV": round(float(quota * prob - 1.0), 3),
  }


def _prob_di_mercato(righe):
  """Probabilità di mercato senza margine. Se c'è Pinnacle (bookmaker 'sharp') si usa solo lui,
  altrimenti la media di tutti. Restituisce (probabilità, margine medio, etichetta)."""
  sharp = [r for r in righe if any(s in str(r[0]).lower() for s in BOOK_SHARP)]
  base = sharp or righe
  risultati = [_prob_senza_margine(r[1:]) for r in base]
  prob = [float(x) for x in np.mean([r[0] for r in risultati], axis=0)]
  margine = float(np.mean([r[1] for r in risultati]))
  return prob, margine, ("Pinnacle" if sharp else f"{len(base)} bookmaker")


def costruisci_analisi(match, ev, fonte="The Odds API"):
  """Mercati con quota reale, probabilità di mercato ed EV per una partita."""
  mercati = []
  p1 = pX = p2 = p_over = None
  lc = lo = None
  n_book = 0
  margine_medio = None
  etichetta = ""

  h2h = ev.get("h2h", [])
  if h2h:
    n_book = len(h2h)
    (p1, pX, p2), margine_medio, etichetta = _prob_di_mercato(h2h)
    q1, b1 = _migliore_quota(h2h, 1)
    q2, b2 = _migliore_quota(h2h, 3)
    mercati.append(_mercato("1 (Vittoria Casa)", q1, b1, p1))
    mercati.append(_mercato("2 (Vittoria Ospite)", q2, b2, p2))

  totals = ev.get("totals", [])
  if totals:
    (p_over, p_under), _, et_tot = _prob_di_mercato(totals)
    qo, bo = _migliore_quota(totals, 1)
    qu, bu = _migliore_quota(totals, 2)
    mercati.append(_mercato("Over 2.5", qo, bo, p_over))
    mercati.append(_mercato("Under 2.5", qu, bu, p_under))
    n_book = max(n_book, len(totals))
    etichetta = etichetta or et_tot

  btts = ev.get("btts", [])
  if btts:
    (p_si, _), _, et_btts = _prob_di_mercato(btts)
    qs, bs = _migliore_quota(btts, 1)
    mercati.append(_mercato("Goal (Entrambe Segnano)", qs, bs, p_si))
    n_book = max(n_book, len(btts))
    etichetta = etichetta or et_btts

  if h2h:
    lc, lo = stima_xg_da_mercato(p1, pX, p2, p_over)
    xg_str = f"xG impliciti: {lc:.2f} - {lo:.2f} | Mercato [1:{p1 * 100:.1f}% X:{pX * 100:.1f}% 2:{p2 * 100:.1f}%]"
    tot_xg = f" Totale gol atteso {lc + lo:.2f}."
  else:
    xg_str = "xG impliciti: n/d | Senza quote 1X2"
    tot_xg = ""
  margine_txt = f" Margine {margine_medio * 100:.1f}%." if margine_medio is not None else ""
  motivazione = (
      f"[{match['Competizione']}] Probabilità da {etichetta} (margine tolto).{tot_xg}{margine_txt} "
      f"Quota = migliore tra {n_book} bookmaker. Fonte: {fonte}."
  )
  return {"Mercati": mercati, "Analisi xG": xg_str, "Motivazione": motivazione}


def applica_pronostico(match, soglia_prob):
  """Sceglie il mercato col valore atteso più alto tra quelli sopra la soglia di probabilità."""
  candidati = [x for x in match.get("Mercati", []) if x["ValoreProb"] >= soglia_prob]
  if not candidati:
    return None
  # Se le quote sono solo stimate l'EV vale 0 per tutti: si sceglie il mercato più probabile
  chiave = "ValoreProb" if match.get("SoloModello") else "EV"
  scelto = max(candidati, key=lambda x: x[chiave])
  riga = {k: v for k, v in match.items() if k not in ("Mercati", "Fonti")}
  riga.update({
      "Consiglio": scelto["Consiglio"],
      "Quota": scelto["Quota"],
      "ValoreProb": scelto["ValoreProb"],
      "EV": scelto["EV"],
      "Bookmaker": scelto["Bookmaker"],
      "ValueBet": bool(scelto["EV"] > SOGLIA_VALUE_BET),
  })
  return riga


def aggancia_quote(partite_base, chiave, forza=False):
  """Aggiunge a ogni partita i mercati con quote reali. Restituisce (partite, errori)."""
  errori = []
  eventi_per_lega = {}
  if chiave:
    for key in sorted({ODDS_KEY_PER_SLUG[m["Lega"]] for m in partite_base if m.get("Lega") in ODDS_KEY_PER_SLUG}):
      eventi, errore = scarica_quote_lega(key, chiave, forza)
      eventi_per_lega[key] = eventi
      if errore and errore not in errori:
        errori.append(errore)
        if "Chiave API non valida" in errore or "Crediti esauriti" in errore:
          break  # inutile insistere con le altre competizioni

  risultato = []
  for m in partite_base:
    m2 = dict(m)
    m2["Mercati"] = []
    key = ODDS_KEY_PER_SLUG.get(m.get("Lega"))
    ev = trova_evento_quote(m, eventi_per_lega.get(key, [])) if key else None
    if ev:
      m2.update(costruisci_analisi(m, ev))
      m2["Fonti"] = {"The Odds API": ev}
    risultato.append(m2)
  return risultato, errori


# ---------------------------------------------------------------------------
# Seconda fonte di quote: OddsPapi (piano gratuito: 250 richieste al mese)
# Ogni partita costa una richiesta, quindi lo scaricamento parte solo da un pulsante.
# ---------------------------------------------------------------------------
def _mese_corrente():
  return datetime.now(tz_roma).strftime("%Y-%m")


def richieste_oddspapi_usate():
  uso = carica_cache_quote().get("oddspapi", {}).get("uso", {})
  return int(uso.get("n", 0)) if uso.get("mese") == _mese_corrente() else 0


def _op_conta_richiesta():
  cache = carica_cache_quote()
  op = cache.setdefault("oddspapi", {})
  uso = op.get("uso", {})
  n = int(uso.get("n", 0)) if uso.get("mese") == _mese_corrente() else 0
  op["uso"] = {"mese": _mese_corrente(), "n": n + 1}
  salva_cache_quote(cache)


def _op_get(percorso, chiave, params):
  """Una richiesta a OddsPapi (rispetta la pausa di 1 secondo). Restituisce (json, errore)."""
  attesa = 1.1 - (time.time() - st.session_state.get("_op_ultima_richiesta", 0.0))
  if attesa > 0:
    time.sleep(attesa)
  try:
    res = requests.get(f"{OP_BASE}/{percorso}", params={**params, "apiKey": chiave}, timeout=20)
  except Exception:
    st.session_state["_op_ultima_richiesta"] = time.time()
    return None, "Impossibile contattare OddsPapi."
  st.session_state["_op_ultima_richiesta"] = time.time()
  _op_conta_richiesta()
  if res.status_code != 200:
    messaggi = {
        401: "Chiave OddsPapi non valida.",
        403: "Chiave OddsPapi non valida o senza accesso.",
        429: "Limite di richieste OddsPapi raggiunto (250 al mese, 1 al secondo).",
    }
    return None, messaggi.get(res.status_code, f"OddsPapi ha risposto con errore {res.status_code}.")
  try:
    return res.json(), None
  except Exception:
    return None, "Risposta di OddsPapi non leggibile."


def _pota(dizionario, massimo):
  """Tiene solo le voci più recenti (campo 'ts') per non far crescere la cache."""
  if len(dizionario) > massimo:
    for k in sorted(dizionario, key=lambda k: dizionario[k].get("ts", 0))[:-massimo]:
      del dizionario[k]


def op_fixtures(chiave, giorno_str, consenti_rete):
  """Partite di calcio con quote del giorno su OddsPapi. Restituisce (lista, errore)."""
  cache = carica_cache_quote()
  voce = cache.get("oddspapi", {}).get("fixtures", {}).get(giorno_str)
  if voce and time.time() - voce.get("ts", 0) < OP_TTL:
    return voce["lista"], None
  if not consenti_rete:
    return [], None

  inizio = datetime.strptime(giorno_str, "%Y-%m-%d").replace(tzinfo=tz_roma).astimezone(timezone.utc) - timedelta(hours=1)
  fine = inizio + timedelta(hours=26)  # la richiesta ammette al massimo 48 ore
  formato = "%Y-%m-%dT%H:%M:%SZ"
  dati, errore = _op_get("fixtures", chiave, {
      "sportId": 10, "from": inizio.strftime(formato), "to": fine.strftime(formato),
      "statusId": 0, "hasOdds": "true",
  })
  if errore:
    return (voce["lista"] if voce else []), errore
  lista = [
      {
          "id": f.get("fixtureId"),
          "p1": [f.get("participant1Name", ""), f.get("participant1ShortName", "")],
          "p2": [f.get("participant2Name", ""), f.get("participant2ShortName", "")],
          "start": f.get("startTime", ""),
      }
      for f in (dati if isinstance(dati, list) else []) if isinstance(f, dict) and f.get("fixtureId")
  ]
  cache = carica_cache_quote()  # ricarica: _op_get ha aggiornato il contatore
  fixtures = cache.setdefault("oddspapi", {}).setdefault("fixtures", {})
  fixtures[giorno_str] = {"ts": time.time(), "lista": lista}
  _pota(fixtures, 5)
  salva_cache_quote(cache)
  return lista, None


def _sim_max(varianti_espn, nomi_altri):
  return max((_somiglianza_varianti(varianti_espn, n) for n in nomi_altri if n), default=0.0)


def trova_fixture_op(match, fixtures):
  """Abbina una partita ESPN a una di OddsPapi. Restituisce (fixture, scambiato)."""
  try:
    inizio = _parse_iso(match["Kickoff"])
  except Exception:
    return None, False
  migliore, punteggio, scambiato = None, 0.0, False
  for fx in fixtures:
    try:
      if abs((_parse_iso(fx["start"]) - inizio).total_seconds()) > 3 * 3600:
        continue
    except Exception:
      continue
    c1 = _sim_max(match.get("NomiCasa", []), fx["p1"])
    o2 = _sim_max(match.get("NomiOspite", []), fx["p2"])
    c2 = _sim_max(match.get("NomiCasa", []), fx["p2"])
    o1 = _sim_max(match.get("NomiOspite", []), fx["p1"])
    dritto, inverso = (min(c1, o2), c1 + o2), (min(c2, o1), c2 + o1)
    (minimo, somma), inv = (inverso, True) if inverso[1] > dritto[1] else (dritto, False)
    if minimo < 0.55:
      continue
    if somma > punteggio:
      migliore, punteggio, scambiato = fx, somma, inv
  return (migliore, scambiato) if punteggio >= 1.3 else (None, False)


def _op_prezzo(mercati, id_mercato, id_esito):
  m = mercati.get(id_mercato)
  if not isinstance(m, dict) or m.get("marketActive") is False:
    return None
  try:
    p = m["outcomes"][id_esito]["players"]["0"]
    if p.get("active") is False:
      return None
    prezzo = float(p["price"])
  except (KeyError, TypeError, ValueError):
    return None
  return prezzo if prezzo > 1 else None


def riassumi_oddspapi(dati, fx):
  """Quote 1X2, Over/Under 2.5 e Goal per bookmaker nel formato usato dal resto del programma."""
  h2h, totals, btts = [], [], []
  for slug, b in (dati.get("bookmakerOdds") or {}).items():
    if not isinstance(b, dict) or b.get("bookmakerIsActive") is False or b.get("suspended"):
      continue
    if any(p in slug.lower() for p in BOOK_ESCLUSI):
      continue
    nome = slug.replace("-", " ").title()
    mk = b.get("markets") or {}
    q1, qx, q2 = _op_prezzo(mk, "101", "101"), _op_prezzo(mk, "101", "102"), _op_prezzo(mk, "101", "103")
    if None not in (q1, qx, q2):
      h2h.append([nome, q1, qx, q2])
    qo, qu = _op_prezzo(mk, "1010", "1010"), _op_prezzo(mk, "1010", "1011")
    if None not in (qo, qu):
      totals.append([nome, qo, qu])
    qs, qn = _op_prezzo(mk, "104", "104"), _op_prezzo(mk, "104", "105")
    if None not in (qs, qn):
      btts.append([nome, qs, qn])
  return {"home": fx["p1"][0], "away": fx["p2"][0], "commence": fx["start"], "h2h": h2h, "totals": totals, "btts": btts}


def _inverti_casa_ospite(ev):
  """Se OddsPapi indica le squadre al contrario rispetto a ESPN, scambia 1 e 2."""
  ev = dict(ev)
  ev["h2h"] = [[b, q2, qx, q1] for b, q1, qx, q2 in ev.get("h2h", [])]
  return ev


def op_quote_fixture(chiave, fx, consenti_rete):
  """Quote di una partita (cache 6 ore). Restituisce (evento_o_None, errore, richiesta_fatta)."""
  cache = carica_cache_quote()
  voce = cache.get("oddspapi", {}).get("eventi", {}).get(fx["id"])
  if voce and time.time() - voce.get("ts", 0) < OP_TTL:
    return voce["ev"], None, False
  if not consenti_rete:
    return None, None, False
  dati, errore = _op_get("odds", chiave, {"fixtureId": fx["id"]})
  if errore or not isinstance(dati, dict):
    return (voce["ev"] if voce else None), (errore or "Risposta di OddsPapi non leggibile."), True
  ev = riassumi_oddspapi(dati, fx)
  cache = carica_cache_quote()
  eventi = cache.setdefault("oddspapi", {}).setdefault("eventi", {})
  eventi[fx["id"]] = {"ts": time.time(), "ev": ev}
  _pota(eventi, 300)
  salva_cache_quote(cache)
  return ev, None, True


def _futura(m, adesso):
  try:
    return _parse_iso(m["Kickoff"]) > adesso
  except Exception:
    return False


def _da_cercare_op(m, adesso, anche_quotate=False):
  """Una partita costa una richiesta: di norma solo se nessun'altra fonte ha quote."""
  if m.get("Fonti") and not anche_quotate:
    return False
  return _futura(m, adesso)


def conta_partite_da_cercare_op(partite, anche_quotate=False):
  adesso = datetime.now(timezone.utc)
  return sum(1 for m in partite if _da_cercare_op(m, adesso, anche_quotate))


def aggancia_oddspapi(partite, chiave, giorno_str, consenti_rete=False, anche_quotate=False):
  """Aggiunge le quote di OddsPapi. Senza consenso di rete usa solo la cache (0 richieste).

  Le partite senza quote vengono cercate (1 richiesta ciascuna); quelle già quotate da un'altra fonte
  ricevono i dati di OddsPapi solo se già in cache, oppure cercandoli se anche_quotate è attivo.
  Restituisce (partite, errori)."""
  adesso = datetime.now(timezone.utc)
  if not any(_futura(m, adesso) for m in partite):
    return partite, []

  errori = []
  fixtures, errore = op_fixtures(chiave, giorno_str, consenti_rete)
  if errore:
    errori.append(errore)
  if not fixtures:
    return partite, errori

  risultato, richieste, limite_raggiunto = [], 0, False
  for m in partite:
    if not _futura(m, adesso):
      risultato.append(m)
      continue
    fx, scambiato = trova_fixture_op(m, fixtures)
    if not fx:
      risultato.append(m)
      continue
    deve_cercare = _da_cercare_op(m, adesso, anche_quotate)
    puo_rete = deve_cercare and consenti_rete and richieste < OP_MAX_RICHIESTE
    ev, errore, fatta = op_quote_fixture(chiave, fx, puo_rete)
    richieste += 1 if fatta else 0
    if deve_cercare and consenti_rete and ev is None and not puo_rete:
      limite_raggiunto = True
    if errore and errore not in errori:
      errori.append(errore)
    m2 = dict(m)
    if ev and (ev.get("h2h") or ev.get("totals") or ev.get("btts")):
      orientato = _inverti_casa_ospite(ev) if scambiato else ev
      m2["Fonti"] = {**m.get("Fonti", {}), "OddsPapi": orientato}
      if not m.get("Mercati"):
        m2.update(costruisci_analisi(m, orientato, "OddsPapi"))
    risultato.append(m2)
    if errore and ("non valida" in errore or "Limite" in errore):
      risultato.extend(partite[len(risultato):])
      break
  if limite_raggiunto:
    errori.append(f"OddsPapi: scaricate {OP_MAX_RICHIESTE} partite (limite per volta). Premi di nuovo il pulsante per le altre.")
  return risultato, errori


# ---------------------------------------------------------------------------
# Unione delle fonti: quote di tutte le fonti attive + modello sui dati storici
# ---------------------------------------------------------------------------
def _unisci_eventi(fonti):
  """Un solo evento con le quote di tutte le fonti: un bookmaker presente in più fonti conta una volta."""
  unito = {"h2h": [], "totals": [], "btts": []}
  visti = {k: set() for k in unito}
  for ev in fonti.values():
    for k in unito:
      for riga in ev.get(k, []):
        nome = re.sub(r"[^a-z0-9]", "", str(riga[0]).lower())
        if nome not in visti[k]:
          visti[k].add(nome)
          unito[k].append(riga)
  return unito


def combina_fonti(partite, dati_gratis):
  """Costruisce i mercati finali di ogni partita con tutte le fonti attive.

  - Più fonti di quote (The Odds API, OddsPapi, quote di football-data): bookmaker uniti e senza doppioni.
  - Con i dati storici attivi: la probabilità è in parte quella del modello sui risultati.
  - Solo dati storici: quote di football-data oppure, se mancano, stima del modello (quota da scrivere)."""
  risultato = []
  for m in partite:
    m2 = dict(m)
    fonti = dict(m.get("Fonti", {}))
    g = dati_gratis.get(m["ID"]) if fg is not None else None
    lam = g.get("lam") if g else None
    if fonti:
      if g and g.get("ev"):
        fonti["football-data"] = g["ev"]
      if len(fonti) >= 2 or lam:
        m2.update(costruisci_analisi(m, _unisci_eventi(fonti), " + ".join(fonti)))
        if lam:
          m2["Mercati"] = fg.mescola_con_modello(m2["Mercati"], lam)
          m2["Motivazione"] += f" Probabilità: {int(fg.PESO_MODELLO * 100)}% modello sui risultati, il resto mercato."
    elif g and (lam or g.get("riga")):
      mercati, descr, solo = fg.mercati_partita(lam, g.get("riga"))
      if mercati:
        m2["Mercati"] = mercati
        m2["SoloModello"] = solo
        m2["Analisi xG"] = fg.xg_testo(lam, solo)
        m2["Motivazione"] = f"[{m['Competizione']}] {descr}. Fonte: {g['fonte']}, nessuna chiave."
    risultato.append(m2)
  return risultato


# ---------------------------------------------------------------------------
# Palinsesto da ESPN
# ---------------------------------------------------------------------------
@st.cache_data(ttl=120, show_spinner=False)
def scarica_tutte_partite(data_str_target):
  """Partite del giorno da ESPN. Restituisce (partite, campionati, tutte_le_richieste_fallite)."""
  partite_trovate = []
  campionati_set = {nome for _, nome in LEGHE_DA_INTERROGARE}

  dt_target_obj = datetime.strptime(data_str_target, "%Y-%m-%d")

  # Giorno stesso, successivo e precedente: ESPN raggruppa per giorno UTC/USA
  date_da_controllare = [
      (dt_target_obj + timedelta(days=d)).strftime("%Y%m%d") for d in (0, 1, -1)
  ]
  richieste = [
      (slug, nome, d) for slug, nome in LEGHE_DA_INTERROGARE for d in date_da_controllare
  ]

  def _scarica(r):
    slug, _, d = r
    return scarica_json(f"{ESPN_BASE}/{slug}/scoreboard?dates={d}")

  # Richieste in parallelo: prima erano sequenziali (fino a ~100 secondi)
  with ThreadPoolExecutor(max_workers=12) as ex:
    risposte = list(ex.map(_scarica, richieste))

  ID_visti = set()
  for (slug, nome_lega_default, _), data in zip(richieste, risposte):
    if not data:
      continue
    league_info = data.get("leagues", [{}])
    comp_name = (
        league_info[0].get("name", nome_lega_default) if league_info else nome_lega_default
    )

    for event in data.get("events", []):
      data_utc_str = event.get("date", "")
      competitions = event.get("competitions", [])
      if not (competitions and data_utc_str):
        continue
      try:
        dt_utc = datetime.fromisoformat(data_utc_str.replace("Z", "+00:00"))
        dt_roma = dt_utc.astimezone(tz_roma)
        dt_match_str = dt_roma.strftime("%Y-%m-%d")
        data_fmt = dt_roma.strftime("%d/%m/%Y")
        ora_fmt = dt_roma.strftime("%H:%M")
      except Exception:
        continue

      if dt_match_str != data_str_target:
        continue
      competitors = competitions[0].get("competitors", [])
      if len(competitors) < 2:
        continue
      home_team = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
      away_team = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
      casa = home_team.get("team", {}).get("shortDisplayName") or home_team.get("team", {}).get("name", "Casa")
      ospite = away_team.get("team", {}).get("shortDisplayName") or away_team.get("team", {}).get("name", "Ospite")

      match_id = f"{data_str_target}_{casa}_{ospite}".replace(" ", "_")
      if match_id in ID_visti:
        continue
      ID_visti.add(match_id)
      campionati_set.add(comp_name)
      partite_trovate.append({
          "ID": match_id,
          "Data": data_fmt,
          "Ora": ora_fmt,
          "Competizione": comp_name,
          "Match": f"{casa} vs {ospite}",
          # Dati tecnici usati per abbinare le quote (non vengono salvati nei ticket)
          "Kickoff": data_utc_str,
          "Lega": slug,
          "NomiCasa": sorted(_nomi_team(home_team) | {casa.lower()}),
          "NomiOspite": sorted(_nomi_team(away_team) | {ospite.lower()}),
      })

  tutte_fallite = all(r is None for r in risposte)
  return partite_trovate, sorted(campionati_set), tutte_fallite


@st.cache_data(ttl=900, show_spinner=False)
def analisi_gratuita(partite, giorno_str):
  """Dati gratuiti (storico + quote di football-data) di tutte le partite coperte.
  Riceve un elenco ridotto di partite; giorno_str serve solo come chiave della cache."""
  return fg.raccogli_dati(partite, CARTELLA_STORICO, datetime.now())


@st.cache_data(ttl=3600, show_spinner=False)
def verifica_gratuita(codice, giorni):
  df, avvisi = fg.carica_storico_campionato(codice, CARTELLA_STORICO, datetime.now())
  if df is None:
    return None, avvisi
  return fg.verifica_storica(df, giorni), avvisi


# ---------------------------------------------------------------------------
# Stato sessione e callback
# ---------------------------------------------------------------------------
if "partite_scelte_globali" not in st.session_state:
  st.session_state.partite_scelte_globali = {}

if "data_corrente" not in st.session_state:
  st.session_state.data_corrente = oggi_date
# Se la sessione resta aperta a lungo la data potrebbe uscire dall'intervallo ammesso
st.session_state.data_corrente = min(max(st.session_state.data_corrente, DATA_MIN), DATA_MAX)

if "archivio_scommesse" not in st.session_state:
  st.session_state.archivio_scommesse = carica_archivio()

if "dati_finanza" not in st.session_state:
  st.session_state.dati_finanza = carica_finanza()


def cb_cambia_giorno(delta):
  nuova = st.session_state.data_corrente + timedelta(days=delta)
  st.session_state.data_corrente = min(max(nuova, DATA_MIN), DATA_MAX)


SIGLE_MERCATI = {
    "1 (Vittoria Casa)": "1", "2 (Vittoria Ospite)": "2", "Over 2.5": "Over 2.5",
    "Under 2.5": "Under 2.5", "Goal (Entrambe Segnano)": "Goal",
}


def sigla_mercato(nome):
  return SIGLE_MERCATI.get(nome, nome)


def nome_esito(consiglio, match_str, lunghezza=16):
  """Nome leggibile dell'esito: '1' diventa 'Troyes', '2' diventa 'Le Havre AC', Goal diventa 'Entrambe segnano'."""
  casa, _, ospite = match_str.partition(" vs ")
  sigla = sigla_mercato(consiglio)
  if sigla == "1" and casa:
    return casa[:lunghezza]
  if sigla == "2" and ospite:
    return ospite[:lunghezza]
  if sigla == "Goal":
    return "Goal (segnano entrambe)"
  return sigla


def riga_da_mercato(match, mercato):
  """Riga della schedina per il mercato scelto (stesso formato di applica_pronostico)."""
  riga = {k: v for k, v in match.items() if k not in ("Mercati", "Fonti")}
  riga.update({
      "Consiglio": mercato["Consiglio"],
      "Quota": mercato["Quota"],
      "ValoreProb": mercato["ValoreProb"],
      "EV": mercato["EV"],
      "Bookmaker": mercato.get("Bookmaker", "n/d"),
      "ValueBet": bool(mercato["EV"] > SOGLIA_VALUE_BET and not match.get("SoloModello")),
  })
  return riga


def cb_tocca(match_id, consiglio):
  """Tocco su una quota: aggiunge l'esito alla schedina; ritocco = lo toglie; altro esito = lo cambia."""
  scelte = st.session_state.partite_scelte_globali
  st.session_state.pop(f"edit_quota_{match_id}", None)
  if scelte.get(match_id, {}).get("Consiglio") == consiglio:
    scelte.pop(match_id, None)
    return
  match = st.session_state.get("_partite_visibili", {}).get(match_id)
  if match is None:
    return
  for mercato in match.get("Mercati", []):
    if mercato["Consiglio"] == consiglio:
      scelte[match_id] = riga_da_mercato(match, mercato)
      return


def giudizio(ev, stima=False):
  """Etichetta semplice sul valore atteso: (testo, classe colore)."""
  if stima:
    return "Quota da verificare", "warn"
  if ev > SOGLIA_VALUE_BET:
    return "Conviene", "value"
  if ev >= -0.05:
    return "Alla pari", "muted"
  return "Poco conveniente", "bad"


def quota_effettiva(match_id, riga):
  """Quota in uso: quella scritta dall'utente nella schedina, altrimenti quella della partita."""
  try:
    return max(1.01, round(float(st.session_state.get(f"edit_quota_{match_id}", riga["Quota"])), 2))
  except (TypeError, ValueError):
    return max(1.01, float(riga["Quota"]))


def riepilogo_schedina(scelte, importo):
  """Quota totale, probabilità di vincere (partite indipendenti), valore atteso e importi."""
  quota, prob, stima = 1.0, 1.0, False
  for mid, riga in scelte.items():
    q = quota_effettiva(mid, riga)
    quota *= q
    prob *= riga["ValoreProb"] / 100.0
    if riga.get("SoloModello") and abs(q - float(riga["Quota"])) < 1e-9:
      stima = True
  return {
      "n": len(scelte), "quota": quota, "prob": prob, "ev": quota * prob - 1.0, "stima": stima,
      "vincita": importo * quota, "guadagno": importo * (quota - 1.0),
  }


def distribuzione_corrette(probabilita):
  """Probabilità di azzeccare esattamente 0, 1, ..., n esiti (partite indipendenti)."""
  dist = [1.0]
  for p in probabilita:
    nuova = [0.0] * (len(dist) + 1)
    for k, v in enumerate(dist):
      nuova[k] += v * (1.0 - p)
      nuova[k + 1] += v * p
    dist = nuova
  return dist


def cb_svuota_carrello():
  st.session_state.partite_scelte_globali = {}
  for k in list(st.session_state.keys()):
    if k.startswith("pick_") or k.startswith("edit_quota_"):
      del st.session_state[k]


def cb_rimuovi_dal_carrello(match_id):
  st.session_state.partite_scelte_globali.pop(match_id, None)
  st.session_state.pop(f"edit_quota_{match_id}", None)


def cb_suggerisci():
  st.session_state["suggerisci_n"] = int(st.session_state.get("n_sugg", 3))


def cb_salva_schedina():
  scelte = st.session_state.partite_scelte_globali
  if not scelte:
    return
  partite, quota_totale = [], 1.0
  for mid, m in scelte.items():
    q = max(1.01, float(st.session_state.get(f"edit_quota_{mid}", m["Quota"])))
    quota_totale *= round(q, 2)
    p = {k: v for k, v in m.items() if k not in CAMPI_TECNICI}
    p["Quota"] = round(q, 2)
    partite.append(p)
  importo = float(st.session_state.get("importo_schedina", 10.0))
  nuova = {
      "id_schedina": f"schedina_{datetime.now(tz_roma).strftime('%Y%m%d_%H%M%S')}",
      "data_salvataggio": datetime.now(tz_roma).strftime("%d/%m/%Y %H:%M"),
      "partite": partite,
      "quota_totale": round(quota_totale, 2),
      "importo_giocato": importo,
      "vincita_potenziale": round(importo * quota_totale, 2),
      "stato_manuale": None,
      "concluso": False,
  }
  salva_archivio([nuova] + st.session_state.archivio_scommesse)
  cb_svuota_carrello()
  st.session_state.msg_schedina = "Schedina salvata nell'archivio."


def cb_imposta_stato(idx, stato):
  archivio = st.session_state.archivio_scommesse
  if 0 <= idx < len(archivio):
    archivio[idx]["stato_manuale"] = stato
    archivio[idx]["concluso"] = stato in ("vinto", "perso")
    salva_archivio(archivio)


def cb_elimina_ticket(idx):
  archivio = st.session_state.archivio_scommesse
  if 0 <= idx < len(archivio):
    archivio.pop(idx)
    salva_archivio(archivio)


def cb_forza_quote():
  st.session_state.forza_quote = True


def cb_salva_chiave():
  chiave = str(st.session_state.get("input_chiave_api", "")).strip()
  if chiave:
    salva_chiave("odds_api_key", chiave)
    st.session_state.input_chiave_api = ""
    st.session_state.forza_quote = True


def cb_salva_chiave_op():
  chiave = str(st.session_state.get("input_chiave_op", "")).strip()
  if chiave:
    salva_chiave("oddspapi_key", chiave)
    st.session_state.input_chiave_op = ""


def cb_interruttori():
  salva_interruttori({k: st.session_state.get(k, v) for k, v in INTERRUTTORI.items()})


def cb_scarica_op():
  st.session_state.scarica_op = True


def cb_rimuovi_movimento(i):
  movimenti = st.session_state.dati_finanza.get("movimenti", [])
  if 0 <= i < len(movimenti):
    movimenti.pop(i)
    salva_finanza(st.session_state.dati_finanza)


# ---------------------------------------------------------------------------
# Interfaccia
# ---------------------------------------------------------------------------
def scheda_kpi(etichetta, valore, nota="", tono=""):
  """Riquadro riassuntivo sobrio (usato nel Bilancio)."""
  nota_html = f'<div class="kpi-n">{nota}</div>' if nota else ""
  classe = f"kpi kpi-{tono}" if tono else "kpi"
  return (f'<div class="{classe}"><div class="kpi-l">{escape(etichetta)}</div>'
          f'<div class="kpi-v">{valore}</div>{nota_html}</div>')


st.markdown(
    '<div class="app-title">Pronostici &amp; Schedine</div>'
    '<div class="app-sub">Scegli le partite, prova le combinazioni e controlla subito quota, probabilità e vincita.</div>',
    unsafe_allow_html=True,
)

st.sidebar.markdown("#### :material/tune: Filtri")
st.sidebar.caption("Giorno")

c1, c2, c3 = st.sidebar.columns([0.22, 0.56, 0.22], gap="small")

with c1:
  st.button("‹", key="btn_ieri", width="stretch", on_click=cb_cambia_giorno, args=(-1,))

with c2:
  data_selezionata = c2.date_input(
      "Giorno",
      value=st.session_state.data_corrente,
      min_value=DATA_MIN,
      max_value=DATA_MAX,
      label_visibility="collapsed",
  )
  if data_selezionata != st.session_state.data_corrente:
    st.session_state.data_corrente = data_selezionata
    st.rerun()

with c3:
  st.button("›", key="btn_domani", width="stretch", on_click=cb_cambia_giorno, args=(1,))

data_selezionata_str = st.session_state.data_corrente.strftime("%Y-%m-%d")
data_display = st.session_state.data_corrente.strftime("%d/%m/%Y")

chiave_api, origine_chiave = leggi_chiave("ODDS_API_KEY", "odds_api_key")
chiave_op, origine_op = leggi_chiave("ODDSPAPI_KEY", "oddspapi_key")
# Interruttori delle fonti: se spenti non viene fatta nessuna richiesta (e non si consumano crediti)
if "interruttori_caricati" not in st.session_state:
  for k, v in leggi_interruttori().items():
    st.session_state[k] = v
  st.session_state["interruttori_caricati"] = True
usa_oddsapi = bool(chiave_api) and st.session_state.get("usa_oddsapi", True)
usa_oddspapi = bool(chiave_op) and st.session_state.get("usa_oddspapi", True)
usa_gratis = fg is not None and st.session_state.get("usa_gratis", True)
op_anche_quotate = st.session_state.get("op_anche_quotate", False)

with st.spinner(f"Ricerca partite e quote in corso per il {data_display}..."):
  partite_base, lista_tornei, rete_ko = scarica_tutte_partite(data_selezionata_str)
  forza_quote = st.session_state.pop("forza_quote", False)
  scarica_op = st.session_state.pop("scarica_op", False)
  lista_grezza, errori_quote = aggancia_quote(partite_base, chiave_api if usa_oddsapi else "", forza_quote)
  if usa_oddspapi:
    # Senza il pulsante usa solo quanto già scaricato (0 richieste)
    lista_grezza, errori_op = aggancia_oddspapi(lista_grezza, chiave_op, data_selezionata_str,
                                                consenti_rete=scarica_op, anche_quotate=op_anche_quotate)
    errori_quote = errori_quote + errori_op
  dati_gratis, avvisi_gratis = {}, []
  if usa_gratis:
    elenco_ridotto = [{k: m[k] for k in ("ID", "Lega", "Kickoff", "NomiCasa", "NomiOspite", "Competizione")} for m in lista_grezza]
    dati_gratis, avvisi_gratis = analisi_gratuita(elenco_ridotto, data_selezionata_str)
  lista_grezza = combina_fonti(lista_grezza, dati_gratis)

campionato_selezionato = st.sidebar.selectbox("Campionato", ["Tutti i campionati"] + lista_tornei)
soglia_prob_min = st.sidebar.slider(
    "Probabilità minima (%)", min_value=0, max_value=85, value=0, step=5,
    help="Nasconde le partite in cui nessun esito arriva a questa probabilità.",
)
criterio_ordinamento = st.sidebar.selectbox("Ordina per", ["Probabilità (%)", "Valore Atteso (EV)"])

with st.sidebar.expander(":material/database: Fonti dati", expanded=not (usa_oddsapi or usa_oddspapi or usa_gratis)):
  st.markdown("**The Odds API**")
  st.toggle("Attiva (consuma crediti)", key="usa_oddsapi", on_change=cb_interruttori,
            disabled=not chiave_api, help="Spento: nessuna richiesta, nessun credito consumato.")
  if chiave_api:
    st.caption(f"Chiave configurata ({origine_chiave}).")
    rimasti = carica_cache_quote().get("crediti_rimasti")
    if rimasti is not None:
      st.caption(f"Crediti rimasti questo mese: **{rimasti}**")
    st.button("Aggiorna quote ora", key="btn_forza_quote", icon=":material/refresh:",
              width="stretch", on_click=cb_forza_quote, disabled=not usa_oddsapi,
              help="Usa crediti: 2 per competizione. Le quote restano valide 3 ore.")
  else:
    st.caption("Piano gratuito con 500 crediti al mese su the-odds-api.com: la chiave arriva via email.")
  st.text_input("Chiave The Odds API", type="password", key="input_chiave_api",
                placeholder="Incolla la chiave e premi Salva")
  st.button("Salva chiave", key="btn_salva_chiave", icon=":material/key:", width="stretch", on_click=cb_salva_chiave)

  st.divider()
  st.markdown("**OddsPapi**")
  st.toggle("Attiva (consuma richieste)", key="usa_oddspapi", on_change=cb_interruttori,
            disabled=not chiave_op, help="Spento: nessuna richiesta e nessun dato di OddsPapi usato.")
  st.checkbox("Cerca anche le partite già quotate", key="op_anche_quotate", disabled=not usa_oddspapi,
              help="Di norma OddsPapi serve solo per le partite senza quote, per risparmiare le 250 richieste mensili. "
                   "Attivandolo ogni partita costa una richiesta e le quote vengono unite a quelle delle altre fonti.")
  if chiave_op:
    st.caption(f"Chiave configurata ({origine_op}). Richieste usate questo mese: **{richieste_oddspapi_usate()} / 250**")
  else:
    st.caption("Facoltativa: oddspapi.io, piano gratuito con 250 richieste al mese. Aggiunge il mercato Goal.")
  st.text_input("Chiave OddsPapi", type="password", key="input_chiave_op",
                placeholder="Incolla la chiave e premi Salva")
  st.button("Salva chiave", key="btn_salva_chiave_op", icon=":material/key:", width="stretch", on_click=cb_salva_chiave_op)

  st.divider()
  st.markdown("**Dati gratuiti**")
  if fg is None:
    st.caption("File `fonte_gratuita.py` non trovato accanto ad app.py: fonte disattivata.")
  else:
    st.toggle("Attiva (senza chiavi)", key="usa_gratis", on_change=cb_interruttori,
              help="Gratis. Spento: i dati storici non vengono né scaricati né usati.")
    st.caption(
        "Storico e quote di football-data.co.uk (Serie A e B, Premier, LaLiga, Bundesliga, Ligue 1) "
        "e risultati delle nazionali. Con altre fonti attive le quote si uniscono e la probabilità tiene conto del modello. "
        "Per le nazionali non esistono quote gratuite: la quota mostrata è una stima da sostituire."
    )
    lega_ver = st.selectbox("Verifica statistica su", list(FD_NOMI_VERIFICA), key="lega_verifica")
    if st.button("Verifica il modello", key="btn_verifica", icon=":material/insights:", width="stretch"):
      st.session_state["verifica_in_corso"] = FD_NOMI_VERIFICA[lega_ver]

lista_finale = []
partite_senza_quote = []
partite_visibili = {}
num_sotto_soglia = 0
for m in lista_grezza:
  if campionato_selezionato != "Tutti i campionati" and m["Competizione"] != campionato_selezionato:
    continue
  if not m["Mercati"]:
    partite_senza_quote.append(m)
    continue
  riga = applica_pronostico(m, soglia_prob_min)
  if riga:
    lista_finale.append(riga)
    partite_visibili[m["ID"]] = m
  else:
    num_sotto_soglia += 1
st.session_state["_partite_visibili"] = partite_visibili

if criterio_ordinamento == "Valore Atteso (EV)":
  lista_finale.sort(key=lambda x: x["EV"], reverse=True)
else:
  lista_finale.sort(key=lambda x: x["ValoreProb"], reverse=True)

# "Suggeriscimi una schedina": parte dal pulsante del pannello, prima di disegnare i selettori
n_suggerite = st.session_state.pop("suggerisci_n", None)
if n_suggerite and lista_finale:
  cb_svuota_carrello()
  for riga in sorted(lista_finale, key=lambda x: (x["EV"], x["ValoreProb"]), reverse=True)[:n_suggerite]:
    st.session_state.partite_scelte_globali[riga["ID"]] = riga

num_in_attesa = sum(1 for s in st.session_state.archivio_scommesse if not e_concluso(s))
n_scelte = len(st.session_state.partite_scelte_globali)

tab_partite, tab_schedina, tab_archivio, tab_bilancio = st.tabs([
    ":material/sports_soccer: 1 · Partite",
    f":material/receipt_long: 2 · La mia schedina ({n_scelte})",
    f":material/folder_open: Archivio ({num_in_attesa})",
    ":material/account_balance_wallet: Bilancio",
])

ORDINE_MERCATI = ["1 (Vittoria Casa)", "2 (Vittoria Ospite)", "Over 2.5", "Under 2.5", "Goal (Entrambe Segnano)"]
INTESTAZIONI = ["1", "2", "Over 2.5", "Under 2.5", "Goal"]
LARGHEZZE = [0.31, 0.105, 0.105, 0.105, 0.105, 0.105, 0.17]

# --------------------------------- PARTITE ---------------------------------
with tab_partite:
  st.markdown(
      '<div class="steps">'
      '<div class="step"><b>1</b>Scegli: tocca le <strong>quote</strong> degli esiti che vuoi giocare.</div>'
      '<div class="step"><b>2</b>Controlla: nella scheda <strong>La mia schedina</strong> vedi vincita, perdita e probabilità.</div>'
      '<div class="step"><b>3</b>Salva: la schedina va in <strong>Archivio</strong> e la segui fino alla fine.</div>'
      '</div>',
      unsafe_allow_html=True,
  )
  barra_a, barra_b = st.columns([0.74, 0.26], vertical_alignment="center")
  attive = [nome for nome, acceso in (("The Odds API", usa_oddsapi), ("OddsPapi", usa_oddspapi), ("dati gratuiti", usa_gratis)) if acceso]
  if attive:
    barra_a.caption("Fonti attive: " + ", ".join(attive) + (" · quote unite per un risultato più affidabile" if len(attive) > 1 else ""))
  else:
    barra_a.caption("Nessuna fonte attiva")
  if barra_b.button("Aggiorna", icon=":material/refresh:", width="stretch", key="btn_aggiorna"):
    st.cache_data.clear()
    st.rerun()

  if rete_ko:
    st.warning("Impossibile contattare ESPN (nessuna risposta). Controlla la connessione e premi Aggiorna.")
  if not attive:
    st.info("Accendi almeno una fonte nel riquadro «Fonti dati» della barra laterale: senza quote le partite non possono essere valutate.")
  for errore in errori_quote:
    st.warning(f"Quote: {errore}")
  for avviso in avvisi_gratis:
    st.caption(f"Dati gratuiti: {avviso}")
  if any(r.get("SoloModello") for r in lista_finale):
    st.caption("Le quote con ~ sono stimate dal modello (nessun bookmaker le fornisce): nella schedina puoi scrivere quella vera.")

  codice_ver = st.session_state.get("verifica_in_corso")
  if codice_ver and fg is not None:
    with st.spinner("Verifica statistica in corso..."):
      esito_ver, avvisi_ver = verifica_gratuita(codice_ver, 60)
    with st.container(border=True):
      st.markdown(f"**Verifica del modello su {[k for k, v in FD_NOMI_VERIFICA.items() if v == codice_ver][0]}**")
      if esito_ver is None:
        st.info("Dati insufficienti per la verifica (servono almeno ~100 partite di addestramento e 20 di prova)."
                + (f" Dettagli: {'; '.join(avvisi_ver)}" if avvisi_ver else ""))
      else:
        st.caption(f"Il modello impara dalle {esito_ver['partite_addestramento']} partite precedenti agli ultimi 60 giorni "
                   f"e viene provato sulle {esito_ver['partite_test']} partite successive, che non ha mai visto.")
        tabella = pd.DataFrame([{
            "Peso del modello": f"{e['peso_modello'] * 100:.0f}%" + (" (solo mercato)" if e["peso_modello"] == 0 else " (solo modello)" if e["peso_modello"] == 1 else ""),
            "Errore (più basso = meglio)": round(e["errore"], 4),
            "Giocate con EV>3%": e["giocate"],
            "Esito (puntata fissa 1)": "n/d" if e["roi"] is None else f"{e['roi'] * 100:+.1f}%",
        } for e in esito_ver["esiti"]])
        st.dataframe(tabella, hide_index=True, width="stretch")
        migliore = min(esito_ver["esiti"], key=lambda e: e["errore"])
        st.caption(
            f"Previsioni migliori con peso del modello al {migliore['peso_modello'] * 100:.0f}%. "
            "Con poche decine di giocate l'esito in euro dipende molto dalla fortuna: guarda soprattutto la colonna dell'errore. "
            "Le quote usate per le giocate sono le migliori del mercato, quindi l'esito è più ottimistico di quanto si ottiene in pratica."
        )
      if st.button("Chiudi verifica", key="btn_chiudi_verifica"):
        st.session_state.pop("verifica_in_corso", None)
        st.rerun()

  if usa_oddspapi:
    visibili = [m for m in lista_grezza
                if campionato_selezionato == "Tutti i campionati" or m["Competizione"] == campionato_selezionato]
    n_da_cercare = conta_partite_da_cercare_op(visibili, op_anche_quotate)
    if n_da_cercare:
      st.button(
          f"Cerca su OddsPapi le quote di {n_da_cercare} partite" + ("" if op_anche_quotate else " senza quote")
          + f" (circa {min(n_da_cercare, OP_MAX_RICHIESTE) + 1} richieste)",
          key="btn_scarica_op", icon=":material/cloud_download:", width="stretch", on_click=cb_scarica_op,
      )


  # --- riepilogo sempre visibile della schedina in costruzione
  scelte_ora = st.session_state.partite_scelte_globali
  if scelte_ora:
    puntata_ora = float(st.session_state.get("importo_schedina", 10.0))
    r = riepilogo_schedina(scelte_ora, puntata_ora)
    etich, tono = giudizio(r["ev"], r["stima"])
    z = st.columns(5, vertical_alignment="center")
    z[0].markdown(scheda_kpi("Esiti scelti", str(r["n"]), "apri «La mia schedina» per i dettagli"), unsafe_allow_html=True)
    z[1].markdown(scheda_kpi("Quota totale", f"{r['quota']:.2f}"), unsafe_allow_html=True)
    z[2].markdown(scheda_kpi("Probabilità di vincere", f"{r['prob'] * 100:.1f}%"), unsafe_allow_html=True)
    z[3].markdown(scheda_kpi(f"Vincita con € {puntata_ora:.0f}", f"€ {r['vincita']:.2f}", f"guadagno netto € {r['guadagno']:.2f}"),
                  unsafe_allow_html=True)
    z[4].markdown(f'<div style="text-align:center"><span class="tag tag-{tono}" style="font-size:0.85rem">{etich}</span></div>',
                  unsafe_allow_html=True)
    st.write("")

  # --- le occasioni migliori del giorno
  migliori = [x for x in lista_finale if not x.get("SoloModello") and x["EV"] > SOGLIA_VALUE_BET]
  migliori = sorted(migliori, key=lambda x: x["EV"], reverse=True)[:3]
  with st.container(border=True):
    st.markdown("**Le occasioni migliori di oggi**")
    st.caption("Sono gli esiti con la quota più alta rispetto alla probabilità stimata: nel lungo periodo sono quelli che rendono di più.")
    if migliori:
      cm = st.columns(len(migliori))
      for col, x in zip(cm, migliori):
        gia = st.session_state.partite_scelte_globali.get(x["ID"], {}).get("Consiglio") == x["Consiglio"]
        with col:
          st.markdown(
              f'<div class="r-time">{escape(x["Ora"])} · {escape(x["Competizione"])}</div>'
              f'<div class="r-teams">{escape(x["Match"])}</div>'
              f'<div class="plab">{escape(nome_esito(x["Consiglio"], x["Match"], 22))} · quota <b>{x["Quota"]:.2f}</b> · '
              f'probabilità {x["ValoreProb"]:.0f}% · vantaggio {x["EV"] * 100:+.0f}%</div>',
              unsafe_allow_html=True,
          )
          st.button("Nella schedina" if gia else "Aggiungi", key=f"top_{x['ID']}", width="stretch",
                    icon=":material/check:" if gia else ":material/add:", type="primary" if gia else "secondary",
                    on_click=cb_tocca, args=(x["ID"], x["Consiglio"]))
    else:
      st.caption("Con le fonti attive nessun esito supera la soglia di convenienza: oggi non c'è niente di davvero vantaggioso.")
    s1, s2, s3 = st.columns([0.25, 0.35, 0.4], vertical_alignment="bottom")
    s1.number_input("Quante partite", min_value=1, max_value=10, value=3, step=1, key="n_sugg")
    s2.button("Suggeriscimi una schedina", icon=":material/lightbulb:", width="stretch", on_click=cb_suggerisci,
              disabled=not lista_finale, help="Sostituisce la schedina con gli esiti dal valore atteso più alto.")

  # --- elenco partite in stile quote
  if lista_finale:
    st.markdown(f"##### {len(lista_finale)} partite · {data_display}")
    with st.expander("Come si leggono le quote"):
      st.markdown(
          "- **1** = vince la squadra di casa · **2** = vince la squadra ospite\n"
          "- **Over 2.5** = si segnano almeno 3 gol · **Under 2.5** = al massimo 2 gol\n"
          "- **Goal** = segnano entrambe le squadre\n"
          "- Il numero sul pulsante è la **quota**: puntando € 10 a quota 2.00 incassi € 20. Sotto trovi la **probabilità** stimata.\n"
          "- La barretta sotto le squadre mostra le probabilità di vittoria casa (blu), pareggio (grigio) e ospite (ocra).\n"
          "- Il giudizio a destra confronta quota e probabilità: **Conviene** se la quota paga più di quanto il rischio meriti."
      )
    if num_sotto_soglia:
      st.caption(f"{num_sotto_soglia} partite nascoste: nessun esito supera la probabilità minima impostata.")

    testata = st.columns(LARGHEZZE)
    testata[0].markdown('<div class="th th-l">Partita</div>', unsafe_allow_html=True)
    for col, nome in zip(testata[1:6], INTESTAZIONI):
      col.markdown(f'<div class="th">{nome}</div>', unsafe_allow_html=True)
    testata[6].markdown('<div class="th">Giudizio</div>', unsafe_allow_html=True)

    for match in lista_finale:
      mid = match["ID"]
      per_nome = {x["Consiglio"]: x for x in partite_visibili[mid]["Mercati"]}
      solo = bool(match.get("SoloModello"))
      scelta = st.session_state.partite_scelte_globali.get(mid, {}).get("Consiglio")

      casa, _, ospite = match["Match"].partition(" vs ")
      p1 = per_nome.get("1 (Vittoria Casa)", {}).get("ValoreProb")
      p2 = per_nome.get("2 (Vittoria Ospite)", {}).get("ValoreProb")
      barra = ""
      if p1 is not None and p2 is not None:
        px_ = max(0.0, 100.0 - p1 - p2)
        barra = (f'<div class="pbar"><i style="width:{p1:.1f}%;background:#4A6FA5"></i>'
                 f'<i style="width:{px_:.1f}%;background:#CBD5E1"></i><i style="width:{p2:.1f}%;background:#C8A27A"></i></div>'
                 f'<div class="plab">{p1:.0f}% · {px_:.0f}% · {p2:.0f}%</div>')
      info = (f'<div class="r-time"><b>{escape(match["Ora"])}</b> · {escape(match["Competizione"])}</div>'
              f'<div class="r-teams">{escape(casa)}<span>vs</span>{escape(ospite)}</div>{barra}')

      righe = st.columns(LARGHEZZE, vertical_alignment="center")
      righe[0].markdown(info, unsafe_allow_html=True)
      for i, (col, nome) in enumerate(zip(righe[1:6], ORDINE_MERCATI)):
        x = per_nome.get(nome)
        if x is None:
          col.markdown('<div class="plab c">–</div>', unsafe_allow_html=True)
          continue
        col.button(f"{'~' if solo else ''}{x['Quota']:.2f}", key=f"q_{mid}_{i}", width="stretch",
                   type="primary" if scelta == nome else "secondary", on_click=cb_tocca, args=(mid, nome),
                   help=f"{nome_esito(nome, match['Match'], 30)}: quota {x['Quota']:.2f}, probabilità {x['ValoreProb']:.0f}%")
        col.markdown(f'<div class="plab c">{x["ValoreProb"]:.0f}%</div>', unsafe_allow_html=True)
      etich, tono = giudizio(match["EV"], solo)
      righe[6].markdown(
          f'<span class="tag tag-{tono}">{etich}</span>'
          f'<div class="plab">Meglio: {escape(nome_esito(match["Consiglio"], match["Match"], 14))}</div>',
          unsafe_allow_html=True,
      )
      with righe[0].expander("Perché", expanded=False):
        st.caption(match.get("Analisi xG", ""))
        st.caption(match.get("Motivazione", ""))
      st.markdown('<hr class="rg">', unsafe_allow_html=True)

  if not lista_finale:
    st.info(f"Nessuna partita con quote o stime per il {data_display} con i filtri scelti.")
  if partite_senza_quote:
    with st.expander(f"Partite senza quote né stime ({len(partite_senza_quote)})"):
      for m in partite_senza_quote:
        st.write(f"{m['Ora']} · {m['Match']} ({m['Competizione']})")

# ----------------------------- LA MIA SCHEDINA -----------------------------
with tab_schedina:
  msg_schedina = st.session_state.pop("msg_schedina", None)
  if msg_schedina:
    st.success(msg_schedina)
  scelte = st.session_state.partite_scelte_globali

  if not scelte:
    st.markdown(
        '<div class="vuoto"><b>La schedina è vuota.</b><br>'
        'Vai nella scheda <b>1 · Partite</b> e tocca una quota (per esempio <b>1</b> per la vittoria della squadra di casa): '
        'comparirà qui con quanto puoi vincere, quanto rischi e con quale probabilità.<br>'
        'Se non sai da dove partire, usa <b>Suggeriscimi una schedina</b>.</div>',
        unsafe_allow_html=True,
    )
  else:
    col_sx, col_dx = st.columns([0.52, 0.48], gap="large")

    with col_sx:
      st.markdown("##### 1. Le tue scelte")
      st.caption("Puoi correggere la quota con quella reale del bookmaker: tutti i calcoli si aggiornano.")
      for mid, m in list(scelte.items()):
        q_uso = quota_effettiva(mid, m)
        stima_leg = bool(m.get("SoloModello")) and abs(q_uso - float(m["Quota"])) < 1e-9
        etich, tono = giudizio(q_uso * m["ValoreProb"] / 100.0 - 1.0, stima_leg)
        with st.container(border=True):
          ca, cb_, cc = st.columns([0.5, 0.3, 0.2], vertical_alignment="center")
          ca.markdown(
              f'<div class="sl-match">{escape(m["Match"])}</div>'
              f'<div class="sl-meta">{escape(m["Ora"])} · {escape(m["Competizione"])}</div>'
              f'<span class="tag tag-pick">{escape(nome_esito(m["Consiglio"], m["Match"], 18))}</span> '
              f'<span class="tag tag-{tono}">{etich}</span>'
              f'<div class="plab">Probabilità {m["ValoreProb"]:.0f}%</div>',
              unsafe_allow_html=True,
          )
          cb_.number_input("Quota", min_value=1.01, max_value=500.0, value=max(1.01, float(m["Quota"])), step=0.05,
                           format="%.2f", key=f"edit_quota_{mid}")
          cc.button("Togli", key=f"del_cart_{mid}", icon=":material/close:", width="stretch",
                    on_click=cb_rimuovi_dal_carrello, args=(mid,))

      importo_giocato = st.number_input("Puntata (€)", min_value=1.0, max_value=10000.0, value=10.0, step=5.0,
                                        key="importo_schedina")
      b1, b2 = st.columns(2)
      b1.button("Salva in archivio", type="primary", icon=":material/save:", width="stretch", on_click=cb_salva_schedina)
      b2.button("Svuota", icon=":material/delete:", width="stretch", on_click=cb_svuota_carrello)

    r = riepilogo_schedina(scelte, importo_giocato)
    etich_tot, tono_tot = giudizio(r["ev"], r["stima"])

    with col_dx:
      st.markdown("##### 2. Conviene?")
      if tono_tot == "warn":
        titolo = "Quote da verificare"
        testo = "Alcune quote sono stime del modello, non quote reali: scrivi quelle vere del bookmaker per avere un giudizio affidabile."
      else:
        titolo = {"value": "Conviene giocarla", "muted": "Alla pari", "bad": "Poco conveniente"}[tono_tot]
        media = r["ev"] * importo_giocato * 100
        testo = (f"Se giocassi questa schedina 100 volte da € {importo_giocato:.0f}, in media "
                 f"{'guadagneresti' if media >= 0 else 'perderesti'} circa <b>€ {abs(media):.0f}</b>. "
                 f"Ogni singola volta, però, o vinci o perdi tutto.")
      st.markdown(f'<div class="giudizio giudizio-{tono_tot}"><div class="g-t">{titolo}</div><div class="g-d">{testo}</div></div>',
                  unsafe_allow_html=True)

      k1, k2 = st.columns(2)
      k1.markdown(scheda_kpi("Se vinci", f"+ € {r['guadagno']:.2f}", f"incassi € {r['vincita']:.2f}", "pos"), unsafe_allow_html=True)
      k2.markdown(scheda_kpi("Se perdi", f"− € {importo_giocato:.2f}", "la puntata", "neg"), unsafe_allow_html=True)
      st.write("")
      k3, k4 = st.columns(2)
      k3.markdown(scheda_kpi("Probabilità di vincere", f"{r['prob'] * 100:.1f}%",
                             f"1 volta su {1 / r['prob']:.0f}" if r["prob"] > 0 else ""), unsafe_allow_html=True)
      k4.markdown(scheda_kpi("Quota totale", f"{r['quota']:.2f}", f"valore atteso {r['ev'] * 100:+.0f}%"), unsafe_allow_html=True)
      st.caption("Calcolo con le partite considerate indipendenti. La probabilità è una stima del modello, non una certezza.")

      if r["n"] >= 2:
        peggiore = None
        for mid, m in scelte.items():
          q_m = quota_effettiva(mid, m)
          ev_senza = (r["quota"] / q_m) * (r["prob"] / (m["ValoreProb"] / 100.0)) - 1.0 if m["ValoreProb"] > 0 else None
          if ev_senza is not None and (peggiore is None or ev_senza > peggiore[1]):
            peggiore = (m, ev_senza)
        if peggiore and peggiore[1] > r["ev"] + 0.01:
          st.info(f"Cosa pesa di più: «{peggiore[0]['Match']}» ({nome_esito(peggiore[0]['Consiglio'], peggiore[0]['Match'], 18)}). "
                  f"Senza questa scelta il valore atteso passerebbe da {r['ev'] * 100:+.0f}% a {peggiore[1] * 100:+.0f}%.")

    # ------------------------------- grafici -------------------------------
    st.markdown("##### 3. Cosa può succedere")
    g1, g2 = st.columns(2, gap="large")
    stile = dict(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                 margin=dict(l=10, r=10, t=40, b=10), height=300, font=dict(size=13))
    VERDE, ROSSO, BLU, GRIGIO = "#5B9A7B", "#C77D75", "#4A6FA5", "#C3CCD9"

    with g1:
      fig1 = go.Figure(go.Bar(
          x=["Se vinci", "Se perdi"], y=[r["guadagno"], -importo_giocato], marker_color=[VERDE, ROSSO],
          text=[f"+ € {r['guadagno']:.2f}<br>{r['prob'] * 100:.1f}% di probabilità",
                f"− € {importo_giocato:.2f}<br>{(1 - r['prob']) * 100:.1f}% di probabilità"],
          textposition="outside", cliponaxis=False,
      ))
      fig1.update_layout(title="Guadagno o perdita (€)", showlegend=False, yaxis=dict(zeroline=True, showgrid=False, visible=False), **stile)
      st.plotly_chart(fig1)

    with g2:
      dist = distribuzione_corrette([m["ValoreProb"] / 100.0 for m in scelte.values()])
      n_es = len(dist) - 1
      fig2 = go.Figure(go.Bar(
          x=[f"{k} su {n_es}" for k in range(n_es + 1)], y=[d * 100 for d in dist],
          marker_color=[VERDE if k == n_es else GRIGIO for k in range(n_es + 1)],
          text=[f"{d * 100:.0f}%" for d in dist], textposition="outside", cliponaxis=False,
      ))
      fig2.update_layout(title="Quanti esiti azzeccherai (vinci solo se tutti)", showlegend=False,
                         yaxis=dict(visible=False, range=[0, max(dist) * 135]), **stile)
      st.plotly_chart(fig2)

    etichette = [f"{nome_esito(m['Consiglio'], m['Match'], 14)} ({m['Match'].partition(' vs ')[0][:10]})" for m in scelte.values()]
    fig3 = go.Figure()
    fig3.add_bar(y=etichette, x=[m["ValoreProb"] for m in scelte.values()], orientation="h", name="Probabilità secondo il modello",
                 marker_color=BLU, text=[f"{m['ValoreProb']:.0f}%" for m in scelte.values()], textposition="outside")
    fig3.add_bar(y=etichette, x=[100.0 / quota_effettiva(mid, m) for mid, m in scelte.items()], orientation="h",
                 name="Probabilità che il bookmaker «prezza» con la quota", marker_color=GRIGIO,
                 text=[f"{100.0 / quota_effettiva(mid, m):.0f}%" for mid, m in scelte.items()], textposition="outside")
    fig3.update_layout(title="Ogni scelta: modello contro quota", barmode="group", xaxis=dict(range=[0, 110], ticksuffix="%"),
                       legend=dict(orientation="h", y=-0.15), template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                       plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=40, b=10), height=110 + 70 * len(scelte),
                       font=dict(size=13))
    st.plotly_chart(fig3)
    st.caption("Se la barra blu è più lunga di quella grigia, il modello pensa che l'esito sia più probabile di quanto dica la quota: "
               "è il segno di una scelta conveniente.")

# -------------------------------- ARCHIVIO ---------------------------------
def mostra_ticket(orig_idx, schedina, sezione):
  """Disegna un ticket nell'archivio. sezione: 'att' (in attesa) o 'conc' (concluso)."""
  stato_manuale = schedina.get("stato_manuale")
  partite_lista = schedina.get("partite", [])
  if partite_lista:
    p_prim = partite_lista[0]
    d_ora_str = f"{p_prim.get('Data', '')} {p_prim.get('Ora', '')}"
    match_str = p_prim.get("Match", "")
    esito_str = sigla_mercato(p_prim.get("Consiglio", p_prim.get("Esito", "")))
    if len(partite_lista) > 1:
      match_str += f" (+{len(partite_lista) - 1})"
  else:
    d_ora_str = schedina.get("data_salvataggio", "N/D")
    match_str = "N/D"
    esito_str = "N/D"

  coda = f"{d_ora_str} · {match_str} · {esito_str} · quota {schedina.get('quota_totale', 1.0)} · € {float(schedina.get('importo_giocato', 0) or 0):.2f}"
  if sezione == "conc":
    badge = ":material/check_circle: Vinta" if stato_manuale == "vinto" else ":material/cancel: Persa"
    titolo = f"{badge} · {coda}"
  else:
    titolo = coda

  with st.expander(titolo, expanded=False):
    st.markdown(f'<span class="tk_{orig_idx}"></span>', unsafe_allow_html=True)

    c_man1, c_man2, c_man3, c_man4 = st.columns(4)
    c_man1.button("Vinta", key=f"btn_vinto_{sezione}_{orig_idx}", icon=":material/check_circle:", width="stretch",
                  on_click=cb_imposta_stato, args=(orig_idx, "vinto"))
    c_man2.button("Persa", key=f"btn_perso_{sezione}_{orig_idx}", icon=":material/cancel:", width="stretch",
                  on_click=cb_imposta_stato, args=(orig_idx, "perso"))
    c_man3.button("Riporta in attesa" if sezione == "conc" else "Reset",
                  key=f"btn_reset_{sezione}_{orig_idx}", icon=":material/undo:", width="stretch",
                  on_click=cb_imposta_stato, args=(orig_idx, None))
    c_man4.button("Elimina", key=f"btn_del_{sezione}_{orig_idx}", icon=":material/delete:", width="stretch",
                  on_click=cb_elimina_ticket, args=(orig_idx,))

    dettaglio = []
    for p in partite_lista:
      comp_val = p.get("Competizione", p.get("Campionato", "N/D"))
      match_val = p.get("Match", "N/D")
      consiglio_val = p.get("Consiglio", p.get("Esito", "N/D"))
      if sezione == "att":
        ris_reale, _, _ = verifica_risultato_partita(comp_val, match_val, consiglio_val, p.get("Data", ""))
      else:
        ris_reale = "Forzato"
      p_copia = p.copy()
      p_copia["Competizione"] = comp_val
      p_copia["Consiglio"] = consiglio_val
      p_copia["Risultato Reale"] = ris_reale
      dettaglio.append(p_copia)

    if sezione == "conc":
      st.markdown("Stato: **vinta**" if stato_manuale == "vinto" else "Stato: **persa**")
    else:
      st.markdown("Stato: **in attesa**")

    df_temp = pd.DataFrame(dettaglio)
    colonne_visibili = [c for c in ["Data", "Ora", "Competizione", "Match", "Consiglio", "Quota", "Risultato Reale"] if c in df_temp.columns]
    st.dataframe(df_temp[colonne_visibili], hide_index=True, width="stretch")


with tab_archivio:
  st.markdown("#### Archivio schedine")

  archivio_corrente = st.session_state.archivio_scommesse
  indici_attesa = [i for i, s in enumerate(archivio_corrente) if not e_concluso(s)]
  indici_conclusi = [i for i, s in enumerate(archivio_corrente) if e_concluso(s)]

  # Colori tenui dei ticket conclusi (una regola CSS per ticket, agganciata allo <span> interno)
  regole_css = []
  for i in indici_conclusi:
    vinto = archivio_corrente[i].get("stato_manuale") == "vinto"
    bg, bordo, testo = ("#EEF6F1", "#CFE3D6", "#2D6A4F") if vinto else ("#FAF0EF", "#EBCFCB", "#8E3B34")
    regole_css.append(
        f'div[data-testid="stExpander"]:has(span.tk_{i}) {{ background-color: {bg} !important; '
        f'border: 1px solid {bordo} !important; border-radius: 10px; margin-bottom: 8px; }} '
        f'div[data-testid="stExpander"]:has(span.tk_{i}) summary p {{ color: {testo} !important; font-weight: 600 !important; }}'
    )
  if regole_css:
    st.markdown("<style>" + " ".join(regole_css) + "</style>", unsafe_allow_html=True)

  col_pdf_arc1, col_spazio_vuoto = st.columns([0.4, 0.6])
  with col_pdf_arc1:
    if indici_attesa:
      pdf_archivio_bytes = genera_pdf_archivio_globale([archivio_corrente[i] for i in indici_attesa])
      st.download_button(
          label="Scarica il PDF delle scommesse in corso",
          icon=":material/download:",
          data=pdf_archivio_bytes,
          file_name=f"Scommesse_In_Corso_{datetime.now(tz_roma).strftime('%Y%m%d_%H%M')}.pdf",
          mime="application/pdf",
          width="stretch"
      )
    else:
      st.caption("Nessuna scommessa in corso da scaricare in PDF.")

  if archivio_corrente:
    st.markdown("##### In attesa")
    if indici_attesa:
      for i in indici_attesa:
        mostra_ticket(i, archivio_corrente[i], "att")
    else:
      st.caption("Nessuna scommessa attualmente in attesa.")

    st.markdown("##### Concluse")
    if indici_conclusi:
      for i in indici_conclusi:
        mostra_ticket(i, archivio_corrente[i], "conc")
    else:
      st.caption("Nessuna scommessa conclusa nell'archivio.")
  else:
    st.info("Nessuna schedina salvata: costruiscine una dalla scheda Partite.")

# -------------------------------- BILANCIO ---------------------------------
with tab_bilancio:
  st.markdown("#### Bilancio e cassa")

  msg_ripristino = st.session_state.pop("msg_ripristino", None)
  if msg_ripristino:
    st.success(msg_ripristino)

  archivio = st.session_state.archivio_scommesse
  puntate_chiuse = 0.0   # puntate dei ticket già conclusi
  puntate_in_gioco = 0.0  # puntate dei ticket ancora in attesa
  tot_vinto_effettivo = 0.0
  vinti_count = 0
  persi_count = 0
  in_attesa_count = 0

  for s in archivio:
    importo = float(s.get("importo_giocato", 0) or 0)
    if e_concluso(s):
      puntate_chiuse += importo
      if s.get("stato_manuale") == "vinto":
        vinti_count += 1
        tot_vinto_effettivo += vincita_ticket(s)
      else:
        persi_count += 1
    else:
      in_attesa_count += 1
      puntate_in_gioco += importo

  # Il bilancio netto considera solo i ticket conclusi: le puntate ancora in gioco
  # non sono perdite, ma sono comunque già uscite dalla cassa
  bilancio_netto = tot_vinto_effettivo - puntate_chiuse

  bankroll_base = float(st.session_state.dati_finanza.get("bankroll_iniziale", 35.80))
  tot_movimenti = sum(float(m.get("importo", 0)) for m in st.session_state.dati_finanza.get("movimenti", []))

  saldo_attuale = bankroll_base + tot_movimenti + bilancio_netto - puntate_in_gioco

  m1, m2, m3, m4 = st.columns(4)
  m1.markdown(scheda_kpi("Saldo in cassa", f"€ {saldo_attuale:.2f}",
                         f"di cui € {puntate_in_gioco:.2f} in gioco" if puntate_in_gioco else ""),
              unsafe_allow_html=True)
  m2.markdown(scheda_kpi("Ritorno effettivo", f"€ {tot_vinto_effettivo:.2f}"), unsafe_allow_html=True)
  m3.markdown(scheda_kpi("Bilancio netto", f"€ {bilancio_netto:+.2f}", tono="pos" if bilancio_netto >= 0 else "neg"),
              unsafe_allow_html=True)
  m4.markdown(scheda_kpi("Vinte · perse · in attesa", f"{vinti_count} · {persi_count} · {in_attesa_count}"),
              unsafe_allow_html=True)

  st.markdown("<div style='height: 0.8rem'></div>", unsafe_allow_html=True)

  with st.expander(":material/payments: Bankroll e movimenti di cassa", expanded=False):
    col_fin1, col_fin2 = st.columns(2)
    with col_fin1:
      nuovo_bankroll = st.number_input(
          "Bankroll iniziale (€)",
          min_value=0.0,
          max_value=10000.0,
          value=bankroll_base,
          step=5.0
      )
      if abs(nuovo_bankroll - bankroll_base) > 1e-9:
        st.session_state.dati_finanza["bankroll_iniziale"] = nuovo_bankroll
        salva_finanza(st.session_state.dati_finanza)
        st.rerun()

    with col_fin2:
      st.markdown("**Deposito o prelievo**")
      c_tipo, c_imp, c_btn = st.columns([0.35, 0.35, 0.30])
      tipo_mov = c_tipo.selectbox("Tipo", ["Deposito (+)", "Prelievo (-)"], label_visibility="collapsed")
      importo_mov = c_imp.number_input("Importo", min_value=1.0, max_value=10000.0, value=10.0, step=5.0, label_visibility="collapsed")
      if c_btn.button("Registra", width="stretch"):
        valore_reale = importo_mov if "Deposito" in tipo_mov else -importo_mov
        st.session_state.dati_finanza.setdefault("movimenti", []).append({
            "data": datetime.now(tz_roma).strftime("%d/%m/%Y %H:%M"),
            "tipo": tipo_mov,
            "importo": valore_reale
        })
        salva_finanza(st.session_state.dati_finanza)
        st.rerun()

    if st.session_state.dati_finanza.get("movimenti"):
      st.divider()
      st.markdown("**Storico depositi e prelievi**")
      for i, mov in enumerate(st.session_state.dati_finanza["movimenti"]):
        c_m1, c_m2, c_m3 = st.columns([0.4, 0.4, 0.2])
        c_m1.write(f"{mov.get('data', '')}")
        c_m2.write(f"{mov.get('tipo', '')}: **€ {abs(float(mov.get('importo', 0))):.2f}**")
        c_m3.button("Rimuovi", key=f"del_mov_{i}", icon=":material/delete:", on_click=cb_rimuovi_movimento, args=(i,))

  with st.expander(":material/save: Backup e ripristino", expanded=False):
    st.caption("Esporta o ripristina archivio e cassa per non perdere i dati.")
    col_bk1, col_bk2 = st.columns(2)
    with col_bk1:
      backup_completo = {
          "archivio_scommesse": st.session_state.archivio_scommesse,
          "dati_finanza": st.session_state.dati_finanza
      }
      st.download_button(
          label="Esporta backup (.json)",
          icon=":material/download:",
          data=json.dumps(pulisci_tipi_numpy(backup_completo), ensure_ascii=False, indent=4),
          file_name=f"Backup_Betting_Pro_{datetime.now(tz_roma).strftime('%Y%m%d_%H%M')}.json",
          mime="application/json",
          width="stretch"
      )
    with col_bk2:
      file_caricato = st.file_uploader("Ripristina backup (.json)", type=["json"], label_visibility="collapsed")
      # Il ripristino parte solo dal pulsante: prima, con il file ancora caricato,
      # l'app si ripristinava e si riavviava in continuazione
      if file_caricato is not None and st.button("Ripristina questo backup", icon=":material/upload:", width="stretch"):
        try:
          dati_ripristinati = json.load(file_caricato)
          arch_nuovo = dati_ripristinati.get("archivio_scommesse")
          fin_nuova = dati_ripristinati.get("dati_finanza")
          if not isinstance(arch_nuovo, list) or not isinstance(fin_nuova, dict) or "bankroll_iniziale" not in fin_nuova:
            st.error("File non valido: mancano 'archivio_scommesse' e/o 'dati_finanza'.")
          else:
            if not isinstance(fin_nuova.get("movimenti"), list):
              fin_nuova["movimenti"] = []
            salva_archivio(arch_nuovo)
            salva_finanza(fin_nuova)
            st.session_state.msg_ripristino = "Dati ripristinati con successo."
            st.rerun()
        except Exception as e:
          st.error(f"File non valido: {e}")

  st.markdown("##### Andamento della cassa")

  dati_linea = [{"Ticket": "Inizio", "Saldo Cassa (€)": round(bankroll_base + tot_movimenti, 2)}]
  cassa_progressiva = bankroll_base + tot_movimenti
  numero_ticket = 0
  for s in reversed(archivio):
    if e_concluso(s):
      numero_ticket += 1
      imp = float(s.get("importo_giocato", 0) or 0)
      if s.get("stato_manuale") == "vinto":
        cassa_progressiva += vincita_ticket(s) - imp
      else:
        cassa_progressiva -= imp
      dati_linea.append({
          "Ticket": f"Ticket #{numero_ticket}",
          "Saldo Cassa (€)": round(cassa_progressiva, 2)
      })

  if len(dati_linea) > 1:
    df_linea = pd.DataFrame(dati_linea)
    fig = px.line(
        df_linea,
        x="Ticket",
        y="Saldo Cassa (€)",
        markers=True,
        template="plotly_white"
    )
    fig.update_traces(line_color="#4A6FA5", line_width=2.5, marker_size=7)
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig)
  else:
    st.caption("Il grafico comparirà appena ci sarà almeno un ticket concluso.")
