import socket
import requests
import re
from urllib.parse import urlparse

def clean_domain(user_input):
    if not re.match(r'^https?://', user_input):
        user_input = 'http://' + user_input
        
    parsed = urlparse(user_input)
    domain = parsed.netloc
    
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain

def resolve_domain(domain):
    try:
        _, _, ip_list = socket.gethostbyname_ex(domain)
        return list(set(ip_list))
    except socket.gaierror:
        return []

def get_ip_info(ip_address="", domain=""):
    """
    특정 IP의 위치 및 ISP 정보를 조회합니다. 
    ip_address가 빈 문자열이면 현재 기기의 공인 IP를 조회합니다.
    """
    try:
        # IP가 비어있으면(내 IP 조회) 엔드포인트가 'http://ip-api.com/json/' 이 됨
        api_url = f"http://ip-api.com/json/{ip_address}"
        response = requests.get(api_url)
        data = response.json()
        
        if data['status'] == 'success':
            return {
                # 내 IP 조회 시에는 도메인이 없으므로 'N/A' 처리
                "Domain": domain if domain else "N/A (My Public IP)",
                # ip-api 응답 중 'query' 필드에 실제 조회된 IP가 담겨옴
                "IP Address": data.get('query'), 
                "ISP": data.get('isp'),
                "Country": data.get('country'),
                "City": data.get('city'),
                "Organization": data.get('org')
            }
        else:
            return {"Error": "IP 정보를 가져오는데 실패했습니다."}
            
    except Exception as e:
        return {"Error": str(e)}

if __name__ == "__main__":
    print("=== IP & ISP 조회 도구 ===")
    
    while True:
        # 안내 문구에 'm' 옵션 추가
        target_url = input("\n조회할 URL/도메인 입력 (내 공인 IP 조회: 'm', 종료: 'q'): ").strip()
        
        if target_url.lower() in ['q', 'exit']:
            print("프로그램을 종료합니다.")
            break
            
        if not target_url:
            continue
            
        # [신규 추가] 'm'을 입력했을 때 내 공인 IP 조회 분기
        if target_url.lower() == 'm':
            print("\n[*] 현재 기기의 공인 IP 정보를 조회합니다...")
            result = get_ip_info()
            
            print("-" * 35)
            for key, value in result.items():
                print(f"{key}: {value}")
            print("-" * 35)
            
        # 일반 도메인/URL을 입력했을 때의 기존 로직
        else:
            domain = clean_domain(target_url)
            print(f"\n[*] 대상 도메인: {domain}")
            
            ip_list = resolve_domain(domain)
            
            if not ip_list:
                print("[!] 도메인의 IP 주소를 찾을 수 없습니다. 다시 확인해주세요.")
                continue
                
            selected_ip = None
            
            if len(ip_list) == 1:
                selected_ip = ip_list[0]
                print(f"[*] 1개의 IP가 발견되었습니다: {selected_ip}")
            else:
                print(f"[*] {len(ip_list)}개의 IP가 발견되었습니다. 조회할 IP를 선택하세요:")
                for i, ip in enumerate(ip_list):
                    print(f"  {i + 1}. {ip}")
                
                while True:
                    choice = input("조회할 번호를 선택하세요 (취소: 'c'): ").strip()
                    if choice.lower() == 'c':
                        break
                    if choice.isdigit() and 1 <= int(choice) <= len(ip_list):
                        selected_ip = ip_list[int(choice) - 1]
                        break
                    else:
                        print("[!] 목록에 있는 올바른 번호를 입력해주세요.")
                
                if not selected_ip:
                    continue 
            
            print(f"\n[*] {selected_ip} 정보 조회 중...")
            result = get_ip_info(selected_ip, domain)
            
            print("-" * 35)
            for key, value in result.items():
                print(f"{key}: {value}")
            print("-" * 35)
        
        # 조회가 끝난 후 공통적으로 재시도 여부 확인
        while True:
            retry = input("\n계속 조회하시겠습니까? (y/n): ").strip().lower()
            if retry in ['y', 'n', 'q']:
                break
            print("[!] 'y' 또는 'n'을 입력해주세요.")
            
        if retry in ['n', 'q']:
            print("프로그램을 종료합니다.")
            break