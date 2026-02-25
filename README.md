text** **GTFS Schedule Poster Generator**
A Python tool that parses GTFS (General Transit Feed Specification) data to generate large-format, printable PDF schedule posters for transit stops.

This tool automatically calculates active bus trips, handles school vs. holiday schedules, generates localized QR codes, and dynamically scales typography to ensure dense schedules fit perfectly on the page.

**Features**
  -Direct GTFS Parsing: Reads directly from a standard gtfs.zip file (no database required).
  -Dynamic Typography: Automatically scales font sizes down for busy stops to prevent text overflow.
  -Jinja2 Templating: Cleanly separates the Python data logic from the HTML/CSS presentation.
  -Automated PDF Conversion: Uses headless Google Chrome to convert HTML into high-quality, print-ready PDFs.
  -Batch Processing: Enter multiple stop IDs at once, and the script will generate all PDFs and package them into a single .zip file.

**Prerequisites:**
  -Python 3.8+
  -Google Chrome / Chromium: The script relies on the Chrome CLI (google-chrome --headless) to generate the PDFs. Chrome must be installed on your system and available in your system's PATH.

**Project Structure**
Before running the script, ensure your repository is structured exactly like this:

gtfs-schedule-poster/
├── main.py
├── requirements.txt
├── gtfs.zip                     <-- YOU MUST ADD THIS (Your GTFS data)
├── assets/                      <-- Required folder for images
│   ├── logo.svg                 <-- Your transit agency logo
│   └── alareuna.svg             <-- (Optional) Bottom graphic/banner
└── templates/                   <-- Required folder for HTML templates
    └── poster_template.html     


**Installation**
_Clone this repository_:
git clone https://github.com/yourusername/gtfs-schedule-poster.git
cd gtfs-schedule-poster

_Install the required Python packages:_
pip install pandas jinja2
Ensure you have your gtfs.zip file and your assets/logo.svg in place.

**Usage**
_Run the script from your terminal:_
python main.py

The interactive prompt will ask you for the following information:
-Stop Numbers: Comma-separated list of stop IDs (e.g., 155527, 155528).
-City Name: Used to generate the correct Digitransit URL for the QR code (e.g., Kotka, Helsinki).
-Date Label: The validity period printed on the poster (e.g., 10.8.2025–31.5.2026).
-School Week Start: A normal Monday during the school term (Format: YYYY-MM-DD).
-Holiday Week Start: A normal Monday during the school holidays (Format: YYYY-MM-DD).

**Output**
The script will create a generated_posters/ directory containing the individual PDFs, and then bundle them into a single schedule_posters.zip file in your root directory.

**Troubleshooting**
FileNotFoundError: templates/poster_template.html: Ensure you have created the templates folder and placed the HTML file inside it.

PDF Generation Fails: Ensure Google Chrome is installed. On some Linux distributions, the command might be google-chrome-stable or chromium-browser. You may need to update the subprocess.run command in main.py to match your local Chrome binary name.**
