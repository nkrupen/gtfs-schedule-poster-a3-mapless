# GTFS Schedule Poster Generator

A Python tool that parses GTFS (General Transit Feed Specification) data to generate large-format, printable PDF schedule posters for transit stops.

This tool automatically calculates active bus trips, handles school vs. holiday schedules, generates localized QR codes, and dynamically scales typography to ensure dense schedules fit perfectly on the page.

---

## Features

- **Direct GTFS Parsing:** Reads directly from a standard `gtfs.zip` file (no database required).
- **Dynamic Typography:** Automatically scales font sizes down for busy stops to prevent text overflow.
- **Simple HTML Templating:** Cleanly separates the Python data logic from the HTML/CSS presentation using strict string replacement (uses `{{ placeholder }}` tags).
- **Automated PDF Conversion:** Uses headless Google Chrome to convert HTML into high-quality, print-ready PDFs.
- **Batch Processing:** Enter multiple stop IDs at once, and the script will generate all PDFs and package them into a single `.zip` file.

---

## Prerequisites

- Python 3.8+
- **Google Chrome / Chromium:** The script relies on the Chrome CLI (`google-chrome --headless`) to generate the PDFs. Chrome **must** be installed on your system and available in your system's PATH.

---

## Project Structure

Before running the script, ensure your repository is structured exactly like this:

```text
gtfs-schedule-poster/
├── main.py
├── requirements.txt
├── gtfs.zip                     <-- YOU MUST ADD THIS (Your GTFS data)
├── assets/                      <-- Required folder for images
│   ├── logo.svg                 <-- Your transit agency logo
│   └── alareuna.svg             <-- (Optional) Bottom graphic/banner
└── templates/                   <-- Required folder for HTML templates
    └── poster_template.html
```

> **Note:** `gtfs.zip` is not included in this repository. You must download the GTFS feed for your target transit agency and place it in the root directory.

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

Ensure you have your `gtfs.zip` file and your `assets/logo.svg` in place.

---

## Usage

Run the script from your terminal:

```bash
python main.py
```

The interactive prompt will ask you for the following information:

- **GTFS File:** The name of your GTFS zip (defaults to `gtfs.zip`).
- **Stop Numbers:** Comma-separated list of stop IDs (e.g., `155527, 155528`).
- **City or Operation Area Name:** Used to generate the correct Digitransit URL for the QR code (e.g., `Kotka`, `Kouvola`).
- **Date Label:** The validity period printed on the poster (e.g., `10.8.2025–31.5.2026`).
- **School Week Start:** A normal Monday during the school term (Format: `YYYY-MM-DD`).
- **Holiday Week Start:** A normal Monday during the school holidays (Format: `YYYY-MM-DD`).

---

## Output

The script will:

1. Create a `generated_posters/` directory containing the individual HTML and PDF files.
2. Bundle them into a single `schedule_posters.zip` file in your root directory.

---

## Troubleshooting

### `FileNotFoundError: templates/poster_template.html`

Ensure you have created the `templates` folder and placed the HTML file inside it.

### PDF Generation Fails

Ensure Google Chrome is installed. On some Linux distributions, the command might be:

- `google-chrome-stable`
- `chromium-browser`

You may need to update the `subprocess.run` command in `main.py` to match your local Chrome binary name.

---

## Running in Google Colab

If you are running this script in Google Colab, Google Chrome is not installed by default. You must run the following commands in a separate Colab cell before running the Python script to install Chrome and its dependencies:

```bash
# 1. Update apt to ensure we can get dependencies
!apt-get update

# 2. Download the official Google Chrome .deb package
!wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

# 3. Install it (this will likely fail initially due to missing deps, which is normal)
!dpkg -i google-chrome-stable_current_amd64.deb

# 4. Fix the missing dependencies automatically
!apt-get -f install -y

# 5. Verify installation
!google-chrome --version
```
