"""
米哈游扫码登录
"""
import json
import time
import uuid
import requests
import qrcode
import os
import platform
import subprocess
import random
import hashlib
import base64
import sys
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode

# ==================== 配置常量 ====================
# DS盐值
DEFAULT_SALT = "dDIQHbKOdaPaLuvQKVzUzqdeCaxjtaPV"

# 设备信息
DEVICE_ID = str(uuid.uuid4()).replace("-", "")[:16]

# ==================== DS签名生成器 ====================
class DSGenerator:
    @staticmethod
    def generate_ds(param_type=3, body=None, query=""):
        """
        生成DS签名
        """
        salt = DEFAULT_SALT
        
        # 时间戳（秒）
        t = str(int(time.time()))
        
        # 6位随机字符串
        r = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=6))
        
        # 构建请求体字符串
        b = ""
        if body:
            b = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
        
        # 查询参数排序
        q = ""
        if query:
            params = sorted(query.split('&'))
            q = '&'.join(params)
        
        # 计算签名
        sign_str = f"salt={salt}&t={t}&r={r}&b={b}&q={q}"
        sign = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
        
        # 最终格式
        return f"{t},{r},{sign}"

# ==================== 核心登录类 ====================
class MihoyoQRLogin:
    def __init__(self):
        """
        初始化扫码登录客户端
        """
        self.session = requests.Session()
        
        # 设备信息
        self.device_id = DEVICE_ID
        self.device_fp = self._generate_device_fingerprint()
        
        # 登录状态
        self.ticket = None
        self.qr_url = None
        self.account_id = None
        self.stoken = None
        self.mid = None
        self.cookie_token = None
        self.game_token = None
        
        # 状态标志
        self.qr_expired = False
        self.qr_confirmed = False
        self.login_success = False
        
        # 日志配置
        self.log_dir = os.path.join(os.path.expanduser('~'), 'Desktop', 'mihoyo_login')
        os.makedirs(self.log_dir, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # DS生成器
        self.ds_generator = DSGenerator()
        
        self._log("扫码登录客户端初始化完成", "INFO")
    
    def _generate_device_fingerprint(self):
        """生成设备指纹"""
        timestamp = int(time.time())
        seed_id = ''.join(random.choices("0123456789abcdef", k=16))
        
        device_info = {
            "device_id": self.device_id,
            "seed_id": seed_id,
            "seed_time": timestamp,
            "platform": "2",
            "device_fp": "",
            "app_name": "bbs_cn",
        }
        
        fp_str = json.dumps(device_info, separators=(',', ':'))
        return hashlib.md5(fp_str.encode()).hexdigest()
    
    def _log(self, message, level="INFO"):
        """日志记录"""
        levels = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "DEBUG": "🔍"
        }
        prefix = levels.get(level, "ℹ️")
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {prefix} {message}"
        
        print(log_msg)
        
        # 保存到日志文件
        log_file = os.path.join(self.log_dir, f"{self.session_id}_log.txt")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + "\n")
    
    def create_qrcode(self):
        """
        创建登录二维码
        """
        self._log("开始创建登录二维码...", "INFO")
        
        url = "https://passport-api.mihoyo.com/account/ma-cn-passport/app/createQRLogin"
        
        # 请求体
        body = {}
        
        # 生成DS签名
        ds = self.ds_generator.generate_ds(param_type=3, body=body)
        
        # 构建请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 miHoYoBBS/2.90.1 Capture/2.2.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'x-rpc-device_id': self.device_id,
            'x-rpc-app_id': 'ddxf5dufpuyo',
            'x-rpc-device_fp': self.device_fp,
            'x-rpc-device_name': 'Mihoyo Capture',
            'x-rpc-device_model': 'MI 14',
            'x-rpc-client_type': '3',
            'ds': ds,
        }
        
        try:
            response = self.session.post(
                url,
                json=body,
                headers=headers,
                timeout=15,
                verify=True
            )
            
            self._log(f"二维码创建请求状态: {response.status_code}", "INFO")
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("retcode") == 0:
                    data = result.get("data", {})
                    self.qr_url = data.get("url", "")
                    self.ticket = data.get("ticket", "")
                    
                    if self.qr_url and self.ticket:
                        self._log(f"二维码创建成功! Ticket: {self.ticket[:20]}...", "SUCCESS")
                        return True, "二维码创建成功"
                    else:
                        self._log("响应中缺少URL或ticket", "ERROR")
                        return False, "响应数据不完整"
                else:
                    err_code = result.get("retcode")
                    err_msg = result.get("message", f"API错误: {err_code}")
                    self._log(f"二维码创建失败: {err_msg}", "ERROR")
                    return False, err_msg
            else:
                self._log(f"HTTP错误: {response.status_code}", "ERROR")
                return False, f"HTTP错误: {response.status_code}"
                
        except Exception as e:
            self._log(f"创建二维码异常: {str(e)}", "ERROR")
            return False, f"异常: {str(e)}"
    
    def query_qr_login_status(self):
        """
        查询二维码状态
        """
        if not self.ticket:
            self._log("没有可用的ticket", "ERROR")
            return False, "error", None, "缺少ticket"
        
        if self.qr_expired:
            self._log("二维码已过期，跳过查询", "WARNING")
            return False, "expired", None, "二维码已过期"
        
        if self.qr_confirmed:
            self._log("二维码已确认，跳过查询", "INFO")
            return True, "confirmed", None, "二维码已确认"
        
        self._log(f"查询二维码状态... Ticket: {self.ticket[:20]}...", "INFO")
        
        url = "https://passport-api.mihoyo.com/account/ma-cn-passport/app/queryQRLoginStatus"
        
        # 请求体
        body = {"ticket": self.ticket}
        
        # 生成DS签名
        ds = self.ds_generator.generate_ds(param_type=3, body=body)
        
        # 构建请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 miHoYoBBS/2.90.1 Capture/2.2.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'x-rpc-device_id': self.device_id,
            'x-rpc-app_id': 'ddxf5dufpuyo',
            'x-rpc-device_fp': self.device_fp,
            'x-rpc-device_name': 'Mihoyo Capture',
            'x-rpc-device_model': 'MI 14',
            'x-rpc-client_type': '3',
            'ds': ds,
        }
        
        try:
            response = self.session.post(
                url,
                json=body,
                headers=headers,
                timeout=10,
                verify=True
            )
            
            self._log(f"查询状态 - HTTP {response.status_code}", "INFO")
            
            if response.status_code != 200:
                error_msg = f"HTTP错误: {response.status_code}"
                self._log(error_msg, "ERROR")
                return False, "error", None, error_msg
            
            result = response.json()
            
            # 检查二维码是否失效（-3501表示二维码已失效）
            if result.get("retcode") == -3501:
                error_msg = result.get("message", "二维码已失效")
                self._log(error_msg, "ERROR")
                self.qr_expired = True
                return False, "expired", None, error_msg
            
            # 检查二维码是否过期（-106表示二维码已过期）
            if result.get("retcode") == -106:
                error_msg = result.get("message", "二维码已过期")
                self._log(error_msg, "ERROR")
                self.qr_expired = True
                return False, "expired", None, error_msg
            
            if result.get("retcode") == 0:
                data = result.get("data", {})
                
                # 修复：字段名是"status"而不是"stat"
                status = data.get("status", "")
                
                self._log(f"状态: {status}", "INFO")
                
                if status == "Confirmed":
                    self._log("✅ 登录确认成功！", "SUCCESS")
                    
                    # 标记二维码已确认
                    self.qr_confirmed = True
                    
                    # 提取token信息
                    tokens = data.get("tokens", [])
                    user_info = data.get("user_info", {})
                    
                    # 从tokens数组中获取token
                    if tokens and len(tokens) > 0:
                        token_data = tokens[0]
                        self.stoken = token_data.get("token", "")
                    
                    # 从user_info获取用户信息
                    self.mid = user_info.get("mid", "")
                    self.account_id = user_info.get("aid", "")  # 注意：字段名是"aid"
                    
                    if self.stoken:
                        self._log(f"获取SToken成功: {self.stoken[:30]}...", "SUCCESS")
                        self._log(f"MID: {self.mid}", "SUCCESS")
                        
                        if self.account_id:
                            self._log(f"账户ID: {self.account_id}", "SUCCESS")
                        
                        self.login_success = True
                        return True, "confirmed", data, "登录成功"
                    else:
                        self._log("响应中缺少token", "WARNING")
                        return True, "confirmed", data, "登录成功但未提取到token"
                        
                elif status == "Scanned":
                    msg = "已扫码，请确认"
                    self._log(msg, "INFO")
                    return True, "scanned", None, msg
                elif status == "Init":
                    msg = "等待扫码"
                    self._log(msg, "INFO")
                    return True, "waiting", None, msg
                elif status == "Created":
                    msg = "二维码已创建"
                    self._log(msg, "INFO")
                    return True, "waiting", None, msg
                else:
                    msg = f"状态: {status}"
                    self._log(msg, "INFO")
                    return True, status, None, msg
            else:
                error_msg = result.get("message", f"API错误，retcode: {result.get('retcode')}")
                self._log(error_msg, "ERROR")
                return False, "error", None, error_msg
                
        except Exception as e:
            error_msg = f"查询异常: {str(e)}"
            self._log(error_msg, "ERROR")
            return False, "error", None, error_msg
    
    def get_user_info_by_stoken(self):
        """
        通过SToken获取用户信息
        """
        if not self.stoken:
            self._log("缺少stoken，无法获取用户信息", "WARNING")
            return False, "缺少stoken"
        
        self._log("通过SToken获取用户信息...", "INFO")
        
        url = "https://passport-api.mihoyo.com/account/auth/api/getCookieAccountInfoBySToken"
        
        # 生成DS签名
        query = f"stoken={self.stoken}"
        ds = self.ds_generator.generate_ds(param_type=3, query=query)
        
        # 构建请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 miHoYoBBS/2.90.1 Capture/2.2.0',
            'x-rpc-app_id': 'bll8iq97cem8',
            'x-rpc-app_version': '2.90.1',
            'x-rpc-client_type': '2',
            'x-rpc-game_biz': 'bbs_cn',
            'x-rpc-sdk_version': '2.20.1',
            'DS': ds,
            'Referer': 'https://user.mihoyo.com/',
        }
        
        try:
            response = requests.get(
                url,
                params={"stoken": self.stoken},
                headers=headers,
                timeout=10,
                verify=True
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if result.get("retcode") == 0:
                    data = result.get("data", {})
                    self.account_id = data.get("account_id", self.account_id)
                    self.cookie_token = data.get("cookie_token", self.cookie_token)
                    
                    self._log(f"获取用户信息成功! 账户ID: {self.account_id}", "SUCCESS")
                    return True, data
                else:
                    err_msg = result.get("message", f"获取用户信息失败: {result.get('retcode')}")
                    self._log(err_msg, "ERROR")
                    return False, err_msg
            else:
                self._log(f"HTTP错误: {response.status_code}", "ERROR")
                return False, f"HTTP错误: {response.status_code}"
                
        except Exception as e:
            self._log(f"获取用户信息异常: {str(e)}", "ERROR")
            return False, str(e)
    
    def get_cookie_string(self):
        """获取Cookie字符串"""
        cookies = []
        
        if self.mid:
            cookies.append(f"mid={self.mid}")
        if self.stoken:
            cookies.append(f"stoken={self.stoken}")
        if self.account_id:
            cookies.append(f"account_id={self.account_id}")
            cookies.append(f"ltuid={self.account_id}")
        if self.cookie_token:
            cookies.append(f"cookie_token={self.cookie_token}")
        
        return "; ".join(cookies) if cookies else None
    
    def save_credentials(self):
        """保存凭证到文件"""
        credentials = {
            "timestamp": datetime.now().isoformat(),
            "device_id": self.device_id,
            "device_fp": self.device_fp,
            "ticket": self.ticket,
            "qr_url": self.qr_url,
            "account_id": self.account_id,
            "stoken": self.stoken,
            "mid": self.mid,
            "cookie_token": self.cookie_token,
            "game_token": self.game_token,
            "cookie_string": self.get_cookie_string(),
            "login_success": self.login_success,
        }
        
        # 保存JSON文件
        json_path = os.path.join(self.log_dir, f"{self.session_id}_credentials.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(credentials, f, indent=2, ensure_ascii=False, default=str)
        
        # 保存纯文本Cookie
        if self.get_cookie_string():
            txt_path = os.path.join(self.log_dir, f"{self.session_id}_cookie.txt")
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(self.get_cookie_string())
        
        self._log(f"凭证已保存到: {json_path}", "SUCCESS")
        return json_path
    
    def display_qrcode(self):
        """显示二维码"""
        if not self.qr_url:
            self._log("没有可用的二维码URL", "ERROR")
            return False
        
        try:
            print("\n" + "="*70)
            print("📱 米哈游扫码登录")
            print("="*70)
            
            # 生成二维码
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4
            )
            qr.add_data(self.qr_url)
            qr.make(fit=True)
            
            # 保存二维码图片
            qr_path = os.path.join(self.log_dir, f"{self.session_id}_qrcode.png")
            qr.make_image(fill_color="black", back_color="white").save(qr_path)
            
            print(f"💾 二维码图片: {qr_path}")
            print(f"🔗 二维码链接: {self.qr_url}")
            if self.ticket:
                print(f"🎫 Ticket: {self.ticket}")
            
            # 自动打开二维码图片
            try:
                if platform.system() == "Windows":
                    os.startfile(qr_path)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", qr_path])
                elif platform.system() == "Linux":
                    subprocess.run(["xdg-open", qr_path])
            except:
                self._log("自动打开二维码失败，请手动打开图片", "WARNING")
            
            # 在控制台显示ASCII二维码
            #print("\nASCII二维码预览:")
            #qr.print_ascii(invert=True)
            
            print("\n⏳ 请使用米游社APP扫描二维码")
            print("扫描成功后，程序会自动获取登录凭证")
            print("="*70)
            
            return True
            
        except Exception as e:
            self._log(f"显示二维码失败: {str(e)}", "ERROR")
            print(f"\n🔗 请手动复制链接到浏览器: {self.qr_url}")
            return False

# ==================== 登录流程管理器 ====================
class QRLoginManager:
    """扫码登录流程管理器"""
    
    def __init__(self):
        self.client = MihoyoQRLogin()
        self.max_wait_time = 180  # 最大等待时间（秒）
        self.poll_interval = 3    # 轮询间隔（秒")
    
    def run_login_flow(self):
        """
        运行登录流程
        """
        print("="*70)
        print("米哈游扫码登录 - 修复版")
        print("="*70)
        
        # 步骤1: 创建二维码
        print("\n[1/4] 创建登录二维码...")
        success, message = self.client.create_qrcode()
        if not success:
            print(f"❌ 创建二维码失败: {message}")
            return False, None
        
        # 步骤2: 显示二维码
        print("\n[2/4] 显示二维码...")
        if not self.client.display_qrcode():
            return False, None
        
        # 步骤3: 轮询等待扫码
        print("\n[3/4] 等待扫码确认...")
        print("请使用米游社APP扫描二维码")
        print("扫描并确认登录后，程序会自动继续...")
        
        start_time = time.time()
        poll_count = 0
        
        while time.time() - start_time < self.max_wait_time:
            poll_count += 1
            elapsed = int(time.time() - start_time)
            
            # 检查状态
            success, status, data, msg = self.client.query_qr_login_status()
            
            # 显示状态
            status_display = {
                "waiting": "⏳ 等待扫码",
                "scanned": "📱 已扫码，等待确认",
                "confirmed": "✅ 扫码确认成功",
                "expired": "❌ 二维码已过期",
                "error": "⚠️  检查状态失败"
            }.get(status, f"状态: {status}")
            
            print(f"\r{status_display}... {elapsed}秒 (轮询{poll_count}次)", end="", flush=True)
            
            if status == "confirmed":
                print(f"\n✅ 扫码确认成功!")
                break
            
            elif status == "expired":
                print(f"\n❌ 二维码已过期")
                return False, None
            
            elif status == "error":
                print(f"\n⚠️  检查状态失败: {msg}")
                # 继续尝试
            
            # 等待下一次轮询
            time.sleep(self.poll_interval)
        else:
            print(f"\n❌ 登录超时 ({self.max_wait_time}秒)")
            return False, None
        
        # 保存凭证
        save_path = self.client.save_credentials()
        
        # 显示结果
        print("\n" + "="*70)
        print("✅ 扫码登录完成!")
        print("="*70)
        
        if self.client.account_id:
            print(f"👤 账户ID: {self.client.account_id}")
        
        if self.client.stoken:
            print(f"🔑 SToken: {self.client.stoken[:50]}...")
        
        cookie_str = self.client.get_cookie_string()
        if cookie_str:
            print(f"🍪 Cookie: {cookie_str}")
        
        print(f"💾 凭证保存至: {save_path}")
        print("="*70)
        
        return True, {
            "account_id": self.client.account_id,
            "stoken": self.client.stoken,
            "mid": self.client.mid,
            "cookie_token": self.client.cookie_token,
            "save_path": save_path
        }

# ==================== 主程序 ====================
def main():
    """主函数"""
    print("="*70)
    print("米哈游扫码登录工具")
    print("修复状态字段问题")
    print("="*70)
    
    manager = QRLoginManager()
    
    try:
        success, result = manager.run_login_flow()
        if not success:
            print("\n❌ 登录失败")
        
        print("\n✨ 程序执行完成")
        print(f"📁 日志文件保存在: {manager.client.log_dir}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作")
        # 保存当前状态
        manager.client.save_credentials()
    except Exception as e:
        print(f"\n❌ 程序异常: {str(e)}")
        import traceback
        traceback.print_exc()

# ==================== 直接运行 ====================
if __name__ == "__main__":
    # 检查必要库
    try:
        import qrcode
        import requests
    except ImportError as e:
        print(f"❌ 缺少必要库: {e}")
        print("请运行以下命令安装:")
        print("pip install requests qrcode[pil]")
        sys.exit(1)
    
    # 运行主程序
    main()
