import requests

base_url = "http://localhost:8000/api/gmail"

def check_endpoint():
    print("Testing /email/list")
    r = requests.get(f"{base_url}/email/list")
    print(r.status_code, r.text)
    
    print("\nTesting /email/read")
    r = requests.get(f"{base_url}/email/read")
    print(r.status_code, r.text)

    print("\nTesting /email/batch_read")
    r = requests.get(f"{base_url}/email/batch_read")
    print(r.status_code, r.text)

if __name__ == "__main__":
    check_endpoint()
