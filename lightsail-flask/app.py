from flask import Flask, jsonify, render_template
import boto3
import threading
from boto3.dynamodb.conditions import Key, Attr
from decimal import Decimal, InvalidOperation  # Import Decimal

AWS_REGION = 'us-west-2'
AWS_ACCESS_KEY = ''       # Replace with your AWS access key
AWS_SECRET_KEY = ''       # Replace with your AWS secret key

DYNAMODB_TABLE_NAME = 'ScannedData'  # Replace with your DynamoDB table name

app = Flask(__name__)

data_list = []  # Global list to store dictionaries of scanned code and weight
data_lock = threading.Lock()  # To prevent race conditions when accessing data_list

MAX_WEIGHT = Decimal('1.0')  # Maximum weight in kg, use Decimal

def parse_scanned_code(code):
    # Parsing code remains the same
    parsed_data = {}
    try:
        parsed_data['producto_id'] = code[0:4]
        parsed_data['genero_code'] = code[4]
        parsed_data['talla_code'] = code[5:7]
        parsed_data['material_code'] = code[7:9]
        parsed_data['pais_code'] = code[9:11]
        parsed_data['año'] = code[11:13]

        # Map codes to actual values
        parsed_data['genero'] = 'Hombre' if parsed_data['genero_code'] == 'H' else 'Mujer'

        talla_map = {
            '01': 'XS',
            '02': 'S',
            '03': 'M',
            '04': 'L',
            '05': 'XL'
        }
        parsed_data['talla'] = talla_map.get(parsed_data['talla_code'], 'Unknown')

        material_map = {
            '01': 'Algodón',
            '02': 'Poliéster',
            '03': 'Lana',
            '04': 'Seda',
            '05': 'Lino'
        }
        parsed_data['material'] = material_map.get(parsed_data['material_code'], 'Unknown')

        pais_map = {
            '01': 'China',
            '02': 'India',
            '03': 'Bangladesh',
            '04': 'Vietnam',
            '05': 'México'
        }
        parsed_data['pais'] = pais_map.get(parsed_data['pais_code'], 'Unknown')

        # Optionally, parse año to full year
        parsed_data['año'] = '20' + parsed_data['año']  # Assuming year 2020-2030

    except Exception as e:
        print(f"Error parsing scanned code: {e}")
        parsed_data = {}

    return parsed_data

def fetch_data_from_dynamodb():
    global data_list
    with data_lock:
        try:
            # Initialize DynamoDB resource
            dynamodb = boto3.resource(
                'dynamodb',
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS_KEY,
                aws_secret_access_key=AWS_SECRET_KEY
            )
            # Reference the DynamoDB table
            table = dynamodb.Table(DYNAMODB_TABLE_NAME)

            # Fetch all items where 'container_cleared' is 'false'
            response = table.scan(
                FilterExpression=Attr('container_cleared').eq('false')
            )
            items = response.get('Items', [])

            data_list.clear()
            for item in items:
                code = item.get('code')
                weight = item.get('weight')
                timestamp = item.get('timestamp')

                # Convert Decimal fields to float
                if isinstance(weight, Decimal):
                    weight = float(weight)
                if isinstance(timestamp, Decimal):
                    timestamp = float(timestamp)

                date_year = item.get('date_year')
                date_month = item.get('date_month')
                date_day = item.get('date_day')
                time_str = item.get('time')

                # Construct datetime string
                if date_year and date_month and date_day and time_str:
                    time_display = f"{date_year}-{date_month}-{date_day} {time_str}"
                elif time_str:
                    time_display = time_str
                else:
                    time_display = 'N/A'

                # If parsed data is already in the item, use it; otherwise, parse it
                genero = item.get('sex') or item.get('genero')
                talla = item.get('size') or item.get('talla')
                material = item.get('material')
                pais = item.get('country') or item.get('pais')
                año = item.get('year') or item.get('año')

                if not all([genero, talla, material, pais, año]):
                    parsed_data = parse_scanned_code(code)
                    genero = parsed_data.get('genero')
                    talla = parsed_data.get('talla')
                    material = parsed_data.get('material')
                    pais = parsed_data.get('pais')
                    año = parsed_data.get('año')

                data_entry = {
                    "code": code,
                    "weight": weight,
                    "timestamp": timestamp,
                    "time_display": time_display,
                    "genero": genero,
                    "talla": talla,
                    "material": material,
                    "pais": pais,
                    "año": año
                }
                data_list.append(data_entry)

            # Sort data_list by timestamp
            data_list.sort(key=lambda x: x.get('timestamp', 0))

        except Exception as e:
            print(f"Error fetching data from DynamoDB: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin.html')
def admin_page():
    return render_template('admin.html')

@app.route('/data')
def get_data():
    fetch_data_from_dynamodb()
    with data_lock:
        last_weight = data_list[-1]['weight'] if data_list else 0.0
        # Compute total weight
        try:
            total_weight = sum(Decimal(str(item['weight'])) for item in data_list)
        except (ValueError, InvalidOperation):
            total_weight = Decimal('0.0')  # Handle any non-numeric weight values
        scans_enabled = total_weight <= MAX_WEIGHT
        return jsonify({
            'last_weight': last_weight,
            'data_list': data_list,
            'scans_enabled': scans_enabled
        })

@app.route('/admin/data')
def get_admin_data():
    fetch_data_from_dynamodb()
    with data_lock:
        total_items = len(data_list)
        gender_counts = {'M': 0, 'H': 0}
        material_counts = {}
        size_counts = {}

        for entry in data_list:
            genero = entry.get('genero')
            if genero == 'Mujer':
                gender_counts['M'] += 1
            elif genero == 'Hombre':
                gender_counts['H'] += 1

            material = entry.get('material')
            if material:
                material_counts[material] = material_counts.get(material, 0) + 1

            talla = entry.get('talla')
            if talla:
                size_counts[talla] = size_counts.get(talla, 0) + 1

        return jsonify({
            'total_items': total_items,
            'gender_counts': gender_counts,
            'material_counts': material_counts,
            'size_counts': size_counts
        })

@app.route('/admin/clear', methods=['POST'])
def clear_data():
    with data_lock:
        try:
            dynamodb = boto3.resource(
                'dynamodb',
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS_KEY,
                aws_secret_access_key=AWS_SECRET_KEY
            )
            table = dynamodb.Table(DYNAMODB_TABLE_NAME)

            # Scan for items where 'container_cleared' is 'false'
            response = table.scan(
                FilterExpression=Attr('container_cleared').eq('false')
            )
            items = response.get('Items', [])

            # Update 'container_cleared' to 'true' for these items
            for item in items:
                table.update_item(
                    Key={
                        'code': item['code']
                    },
                    UpdateExpression='SET container_cleared = :val',
                    ExpressionAttributeValues={
                        ':val': 'true'
                    }
                )
            # Clear local data_list
            data_list.clear()
            return '', 200
        except Exception as e:
            print(f"Error clearing data from DynamoDB: {e}")
            return jsonify({'error': 'Error clearing data'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, use_reloader=False)
