import oci
import os
import sys
import time
import requests

# ── Slack 설정 ──────────────────────────────────────────
SLACK_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = "C08GM55F90A"

def send_slack_message(message):
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {SLACK_TOKEN}",
        "Content-Type": "application/json; charset=utf-8"
    }
    payload = {
        "channel": SLACK_CHANNEL,
        "text": message
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        res_json = response.json()
        if not res_json.get("ok"):
            print(f"❌ 슬랙 전송 실패: {res_json.get('error')}")
    except Exception as e:
        print(f"❌ 슬랙 요청 에러: {e}")

# ── OCI 설정 ──────────────────────────────────────────────
config = {
    "user":        os.environ["OCI_USER"],
    "fingerprint": os.environ["OCI_FINGERPRINT"],
    "tenancy":     os.environ["OCI_TENANCY"],
    "region":      os.environ["OCI_REGION"],
    "key_content": os.environ["OCI_KEY_CONTENT"],
}

compute = oci.core.ComputeClient(config)

# ── 인스턴스 스펙 ──────────────────────────────────────────
details = oci.core.models.LaunchInstanceDetails(
    compartment_id=os.environ["OCI_COMPARTMENT_ID"],
    availability_domain=os.environ["OCI_AVAILABILITY_DOMAIN"],
    shape="VM.Standard.A1.Flex",
    shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
        ocpus=4,
        memory_in_gbs=24,
    ),
    subnet_id=os.environ["OCI_SUBNET_ID"],
    image_id=os.environ["OCI_IMAGE_ID"],
    display_name="free-tier-auto",
    metadata={
        "ssh_authorized_keys": os.environ["SSH_PUBLIC_KEY"]
    },
    create_vnic_details=oci.core.models.CreateVnicDetails(
        assign_public_ip=True,
        subnet_id=os.environ["OCI_SUBNET_ID"],
    ),
)

# ── 재시도 루프 (지수 백오프) ──────────────────────────────
delay     = 60       # 시작 간격 (초)
MAX_DELAY = 300      # GitHub Actions 제한상 최대 5분
attempt   = 0

while True:
    attempt += 1
    
    # 일반 시도 메시지 (멘션 없음 - 조용히 채널에 쌓임)
    status_msg = f"🔄 [오라클 봇] #{attempt}번째 인스턴스 생성 시도 중... (대기 간격: {delay}초)"
    print(status_msg)
    send_slack_message(status_msg)

    try:
        result = compute.launch_instance(details)
        instance_id = result.data.id
        
        # 💡 [성공 알림] <!here> 를 추가하여 강제 푸시 알림 유도
        success_msg = f"<!here> 🎉 [오라클 클라우드] 인스턴스 생성 성공!\n• ID: {instance_id}\n• 상태: {result.data.lifecycle_state}"
        print(success_msg)
        
        send_slack_message(success_msg)
        sys.exit(0)

    except oci.exceptions.ServiceError as e:
        if e.status == 429:
            delay = min(delay * 2, MAX_DELAY)
            print(f"⚠️  429 Too Many Requests → {delay}초 후 재시도")

        elif "Out of host capacity" in str(e.message):
            # 단순 용량 부족은 알림 없이 화면 로그에만 기록하고 재시도
            print(f"❌ 용량 부족 (Out of capacity) → {delay}초 후 재시도")

        elif "LimitExceeded" in str(e.code):
            # 💡 [한도 초과 알림] <!here> 추가 후 종료
            limit_msg = f"<!here> 🚫 [오라클 클라우드] 리소스 한도 초과 — 이미 인스턴스가 존재할 수 있습니다."
            print(limit_msg)
            
            send_slack_message(limit_msg)
            sys.exit(1)

        else:
            # 💡 [치명적 에러 알림] 설정값 오류 등 예외 발생 시 <!here> 추가 후 종료
            real_error_msg = f"<!here> 🚨 [오류 발생] 설정값이나 권한에 문제가 있습니다!\n코드: {e.code}\n내용: {e.message}"
            print(real_error_msg)
            
            send_slack_message(real_error_msg)
            sys.exit(1)

    time.sleep(delay)