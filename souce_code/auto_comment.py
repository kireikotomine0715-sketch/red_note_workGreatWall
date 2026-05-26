import time
import json
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains

# ==================== 配置区 ====================
TARGET_URL = "https://www.xiaohongshu.com/explore/6a12ef570000000035025562?xsec_token=ABjotNtB5wKnwwq8aazZsDsnxoKfMRR5_6SSH51l7j-xs=&xsec_source=pc_search"          # 目标网页
DICT_FILE = "comments.txt"                   # 字典文件（一行一条）
INTERVAL_MIN = 60                            # 最小间隔秒数
INTERVAL_MAX = 120                           # 最大间隔秒数（随机，防检测）
HEADLESS = False                             # 是否无头模式
MAX_RETRIES = 3                              # 单次发送最大重试次数
# =================================================


def load_comments(filepath):
    """从字典文件加载评论列表，支持 .txt（每行一条）和 .json（数组）"""
    if filepath.endswith(".json"):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]


def init_driver():
    options = webdriver.ChromeOptions()
    if HEADLESS:
        options.add_argument("--headless")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def _find_editor(driver):
    """每次重新查找输入框，避免 stale element"""
    return WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "content-textarea"))
    )


def _find_button(driver):
    """每次重新查找发送按钮，等待 enabled"""
    return WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.submit:not([disabled])"))
    )


def send_comment(driver, text):
    """执行一次评论发送，内置重试处理 stale element"""

    def _send_once():
        # 1. 找到输入框，点击聚焦
        editor = _find_editor(driver)
        ActionChains(driver).move_to_element(editor).click().perform()
        time.sleep(0.3)

        # 2. 填入文字（每次都重新找到元素，避免 stale）
        editor = _find_editor(driver)
        driver.execute_script("arguments[0].textContent = arguments[1];", editor, text)
        driver.execute_script("""
            arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
            arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
            arguments[0].dispatchEvent(new Event('keyup', {bubbles: true}));
        """, editor)

        # 3. 等 Vue 重新渲染后，重新找到按钮并点击
        time.sleep(1)
        submit_btn = _find_button(driver)
        submit_btn.click()
        print(f"[{time.strftime('%H:%M:%S')}] 已发送: {text}")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            _send_once()
            return  # 成功则退出
        except StaleElementReferenceException:
            print(f"  [重试] 第 {attempt} 次遇到 stale element，重新获取元素...")
            time.sleep(1)
        except Exception as e:
            # 其他异常直接抛出，由外层处理
            raise e

    # 重试耗尽
    raise RuntimeError(f"重试 {MAX_RETRIES} 次后仍然 stale element，跳过本条")


def main():
    comments = load_comments(DICT_FILE)
    if not comments:
        print("字典文件为空，退出。")
        return

    print(f"已加载 {len(comments)} 条评论")
    print(f"目标页面: {TARGET_URL}")
    print(f"发送间隔: {INTERVAL_MIN}~{INTERVAL_MAX} 秒")
    print("=" * 40)

    driver = init_driver()
    driver.get(TARGET_URL)

    try:
        print("页面已打开，如需要请手动登录。60 秒后自动开始...")
        time.sleep(60)

        idx = 0
        while True:
            text = comments[idx % len(comments)]
            try:
                send_comment(driver, text)
            except Exception as e:
                print(f"[错误] 发送失败: {e}")
                driver.refresh()
                time.sleep(10)
                continue

            idx += 1
            delay = random.randint(INTERVAL_MIN, INTERVAL_MAX)
            print(f"  -> 等待 {delay} 秒后发送下一条...")
            time.sleep(delay)

    except KeyboardInterrupt:
        print("\n已手动停止。")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
