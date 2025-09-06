from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import subprocess
import threading
import time
import psutil
import socket
import asyncio
import uuid
import json

app = FastAPI()

# 实例配置
instances = {
    "5090": {
        "name": "5090",
        "port": 5090,
        "gpu": 1,
        "process": None,
        "status": "stopped",
        "url": "http://localhost:5090",
        "last_broadcast_status": None
    },
    "4090": {
        "name": "4090",
        "port": 4090,
        "gpu": 0,
        "process": None,
        "status": "stopped",
        "url": "http://localhost:4090",
        "last_broadcast_status": None
    }
}

# WebSocket连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                self.disconnect(connection)

manager = ConnectionManager()

# 当前选中的机器
current_machine = "5090"

def is_port_open(host, port):
    """检查端口是否开放"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

async def check_instance_status():
    """定期检查实例状态并广播更新"""
    while True:
        for machine_id, inst in instances.items():
            old_status = inst["status"]
            
            # 如果实例正在启动或运行中，检查端口状态
            if inst["status"] in ["starting", "running"]:
                if is_port_open("localhost", inst["port"]):
                    inst["status"] = "running"
                elif inst["status"] == "starting" and time.time() - inst.get("start_time", 0) > 30:
                    # 如果启动超过30秒但端口仍未开放，标记为启动失败
                    inst["status"] = "stopped"
            
            # 如果状态发生变化，广播给所有客户端
            if old_status != inst["status"]:
                await manager.broadcast({
                    "type": "status_update",
                    "machine": machine_id,
                    "status": inst["status"]
                })
                inst["last_broadcast_status"] = inst["status"]
        
        await asyncio.sleep(2)  # 每2秒检查一次

def monitor_instance(machine_id):
    """监控实例进程状态"""
    inst = instances[machine_id]
    while True:
        if inst["process"] is None:
            inst["status"] = "stopped"
            break
            
        # 检查进程是否还在运行
        if inst["process"].poll() is not None:
            inst["status"] = "stopped"
            inst["process"] = None
            break
            
        time.sleep(2)

def run_instance(machine_id):
    """启动实例"""
    inst = instances[machine_id]
    if inst["status"] == "running" or inst["status"] == "starting":
        return {"status": "error", "message": f"{machine_id} 已经在运行或启动中"}
    
    try:
        PYTHON_EXE = r".\python_embeded\python.exe"
        COMFYUI_MAIN = r".\ComfyUI\main.py"
        CMD = [
            PYTHON_EXE, "-s", COMFYUI_MAIN,
            "--windows-standalone-build",
            "--listen", "localhost",
            "--multi-user",
            "--cuda-device", str(inst["gpu"]),
            "--port", str(inst["port"]),
            "--disable-auto-launch",
            "--disable-xformers"
        ]
        
        inst["process"] = subprocess.Popen(CMD)
        inst["status"] = "starting"
        inst["start_time"] = time.time()
        
        # 启动监控线程
        threading.Thread(target=monitor_instance, args=(machine_id,), daemon=True).start()
        
        return {"status": "success", "message": f"{machine_id} 启动中..."}
    except Exception as e:
        inst["status"] = "error"
        return {"status": "error", "message": f"{machine_id} 启动失败: {str(e)}"}

def stop_instance(machine_id):
    """停止实例"""
    inst = instances[machine_id]
    if inst["process"] is None or inst["status"] == "stopped":
        return {"status": "error", "message": f"{machine_id} 未在运行"}
    
    try:
        # 终止进程及其所有子进程
        parent = psutil.Process(inst["process"].pid)
        for child in parent.children(recursive=True):
            child.terminate()
        parent.terminate()
        
        # 等待进程结束
        parent.wait(timeout=10)
        
        inst["process"] = None
        inst["status"] = "stopped"
        
        return {"status": "success", "message": f"{machine_id} 已停止"}
    except Exception as e:
        return {"status": "error", "message": f"{machine_id} 停止失败: {str(e)}"}

def restart_instance(machine_id):
    """重启实例"""
    stop_result = stop_instance(machine_id)
    if stop_result["status"] == "error":
        return stop_result
    
    time.sleep(2)  # 等待一段时间再启动
    return run_instance(machine_id)

@app.on_event("startup")
async def startup_event():
    """启动时创建状态检查任务"""
    asyncio.create_task(check_instance_status())

@app.websocket("/ws/status")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # 发送当前所有状态给新连接的客户端
        for machine_id, inst in instances.items():
            await websocket.send_json({
                "type": "status_update",
                "machine": machine_id,
                "status": inst["status"]
            })
        
        # 保持连接开放
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    # 生成唯一的缓存破坏参数
    cache_buster = str(uuid.uuid4())[:8]
    
    html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ComfyUI 多端口切换</title>
<style>
    html, body {{
        margin: 0;
        padding: 0;
        height: 100%;
        width: 100%;
        overflow: hidden;
        font-family: Arial, sans-serif;
        background-color: #000;
    }}
    iframe {{
        width: 100%;
        height: 100%;
        border: none;
    }}
    .buttons {{
        position: fixed;
        bottom: 40px;
        right: 20px;
        background: rgba(0, 0, 0, 0.9);
        padding: 10px;
        border-radius: 8px;
        border: 1px solid #333;
        box-shadow: 0 0 10px rgba(0,0,0,0.3);
        z-index: 1000;
        display: flex;
        align-items: center;
        user-select: none;
    }}
    .drag-handle {{
        width: 14px;
        height: 20px;
        display: grid;
        grid-template-columns: 2fr;
        grid-template-rows: repeat(3, 1fr);
        gap: 2px;
        margin-right: 1px;
        cursor: grab;
    }}
    .drag-handle div {{
        width: 4px;
        height: 4px;
        border-radius: 50%;
        background-color: #333;
        justify-self: center;
        align-self: center;
    }}
    .buttons button {{
        margin: 0 4px;
        padding: 10px 10px;
        cursor: pointer;
        border: 1px solid #666;
        border-radius: 4px;
        background-color: #111;
        color: white;
        font-size:13px;
        transition: background-color 0.3s;
    }}
    .buttons button:hover {{
        background-color: #ab8ed7 !important;
    }}
    .buttons button.selected {{
        background-color: #6f40b5;
    }}
    .buttons button:disabled {{
        cursor: not-allowed;
    }}
    .status {{
        margin: 0 2px;
        font-weight: bold;
        color: #333;
        min-width: 20px;
    }}
    .status-indicator {{
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        margin-right: 5px;
    }}
    .status-stopped {{
        background-color: #999;
    }}
    .status-starting {{
        background-color: #fd7e14;
        animation: pulse 1.5s infinite;
    }}
    .status-running {{
        background-color: #28a745;
    }}
    @keyframes pulse {{
        0% {{ opacity: 1; }}
        50% {{ opacity: 0.5; }}
        100% {{ opacity: 1; }}
    }}
    #drag-mask {{
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        z-index: 999;
        display: none;
        background: transparent;
        cursor: grabbing;
    }}
    .status-overlay {{
        position: fixed;
        top: 50%;
        left: 50%;
        color: white;
        padding: 20px;
        border-radius: 8px;
        z-index: 100;
        text-align: center;
        display: none;
        font-size: 20px;
    }}
    .loader {{
        border: 5px solid #f3f3f3;
        border-top: 5px solid #3498db;
        border-radius: 50%;
        width: 50px;
        height: 50px;
        animation: spin 1s linear infinite;
        margin: 0 auto 15px;
    }}
    @keyframes spin {{
        0% {{ transform: rotate(0deg); }}
        100% {{ transform: rotate(360deg); }}
    }}
</style>
</head>
<body>
<!-- 状态覆盖层 -->
<div class="status-overlay" id="status-overlay">
    <div class="loader" id="overlay-loader"></div>
    <div id="overlay-text">程序未启动</div>
</div>

<!-- iframe 容器 -->
<div id="iframe-container" style="width: 100%; height: 100%;">
    <iframe id="iframe-5090" style="display: none;" src="http://localhost:5090?cb={cache_buster}"></iframe>
    <iframe id="iframe-4090" style="display: none;" src="http://localhost:4090?cb={cache_buster}"></iframe>
</div>

<!-- 悬浮按钮 -->
<div class="buttons" id="floating-buttons">
    <div class="drag-handle" id="drag-handle">
        <div></div><div></div>
        <div></div><div></div>
    </div>
    
    <button id="btn-5090" onclick="selectMachine('5090')" class="selected" style="font-size: 15px;font-weight: bold; width:90px;">
        <span id="status-indicator-5090" class="status-indicator status-stopped"></span>&ensp;5090 
    </button>
    <button id="btn-4090" onclick="selectMachine('4090')" style="font-size: 15px;font-weight: bold; width:90px;">
        <span id="status-indicator-4090" class="status-indicator status-stopped"></span>&ensp; 4090
    </button>

    <button id="btn-start" onclick="startInstance()" style="width:50px;">启动</button>
    <button id="btn-stop" onclick="stopInstance()" style="width:50px;">关闭</button>
    <button id="btn-restart" onclick="restartInstance()" style="width:50px;">重启</button>
</div>

<div id="drag-mask"></div>

<script>
let currentMachine = '5090';
let statusCheckInterval;
let machineLoaded = {{
    '5090': false,
    '4090': false
}};

// WebSocket连接
let socket = null;
function connectWebSocket() {{
    if (socket) return;
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = protocol + '//' + window.location.host + '/ws/status';
    
    try {{
        socket = new WebSocket(wsUrl);
        
        socket.onmessage = function(event) {{
            const data = JSON.parse(event.data);
            if (data.type === 'status_update') {{
                updateStatusIndicator(data.machine, data.status);
                if (data.machine === currentMachine) {{
                    updateUI();
                }}
            }}
        }};
        
        socket.onclose = function() {{
            socket = null;
            // 尝试重新连接
            setTimeout(connectWebSocket, 3000);
        }};
    }} catch (error) {{
        console.error('WebSocket连接失败:', error);
    }}
}}

function selectMachine(machine) {{
    currentMachine = machine;
    
    document.getElementById('btn-5090').classList.remove('selected');
    document.getElementById('btn-4090').classList.remove('selected');
    document.getElementById('btn-' + machine).classList.add('selected');
    
    updateUI();
}}

function updateStatusIndicator(machine, status) {{
    const indicator = document.getElementById('status-indicator-' + machine);
    indicator.className = 'status-indicator';
    
    switch(status) {{
        case 'stopped':
            indicator.classList.add('status-stopped');
            break;
        case 'starting':
            indicator.classList.add('status-starting');
            break;
        case 'running':
            indicator.classList.add('status-running');
            break;
    }}
}}

function updateUI() {{
    fetch('/status/' + currentMachine)
        .then(response => response.json())
        .then(data => {{
            const status = data.status;
            const overlay = document.getElementById('status-overlay');
            const overlayText = document.getElementById('overlay-text');
            const overlayLoader = document.getElementById('overlay-loader');
            const iframe5090 = document.getElementById('iframe-5090');
            const iframe4090 = document.getElementById('iframe-4090');
            
            // 隐藏所有iframe
            iframe5090.style.display = 'none';
            iframe4090.style.display = 'none';
            
            switch(status) {{
                case 'stopped':
                    overlay.style.display = 'block';
                    overlayText.textContent = '程序未启动';
                    overlayLoader.style.display = 'none';
                    machineLoaded[currentMachine] = false;
                    break;
                case 'starting':
                    overlay.style.display = 'block';
                    overlayText.textContent = '启动中...';
                    overlayLoader.style.display = 'block';
                    machineLoaded[currentMachine] = false;
                    break;
                case 'running':
                    overlay.style.display = 'none';
                    // 显示当前机器的iframe
                    const iframeId = 'iframe-' + currentMachine;
                    const iframeElement = document.getElementById(iframeId);
                    
                    // 如果iframe尚未加载，强制重新加载
                    if (!machineLoaded[currentMachine]) {{
                        // 添加时间戳参数防止缓存
                        const timestamp = new Date().getTime();
                        const newUrl = iframeElement.src.split('?')[0] + '?cb=' + timestamp;
                        iframeElement.src = newUrl;
                        machineLoaded[currentMachine] = true;
                    }}
                    
                    iframeElement.style.display = 'block';
                    break;
            }}
            
            // 更新按钮状态
            updateButtonStatus(status);
        }});
}}

function updateButtonStatus(status) {{
    const startBtn = document.getElementById('btn-start');
    const stopBtn = document.getElementById('btn-stop');
    const restartBtn = document.getElementById('btn-restart');
    
    switch(status) {{
        case 'stopped':
            startBtn.disabled = false;
            stopBtn.disabled = true;
            restartBtn.disabled = true;
            break;
        case 'starting':
            startBtn.disabled = true;
            stopBtn.disabled = false;
            restartBtn.disabled = true;
            break;
        case 'running':
            startBtn.disabled = true;
            stopBtn.disabled = false;
            restartBtn.disabled = false;
            break;
    }}
}}

async function startInstance() {{
    const overlay = document.getElementById('status-overlay');
    const overlayText = document.getElementById('overlay-text');
    const overlayLoader = document.getElementById('overlay-loader');
    
    overlay.style.display = 'block';
    overlayText.textContent = '启动中...';
    overlayLoader.style.display = 'block';
    
    try {{
        await fetch('/start/' + currentMachine);
        startStatusCheck();
    }} catch (error) {{
        overlayText.textContent = '启动失败: ' + error;
        overlayLoader.style.display = 'none';
    }}
}}

async function stopInstance() {{
    const overlay = document.getElementById('status-overlay');
    const overlayText = document.getElementById('overlay-text');
    const overlayLoader = document.getElementById('overlay-loader');
    
    overlay.style.display = 'block';
    overlayText.textContent = '停止中...';
    overlayLoader.style.display = 'block';
    
    try {{
        await fetch('/stop/' + currentMachine);
        // 重置加载状态
        machineLoaded[currentMachine] = false;
        startStatusCheck();
    }} catch (error) {{
        overlayText.textContent = '停止失败: ' + error;
        overlayLoader.style.display = 'none';
    }}
}}

async function restartInstance() {{
    const overlay = document.getElementById('status-overlay');
    const overlayText = document.getElementById('overlay-text');
    const overlayLoader = document.getElementById('overlay-loader');
    
    overlay.style.display = 'block';
    overlayText.textContent = '重启中...';
    overlayLoader.style.display = 'block';
    
    try {{
        // 重置加载状态
        machineLoaded[currentMachine] = false;
        await fetch('/restart/' + currentMachine);
        startStatusCheck();
    }} catch (error) {{
        overlayText.textContent = '重启失败: ' + error;
        overlayLoader.style.display = 'none';
    }}
}}

function startStatusCheck() {{
    if (statusCheckInterval) {{
        clearInterval(statusCheckInterval);
    }}
    
    statusCheckInterval = setInterval(() => {{
        updateUI();
        
        // 更新所有机器的状态指示器
        fetch('/status/5090')
            .then(response => response.json())
            .then(data => updateStatusIndicator('5090', data.status));
            
        fetch('/status/4090')
            .then(response => response.json())
            .then(data => updateStatusIndicator('4090', data.status));
            
        fetch('/status/' + currentMachine)
            .then(response => response.json())
            .then(data => {{
                if (data.status === 'running') {{
                    clearInterval(statusCheckInterval);
                }}
            }});
    }}, 1000);
}}

// 初始化页面
document.addEventListener('DOMContentLoaded', function() {{
    // 连接WebSocket
    connectWebSocket();
    
    updateUI();
    
    // 初始获取所有机器的状态
    fetch('/status/5090')
        .then(response => response.json())
        .then(data => updateStatusIndicator('5090', data.status));
        
    fetch('/status/4090')
        .then(response => response.json())
        .then(data => updateStatusIndicator('4090', data.status));
        
    // 启动状态检查
    startStatusCheck();
}});

// 拖动逻辑
const dragElement = document.getElementById("floating-buttons");
const handle = document.getElementById("drag-handle");
const dragMask = document.getElementById("drag-mask");
let isDragging = false, offsetX = 0, offsetY = 0;

const savedLeft = localStorage.getItem("floating-left");
const savedTop = localStorage.getItem("floating-top");
if (savedLeft && savedTop) {{
    dragElement.style.left = savedLeft + "px";
    dragElement.style.top = savedTop + "px";
    dragElement.style.bottom = "auto";
    dragElement.style.right = "auto";
}}

handle.addEventListener("mousedown", function(e) {{
    if (e.button !== 0) return;
    isDragging = true;
    const rect = dragElement.getBoundingClientRect();
    offsetX = e.clientX - rect.left;
    offsetY = e.clientY - rect.top;
    dragElement.style.transition = "none";

    dragMask.style.display = "block";

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);

    e.preventDefault();
}});

function onMouseMove(e) {{
    if (!isDragging) return;
    let left = e.clientX - offsetX;
    let top = e.clientY - offsetY;

    const maxLeft = window.innerWidth - dragElement.offsetWidth;
    const maxTop = window.innerHeight - dragElement.offsetHeight;
    left = Math.max(0, Math.min(left, maxLeft));
    top = Math.max(0, Math.min(top, maxTop));

    dragElement.style.left = left + "px";
    dragElement.style.top = top + "px";
    dragElement.style.bottom = "auto";
    dragElement.style.right = "auto";
}}

function onMouseUp() {{
    if (!isDragging) return;
    isDragging = false;
    dragMask.style.display = "none";
    dragElement.style.transition = "all 0.1s";

    localStorage.setItem("floating-left", parseInt(dragElement.style.left));
    localStorage.setItem("floating-top", parseInt(dragElement.style.top));

    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
}}
</script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

# API 路由
@app.get("/start/{machine_id}")
async def start_machine(machine_id: str):
    result = run_instance(machine_id)
    # 广播状态更新
    await manager.broadcast({
        "type": "status_update",
        "machine": machine_id,
        "status": instances[machine_id]["status"]
    })
    return result

@app.get("/stop/{machine_id}")
async def stop_machine(machine_id: str):
    result = stop_instance(machine_id)
    # 广播状态更新
    await manager.broadcast({
        "type": "status_update",
        "machine": machine_id,
        "status": instances[machine_id]["status"]
    })
    return result

@app.get("/restart/{machine_id}")
async def restart_machine(machine_id: str):
    result = restart_instance(machine_id)
    # 广播状态更新
    await manager.broadcast({
        "type": "status_update",
        "machine": machine_id,
        "status": instances[machine_id]["status"]
    })
    return result

@app.get("/status/{machine_id}")
async def get_status(machine_id: str):
    if machine_id in instances:
        return {"status": instances[machine_id]["status"]}
    return {"status": "unknown"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("comfy_web:app", host="0.0.0.0", port=8000, reload=True, access_log=False)