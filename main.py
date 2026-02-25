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

        final_rows, mon_fri_fns, has_s, has_h, next_fn = [], {}, False, False, 1
        for k, info in merged.items():
            pat = info["S"] or info["H"]
            t = "NORMAL"
            if info["S"] and not info["H"]: t, has_s = "SCHOOL", True
            elif not info["S"] and info["H"]: t, has_h = "HOLIDAY", True
            
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
                res += f"<div style='display:flex; border-bottom:1px solid #ddd; padding:4px;'><div style='width:50px; font-weight:bold;'>{h:02d}</div><div style='display:flex; flex-wrap:wrap; gap:10px;'>{' '.join(h_map[h])}</div></div>"
            html_blocks[b] = res

        legend = "<div style='font-size:0.8em; margin-top:10px;'>"
        for p, fid in sorted(mon_fri_fns.items(), key=lambda x: x[1]):
            days = ["ma","ti","ke","to","pe"]
            active_days = [days[i] for i, v in enumerate(p) if v]
            legend += f"<div><b>{fid})</b> vain {', '.join(active_days)}</div>"
        if has_s: legend += "<div><span style='background:#E3F2FD;'>&nbsp;&nbsp;</span> = vain koulupäivinä</div>"
        if has_h: legend += "<div><span style='background:#FFF3E0;'>&nbsp;&nbsp;</span> = vain lomapäivinä</div>"
        legend += "</div>"
        
        return html_blocks, legend

    def generate_poster(self, stop_id, city, label, s_mon, h_mon):
        name = self.data["stops"][self.data["stops"]["stop_id"]==str(stop_id)].iloc[0]["stop_name"]
        zone = self.data["stops"][self.data["stops"]["stop_id"]==str(stop_id)].iloc[0].get("zone_id", "A")
        blocks, legend = self.generate_html_content(stop_id, s_mon, h_mon)
        
        with open("templates/poster_template.html", "r") as f:
            html = f.read()

        replacements = {
            "{{ stop_name }}": name,
            "{{ date_label }}": label,
            "{{ stop_zone }}": zone,
            "{{ monfri_html }}": blocks["Mon-Fri"],
            "{{ saturday_html }}": blocks["Sat"],
            "{{ sunday_html }}": blocks["Sun"],
            "{{ legend_html }}": legend,
            "{{ font_size }}": "22px",
            "{{ line_height }}": "1.2",
            "{{ stop_number_html }}": f"<div>Pysäkki: {stop_id}</div>",
            "{{ qr_img_url }}": f"https://api.qrserver.com/v1/create-qr-code/?data=https://{city}.fi/{stop_id}",
            "{{ logo_html }}": "",
            "{{ alareuna_svg_inline }}": ""
        }

        for k, v in replacements.items():
            html = html.replace(k, str(v))

        out_html = f"{stop_id}.html"
        with open(out_html, "w") as f: f.write(html)
        subprocess.run(["google-chrome", "--headless", "--no-sandbox", f"--print-to-pdf={stop_id}.pdf", "--no-pdf-header-footer", out_html])
        return f"{stop_id}.pdf"

if __name__ == "__main__":
    if os.path.exists("gtfs.zip"):
        gen = GTFSSchedulePoster("gtfs.zip")
        stops = input("Pysäkit (esim. 155527,155528): ")
        city = input("Kaupunki (QR-koodia varten): ")
        label = input("Voimassaolo (esim. 10.8.2025 alkaen): ")
        s_date = datetime.strptime(input("Kouluviikon ma (YYYY-MM-DD): "), "%Y-%m-%d")
        h_date = datetime.strptime(input("Lomaviikon ma (YYYY-MM-DD): "), "%Y-%m-%d")
        
        os.makedirs("output", exist_ok=True)
        for s in stops.split(","):
            pdf = gen.generate_poster(s.strip(), city, label, s_date, h_date)
            shutil.move(pdf, f"output/{pdf}")
        
        shutil.make_archive("posters", 'zip', "output")
        from google.colab import files
        files.download("posters.zip")
