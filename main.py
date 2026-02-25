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
        self.config = {
            "color": "#3069b3",
            "page_w_mm": 800,
            "page_h_mm": 1131,
            "font_main": "Arial, sans-serif",
        }
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
                            first_line = text.splitlines()[0] if text.splitlines() else ""
                            sep = ";" if first_line.count(";") > first_line.count(",") else ","
                            df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, quotechar='"', skipinitialspace=True)
                            df.columns = df.columns.str.lower().str.strip().str.replace('"', "")
                            return df
                    return pd.DataFrame()

                tables = ["stops", "stop_times", "trips", "routes", "calendar", "calendar_dates"]
                for t in tables:
                    self.data[t] = load_csv(f"{t}.txt")
        except FileNotFoundError:
            print(f"❌ Error: {self.gtfs_path} not found.")

    def _is_service_active_in_week(self, service_id, mon_dt, sun_dt):
        active = [False] * 7
        cal = self.data.get("calendar", pd.DataFrame())
        if not cal.empty and "service_id" in cal.columns:
            row = cal[cal["service_id"] == service_id]
            if not row.empty:
                r = row.iloc[0]
                try:
                    s_dt = datetime.strptime(r["start_date"], "%Y%m%d")
                    e_dt = datetime.strptime(r["end_date"], "%Y%m%d")
                    if not (e_dt < mon_dt or s_dt > sun_dt):
                        days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
                        for i, d in enumerate(days):
                            if r.get(d) == "1":
                                if s_dt <= (mon_dt + timedelta(days=i)) <= e_dt: active[i] = True
                except: pass
        cd = self.data.get("calendar_dates", pd.DataFrame())
        if not cd.empty:
            for _, r in cd[cd["service_id"] == service_id].iterrows():
                try:
                    dt = datetime.strptime(r["date"], "%Y%m%d")
                    if mon_dt <= dt <= sun_dt:
                        wd = dt.weekday()
                        if r["exception_type"] == "1": active[wd] = True
                        elif r["exception_type"] == "2": active[wd] = False
                except: pass
        return tuple(active)

    def _get_active_trips_for_week(self, stop_id, mon_dt, sun_dt):
        st, trips = self.data.get("stop_times"), self.data.get("trips")
        visits = st[st["stop_id"] == str(stop_id)]
        if visits.empty: return pd.DataFrame()
        valid_sids = {sid: self._is_service_active_in_week(sid, mon_dt, sun_dt) 
                      for sid in trips["service_id"].unique() if any(self._is_service_active_in_week(sid, mon_dt, sun_dt))}
        active = trips[(trips["trip_id"].isin(visits["trip_id"])) & (trips["service_id"].isin(valid_sids.keys()))].copy()
        active["week_pattern"] = active["service_id"].map(valid_sids)
        return active

    def get_stop_info(self, stop_id):
        s = self.data.get("stops")
        row = s[s["stop_id"] == str(stop_id)]
        if row.empty: return "Unknown Stop", "???", "A"
        name = row.iloc[0].get("stop_name", "Unknown")
        code = row.iloc[0].get("stop_code", stop_id)
        zone = row.iloc[0].get("zone_id", "A")
        if zone == "1": zone = "A"
        if zone == "2": zone = "B"
        return name, code, zone

    def generate_schedule_html_data(self, stop_id, s_mon, h_mon):
        trips_s = self._get_active_trips_for_week(stop_id, s_mon, s_mon + timedelta(days=6))
        trips_h = self._get_active_trips_for_week(stop_id, h_mon, h_mon + timedelta(days=6))
        visits = self.data["stop_times"][self.data["stop_times"]["stop_id"] == str(stop_id)]

        def get_deps(df, tag):
            if df.empty: return []
            m = visits.merge(df, on="trip_id").merge(self.data["routes"], on="route_id")
            res = []
            for _, r in m.iterrows():
                t = r["arrival_time"].split(":")
                h, mi = int(t[0]), int(t[1])
                res.append({"sig": (h, mi, r["route_short_name"]), "pat": r["week_pattern"], "line": r["route_short_name"], "h": h, "m": mi, "type": tag})
            return res

        d_s, d_h = get_deps(trips_s, "S"), get_deps(trips_h, "H")
        merged = {}
        for d in d_s:
            k = d["sig"]
            if k not in merged: merged[k] = {"S": None, "H": None, "line": d["line"], "h": d["h"], "m": d["m"]}
            merged[k]["S"] = d["pat"]
        for d in d_h:
            k = d["sig"]
            if k not in merged: merged[k] = {"S": None, "H": None, "line": d["line"], "h": d["h"], "m": d["m"]}
            merged[k]["H"] = d["pat"]

        rows, mon_fri_pats, has_s, has_h = [], {}, False, False
        next_fn = 1
        for k, info in merged.items():
            ps, ph = info["S"], info["H"]
            t = "NORMAL"
            if ps and not ph: t, pat, has_s = "SCHOOL", ps, True
            elif not ps and ph: t, pat, has_h = "HOLIDAY", ph, True
            else: t, pat = "NORMAL", ps
            
            if not pat: continue
            mf = pat[0:5]
            if any(mf):
                fn = None
                if not all(mf):
                    if mf not in mon_fri_pats: mon_fri_pats[mf] = next_fn; next_fn += 1
                    fn = mon_fri_pats[mf]
                rows.append({"bucket": "Mon-Fri", "h": info["h"], "m": info["m"], "line": info["line"], "fn": fn, "type": t})
            if pat[5]: rows.append({"bucket": "Sat", "h": info["h"], "m": info["m"], "line": info["line"], "fn": None, "type": "NORMAL"})
            if pat[6]: rows.append({"bucket": "Sun", "h": info["h"], "m": info["m"], "line": info["line"], "fn": None, "type": "NORMAL"})

        legend = '<div class="legend-container" style="font-size:1.8em; margin-top:20px;">'
        if mon_fri_pats:
            dfi = ["maanantaisin", "tiistaisin", "keskiviikkoisin", "torstaisin", "perjantaisin"]
            den = ["on Mondays", "on Tuesdays", "on Wednesdays", "on Thursdays", "on Fridays"]
            for p, fid in sorted(mon_fri_pats.items(), key=lambda x: x[1]):
                idx = [i for i, v in enumerate(p) if v]
                fi, en = ", ".join([dfi[i] for i in idx]).capitalize(), ", ".join([den[i] for i in idx])
                legend += f'<div><strong>{fid})</strong> {fi} / <span style="font-style:italic; opacity:0.8;">{en}</span></div>'
        legend += '<div>Arkipyhinä sunnuntai-aikataulut. / <span style="font-style:italic; opacity:0.8;">Public holidays use Sunday times.</span></div>'
        if has_s: legend += '<div><span style="background:#E3F2FD; border:1px solid #BBDEFB; padding:2px 5px;">&nbsp;</span> = Vain koulupäivinä / <span style="font-style:italic; opacity:0.8;">School days only</span></div>'
        if has_h: legend += '<div><span style="background:#FFF3E0; border:1px solid #FFE0B2; padding:2px 5px;">&nbsp;</span> = Vain lomapäivinä / <span style="font-style:italic; opacity:0.8;">Holidays only</span></div>'
        legend += "</div>"

        html_map = {}
        tr, ti = 0, 0
        for b in ["Mon-Fri", "Sat", "Sun"]:
            e = sorted([r for r in rows if r["bucket"] == b], key=lambda x: (x["h"], x["m"]))
            chunk = '<div class="sc-row sc-header" style="font-weight:bold; border-bottom:3px solid black;"><div class="sc-h" style="width:7em; padding:4px;">Tunti | Hour</div><div class="sc-m" style="flex:1; padding:4px;">min | linja</div></div>'
            if not e: html_map[b] = chunk; continue
            ti += len(e)
            h_map = {}
            for x in e:
                c = "#1565C0" if x["type"]=="SCHOOL" else ("#EF6C00" if x["type"]=="HOLIDAY" else "#000")
                bg = "#E3F2FD" if x["type"]=="SCHOOL" else ("#FFF3E0" if x["type"]=="HOLIDAY" else "transparent")
                fn = f"<sup>{x['fn']})</sup>" if x["fn"] else ""
                h_map.setdefault(x["h"], []).append(f"<div style='display:inline-block; background:{bg}; color:{c}; padding:4px; border-radius:4px; margin:2px;'><strong>{x['m']:02d}</strong>{fn}/{x['line']}</div>")
            
            srt = sorted(h_map.keys())
            i = 0
            while i < len(srt):
                ch, cur_m, eh, j = srt[i], "".join(h_map[srt[i]]), srt[i], i+1
                while j < len(srt) and srt[j] == eh + 1 and "".join(h_map[srt[j]]) == cur_m: eh = srt[j]; j += 1
                lbl = f"{ch if ch < 24 else ch-24:02d}" + (f"&ndash;{eh if eh < 24 else eh-24:02d}" if eh > ch else "")
                chunk += f'<div class="sc-row" style="display:flex; border-bottom:1px solid #ddd;"><div class="sc-h" style="width:7em; padding:4px; font-weight:bold;">{lbl}</div><div class="sc-m" style="flex:1; padding:4px;">{cur_m}</div></div>'; tr += 1; i = j
            html_map[b] = chunk
        return html_map, legend, tr, ti

    def generate_poster(self, stop_id, label, city, s_dt, h_dt, out):
        try:
            name, code, zone = self.get_stop_info(stop_id)
            print(f"   -> Processing: {name} ({stop_id})")
            chunks, leg, rows, items = self.generate_schedule_html_data(stop_id, s_dt, h_dt)
            ds = rows + (items / 6.0)
            f_size = "3.8em" if ds < 55 else ("3.1em" if ds < 80 else "2.1em")
            l_height = "1.3" if ds < 55 else "1.1"

            with open('templates/poster_template.html', 'r', encoding='utf-8') as f:
                template_str = f.read()

            replacements = {
                "{{ stop_name }}": name,
                "{{ date_label }}": label,
                "{{ stop_zone }}": zone,
                "{{ stop_number_html }}": f'<div>Pysäkki: {code}</div>' if zone != "B" else "",
                "{{ monfri_html }}": chunks["Mon-Fri"],
                "{{ saturday_html }}": chunks["Sat"],
                "{{ sunday_html }}": chunks["Sun"],
                "{{ legend_html }}": leg,
                "{{ font_size }}": f_size,
                "{{ line_height }}": l_height,
                "{{ qr_img_url }}": f"https://api.qrserver.com/v1/create-qr-code/?data={urllib.parse.quote(f'https://{city.lower()}.digitransit.fi/pysakit/{city.capitalize()}:{stop_id}')}",
                "{{ logo_html }}": open("assets/logo.svg").read() if os.path.exists("assets/logo.svg") else "",
                "{{ alareuna_svg_inline }}": open("assets/alareuna.svg").read() if os.path.exists("assets/alareuna.svg") else ""
            }

            for k, v in replacements.items():
                template_str = template_str.replace(k, str(v))

            with open(out, "w", encoding='utf-8') as f: f.write(template_str)
            pdf = out.replace(".html", ".pdf")
            subprocess.run(["google-chrome", "--headless", "--no-sandbox", f"--print-to-pdf={pdf}", "--no-pdf-header-footer", out], check=True)
            return pdf
        except Exception as e: 
            print(f"   ❌ Error on stop {stop_id}: {e}")
            return None

    def generate_batch(self, stops_str, label, city, s_dt, h_dt):
        ids = [i.strip() for i in stops_str.split(",") if i.strip()]
        print(f"\n--- Starting Batch: {len(ids)} stops ---")
        if os.path.exists("generated_posters"): shutil.rmtree("generated_posters")
        os.makedirs("generated_posters", exist_ok=True)
        
        success_count = 0
        for sid in ids:
            res = self.generate_poster(sid, label, city, s_dt, h_dt, f"{sid}.html")
            if res: 
                shutil.move(res, f"generated_posters/{res}")
                success_count += 1
            if os.path.exists(f"{sid}.html"): os.remove(f"{sid}.html")
        
        if success_count > 0:
            shutil.make_archive("schedule_posters", 'zip', "generated_posters")
            print(f"\n✅ Batch complete! {success_count} posters generated.")
            try:
                from google.colab import files
                files.download("schedule_posters.zip")
            except Exception as e:
                print(f"⚠️ Manual download required: schedule_posters.zip")
        else:
            print("\n❌ No posters were generated. Check stop IDs and GTFS data.")

if __name__ == "__main__":
    GTFS_FILE = "gtfs.zip"
    if os.path.exists(GTFS_FILE):
        # 1. Capture Inputs
        print("--- GTFS Poster Generator Configuration ---")
        STOPS_INPUT = input("Enter stop numbers (e.g., 155527,155528): ")
        CITY_INPUT = input("Enter city (e.g., Kotka, Helsinki): ").strip()
        LABEL_INPUT = input("Enter date label (e.g., 10.8.2025–31.5.2026): ")
        S_MON_INPUT = input("School Monday (YYYY-MM-DD): ")
        H_MON_INPUT = input("Holiday Monday (YYYY-MM-DD): ")
        
        # 2. Parse Dates
        try:
            S_DATE = datetime.strptime(S_MON_INPUT, "%Y-%m-%d")
            H_DATE = datetime.strptime(H_MON_INPUT, "%Y-%m-%d")
            
            # 3. Initialize and Run
            gen = GTFSSchedulePoster(GTFS_FILE)
            gen.generate_batch(STOPS_INPUT, LABEL_INPUT, CITY_INPUT, S_DATE, H_DATE)
            
        except ValueError:
            print("❌ Error: Date format must be YYYY-MM-DD.")
    else:
        print(f"❌ Error: {GTFS_FILE} not found in the current directory.")
