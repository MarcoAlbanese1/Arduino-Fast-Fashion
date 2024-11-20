from flask import Flask, jsonify, render_template, request
import serial
import threading
import time
import re
import datetime
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr  # Import Attr for filtering
from decimal import Decimal


AWS_REGION = 'us-west-2'
AWS_ACCESS_KEY = ''       # Replace with your AWS access key
AWS_SECRET_KEY = ''       # Replace with your AWS secret key

MAX_WEIGHT = 1.0  # Maximum weight in kg

app = Flask(__name__)

data_list = []  # Global list to store dictionaries of scanned code and weight
data_lock = threading.Lock()
scans_enabled = True  # Flag to control scanning

latest_weight = None  # Global variable to store the latest weight

# Initialize DynamoDB resource
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
# Reference the DynamoDB table
table = dynamodb.Table('ScannedData')

def parse_scanned_code(code):
    # Assuming the code format is:
    # producto_id (positions 0-3): 4 digits
    # genero (position 4): 'H' or 'M'
    # talla (positions 5-6): '01' to '05'
    # material (positions 7-8): '01' to '05'
    # pais (positions 9-10): '01' to '05'
    # año (positions 11-12): '20' to '30'
    parsed_data = {}
    try:
        parsed_data['id'] = code[0:4]
        parsed_data['sex'] = code[4]
        parsed_data['size'] = code[5:7]
        parsed_data['material'] = code[7:9]
        parsed_data['country'] = code[9:11]
        parsed_data['year'] = code[11:13]

        # Map codes to actual values
        parsed_data['sex'] = 'Hombre' if parsed_data['sex'] == 'H' else 'Mujer'

        talla_map = {
            '01': 'XS',
            '02': 'S',
            '03': 'M',
            '04': 'L',
            '05': 'XL'
        }
        parsed_data['size'] = talla_map.get(parsed_data['size'], 'Unknown')

        material_map = {
            '01': 'Algodon',
            '02': 'Poliester',
            '03': 'Lana',
            '04': 'Seda',
            '05': 'Lino'
        }
        parsed_data['material'] = material_map.get(parsed_data['material'], 'Unknown')

        pais_map = {
            '01': 'China',
            '02': 'India',
            '03': 'Bangladesh',
            '04': 'Vietnam',
            '05': 'México'
        }
        parsed_data['country'] = pais_map.get(parsed_data['country'], 'Unknown')

        # Optionally, parse año to full year
        parsed_data['year'] = '20' + parsed_data['year']  # Assuming year 2020-2030

    except Exception as e:
        print(f"Error parsing scanned code: {e}")
        parsed_data = {}

    return parsed_data

def wait_for_stable_weight(timeout=5, stability_threshold=0.01):
    global latest_weight
    start_time = time.time()
    last_weight = None
    stable_since = start_time

    while time.time() - start_time < timeout:
        with data_lock:
            current_weight = latest_weight
        if last_weight is None or abs(float(current_weight) - float(last_weight)) > stability_threshold:
            stable_since = time.time()
            last_weight = current_weight
        elif time.time() - stable_since >= 1:  # Weight is stable for 1 second
            return current_weight
        time.sleep(0.1)
    return None  # Weight did not stabilize within timeout


def read_code_from_serial(ser_code):
    global latest_weight
    try:
        while True:
            if ser_code.in_waiting > 0:
                # Read all available data
                line = ser_code.read(ser_code.in_waiting).decode('utf-8', errors='ignore')
                line = line.strip()
                if line:
                    print(f"Received from code scanner: {line}")
                    # Wait for weight to stabilize
                    weight = wait_for_stable_weight()
                    if weight:
                        process_scanned_data(line, weight)
                    else:
                        print("Failed to get stable weight.")
    except Exception as e:
        print(f"Error in read_code_from_serial: {e}")
    finally:
        ser_code.close()



def read_weight_from_serial(ser_weight):
    global latest_weight
    try:
        while True:
            if ser_weight.in_waiting > 0:
                line = ser_weight.readline().decode('utf-8', errors='ignore').rstrip()
                print(f"Received from weight sensor: {line}")
                # Use regular expression to extract the numeric weight
                match = re.search(r"Peso:\s*([-+]?\d*\.\d+|\d+)", line)
                if match:
                    weight_value = match.group(1)
                    with data_lock:
                        latest_weight = Decimal(str(weight_value))
                else:
                    print(f"Could not parse weight from line: {line}")
    except Exception as e:
        print(f"Error in read_weight_from_serial: {e}")
    finally:
        ser_weight.close()


def process_scanned_data(scanned_code, weight):
    global data_list, scans_enabled
    # Get current datetime components
    now = datetime.datetime.now()
    date_year = str(now.year)
    date_month = str(now.month).zfill(2)
    date_day = str(now.day).zfill(2)
    time_str = now.strftime('%H:%M:%S')
    timestamp = Decimal(str(now.timestamp()))  # Convert timestamp to Decimal

    # Parse the scanned_code to get detailed info
    parsed_data = parse_scanned_code(scanned_code)
    if not parsed_data:
        return  # Skip if parsing failed

    # Convert weight to Decimal
    try:
        weight_value = Decimal(str(weight))
    except (ValueError) as e:
        print(f"Invalid weight value: {weight}. Error: {e}")
        return

    with data_lock:
        # Check if scanning is enabled
        if not scans_enabled:
            print("Scans are disabled because total weight exceeds the maximum limit.")
            return

        data_entry = {
            "code": scanned_code,
            "weight": weight_value,  # Use Decimal type
            "date_year": date_year,
            "date_month": date_month,
            "date_day": date_day,
            "time": time_str,
            "timestamp": timestamp,  # Use Decimal type
            "id": parsed_data.get('id'),
            "sex": parsed_data.get('sex'),
            "size": parsed_data.get('size'),
            "material": parsed_data.get('material'),
            "country": parsed_data.get('country'),
            "year": parsed_data.get('year'),
            "container_cleared": "false"
        }

        data_list.append(data_entry)

    # Write the data_entry to the DynamoDB table
    try:
        print("Uploading to DynamoDB")
        table.put_item(Item=data_entry)
        print("Successfully uploaded")
    except ClientError as e:
        print(f"Error writing to DynamoDB: {e.response['Error']['Message']}")
        return
    except Exception as e:
        print(f"Error writing to DynamoDB: {e}")
        return

    # After adding the item, check total weight
    with data_lock:
        # Fetch current total_weight from DynamoDB including the new item
        response = table.scan(
            FilterExpression=Attr('container_cleared').eq("false"),
            ProjectionExpression='weight'
        )
        items = response.get('Items', [])
        # Sum the weights of items currently in the container
        current_total_weight = sum(Decimal(item['weight']) for item in items)

        # Check if total weight exceeds the limit
        if current_total_weight > Decimal(str(MAX_WEIGHT)):
            scans_enabled = False
            print(f"Total weight exceeds {MAX_WEIGHT} kg after adding the item. Scans are now disabled until cleared.")


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin.html')
def admin_page():
    return render_template('admin.html')

@app.route('/data')
def get_data():
    global scans_enabled
    try:
        # Fetch items where container_cleared == "false"
        response = table.scan(
            FilterExpression=Attr('container_cleared').eq("false")
        )
        items = response.get('Items', [])
        
        # Convert Decimal types to float or str
        for item in items:
            if 'weight' in item:
                item['weight'] = float(item['weight'])
            if 'timestamp' in item:
                item['timestamp'] = float(item['timestamp'])
        
        # Sort items based on the timestamp
        items.sort(key=lambda x: x.get('timestamp', 0))
        last_item = items[-1] if items else {}
        last_weight = last_item.get('weight', 0)
        return jsonify({
            'last_weight': last_weight,
            'data_list': items,
            'scans_enabled': scans_enabled
        })
    except ClientError as e:
        print(f"Error fetching data from DynamoDB: {e.response['Error']['Message']}")
        return jsonify({'error': 'Error fetching data'}), 500




@app.route('/admin/data')
def get_admin_data():
    try:
        # Fetch items where container_cleared == "false"
        response = table.scan(
            FilterExpression=Attr('container_cleared').eq("false")
        )
        items = response.get('Items', [])
        total_items = len(items)
        gender_counts = {'M': 0, 'H': 0}
        material_counts = {}
        size_counts = {}

        for entry in items:
            genero = entry.get('sex')
            if genero == 'Mujer':
                gender_counts['M'] += 1
            elif genero == 'Hombre':
                gender_counts['H'] += 1

            material = entry.get('material')
            if material:
                material_counts[material] = material_counts.get(material, 0) + 1

            talla = entry.get('size')
            if talla:
                size_counts[talla] = size_counts.get(talla, 0) + 1

        return jsonify({
            'total_items': total_items,
            'gender_counts': gender_counts,
            'material_counts': material_counts,
            'size_counts': size_counts
        })
    except ClientError as e:
        print(f"Error fetching data from DynamoDB: {e.response['Error']['Message']}")
        return jsonify({'error': 'Error fetching data'}), 500

@app.route('/admin/clear', methods=['POST'])
def clear_data():
    global scans_enabled
    try:
        # Scan for items where container_cleared == "false"
        response = table.scan(
            FilterExpression=Attr('container_cleared').eq("false")
        )
        items = response.get('Items', [])

        print(items)

        for item in items:
            # Update the item to set container_cleared to "true"
            table.update_item(
                Key={
                    'code': item['code']
                },
                UpdateExpression='SET container_cleared = :val',
                ExpressionAttributeValues={
                    ':val': "true"
                }
            )
        # Reset scans_enabled to allow new scans
        with data_lock:
            scans_enabled = True
        return '', 200
    except ClientError as e:
        print(f"Error clearing data from DynamoDB: {e.response['Error']['Message']}")
        return jsonify({'error': 'Error clearing data'}), 500

if __name__ == '__main__':
    ser_code = serial.Serial(
        port='COM5',
        baudrate=9600,  # Verify the baud rate
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=1  # Set a timeout to prevent blocking
    )

    ser_weight = serial.Serial('COM6', 9600) # Keep COM6 for the weight sensor
    time.sleep(2)

    thread_code = threading.Thread(target=read_code_from_serial, args=(ser_code,))
    thread_weight = threading.Thread(target=read_weight_from_serial, args=(ser_weight,))
    thread_code.daemon = True
    thread_weight.daemon = True
    thread_code.start()
    thread_weight.start()

    app.run(debug=True, use_reloader=False)