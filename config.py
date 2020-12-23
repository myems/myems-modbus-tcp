myems_system_db = {
    'user': 'root',
    'password': '!MyEMS1',
    'host': '127.0.0.1',
    'database': 'myems_system_db',
    'port': 3306,
}

myems_historical_db = {
    'user': 'root',
    'password': '!MyEMS1',
    'host': '127.0.0.1',
    'database': 'myems_historical_db',
    'port': 3306,
}

# Indicates how long the process waits between readings
interval_in_seconds = 180

# Get the gateway ID and token from MyEMS Admin
# This is used for getting data sources associated with the gateway
gateway = {
    'id': 1,
    'token': 'AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA'
}
