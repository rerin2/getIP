import socket
import requests
import re
import subprocess
import platform
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
    """기본 IP 및 ISP 상세 조회"""
    try:
        api_url = f"http://ip-api.com/json/{ip_address}"
        response = requests.get(api_url, timeout=5)
        data = response.json()
        
        if data['status'] == 'success':
            return {
                "Domain": domain if domain else "N/A (My Public IP)",
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

def get_ip_info_simple(ip_address):
    """라우팅 추적용 간소화된 정보 조회"""
    try:
        api_url = f"http://ip-api.com/json/{ip_address}"
        response = requests.get(api_url, timeout=2) 
        data = response.json()
        
        if data['status'] == 'success':
            return {
                "Country": data.get('country', 'N/A'),
                "City": data.get('city', 'N/A'),
                "ISP": data.get('isp', 'N/A')
            }
        return None
    except:
        return None

def trace_route(domain):
    """지정된 도메인/IP의 라우팅 경로를 추적하고 각 IP의 정보를 출력합니다."""
    print(f"\n[*] '{domain}' 라우팅 경로 추적을 시작합니다. (최대 30홉)")
    print("-" * 90)
    
    system = platform.system().lower()
    
    # --- [수정 항목] 타임아웃 및 시도 횟수 제한 옵션 추가 ---
    if system == 'windows':
        # -w 1000 : 대기 시간을 1000ms(1초)로 제한 (3번 시도하므로 총 3초 소요)
        command = ['tracert', '-d', '-4', '-w', '1000', domain] 
    else:
        # -w 3 : 타임아웃 3초 제한, -q 1 : 테스트 쿼리를 1번만 전송하여 3초 만에 패스
        command = ['traceroute', '-n', '-4', '-w', '3', '-q', '1', domain]
        
    try:
        process = subprocess.Popen(
            command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            errors='ignore'
        )
        
        hop_pattern = re.compile(r'^\s*(\d+)\s+')
        ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
        time_pattern = re.compile(r'(<?\d+)\s*ms')
        
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
                
            hop_match = hop_pattern.search(line)
            if hop_match:
                hop_num = hop_match.group(1)
                ip_match = ip_pattern.findall(line)
                
                if ip_match:
                    ip_address = ip_match[-1]
                    times = time_pattern.findall(line)
                    latency = f"{times[0]}ms" if times else "N/A"
                    
                    info = get_ip_info_simple(ip_address)
                    
                    if info:
                        print(f"[Hop {hop_num:>2}] {ip_address:<15} | 지연: {latency:<6} | 국가: {info['Country']:<12} | 도시: {info['City']:<15} | ISP: {info['ISP']}")
                    else:
                        print(f"[Hop {hop_num:>2}] {ip_address:<15} | 지연: {latency:<6} | 정보 없음 (사설망 또는 조회 불가)")
                        
                else:
                    if '*' in line:
                        print(f"[Hop {hop_num:>2}] * 요청 시간 초과 (3초 대기 후 패스)")
                        
        process.wait()
        print("-" * 90)
        print("[*] 라우팅 경로 추적이 완료되었습니다.")
        
    except FileNotFoundError:
        print("[!] tracert(또는 traceroute) 명령어를 찾을 수 없습니다. OS 환경을 확인해주세요.")
    except Exception as e:
        print(f"[!] 추적 중 오류 발생: {e}")

if __name__ == "__main__":
    print("=== IP & ISP 및 라우팅 조회 도구 ===")
    print("- URL 또는 도메인 입력: 해당 주소 IP/ISP 조회")
    print("- 'm' 입력: 현재 기기의 공인 IP 조회")
    print("- 't' 입력: 라우팅 추적 (Traceroute) 실행")
    print("- 'q' 입력: 프로그램 종료")
    
    while True:
        target_url = input("\n[입력 대기] 도메인/URL, m(내 IP), t(라우팅 추적), q(종료) : ").strip()
        
        if target_url.lower() in ['q', 'exit']:
            print("프로그램을 종료합니다.")
            break
            
        if not target_url:
            continue
            
        if target_url.lower() == 'm':
            print("\n[*] 현재 기기의 공인 IP 정보를 조회합니다...")
            result = get_ip_info()
            
            print("-" * 35)
            for key, value in result.items():
                print(f"{key}: {value}")
            print("-" * 35)
            
        elif target_url.lower() == 't':
            trace_target = input("라우팅을 추적할 도메인 또는 IP를 입력하세요: ").strip()
            if trace_target:
                domain = clean_domain(trace_target)
                trace_route(domain)
            else:
                print("[!] 입력이 취소되었습니다.")
                
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