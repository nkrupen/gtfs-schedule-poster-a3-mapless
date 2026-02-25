import pandas as pd
import zipfile
import os
import io
import re
import urllib.parse
import warnings
from datetime import datetime, timedelta
import subprocess
import shutil

warnings.filterwarnings("ignore")

class GTFSSchedulePoster:
    def __init__(self, gtfs_path):
        self.gtfs_path = gtfs_path
        self.data = {}
        self._load_data()

    def _load_data(self):
        print(f"Loading GTFS data from {self.gtfs_path}...")
        try:
            with zipfile.ZipFile(self.gtfs_path, "r") as z:
                def load_csv(name):
                    if name in z.namelist():
                        with z.open(name) as f:
                            content = f.read()
                            try:
                                text = content.decode("utf-8-sig")
                            except:
                                text = content.decode("latin1")
                            sep = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
                            df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str)
                            df.columns = df.columns.str.lower().str.strip()
                            return df
                    return pd.DataFrame()

                for table in ["stops", "stop_times", "trips", "routes", "calendar", "calendar_dates"]:
                    self.data[table] = load_csv(f"{table}.txt")
        except FileNotFoundError:
            print(f"❌ Error: {self.gtfs_path} not found.")

    def _get_active_trips(self, stop_id, mon_dt):
        sun_dt = mon_dt + timedelta(days=6)
        st, trips = self.data["stop_times"], self.data["trips"]
        visits = st[st["stop_id"] == str(stop_id)]
        
        valid_sids = {}
        for sid in trips["service_id"].unique():
            active = [False] * 7
            cal = self.data["calendar"]
            if not cal.empty:
                r = cal[cal["service_id"] == sid]
                if not r.empty:
                    r = r.iloc[0]
                    s_dt = datetime.strptime(r["start_date"], "%Y%m%d")
                    e_dt = datetime.strptime(r["end_date"], "%Y%m%d")
                    if not (e_dt < mon_dt or s_dt > sun_dt):
                        days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
                        for i, d in enumerate(days):
                            if r.get(d) == "1": active[i] = True
            
            cd = self.data["calendar_dates"]
            if not cd.empty:
                for _, r in cd[cd["service_id"] == sid].iterrows():
                    dt = datetime.strptime(r["date"], "%Y%m%d")
                    if mon_dt <= dt <= sun_dt:
                        wd = dt.weekday()
                        if r["exception_type"] == "1": active[wd] = True
                        elif r["exception_type"] == "2": active[wd] = False
            
            if any(active): valid_sids[sid] = tuple(active)

        active_df = trips[trips["trip_id"].isin(visits["trip_id"]) & trips["service_id"].isin(valid_sids.keys())].copy()
        active_df["pattern"] = active_df["service_id"].map(valid_sids)
        return active_df

    def generate_html_content(self, stop_id, s_mon, h_mon):
        visits = self.data["stop_times"][self.data["stop_times"]["stop_id"] == str(stop_id)]
        
        def process(mon_dt, tag):
            df = self._get_active_trips(stop_id, mon_dt)
            if df.empty: return []
            m = visits.merge(df, on="trip_id").merge(self.data["routes"], on="route_id")
            return [{"h": int(r["arrival_time"].split(":")[0]), "m": int(r["arrival_time"].split(":")[1]), 
                     "line": r["route_short_name"], "pat": r["pattern"], "type": tag} for _, r in m.iterrows()]

        all_deps = process(s_mon, "S") + process(h_mon, "H")
        merged = {}
        for d in all_deps:
            key = (d["h"], d["m"], d["line"])
            if key not in merged: merged[key] = {"S": None, "H": None, "h": d["h"], "m": d["m"], "line": d["line"]}
            merged[key][d["type"]] = d["pat"]

        final_rows, mon_fri_fns, next_fn = [], {}, 1
        for k, info in merged.items():
            pat = info["S"] or info["H"]
            t = "NORMAL"
            if info["S"] and not info["H"]: t = "SCHOOL"
            elif not info["S"] and info["H"]: t = "HOLIDAY"
            
            mf = pat[0:5]
            fn = None
            if any(mf) and not all(mf):
                if mf not in mon_fri_fns: mon_fri_fns[mf] = next_fn; next_fn += 1
                fn = mon_fri_fns[mf]
            
            if any(mf): final_rows.append({"b": "Mon-Fri", "h": info["h"], "m": info["m"], "line": info["line"], "fn": fn, "t": t})
            if pat[5]: final_rows.append({"b": "Sat", "h": info["h"], "m": info["m"], "line": info["line"], "fn": None, "t": "NORMAL"})
            if pat[6]: final_rows.append({"b": "Sun", "h": info["h"], "m": info["m"], "line": info["line"], "fn": None, "t": "NORMAL"})

        html_blocks = {}
        for b in ["Mon-Fri", "Sat", "Sun"]:
            rows = sorted([r for r in final_rows if r["b"] == b], key=lambda x: (x["h"], x["m"]))
            h_map = {}
            for r in rows:
                bg = "#E3F2FD" if r["t"]=="SCHOOL" else ("#FFF3E0" if r["t"]=="HOLIDAY" else "transparent")
                fn = f"<sup>{r['fn']})</sup>" if r["fn"] else ""
                h_map.setdefault(r["h"], []).append(f"<span style='background:{bg}; padding:2px; border-radius:4px;'><b>{r['m']:02d}</b>{fn}/{r['line']}</span>")
            
            res = ""
            for h in sorted(h_map.keys()):
                res += f"<div style='display:flex; border-bottom:1px solid #ddd; padding:4px;'><div style='width:70px; font-weight:bold;'>{h:02d}</div><div style='display:flex; flex-wrap:wrap; gap:10px;'>{' '.join(h_map[h])}</div></div>"
            html_blocks[b] = res or "Ei vuoroja"

        legend = "<div style='font-size:1.5em; margin-top:20px;'>"
        for p, fid in sorted(mon_fri_fns.items(), key=lambda x: x[1]):
            days = ["ma","ti","ke","to","pe"]
            active_days = [days[i] for i, v in enumerate(p) if v]
            legend += f"<div><b>{fid})</b> vain {', '.join(active_days)}</div>"
        legend += "</div>"
        
        return html_blocks, legend

    def generate_poster(self, stop_id, city, label, s_mon, h_mon):
        stop_row = self.data["stops"][self.data["stops"]["stop_id"]==str(stop_id)].iloc[0]
        name = stop_row["stop_name"]
        zone = stop_row.get("zone_id", "A")
        blocks, legend = self.generate_html_content(stop_id, s_mon, h_mon)
        
        # YOUR PRECISE DESIGN
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="UTF-8">
        <style>
            @page {{ size: 800mm 1131mm; margin: 0; }}
            body {{ margin: 0; font-family: Arial, sans-serif; background: #3069b3; }}
            .poster {{ width: 800mm; height: 1131mm; display: flex; flex-direction: column; }}
            .header {{ padding: 60px; color: white; display: flex; justify-content: space-between; align-items: flex-start; }}
            .h-stop-name {{ font-size: 8em; font-weight: bold; }}
            .content {{ background: white; margin: 40px; padding: 60px; border-radius: 60px; flex-grow: 1; font-size: 32px; line-height: 1.2; }}
            .sc-title {{ font-size: 2.5em; font-weight: bold; border-bottom: 8px solid black; margin-bottom: 30px; margin-top: 40px; }}
            .footer {{ position: relative; height: 200px; margin-top: 40px; }}
            .qr {{ position: absolute; right: 20px; bottom: 20px; width: 250px; height: 250px; background: white; padding: 15px; border-radius: 30px; }}
        </style>
        </head>
        <body>
            <div class="poster">
                <div class="header">
                    <div>
                        <div class="h-stop-name">{name}</div>
                        <div style="font-size: 3em; margin-top: 20px;">Voimassa / Valid: {label}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 6em; font-weight: bold;">{zone}</div>
                        <div style="font-size: 3em;">Pysäkki: {stop_id}</div>
                    </div>
                </div>
                <div class="content">
                    <div class="sc-title" style="margin-top:0;">Maanantai&ndash;perjantai / Monday&ndash;Friday</div>
                    {blocks['Mon-Fri']}
                    {legend}
                    <div style="display: flex; gap: 80px; margin-top: 60px;">
                        <div style="flex: 1;">
                            <div class="sc-title">Lauantai / Saturday</div>
                            {blocks['Sat']}
                        </div>
                        <div style="flex: 1;">
                            <div class="sc-title">Sunnuntai / Sunday</div>
                            {blocks['Sun']}
                            <div class="footer">
                                <div class="qr"><img src="https://api.qrserver.com/v1/create-qr-code/?data=https://{city}.fi/{stop_id}" style="width:100%;"></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        out_html = f"{stop_id}.html"
        with open(out_html, "w", encoding="utf-8") as f: f.write(html_template)
        subprocess.run(["google-chrome", "--headless", "--no-sandbox", f"--print-to-pdf={stop_id}.pdf", "--no-pdf-header-footer", out_html], check=True)
        return f"{stop_id}.pdf"

# ---------------------------------------------------------
# RUNNING LOGIC
# ---------------------------------------------------------
if __name__ == "__main__":
    GTFS_ZIP = "gtfs.zip"
    if os.path.exists(GTFS_ZIP):
        gen = GTFSSchedulePoster(GTFS_ZIP)
        
        # CAPTURE USER INPUTS
        stops_in = input("Enter stop numbers (comma separated): ")
        city_in = input("Enter city for QR: ")
        label_in = input("Enter date label (e.g. 10.8.2025 alkaen): ")
        s_date_in = datetime.strptime(input("School Monday (YYYY-MM-DD): "), "%Y-%m-%d")
        h_date_in = datetime.strptime(input("Holiday Monday (YYYY-MM-DD): "), "%Y-%m-%d")
        
        output_dir = "posters_output"
        if os.path.exists(output_dir): shutil.rmtree(output_dir)
        os.makedirs(output_dir)

        for s in stops_in.split(","):
            s_id = s.strip()
            print(f"Generating {s_id}...")
            pdf_file = gen.generate_poster(s_id, city_in, label_in, s_date_in, h_date_in)
            shutil.move(pdf_file, os.path.join(output_dir, pdf_file))
        
        shutil.make_archive("posters", 'zip', output_dir)
        print("\n✅ PROCESS COMPLETE. Files are zipped in posters.zip.")
        print("Run the next cell to download.")
    else:
        print("Please upload gtfs.zip first.")
