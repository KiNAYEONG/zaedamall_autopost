# tools/auto_write_debug.py
# iframe 구조만 출력해서 확인

import time, argparse
from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def setup_driver():
    opts = ChromeOptions()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-popup-blocking")
    service = Service(ChromeDriverManager().install())
    return Chrome(service=service, options=opts)

def debug_iframes(drv, url):
    print(f"📍 글쓰기 페이지 이동: {url}")
    drv.get(url)
    time.sleep(2)

    iframes = drv.find_elements(By.TAG_NAME, "iframe")
    print(f"발견된 iframe 개수: {len(iframes)}")
    for i, iframe in enumerate(iframes):
        iframe_id = iframe.get_attribute("id") or "없음"
        iframe_name = iframe.get_attribute("name") or "없음"
        iframe_src = iframe.get_attribute("src") or "없음"
        print(f"  iframe {i}: id={iframe_id}, name={iframe_name}, src={iframe_src}")
        try:
            drv.switch_to.frame(iframe)
            bodies = drv.find_elements(By.TAG_NAME, "body")
            for j, b in enumerate(bodies):
                print(f"    body {j}: class={b.get_attribute('class')}, contenteditable={b.get_attribute('contenteditable')}")
        finally:
            drv.switch_to.default_content()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    args = ap.parse_args()
    drv = setup_driver()
    debug_iframes(drv, args.url)
    input("🔍 구조 확인 후 엔터를 누르면 브라우저가 닫힙니다...")
    drv.quit()

if __name__ == "__main__":
    main()
