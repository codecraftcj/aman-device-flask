import requests
API_ENDPOINT = "http://0.0.0.0:8082" 
response = requests.get(f"{API_ENDPOINT}/get-jobs")
print(response)