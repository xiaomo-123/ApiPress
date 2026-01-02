import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import requests
import threading
import time
from datetime import datetime
import json
import re
import os

# ===================== 全局配置 & 数据管理 =====================
# 配置文件路径（本地JSON存储，自动创建）
CONFIG_FILE = "api_press_config.json"
# 全局数据管理类
class TestData:
    """统一管理压测所有统计数据，线程安全"""
    def __init__(self):
        self.success_count = 0
        self.fail_count = 0
        self.response_times = []
        self.status_code_dict = {}
        self.current_request = 0
        self.total_requests = 0
        self.completed_requests = 0  # 新增:已完成的请求数
        self.thread_num = 0
        self.is_running = False
        self.test_start_time = 0
        self.test_end_time = 0
        self.lock = threading.Lock()

# 初始化全局对象
test_data = TestData()
root = tk.Tk()
controls = {}
# 日志/报表控件全局声明
log_text = None
response_text = None  # 新增:右侧响应结果显示窗口
success_rate_label, qps_label, avg_rt_label = None, None, None
success_label, fail_label, total_time_label, min_rt_label, max_rt_label = None, None, None, None, None
detail_text = None

# ===================== 参数保存/加载核心方法 =====================
def save_config():
    """保存当前压测配置到本地JSON文件（独立调用+自动调用）"""
    config_data = {
        "target_url": controls["url_entry"].get().strip(),
        "request_method": controls["method_combo"].get(),
        "thread_num": controls["thread_entry"].get().strip(),
        "total_requests": controls["req_entry"].get().strip(),
        "timeout": controls["timeout_entry"].get().strip(),
        "headers": controls["headers_text"].get(1.0, tk.END).strip(),
        "data": controls["data_text"].get(1.0, tk.END).strip()
    }

    # 获取当前选中的配置
    selected_config = controls["config_list_combo"].get()

    # 确定保存路径
    if selected_config == "默认配置" or not selected_config:
        config_file = CONFIG_FILE
        config_name = "默认配置"
    else:
        config_dir = "configs"
        config_file = os.path.join(config_dir, f"{selected_config}.json")
        config_name = selected_config

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
        messagebox.showinfo("保存成功", f"✅ 压测参数已保存到配置 '{config_name}'！")
        log_print(f"✅ 压测参数已保存到配置 '{config_name}'：{config_file}", "SUCCESS")
    except Exception as e:
        messagebox.showerror("保存失败", f"❌ 参数保存出错：{str(e)}")
        log_print(f"❌ 参数保存失败：{str(e)}", "ERROR")

def load_config():
    """启动时加载本地保存的配置，自动填充到界面"""
    if not os.path.exists(CONFIG_FILE):
        log_print(f"ℹ️ 未检测到历史配置文件，使用默认参数", "INFO")
        return
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        # 自动填充配置到控件
        controls["url_entry"].delete(0, tk.END)
        controls["url_entry"].insert(0, config_data.get("target_url", "https://www.baidu.com"))
        
        method = config_data.get("request_method", "GET")
        controls["method_combo"].set(method)
        
        controls["thread_entry"].delete(0, tk.END)
        controls["thread_entry"].insert(0, config_data.get("thread_num", "8"))
        
        controls["req_entry"].delete(0, tk.END)
        controls["req_entry"].insert(0, config_data.get("total_requests", "200"))
        
        controls["timeout_entry"].delete(0, tk.END)
        controls["timeout_entry"].insert(0, config_data.get("timeout", "5"))
        
        controls["headers_text"].delete(1.0, tk.END)
        controls["headers_text"].insert(tk.END, config_data.get("headers", '{"Content-Type": "application/json"}'))
        
        controls["data_text"].delete(1.0, tk.END)
        controls["data_text"].insert(tk.END, config_data.get("data", '{"username": "test", "password": "123456"}'))
        
        log_print(f"✅ 已加载历史压测配置，参数自动填充完成", "SUCCESS")
    except Exception as e:
        log_print(f"❌ 配置加载失败，使用默认参数：{str(e)}", "ERROR")

# ===================== 配置文件管理方法 =====================
def get_config_list():
    """获取所有配置文件列表"""
    config_dir = "configs"
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    config_files = []
    for file in os.listdir(config_dir):
        if file.endswith('.json'):
            config_files.append(file[:-5])  # 去掉.json后缀

    # 检查默认配置文件
    if os.path.exists(CONFIG_FILE):
        config_files.insert(0, "默认配置")

    return config_files if config_files else ["默认配置"]

def save_config_as(combo):
    """另存为新的配置文件"""
    from tkinter import simpledialog
    config_name = simpledialog.askstring("保存配置", "请输入配置名称：", parent=root)
    if not config_name:
        return

    # 验证配置名称
    if not config_name.strip():
        messagebox.showerror("错误", "配置名称不能为空！")
        return

    config_name = config_name.strip()

    # 创建配置目录
    config_dir = "configs"
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    # 保存配置
    config_file = os.path.join(config_dir, f"{config_name}.json")
    if os.path.exists(config_file):
        if not messagebox.askyesno("确认", f"配置 '{config_name}' 已存在，是否覆盖？"):
            return

    config_data = {
        "target_url": controls["url_entry"].get().strip(),
        "request_method": controls["method_combo"].get(),
        "thread_num": controls["thread_entry"].get().strip(),
        "total_requests": controls["req_entry"].get().strip(),
        "timeout": controls["timeout_entry"].get().strip(),
        "headers": controls["headers_text"].get(1.0, tk.END).strip(),
        "data": controls["data_text"].get(1.0, tk.END).strip()
    }

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)

        # 更新配置列表
        combo['values'] = get_config_list()
        combo.set(config_name)

        messagebox.showinfo("成功", f"✅ 配置 '{config_name}' 已保存！")
        log_print(f"✅ 配置 '{config_name}' 已保存到 {config_file}", "SUCCESS")
    except Exception as e:
        messagebox.showerror("错误", f"❌ 保存配置失败：{str(e)}")
        log_print(f"❌ 保存配置失败：{str(e)}", "ERROR")

def set_default_config(combo):
    """设置选中的配置为默认配置"""
    selected = combo.get()
    if not selected or selected == "默认配置":
        messagebox.showwarning("提示", "请选择一个配置文件！")
        return

    config_dir = "configs"
    config_file = os.path.join(config_dir, f"{selected}.json")

    if not os.path.exists(config_file):
        messagebox.showerror("错误", f"配置文件 '{selected}' 不存在！")
        return

    try:
        # 读取配置
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        # 保存为默认配置
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)

        messagebox.showinfo("成功", f"✅ '{selected}' 已设置为默认配置！")
        log_print(f"✅ 配置 '{selected}' 已设置为默认配置", "SUCCESS")
    except Exception as e:
        messagebox.showerror("错误", f"❌ 设置默认配置失败：{str(e)}")
        log_print(f"❌ 设置默认配置失败：{str(e)}", "ERROR")

def delete_config(combo):
    """删除选中的配置文件"""
    selected = combo.get()
    if not selected or selected == "默认配置":
        messagebox.showwarning("提示", "请选择一个要删除的配置文件！")
        return

    if not messagebox.askyesno("确认", f"确定要删除配置 '{selected}' 吗？"):
        return

    config_dir = "configs"
    config_file = os.path.join(config_dir, f"{selected}.json")

    try:
        if os.path.exists(config_file):
            os.remove(config_file)
            combo['values'] = get_config_list()
            combo.set("默认配置")
            messagebox.showinfo("成功", f"✅ 配置 '{selected}' 已删除！")
            log_print(f"✅ 配置 '{selected}' 已删除", "SUCCESS")
        else:
            messagebox.showerror("错误", f"配置文件 '{selected}' 不存在！")
    except Exception as e:
        messagebox.showerror("错误", f"❌ 删除配置失败：{str(e)}")
        log_print(f"❌ 删除配置失败：{str(e)}", "ERROR")

def load_selected_config(combo):
    """加载选中的配置文件"""
    selected = combo.get()
    if not selected:
        return

    if selected == "默认配置":
        # 加载默认配置
        if not os.path.exists(CONFIG_FILE):
            log_print(f"ℹ️ 默认配置文件不存在", "INFO")
            return
        config_file = CONFIG_FILE
    else:
        # 加载自定义配置
        config_dir = "configs"
        config_file = os.path.join(config_dir, f"{selected}.json")

    if not os.path.exists(config_file):
        log_print(f"❌ 配置文件 '{selected}' 不存在", "ERROR")
        return

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        # 填充配置到控件
        controls["url_entry"].delete(0, tk.END)
        controls["url_entry"].insert(0, config_data.get("target_url", "https://www.baidu.com"))

        method = config_data.get("request_method", "GET")
        controls["method_combo"].set(method)

        controls["thread_entry"].delete(0, tk.END)
        controls["thread_entry"].insert(0, config_data.get("thread_num", "8"))

        controls["req_entry"].delete(0, tk.END)
        controls["req_entry"].insert(0, config_data.get("total_requests", "200"))

        controls["timeout_entry"].delete(0, tk.END)
        controls["timeout_entry"].insert(0, config_data.get("timeout", "5"))

        controls["headers_text"].delete(1.0, tk.END)
        controls["headers_text"].insert(tk.END, config_data.get("headers", '{"Content-Type": "application/json"}'))

        controls["data_text"].delete(1.0, tk.END)
        controls["data_text"].insert(tk.END, config_data.get("data", '{"username": "test", "password": "123456"}'))

        log_print(f"✅ 已加载配置：{selected}", "SUCCESS")
    except Exception as e:
        messagebox.showerror("错误", f"❌ 加载配置失败：{str(e)}")
        log_print(f"❌ 加载配置失败：{str(e)}", "ERROR")

# ===================== 日志复制核心方法 =====================
def copy_log():
    """复制日志区选中内容/全部内容到剪贴板"""
    try:
        # 获取选中内容
        selected_text = log_text.get(tk.SEL_FIRST, tk.SEL_LAST)
        if not selected_text:
            # 无选中则复制全部日志
            selected_text = log_text.get(1.0, tk.END)
        # 写入剪贴板
        root.clipboard_clear()
        root.clipboard_append(selected_text)
        root.update() # 生效剪贴板
        messagebox.showinfo("成功", "📋 日志内容已复制到剪贴板！")
        log_print("✅ 日志内容已复制到剪贴板", "SUCCESS")
    except tk.TclError:
        messagebox.showwarning("提示", "暂无日志内容可复制！")
    except Exception as e:
        messagebox.showerror("错误", f"日志复制失败：{str(e)}")

# ===================== 核心UI布局（含独立保存按钮）=====================
def create_ui():
    """创建上下分区UI + 独立保存参数按钮 + 全功能集成"""
    global log_text, response_text, success_rate_label, qps_label, avg_rt_label
    global success_label, fail_label, total_time_label, min_rt_label, max_rt_label, detail_text

    # 主窗口基础配置
    root.title("🐍 PyApiPress - API压力测试工具 (终极完整版)")
    root.geometry("900x600")
    root.resizable(True, True)
    # 全局样式统一
    style = ttk.Style()
    style.configure('TLabel', font=("微软雅黑", 9))
    style.configure('TButton', font=("微软雅黑", 9), padding=3)
    style.configure('TEntry', font=("微软雅黑", 9))
    style.configure('TLabelframe', font=("微软雅黑", 10, "bold"), padding=5)

    # ---------------------- 上侧主操作区 (核心：新增保存参数按钮) ----------------------
    top_main_frame = ttk.LabelFrame(root, text="🔧 主操作区", padding=8)
    top_main_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    # 压测配置区（紧凑排版）
    config_frame = ttk.LabelFrame(top_main_frame, text="压测参数配置", padding=6)
    config_frame.pack(fill=tk.X, padx=2, pady=2)

    cfg_grid = ttk.Frame(config_frame)
    cfg_grid.pack(fill=tk.X, expand=True, padx=2, pady=1)

    # 第一行：URL + 方法 + 并发 + 请求数 + 超时 一行紧凑排布
    ttk.Label(cfg_grid, text="目标API：", font=("微软雅黑",9,"bold")).grid(row=0, column=0, sticky=tk.W, padx=2, pady=3)
    url_entry = ttk.Entry(cfg_grid, width=40)
    url_entry.grid(row=0, column=1, padx=2, pady=3, sticky=tk.W)
    url_entry.insert(0, "https://www.baidu.com")

    ttk.Label(cfg_grid, text="请求方法：").grid(row=0, column=2, sticky=tk.W, padx=2, pady=3)
    method_combo = ttk.Combobox(cfg_grid, values=["GET", "POST", "PUT", "DELETE"], width=9, state="readonly")
    method_combo.grid(row=0, column=3, padx=2, pady=3)
    method_combo.current(0)

    ttk.Label(cfg_grid, text="并发数：").grid(row=0, column=4, sticky=tk.W, padx=2, pady=3)
    thread_entry = ttk.Entry(cfg_grid, width=6)
    thread_entry.grid(row=0, column=5, padx=2, pady=3)
    thread_entry.insert(0, "8")

    ttk.Label(cfg_grid, text="总请求数：").grid(row=0, column=6, sticky=tk.W, padx=2, pady=3)
    req_entry = ttk.Entry(cfg_grid, width=8)
    req_entry.grid(row=0, column=7, padx=2, pady=3)
    req_entry.insert(0, "200")

    ttk.Label(cfg_grid, text="超时(秒)：").grid(row=0, column=8, sticky=tk.W, padx=2, pady=3)
    timeout_entry = ttk.Entry(cfg_grid, width=6)
    timeout_entry.grid(row=0, column=9, padx=2, pady=3)
    timeout_entry.insert(0, "5")

    # 第二行：请求头 + 请求体
    ttk.Label(cfg_grid, text="请求头：", font=("微软雅黑",9,"bold")).grid(row=1, column=0, sticky=tk.NW, padx=2, pady=3)
    headers_text = scrolledtext.ScrolledText(cfg_grid, width=48, height=2, font=("Consolas", 9))
    headers_text.grid(row=1, column=1, columnspan=6, padx=2, pady=3, sticky=tk.W+tk.E)
    headers_text.insert(tk.END, '{"Content-Type": "application/json"}')

    ttk.Label(cfg_grid, text="请求体：", font=("微软雅黑",9,"bold")).grid(row=2, column=0, sticky=tk.NW, padx=2, pady=3)
    data_text = scrolledtext.ScrolledText(cfg_grid, width=48, height=2, font=("Consolas", 9))
    data_text.grid(row=2, column=1, columnspan=6, padx=2, pady=3, sticky=tk.W+tk.E)
    data_text.insert(tk.END, '{"username": "test", "password": "123456"}')

    # 第三行：配置文件管理
    ttk.Label(cfg_grid, text="配置文件：", font=("微软雅黑",9,"bold")).grid(row=3, column=0, sticky=tk.W, padx=2, pady=3)

    # 配置文件列表
    config_list_combo = ttk.Combobox(cfg_grid, values=get_config_list(), width=30, state="readonly")
    config_list_combo.grid(row=3, column=1, columnspan=4, padx=2, pady=3, sticky=tk.W)
    config_list_combo.current(0)
    config_list_combo.bind("<<ComboboxSelected>>", lambda event: load_selected_config(config_list_combo))

    # 配置文件操作按钮
    config_btn_frame = ttk.Frame(cfg_grid)
    config_btn_frame.grid(row=3, column=5, columnspan=5, padx=2, pady=3, sticky=tk.W)

    save_as_btn = ttk.Button(config_btn_frame, text="另存为", width=8, command=lambda: save_config_as(config_list_combo))
    save_as_btn.pack(side=tk.LEFT, padx=1)

    set_default_btn = ttk.Button(config_btn_frame, text="设为默认", width=8, command=lambda: set_default_config(config_list_combo))
    set_default_btn.pack(side=tk.LEFT, padx=1)

    delete_btn = ttk.Button(config_btn_frame, text="删除", width=8, command=lambda: delete_config(config_list_combo))
    delete_btn.pack(side=tk.LEFT, padx=1)

    # ✅ 功能按钮组【核心新增：💾 保存参数按钮，置顶优先】
    btn_frame = ttk.Frame(cfg_grid)
    btn_frame.grid(row=1, column=7, rowspan=2, columnspan=3, padx=5, pady=2, sticky=tk.N+tk.W)
    
    # 新增：💾 保存参数按钮（置顶，优先级最高）
    save_btn = ttk.Button(btn_frame, text="💾 保存参数", width=11, command=save_config)
    save_btn.pack(fill=tk.X, pady=1)
    
    # 原有按钮排序优化
    start_btn = ttk.Button(btn_frame, text="▶ 开始压测", width=11, command=lambda: start_test(
        url_entry.get(), method_combo.get(), thread_entry.get(), req_entry.get(),
        timeout_entry.get(), headers_text.get(1.0, tk.END), data_text.get(1.0, tk.END)
    ))
    start_btn.pack(fill=tk.X, pady=1)

    stop_btn = ttk.Button(btn_frame, text="■ 停止压测", width=11, command=stop_test, state=tk.DISABLED)
    stop_btn.pack(fill=tk.X, pady=1)

    clear_btn = ttk.Button(btn_frame, text="🗑 清空日志", width=11, command=lambda: clear_log())
    clear_btn.pack(fill=tk.X, pady=1)
    
    copy_btn = ttk.Button(btn_frame, text="📋 复制日志", width=11, command=copy_log)
    copy_btn.pack(fill=tk.X, pady=1)

    export_btn = ttk.Button(btn_frame, text="📤 导出报告", width=11, command=export_report)
    export_btn.pack(fill=tk.X, pady=1)

    # 实时日志区（左右分栏）
    log_container = ttk.Frame(top_main_frame)
    log_container.pack(fill=tk.BOTH, expand=True, padx=2, pady=4)

    # 左侧日志区
    left_frame = ttk.LabelFrame(log_container, text="📝 压测实时日志（支持选中复制）", padding=6)
    left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 2))

    log_text = scrolledtext.ScrolledText(left_frame, wrap=tk.WORD, font=("Consolas", 9), bg="#fdfdfd", selectbackground="#99ccff")
    log_text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
    # 日志颜色标签
    log_text.tag_config("INFO", foreground="#000000")
    log_text.tag_config("SUCCESS", foreground="#008800")
    log_text.tag_config("ERROR", foreground="#dd0000")
    log_text.tag_config("WARN", foreground="#cc6600")
    log_text.tag_config("PROGRESS", foreground="#0055cc")

    # 右侧响应结果区
    right_frame = ttk.LabelFrame(log_container, text="💬 响应结果窗口", padding=6)
    right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(2, 0))

    response_text = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, font=("Consolas", 9), bg="#f0f5ff", selectbackground="#99ccff")
    response_text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
    # 响应结果颜色标签
    response_text.tag_config("REQUEST", foreground="#0055cc")
    response_text.tag_config("RESPONSE", foreground="#008800")
    response_text.tag_config("ERROR", foreground="#dd0000")

    # ---------------------- 下侧统计报表区 ----------------------
    bottom_report_frame = ttk.LabelFrame(root, text="📊 压测结果统计报表", padding=8)
    bottom_report_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    # 核心指标区
    core_metric_frame = ttk.Frame(bottom_report_frame, relief=tk.RAISED, padding=6)
    core_metric_frame.pack(fill=tk.X, pady=4)
    success_rate_label = ttk.Label(core_metric_frame, text="成功率：-- %", font=("微软雅黑", 15, "bold"), foreground="#008800")
    success_rate_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=0, pady=2)
    qps_label = ttk.Label(core_metric_frame, text="QPS：-- req/s", font=("微软雅黑", 15, "bold"), foreground="#0055cc")
    qps_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=0, pady=2)
    avg_rt_label = ttk.Label(core_metric_frame, text="平均响应时间：-- ms", font=("微软雅黑", 15, "bold"), foreground="#cc6600")
    avg_rt_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=0, pady=2)

    # 基础数据区
    base_metric_frame = ttk.LabelFrame(bottom_report_frame, text="基础性能指标", padding=6)
    base_metric_frame.pack(fill=tk.X, padx=2, pady=3)
    ttk.Label(base_metric_frame, text="✅ 成功数：", font=("微软雅黑",9)).grid(row=0, column=0, sticky=tk.W, padx=8, pady=2)
    success_label = ttk.Label(base_metric_frame, text="--", font=("微软雅黑",9,"bold"))
    success_label.grid(row=0, column=1, sticky=tk.W, padx=2, pady=2)
    ttk.Label(base_metric_frame, text="❌ 失败数：", font=("微软雅黑",9)).grid(row=0, column=2, sticky=tk.W, padx=8, pady=2)
    fail_label = ttk.Label(base_metric_frame, text="--", font=("微软雅黑",9,"bold"), foreground="#dd0000")
    fail_label.grid(row=0, column=3, sticky=tk.W, padx=2, pady=2)
    ttk.Label(base_metric_frame, text="⏱ 总耗时：", font=("微软雅黑",9)).grid(row=0, column=4, sticky=tk.W, padx=8, pady=2)
    total_time_label = ttk.Label(base_metric_frame, text="-- s", font=("微软雅黑",9,"bold"))
    total_time_label.grid(row=0, column=5, sticky=tk.W, padx=2, pady=2)
    ttk.Label(base_metric_frame, text="⚡ 最小RT：", font=("微软雅黑",9)).grid(row=0, column=6, sticky=tk.W, padx=8, pady=2)
    min_rt_label = ttk.Label(base_metric_frame, text="-- ms", font=("微软雅黑",9,"bold"))
    min_rt_label.grid(row=0, column=7, sticky=tk.W, padx=2, pady=2)
    ttk.Label(base_metric_frame, text="⚠️ 最大RT：", font=("微软雅黑",9)).grid(row=0, column=8, sticky=tk.W, padx=8, pady=2)
    max_rt_label = ttk.Label(base_metric_frame, text="-- ms", font=("微软雅黑",9,"bold"), foreground="#cc6600")
    max_rt_label.grid(row=0, column=9, sticky=tk.W, padx=2, pady=2)

    # 详情数据区
    detail_frame = ttk.LabelFrame(bottom_report_frame, text="详细数据明细", padding=6)
    detail_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=3)
    detail_text = scrolledtext.ScrolledText(detail_frame, wrap=tk.WORD, font=("Consolas", 9), height=4)
    detail_text.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

    # 保存全局控件引用
    controls.update({
        "start_btn": start_btn, "stop_btn": stop_btn, "save_btn": save_btn,
        "url_entry": url_entry, "method_combo": method_combo, "thread_entry": thread_entry,
        "req_entry": req_entry, "timeout_entry": timeout_entry,
        "headers_text": headers_text, "data_text": data_text,
        "config_list_combo": config_list_combo
    })

# ===================== 核心功能函数 =====================
def log_print(content, level="INFO"):
    """带时间、带颜色的日志打印函数，线程安全"""
    time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_content = f"[{time_str}] [{level}] {content}\n"
    root.after(0, lambda: log_text.insert(tk.END, log_content))
    root.after(0, lambda: log_text.see(tk.END))
    tag = level if level in ["INFO", "SUCCESS", "ERROR", "WARN", "PROGRESS"] else "INFO"
    root.after(0, lambda: log_text.tag_add(tag, log_text.index("end-2l"), log_text.index("end-1l")))

def clear_log():
    """清空实时日志区和响应结果窗口"""
    log_text.delete(1.0, tk.END)
    response_text.delete(1.0, tk.END)
    log_print("日志区已清空，准备新一轮压测", "INFO")

def validate_params(url, thread_num, total_req, timeout):
    """压测参数合法性校验"""
    if not re.match(r'^https?://', url.strip()):
        messagebox.showerror("参数错误", "目标API地址格式错误！必须以 http:// 或 https:// 开头")
        return False
    try:
        thread_num = int(thread_num)
        total_req = int(total_req)
        timeout = int(timeout)
        if thread_num <= 0 or total_req <= 0 or timeout <= 0:
            messagebox.showerror("参数错误", "并发数、总请求数、超时时间 必须为正整数！")
            return False
        # 验证并发数不超过总请求数
        if thread_num > total_req:
            messagebox.showerror("参数错误", f"并发数({thread_num})不应超过总请求数({total_req})！")
            return False
    except ValueError:
        messagebox.showerror("参数错误", "并发数、总请求数、超时时间 必须输入数字！")
        return False
    return True

def parse_json(text):
    """JSON文本解析"""
    try:
        return json.loads(text.strip()) if text.strip() else {}
    except Exception as e:
        log_print(f"JSON格式解析失败：{str(e)}，将使用空字典", "WARN")
        return {}

def send_request(url, method, headers, data_list, timeout):
    """单请求发送逻辑"""
    session = requests.Session()
    data_index = 0
    while True:
        with test_data.lock:
            if not test_data.is_running or test_data.current_request >= test_data.total_requests:
                break
            test_data.current_request += 1
            current = test_data.current_request
            total = test_data.total_requests

        # 从参数列表中获取当前请求的数据
        data = data_list[data_index % len(data_list)] if isinstance(data_list, list) and data_list else data_list
        data_index += 1

        log_print(f"正在压测：{current}/{total} 次请求", "PROGRESS")

        # 在右侧窗口显示请求参数
        request_info = f"\n{'='*60}\n请求 #{current}\n{'='*60}\n"
        request_info += f"URL: {url}\n"
        request_info += f"Method: {method}\n"
        request_info += f"Headers: {json.dumps(headers, ensure_ascii=False, indent=2)}\n"
        request_info += f"Data: {json.dumps(data, ensure_ascii=False, indent=2)}\n"
        root.after(0, lambda: response_text.insert(tk.END, request_info, "REQUEST"))
        root.after(0, lambda: response_text.see(tk.END))

        try:
            start_time = time.time()
            if method.upper() == "GET":
                resp = session.get(url, headers=headers, timeout=timeout)
            elif method.upper() in ["POST", "PUT", "DELETE"]:
                resp = getattr(session, method.lower())(url, headers=headers, json=data, timeout=timeout)
            else:
                raise Exception(f"不支持的请求方法：{method}")
            rt = round((time.time() - start_time) * 1000, 2)

            # 在右侧窗口显示响应结果
            response_info = f"\n响应 #{current}\n"
            response_info += f"状态码: {resp.status_code}\n"
            response_info += f"响应时间: {rt}ms\n"
            try:
                response_data = resp.json()
                response_info += f"响应内容:\n{json.dumps(response_data, ensure_ascii=False, indent=2)}\n"
            except:
                response_info += f"响应内容:\n{resp.text[:1000]}\n"
            root.after(0, lambda: response_text.insert(tk.END, response_info, "RESPONSE"))
            root.after(0, lambda: response_text.see(tk.END))

            # 使用锁保护统计数据更新
            with test_data.lock:
                test_data.response_times.append(rt)
                code = resp.status_code
                test_data.status_code_dict[code] = test_data.status_code_dict.get(code, 0) + 1
                if 200 <= code < 300:
                    test_data.success_count += 1
                else:
                    test_data.fail_count += 1
                test_data.completed_requests += 1  # 新增:记录已完成的请求数

            log_print(f"请求成功 | 状态码：{code} | 响应时间：{rt}ms", "SUCCESS")
        except Exception as e:
            error_info = f"\n错误 #{current}\n"
            error_info += f"错误信息: {str(e)}\n"
            root.after(0, lambda: response_text.insert(tk.END, error_info, "ERROR"))
            root.after(0, lambda: response_text.see(tk.END))

            # 使用锁保护统计数据更新
            with test_data.lock:
                test_data.fail_count += 1
                test_data.status_code_dict["ERROR"] = test_data.status_code_dict.get("ERROR", 0) + 1
                test_data.completed_requests += 1  # 新增:记录已完成的请求数

            log_print(f"请求失败 | 错误原因：{str(e)}", "ERROR")

def start_test(url, method, thread_num, total_req, timeout, headers_str, data_str):
    """启动压测（自动保存参数保留）"""
    if not validate_params(url, thread_num, total_req, timeout):
        return
    
    url = url.strip()
    thread_num = int(thread_num)
    total_req = int(total_req)
    timeout = int(timeout)
    headers = parse_json(headers_str)
    data = parse_json(data_str)

    with test_data.lock:
        test_data.success_count = 0
        test_data.fail_count = 0
        test_data.response_times = []
        test_data.status_code_dict = {}
        test_data.current_request = 0
        test_data.total_requests = total_req
        test_data.completed_requests = 0  # 初始化已完成的请求数
        test_data.thread_num = thread_num
        test_data.is_running = True
        test_data.test_start_time = time.time()

    # 尝试解析data_str,如果data_str是文件路径则从文件加载
    data = parse_json(data_str)
    if isinstance(data, dict) and "file" in data:
        # 如果data包含file字段,从文件加载参数数组
        file_path = data["file"]
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data_list = json.load(f)
            if not isinstance(data_list, list):
                log_print(f"❌ 文件内容必须是JSON数组格式", "ERROR")
                return
            log_print(f"✅ 从文件加载了 {len(data_list)} 组参数", "SUCCESS")
        except Exception as e:
            log_print(f"❌ 加载参数文件失败：{str(e)}", "ERROR")
            return
    else:
        # 使用单个参数或参数数组
        data_list = data if isinstance(data, list) else [data]

    # 清空响应窗口
    response_text.delete(1.0, tk.END)
    response_text.insert(tk.END, "=== 压测开始 ===\n")

    controls["start_btn"]["state"] = tk.DISABLED
    controls["stop_btn"]["state"] = tk.NORMAL
    log_print(f"✅ 压测任务启动 | 目标API：{url} | 方法：{method} | 并发数：{thread_num} | 总请求数：{total_req}", "INFO")
    log_print(f"📋 参数数量：{len(data_list)} 组", "INFO")

    for _ in range(thread_num):
        t = threading.Thread(target=send_request, args=(url, method, headers, data_list, timeout), daemon=True)
        t.start()
    root.after(500, check_test_finish)

def stop_test():
    """强制停止压测"""
    with test_data.lock:
        test_data.is_running = False
    test_data.test_end_time = time.time()
    controls["start_btn"]["state"] = tk.NORMAL
    controls["stop_btn"]["state"] = tk.DISABLED
    log_print("⚠️ 压测任务已被强制停止", "WARN")
    generate_report()

def check_test_finish():
    """轮询检查压测完成状态"""
    if test_data.is_running and test_data.completed_requests < test_data.total_requests:
        root.after(500, check_test_finish)
        return
    if test_data.is_running:
        with test_data.lock:
            test_data.is_running = False
        test_data.test_end_time = time.time()
        controls["start_btn"]["state"] = tk.NORMAL
        controls["stop_btn"]["state"] = tk.DISABLED
        log_print("🎉 压测任务执行完成！正在生成统计报告...", "SUCCESS")
        generate_report()

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

    # 更新统计区UI
    success_rate_label.config(text=f"成功率：{success_rate} %")
    qps_label.config(text=f"QPS：{qps} req/s")
    avg_rt_label.config(text=f"平均响应时间：{avg_rt} ms")
    success_label.config(text=f"{success_cnt}")
    fail_label.config(text=f"{fail_cnt}")
    total_time_label.config(text=f"{total_time} s")
    min_rt_label.config(text=f"{min_rt} ms")
    max_rt_label.config(text=f"{max_rt} ms")

    detail_content = f"""【压测详情汇总】
📌 目标API：{controls['url_entry'].get()} | 请求方法：{controls['method_combo'].get()}
📌 并发数：{test_data.thread_num} | 总请求数：{total_req} | 压测总耗时：{total_time} s
✅ 成功数：{success_cnt} | ❌ 失败数：{fail_cnt} | 📈 成功率：{success_rate}% | ⚡ QPS：{qps} req/s
⏳ 响应时间：平均 {avg_rt}ms | 最小 {min_rt}ms | 最大 {max_rt}ms
📋 状态码分布：{code_dist}
"""
    detail_text.delete(1.0, tk.END)
    detail_text.insert(tk.END, detail_content)
    log_print("📊 压测报告已生成，查看下方统计区", "INFO")

def export_report():
    """导出压测报告"""
    if test_data.total_requests == 0:
        messagebox.showwarning("提示", "暂无压测数据，无法导出报告！")
        return
    file_path = filedialog.asksaveasfilename(
        title="保存压测报告", defaultextension=".txt",
        filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        initialfile=f"API压测报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    if not file_path:
        return
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(detail_text.get(1.0, tk.END))
    messagebox.showinfo("成功", f"压测报告已导出至：\n{file_path}")
    log_print(f"💾 压测报告已导出到本地文件：{file_path}", "SUCCESS")

# ===================== 程序入口 =====================
if __name__ == "__main__":
    create_ui()
    load_config() # 启动自动加载参数
    log_print("欢迎使用 PyApiPress API压力测试工具（终极完整版），支持手动/自动保存参数！", "INFO")
    root.mainloop()