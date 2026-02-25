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
            "font_stop": "Arial, sans-serif",
            "box_padding": 8.0,
            "box_font_size": 16.0,
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
                            except Exception:
                                text = content.decode("latin1")
                            first_line = text.splitlines()[0] if text.splitlines() else ""
                            sep = ";" if first_line.count(";") > first_line.count(",") else ","
                            df = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, quotechar='"', skipinitialspace=True)
                            df.columns = df.columns.str.lower().str.strip().str.replace('"', "")
                            return df
                    return pd.DataFrame()

                for table in ["stops", "stop_times", "trips", "routes", "calendar", "calendar_dates", "agency"]:
                    self.data[table] = load_csv(f"{table}.txt")
        except FileNotFoundError:
            print(f"Error: The file {self.gtfs_path} was not found.")
            self.data = {}

    def _is_service_active_in_week(self, service_id, monday_dt, sunday_dt):
        active_days = [False] * 7
        cal = self.data.get("calendar", pd.DataFrame())
        if not cal.empty and "service_id" in cal.columns:
            row = cal[cal["service_id"] == service_id]
            if not row.empty:
                r = row.iloc[0]
                try:
                    start_date = datetime.strptime(r["start_date"], "%Y%m%d")
                    end_date = datetime.strptime(r["end_date"], "%Y%m%d")
                    if not (end_date < monday_dt or start_date > sunday_dt):
                        days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
                        for i, day_name in enumerate(days):
                            if r.get(day_name) == "1":
                                if start_date <= (monday_dt + timedelta(days=i)) <= end_date:
                                    active_days[i] = True
                except: pass
        cd = self.data.get("calendar_dates", pd.DataFrame())
        if not cd.empty:
            for _, r in cd[cd["service_id"] == service_id].iterrows():
                try:
                    dt = datetime.strptime(r["date"], "%Y%m%d")
                    if monday_dt <= dt <= sunday_dt:
                        wd = dt.weekday()
                        if r["exception_type"] == "1": active_days[wd] = True
                        elif r["exception_type"] == "2": active_days[wd] = False
                except: pass
        return tuple(active_days)

    def _get_active_trips_for_week_single_stop(self, stop_id, start_dt, end_dt):
        st, trips = self.data.get("stop_times"), self.data.get("trips")
        visits = st[st["stop_id"] == str(stop_id)]
        if visits.empty or trips.empty: return pd.DataFrame()
        valid_sids = {sid: self._is_service_active_in_week(sid, start_dt, end_dt) 
                      for sid in trips["service_id"].unique() if any(self._is_service_active_in_week(sid, start_dt, end_dt))}
        active = trips[trips["trip_id"].isin(visits["trip_id"]) & trips["service_id"].isin(valid_sids.keys())].copy()
        active["week_pattern"] = active["service_id"].map(valid_sids)
        return active

    def get_stop_info(self, stop_id):
        s = self.data.get("stops")
        row = s[s["stop_id"] == str(stop_id)]
        if row.empty: return "Unknown", "???", "Unknown"
        name, code, rz = row.iloc[0].get("stop_name", "Unknown"), row.iloc[0].get("stop_code", ""), str(row.iloc[0].get("zone_id", ""))
        zone = "A" if rz == "1" else ("B" if rz == "2" else rz)
        if not str(code).startswith("K"):
            for col in row.columns:
                val = str(row.iloc[0][col])
                if val.startswith("K") and len(val) < 8: code = val; break
        return name, code, zone

    def _clean_stop_name(self, name):
        return re.sub(r"(?i)\bpäätepysäkki\b", "", str(name)).strip()

    def _clean_line_dest(self, dest):
        s = str(dest or "").strip()
        s = re.sub(r"(?i)\(\s*KANTASATAMA\s*\)|\bKANTASATAMA\b", "", s).strip(" -–—,/| ")
        return re.sub(r"\s{2,}", " ", s)

    def _read_svg(self, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f: return f.read()
        return ""

    def _svg_force_current_color(self, svg):
        if not svg: return ""
        s = svg.strip().replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg" class="bus-icon"', 1)
        return re.sub(r'fill="[^"]*"|fill\s*:\s*[^;"]+;', 'fill="currentColor"', s)

    def generate_line_bar_data(self, active_trips):
        if active_trips.empty: return []
        m = active_trips.merge(self.data["routes"], on="route_id")
        res = []
        for name, group in m.groupby("route_short_name"):
            dest = group["trip_headsign"].mode()[0] if not group["trip_headsign"].mode().empty else ""
            res.append({"num": name, "dest": self._clean_line_dest(dest)})
        res.sort(key=lambda x: [int(t) if t.isdigit() else t.lower() for t in re.split("([0-9]+)", str(x["num"]))])
        return res

    def generate_schedule_html_data(self, stop_id, s_mon, h_mon):
        trips_s = self._get_active_trips_for_week_single_stop(stop_id, s_mon, s_mon + timedelta(days=6))
        trips_h = self._get_active_trips_for_week_single_stop(stop_id, h_mon, h_mon + timedelta(days=6))
        visits = self.data["stop_times"][self.data["stop_times"]["stop_id"] == str(stop_id)]

        def get_deps(df, is_s):
            if df.empty: return []
            m = visits.merge(df, on="trip_id").merge(self.data["routes"], on="route_id")
            res = []
            for _, r in m.iterrows():
                try: t = r["arrival_time"].split(":"); h, mi = int(t[0]), int(t[1])
                except: h, mi = 0, 0
                res.append({"sig": (h, mi, r["route_short_name"]), "pat": r["week_pattern"], "line": r["route_short_name"], "h": h, "m": mi, "type": "S" if is_s else "H"})
            return res

        d_s, d_h = get_deps(trips_s, True), get_deps(trips_h, False)
        merged = {}
        for d in d_s:
            k = d["sig"]; merged.setdefault(k, {"S": None, "H": None, "line": d["line"], "h": d["h"], "m": d["m"]})
            merged[k]["S"] = self._combine_patterns(merged[k]["S"], d["pat"])
        for d in d_h:
            k = d["sig"]; merged.setdefault(k, {"S": None, "H": None, "line": d["line"], "h": d["h"], "m": d["m"]})
            merged[k]["H"] = self._combine_patterns(merged[k]["H"], d["pat"])

        mon_fri_pats, raw_rows, next_fn, has_s, has_h = {}, [], 1, False, False
        for _, info in merged.items():
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
                raw_rows.append({"bucket": "Mon-Fri", "h": info["h"], "m": info["m"], "line": info["line"], "footnote": fn, "type": t})
            if pat[5]: raw_rows.append({"bucket": "Sat", "h": info["h"], "m": info["m"], "line": info["line"], "footnote": None, "type": "NORMAL"})
            if pat[6]: raw_rows.append({"bucket": "Sun", "h": info["h"], "m": info["m"], "line": info["line"], "footnote": None, "type": "NORMAL"})

        legend_html = f'<div class="legend-container">'
        for p, fid in sorted(mon_fri_pats.items(), key=lambda x: x[1]):
            idxs = [i for i, v in enumerate(p) if v]
            legend_html += f'<div class="legend-item"><strong>{fid})</strong> {", ".join(["maanantaisin","tiistaisin","keskiviikkoisin","torstaisin","perjantaisin"][i] for i in idxs).capitalize()} / <span class="en"><i>{", ".join(["on Mondays","on Tuesdays","on Wednesdays","on Thursdays","on Fridays"][i] for i in idxs)}</i></span></div>'
        legend_html += '<div class="legend-note">Arkipyhinä ajetaan sunnuntain vuorot. / <span class="en"><i>On public holidays, Sunday services are operated.</i></span></div><div class="legend-badges">'
        if has_s: legend_html += f'<div class="legend-item"><span style="display:inline-block; padding:2px 6px; border-radius:4px; background:#E3F2FD; color:#1565C0; font-weight:bold;">&nbsp;</span> = Vain koulupäivinä / <span class="en"><i>On school days</i></span></div>'
        if has_h: legend_html += f'<div class="legend-item"><span style="display:inline-block; padding:2px 6px; border-radius:4px; background:#FFF3E0; color:#EF6C00; font-weight:bold;">&nbsp;</span> = Vain lomapäivinä / <span class="en"><i>Only on school holidays</i></span></div>'
        legend_html += "</div></div>"

        final_html = {}
        tr, ti = 0, 0
        for b in ["Mon-Fri", "Sat", "Sun"]:
            ents = sorted([r for r in raw_rows if r["bucket"] == b], key=lambda x: (x["h"], x["m"]))
            h_row = '<div class="sc-row sc-header"><div class="sc-h">Tunti | Hour</div><div class="sc-m">min | linja / <span class="en">route</span></div></div>'
            if not ents: final_html[b] = h_row; continue
            ti += len(ents); h_map = {}
            for e in ents:
                fn = f"<sup>{e['footnote']})</sup>" if e["footnote"] else ""
                bg = "#E3F2FD" if e["type"]=="SCHOOL" else ("#FFF3E0" if e["type"]=="HOLIDAY" else "transparent")
                clr = "#1565C0" if e["type"]=="SCHOOL" else ("#EF6C00" if e["type"]=="HOLIDAY" else "#000")
                h_map.setdefault(e["h"], []).append(f"<div class='time-group' style='background:{bg}; color:{clr}; padding:1px 4px; border-radius:4px;'><strong>{e['m']:02d}</strong>{fn}<span class='s-line'>/{e['line']}</span></div>")
            chunk = h_row; srt = sorted(h_map.keys()); i = 0
            while i < len(srt):
                ch, cm, eh, j = srt[i], "".join(h_map[srt[i]]), srt[i], i+1
                while j < len(srt) and srt[j] == eh + 1 and "".join(h_map[srt[j]]) == cm: eh = srt[j]; j += 1
                lbl = f"{ch if ch < 24 else ch-24:02d}" + (f"&ndash;{eh if eh < 24 else eh-24:02d}" if eh > ch else "")
                chunk += f'<div class="sc-row"><div class="sc-h">{lbl}</div><div class="sc-m">{cm}</div></div>'; tr += 1; i = j
            final_html[b] = chunk
        return final_html, legend_html, tr, ti

    def _get_dynamic_layout_params(self, rows, items):
        ds = rows + (items / 6.0)
        f, lh, vm, hf = "3.8em", "1.3", "25px", "2.5em"
        if ds > 55: f, lh, vm = "3.1em", "1.2", "15px"
        if ds > 80: f, lh, hf = "2.5em", "1.15", "2.2em"
        if ds > 110: f, lh, vm, hf = "2.1em", "1.1", "5px", "2.0em"
        return f, lh, vm, hf

    def generate_poster(self, stop_id, date_label, city, s_mon, h_mon, output_file):
        try:
            name, code, zone = self.get_stop_info(stop_id)
            sched, legend, rows, items = self.generate_schedule_html_data(stop_id, s_mon, h_mon)
            f, lh, vm, hf = self._get_dynamic_layout_params(rows, items)
            line_bar = "".join([f'<div class="lb-item"><span class="bus-icon-wrap">{self._svg_force_current_color(self._read_svg("bus-icon.svg"))}</span><span class="lb-num">{i["num"]}</span><span class="lb-dest">{i["dest"]}</span></div>' for i in self.generate_line_bar_data(self._get_active_trips_for_week_single_stop(stop_id, s_mon, s_mon+timedelta(days=6)))])
            
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=1000x1000&data={urllib.parse.quote(f'https://{city.lower()}.digitransit.fi/pysakit/{city.capitalize()}:{stop_id}')}"
            logo = self._read_svg("logo.svg") or '<div style="font-size:3em; color:white;">LOGO</div>'
            footer = self._read_svg("alareuna.svg") or '<svg viewBox="0 0 800 140"><rect width="800" height="140" fill="#f0f0f0"/></svg>'

            html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
                @page {{ size: 800mm 1131mm; margin: 0; }}
                body {{ margin: 0; font-family: {self.config['font_main']}; background: {self.config['color']}; -webkit-print-color-adjust: exact; }}
                .poster-container {{ width: 800mm; height: 1131mm; display: flex; flex-direction: column; overflow: hidden; }}
                .header {{ flex: 0 0 auto; padding: 15mm 20mm; display: flex; justify-content: space-between; color: white; }}
                .h-stop-name {{ font-size: 6.2em; font-weight: bold; line-height: 1; }}
                .h-value {{ font-size: 5.6em; font-weight: bold; }}
                .line-bar {{ background: white; margin: 0 20mm 10mm; padding: 12mm; display: flex; flex-wrap: wrap; gap: 30px; border-radius: 30px; }}
                .lb-item {{ display: flex; align-items: center; gap: 14px; font-size: 3em; }}
                .content-wrap {{ flex: 1; padding: 0 20mm 20mm; display: flex; flex-direction: column; }}
                .unified-box {{ background: white; border-radius: 30px; padding: 15mm; flex: 1; display: flex; flex-direction: column; }}
                .sc-block {{ margin-bottom: {vm}; }}
                .sc-title {{ font-size: {f}; font-weight: bold; border-bottom: 4px solid black; margin-bottom: {vm}; }}
                .sc-row {{ display: flex; border-bottom: 1px solid #ddd; font-size: {f}; line-height: {lh}; }}
                .sc-header {{ font-weight: bold; border-bottom: 3px solid black; font-size: calc({hf} * 1.1); }}
                .sc-h {{ width: 7em; font-weight: bold; }}
                .sc-m {{ flex: 1; display: flex; flex-wrap: wrap; gap: 10px; }}
                .bottom-row {{ display: flex; gap: 20mm; flex: 1; margin-top: 20px; }}
                .alareuna-box {{ position: relative; margin-top: auto; }}
                .qr-group {{ position: absolute; bottom: 30px; right: 20px; background: white; padding: 20px; border-radius: 30px; width: 240px; height: 240px; }}
                .en {{ color: #666; font-style: italic; }}
            </style></head><body><div class="poster-container">
                <div class="header">
                    <div><div class="h-stop-name">{name}</div><div style="font-size:3em;">Voimassa / Valid {date_label}</div></div>
                    <div style="display:flex; gap:15mm; align-items:center;">
                        <div style="text-align:center;"><div style="font-size:2.2em;">Vyöhyke / Zone</div><div class="h-value">{zone}</div></div>
                        {f'<div style="text-align:center;"><div style="font-size:2.2em;">Pysäkki / Stop</div><div class="h-value">{code}</div></div>' if zone != "B" else ""}
                        <div style="height:40mm;">{logo}</div>
                    </div>
                </div>
                <div class="line-bar">{line_bar}</div>
                <div class="content-wrap"><div class="unified-box">
                    <div class="sc-block"><div style="font-size:3.8em; font-weight:bold; margin-bottom:15px;">Pysäkkiaikataulu / <span class="en">Stop timetable</span></div>{sched['Mon-Fri']}</div>
                    {legend}
                    <div class="bottom-row">
                        <div style="flex:1;"><div class="sc-title">Lauantai / <span class="en">Saturday</span></div>{sched['Sat']}</div>
                        <div style="flex:1; display:flex; flex-direction:column;"><div class="sc-title">Sunnuntai / <span class="en">Sunday</span></div>{sched['Sun']}
                            <div class="alareuna-box">{footer}<div class="qr-group"><img src="{qr_url}" style="width:100%;"></div></div>
                        </div>
                    </div>
                </div></div>
            </div></body></html>"""

            with open(output_file, "w", encoding="utf-8") as f_out: f_out.write(html)
            pdf = output_file.replace(".html", ".pdf")
            subprocess.run(["google-chrome", "--headless", "--no-sandbox", f"--print-to-pdf={pdf}", "--no-pdf-header-footer", output_file], check=True)
            return pdf
        except Exception as e:
            print(f"Error: {e}"); return None

    def generate_batch(self, stops_str, city, label, s_mon, h_mon):
        ids = [s.strip() for s in stops_str.split(',') if s.strip()]
        out_dir = "generated_posters"
        if os.path.exists(out_dir): shutil.rmtree(out_dir)
        os.makedirs(out_dir)
        for sid in ids:
            print(f"Processing {sid}...")
            res = self.generate_poster(sid, label, city, s_mon, h_mon, f"{sid}.html")
            if res: shutil.move(res, os.path.join(out_dir, res))
            if os.path.exists(f"{sid}.html"): os.remove(f"{sid}.html")
        shutil.make_archive("schedule_posters", 'zip', out_dir)
        try:
            from google.colab import files
            files.download("schedule_posters.zip")
        except: print("Download schedule_posters.zip from sidebar.")

if __name__ == "__main__":
    GTFS = "gtfs.zip"
    if os.path.exists(GTFS):
        gen = GTFSSchedulePoster(GTFS)
        stops = input("Stop IDs (comma separated): ")
        city = input("City (for QR): ")
        label = input("Date Label (e.g. 10.8.2025–31.5.2026): ")
        s_date = datetime.strptime(input("School Monday (YYYY-MM-DD): "), "%Y-%m-%d")
        h_date = datetime.strptime(input("Holiday Monday (YYYY-MM-DD): "), "%Y-%m-%d")
        gen.generate_batch(stops, city, label, s_date, h_date)
    else: print("Please upload gtfs.zip")
