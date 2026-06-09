import time
import json
import requests
from kafka import KafkaProducer

producer = KafkaProducer(
    bootstrap_servers=['broker:9092'],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)
TOPIC_NAME = 'raw-adsb'

def fetch_and_send_flights():
    # Obszar Polski + trochę Czech i Słowacji
    url = "https://opensky-network.org/api/states/all?lamin=49.0&lomin=14.0&lamax=55.0&lomax=24.0" 
    
    while True:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                states = data.get('states', [])
                
                if states:
                    for state in states:
                        flight_data = {
                            "icao24": state[0],
                            "callsign": state[1].strip() if state[1] else "UNKNOWN",
                            "origin_country": state[2],
                            "longitude": state[5],
                            "latitude": state[6],
                            "altitude": state[7],
                            "on_ground": state[8],
                            "velocity": state[9],
                            "vertical_rate": state[11]
                        }
                        if flight_data['longitude'] and flight_data['latitude']:
                            producer.send(TOPIC_NAME, flight_data)
                    
                    print(f"Wysłano {len(states)} lotów do Kafki.")
            time.sleep(10)
        except Exception as e:
            print(f"Błąd API: {e}")
            time.sleep(10)

if __name__ == "__main__":
    fetch_and_send_flights()