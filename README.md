# GTFS Schedule Poster Generator (A3-format posters without a map or a route tree)

A Python tool that parses GTFS (General Transit Feed Specification) data to generate A3-format, printable PDF schedule posters for transit stops.

This tool automatically calculates active bus trips, handles school vs. holiday schedules, generates localized QR codes, and dynamically scales typography to ensure dense schedules fit perfectly on the page.

---

## Features

- **Direct GTFS Parsing:** Reads directly from a standard `gtfs.zip` file (no database required).
- **Dynamic Typography:** Automatically scales font sizes down for busy stops to prevent text overflow.
- **School vs. Holiday Logic:** Compares two representative weeks (school & holiday) to correctly classify departures.
- **Simple HTML Templating:** Clean separation between Python data logic and HTML/CSS layout using strict `{{ placeholder }}` replacement.
- **Automated PDF Conversion:** Uses headless Google Chrome to generate high-quality, print-ready PDFs.
- **Batch Processing:** Generate posters for multiple stop IDs in one run and automatically bundle them into a single `.zip` file.
- **QR Code Integration:** Automatically generates Digitransit-based stop links using the provided city/area name.

---

## Copyright and License

Copyright 2026 Kotkan Kaupunki / City of Kotka. 
This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

**Author & Primary Maintainer:** Nikolay Krupen

---

## Prerequisites

- Python 3.8+
- **Google Chrome / Chromium**  
  The script relies on the Chrome CLI (`google-chrome --headless`) to generate PDFs. Chrome **must** be installed and available in your system's PATH.

---

## Project Structure

Before running the script, ensure your repository is structured exactly like this:

```text
gtfs-schedule-poster-a3-mapless/
├── main.py
├── requirements.txt
├── gtfs.zip                     <-- YOU MUST ADD THIS (Your GTFS data)
├── assets/                      <-- Required folder for images
│   ├── logo.svg                 <-- Your transit agency logo
│   └── alareuna.svg             <-- (Optional) Bottom graphic/banner
└── templates/                   <-- Required folder for HTML templates
    └── poster_template.html
```

> **Important:** `gtfs.zip` is not included in this repository.  
> You must download the GTFS feed for your target transit agency and place it in the root directory.
> 
> If Colab is used, it is sufficient to place all assets (gtfs.zip, logo and a bottom banner) to the /content folder, so their file path would be e.g. /content/alareuna.svg.

---

# Installation (Local Environment)

Clone this repository:

```bash
git clone https://github.com/nkrupen/gtfs-schedule-poster-a3-mapless.git
cd gtfs-schedule-poster-a3-mapless
```

Install the required Python packages:

```bash
pip install -r requirements.txt
```

Ensure:

- `gtfs.zip` is present in the root directory.
- `assets/logo.svg` exists.
- `templates/poster_template.html` exists.

---

# Usage (Local Environment)

Run the script:

```bash
python main.py
```

The interactive prompt will ask for:

- **GTFS File:** Name of your GTFS zip (default: `gtfs.zip`)
- **Stop Numbers:** Comma-separated stop IDs (e.g., `155527,155528`)
- **City or Operation Area Name:** Used for Digitransit QR code URL (e.g., `Kotka`, `Kouvola`)
- **Date Label:** Validity period printed on the poster (e.g., `10.8.2025–31.5.2026`)
- **School Week Start:** A normal Monday during school term (`YYYY-MM-DD`)
- **Holiday Week Start:** A normal Monday during school holidays (`YYYY-MM-DD`)

---

# Running in Google Colab

Google Colab requires additional setup because Chrome is not installed by default and Python must be executed with `!python`.

---

## Step 1 – Install Google Chrome in Colab

Run this in a **separate Colab cell** before executing the script:

```bash
# 1. Update apt
!apt-get update

# 2. Download Chrome
!wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

# 3. Install (dependency warnings are normal)
!dpkg -i google-chrome-stable_current_amd64.deb

# 4. Fix missing dependencies
!apt-get -f install -y

# 5. Verify installation
!google-chrome --version
```

---

## Step 2 – (Optional) Reset Project Folder in Colab

If the repository becomes nested or corrupted:

```bash
# 1. Move out of the folder
%cd /content

# 2. Force delete existing folder
!rm -rf gtfs-schedule-poster-a3-mapless

# 3. Clone fresh
!git clone https://github.com/nkrupen/gtfs-schedule-poster-a3-mapless.git

# 4. Enter folder
%cd gtfs-schedule-poster-a3-mapless
```

---

## Step 3 – Clone the repository

```bash
!git clone https://github.com/nkrupen/gtfs-schedule-poster-a3-mapless.git
%cd gtfs-schedule-poster-a3-mapless

```

---

## Step 4 – Run the Script in Colab

⚠️ In Colab, you must use `!python`:

```bash
!python main.py
```

Do **not** use:

```bash
python main.py
```

The interactive prompts will work inside the Colab cell.

---

## Step 5 – Download Posters Manually (If Needed)

If the ZIP file does not download automatically:

```python
from google.colab import files
files.download('schedule_posters.zip')
```

---

# Output

The script will:

1. Generate individual HTML files.
2. Convert them into PDF posters.
3. Store them in a `generated_posters/` directory.
4. Bundle them into:

```text
schedule_posters.zip
```

Located in the project root.

---

# Troubleshooting

## `FileNotFoundError: templates/poster_template.html`

Ensure:

- The `templates` folder exists.
- `poster_template.html` is inside it.
- There is no duplicated nested repository folder.

---

## PDF Generation Fails

Ensure Chrome is correctly installed.

On some Linux systems, the binary may be:

- `google-chrome-stable`
- `chromium-browser`

If necessary, modify the Chrome command in `main.py`.

---

## Nested Repository Issue in Colab

If your path looks like:

```text
gtfs-schedule-poster-a3-mapless/gtfs-schedule-poster-a3-mapless/main.py
```

You cloned the repository inside itself.  
Use the reset steps above.

---

# Notes & Best Practices

- Always use representative Mondays for school and holiday comparison. Choose the weeks that do not have any public holidays.
- Ensure your GTFS feed is up to date and internally consistent, as well as covering the period with the chosen weeks.
- Large stops may significantly scale down typography automatically.
- The script assumes standard GTFS structure (`trips.txt`, `stop_times.txt`, `calendar.txt`, etc.) and is tailored to Finnish names of calendars (e.g. containing "KOUL" for school days and "LOMA" for school holidays).
- When modifying the HTML template, keep all required `{{ placeholder }}` tags intact.

---
