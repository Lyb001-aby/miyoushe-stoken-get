'''
通过获取的stoken_v2进行一次模拟扫码，获取ltoken_v2,cookie_token_v2等其他重要cookie
由于作者实力有限，且没有任何参考文档，这个做的很粗糙，而且这个脚本每次运行都会随机指纹创建一个虚拟小米手机（会体现在米哈游账号与安全下的登录设备），希望有大佬能改进
'''
import hashlib
import random
import string
import time
import json
import uuid
import requests
import qrcode
import os
import platform
import subprocess
import threading

class MihoyoAndroidLogin:
    """
    米哈游安卓端扫码登录器 (v2.90.1版本)
    通过stoken获取ltoken_v2和cookie_token
    参考安卓端实现，修正API路径和状态字段
    """
    
    def __init__(self, stoken, mid):
        """
        初始化登录器
        :param stoken: 你的stoken
        :param mid: 你的mid
        """
        self.stoken = stoken
        self.mid = mid
        self.session = requests.Session()
        
        # 设备信息（模拟安卓设备）
        self.device_id = str(uuid.uuid4()).upper()
        self.device_fp = self._generate_device_fp()
        
        # v2.90.1版本salt
        self.salt = "dDIQHbKOdaPaLuvQKVzUzqdeCaxjtaPV"
        
        # 登录状态
        self.ticket = None
        self.qr_url = None
        
        # 设置基础请求头（安卓端）
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 miHoYoBBS/2.90.1',
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'x-rpc-client_type': '2',  # 安卓端
            'x-rpc-app_version': '2.90.1',
            'x-rpc-sys_version': '12',  # Android 12
            'x-rpc-device_model': 'MI 14',
            'x-rpc-device_name': 'Xiaomi',
            'x-rpc-game_biz': 'bbs_cn',
            'x-rpc-app_id': 'bll8iq97cem8',
            'x-rpc-sdk_version': '2.90.1',
            'x-rpc-account_version': '2.90.1',
        })
    
    def _generate_device_fp(self):
        """生成设备指纹"""
        timestamp = int(time.time())
        device_info = {
            "device_id": self.device_id,
            "platform": "2",
            "timestamp": timestamp,
        }
        fp_str = json.dumps(device_info, separators=(',', ':'))
        return hashlib.md5(fp_str.encode()).hexdigest()
    
    def generate_ds(self, body=None, query=None):
        """
        v2.90.1版本的DS签名算法
        格式: timestamp,random_str,signature
        """
        # 生成时间戳和随机字符串
        timestamp = str(int(time.time()))
        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        
        # 构建请求体字符串
        b = ""
        if body:
            b = json.dumps(body, separators=(',', ':'), ensure_ascii=False)
        
        # 查询参数排序
        q = ""
        if query:
            params = sorted(query.split('&'))
            q = '&'.join(params)
        
        # 构建签名字符串
        sign_str = f"salt={self.salt}&t={timestamp}&r={random_str}&b={b}&q={q}"
        signature = hashlib.md5(sign_str.encode('utf-8')).hexdigest()
        
        # 最终格式
        return f"{timestamp},{random_str},{signature}"
    
    def generate_app_headers(self, body=None):
        """生成APP端的请求头（用于模拟手机APP确认登录）"""
        headers = {
            'User-Agent': 'Mozilla/5.0 miHoYoBBS/2.90.1 Capture/2.2.0',
            'Cookie': f'stoken={self.stoken}; mid={self.mid}',
            'Content-Type': 'application/json',
            'x-rpc-client_type': '2',
            'x-rpc-app_version': '2.90.1',
            'x-rpc-device_id': self.device_id,
            'x-rpc-device_fp': self.device_fp,
            'x-rpc-game_biz': 'bbs_cn',
            'x-rpc-app_id': 'bll8iq97cem8',
            'x-rpc-sdk_version': '2.90.1',
            'x-rpc-account_version': '2.90.1',
            'x-rpc-device_model': 'Mi 14',
            'x-rpc-device_name': 'Mihoyo Capture',
            'Accept': '*/*',
            'Accept-Language': 'zh-cn',
        }
        
        # 生成DS签名
        if body:
            ds = self.generate_ds(body=body)
            headers['DS'] = ds
        
        return headers
    
    def generate_web_headers(self, body=None, query=None):
        """生成Web端的请求头"""
        headers = self.session.headers.copy()
        
        # 生成DS签名
        ds = self.generate_ds(body=body, query=query)
        headers['DS'] = ds
        
        # 添加设备相关头部
        headers.update({
            'x-rpc-device_id': self.device_id,
            'x-rpc-device_fp': self.device_fp,
        })
        
        return headers
    
    def create_qrcode(self):
        """
        创建登录二维码（安卓端API）
        """
        url = "https://passport-api.mihoyo.com/account/ma-cn-passport/web/createQRLogin"
        
        body = {}
        
        headers = self.generate_web_headers(body=body)
        
        try:
            print("创建登录二维码...")
            response = self.session.post(url, headers=headers, json=body, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                print(f"创建二维码响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
                
                if result.get("retcode") == 0:
                    data = result.get("data", {})
                    self.qr_url = data.get("url", "")
                    self.ticket = data.get("ticket", "")
                    
                    if self.qr_url and self.ticket:
                        print(f"✅ 获取到Ticket: {self.ticket}")
                        return True, self.qr_url
                    else:
                        print("❌ 响应中缺少URL或ticket")
                        return False, "响应数据不完整"
                else:
                    err_msg = result.get("message", f"API错误: {result.get('retcode')}")
                    print(f"❌ 创建二维码失败: {err_msg}")
                    return False, err_msg
            else:
                print(f"❌ HTTP错误: {response.status_code}")
                return False, f"HTTP错误: {response.status_code}"
                
        except Exception as e:
            print(f"❌ 创建二维码异常: {str(e)}")
            return False, f"异常: {str(e)}"
    
    def display_qrcode(self, qr_url):
        """显示二维码"""
        if not qr_url:
            print("❌ 没有可用的二维码URL")
            return False
        
        try:
            print("\n" + "="*60)
            print("📱 米哈游扫码登录")
            print("="*60)
            
            # 生成二维码
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4
            )
            qr.add_data(qr_url)
            qr.make(fit=True)
            
            # 保存二维码图片
            qr_dir = os.path.join(os.getcwd(), "qrcodes")
            os.makedirs(qr_dir, exist_ok=True)
            qr_path = os.path.join(qr_dir, f"mihoyo_qr_{int(time.time())}.png")
            qr.make_image(fill_color="black", back_color="white").save(qr_path)
            
            print(f"💾 二维码图片: {qr_path}")
            print(f"🔗 二维码链接: {qr_url}")
            
            # 自动打开二维码图片
            try:
                if platform.system() == "Windows":
                    os.startfile(qr_path)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", qr_path])
                elif platform.system() == "Linux":
                    subprocess.run(["xdg-open", qr_path])
            except:
                print("⚠️ 自动打开二维码失败，请手动打开图片")
            
            print("\n⏳ 请使用米游社APP扫描二维码")
            print("="*60)
            
            return True
            
        except Exception as e:
            print(f"❌ 显示二维码失败: {str(e)}")
            print(f"🔗 请手动复制链接到浏览器: {qr_url}")
            return False
    
    def scan_qrcode(self, ticket):
        """模拟手机APP扫描二维码（第一步）"""
        url = "https://passport-api.mihoyo.com/account/ma-cn-passport/app/scanQRLogin"
        
        body = {
            'ticket': ticket,
            'token_types': ['4']
        }
        
        headers = self.generate_app_headers(body)
        
        try:
            print(f"模拟扫描二维码...")
            response = requests.post(url, headers=headers, json=body, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                print(f"扫描响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
                return result.get('retcode') == 0
            else:
                print(f"❌ 扫描请求失败: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ 扫描二维码异常: {str(e)}")
            return False
    
    def confirm_qr_login(self, ticket):
        """使用stoken确认二维码登录（第二步）"""
        url = "https://passport-api.mihoyo.com/account/ma-cn-passport/app/confirmQRLogin"
        
        body = {
            'ticket': ticket,
            'token_types': ['4']
        }
        
        headers = self.generate_app_headers(body)
        time.sleep(1)
        try:
            print(f"确认二维码登录...")
            response = requests.post(url, headers=headers, json=body, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                print(f"确认登录响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
                return result.get('retcode') == 0
            else:
                print(f"❌ 确认请求失败: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ 确认登录异常: {str(e)}")
            return False
    
    def web_query_qr_status(self, ticket):
        """网页端查询二维码状态（关键方法，会返回cookie）"""
        url = "https://passport-api.mihoyo.com/account/ma-cn-passport/web/queryQRLoginStatus"
        
        body = {"ticket": ticket}
        
        # 使用网页端的headers
        headers = self.generate_web_headers(body=body)
        
        try:
            response = self.session.post(url, headers=headers, json=body, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                print(f"网页端状态查询响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
                
                # 检查响应头中的Set-Cookie
                if 'Set-Cookie' in response.headers:
                    print(f"Set-Cookie头: {response.headers['Set-Cookie']}")
                
                if result.get("retcode") == 0:
                    data = result.get("data", {})
                    status = data.get("status", "")
                    
                    # 检查当前session的cookie
                    current_cookies = self.session.cookies.get_dict()
                    print(f"当前session cookie: {current_cookies}")
                    
                    return True, status, data
                else:
                    error_msg = result.get("message", f"API错误: {result.get('retcode')}")
                    print(f"❌ 状态查询失败: {error_msg}")
                    return False, "error", None
            else:
                print(f"❌ 状态查询HTTP错误: {response.status_code}")
                return False, "error", None
                
        except Exception as e:
            print(f"❌ 状态查询异常: {str(e)}")
            return False, "error", None

    def web_polling_loop(self, ticket, timeout=120, interval=3):
        """
        网页端轮询循环（3秒一次）
        返回: (success, cookies, status)
        """
        print(f"开始网页端轮询，超时: {timeout}秒，间隔: {interval}秒")
        
        start_time = time.time()
        poll_count = 0
        
        while time.time() - start_time < timeout:
            poll_count += 1
            elapsed = int(time.time() - start_time)
            
            print(f"\n轮询 #{poll_count} ({elapsed}/{timeout}秒)...")
            
            # 执行一次轮询
            success, status, data = self.web_query_qr_status(ticket)
            
            if success:
                if status in ["confirmed", "Confirmed"]:
                    print("✅ 网页端确认成功！")
                    
                    # 获取当前cookie
                    cookies = self.session.cookies.get_dict()
                    print(f"获取到的cookie: {cookies}")
                    
                    return True, cookies, status
                    
                elif status in ["scanned", "Scanned"]:
                    print("📱 二维码已被扫描")
                    # 这里可以触发APP端确认，但我们让主流程控制
                    
                elif status in ["expired", "Expired"]:
                    print("❌ 二维码已过期")
                    return False, None, "expired"
                    
                elif status in ["init", "Init", "created", "Created"]:
                    print("⏳ 等待扫码...")
                    
                else:
                    print(f"状态: {status}")
            else:
                print("⚠️ 轮询失败")
            
            # 等待间隔
            time.sleep(interval)
        
        print("❌ 轮询超时")
        return False, None, "timeout"
    
    def login(self, timeout=180):
        """完整的登录流程"""
        print("=" * 50)
        print("米哈游安卓端扫码登录 (v2.90.1)")
        print(f"设备ID: {self.device_id}")
        print(f"设备指纹: {self.device_fp}")
        print("=" * 50)
        
        # 1. 创建二维码
        print("\n[1/5] 创建登录二维码...")
        success, qr_url = self.create_qrcode()
        if not success:
            print("❌ 创建二维码失败，退出流程")
            return None
        
        # 2. 显示二维码
        print("\n[2/5] 二维码创建成功")
        #self.display_qrcode(qr_url)#本来是显示二维码的，但是这个脚本自动扫码，所以注释
        
        # 3. 创建线程通信标志
        login_confirmed = threading.Event()
        threads_result = {
            'polling_success': False,
            'polling_cookies': None,
            'polling_status': None,
            'scan_success': False,
            'confirm_success': False
        }
        
        # 4. 双线程同时执行轮询和扫码
        print("\n[3-4/5] 启动双线程执行轮询和自动扫码...")
        
        def polling_task():
            """执行轮询任务"""
            try:
                success, cookies, status = self.web_polling_loop(self.ticket, timeout=timeout-10, interval=2)
                threads_result['polling_success'] = success
                threads_result['polling_cookies'] = cookies
                threads_result['polling_status'] = status
                if success and status in ["confirmed", "Confirmed"]:
                    login_confirmed.set()
            except Exception as e:
                print(f"轮询任务异常: {e}")
        
        def scan_task():
            """执行扫码确认任务"""
            try:
                # 稍微延迟一下开始扫码，给用户时间看到二维码
                time.sleep(3)
                
                # 执行扫码
                if self.scan_qrcode(self.ticket):
                    threads_result['scan_success'] = True
                    print("✅ 模拟扫码成功")
                    
                    # 执行确认登录
                    if self.confirm_qr_login(self.ticket):
                        threads_result['confirm_success'] = True
                        print("✅ 确认登录成功")
                    else:
                        print("⚠️ 扫码成功但确认登录失败")
                else:
                    print("⚠️ 模拟扫码失败")
            except Exception as e:
                print(f"扫码任务异常: {e}")
        
        # 启动两个线程
        poll_thread = threading.Thread(target=polling_task)
        scan_thread = threading.Thread(target=scan_task)
        
        poll_thread.start()
        scan_thread.start()
        
        # 等待线程完成
        poll_thread.join(timeout=timeout-20)
        scan_thread.join(timeout=timeout-20)
        
        # 5. 检查结果并返回cookie
        print(f"\n[5/5] 线程执行完成，检查结果...")
        
        final_cookies = {}
        
        # 如果轮询已经确认登录，直接使用轮询结果
        if threads_result['polling_success'] and threads_result['polling_status'] in ["confirmed", "Confirmed"]:
            print("✅ 轮询已确认登录成功")
            if threads_result['polling_cookies']:
                final_cookies = threads_result['polling_cookies']
        
        # 如果没有通过轮询确认，但扫码确认成功，尝试手动获取一次状态
        elif threads_result['confirm_success']:
            print("✅ 扫码确认成功，尝试获取最终状态...")
            success, status, data = self.web_query_qr_status(self.ticket)
            if success and status in ["confirmed", "Confirmed"]:
                final_cookies = self.session.cookies.get_dict()
        
        # 保存到文件
        if final_cookies:
            self.save_cookies(final_cookies)
        
        return final_cookies
        
    def save_cookies(self, cookies):
        """保存Cookie到文件"""
        try:
            # 保存JSON文件
            json_path = os.path.join(os.getcwd(), "mihoyo_cookies.json")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(cookies, f, indent=2, ensure_ascii=False)
            print(f"✅ Cookie已保存到: {json_path}")
            
            # 保存Cookie字符串
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            txt_path = os.path.join(os.getcwd(), "mihoyo_cookie.txt")
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(cookie_str)
            print(f"✅ Cookie字符串已保存到: {txt_path}")
            
        except Exception as e:
            print(f"❌ 保存Cookie失败: {e}")

# 使用示例
if __name__ == "__main__":
    # 替换为你的实际stoken
    STOKEN = "v2_xxxxxxxxxxxxxxxxx.CAE="
    MID = "xxxxxxxxx_mhy"
    
    print("米哈游安卓端扫码登录工具")
    print("=" * 40)
    
    # 创建登录器
    try:
        login = MihoyoAndroidLogin(STOKEN, MID)
        
        # 尝试登录
        cookies = login.login(timeout=120)
        
        if cookies:
            print("\n" + "="*50)
            print("✅ 登录成功！获取到的完整Cookie:")
            print("="*50)
            
            # 按重要性排序显示
            important_keys = ['ltoken_v2', 'cookie_token', 'account_id', 'ltuid', 'mid', 'stoken', 
                             'cookie_token_v2', 'ltuid_v2', 'account_id_v2']
            for key in important_keys:
                if key in cookies:
                    value = cookies[key]
                    if len(str(value)) > 50:
                        print(f"{key}: {value[:50]}...")
                    else:
                        print(f"{key}: {value}")
            
            print("\n完整的Cookie字典:")
            print(json.dumps(cookies, indent=2, ensure_ascii=False))
            
            # 显示Cookie字符串
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            print(f"\nCookie字符串（用于复制）:")
            print(cookie_str)
            
        else:
            print("\n❌ 登录失败，请检查:")
            print("1. stoken和mid是否正确")
            print("2. 网络连接是否正常")
            print("3. 二维码是否已扫码确认")
            
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断操作")
    except Exception as e:
        print(f"\n❌ 程序异常: {str(e)}")
        import traceback
        traceback.print_exc()
