from flask import Flask, request, send_file, render_template, jsonify
import requests
from bs4 import BeautifulSoup
import pandas as pd
import io
import threading
import concurrent.futures
import re

app = Flask(__name__)

# Global variables for tracking progress and storing data
progress = {'percentage': 0}
progress_lock = threading.Lock()
data_list = []


def fetch_html(affno):
    """
    Fetches the HTML content for a given affiliation number (affno).
    """
    url = f'https://saras.cbse.gov.in/cbse_aff/schdir_Report/AppViewdir.aspx?affno={affno}'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        app.logger.error(f"Error fetching affno {affno}: {e}")
        return None


def process_value(original_key, value):
    """
    Processes the extracted value based on the key.
    - Emails are converted to lowercase.
    - "N/A" remains unchanged.
    - "AM" and "PM" are ensured to be uppercase.
    - WEBSITE is not transformed.
    - Other values are title-cased.
    """
    if value.upper() == "N/A":
        return "N/A"

    if original_key == 'EMAIL':
        return value.lower()

    if original_key == 'WEBSITE':
        return value  # Do not transform the website link

    # Title case the value
    processed_value = value.title()

    # Replace 'Am'/'Pm' with 'AM'/'PM'
    processed_value = re.sub(r'\bAm\b', 'AM', processed_value)
    processed_value = re.sub(r'\bPm\b', 'PM', processed_value)

    return processed_value


def extract_data(html_content, affno):
    """
    Extracts relevant data from the HTML content for a given affiliation number.
    - Table headers are mapped to uppercase keys.
    - Values are title-cased (first letter of each word capitalized), except:
        - Emails are in lowercase.
        - WEBSITE is not transformed.
        - "N/A" remains as "N/A".
        - "AM"/"PM" are uppercase.
    - Adds a new 'SIR/MAM' field based on the 'SEX' field.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Define the data dictionary with uppercase keys
    data = {
        'NAME OF INSTITUTION': '',
        'AFFILIATION NUMBER': affno,
        'STATE': '',
        'DISTRICT': '',
        'POSTAL ADDRESS': '',
        'PIN CODE': '',
        'PHONE NO. WITH STD CODE': '',
        'OFFICE': '',
        'RESIDENCE': '',
        'FAX NO': '',
        'EMAIL': '',
        'WEBSITE': '',
        'YEAR OF FOUNDATION': '',
        'DATE OF FIRST OPENING OF SCHOOL': '',
        'NAME OF PRINCIPAL/ HEAD OF INSTITUTION': '',
        'SEX': '',
        'SIR/MAM': '',  # New column placed immediately after 'SEX'
        'PRINCIPAL\'S EDUCATIONAL/PROFESSIONAL QUALIFICATIONS': '',
        'NO OF EXPERIENCE (IN YEARS) ADMINISTRATIVE': '',
        'NO OF EXPERIENCE (IN YEARS) TEACHING': '',
        'STATUS OF THE SCHOOL': '',
        'TYPE OF AFFILIATION': '',
        'AFFILIATION PERIOD FROM': '',
        'AFFILIATION PERIOD TO': '',
        'NAME OF TRUST/ SOCIETY/ MANAGING COMMITTEE': ''
    }

    table = soup.find('table')  # Adjust if the structure is different
    if table:
        rows = table.find_all('tr')
        for row in rows:
            columns = row.find_all('td')
            if len(columns) >= 2:
                key = columns[0].get_text(strip=True).upper()  # Normalize key to uppercase
                value = columns[1].get_text(strip=True)

                # Mapping normalized key to original data keys
                key_mapping = {
                    'NAME OF INSTITUTION': 'NAME OF INSTITUTION',
                    'AFFILIATION NUMBER': 'AFFILIATION NUMBER',
                    'STATE': 'STATE',
                    'DISTRICT': 'DISTRICT',
                    'POSTAL ADDRESS': 'POSTAL ADDRESS',
                    'PIN CODE': 'PIN CODE',
                    'PHONE NO. WITH STD CODE': 'PHONE NO. WITH STD CODE',
                    'OFFICE': 'OFFICE',
                    'RESIDENCE': 'RESIDENCE',
                    'FAX NO': 'FAX NO',
                    'EMAIL': 'EMAIL',
                    'WEBSITE': 'WEBSITE',
                    'YEAR OF FOUNDATION': 'YEAR OF FOUNDATION',
                    'DATE OF FIRST OPENING OF SCHOOL': 'DATE OF FIRST OPENING OF SCHOOL',
                    'NAME OF PRINCIPAL/ HEAD OF INSTITUTION': 'NAME OF PRINCIPAL/ HEAD OF INSTITUTION',
                    'SEX': 'SEX',
                    'PRINCIPAL\'S EDUCATIONAL/PROFESSIONAL QUALIFICATIONS': 'PRINCIPAL\'S EDUCATIONAL/PROFESSIONAL QUALIFICATIONS',
                    'NO OF EXPERIENCE (IN YEARS) ADMINISTRATIVE': 'NO OF EXPERIENCE (IN YEARS) ADMINISTRATIVE',
                    'NO OF EXPERIENCE (IN YEARS) TEACHING': 'NO OF EXPERIENCE (IN YEARS) TEACHING',
                    'STATUS OF THE SCHOOL': 'STATUS OF THE SCHOOL',
                    'TYPE OF AFFILIATION': 'TYPE OF AFFILIATION',
                    'AFFILIATION PERIOD FROM': 'AFFILIATION PERIOD FROM',
                    'AFFILIATION PERIOD TO': 'AFFILIATION PERIOD TO',
                    'NAME OF TRUST/ SOCIETY/ MANAGING COMMITTEE': 'NAME OF TRUST/ SOCIETY/ MANAGING COMMITTEE'
                }

                if key in key_mapping:
                    original_key = key_mapping[key]
                    if original_key in ['PHONE NO. WITH STD CODE', 'OFFICE', 'RESIDENCE']:
                        if original_key in ['OFFICE', 'RESIDENCE']:
                            # Replace line breaks with commas and process each part
                            parts = [part.strip() for part in value.splitlines() if part.strip()]
                            processed_parts = [process_value(original_key, part) for part in parts]
                            data[original_key] = ', '.join(processed_parts)
                        else:
                            data[original_key] = process_value(original_key, value)
                    elif original_key == 'SEX':
                        # Process SEX field first
                        data[original_key] = process_value(original_key, value)
                        # Determine SIR/MAM based on SEX
                        sex = data.get('SEX', '').upper()
                        if sex == 'MALE':
                            data['SIR/MAM'] = 'Sir'
                        elif sex == 'FEMALE':
                            data['SIR/MAM'] = 'Mam'
                        else:
                            data['SIR/MAM'] = 'Sir/Mam'
                    else:
                        data[original_key] = process_value(original_key, value)

    return data


@app.route('/')
def home():
    """
    Renders the home page.
    """
    return render_template('index.html')


@app.route('/scrape', methods=['POST'])
def scrape():
    """
    Initiates the scraping process for provided affiliation numbers.
    """
    global progress
    global data_list

    # Extract form data
    affnos = request.form.get('affnos', '').split(',')
    filename = request.form.get('filename', 'data') + '.csv'  # Automatically append .csv

    # Clean and validate affnos
    affnos = [affno.strip() for affno in affnos if affno.strip().isdigit()]
    if not affnos:
        return jsonify({'status': 'Error', 'message': 'No valid affiliation numbers provided.'}), 400

    data_list = []
    progress['percentage'] = 0  # Reset progress

    def scrape_affno(affno):
        """
        Scrapes data for a single affiliation number.
        """
        html_content = fetch_html(affno)
        if html_content:
            return extract_data(html_content, affno)
        return None

    def scrape_data():
        """
        Scrapes data for all affiliation numbers concurrently.
        """
        global data_list
        total_affnos = len(affnos)
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_affno = {executor.submit(scrape_affno, affno): affno for affno in affnos}
            for i, future in enumerate(concurrent.futures.as_completed(future_to_affno)):
                affno = future_to_affno[future]
                try:
                    data = future.result()
                    if data:
                        data_list.append(data)
                    else:
                        app.logger.warning(f"No data extracted for affno {affno}")
                except Exception as e:
                    app.logger.error(f"Error processing affno {affno}: {e}")
                with progress_lock:
                    progress['percentage'] = int(((i + 1) / total_affnos) * 100)

    # Run scraping in a separate thread
    thread = threading.Thread(target=scrape_data)
    thread.start()

    # Return a response indicating the data is being processed
    return jsonify({'status': 'Scraping started', 'filename': filename})


@app.route('/progress')
def check_progress():
    """
    Returns the current progress of the scraping process.
    """
    with progress_lock:
        return jsonify({'progress': progress['percentage']})


@app.route('/download')
def download():
    """
    Allows users to download the scraped data as a CSV file.
    """
    global data_list
    filename = request.args.get('filename', 'data.csv')
    if not data_list:
        return jsonify({'status': 'Error', 'message': 'No data available for download.'}), 400

    df = pd.DataFrame(data_list)

    # Ensure that the columns are in uppercase
    df.columns = [column.upper() for column in df.columns]

    # Reorder columns to place 'SIR/MAM' next to 'SEX'
    columns_order = [
        'NAME OF INSTITUTION',
        'AFFILIATION NUMBER',
        'STATE',
        'DISTRICT',
        'POSTAL ADDRESS',
        'PIN CODE',
        'PHONE NO. WITH STD CODE',
        'OFFICE',
        'RESIDENCE',
        'FAX NO',
        'EMAIL',
        'WEBSITE',
        'YEAR OF FOUNDATION',
        'DATE OF FIRST OPENING OF SCHOOL',
        'NAME OF PRINCIPAL/ HEAD OF INSTITUTION',
        'SEX',
        'SIR/MAM',  # Placed immediately after 'SEX'
        'PRINCIPAL\'S EDUCATIONAL/PROFESSIONAL QUALIFICATIONS',
        'NO OF EXPERIENCE (IN YEARS) ADMINISTRATIVE',
        'NO OF EXPERIENCE (IN YEARS) TEACHING',
        'STATUS OF THE SCHOOL',
        'TYPE OF AFFILIATION',
        'AFFILIATION PERIOD FROM',
        'AFFILIATION PERIOD TO',
        'NAME OF TRUST/ SOCIETY/ MANAGING COMMITTEE'
    ]

    # Reorder the DataFrame columns
    df = df.reindex(columns=columns_order)

    csv_output = io.StringIO()
    df.to_csv(csv_output, index=False, encoding='utf-8')
    csv_output.seek(0)

    return send_file(
        io.BytesIO(csv_output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )


if __name__ == '__main__':
    app.run(debug=True)
