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
    """
    Large-format schedule poster generator.
    Supports batch processing and zipping of results.
    """

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

                self.data["stops"] = load_csv("stops.txt")
                self.data["stop_times"] = load_csv("stop_times.txt")
                self.data["trips"] = load_csv("trips.txt")
                self.data["routes"] = load_csv("routes.txt")
                self.data["calendar"] = load_csv("calendar.txt")
                self.data["calendar_dates"] = load_csv("calendar_dates.txt")
                self.data["agency"] = load_csv("agency.txt")
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
                                current_day_date = monday_dt + timedelta(days=i)
                                if start_date <= current_day_date <= end_date:
                                    active_days[i] = True
                except Exception: pass
        cal_dates = self.data.get("calendar_dates", pd.DataFrame())
        if not cal_dates.empty and "service_id" in cal_dates.columns:
            dates = cal_dates[cal_dates["service_id"] == service_id]
            for _, d_row in dates.iterrows():
                try:
                    exc_date = datetime.strptime(d_row["date"], "%Y%m%d")
                    if monday_dt <= exc_date <= sunday_dt:
                        wd = exc_date.weekday()
                        if d_row.get("exception_type") == "1": active_days[wd] = True
                        elif d_row.get("exception_type") == "2": active_days[wd] = False
                except Exception: pass
        return tuple(active_days)

    def _get_active_trips_for_week_single_stop(self, stop_id, start_dt, end_dt):
        st = self.data.get("stop_times", pd.DataFrame())
        trips = self.data.get("trips", pd.DataFrame())
        if st.empty or trips.empty: return pd.DataFrame()
        stop_visits = st[st["stop_id"] == str(stop_id)]
        if stop_visits.empty: return pd.DataFrame()
        valid_sids = set()
        schedule_map = {}
        for sid in trips["service_id"].unique():
            active_tuple = self._is_service_active_in_week(sid, start_dt, end_dt)
            if any(active_tuple):
                valid_sids.add(sid)
                schedule_map[sid] = active_tuple
        relevant_trips = trips[trips["trip_id"].isin(stop_visits["trip_id"])]
        active_trips = relevant_trips[relevant_trips["service_id"].isin(valid_sids)].copy()
        active_trips["week_pattern"] = active_trips["service_id"].map(schedule_map)
        return active_trips

    def get_stop_info(self, stop_id):
        stops = self.data.get("stops", pd.DataFrame())
        if stops.empty: return "Unknown", "???", "Unknown"
        row = stops[stops["stop_id"] == str(stop_id)]
        if row.empty: return "Unknown", "???", "Unknown"
        name = row.iloc[0].get("stop_name", "Unknown")
        code = row.iloc[0].get("stop_code", "")
        raw_zone = str(row.iloc[0].get("zone_id", ""))
        zone = "A" if raw_zone == "1" else ("B" if raw_zone == "2" else raw_zone)
        if not str(code).startswith("K"):
            for col in row.columns:
                val = str(row.iloc[0][col])
                if val.startswith("K") and len(val) < 8:
                    code = val
                    break
        return name, code, zone

    def _clean_stop_name(self, name):
        return re.sub(r"(?i)\bpäätepysäkki\b", "", str(name)).strip()

    def _clean_line_dest(self, dest: str) -> str:
        s = str(dest or "").strip()
        s = re.sub(r"\(\s*KANTASATAMA\s*\)|\bKANTASATAMA\b", "", s, flags=re.IGNORECASE).strip()
        return re.sub(r"\s{2,}", " ", s).strip(" -–—,/|")

    def _read_svg_candidates(self, candidates):
        for p in candidates:
            if p and os.path.exists(p):
                with open(p, "r", encoding="utf-8") as sf: return sf.read()
        return ""

    def _svg_force_current_color(self, svg_text: str) -> str:
        if not svg_text: return ""
        s = svg_text.strip()
        if "<svg" in s and "xmlns=" not in s: s = s.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
        s = re.sub(r'fill="[^"]*"', 'fill="currentColor"', s, flags=re.IGNORECASE)
        s = re.sub(r"fill\s*:\s*[^;\"']+;", "fill: currentColor;", s, flags=re.IGNORECASE)
        return s if "class=" in s.split(">")[0] else s.replace("<svg", '<svg class="bus-icon"', 1)

    def _join_natural(self, items, conj):
        if not items: return ""
        if len(items) == 1: return items[0]
        return ", ".join(items[:-1]) + f" {conj} " + items[-1]

    def generate_line_bar_data(self, active_trips):
        if active_trips.empty: return []
        merged = active_trips.merge(self.data["routes"], on="route_id", how="left")
        lines_data = []
        for name, group in merged.groupby("route_short_name"):
            headsign = group["trip_headsign"].mode()[0] if "trip_headsign" in group.columns and not group["trip_headsign"].mode().empty else ""
            lines_data.append({"num": name, "dest": self._clean_line_dest(headsign)})
        lines_data.sort(key=lambda x: [int(t) if t.isdigit() else t.lower() for t in re.split("([0-9]+)", str(x["num"]))])
        return lines_data

    def _combine_patterns(self, p1, p2):
        if p1 is None: return p2
        if p2 is None: return p1
        return tuple(a or b for a, b in zip(p1, p2))

    def generate_schedule_html_data(self, stop_id, school_week_start, holiday_week_start):
        school_end = school_week_start + timedelta(days=6)
        holiday_end = holiday_week_start + timedelta(days=6)
        trips_s = self._get_active_trips_for_week_single_stop(stop_id, school_week_start, school_end)
        trips_h = self._get_active_trips_for_week_single_stop(stop_id, holiday_week_start, holiday_end)
        visits = self.data["stop_times"][self.data["stop_times"]["stop_id"] == str(stop_id)]

        def process_trips(trips_df, is_school):
            if trips_df.empty: return []
            merged = visits.merge(trips_df, on="trip_id").merge(self.data["routes"], on="route_id", how="left")
            departures = []
            for _, row in merged.iterrows():
                try:
                    parts = str(row.get("arrival_time")).split(":")
                    h, m = int(parts[0]), int(parts[1])
                except: h, m = 0, 0
                departures.append({"sig": (h, m, row.get("route_short_name", "")), "pattern": row.get("week_pattern"), "line": row.get("route_short_name", ""), "h": h, "m": m, "type": "S" if is_school else "H"})
            return departures

        deps_s, deps_h = process_trips(trips_s, True), process_trips(trips_h, False)
        merged_map = {}
        for d in deps_s:
            k = d["sig"]; merged_map.setdefault(k, {"S": None, "H": None, "line": d["line"], "h": d["h"], "m": d["m"]})
            merged_map[k]["S"] = self._combine_patterns(merged_map[k]["S"], d["pattern"])
        for d in deps_h:
            k = d["sig"]; merged_map.setdefault(k, {"S": None, "H": None, "line": d["line"], "h": d["h"], "m": d["m"]})
            merged_map[k]["H"] = self._combine_patterns(merged_map[k]["H"], d["pattern"])

        mon_fri_patterns, raw_rows, next_footnote, has_school, has_holiday = {}, [], 1, False, False
        for _, info in merged_map.items():
            ps, ph = info["S"], info["H"]
            f_type = "NORMAL"
            if ps and not ph: f_type, active_pat, has_school = "SCHOOL", ps, True
            elif not ps and ph: f_type, active_pat, has_holiday = "HOLIDAY", ph, True
            else: f_type, active_pat = "NORMAL", ps
            if not active_pat: continue
            mf = active_pat[0:5]
            if any(mf):
                ft_idx = None
                if not all(mf):
                    if mf not in mon_fri_patterns: mon_fri_patterns[mf] = next_footnote; next_footnote += 1
                    ft_idx = mon_fri_patterns[mf]
                raw_rows.append({"bucket": "Mon-Fri", "h": info["h"], "m": info["m"], "line": info["line"], "footnote": ft_idx, "type": f_type})
            if active_pat[5]: raw_rows.append({"bucket": "Sat", "h": info["h"], "m": info["m"], "line": info["line"], "footnote": None, "type": "NORMAL"})
            if active_pat[6]: raw_rows.append({"bucket": "Sun", "h": info["h"], "m": info["m"], "line": info["line"], "footnote": None, "type": "NORMAL"})

        legend_html = '<div class="legend-container">'
        if mon_fri_patterns:
            days_fi = ["maanantaisin", "tiistaisin", "keskiviikkoisin", "torstaisin", "perjantaisin"]
            days_en = ["on Mondays", "on Tuesdays", "on Wednesdays", "on Thursdays", "on Fridays"]
            for pat, fid in sorted(mon_fri_patterns.items(), key=lambda x: x[1]):
                idxs = [i for i, v in enumerate(pat) if v]
                fi_str = self._join_natural([days_fi[i] for i in idxs], "ja").capitalize()
                en_str = self._join_natural([days_en[i] for i in idxs], "and")
                legend_html += f'<div class="legend-item"><strong>{fid})</strong> {fi_str} / <span style="color:#000;"><i>{en_str}</i></span></div>'
        legend_html += '<div class="legend-note">Arkipyhinä ajetaan sunnuntain vuorot. / <span class="en"><i>On public holidays, Sunday services are operated.</i></span></div><div class="legend-badges">'
        if has_school or has_holiday: legend_html += f'<div class="legend-item">Mustalla olevat vuorot ajetaan koulupäivinä sekä koulujen lomapäivinä / <span class="en"><i>Departures colored in black operated on school days and school holidays</i></span></div>'
        if has_school: legend_html += f'<div class="legend-item"><span style="display:inline-block; padding:2px 6px; border-radius:4px; background:#E3F2FD; color:#1565C0; font-weight:bold; border:1px solid #BBDEFB;">&nbsp;</span> = Vain koulupäivinä / <span class="en"><i>On school days</i></span></div>'
        if has_holiday: legend_html += f'<div class="legend-item"><span style="display:inline-block; padding:2px 6px; border-radius:4px; background:#FFF3E0; color:#EF6C00; font-weight:bold; border:1px solid #FFE0B2;">&nbsp;</span> = Vain koulujen lomapäivinä / <span class="en"><i>Only on school holidays</i></span></div>'
        legend_html += "</div></div>"

        final_html_map, tr_count, ti_count = {}, 0, 0
        for bucket in ["Mon-Fri", "Sat", "Sun"]:
            entries = sorted([r for r in raw_rows if r["bucket"] == bucket], key=lambda x: (x["h"], x["m"]))
            h_row = '<div class="sc-row sc-header"><div class="sc-h">Tunti |&nbsp;<i>hour</i></div><div class="sc-m">min | linja <span style="margin-left:2em; color:#000;"><i>min | route</i></span></div></div>'
            if not entries: final_html_map[bucket] = h_row; continue
            ti_count += len(entries); h_map = {}
            for e in entries:
                note = f"<sup>{e['footnote']})</sup>" if e['footnote'] else ""
                bg = "#E3F2FD" if e["type"]=="SCHOOL" else ("#FFF3E0" if e["type"]=="HOLIDAY" else "transparent")
                clr = "#1565C0" if e["type"]=="SCHOOL" else ("#EF6C00" if e["type"]=="HOLIDAY" else "#000")
                h_map.setdefault(e["h"], []).append(f"<div class='time-group' style='display:inline-block; width:4.5em; padding:1px 0; border-radius:4px; margin:0 2px; border:1px solid transparent; background:{bg}; color:{clr};'><span style='font-weight:bold;'>{e['m']:02d}</span>{note}<span class='s-line'>/{e['line']}</span></div>")
            chunk = h_row; srt = sorted(h_map.keys()); i = 0
            while i < len(srt):
                ch, cm, eh, j = srt[i], "".join(h_map[srt[i]]), srt[i], i+1
                while j < len(srt) and srt[j] == eh+1 and "".join(h_map[srt[j]]) == cm: eh = srt[j]; j += 1
                lbl = f"{ch if ch < 24 else ch-24:02d}" + (f"&ndash;{eh if eh < 24 else eh-24:02d}" if eh > ch else "")
                chunk += f'<div class="sc-row"><div class="sc-h">{lbl}</div><div class="sc-m">{cm}</div></div>'; tr_count += 1; i = j
            final_html_map[bucket] = chunk
        return final_html_map, legend_html, tr_count, ti_count

    def _get_dynamic_layout_params(self, row_count, item_count):
        ds = row_count + (item_count / 6.0)
        f, lh, vm, hf = "3.8em", "1.3", "25px", "2.5em"
        if ds > 55: f, lh, vm = "3.1em", "1.2", "15px"
        if ds > 80: f, lh, hf = "2.5em", "1.15", "2.2em"
        if ds > 110: f, lh, vm, hf = "2.1em", "1.1", "5px", "2.0em"
        return f, lh, vm, hf

    def generate_poster(self, stop_id, date_label, city, school_start, holiday_start, output_file):
        try:
            name, code, zone = self.get_stop_info(stop_id)
            if name == "Unknown": return None
            sched, legend, rows, items = self.generate_schedule_html_data(stop_id, school_start, holiday_start)
            f, lh, vm, hf = self._get_dynamic_layout_params(rows, items)
            line_data = self.generate_line_bar_data(self._get_active_trips_for_week_single_stop(stop_id, school_start, school_start+timedelta(days=6)))
            bus_svg = self._svg_force_current_color(self._read_svg_candidates(["bus-icon.svg"])) or '<svg viewBox="0 0 24 24"><path fill="currentColor" d="M4 16c0 1.1.9 2 2 2v1c0 .55.45 1 1 1s1-.45 1-1v-1h8v1c0 .55.45 1 1 1s1-.45 1-1v-1c1.1 0 2-.9 2-2V6c0-3-3.6-3-8-3S4 3 4 6v10zm3.5 1a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zm9 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zM6 6h12v6H6V6z"/></svg>'
            line_bar_html = "".join([f'<div class="lb-item"><span class="bus-icon-wrap" style="width:50px; height:50px;">{bus_svg}</span><span class="lb-num" style="font-size:3em; font-weight:bold;">{i["num"]}</span><span class="lb-dest" style="font-size:2em;">{i["dest"]}</span></div>' for i in line_data])
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=1000x1000&data={urllib.parse.quote(f'https://{city.lower()}.digitransit.fi/pysakit/{city.capitalize()}:{stop_id}')}"
            logo_html = self._read_svg_candidates(["logo.svg"]) or '<div style="font-size:3em; color:white;">LOGO</div>'
            footer_html = self._read_svg_candidates(["alareuna.svg"]) or '<svg viewBox="0 0 800 140"><rect width="800" height="140" fill="#f0f0f0"/></svg>'

            html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
@page {{ size: 800mm 1131mm; margin: 0; }}
body {{ margin: 0; padding: 0; font-family: {self.config['font_main']}; background: {self.config['color']}; -webkit-print-color-adjust: exact; }}
.poster-container {{ width: 800mm; height: 1131mm; display: flex; flex-direction: column; overflow: hidden; }}
.header {{ flex: 0 0 auto; padding: 15mm 20mm 5mm 20mm; display: flex; justify-content: space-between; align-items: flex-start; color: white; }}
.h-stop-name {{ font-size: 6.2em; font-weight: bold; line-height: 1; }}
.header-right {{ display: flex; align-items: center; gap: 20mm; }}
.h-value {{ font-size: 5.6em; font-weight: bold; line-height: 0.95; }}
.line-bar-container {{ flex: 0 0 auto; padding: 0 20mm; margin-bottom: 10mm; }}
.line-bar {{ background: white; padding: 12mm 15mm; display: flex; flex-wrap: wrap; gap: 30px; border-radius: 30px; }}
.lb-item {{ display: flex; align-items: center; gap: 14px; margin-right: 40px; }}
.content-wrap {{ flex: 1; padding: 0 20mm 20mm; display: flex; flex-direction: column; }}
.unified-box {{ background: white; border-radius: 30px; padding: 15mm; flex: 1; display: flex; flex-direction: column; }}
.sc-block {{ margin-bottom: {vm}; }}
.sc-title {{ font-size: {f}; font-weight: bold; border-bottom: 4px solid black; padding-bottom: 8px; margin-bottom: {vm}; }}
.sc-header {{ border-bottom: 3px solid black; font-weight: bold; font-size: calc({hf} * 1.15) !important; }}
.sc-row {{ display: flex; border-bottom: 1px solid #ddd; font-size: {f}; line-height: {lh}; }}
.sc-row:nth-child(odd):not(.sc-header) {{ background: #f2f2f2; }}
.sc-h {{ width: 7em; font-weight: bold; padding: 4px 6px; }}
.sc-m {{ flex: 1; padding: 4px 10px; display: flex; flex-wrap: wrap; gap: 0.8em; }}
.bottom-row {{ display: flex; gap: 20mm; flex: 1; margin-top: 0; }}
.alareuna-box {{ flex: 0 0 auto; position: relative; margin-top: 20px; }}
.qr-group {{ position: absolute; bottom: 30px; right: 20px; background: white; padding: 20px; border-radius: 30px; width: 240px; height: 240px; }}
.en {{ font-style: italic; color: #000; }}
</style></head><body><div class="poster-container">
<div class="header">
    <div><div class="h-stop-name">{self._clean_stop_name(name)}</div><div style="font-size:3em; margin-top:15px;">Aikataulut ovat voimassa | <span class="en">Timetables valid</span> {date_label}</div></div>
    <div class="header-right"><div style="text-align:center;"><div style="font-size:2.2em;">Vyöhyke <span class="en">| Zone</span></div><div class="h-value">{zone}</div></div>
    {f'<div style="text-align:center;"><div style="font-size:2.2em;">Pysäkkinumero <span class="en">| Stop number</span></div><div class="h-value">{(code if (code and code != "???") else stop_id)}</div></div>' if zone != "B" else ""}
    <div style="height:40mm;">{logo_html}</div></div>
</div>
<div class="line-bar-container"><div class="line-bar">{line_bar_html}</div></div>
<div class="content-wrap"><div class="unified-box">
    <div class="sc-block"><div style="font-size:3.8em; font-weight:bold; margin-bottom:15px;">Pysäkkiaikataulu <span class="en">| Stop timetable</span> <span style="font-size:0.7em; font-weight:normal; margin-left:2em;">Ajat ovat arvioaikoja | <span class="en">The times are estimates</span></span></div>{sched['Mon-Fri']}</div>
    {legend}
    <div class="bottom-row">
        <div style="flex:1;"><div class="sc-title">Lauantai <span class="en">| Saturday</span></div>{sched['Sat']}</div>
        <div style="flex:1; display:flex; flex-direction:column;"><div class="sc-title">Sunnuntai <span class="en">| Sunday</span></div>{sched['Sun']}
        <div class="alareuna-box">{footer_html}<div class="qr-group"><img src="{qr_url}" style="width:100%;"></div></div></div>
    </div>
</div></div></div></body></html>"""

            with open(output_file, "w", encoding="utf-8") as f_out: f_out.write(html)
            pdf = output_file.replace(".html", ".pdf")
            subprocess.run(["google-chrome", "--headless", "--no-sandbox", f"--print-to-pdf={pdf}", "--no-pdf-header-footer", output_file], check=True)
            return pdf
        except Exception as e: print(f"Error: {e}"); return None

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
        except: print("Download schedule_posters.zip manually.")

if __name__ == "__main__":
    GTFS = "gtfs.zip"
    if os.path.exists(GTFS):
        gen = GTFSSchedulePoster(GTFS)
        stops = input("Stop IDs (comma separated): ")
        city = input("City (for QR): ")
        label = input("Date Label: ")
        s_date = datetime.strptime(input("School Monday (YYYY-MM-DD): "), "%Y-%m-%d")
        h_date = datetime.strptime(input("Holiday Monday (YYYY-MM-DD): "), "%Y-%m-%d")
        gen.generate_batch(stops, city, label, s_date, h_date)
    else: print("Please upload gtfs.zip")
