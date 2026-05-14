"""Export PGA Championship Pool Rosters 2026 from Excel to flat CSV."""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import os

DIR = os.path.dirname(__file__)
XLSX = os.path.join(DIR, 'PGA Championship Pool Rosters 2026.xlsx')
OUT = os.path.join(DIR, 'rosters.csv')

df = pd.read_excel(XLSX, header=None)
print(f"Sheet shape: {df.shape}")

rows_out = []

# Scan every column for participant headers (flexible stride)
for col in range(df.shape[1]):
    for row in range(df.shape[0] - 1):
        val = df.iloc[row, col]
        next_val = df.iloc[row + 1, col]
        if (pd.notna(val) and isinstance(val, str) and val.strip()
            and pd.notna(next_val) and str(next_val).strip() == 'Name'):
            raw = val.strip()
            if raw.startswith('PGA Championship'):
                continue
            participant = raw.replace(' - pd', '').replace(' -pd', '').strip()
            price_col = col + 1
            r = row + 2
            while r < df.shape[0]:
                gval = df.iloc[r, col]
                if pd.notna(gval) and str(gval).strip() == 'TOTAL':
                    break
                if pd.notna(gval) and isinstance(gval, str) and gval.strip():
                    golfer_raw = gval.strip()
                    price_val = df.iloc[r, price_col] if price_col < df.shape[1] else None
                    try:
                        price = float(price_val)
                    except (ValueError, TypeError):
                        price = 0.0
                    if '. ' in golfer_raw and ',' not in golfer_raw:
                        golfer_raw = golfer_raw.replace('. ', ', ', 1)
                    parts = golfer_raw.split(', ')
                    if len(parts) == 2:
                        golfer_name = f"{parts[1].strip()} {parts[0].strip()}"
                    else:
                        golfer_name = golfer_raw
                    golfer_name = golfer_name.replace('(cp)', '').replace('(pc)', '').strip()
                    rows_out.append({
                        'Participant': participant,
                        'Golfer': golfer_name,
                        'Price': price,
                    })
                r += 1

CLUB_PRO_GOLFERS = [
    "Derek Berg", "Francisco Bide", "Michael Block", "Tyler Collet",
    "Jesse Droemer", "Bryce Fisher", "Chris Gabriele", "Mark Geddes",
    "Zach Haynes", "Austin Hurt", "Jared Jones", "Michael Katrude",
    "Ben Kern", "Ryan Lenahan", "Paul McClure", "Ben Polland",
    "Garrett Sapp", "Braden Shattuck", "Ryan Vermeer", "Timothy Wiseman",
]
PAST_CHAMP_GOLFERS = [
    "Stewart Cink", "Martin Kaymer", "Luke Donald", "Jimmy Walker",
    "Jason Dufner", "Shaun Micheel", "Y.E. Yang",
]

expanded = []
for r in rows_out:
    golfer = r['Golfer']
    if 'club pro' in golfer.lower() or 'club pro pod' in golfer.lower():
        for cp in CLUB_PRO_GOLFERS:
            expanded.append({'Participant': r['Participant'], 'Golfer': cp, 'Price': round(r['Price'] / len(CLUB_PRO_GOLFERS), 4)})
    elif 'past champ' in golfer.lower() or 'past champs' in golfer.lower():
        for pc in PAST_CHAMP_GOLFERS:
            expanded.append({'Participant': r['Participant'], 'Golfer': pc, 'Price': round(r['Price'] / len(PAST_CHAMP_GOLFERS), 4)})
    else:
        expanded.append(r)

out_df = pd.DataFrame(expanded)
participants = out_df['Participant'].nunique()
print(f"Participants: {participants}")
print(f"Total roster entries: {len(out_df)} (after pod expansion)")
out_df.to_csv(OUT, index=False, encoding='utf-8')
print(f"Saved: {OUT}")

for p in sorted(out_df['Participant'].unique()):
    count = len(out_df[out_df['Participant'] == p])
    cost = out_df[out_df['Participant'] == p]['Price'].sum()
    print(f"  {p}: {count} golfers, ${cost:.2f}")
