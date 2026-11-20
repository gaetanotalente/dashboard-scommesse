"""Fonte gratuita, senza chiavi API.

- Campionati nazionali: storico e quote da football-data.co.uk
  (file per stagione + fixtures.csv con le quote delle prossime partite).
- Nazionali: storico dei risultati da github.com/martj42/international_results.
  Per le nazionali non esiste una fonte gratuita di quote: il modello stima
  le probabilita' e la quota va controllata/scritta a mano.

Il modulo non usa Streamlit, quindi si puo' provare anche da solo.
"""
from datetime import datetime, timedelta
from io import StringIO
import difflib
import json
import os
import re
import time
import unicodedata

import numpy as np
import pandas as pd
import requests
from scipy.optimize import minimize
from scipy.stats import poisson

FD_BASE = "https://www.football-data.co.uk"
FD_FIXTURES = FD_BASE + "/fixtures.csv"
NAZ_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"

# lega ESPN -> codice file di football-data
FD_CODICE_PER_SLUG = {
    "ita.1": "I1", "ita.2": "I2", "eng.1": "E0", "esp.1": "SP1", "ger.1": "D1", "fra.1": "F1",
}
# competizioni ESPN fra squadre nazionali
SLUG_NAZIONALI = {"uefa.nations", "fifa.worldq.uefa", "fifa.worldq.conmebol", "fifa.friendly"}

TTL_STAGIONE_CORRENTE = 12 * 3600
TTL_STAGIONE_PASSATA = 30 * 24 * 3600
TTL_FIXTURES = 3 * 3600
TTL_NAZIONALI = 12 * 3600

MEZZA_VITA_CAMPIONATO = 220   # giorni: una partita di 220 giorni fa pesa la meta'
MEZZA_VITA_NAZIONALI = 400
ANNI_NAZIONALI = 4            # le nazionali giocano poco: servono piu' anni
MIN_PARTITE_SQUADRA = 4       # sotto questa soglia il modello non si pronuncia
PESO_MODELLO = 0.35           # nelle partite con quote: 35% modello, 65% mercato
SOGLIA_VALUE = 0.03

# nomi usati nei file di football-data: bookmaker con sicurezza, gli altri restano col codice
NOMI_BOOK = {"B365": "Bet365", "PS": "Pinnacle", "P": "Pinnacle", "BV": "BetVictor"}
BOOK_1X2 = ["B365", "BV", "BW", "PS", "P", "PP", "BFD", "SKB", "WH", "IW", "VC", "LB"]
BOOK_OU = [("B365", "B365>2.5", "B365<2.5"), ("PS", "P>2.5", "P<2.5")]

STOPWORDS = {"fc", "cf", "afc", "ac", "as", "sc", "fk", "bk", "if", "ssc", "us", "the", "club", "calcio", "de", "of"}
ALIAS = {  # nome ESPN (normalizzato) -> nome nei dati (normalizzato)
    "manchester united": "man united", "manchester city": "man city",
    "nottingham forest": "nott m forest", "sheffield wednesday": "sheffield weds",
    "wolverhampton wanderers": "wolves", "wolverhampton": "wolves",
    "west bromwich albion": "west brom", "tottenham hotspur": "tottenham",
    "newcastle united": "newcastle", "leicester city": "leicester",
    "brighton and hove albion": "brighton", "leeds united": "leeds",
    "internazionale": "inter", "inter milan": "inter", "ac milan": "milan",
    "hellas verona": "verona", "bayern munchen": "bayern munich",
    "borussia monchengladbach": "m gladbach", "borussia dortmund": "dortmund",
    "eintracht frankfurt": "ein frankfurt", "bayer leverkusen": "leverkusen",
    "paris saint germain": "paris sg", "saint etienne": "st etienne",
    "atletico madrid": "ath madrid", "athletic club": "ath bilbao",
    "athletic bilbao": "ath bilbao", "real betis": "betis", "real sociedad": "sociedad",
    "rayo vallecano": "vallecano", "celta vigo": "celta", "espanyol": "espanol",
    "rb leipzig": "rb leipzig", "mainz 05": "mainz", "1 fsv mainz 05": "mainz",
    # nazionali
    "czechia": "czech republic", "turkiye": "turkey", "turkey": "turkey",
    "bosnia herzegovina": "bosnia and herzegovina", "bosnia": "bosnia and herzegovina",
    "ireland": "republic of ireland", "usa": "united states", "korea republic": "south korea",
    "ir iran": "iran", "cote d ivoire": "ivory coast", "congo dr": "dr congo",
    "cape verde islands": "cape verde", "macedonia": "north macedonia",
}


# ---------------------------------------------------------------------------
# Nomi squadra
# ---------------------------------------------------------------------------
def norm_nome(nome):
  t = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().lower()
  t = t.replace("&", " and ")
  t = re.sub(r"[^a-z0-9]+", " ", t).strip()
  return re.sub(r"\s+", " ", t)


def _chiave(nome):
  n = norm_nome(nome)
  if n in ALIAS:
    n = ALIAS[n]
  tokens = [x for x in n.split() if x not in STOPWORDS]
  return " ".join(tokens) or n


def _punteggio(a, b):
  """Somiglianza 0-1 tra due nomi gia' passati da _chiave."""
  if a == b:
    return 1.0
  ta, tb = set(a.split()), set(b.split())
  if ta and tb and (ta <= tb or tb <= ta) and max(len(x) for x in (ta & tb) or {""}) >= 4:
    return 0.9
  return difflib.SequenceMatcher(None, a, b).ratio()


def trova_squadra(varianti, squadre):
  """Nome della squadra nei dati che corrisponde a una delle varianti ESPN, o None se incerto."""
  if isinstance(varianti, str):
    varianti = [varianti]
  chiavi_dati = {s: _chiave(s) for s in squadre}
  migliore = (0.0, None)
  seconda = 0.0
  for s, k in chiavi_dati.items():
    p = max(_punteggio(_chiave(v), k) for v in varianti)
    if p > migliore[0]:
      seconda = migliore[0]
      migliore = (p, s)
    elif p > seconda:
      seconda = p
  p, nome = migliore
  if nome is None or p < 0.82:
    return None
  if p < 1.0 and seconda > p - 0.04:   # due candidati quasi uguali: meglio non rischiare
    return None
  return nome


# ---------------------------------------------------------------------------
# Download con cache su disco
# ---------------------------------------------------------------------------
def _leggi_testo(percorso):
  with open(percorso, "rb") as f:
    dati = f.read()
  for codifica in ("utf-8-sig", "latin-1"):
    try:
      return dati.decode(codifica)
    except UnicodeDecodeError:
      continue
  return dati.decode("utf-8", "ignore")


def scarica_csv(url, percorso, ttl, rete=True, sessione=None):
  """Scarica un CSV (o riusa la copia su disco). Restituisce (DataFrame|None, errore|None)."""
  sessione = sessione or requests
  esiste = os.path.exists(percorso)
  fresco = esiste and (time.time() - os.path.getmtime(percorso)) < ttl
  errore = None
  if not fresco and rete:
    try:
      r = sessione.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
      if r.status_code == 200 and r.content:
        os.makedirs(os.path.dirname(percorso), exist_ok=True)
        with open(percorso, "wb") as f:
          f.write(r.content)
        esiste = fresco = True
      elif r.status_code == 404:
        errore = "file non trovato"
      else:
        errore = f"risposta {r.status_code}"
    except Exception as e:
      errore = f"nessuna risposta ({type(e).__name__})"
  if not esiste:
    return None, errore or "file non scaricato"
  try:
    df = pd.read_csv(StringIO(_leggi_testo(percorso)), on_bad_lines="skip")
  except Exception as e:
    return None, f"file illeggibile ({type(e).__name__})"
  return df, (None if fresco else errore)   # copia vecchia ma usabile: l'errore resta come avviso


def stagioni(oggi, quante=2):
  """Codici stagione di football-data, dalla piu' recente: es. ['2627', '2526']."""
  inizio = oggi.year if oggi.month >= 7 else oggi.year - 1
  return [f"{(inizio - i) % 100:02d}{(inizio - i + 1) % 100:02d}" for i in range(quante)]


def carica_storico_campionato(codice, cartella, oggi, rete=True, sessione=None):
  """Partite giocate delle ultime due stagioni. Restituisce (DataFrame|None, avvisi)."""
  pezzi, avvisi = [], []
  for i, cod in enumerate(stagioni(oggi)):
    ttl = TTL_STAGIONE_CORRENTE if i == 0 else TTL_STAGIONE_PASSATA
    df, err = scarica_csv(f"{FD_BASE}/mmz4281/{cod}/{codice}.csv",
                          os.path.join(cartella, f"fd_{codice}_{cod}.csv"), ttl, rete, sessione)
    if df is None:
      if i == 0:
        avvisi.append(f"{codice} {cod}: {err}")
      continue
    if err:
      avvisi.append(f"{codice} {cod}: {err} (uso la copia salvata)")
    pezzi.append(df)
  if not pezzi:
    return None, avvisi
  df = pd.concat(pezzi, ignore_index=True)
  return normalizza_storico(df), avvisi


def normalizza_storico(df):
  """Tiene le partite con risultato e rende la data un vero datetime."""
  df = df.copy()
  for c in ("Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"):
    if c not in df.columns:
      return pd.DataFrame(columns=["data", "casa", "ospite", "gc", "go"])
  df["data"] = pd.to_datetime(df["Date"], dayfirst=True, format="mixed", errors="coerce")
  df["gc"] = pd.to_numeric(df["FTHG"], errors="coerce")
  df["go"] = pd.to_numeric(df["FTAG"], errors="coerce")
  df = df.dropna(subset=["data", "HomeTeam", "AwayTeam", "gc", "go"])
  df = df.rename(columns={"HomeTeam": "casa", "AwayTeam": "ospite"})
  df["gc"], df["go"] = df["gc"].astype(int), df["go"].astype(int)
  return df.sort_values("data").reset_index(drop=True)


def carica_nazionali(cartella, oggi, rete=True, sessione=None):
  df, err = scarica_csv(NAZ_URL, os.path.join(cartella, "nazionali_results.csv"), TTL_NAZIONALI, rete, sessione)
  if df is None:
    return None, [f"nazionali: {err}"]
  df = df.copy()
  df["data"] = pd.to_datetime(df.get("date"), errors="coerce")
  df["gc"] = pd.to_numeric(df.get("home_score"), errors="coerce")
  df["go"] = pd.to_numeric(df.get("away_score"), errors="coerce")
  df = df.dropna(subset=["data", "home_team", "away_team", "gc", "go"])
  df = df[df["data"] >= (pd.Timestamp(oggi) - pd.Timedelta(days=365 * ANNI_NAZIONALI))]
  df = df.rename(columns={"home_team": "casa", "away_team": "ospite"})
  df["neutro"] = (df["neutral"].astype(str).str.upper().eq("TRUE")
                  if "neutral" in df else pd.Series(False, index=df.index))
  amichevole = (df["tournament"].astype(str).str.lower().eq("friendly")
                if "tournament" in df else pd.Series(False, index=df.index))
  df["peso"] = np.where(amichevole, 0.6, 1.0)   # le amichevoli dicono meno sulla forza reale
  df["gc"], df["go"] = df["gc"].astype(int), df["go"].astype(int)
  return df.sort_values("data").reset_index(drop=True), ([f"nazionali: {err} (uso la copia salvata)"] if err else [])


def carica_fixtures(cartella, rete=True, sessione=None):
  df, err = scarica_csv(FD_FIXTURES, os.path.join(cartella, "fd_fixtures.csv"), TTL_FIXTURES, rete, sessione)
  if df is None:
    return None, [f"fixtures: {err}"]
  df = df.copy()
  df["data"] = pd.to_datetime(df.get("Date"), dayfirst=True, format="mixed", errors="coerce")
  df = df.dropna(subset=["data", "HomeTeam", "AwayTeam"])
  return df.reset_index(drop=True), ([f"fixtures: {err} (uso la copia salvata)"] if err else [])


# ---------------------------------------------------------------------------
# Modello: forza di attacco e difesa (Poisson con memoria decrescente)
# ---------------------------------------------------------------------------
def adatta_modello(df, data_rif, mezza_vita, regolarizzazione=2.0):
  """Stima gol attesi di ogni squadra. df: colonne data, casa, ospite, gc, go (+ neutro, peso)."""
  squadre = sorted(set(df["casa"]) | set(df["ospite"]))
  idx = {s: i for i, s in enumerate(squadre)}
  n = len(squadre)
  h = df["casa"].map(idx).to_numpy()
  a = df["ospite"].map(idx).to_numpy()
  gc, go = df["gc"].to_numpy(float), df["go"].to_numpy(float)
  eta_casa = (1.0 - (df["neutro"].to_numpy(float) if "neutro" in df else 0.0))
  giorni = (pd.Timestamp(data_rif) - df["data"]).dt.days.clip(lower=0).to_numpy(float)
  w = 0.5 ** (giorni / mezza_vita)
  if "peso" in df:
    w = w * df["peso"].to_numpy(float)

  def perdita(x):
    mu, casa_v = x[0], x[1]
    att, dif = x[2:2 + n], x[2 + n:]
    lc = np.exp(mu + casa_v * eta_casa + att[h] - dif[a])
    lo = np.exp(mu + att[a] - dif[h])
    nll = np.sum(w * (lc - gc * np.log(lc))) + np.sum(w * (lo - go * np.log(lo)))
    nll += regolarizzazione * (np.sum(att ** 2) + np.sum(dif ** 2))
    dc, do = w * (lc - gc), w * (lo - go)
    g = np.zeros_like(x)
    g[0] = dc.sum() + do.sum()
    g[1] = (dc * eta_casa).sum()
    g[2:2 + n] = np.bincount(h, dc, n) + np.bincount(a, do, n) + 2 * regolarizzazione * att
    g[2 + n:] = -np.bincount(a, dc, n) - np.bincount(h, do, n) + 2 * regolarizzazione * dif
    return nll, g

  x0 = np.zeros(2 + 2 * n)
  x0[0] = np.log(max(0.5, (gc.mean() + go.mean()) / 2))
  sol = minimize(perdita, x0, jac=True, method="L-BFGS-B")
  x = sol.x
  conteggi = pd.concat([df["casa"], df["ospite"]]).value_counts().to_dict()
  return {
      "mu": float(x[0]), "casa": float(x[1]),
      "att": {s: float(x[2 + i]) for s, i in idx.items()},
      "dif": {s: float(x[2 + n + i]) for s, i in idx.items()},
      "partite": {s: int(c) for s, c in conteggi.items()},
      "n_partite": int(len(df)),
  }


def gol_attesi(modello, casa, ospite, neutro=False):
  """(lambda casa, lambda ospite) oppure None se una delle due squadre ha pochi dati."""
  for s in (casa, ospite):
    if modello["partite"].get(s, 0) < MIN_PARTITE_SQUADRA:
      return None
  lc = np.exp(modello["mu"] + (0.0 if neutro else modello["casa"]) + modello["att"][casa] - modello["dif"][ospite])
  lo = np.exp(modello["mu"] + modello["att"][ospite] - modello["dif"][casa])
  return float(lc), float(lo)


def probabilita(lc, lo, max_goals=11):
  k = np.arange(max_goals)
  m = np.outer(poisson.pmf(k, lc), poisson.pmf(k, lo))
  m = m / m.sum()
  i, j = np.indices(m.shape)
  p_over = float(m[(i + j) > 2.5].sum())
  return {
      "1": float(m[i > j].sum()), "X": float(m[i == j].sum()), "2": float(m[i < j].sum()),
      "over": p_over, "under": 1.0 - p_over, "goal": float(m[(i >= 1) & (j >= 1)].sum()),
  }


# ---------------------------------------------------------------------------
# Quote di football-data (fixtures.csv e file storici)
# ---------------------------------------------------------------------------
def _num(riga, colonna):
  try:
    v = float(riga.get(colonna))
  except (TypeError, ValueError):
    return None
  return v if v > 1.0 and not np.isnan(v) else None


def quote_1x2(riga):
  """Righe [bookmaker, casa, pareggio, ospite], una per bookmaker presente nel file."""
  righe = []
  for cod in BOOK_1X2:
    q = [_num(riga, cod + s) for s in ("H", "D", "A")]
    if all(q):
      righe.append([NOMI_BOOK.get(cod, cod)] + q)
  return righe


def quote_ou(riga):
  righe = []
  for cod, colo, colu in BOOK_OU:
    qo, qu = _num(riga, colo), _num(riga, colu)
    if qo and qu:
      righe.append([NOMI_BOOK.get(cod, cod), qo, qu])
  return righe


def _senza_margine(quote):
  inv = [1.0 / q for q in quote]
  s = sum(inv)
  return [x / s for x in inv]


def prob_mercato_1x2(riga):
  """Probabilita' di mercato senza margine: Pinnacle se c'e', poi media di mercato, poi media dei bookmaker."""
  righe = quote_1x2(riga)
  for r in righe:
    if r[0] == "Pinnacle":
      return _senza_margine(r[1:]), "Pinnacle"
  med = [_num(riga, "AvgH"), _num(riga, "AvgD"), _num(riga, "AvgA")]
  if all(med):
    return _senza_margine(med), "media del mercato"
  if righe:
    return list(np.mean([_senza_margine(r[1:]) for r in righe], axis=0)), f"{len(righe)} bookmaker"
  return None, ""


def prob_mercato_ou(riga):
  righe = quote_ou(riga)
  for r in righe:
    if r[0] == "Pinnacle":
      return _senza_margine(r[1:]), "Pinnacle"
  med = [_num(riga, "Avg>2.5"), _num(riga, "Avg<2.5")]
  if all(med):
    return _senza_margine(med), "media del mercato"
  if righe:
    return list(np.mean([_senza_margine(r[1:]) for r in righe], axis=0)), f"{len(righe)} bookmaker"
  return None, ""


def migliore_quota(righe, idx, riga_fd=None, colonna_max=None):
  """Quota piu' alta fra i bookmaker (scartando valori oltre +25% sulla mediana)."""
  if righe:
    valori = sorted(r[idx] for r in righe)
    mediana = valori[len(valori) // 2]
    ammesse = [r for r in righe if r[idx] <= mediana * 1.25] or righe
    r = max(ammesse, key=lambda x: x[idx])
    return r[idx], r[0]
  if riga_fd is not None and colonna_max:
    q = _num(riga_fd, colonna_max)
    if q:
      return q, "miglior prezzo del mercato"
  return None, None


# ---------------------------------------------------------------------------
# Costruzione dei mercati di una partita
# ---------------------------------------------------------------------------
def _mercato(nome, quota, bookmaker, prob):
  return {"Consiglio": nome, "Quota": round(float(quota), 2), "Bookmaker": bookmaker,
          "ValoreProb": round(float(prob) * 100, 1), "EV": round(float(quota * prob - 1.0), 3)}


def _mix(p_modello, p_mercato, peso=PESO_MODELLO):
  if p_modello is None:
    return p_mercato
  if p_mercato is None:
    return p_modello
  return peso * p_modello + (1 - peso) * p_mercato


def mercati_partita(lam, riga_quote, peso=PESO_MODELLO):
  """Restituisce (mercati, descrizione fonte, solo_modello).

  lam: (lambda casa, lambda ospite) del modello oppure None.
  riga_quote: riga di fixtures.csv con le quote oppure None.
  Con le quote: probabilita' = mix modello/mercato, quota = migliore tra i bookmaker.
  Senza quote: solo il modello, e la quota proposta e' quella 'equa' (1/probabilita'): va sostituita
  con quella vera del bookmaker."""
  pm = probabilita(*lam) if lam else None
  mercati = []
  if riga_quote is not None:
    r1 = quote_1x2(riga_quote)
    p_mkt, et = prob_mercato_1x2(riga_quote)
    if p_mkt is not None:
      q1, b1 = migliore_quota(r1, 1, riga_quote, "MaxH")
      q2, b2 = migliore_quota(r1, 3, riga_quote, "MaxA")
      if q1 and q2:
        mercati.append(_mercato("1 (Vittoria Casa)", q1, b1, _mix(pm and pm["1"], p_mkt[0], peso)))
        mercati.append(_mercato("2 (Vittoria Ospite)", q2, b2, _mix(pm and pm["2"], p_mkt[2], peso)))
    ro = quote_ou(riga_quote)
    p_ou, _ = prob_mercato_ou(riga_quote)
    if p_ou is not None:
      qo, bo = migliore_quota(ro, 1, riga_quote, "Max>2.5")
      qu, bu = migliore_quota(ro, 2, riga_quote, "Max<2.5")
      if qo and qu:
        mercati.append(_mercato("Over 2.5", qo, bo, _mix(pm and pm["over"], p_ou[0], peso)))
        mercati.append(_mercato("Under 2.5", qu, bu, _mix(pm and pm["under"], p_ou[1], peso)))
    if mercati:
      descr = (f"Probabilita' = {int(peso * 100)}% modello sui risultati + {100 - int(peso * 100)}% mercato"
               f" ({et}, margine tolto)" if pm else f"Probabilita' dal mercato ({et}, margine tolto), modello non disponibile")
      return mercati, descr, False
  if pm:
    for nome, chiave in (("1 (Vittoria Casa)", "1"), ("2 (Vittoria Ospite)", "2"), ("Over 2.5", "over"),
                         ("Under 2.5", "under"), ("Goal (Entrambe Segnano)", "goal")):
      p = pm[chiave]
      m = _mercato(nome, 1.0 / p, "quota stimata (scrivi la tua)", p)
      m["EV"] = 0.0
      mercati.append(m)
    return mercati, "Solo modello sui risultati passati: nessuna quota reale disponibile", True
  return [], "", False


def xg_testo(lam, solo_modello):
  if not lam:
    return "xG: n/d | storico insufficiente"
  p = probabilita(*lam)
  return f"xG modello: {lam[0]:.2f} - {lam[1]:.2f} | Poisson [1:{p['1'] * 100:.1f}% X:{p['X'] * 100:.1f}% 2:{p['2'] * 100:.1f}%]"


# ---------------------------------------------------------------------------
# Aggancio alle partite ESPN
# ---------------------------------------------------------------------------
_MODELLI = {}   # memoria del processo: il modello si ricalcola solo se il file cambia


def _modello_in_cache(chiave, firma, costruttore):
  v = _MODELLI.get(chiave)
  if v and v[0] == firma:
    return v[1]
  modello = costruttore()
  _MODELLI[chiave] = (firma, modello)
  return modello


def _firma(df):
  return (len(df), str(df["data"].max()))


def trova_riga_fixture(fixtures, casa_fd, ospite_fd, giorno):
  """Riga di fixtures.csv con le due squadre (nei nomi di football-data) entro 1 giorno dalla data."""
  if fixtures is None or fixtures.empty:
    return None
  sel = fixtures[(fixtures["HomeTeam"] == casa_fd) & (fixtures["AwayTeam"] == ospite_fd)]
  if sel.empty:
    return None
  sel = sel.assign(_d=(sel["data"] - pd.Timestamp(giorno)).abs())
  riga = sel.sort_values("_d").iloc[0]
  return riga if riga["_d"] <= pd.Timedelta(days=1) else None


def ev_da_riga(riga):
  """Quote per bookmaker di una riga di fixtures.csv, nel formato usato dal resto del programma."""
  if not riga:
    return None
  ev = {"h2h": quote_1x2(riga), "totals": quote_ou(riga)}
  return ev if (ev["h2h"] or ev["totals"]) else None


def mescola_con_modello(mercati, lam, peso=PESO_MODELLO):
  """Sposta le probabilita' di mercati gia' quotati verso quelle del modello (peso 0-1). Ricalcola l'EV."""
  if not lam:
    return mercati
  pm = probabilita(*lam)
  mappa = {"1 (Vittoria Casa)": "1", "2 (Vittoria Ospite)": "2", "Over 2.5": "over",
           "Under 2.5": "under", "Goal (Entrambe Segnano)": "goal"}
  risultato = []
  for x in mercati:
    k = mappa.get(x["Consiglio"])
    if not k:
      risultato.append(x)
      continue
    p = _mix(pm[k], x["ValoreProb"] / 100.0, peso)
    risultato.append(dict(x, ValoreProb=round(p * 100, 1), EV=round(x["Quota"] * p - 1.0, 3)))
  return risultato


def _contesto(da_fare, cartella, oggi, rete, sessione):
  """Scarica (o legge dalla cache) storici, fixtures e nazionali necessari. Restituisce (contesto, messaggi)."""
  messaggi = []
  storici, fixtures, nazionali = {}, None, None
  codici = sorted({FD_CODICE_PER_SLUG[m["Lega"]] for m in da_fare if m["Lega"] in FD_CODICE_PER_SLUG})
  if codici:
    fixtures, av = carica_fixtures(cartella, rete, sessione)
    messaggi += av
    for c in codici:
      df, av = carica_storico_campionato(c, cartella, oggi, rete, sessione)
      messaggi += av
      if df is not None and len(df) >= 30:
        storici[c] = _modello_in_cache(("lega", c), _firma(df),
                                       lambda df=df: adatta_modello(df, oggi, MEZZA_VITA_CAMPIONATO))
  if any(m["Lega"] in SLUG_NAZIONALI for m in da_fare):
    naz, av = carica_nazionali(cartella, oggi, rete, sessione)
    messaggi += av
    if naz is not None and len(naz) >= 200:
      nazionali = _modello_in_cache(("naz",), _firma(naz),
                                    lambda: adatta_modello(naz, oggi, MEZZA_VITA_NAZIONALI, 4.0))
  return {"storici": storici, "fixtures": fixtures, "nazionali": nazionali}, messaggi


def _dati_partita(m, ctx):
  """{'lam', 'riga', 'fonte'} per una partita ESPN, oppure None se le squadre non sono riconosciute."""
  slug = m["Lega"]
  if slug in FD_CODICE_PER_SLUG:
    modello = ctx["storici"].get(FD_CODICE_PER_SLUG[slug])
    fonte = "football-data.co.uk"
  else:
    modello = ctx["nazionali"]
    fonte = "martj42/international_results"
  if not modello:
    return None
  squadre = list(modello["partite"])
  casa_fd = trova_squadra(m.get("NomiCasa", []), squadre)
  ospite_fd = trova_squadra(m.get("NomiOspite", []), squadre)
  if not (casa_fd and ospite_fd):
    return None
  riga = None
  if slug in FD_CODICE_PER_SLUG:
    giorno = (m.get("Kickoff") or "")[:10] or None
    if giorno:
      r = trova_riga_fixture(ctx["fixtures"], casa_fd, ospite_fd, giorno)
      riga = r.to_dict() if r is not None else None
  return {"lam": gol_attesi(modello, casa_fd, ospite_fd), "riga": riga, "fonte": fonte}


def _coperta(m):
  return m.get("Lega") in FD_CODICE_PER_SLUG or m.get("Lega") in SLUG_NAZIONALI


def raccogli_dati(partite, cartella, oggi=None, rete=True, sessione=None):
  """Dati gratuiti di TUTTE le partite coperte, anche di quelle gia' quotate da altre fonti.

  Restituisce ({ID: {'lam', 'riga', 'ev', 'fonte'}}, messaggi). 'ev' sono le quote per bookmaker
  di fixtures.csv, da unire a quelle delle altre fonti."""
  oggi = oggi or datetime.now()
  da_fare = [m for m in partite if _coperta(m)]
  if not da_fare:
    return {}, []
  ctx, messaggi = _contesto(da_fare, cartella, oggi, rete, sessione)
  dati = {}
  for m in da_fare:
    d = _dati_partita(m, ctx)
    if d:
      d["ev"] = ev_da_riga(d["riga"])
      dati[m["ID"]] = d
  return dati, messaggi


def analizza_partite(partite, cartella, oggi=None, rete=True, sessione=None):
  """Aggiunge mercati e analisi alle sole partite senza quote. Restituisce (partite, messaggi).

  Le partite che hanno gia' quote reali (da The Odds API o OddsPapi) restano come sono."""
  vuote = [m for m in partite if not m.get("Mercati") and _coperta(m)]
  dati, messaggi = raccogli_dati(vuote, cartella, oggi, rete, sessione)
  risultato = []
  for m in partite:
    d = dati.get(m["ID"]) if not m.get("Mercati") else None
    if not d:
      risultato.append(m)
      continue
    mercati, descr, solo = mercati_partita(d["lam"], d["riga"])
    if not mercati:
      risultato.append(m)
      continue
    m2 = dict(m)
    m2["Mercati"] = mercati
    m2["SoloModello"] = solo
    m2["Analisi xG"] = xg_testo(d["lam"], solo)
    m2["Motivazione"] = f"[{m['Competizione']}] {descr}. Fonte: {d['fonte']}, nessuna chiave."
    risultato.append(m2)
  return risultato, messaggi


# ---------------------------------------------------------------------------
# Verifica statistica: il modello avrebbe funzionato sulle partite passate?
# ---------------------------------------------------------------------------
def _col_prima(riga, colonne):
  for c in colonne:
    v = _num(riga, c)
    if v:
      return v
  return None


def verifica_storica(df, giorni_test=60, pesi=(0.0, 0.2, 0.35, 0.5, 0.75, 1.0), soglia=SOGLIA_VALUE):
  """Adatta il modello sulle partite precedenti agli ultimi `giorni_test` giorni e lo prova su quelle.

  Per ogni peso del modello (0 = solo mercato, 1 = solo modello) calcola l'errore logaritmico
  (piu' basso = meglio) e il risultato di una puntata fissa da 1 sulle giocate con EV > soglia.
  Usa le quote medie del mercato per le probabilita' e le quote massime (o Bet365) per le puntate."""
  df = df.sort_values("data")
  taglio = df["data"].max() - pd.Timedelta(days=giorni_test)
  train, test = df[df["data"] < taglio], df[df["data"] >= taglio]
  if len(train) < 100 or len(test) < 20:
    return None
  modello = adatta_modello(train, taglio, MEZZA_VITA_CAMPIONATO)
  righe = []
  for _, r in test.iterrows():
    lam = gol_attesi(modello, r["casa"], r["ospite"])
    med = [_col_prima(r, [p + s for p in ("AvgC", "Avg")]) for s in ("H", "D", "A")]
    best = [_col_prima(r, [c + s for c in ("MaxC", "Max", "B365C", "B365")]) for s in ("H", "D", "A")]
    if not lam or not all(med):
      continue
    pm = probabilita(*lam)
    righe.append((np.array([pm["1"], pm["X"], pm["2"]]), np.array(_senza_margine(med)),
                  np.array([x or 0.0 for x in best]), 0 if r["gc"] > r["go"] else (1 if r["gc"] == r["go"] else 2)))
  if len(righe) < 20:
    return None
  esiti = []
  for w in pesi:
    ll, n_giocate, profitto = 0.0, 0, 0.0
    for pmod, pmkt, quote, y in righe:
      p = w * pmod + (1 - w) * pmkt
      ll += -np.log(max(p[y], 1e-9))
      for k in (0, 2):                       # come l'app: solo segno 1 e segno 2
        if quote[k] > 1 and quote[k] * p[k] - 1 > soglia:
          n_giocate += 1
          profitto += (quote[k] - 1) if y == k else -1
    esiti.append({"peso_modello": w, "errore": ll / len(righe), "giocate": n_giocate,
                  "profitto": profitto, "roi": (profitto / n_giocate) if n_giocate else None})
  return {"partite_test": len(righe), "partite_addestramento": len(train), "esiti": esiti}
