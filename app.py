from flask import Flask, request, send_file, render_template, jsonify
import requests
from bs4 import BeautifulSoup
import pandas as pd
import io
import threading
import concurrent.futures

app = Flask(__name__)

# Global variables for tracking progress and storing data
progress = {'percentage': 0}
progress_lock = threading.Lock()
data_list = []


def fetch_html(affno):
    url = f'https://saras.cbse.gov.in/cbse_aff/schdir_Report/AppViewdir.aspx?affno={affno}'
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        print(f"Failed to retrieve data for affno {affno}")
        return None


def extract_data(html_content, affno):
    soup = BeautifulSoup(html_content, 'html.parser')

    data = {
        'Name of Institution': '',
        'Affiliation Number': affno,
        'State': '',
        'District': '',
        'Postal Address': '',
        'Pin Code': '',
        'Phone No. with STD Code': '',
        'Office': '',
        'Residence': '',
        'FAX No': '',
        'Email': '',
        'Website': '',
        'Year of Foundation': '',
        'Date of First Opening of School': '',
        'Name of Principal/ Head of Institution': '',
        'Sex': '',
        'Principal\'s Educational/Professional Qualifications': '',
        'No of Experience (in Years) Administrative': '',
        'No of Experience (in Years) Teaching': '',
        'Status of The School': '',
        'Type of affiliation': '',
        'Affiliation Period From': '',
        'Affiliation Period To': '',
        'Name of Trust/ Society/ Managing Committee': ''
    }

    table = soup.find('table')  # Adjust if the structure is different
    if table:
        rows = table.find_all('tr')
        for row in rows:
            columns = row.find_all('td')
            if len(columns) >= 2:
                key = columns[0].get_text(strip=True)
                value = columns[1].get_text(strip=True)

                if key in data:
                    if key == 'Phone No. with STD Code':
                        data[key] = value
                    elif key in ['Office', 'Residence']:
                        data[key] = ', '.join(value.splitlines())
                    else:
                        data[key] = value

    return data


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/scrape', methods=['POST'])
def scrape():
    global progress
    global data_list
    affnos = request.form['affnos'].split(',')
    filename = request.form['filename'] + '.csv'  # Automatically append .csv

    data_list = []

    def scrape_affno(affno):
        html_content = fetch_html(affno.strip())
        if html_content:
            return extract_data(html_content, affno.strip())
        return None

    def scrape_data():
        global data_list
        total_affnos = len(affnos)
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_affno = {executor.submit(scrape_affno, affno): affno for affno in affnos}
            for i, future in enumerate(concurrent.futures.as_completed(future_to_affno)):
                data = future.result()
                if data:
                    data_list.append(data)
                with progress_lock:
                    progress['percentage'] = int(((i + 1) / total_affnos) * 100)

    # Run scraping in a separate thread
    thread = threading.Thread(target=scrape_data)
    thread.start()

    # Return a response indicating the data is being processed
    return jsonify({'status': 'Scraping started', 'filename': filename})


@app.route('/progress')
def check_progress():
    with progress_lock:
        return jsonify({'progress': progress['percentage']})


@app.route('/download')
def download():
    global data_list
    filename = request.args.get('filename', 'data.csv')
    df = pd.DataFrame(data_list)
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
