from flask import Flask, jsonify, render_template
import serial
import threading
import time
import re
import datetime
import boto3

AWS_S3_BUCKET_NAME = 'arduinofastfashion'
AWS_REGION = 'us-west-2'
AWS_ACCESS_KEY = 'ACCESS_KEY'
AWS_SECRET_KEY = 'SECRET_KEY'

LOCAL_FILE = 'data_log.txt'
NAME_FOR_S3 = 'data_log.txt'

with open(LOCAL_FILE, 'w') as file:
    file.write('')  # Empty the contents of the file

app = Flask(__name__)

data_list = []  # Global list to store dictionaries of scanned code and weight

def read_from_serial(ser):
    global data_list
    scanned_code = ""  # Temporary variable to hold the scanned code
    weight = ""        # Temporary variable to hold the weight
    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').rstrip()
                print(f"Received: {line}")

                # Parse the line for scanned code and weight
                scanned_code_match = re.match(r"Scanned Code:\s*(.+)", line)
                weight_match = re.match(r"Peso:\s*([0-9.]+)\s*kg", line)

                if scanned_code_match:
                    scanned_code = scanned_code_match.group(1)
                elif weight_match:
                    weight = weight_match.group(1)
                    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    data_entry = {
                        "code": scanned_code,
                        "weight": weight,
                        "time": timestamp
                    }
                    data_list.append(data_entry)
                    
                    # Write the data_entry to the log file
                    try:
                        with open('data_log.txt', 'a') as f:
                            f.write(f"{data_entry['code']},{data_entry['weight']},{data_entry['time']}\n")
                            
                        s3_client = boto3.client(
                            service_name='s3',
                            region_name=AWS_REGION,
                            aws_access_key_id=AWS_ACCESS_KEY,
                            aws_secret_access_key=AWS_SECRET_KEY
                        )

                        response = s3_client.upload_file(LOCAL_FILE, AWS_S3_BUCKET_NAME, NAME_FOR_S3)

                    except Exception as e:
                        print(f"Error writing to log file: {e}")
                    
                    # Reset temporary variables after storing
                    scanned_code = ""
                    weight = ""
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ser.close()
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data')
def get_data():
    last_weight = data_list[-1]['weight'] if data_list else "0"
    return jsonify({
        'last_weight': last_weight,
        'data_list': data_list
    })

if __name__ == '__main__':
    ser = serial.Serial('COM6', 9600)  # Adjust the port for your OS
    time.sleep(2)

    thread = threading.Thread(target=read_from_serial, args=(ser,))
    thread.daemon = True
    thread.start()

    app.run(debug=True, use_reloader=False)
