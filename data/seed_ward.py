"""
seed_ward.py — creates ward.db and imports ward data.
Real data: 2016 (from CSV) for all wards.
Generated data: 2024 + 2025 for Jayanagar (Ward 153) — realistic growth applied.
"""

import sqlite3, os, random

BASE = os.path.dirname(__file__)
DB   = os.path.join(BASE, "ward.db")

con = sqlite3.connect(DB)
con.executescript("""
CREATE TABLE IF NOT EXISTS ward_data (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    year                    INTEGER,
    month                   INTEGER,
    ward_no                 INTEGER,
    ward_name               TEXT,
    building_area_km2       REAL,
    builtup_area_percentage REAL,
    population              INTEGER,
    rainfall                REAL,
    rh2m                    REAL,
    t2m_max                 REAL,
    t2m_min                 REAL,
    ws2m                    REAL,
    gwl                     REAL
);
CREATE INDEX IF NOT EXISTS idx_ward_year_month ON ward_data(year, month, ward_no);
CREATE INDEX IF NOT EXISTS idx_ward_name       ON ward_data(ward_name);
""")

# Wipe existing rows so re-running seed never duplicates
con.execute("DELETE FROM ward_data")
con.commit()

# ── Real 2016 data from CSV ────────────────────────────────────────────────────
real_data = [
    (2016,1,1,"kempegowda ward",0.816510443,7.49,43870,3.774505628,67.23,32.12,10.54,2.13,10.7),
    (2016,1,2,"chowdeswari ward",0.725204196,11.16,49985,3.866512346,67.23,32.12,10.54,2.13,26.18506047),
    (2016,1,3,"atturu",1.397200532,15.88,90428,3.923646701,67.23,32.12,10.54,2.13,24.96046881),
    (2016,1,4,"yelahanka satellite town",0.861904265,18.74,53579,4.050855448,67.23,32.12,10.54,2.13,22.18201133),
    (2016,1,5,"jakkuru",2.108904743,8.97,81956,4.444738603,67.23,32.12,10.54,2.13,25.4105033),
    (2016,1,6,"thanisandra",1.991155232,19.91,134849,5.131646239,67.23,32.12,10.54,2.13,25.77507016),
    (2016,1,7,"byatarayanapura",1.606173903,16.06,109377,5.066293383,67.23,32.12,10.54,2.13,17.15062824),
    (2016,1,9,"vidyaranyapura",1.42716793,14.42,89928,4.891140045,67.23,32.12,10.54,2.13,21.60277354),
    (2016,1,10,"dodda bommasandra",0.789682797,18.8,47201,5.184164493,67.23,32.12,10.54,2.13,24.17674657),
    (2016,1,12,"shettihalli",1.416726031,17.49,89700,4.356368775,67.23,32.12,10.54,2.13,31.1),
    (2016,1,14,"bagalakunte",1.158805349,26.95,98756,3.996750842,67.23,32.12,10.54,2.13,20.8),
    (2016,1,16,"jalahalli",0.768856585,14.79,43401,4.636503079,67.23,32.12,10.54,2.13,24.6),
    (2016,1,18,"radhakrishna temple ward",0.603073985,31.74,40656,5.731424642,67.23,32.12,10.54,2.13,21.02353575),
    (2016,1,19,"sanjaya nagar",0.500802626,33.39,37665,5.731424642,67.23,32.12,10.54,2.13,21.02353575),
    (2016,1,22,"vishwanath nagenahalli",0.655576241,43.71,73103,6.27868479,67.23,32.12,10.54,2.13,17.87032493),
    (2016,1,24,"hbr layout",1.14722258,24.94,79851,5.236820034,67.23,32.12,10.54,2.13,18.83951008),
    (2016,1,25,"horamavu",3.068642999,17.54,175482,4.794966359,67.23,32.12,10.54,2.13,23.8367106),
    (2016,1,26,"ramamurthy nagar",1.533114031,21,69485,4.853055183,67.23,32.12,10.54,2.13,23.20178802),
    (2016,1,27,"banasavadi",1.130288746,33.24,64895,4.661632247,67.23,32.12,10.54,2.13,19.82727379),
    (2016,1,28,"kammanahalli",0.448206786,44.82,54735,4.880090772,67.23,32.12,10.54,2.13,13.53092415),
    (2016,1,29,"kacharkanahalli",0.600146243,35.3,36136,4.661632247,67.23,32.12,10.54,2.13,19.82727379),
    (2016,1,35,"aramane nagara",1.132699304,15.1,40389,6.669276562,67.23,32.12,10.54,2.13,3),
    (2016,1,36,"mattikere",0.380920236,42.32,37627,7.526545303,67.23,32.12,10.54,2.13,21.45805967),
    (2016,1,38,"hmt ward",1.255802146,24.15,41051,5.808046951,67.23,32.12,10.54,2.13,23.56438497),
    (2016,1,39,"chokkasandra",0.981361439,25.83,83187,4.088841665,67.23,32.12,10.54,2.13,27.12283672),
    (2016,1,40,"dodda bidarakallu",1.925267004,14.92,141193,4.225505632,67.23,32.12,10.54,2.13,24.99215138),
    (2016,1,41,"peenya industrial area",1.724990798,31.36,83877,6.01600777,67.23,32.12,10.54,2.13,23.36026443),
    (2016,1,42,"lakshmi devi nagar",0.430075108,28.67,52579,6.38111538,67.23,32.12,10.54,2.13,22.37823438),
    (2016,1,45,"malleswaram",0.471375315,26.19,33181,7.526545303,67.23,32.12,10.54,2.13,21.45805967),
    (2016,1,48,"muneshwara nagar",0.20914606,41.83,38804,5.345330852,67.23,32.12,10.54,2.13,17.83316781),
    (2016,1,50,"benniganahalli",0.791753606,16.16,60823,4.880090772,67.23,32.12,10.54,2.13,13.53092415),
    (2016,1,51,"vijnanapura",0.59914299,28.53,52943,5.031805756,67.23,32.12,10.54,2.13,17.94597842),
    (2016,1,52,"k r puram",0.904881145,18.85,40525,5.044478119,67.23,32.12,10.54,2.13,26.57630225),
    (2016,1,53,"basavanapura",1.181970664,18.76,72181,5.81798217,67.23,32.12,10.54,2.13,22.38583579),
    (2016,1,54,"hudi",1.933070567,12.89,78154,5.272781965,67.23,32.12,10.54,2.13,25.27428905),
    (2016,1,58,"new tippasandara",0.944925044,27.79,49606,5.208228393,67.23,32.12,10.54,2.13,16.10544514),
    (2016,1,65,"kadu malleshwar ward",0.493097923,35.22,36413,7.607128483,67.23,32.12,10.54,2.13,18.28627029),
    (2016,1,68,"mahalakshimpuram",0.379836772,42.2,49684,9.868926113,67.23,32.12,10.54,2.13,18.73937276),
    (2016,1,69,"laggere",0.550009424,34.38,85611,6.979590823,67.23,32.12,10.54,2.13,21.47897829),
    (2016,1,72,"herohalli",1.351383905,17.33,110805,6.950686921,67.23,32.12,10.54,2.13,25.9),
    (2016,1,73,"kottegepalya",1.309737074,22.58,106069,7.821640646,67.23,32.12,10.54,2.13,19.84743105),
    (2016,1,74,"shakthi ganapathi nagar",0.296271914,42.32,49405,6.979590823,67.23,32.12,10.54,2.13,21.47897829),
    (2016,1,77,"dattatreya temple",0.307863598,43.98,32972,7.607128483,67.23,32.12,10.54,2.13,18.28627029),
    (2016,1,78,"pulikeshinagar",0.478688256,28.16,29184,5.345330852,67.23,32.12,10.54,2.13,17.83316781),
    (2016,1,80,"hoysala nagar",0.624352885,29.73,34902,5.253929213,67.23,32.12,10.54,2.13,16.68135269),
    (2016,1,81,"vijnana nagar",1.363220205,23.92,86631,5.08276528,67.23,32.12,10.54,2.13,19.95664236),
    (2016,1,82,"garudachar playa",1.37975324,20.29,76445,6.171110201,67.23,32.12,10.54,2.13,18.06249395),
    (2016,1,83,"kadugodi",1.384228193,12.36,61815,8.159054378,67.23,32.12,10.54,2.13,20.94556972),
    (2016,1,84,"hagadur",1.868155536,14.83,70613,8.140988125,67.23,32.12,10.54,2.13,22.70648437),
    (2016,1,85,"dodda nekkundi",2.395965263,19.97,106782,6.352029945,67.23,32.12,10.54,2.13,22.40020636),
    (2016,1,86,"marathahalli",0.747464922,24.11,52883,5.133724804,67.23,32.12,10.54,2.13,21.96730629),
    (2016,1,87,"hal airport",1.013149282,14.9,43873,5.133724804,67.23,32.12,10.54,2.13,21.96730629),
    (2016,1,90,"halsoor",0.394650703,23.21,34696,5.569020687,67.23,32.12,10.54,2.13,15.76424247),
    (2016,1,93,"vasanth nagar",0.697240071,22.49,21525,7.607128483,67.23,32.12,10.54,2.13,18.28627029),
    (2016,1,94,"gandhinagar",0.517977772,27.26,29339,7.32873772,67.23,32.12,10.54,2.13,16.12774876),
    (2016,1,96,"okalipuram",0.295201916,36.9,39279,9.868926113,67.23,32.12,10.54,2.13,18.73937276),
    (2016,1,104,"govindaraja nagar",0.279028757,34.88,27440,8.727662459,67.23,32.12,10.54,2.13,16.83245771),
    (2016,1,110,"sampangiram nagar",0.871079114,19.8,25064,5.929812981,67.23,32.12,10.54,2.13,15.4230398),
    (2016,1,112,"domlur",0.550461182,32.38,28788,5.536366014,67.23,32.12,10.54,2.13,18.67996612),
    (2016,1,114,"agaram",0.746257394,6.78,37575,6.751735944,67.23,32.12,10.54,2.13,14.73501602),
    (2016,1,119,"dharmaraya swamy temple",0.433313525,39.39,24452,7.050346957,67.23,32.12,10.54,2.13,13.96922723),
    (2016,1,124,"hosahalli",0.333343407,37.04,40282,7.586398804,67.23,32.12,10.54,2.13,14.92554266),
    (2016,1,126,"maruthi mandir ward",0.325545732,40.69,34014,8.546069549,67.23,32.12,10.54,2.13,15.75493962),
    (2016,1,128,"nagarabhavi",0.456378591,28.52,47538,8.546069549,67.23,32.12,10.54,2.13,15.75493962),
    (2016,1,129,"jnana bharathi ward",1.907018274,16.03,110527,6.797997913,67.23,32.12,10.54,2.13,20.4014602),
    (2016,1,130,"ullalu",1.340874648,15.41,98465,9.996375077,67.23,32.12,10.54,2.13,18.53586893),
    (2016,1,143,"vishveshwara puram",0.600131161,24.01,30786,7.050346957,67.23,32.12,10.54,2.13,13.96922723),
    (2016,1,144,"siddapura",0.24079122,34.4,36304,6.51429511,67.23,32.12,10.54,2.13,13.01291179),
    (2016,1,145,"hombegowda nagara",0.49384872,35.27,39271,6.51429511,67.23,32.12,10.54,2.13,13.01291179),
    (2016,1,147,"adugodi",0.298018371,18.63,36708,6.51429511,67.23,32.12,10.54,2.13,13.01291179),
    (2016,1,149,"varthuru",2.035875914,7.19,80637,6.713925416,67.23,32.12,10.54,2.13,29.49454389),
    (2016,1,150,"bellanduru",3.702715283,14.03,158470,6.739050741,67.23,32.12,10.54,2.13,29.425),
    (2016,1,153,"jayanagar",0.613730794,24.55,39294,7.050346957,67.23,32.12,10.54,2.13,13.96922723),
    (2016,1,154,"basavanagudi",0.467493204,38.96,31073,7.586398804,67.23,32.12,10.54,2.13,14.92554266),
    (2016,1,157,"gali anjenaya temple ward",0.445422692,40.49,39068,7.586398804,67.23,32.12,10.54,2.13,14.92554266),
    (2016,1,158,"deepanjali nagar",0.590377815,28.11,55972,7.586398804,67.23,32.12,10.54,2.13,14.92554266),
    (2016,1,159,"kengeri",0.746648735,14.64,52202,10.61635075,67.23,32.12,10.54,2.13,18.57517702),
]

con.executemany("""
    INSERT INTO ward_data
    (year,month,ward_no,ward_name,building_area_km2,builtup_area_percentage,
     population,rainfall,rh2m,t2m_max,t2m_min,ws2m,gwl)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
""", real_data)
print(f"✓ Inserted {len(real_data)} real 2016 rows")

# ── Generate 2024 + 2025 monthly data for Jayanagar (Ward 153) ────────────────
# Basis: 2016 Jan values for Jayanagar
# Growth assumptions (8 years 2016→2024):
#   Population:           +1.8% per year (Bangalore growth rate)
#   Builtup area %:       +0.4% per year (densification)
#   Building area km2:    unchanged (ward boundary fixed)
#   GWL:                  declining ~0.5m per year (groundwater depletion trend)
#   T2M_MAX:              +0.15°C per year (urban heat island)
#   T2M_MIN:              +0.12°C per year
#   RH2M:                 slight decline -0.1 per year
#   WS2M:                 stable ±noise

# Monthly rainfall pattern for Bangalore (mm) — seasonal
RAINFALL_PATTERN = {
    1: 2.1,  2: 4.3,  3: 9.8,  4: 38.5,
    5: 97.2, 6:112.4, 7: 88.3, 8: 89.6,
    9:127.4,10: 95.2,11: 35.6,12:  5.8
}
# Monthly temperature patterns
T2M_MAX_PATTERN = {
    1:32.1, 2:34.2, 3:35.8, 4:34.5,
    5:33.1, 6:29.4, 7:28.6, 8:28.9,
    9:29.8,10:28.7,11:28.2,12:29.1
}
T2M_MIN_PATTERN = {
    1:15.2, 2:16.8, 3:19.4, 4:21.2,
    5:21.8, 6:20.1, 7:19.6, 8:19.8,
    9:19.9,10:19.2,11:17.4,12:15.6
}
RH2M_PATTERN = {
    1:62.1, 2:58.3, 3:55.4, 4:62.1,
    5:70.2, 6:82.4, 7:85.6, 8:84.3,
    9:83.1,10:79.4,11:72.3,12:65.2
}

jayanagar_2016 = {
    "ward_no":153, "ward_name":"jayanagar",
    "building_area_km2":0.613730794,
    "builtup_area_percentage":24.55,
    "population":39294,
    "gwl":13.96922723,
    "ws2m":2.13
}

rows_generated = 0
random.seed(42)

for year in [2024, 2025]:
    years_from_2016 = year - 2016
    pop   = int(jayanagar_2016["population"] * (1.018 ** years_from_2016))
    builtup = min(99.0, round(jayanagar_2016["builtup_area_percentage"] + 0.4 * years_from_2016, 2))
    # GWL declines with more variability in recent years
    gwl_base = round(jayanagar_2016["gwl"] - 0.5 * years_from_2016, 2)

    for month in range(1, 13):
        rainfall  = round(RAINFALL_PATTERN[month] * random.uniform(0.75, 1.25), 3)
        t2m_max   = round(T2M_MAX_PATTERN[month] + 0.15 * years_from_2016 + random.uniform(-0.3, 0.3), 2)
        t2m_min   = round(T2M_MIN_PATTERN[month] + 0.12 * years_from_2016 + random.uniform(-0.2, 0.2), 2)
        rh2m      = round(RH2M_PATTERN[month] - 0.1 * years_from_2016 + random.uniform(-1.5, 1.5), 2)
        ws2m      = round(jayanagar_2016["ws2m"] + random.uniform(-0.3, 0.3), 2)
        # GWL higher in monsoon months (recharge), lower in dry months
        monsoon_bonus = 2.5 if month in [6,7,8,9] else 0
        gwl = round(gwl_base + monsoon_bonus + random.uniform(-0.8, 0.8), 2)

        con.execute("""
            INSERT INTO ward_data
            (year,month,ward_no,ward_name,building_area_km2,builtup_area_percentage,
             population,rainfall,rh2m,t2m_max,t2m_min,ws2m,gwl)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (year, month, 153, "jayanagar",
              jayanagar_2016["building_area_km2"],
              builtup, pop, rainfall,
              rh2m, t2m_max, t2m_min, ws2m, gwl))
        rows_generated += 1

print(f"✓ Generated {rows_generated} rows for Jayanagar 2024–2025")
con.commit()
con.close()

# Quick verification
con = sqlite3.connect(DB)
total = con.execute("SELECT COUNT(*) FROM ward_data").fetchone()[0]
jayanagar_count = con.execute(
    "SELECT COUNT(*) FROM ward_data WHERE ward_name='jayanagar'"
).fetchone()[0]
years = con.execute(
    "SELECT DISTINCT year FROM ward_data WHERE ward_name='jayanagar' ORDER BY year"
).fetchall()
con.close()

print(f"\n✓ ward.db ready — {total} total rows")
print(f"  Jayanagar: {jayanagar_count} rows across years {[r[0] for r in years]}")
