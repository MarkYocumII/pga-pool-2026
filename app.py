"""PGA Championship Pool 2026 — Live Scoring Leaderboard"""
import streamlit as st
import pandas as pd
import requests
import re
import unicodedata
import os
from datetime import datetime, timezone

st.set_page_config(page_title="PGA Championship Pool 2026", page_icon="⛳", layout="centered")

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=180_000, key="datarefresh")
except ImportError:
    pass

DIR = os.path.dirname(__file__)
ROSTER_PATH = os.path.join(DIR, "rosters.csv")


# === SCORING ===
def points_for_position(pos, status=None):
    if status and status.upper() in ("CUT", "MC", "WD", "DQ"):
        return 0
    if pos is None:
        return 0
    if pos == 1: return 90
    if pos == 2: return 65
    if pos == 3: return 60
    if pos == 4: return 55
    if pos == 5: return 50
    if pos == 6: return 45
    if pos == 7: return 40
    if pos == 8: return 35
    if pos == 9: return 30
    if pos == 10: return 25
    if 11 <= pos <= 15: return 20
    if 16 <= pos <= 20: return 15
    if 21 <= pos <= 25: return 10
    if 26 <= pos <= 30: return 5
    if pos >= 31: return 2
    return 0


# === NAME NORMALIZATION ===
def norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"[^a-z\s]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s

ALIASES = {
    "rasmus hojgaard": "rasmus hjgaard",
    "nicolai hojgaard": "nicolai hjgaard",
    "rasmus neegaardpetersen": "rasmus neergaardpetersen",
    "sungjae im": "sung jae im",
    "im sungjae": "sung jae im",
    "johnny keefer": "john keefer",
    "cameron cam smith": "cameron smith",
    "fitzpatrick alax": "alex fitzpatrick",
    "jacob bridgemen": "jacob bridgeman",
    "denny mcarthy": "denny mccarthy",
    "michael katrude": "michael kartrude",
}

def resolve_name(name):
    n = norm(name)
    return ALIASES.get(n, n)


# === FORMAT HELPERS ===
def _fmt_golf_score(v):
    if pd.isna(v): return "-"
    n = int(v)
    if n == 999: return "-"
    if n == 998: return "CUT"
    if n == 0: return "E"
    if n > 0: return f"+{n}"
    return str(n)

def _fmt_thru(v):
    if pd.isna(v): return "-"
    try:
        n = int(v)
        if n >= 18: return "F"
        return str(n)
    except (ValueError, TypeError):
        return str(v)

def _fmt_own_pct(v):
    if pd.isna(v): return "-"
    return f"{int(v)}%"

def score_to_int(score_str):
    s = str(score_str).strip()
    if s == "E": return 0
    if s in ("-", "", "None"): return None
    try: return int(s)
    except ValueError: return None

def force_numeric_cols(df):
    for col in ["Score", "Points", "Pool Pts", "Own %", "Pts/$"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(999).astype(int)
    if "Thru" in df.columns:
        df["Thru"] = pd.to_numeric(df["Thru"], errors="coerce").astype("Int64")
    return df


def golf_dataframe(df, height=None, **kwargs):
    display = df.copy()
    display = display[[c for c in display.columns if not c.startswith("_")]]
    for col in ["Score", "Points", "Pool Pts", "Own %", "Pts/$"]:
        if col in display.columns:
            display[col] = pd.to_numeric(display[col], errors="coerce").astype("Int64")

    if "tee_time" in display.columns and "Thru" in display.columns:
        tee_map = {}
        for idx, row in display.iterrows():
            tt = row.get("tee_time", "")
            thru = row.get("Thru")
            if tt and (pd.isna(thru) or thru is None or thru == 0):
                tee_map[idx] = tt
        display = display.drop(columns=["tee_time"])
    else:
        tee_map = {}
        if "tee_time" in display.columns:
            display = display.drop(columns=["tee_time"])

    if "Thru" in display.columns:
        def _thru_to_int(v):
            if pd.isna(v) or v is None: return 0
            try:
                n = int(v)
                return 19 if n >= 18 else n
            except (ValueError, TypeError): return 0
        display["Thru"] = display["Thru"].apply(_thru_to_int).astype("Int64")

    if tee_map:
        for idx, tee_str in tee_map.items():
            if idx in display.index and "Thru" in display.columns:
                m = re.search(r'T(\d{1,2}):(\d{2})\s*(AM|PM)', tee_str)
                if m:
                    hr = int(m.group(1))
                    mn = int(m.group(2))
                    ap = m.group(3)
                    if ap == 'PM' and hr != 12: hr += 12
                    if ap == 'AM' and hr == 12: hr = 0
                    display.at[idx, "Thru"] = int(20 + hr + mn / 60.0)

    if "Today" in display.columns:
        def _today_to_int(v):
            s = str(v).strip()
            if s.startswith("T") and ("AM" in s or "PM" in s): return 999
            n = score_to_int(s)
            return n if n is not None else 999
        display["Today"] = display["Today"].apply(_today_to_int).astype(int)

    if "_proj_mc" in display.columns and "Today" in display.columns:
        mc_mask = display["_proj_mc"].fillna(False)
        display.loc[mc_mask, "Today"] = 998

    if "_proj_mc" in display.columns:
        proj_mc_mask = display["_proj_mc"].fillna(False)
        if "Golfer" in display.columns:
            display.loc[proj_mc_mask, "Golfer"] = display.loc[proj_mc_mask, "Golfer"] + "  (MC)"
        display = display.drop(columns=["_proj_mc"])

    if "Score" in display.columns:
        display["Score"] = display["Score"].replace(999, pd.NA).astype("Int64")
    if "Today" in display.columns:
        display["Today"] = display["Today"].astype("Int64")

    _thru_tee_display = {}
    if tee_map:
        for idx, tee_str in tee_map.items():
            _thru_tee_display[idx] = tee_str

    if "Thru" in display.columns:
        def _thru_display(idx, val):
            if idx in _thru_tee_display: return _thru_tee_display[idx]
            if pd.isna(val): return "-"
            n = int(val)
            if n == 0: return "-"
            if n == 19: return "F"
            if n >= 20: return "-"
            return str(n)
        display["Thru"] = [_thru_display(idx, display.at[idx, "Thru"]) for idx in display.index]

    fmt = {}
    for col in display.columns:
        if col in ("Score", "Today"): fmt[col] = _fmt_golf_score
        elif col == "Own %": fmt[col] = _fmt_own_pct

    styled = display.style.format(fmt, na_rep="-", precision=0)
    kw = {**kwargs}
    if height: kw["height"] = height
    st.dataframe(styled, **kw)


# === FETCH LIVE LEADERBOARD ===
@st.cache_data(ttl=180)
def fetch_leaderboard():
    url = "https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return None, str(e), None

    golfers = []
    try:
        events = data.get("events", [])
        if not events:
            return None, "No events found in ESPN data", None

        event = None
        for ev in events:
            name_lower = ev.get("name", "").lower()
            if "pga" in name_lower or "quail" in name_lower or "championship" in name_lower:
                event = ev
                break
        if event is None:
            event = events[0]

        event_name = event.get("name", "Unknown Event")
        competitions = event.get("competitions", [])
        if not competitions:
            return None, f"No competitions in event: {event_name}", None

        competitors = competitions[0].get("competitors", [])

        raw_golfers = []
        for idx, comp in enumerate(competitors):
            athlete = comp.get("athlete", {})
            name = athlete.get("displayName", "Unknown")
            order = comp.get("order", idx + 1)
            score_raw = comp.get("score", "-")
            score_display = str(score_raw) if score_raw else "-"

            status_info = comp.get("status", {})
            status_type = status_info.get("type", {}).get("name", "") if isinstance(status_info, dict) else ""
            status = status_type.upper() if status_type.upper() in ("CUT", "MC", "WD", "DQ") else None

            thru = None
            tee_time_str = ""
            linescores = comp.get("linescores", [])

            # Find the active round (last round with actual holes played)
            current_round = None
            if linescores:
                for rd in reversed(linescores):
                    if rd.get("linescores", []):
                        current_round = rd
                        break
                if current_round is None:
                    # No holes played yet — use first round for tee time
                    current_round = linescores[0]

            if current_round:
                hole_scores = current_round.get("linescores", [])
                if hole_scores:
                    thru = min(len(hole_scores), 18)
                else:
                    stats = current_round.get("statistics", {})
                    cats = stats.get("categories", []) if stats else []
                    for cat in cats:
                        for s in cat.get("stats", []):
                            dv = s.get("displayValue", "")
                            if any(tz in dv for tz in ("AM", "PM", "PDT", "PST", "EDT", "EST")):
                                try:
                                    cleaned = dv
                                    for tz in (" PDT ", " PST ", " EDT ", " EST ", " CDT ", " CST "):
                                        cleaned = cleaned.replace(tz, " ")
                                    dt = __import__("datetime").datetime.strptime(cleaned, "%a %b %d %H:%M:%S %Y")
                                    h = dt.hour
                                    ampm = "AM" if h < 12 else "PM"
                                    if h > 12: h -= 12
                                    if h == 0: h = 12
                                    tee_time_str = f"T{h}:{dt.minute:02d} {ampm}"
                                except Exception:
                                    pass

            today = tee_time_str if tee_time_str else "-"
            if current_round:
                today_val = current_round.get("displayValue", "-")
                if today_val and today_val != "-":
                    today = today_val

            raw_golfers.append({
                "name": name, "name_norm": resolve_name(name),
                "order": order, "status": status, "score": score_display,
                "today": today, "thru": thru, "tee_time": tee_time_str,
            })

        active = [g for g in raw_golfers if g["status"] is None]
        inactive = [g for g in raw_golfers if g["status"] is not None]

        pos = 1
        i = 0
        while i < len(active):
            j = i
            while j < len(active) and active[j]["score"] == active[i]["score"]:
                j += 1
            tied = j - i > 1
            for k in range(i, j):
                active[k]["pos_int"] = pos
                active[k]["pos_str"] = f"T{pos:02d}" if tied else f"{pos:02d}"
            pos = j + 1
            i = j

        for g in active:
            golfers.append({
                "name": g["name"], "name_norm": g["name_norm"],
                "pos_str": g["pos_str"], "pos_int": g["pos_int"],
                "status": None, "score": g["score"], "today": g["today"],
                "thru": g["thru"], "tee_time": g.get("tee_time", ""),
                "points": points_for_position(g["pos_int"], None),
                "proj_mc": False,
            })

        for g in inactive:
            golfers.append({
                "name": g["name"], "name_norm": g["name_norm"],
                "pos_str": g["status"] or "-", "pos_int": None,
                "status": g["status"], "score": g["score"],
                "today": g.get("today", "-"), "thru": g["thru"],
                "tee_time": g.get("tee_time", ""),
                "points": 0, "proj_mc": True,
            })
    except Exception as e:
        return None, f"Parse error: {e}", None

    return golfers, event_name, None


# === LOAD ROSTERS ===
@st.cache_data(ttl=300)
def load_rosters():
    df = pd.read_csv(ROSTER_PATH, encoding="utf-8")
    df["Golfer_Norm"] = df["Golfer"].apply(resolve_name)
    return df


# === COMPUTE SCORES ===
def compute_pool_scores(rosters, golfers_live):
    live_lookup = {g["name_norm"]: g for g in golfers_live}
    live_names = list(live_lookup.keys())

    def best_match(roster_norm):
        if roster_norm in live_lookup:
            return live_lookup[roster_norm]
        roster_parts = set(roster_norm.split())
        for ln in live_names:
            if len(roster_parts & set(ln.split())) >= 2:
                return live_lookup[ln]
        for ln in live_names:
            if roster_norm.split()[-1] == ln.split()[-1] and len(roster_norm.split()[-1]) > 3:
                return live_lookup[ln]
        for ln in live_names:
            r_parts = roster_norm.split()
            l_parts = ln.split()
            if len(r_parts) >= 2 and len(l_parts) >= 2:
                if r_parts[0] == l_parts[0] and r_parts[-1][:3] == l_parts[-1][:3]:
                    return live_lookup[ln]
        return None

    participant_scores = []
    participant_details = {}

    for participant, group in rosters.groupby("Participant"):
        total_pts = 0
        golfer_details = []
        for _, row in group.iterrows():
            match = best_match(row["Golfer_Norm"])
            if match:
                pts = match["points"]
                golfer_details.append({
                    "Golfer": row["Golfer"], "Price": f"${row['Price']:.2f}",
                    "Position": match["pos_str"], "_pos_sort": match["pos_int"] or 999,
                    "_proj_mc": match.get("proj_mc", False),
                    "Score": score_to_int(match["score"]),
                    "Today": match.get("today", "-"), "Thru": match["thru"],
                    "tee_time": match.get("tee_time", ""), "Points": pts,
                })
            else:
                golfer_details.append({
                    "Golfer": row["Golfer"], "Price": f"${row['Price']:.2f}",
                    "Position": "-", "_pos_sort": 999, "_proj_mc": True,
                    "Score": score_to_int("-"), "Today": "-", "Thru": None,
                    "tee_time": "", "Points": 0,
                })
            total_pts += golfer_details[-1]["Points"]

        making_cut = sum(1 for g in golfer_details if not g.get("_proj_mc", False))
        participant_scores.append({
            "Participant": participant, "Points": total_pts,
            "Golfers": len(group), "Making Cut": making_cut,
        })
        participant_details[participant] = sorted(
            golfer_details, key=lambda x: (-x["Points"], x["Score"] if x["Score"] is not None else 999, x["_pos_sort"]))

    df_scores = pd.DataFrame(participant_scores).sort_values("Points", ascending=False).reset_index(drop=True)

    ranks = []
    pos = 1
    i = 0
    pts_list = df_scores["Points"].tolist()
    while i < len(pts_list):
        j = i
        while j < len(pts_list) and pts_list[j] == pts_list[i]:
            j += 1
        tied = j - i > 1
        for k in range(i, j):
            ranks.append(f"T{pos}" if tied else str(pos))
        pos = j + 1
        i = j
    df_scores.insert(0, "Rank", ranks)
    return df_scores, participant_details


# === MAIN ===
def main():
    st.markdown("# ⛳ PGA Championship Pool 2026")

    rosters = load_rosters()
    n_participants = rosters["Participant"].nunique()
    st.markdown(f"##### Live Scoring Leaderboard — {n_participants} Participants")

    result = fetch_leaderboard()
    if result is None or result[0] is None:
        st.error(f"Could not fetch leaderboard: {result[1] if result else 'Unknown error'}")
        st.info("The leaderboard will appear once tournament data is available from ESPN.")
        return
    golfers_live, event_info, _ = result

    st.caption(f"**{event_info}** | Updated: {datetime.now(timezone.utc).strftime('%I:%M %p UTC')} | Auto-refreshes every 3 min")

    df_scores, participant_details = compute_pool_scores(rosters, golfers_live)

    # PODIUM
    if len(df_scores) >= 3:
        st.markdown("### Podium")
        cols = st.columns(3)
        medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
        for i, col in enumerate(cols):
            row = df_scores.iloc[i]
            col.metric(label=f"{medals[i]} {row['Participant']}", value=f"{row['Points']} pts", delta=f"{row['Golfers']} golfers")
    st.markdown("")

    # LEADERBOARD + ROSTER DETAIL
    st.markdown("### 📊 Full Pool Leaderboard")
    st.caption("Select a participant to view their roster below")
    participant_list = df_scores["Participant"].tolist()
    selected = st.selectbox("🔍 Find participant:", ["-- Show All --"] + participant_list)

    st.dataframe(
        df_scores if selected == "-- Show All --" or not selected else df_scores,
        use_container_width=True,
        height=min(700, 35 * min(len(df_scores), 20) + 38),
        hide_index=True,
    )

    if selected and selected != "-- Show All --" and selected in participant_details:
        st.markdown("---")
        detail_df = pd.DataFrame(participant_details[selected]).drop(columns=["_pos_sort"], errors="ignore")
        detail_df = force_numeric_cols(detail_df)
        total = detail_df["Points"].sum()
        rank_row = df_scores[df_scores["Participant"] == selected]
        rank_str = rank_row["Rank"].values[0] if len(rank_row) > 0 else "?"
        st.markdown(f"### 🔎 {selected}")
        st.markdown(f"**Rank {rank_str}** — {len(detail_df)} golfers — **{total} points**")
        golf_dataframe(detail_df, use_container_width=True, hide_index=True)

    # TOURNAMENT LEADERBOARD + OWNERSHIP
    st.markdown("### ⛳ PGA Championship Leaderboard & Ownership (Full Field)")
    top_golfers = sorted(golfers_live, key=lambda x: (x["pos_int"] if x["pos_int"] else 999))

    # Pre-build ownership counts (O(n) instead of O(n*m))
    ownership_exact = rosters.groupby("Golfer_Norm")["Participant"].nunique().to_dict()
    roster_norms_by_participant = rosters.groupby("Participant")["Golfer_Norm"].apply(set).to_dict()

    def count_owners(gn):
        count = 0
        gp = set(gn.split())
        for participant, golfer_norms in roster_norms_by_participant.items():
            for rn in golfer_norms:
                if rn == gn or len(set(rn.split()) & gp) >= 2:
                    count += 1
                    break
        return count

    combined_rows = []
    for g in top_golfers:
        gn = g["name_norm"]
        count = ownership_exact.get(gn, 0)
        if count == 0:
            count = count_owners(gn)
        combined_rows.append({
            "#": g["pos_int"] if g["pos_int"] else 999,
            "_proj_mc": g.get("proj_mc", False),
            "Pos": g["pos_str"], "Golfer": g["name"],
            "Score": score_to_int(g["score"]), "Today": g.get("today", "-"),
            "Thru": g["thru"], "tee_time": g.get("tee_time", ""),
            "Pool Pts": g["points"],
            "Rostered": f"{count}/{n_participants}",
            "Own %": round(count / n_participants * 100),
        })
    combined_df = pd.DataFrame(combined_rows).sort_values(["#"]).drop(columns=["#"]).reset_index(drop=True)
    combined_df = force_numeric_cols(combined_df)
    golf_dataframe(combined_df, use_container_width=True, hide_index=True)

    # BEST VALUE PICKS
    st.markdown("### 💰 Best Value Picks (Points per Dollar)")
    roster_price_lookup = rosters.drop_duplicates("Golfer_Norm").set_index("Golfer_Norm")["Price"].to_dict()
    all_roster_norms = set(roster_price_lookup.keys())
    value_picks = []
    seen = set()
    for g in golfers_live:
        if g["points"] <= 0: continue
        gn = g["name_norm"]
        price = roster_price_lookup.get(gn)
        if price is None:
            gp = set(gn.split())
            for rn in all_roster_norms:
                if len(set(rn.split()) & gp) >= 2:
                    price = roster_price_lookup[rn]
                    break
        if price and price > 0 and g["name"] not in seen:
            value_picks.append({
                "Golfer": g["name"], "Score": score_to_int(g["score"]),
                "Pool Pts": g["points"], "Price": f"${price:.2f}",
                "Pts/$": round(g["points"] / price, 1),
            })
            seen.add(g["name"])
    if value_picks:
        value_picks.sort(key=lambda x: x["Pts/$"], reverse=True)
        vp_df = force_numeric_cols(pd.DataFrame(value_picks[:12]))
        golf_dataframe(vp_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.caption("PGA Championship Pool 2026 | Scoring: W=90, 2nd=65, 3rd=60, 4th=55, 5th=50, 6-10=45-25, 11-15=20, 16-20=15, 21-25=10, 26-30=5, 31+=2, MC=0")
    st.caption("Data: ESPN | Built with Streamlit | Auto-refreshes every 3 minutes")


if __name__ == "__main__":
    main()
