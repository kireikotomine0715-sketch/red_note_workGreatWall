import time
import json
import random
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains


# ==================== 核心逻辑（与原脚本一致）====================

def init_driver(headless=False):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def load_comments(filepath):
    if filepath.endswith(".json"):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    else:
        with open(filepath, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]


def _find_editor(driver):
    return WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "content-textarea"))
    )


def _find_button(driver):
    return WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn.submit:not([disabled])"))
    )


def send_comment(driver, text, max_retries=3):
    def _send_once():
        editor = _find_editor(driver)
        ActionChains(driver).move_to_element(editor).click().perform()
        time.sleep(0.3)

        editor = _find_editor(driver)
        driver.execute_script("arguments[0].textContent = arguments[1];", editor, text)
        driver.execute_script("""
            arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
            arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
            arguments[0].dispatchEvent(new Event('keyup', {bubbles: true}));
        """, editor)

        time.sleep(1)
        submit_btn = _find_button(driver)
        submit_btn.click()

    for attempt in range(1, max_retries + 1):
        try:
            _send_once()
            return
        except StaleElementReferenceException:
            time.sleep(1)
        except Exception:
            raise
    raise RuntimeError(f"重试 {max_retries} 次后仍然失败")


# ==================== GUI ====================


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("洛克王国自动砌长城工具-童年的纸飞机，现在终于飞回我手里")
        self.root.geometry("640x620")
        self.root.resizable(False, False)

        self.driver = None
        self.running = False
        self.thread = None

        self._build_ui()

    def _build_ui(self):
        # 主框架
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # ---------- URL ----------
        ttk.Label(main, text="目标网址").pack(anchor=tk.W)
        self.url_var = tk.StringVar(value="")
        url_frame = ttk.Frame(main)
        url_frame.pack(fill=tk.X, pady=(2, 10))
        ttk.Entry(url_frame, textvariable=self.url_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ---------- 字典文件 ----------
        ttk.Label(main, text="字典文件").pack(anchor=tk.W)
        dict_frame = ttk.Frame(main)
        dict_frame.pack(fill=tk.X, pady=(2, 10))
        self.dict_var = tk.StringVar(value="comments.txt")
        ttk.Entry(dict_frame, textvariable=self.dict_var, width=50).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(dict_frame, text="浏览", command=self._browse_dict, width=6).pack(side=tk.LEFT, padx=(5, 0))

        # ---------- 定时参数 ----------
        ttk.Label(main, text="发送间隔（秒），系统会在区间内随机").pack(anchor=tk.W)
        interval_frame = ttk.Frame(main)
        interval_frame.pack(fill=tk.X, pady=(2, 10))
        ttk.Label(interval_frame, text="最小").pack(side=tk.LEFT)
        self.min_var = tk.IntVar(value=60)
        ttk.Entry(interval_frame, textvariable=self.min_var, width=8).pack(side=tk.LEFT, padx=(3, 12))
        ttk.Label(interval_frame, text="最大").pack(side=tk.LEFT)
        self.max_var = tk.IntVar(value=120)
        ttk.Entry(interval_frame, textvariable=self.max_var, width=8).pack(side=tk.LEFT, padx=(3, 0))

        # ---------- 选项 ----------
        opt_frame = ttk.Frame(main)
        opt_frame.pack(fill=tk.X, pady=(5, 10))
        self.headless_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="无头模式（后台运行，不显示浏览器窗口）", variable=self.headless_var).pack(side=tk.LEFT)
        self.login_wait_var = tk.IntVar(value=60)
        ttk.Label(opt_frame, text="登录等待(秒):").pack(side=tk.LEFT, padx=(30, 3))
        ttk.Entry(opt_frame, textvariable=self.login_wait_var, width=5).pack(side=tk.LEFT)

        # ---------- 按钮 ----------
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        self.start_btn = ttk.Button(btn_frame, text="开始发送", command=self._start, width=14)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self._stop, width=14, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT)
        self.count_label = ttk.Label(btn_frame, text="已发送: 0 条")
        self.count_label.pack(side=tk.RIGHT)

        # ---------- 日志区 ----------
        ttk.Label(main, text="运行日志").pack(anchor=tk.W)
        log_frame = ttk.Frame(main)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_text = tk.Text(log_frame, height=14, state=tk.DISABLED, wrap=tk.WORD,
                                font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
                                insertbackground="white")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ---------- 日志方法 ----------
    def _log(self, msg):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ---------- 文件浏览 ----------
    def _browse_dict(self):
        path = filedialog.askopenfilename(
            title="选择字典文件",
            filetypes=[("文本文件", "*.txt"), ("JSON 文件", "*.json"), ("所有文件", "*.*")]
        )
        if path:
            self.dict_var.set(path)

    # ---------- UI 状态切换 ----------
    def _set_ui_state(self, running):
        state = tk.DISABLED if running else tk.NORMAL
        self.start_btn.configure(state=state)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)

    # ---------- 启停 ----------
    def _start(self):
        url = self.url_var.get().strip()
        dict_file = self.dict_var.get().strip()
        min_sec = self.min_var.get()
        max_sec = self.max_var.get()

        if not url:
            messagebox.showerror("错误", "请输入目标网址")
            return
        if not dict_file:
            messagebox.showerror("错误", "请选择字典文件")
            return
        if min_sec <= 0 or max_sec <= 0 or max_sec < min_sec:
            messagebox.showerror("错误", "定时参数不合法：需要 最小 > 0 且 最大 >= 最小")
            return

        try:
            comments = load_comments(dict_file)
        except FileNotFoundError:
            messagebox.showerror("错误", f"字典文件不存在:\n{dict_file}")
            return
        except Exception as e:
            messagebox.showerror("错误", f"读取字典文件失败:\n{e}")
            return

        if not comments:
            messagebox.showerror("错误", "字典文件为空")
            return

        self.running = True
        self._set_ui_state(True)
        self.count_label.configure(text="已发送: 0 条")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

        self._log(f"已加载 {len(comments)} 条评论")
        self._log(f"目标: {url}")

        self.thread = threading.Thread(
            target=self._run,
            args=(url, comments, min_sec, max_sec),
            daemon=True
        )
        self.thread.start()

    def _stop(self):
        self._log("正在停止...")
        self.running = False

    # ---------- 主循环（运行在子线程） ----------
    def _run(self, url, comments, min_sec, max_sec):
        try:
            self.driver = init_driver(headless=self.headless_var.get())
            self.driver.get(url)
        except Exception as e:
            self.root.after(0, lambda: self._log(f"[错误] 浏览器启动失败: {e}"))
            self.root.after(0, self._on_stopped)
            return

        login_wait = self.login_wait_var.get()
        self.root.after(0, lambda: self._log(f"页面已打开，等待 {login_wait} 秒（请手动登录）..."))

        for remaining in range(login_wait, 0, -1):
            if not self.running:
                self.driver.quit()
                self.root.after(0, self._on_stopped)
                return
            time.sleep(1)

        idx = 0
        count = 0
        while self.running:
            text = comments[idx % len(comments)]
            try:
                send_comment(self.driver, text)
                count += 1
                idx += 1
                self.root.after(0, lambda c=count: self.count_label.configure(text=f"已发送: {c} 条"))
                self.root.after(0, lambda t=text: self._log(f"已发送: {t}"))

                delay = random.randint(min_sec, max_sec)
                self.root.after(0, lambda d=delay: self._log(f"等待 {d} 秒..."))
                # 分段 sleep，可随时响应停止
                for _ in range(delay):
                    if not self.running:
                        break
                    time.sleep(1)

            except StaleElementReferenceException:
                self.root.after(0, lambda: self._log("[警告] 元素失效，刷新页面重试..."))
                try:
                    self.driver.refresh()
                    time.sleep(8)
                except Exception:
                    pass
            except Exception as e:
                self.root.after(0, lambda e=e: self._log(f"[错误] {e}"))
                try:
                    self.driver.refresh()
                    time.sleep(8)
                except Exception:
                    pass

        self.driver.quit()
        self.root.after(0, self._on_stopped)

    def _on_stopped(self):
        self.running = False
        self._set_ui_state(False)
        self._log("已停止。")


# ==================== 入口 ====================

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
