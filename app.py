from flask import Flask, request, send_file, render_template
import requests
from bs4 import BeautifulSoup
import pandas as pd
import io

app = Flask(__name__)

def fetch_html(affno):
    url = f'https://saras.cbse.gov.in/cbse_aff/schdir_Report/AppViewdir.aspx?affno={affno}'
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        print(f"Failed to retrieve data for affno {affno}")
        return None

def extract_data(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    data = {
        'Name of Institution': '',
        'Affiliation Number': '',
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
                    # Handle cases with multiple values
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
    start_affno = int(request.form['start_affno'])
    end_affno = int(request.form['end_affno'])
    filename = request.form['filename']
    
    data_list = []
    for affno in range(start_affno, end_affno + 1):
        html_content = fetch_html(affno)
        if html_content:
            data = extract_data(html_content)
            data['Affiliation Number'] = affno
            data_list.append(data)
    
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
