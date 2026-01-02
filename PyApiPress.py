import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import requests
import threading
import time
from datetime import datetime
import json
import re
import os
import ast

# ===================== 全局配置 & 数据管理 =====================
CONFIG_FILE = "api_press_config.json"  # 配置文件路径
# 全局压测数据管理类
class TestData:
    def __init__(self):
        self.success_count = 0
        self.fail_count = 0
        self.response_times = []
        self.status_code_dict = {}
        self.current_request = 0
        self.total_requests = 0
        self.thread_num = 0
        self.is_running = False
        self.test_start_time = 0
        self.test_end_time = 0
        self.lock = threading.Lock()
        self.api1_response_data = None  # 存储API1响应数据，供API2调用

# 全局对象初始化
test_data = TestData()
root = tk.Tk()
controls = {}  # 存储所有控件，用于参数读写
# 全局控件声明
log_text = None
success_rate_label, qps_label, avg_rt_label = None, None, None
success_label, fail_label, total_time_label, min_rt_label, max_rt_label = None, None, None, None, None
detail_text = None
chain_switch = None  # 链式调用开关

# ===================== 核心方法：参数保存/加载（完整双API+链式配置） =====================
def save_config():
    """保存完整配置：双API参数+链式开关+所有配置项，无丢失"""
    config_data = {
        # 链式调用开关
        "enable_chain": chain_switch.get(),
        # API1 配置（左侧）
        "api1": {
            "target_url": controls["api1_url"].get().strip(),
            "request_method": controls["api1_method"].get(),
            "timeout": controls["api1_timeout"].get().strip(),
            "headers": controls["api1_headers"].get(1.0, tk.END).strip(),
            "data": controls["api1_data"].get(1.0, tk.END).strip()
        },
        # API2 配置（右侧）
        "api2": {
            "target_url": controls["api2_url"].get().strip(),
            "request_method": controls["api2_method"].get(),
            "thread_num": controls["api2_thread"].get().strip(),
            "total_requests": controls["api2_requests"].get().strip(),
            "timeout": controls["api2_timeout"].get().strip(),
            "headers": controls["api2_headers"].get(1.0, tk.END).strip(),
            "data": controls["api2_data"].get(1.0, tk.END).strip()
        }
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
        messagebox.showinfo("保存成功", "✅ 所有压测参数（双API+链式配置）已完整保存！")
        log_print(f"✅ 完整配置已保存至 {CONFIG_FILE}", "SUCCESS")
    except Exception as e:
        messagebox.showerror("保存失败", f"❌ 参数保存出错：{str(e)}")
        log_print(f"❌ 参数保存失败：{str(e)}", "ERROR")

def load_config():
    """加载完整配置：双API+链式开关+变量规则，精准还原界面"""
    if not os.path.exists(CONFIG_FILE):
        log_print(f"ℹ️ 未检测到历史配置，加载默认参数", "INFO")
        return
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        # 1. 加载链式调用开关
        chain_switch.set(config_data.get("enable_chain", False))
        
        # 2. 加载左侧API1配置
        api1_cfg = config_data.get("api1", {})
        controls["api1_url"].delete(0, tk.END)
        controls["api1_url"].insert(0, api1_cfg.get("target_url", "https://www.baidu.com"))
        controls["api1_method"].set(api1_cfg.get("request_method", "GET"))
        controls["api1_timeout"].delete(0, tk.END)
        controls["api1_timeout"].insert(0, api1_cfg.get("timeout", "5"))
        controls["api1_headers"].delete(1.0, tk.END)
        controls["api1_headers"].insert(tk.END, api1_cfg.get("headers", '{"Content-Type": "application/json"}'))
        controls["api1_data"].delete(1.0, tk.END)
        controls["api1_data"].insert(tk.END, api1_cfg.get("data", "{}"))
        
        # 3. 加载右侧API2配置
        api2_cfg = config_data.get("api2", {})
        controls["api2_url"].delete(0, tk.END)
        controls["api2_url"].insert(0, api2_cfg.get("target_url", "https://www.baidu.com"))
        controls["api2_method"].set(api2_cfg.get("request_method", "POST"))
        controls["api2_thread"].delete(0, tk.END)
        controls["api2_thread"].insert(0, api2_cfg.get("thread_num", "8"))
        controls["api2_requests"].delete(0, tk.END)
        controls["api2_requests"].insert(0, api2_cfg.get("total_requests", "200"))
        controls["api2_timeout"].delete(0, tk.END)
        controls["api2_timeout"].insert(0, api2_cfg.get("timeout", "5"))
        controls["api2_headers"].delete(1.0, tk.END)
        controls["api2_headers"].insert(tk.END, api2_cfg.get("headers", '{"Content-Type": "application/json"}'))
        controls["api2_data"].delete(1.0, tk.END)
        controls["api2_data"].insert(tk.END, api2_cfg.get("data", '{"token": "${token}", "userId": "${data.id}"}'))

        log_print(f"✅ 历史配置加载完成：双API参数+链式开关已还原", "SUCCESS")
    except Exception as e:
        messagebox.showwarning("加载失败", f"⚠️ 配置文件损坏，使用默认参数：{str(e)}")
        log_print(f"❌ 配置加载失败：{str(e)}", "ERROR")

# ===================== 核心方法：链式变量替换+API调用 =====================
def extract_json_value(json_data, key_path):
    """根据键路径提取JSON值，支持多级路径 例：data.user.id → 逐层取值"""
    try:
        keys = key_path.split(".")
        value = json_data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return None
        return value
    except Exception:
        return None

def replace_variables(content, data_dict):
    """替换内容中的 ${变量名} 为API1响应的实际值，支持多级路径"""
    if not content or not data_dict:
        return content
    # 正则匹配 ${xxx.xxx} 格式的变量
    pattern = r"\$\{([\w\.]+)\}"
    matches = re.findall(pattern, content)
    for key_path in matches:
        real_value = extract_json_value(data_dict, key_path)
        if real_value is not None:
            # 区分字符串/数字类型，保持原始格式
            if isinstance(real_value, (int, float, bool)):
                content = content.replace(f"${{{key_path}}}", str(real_value))
            else:
                content = content.replace(f"${{{key_path}}}", json.dumps(real_value).strip('"'))
    return content

def call_api1():
    """调用前置API1，获取响应数据并存储，供API2使用"""
    try:
        url = controls["api1_url"].get().strip()
        method = controls["api1_method"].get()
        timeout = int(controls["api1_timeout"].get().strip())
        headers = parse_json(controls["api1_headers"].get(1.0, tk.END).strip())
        data = parse_json(controls["api1_data"].get(1.0, tk.END).strip())

        if not url.startswith(("http://", "https://")):
            raise ValueError("API1地址格式错误，必须以http/https开头")
        
        # 发送API1请求
        session = requests.Session()
        resp = None
        if method == "GET":
            resp = session.get(url, headers=headers, timeout=timeout)
        elif method == "POST":
            resp = session.post(url, headers=headers, json=data, timeout=timeout)
        elif method == "PUT":
            resp = session.put(url, headers=headers, json=data, timeout=timeout)
        elif method == "DELETE":
            resp = session.delete(url, headers=headers, timeout=timeout)
        
        resp.raise_for_status()
        api1_data = resp.json()
        test_data.api1_response_data = api1_data
        log_print(f"✅ API1调用成功 | 状态码：{resp.status_code} | 响应数据：{json.dumps(api1_data, ensure_ascii=False)}", "SUCCESS")
        return True
    except Exception as e:
        log_print(f"❌ API1调用失败：{str(e)}", "ERROR")
        messagebox.showerror("API1失败", f"前置接口调用出错：{str(e)}")
        return False

def send_chain_request():
    """链式调用核心：API1成功后，变量替换+调用API2（多线程）"""
    while True:
        with test_data.lock:
            if not test_data.is_running or test_data.current_request >= test_data.total_requests:
                break
            test_data.current_request += 1
            current = test_data.current_request
            total = test_data.total_requests

        log_print(f"📶 链式压测进度：{current}/{total} 次请求", "PROGRESS")
        try:
            # 1. 获取API2原始配置
            url = controls["api2_url"].get().strip()
            method = controls["api2_method"].get()
            timeout = int(controls["api2_timeout"].get().strip())
            raw_headers = controls["api2_headers"].get(1.0, tk.END).strip()
            raw_data = controls["api2_data"].get(1.0, tk.END).strip()

            # 2. 变量替换：API2请求头/体 替换为API1的实际值
            replaced_headers = replace_variables(raw_headers, test_data.api1_response_data)
            replaced_data = replace_variables(raw_data, test_data.api1_response_data)
            headers = parse_json(replaced_headers)
            data = parse_json(replaced_data)

            # 3. 发送API2请求
            start_time = time.time()
            session = requests.Session()
            resp = None
            if method == "GET":
                resp = session.get(url, headers=headers, timeout=timeout)
            elif method == "POST":
                resp = session.post(url, headers=headers, json=data, timeout=timeout)
            elif method == "PUT":
                resp = session.put(url, headers=headers, json=data, timeout=timeout)
            elif method == "DELETE":
                resp = session.delete(url, headers=headers, timeout=timeout)
            
            resp.raise_for_status()
            rt = round((time.time() - start_time) * 1000, 2)
            
            # 4. 统计数据
            with test_data.lock:
                test_data.response_times.append(rt)
                code = resp.status_code
                test_data.status_code_dict[code] = test_data.status_code_dict.get(code, 0) + 1
                test_data.success_count += 1
            log_print(f"✅ API2请求成功 | 状态码：{code} | 响应时间：{rt}ms", "SUCCESS")

        except Exception as e:
            with test_data.lock:
                test_data.fail_count += 1
                test_data.status_code_dict["ERROR"] = test_data.status_code_dict.get("ERROR", 0) + 1
            log_print(f"❌ API2请求失败：{str(e)}", "ERROR")

# ===================== 工具通用方法 =====================
def parse_json(text):
    """JSON解析，容错处理"""
    if not text or text.strip() == "":
        return {}
    try:
        return json.loads(text.strip())
    except Exception as e:
        log_print(f"⚠️ JSON解析失败：{str(e)}，使用空字典", "WARN")
        return {}

def log_print(content, level="INFO"):
    """线程安全的日志打印，分级着色"""
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_content = f"[{time_str}] [{level}] {content}\n"
    root.after(0, lambda: log_text.insert(tk.END, log_content))
    root.after(0, lambda: log_text.see(tk.END))
    tag = level if level in ["INFO", "SUCCESS", "ERROR", "WARN", "PROGRESS"] else "INFO"
    root.after(0, lambda: log_text.tag_add(tag, log_text.index("end-2l"), log_text.index("end-1l")))

def copy_log():
    """日志复制：选中/全量复制"""
    try:
        selected_text = log_text.get(tk.SEL_FIRST, tk.SEL_LAST) or log_text.get(1.0, tk.END)
        root.clipboard_clear()
        root.clipboard_append(selected_text)
        root.update()
        messagebox.showinfo("成功", "📋 日志已复制到剪贴板！")
    except tk.TclError:
        messagebox.showwarning("提示", "暂无日志可复制！")

def clear_log():
    """清空日志"""
    log_text.delete(1.0, tk.END)
    log_print("ℹ️ 日志区已清空，准备新一轮压测", "INFO")

def generate_report():
    """生成压测报告"""
    total_req = test_data.total_requests
    success_cnt = test_data.success_count
    fail_cnt = test_data.fail_count
    total_time = round(test_data.test_end_time - test_data.test_start_time, 2) if test_data.test_end_time else 0
    success_rate = round((success_cnt / total_req) * 100, 2) if total_req > 0 else 0
    qps = round(total_req / total_time, 2) if total_time > 0 else 0

    rt_list = test_data.response_times
    avg_rt = round(sum(rt_list)/len(rt_list), 2) if rt_list else 0
    min_rt = round(min(rt_list), 2) if rt_list else 0
    max_rt = round(max(rt_list), 2) if rt_list else 0
    code_dist = test_data.status_code_dict

    # 更新报表UI
    success_rate_label.config(text=f"成功率：{success_rate} %")
    qps_label.config(text=f"QPS：{qps} req/s")
    avg_rt_label.config(text=f"平均响应时间：{avg_rt} ms")
    success_label.config(text=f"{success_cnt}")
    fail_label.config(text=f"{fail_cnt}")
    total_time_label.config(text=f"{total_time} s")
    min_rt_label.config(text=f"{min_rt} ms")
    max_rt_label.config(text=f"{max_rt} ms")

    detail_content = f"""【链式API压测报告】
🔗 链式调用状态：{"已启用" if chain_switch.get() else "未启用"}
📌 API1地址：{controls['api1_url'].get()} | API2地址：{controls['api2_url'].get()}
📌 压测配置：并发数 {test_data.thread_num} | 总请求数 {total_req} | 超时 {controls['api2_timeout'].get()}s
✅ 成功请求：{success_cnt} | ❌ 失败请求：{fail_cnt} | 📈 成功率：{success_rate}%
⏱ 压测总耗时：{total_time}s | ⚡ QPS：{qps} req/s
📊 响应时间：平均 {avg_rt}ms | 最小 {min_rt}ms | 最大 {max_rt}ms
📋 状态码分布：{code_dist}
"""
    detail_text.delete(1.0, tk.END)
    detail_text.insert(tk.END, detail_content)
    log_print("✅ 压测报告生成完成，查看下方报表", "SUCCESS")

def start_chain_test():
    """启动压测：链式开关判断+参数校验+执行"""
    # 参数校验
    try:
        thread_num = int(controls["api2_thread"].get().strip())
        total_requests = int(controls["api2_requests"].get().strip())
        api2_timeout = int(controls["api2_timeout"].get().strip())
        if thread_num <=0 or total_requests <=0 or api2_timeout <=0:
            raise ValueError("并发数、请求数、超时时间必须为正整数")
        if not controls["api2_url"].get().strip().startswith(("http://", "https://")):
            raise ValueError("API2地址格式错误，必须以http/https开头")
    except ValueError as e:
        messagebox.showerror("参数错误", f"⚠️ {str(e)}")
        return

    # 初始化压测数据
    with test_data.lock:
        test_data.success_count = 0
        test_data.fail_count = 0
        test_data.response_times = []
        test_data.status_code_dict = {}
        test_data.current_request = 0
        test_data.total_requests = total_requests
        test_data.thread_num = thread_num
        test_data.is_running = True
        test_data.test_start_time = time.time()
        test_data.api1_response_data = None

    controls["start_btn"]["state"] = tk.DISABLED
    controls["stop_btn"]["state"] = tk.NORMAL
    log_print(f"🚀 压测任务启动 | 并发数：{thread_num} | 总请求数：{total_requests}", "INFO")

    # 链式调用判断
    if chain_switch.get():
        log_print("🔗 已启用链式调用，开始执行前置API1...", "INFO")
        if not call_api1():  # API1调用失败则终止
            with test_data.lock:
                test_data.is_running = False
            controls["start_btn"]["state"] = tk.NORMAL
            controls["stop_btn"]["state"] = tk.DISABLED
            return
    else:
        log_print("ℹ️ 未启用链式调用，直接执行API2压测", "INFO")

    # 启动多线程执行API2压测
    for _ in range(thread_num):
        t = threading.Thread(target=send_chain_request, daemon=True)
        t.start()
    root.after(500, check_test_finish)

def stop_test():
    """停止压测"""
    with test_data.lock:
        test_data.is_running = False
    test_data.test_end_time = time.time()
    controls["start_btn"]["state"] = tk.NORMAL
    controls["stop_btn"]["state"] = tk.DISABLED
    log_print("🛑 压测任务已强制停止", "WARN")
    generate_report()

def check_test_finish():
    """检查压测完成状态"""
    if test_data.is_running and test_data.current_request < test_data.total_requests:
        root.after(500, check_test_finish)
        return
    if test_data.is_running:
        with test_data.lock:
            test_data.is_running = False
        test_data.test_end_time = time.time()
        controls["start_btn"]["state"] = tk.NORMAL
        controls["stop_btn"]["state"] = tk.DISABLED
        log_print("🎉 压测任务执行完成！", "SUCCESS")
        generate_report()

def export_report():
    """导出报告"""
    if test_data.total_requests == 0:
        messagebox.showwarning("提示", "暂无压测数据，无法导出！")
        return
    file_path = filedialog.asksaveasfilename(
        title="保存压测报告", defaultextension=".txt",
        filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        initialfile=f"链式API压测报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    if not file_path: return
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(detail_text.get(1.0, tk.END))
    messagebox.showinfo("成功", f"📄 报告已导出至：\n{file_path}")

# ===================== 核心UI布局：左右双API分栏+链式开关 =====================
def create_ui():
    global log_text, success_rate_label, qps_label, avg_rt_label, chain_switch
    global success_label, fail_label, total_time_label, min_rt_label, max_rt_label, detail_text

    # 主窗口配置
    root.title("🐍 PyApiPress - 链式API压力测试工具 (终极版)")
    root.geometry("1400x800")
    root.resizable(True, True)
    style = ttk.Style()
    style.configure('TLabel', font=("微软雅黑", 9))
    style.configure('TButton', font=("微软雅黑", 9), padding=3)
    style.configure('TEntry', font=("微软雅黑", 9))
    style.configure('TLabelframe', font=("微软雅黑", 10, "bold"), padding=6)

    # ---------------------- 顶部：功能按钮+链式开关区 ----------------------
    top_frame = ttk.Frame(root)
    top_frame.pack(fill=tk.X, padx=8, pady=4)
    
    # 链式调用开关（核心修复：移除ttk.Checkbutton的font参数）
    chain_frame = ttk.Frame(top_frame)
    chain_frame.pack(side=tk.LEFT, padx=2)
    chain_switch = tk.BooleanVar(value=False)
    # ✅ 修复点1：删除ttk.Checkbutton的font参数，解决unknown option "-font"报错
    chain_check = ttk.Checkbutton(chain_frame, text="🔗 启用链式API调用", variable=chain_switch)
    chain_check.pack(side=tk.LEFT, padx=2)
    # 单独用Label做说明文字，规避ttk控件字体限制
    ttk.Label(chain_frame, text="(API2可通过${变量名}引用API1响应数据)", font=("微软雅黑",8)).pack(side=tk.LEFT, padx=5)

    # 功能按钮组
    btn_frame = ttk.Frame(top_frame)
    btn_frame.pack(side=tk.RIGHT, padx=2)
    save_btn = ttk.Button(btn_frame, text="💾 保存参数", width=10, command=save_config)
    save_btn.pack(side=tk.LEFT, padx=2)
    start_btn = ttk.Button(btn_frame, text="▶ 开始压测", width=10, command=start_chain_test)
    start_btn.pack(side=tk.LEFT, padx=2)
    stop_btn = ttk.Button(btn_frame, text="■ 停止压测", width=10, command=stop_test, state=tk.DISABLED)
    stop_btn.pack(side=tk.LEFT, padx=2)
    clear_btn = ttk.Button(btn_frame, text="🗑 清空日志", width=10, command=clear_log)
    clear_btn.pack(side=tk.LEFT, padx=2)
    copy_btn = ttk.Button(btn_frame, text="📋 复制日志", width=10, command=copy_log)
    copy_btn.pack(side=tk.LEFT, padx=2)
    export_btn = ttk.Button(btn_frame, text="📤 导出报告", width=10, command=export_report)
    export_btn.pack(side=tk.LEFT, padx=2)

    # 存储核心按钮控件
    controls["start_btn"] = start_btn
    controls["stop_btn"] = stop_btn

    # ---------------------- 中间：左右双API配置区（核心布局） ----------------------
    config_main_frame = ttk.LabelFrame(root, text="⚙️ API压测参数配置区")
    config_main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    # 左侧：API1 前置接口配置区
    api1_frame = ttk.LabelFrame(config_main_frame, text="🔹 前置接口 (API-1)")
    api1_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

    # API1 配置项
    ttk.Label(api1_frame, text="目标地址：", font=("微软雅黑",9,"bold")).grid(row=0, column=0, sticky=tk.W, padx=2, pady=3)
    api1_url = ttk.Entry(api1_frame, width=45)
    api1_url.grid(row=0, column=1, padx=2, pady=3)
    api1_url.insert(0, "https://www.baidu.com")

    ttk.Label(api1_frame, text="请求方法：").grid(row=0, column=2, sticky=tk.W, padx=2, pady=3)
    api1_method = ttk.Combobox(api1_frame, values=["GET", "POST", "PUT", "DELETE"], width=8, state="readonly")
    api1_method.grid(row=0, column=3, padx=2, pady=3)
    api1_method.current(0)

    ttk.Label(api1_frame, text="超时(秒)：").grid(row=0, column=4, sticky=tk.W, padx=2, pady=3)
    api1_timeout = ttk.Entry(api1_frame, width=6)
    api1_timeout.grid(row=0, column=5, padx=2, pady=3)
    api1_timeout.insert(0, "5")

    ttk.Label(api1_frame, text="请求头(Headers)：", font=("微软雅黑",9,"bold")).grid(row=1, column=0, sticky=tk.NW, padx=2, pady=3)
    api1_headers = scrolledtext.ScrolledText(api1_frame, width=68, height=5, font=("Consolas",9))
    api1_headers.grid(row=1, column=1, columnspan=5, padx=2, pady=3)
    api1_headers.insert(tk.END, '{"Content-Type": "application/json"}')

    ttk.Label(api1_frame, text="请求体(Data)：", font=("微软雅黑",9,"bold")).grid(row=2, column=0, sticky=tk.NW, padx=2, pady=3)
    api1_data = scrolledtext.ScrolledText(api1_frame, width=68, height=5, font=("Consolas",9))
    api1_data.grid(row=2, column=1, columnspan=5, padx=2, pady=3)
    api1_data.insert(tk.END, "{}")

    # 右侧：API2 链式接口配置区
    api2_frame = ttk.LabelFrame(config_main_frame, text="🔹 压测接口 (API-2)【支持${变量}取值】")
    api2_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=4, pady=4)

    # API2 配置项
    ttk.Label(api2_frame, text="目标地址：", font=("微软雅黑",9,"bold")).grid(row=0, column=0, sticky=tk.W, padx=2, pady=3)
    api2_url = ttk.Entry(api2_frame, width=45)
    api2_url.grid(row=0, column=1, padx=2, pady=3)
    api2_url.insert(0, "https://www.baidu.com")

    ttk.Label(api2_frame, text="请求方法：").grid(row=0, column=2, sticky=tk.W, padx=2, pady=3)
    api2_method = ttk.Combobox(api2_frame, values=["GET", "POST", "PUT", "DELETE"], width=8, state="readonly")
    api2_method.grid(row=0, column=3, padx=2, pady=3)
    api2_method.current(1)

    ttk.Label(api2_frame, text="超时(秒)：").grid(row=0, column=4, sticky=tk.W, padx=2, pady=3)
    api2_timeout = ttk.Entry(api2_frame, width=6)
    api2_timeout.grid(row=0, column=5, padx=2, pady=3)
    api2_timeout.insert(0, "5")

    ttk.Label(api2_frame, text="并发数：", font=("微软雅黑",9,"bold")).grid(row=1, column=0, sticky=tk.W, padx=2, pady=3)
    api2_thread = ttk.Entry(api2_frame, width=8)
    api2_thread.grid(row=1, column=1, padx=2, pady=3)
    api2_thread.insert(0, "8")

    ttk.Label(api2_frame, text="总请求数：", font=("微软雅黑",9,"bold")).grid(row=1, column=2, sticky=tk.W, padx=2, pady=3)
    api2_requests = ttk.Entry(api2_frame, width=10)
    api2_requests.grid(row=1, column=3, padx=2, pady=3)
    api2_requests.insert(0, "200")

    ttk.Label(api2_frame, text="请求头(Headers)：", font=("微软雅黑",9,"bold")).grid(row=2, column=0, sticky=tk.NW, padx=2, pady=3)
    api2_headers = scrolledtext.ScrolledText(api2_frame, width=68, height=5, font=("Consolas",9))
    api2_headers.grid(row=2, column=1, columnspan=5, padx=2, pady=3)
    api2_headers.insert(tk.END, '{"Content-Type": "application/json", "token": "${token}"}')

    ttk.Label(api2_frame, text="请求体(Data)：", font=("微软雅黑",9,"bold")).grid(row=3, column=0, sticky=tk.NW, padx=2, pady=3)
    api2_data = scrolledtext.ScrolledText(api2_frame, width=68, height=5, font=("Consolas",9))
    api2_data.grid(row=3, column=1, columnspan=5, padx=2, pady=3)
    api2_data.insert(tk.END, '{"userId": "${data.id}", "userName": "${data.name}", "role": "${role}"}')

    # 存储所有API配置控件
    controls.update({
        # API1控件
        "api1_url": api1_url, "api1_method": api1_method, "api1_timeout": api1_timeout,
        "api1_headers": api1_headers, "api1_data": api1_data,
        # API2控件
        "api2_url": api2_url, "api2_method": api2_method, "api2_timeout": api2_timeout,
        "api2_thread": api2_thread, "api2_requests": api2_requests,
        "api2_headers": api2_headers, "api2_data": api2_data
    })

    # ---------------------- 下半区：日志区 + 报表区 ----------------------
    bottom_main_frame = ttk.Frame(root)
    bottom_main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    # 日志区
    log_frame = ttk.LabelFrame(bottom_main_frame, text="📝 压测实时日志（支持选中复制）")
    log_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=2, pady=2)
    log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas",9), bg="#fdfdfd", selectbackground="#99ccff")
    log_text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
    log_text.tag_config("INFO", foreground="#000000")
    log_text.tag_config("SUCCESS", foreground="#008800")
    log_text.tag_config("ERROR", foreground="#dd0000")
    log_text.tag_config("WARN", foreground="#cc6600")
    log_text.tag_config("PROGRESS", foreground="#0055cc")

    # 报表区
    report_frame = ttk.LabelFrame(bottom_main_frame, text="📊 压测结果统计报表")
    report_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=2, pady=2)

    # 核心指标
    core_metric = ttk.Frame(report_frame, relief=tk.RAISED, padding=6)
    core_metric.pack(fill=tk.X, pady=3)
    success_rate_label = ttk.Label(core_metric, text="成功率：-- %", font=("微软雅黑",14,"bold"), foreground="#008800")
    success_rate_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
    qps_label = ttk.Label(core_metric, text="QPS：-- req/s", font=("微软雅黑",14,"bold"), foreground="#0055cc")
    qps_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
    avg_rt_label = ttk.Label(core_metric, text="平均响应时间：-- ms", font=("微软雅黑",14,"bold"), foreground="#cc6600")
    avg_rt_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # 基础指标
    base_metric = ttk.Frame(report_frame, padding=6)
    base_metric.pack(fill=tk.X, pady=3)
    success_label = ttk.Label(base_metric, text="✅ 成功数：--", font=("微软雅黑",9,"bold"))
    success_label.pack(side=tk.LEFT, padx=15)
    fail_label = ttk.Label(base_metric, text="❌ 失败数：--", font=("微软雅黑",9,"bold"), foreground="#dd0000")
    fail_label.pack(side=tk.LEFT, padx=15)
    total_time_label = ttk.Label(base_metric, text="⏱ 总耗时：-- s", font=("微软雅黑",9,"bold"))
    total_time_label.pack(side=tk.LEFT, padx=15)
    min_rt_label = ttk.Label(base_metric, text="⚡ 最小RT：-- ms", font=("微软雅黑",9,"bold"))
    min_rt_label.pack(side=tk.LEFT, padx=15)
    max_rt_label = ttk.Label(base_metric, text="⚠️ 最大RT：-- ms", font=("微软雅黑",9,"bold"), foreground="#cc6600")
    max_rt_label.pack(side=tk.LEFT, padx=15)

    # 详细报表
    detail_frame = ttk.Frame(report_frame)
    detail_frame.pack(fill=tk.X, pady=3)
    detail_text = scrolledtext.ScrolledText(detail_frame, wrap=tk.WORD, font=("Consolas",9), height=4)
    detail_text.pack(fill=tk.X, expand=True, padx=1, pady=1)

# ===================== 程序入口 =====================
if __name__ == "__main__":
    create_ui()
    load_config()  # 启动自动加载完整配置
    log_print("欢迎使用 PyApiPress 链式API压测工具！支持双API配置+变量取值+参数持久化", "INFO")
    log_print("📖 变量使用说明：API2中用 ${键名} 或 ${多级键名} 引用API1响应数据，例：${token}、${data.user.id}", "INFO")
    root.mainloop()