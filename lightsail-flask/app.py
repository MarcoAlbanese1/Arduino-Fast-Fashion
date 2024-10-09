from flask import Flask, jsonify, render_template
import boto3

AWS_S3_BUCKET_NAME = 'arduinofastfashion'
AWS_REGION = 'us-west-2'
AWS_ACCESS_KEY = 'ACCESS_KEY'       # Replace with your AWS access key
AWS_SECRET_KEY = 'SECRET_KEY'       # Replace with your AWS secret key

LOCAL_FILE = 'data_log.txt'
NAME_FOR_S3 = 'data_log.txt'

app = Flask(__name__)

data_list = []  # Global list to store dictionaries of scanned code and weight

def fetch_data_from_s3():
    global data_list
    try:
        s3_client = boto3.client(
            service_name='s3',
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY,
            aws_secret_access_key=AWS_SECRET_KEY
        )
        # Download the file from S3
        s3_client.download_file(AWS_S3_BUCKET_NAME, NAME_FOR_S3, LOCAL_FILE)
        
        # Read the data from the local file and populate data_list
        data_list.clear()
        with open(LOCAL_FILE, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 3:
                    code, weight, timestamp = parts
                    data_entry = {
                        "code": code,
                        "weight": weight,
                        "time": timestamp
                    }
                    data_list.append(data_entry)
    except Exception as e:
        print(f"Error fetching data from S3: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    fetch_data_from_s3()
    last_weight = data_list[-1]['weight'] if data_list else "0"
    return jsonify({
        'last_weight': last_weight,
        'data_list': data_list
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, use_reloader=False)
