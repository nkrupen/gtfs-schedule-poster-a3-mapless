# GTFS Schedule Poster Generator

A Python tool that parses GTFS (General Transit Feed Specification) data to generate large-format, printable PDF schedule posters for transit stops.

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

---

## Installation

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

## Usage (Local Environment)

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

## Output

The script will:

1. Generate individual HTML files.
2. Convert them into PDF posters.
3. Store them in a `generated_posters/` directory.
4. Automatically create a bundled file:

```text
schedule_posters.zip
```

This ZIP file is located in the project root directory.

---

# Running in Google Colab

Google Colab requires additional setup because Chrome is not installed by default.

---

## Step 1 – Install Google Chrome in Colab

Run this in a **separate Colab cell** before executing `main.py`:

```bash
# 1. Update apt to ensure we can get dependencies
!apt-get update

# 2. Download the official Google Chrome .deb package
!wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

# 3. Install it (initial dependency errors are normal)
!dpkg -i google-chrome-stable_current_amd64.deb

# 4. Fix missing dependencies
!apt-get -f install -y

# 5. Verify installation
!google-chrome --version
```

---

## Step 2 – (Optional) Reset Project Folder in Colab

If the repository becomes corrupted or nested incorrectly, you can force reset it:

```bash
# 1. Move out of the folder if you are in it
%cd /content

# 2. Force delete the existing project folder
!rm -rf gtfs-schedule-poster-a3-mapless

# 3. Clone it fresh from GitHub
!git clone https://github.com/nkrupen/gtfs-schedule-poster-a3-mapless.git

# 4. Enter the fresh folder
%cd gtfs-schedule-poster-a3-mapless
```

This ensures you are working from a clean repository state.

---

## Step 3 – Download Posters Manually (If Needed)

If the automatic download does not trigger in Colab, manually download the ZIP file:

```python
from google.colab import files
files.download('schedule_posters.zip')
```

---

## Known Non-Critical Error in Colab

You may see the following error after execution:

```text
AttributeError: 'NoneType' object has no attribute 'kernel'
```

Full traceback example:

```text
Traceback (most recent call last):
  File ".../main.py", line 1152, in <module>
    gen.generate_batch(...)
  File ".../main.py", line 1129, in generate_batch
    files.download(final_zip_name)
  File ".../google/colab/files.py", line 232, in download
    comm_manager = _IPython.get_ipython().kernel.comm_manager
AttributeError: 'NoneType' object has no attribute 'kernel'
```

### ✅ This error can be safely ignored.

It occurs when:

- The script is executed outside a proper interactive Colab cell context.
- The file has already been generated successfully.
- The Colab communication manager is unavailable.

If `schedule_posters.zip` exists in the directory, your posters were generated correctly.

---

# Troubleshooting

## `FileNotFoundError: templates/poster_template.html`

Ensure:

- The `templates` folder exists.
- The file `poster_template.html` is inside it.
- The folder structure is correct (no nested duplicate repository folder).

---

## PDF Generation Fails

Ensure Chrome is correctly installed.

On some Linux systems, the binary may be:

- `google-chrome-stable`
- `chromium-browser`

If necessary, modify the Chrome command in `main.py` to match your system.

---

## Nested Repository Issue in Colab

If your path looks like this:

```text
gtfs-schedule-poster-a3-mapless/gtfs-schedule-poster-a3-mapless/main.py
```

You have cloned the repository inside itself.  
Use the reset steps above to fix it.

---

# Notes & Best Practices

- Always use representative Mondays for school and holiday comparison.
- Ensure your GTFS feed is up to date and internally consistent.
- Large stops with many departures may significantly scale down typography automatically.
- The script assumes standard GTFS structure (`trips.txt`, `stop_times.txt`, `calendar.txt`, etc.).
- If modifying the HTML template, keep all required `{{ placeholder }}` tags intact.

---
