import requests
creds_path = r'd:\1code\DeskTop_py\RM_FB_chrome\vpn_configs\credentials.txt'
u, p = open(creds_path).read().splitlines()[:2]
server = 'al-tia.prod.surfshark.com'
ports = [80, 443, 8080, 1232, 3128, 8000]

for port in ports:
    try:
        proxy_url = f'http://{u}:{p}@{server}:{port}'
        resp = requests.get('http://ip-api.com/json/', proxies={'http': proxy_url, 'https': proxy_url}, timeout=3)
        print(f'Testing {port}... Success: {resp.json().get("query")}')
    except Exception as e:
        print(f'Port {port} failed: {type(e).__name__}')