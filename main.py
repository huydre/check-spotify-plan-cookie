from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import os
import time
import random
import shutil

def load_proxies(proxy_file):
    """
    Đọc danh sách proxy từ file
    """
    if not os.path.exists(proxy_file):
        print(f"File proxy {proxy_file} không tồn tại")
        return []

    try:
        with open(proxy_file, 'r') as f:
            proxies = [line.strip() for line in f.readlines() if line.strip()]
        print(f"Đã đọc {len(proxies)} proxy từ file {proxy_file}")
        return proxies
    except Exception as e:
        print(f"Lỗi khi đọc file proxy: {e}")
        return []

def setup_driver_with_proxy(proxy=None):
    """
    Thiết lập trình duyệt với proxy (nếu có)
    """
    options = Options()
    options.add_argument("--start-maximized")
    # options.add_argument("--headless")  # Bỏ comment nếu muốn chạy ẩn

    if proxy:
        print(f"Đang sử dụng proxy: {proxy}")

        # Kiểm tra định dạng proxy
        proxy_parts = proxy.split(':')

        if len(proxy_parts) >= 2:  # Ít nhất có ip:port
            ip, port = proxy_parts[0], proxy_parts[1]

            if len(proxy_parts) >= 4:  # Có username và password
                username, password = proxy_parts[2], proxy_parts[3]
                proxy_auth = f"{username}:{password}@{ip}:{port}"
                options.add_argument(f'--proxy-server=http://{proxy_auth}')
            else:
                options.add_argument(f'--proxy-server=http://{ip}:{port}')

    # Sử dụng webdriver_manager để tự động tải ChromeDriver phù hợp
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    return driver

def import_cookies_from_file(driver, cookie_file):
    """
    Import cookies từ một file cụ thể
    """
    if not os.path.exists(cookie_file):
        print(f"File cookie {cookie_file} không tồn tại")
        return False

    try:
        # Đọc file cookie dạng Netscape
        with open(cookie_file, 'r') as f:
            lines = f.readlines()

        # Bỏ qua dòng header nếu có
        if lines and lines[0].startswith('# Netscape HTTP Cookie File'):
            lines = lines[1:]

        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    # Format Netscape: domain, flag, path, secure, expiration, name, value
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        domain, flag, path, secure, expiry, name, value = parts[:7]

                        cookie = {
                            'domain': domain,
                            'path': path,
                            'name': name,
                            'value': value,
                            'secure': secure.lower() == 'true'
                        }

                        # Thêm expiry nếu có giá trị hợp lệ
                        if expiry and expiry != '0':
                            try:
                                cookie['expiry'] = int(expiry)
                            except:
                                pass

                        driver.add_cookie(cookie)
                except Exception as e:
                    print(f"Lỗi khi xử lý cookie: {e}")
                    continue

        return True
    except Exception as e:
        print(f"Lỗi khi đọc file {cookie_file}: {e}")
        return False

def check_login_status(driver):
    """
    Kiểm tra xem cookie có còn hiệu lực không (đã đăng nhập hay chưa)
    """
    try:
        # Kiểm tra nếu có h1 "Log in to Spotify"
        login_h1_xpath = "//h1[contains(text(), 'Log in to Spotify')]"
        login_h1 = driver.find_elements(By.XPATH, login_h1_xpath)
        if login_h1:
            print("Phát hiện trang đăng nhập với h1 'Log in to Spotify'")
            return False

        # Kiểm tra phần tử chỉ xuất hiện khi đã đăng nhập
        login_check_xpath = "//div[contains(@class, 'account-header') or contains(@class, 'user-info')]"
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, login_check_xpath))
        )
        return True
    except:
        # Kiểm tra nếu có nút đăng nhập hiển thị
        try:
            login_button_xpath = "//button[contains(text(), 'Log in') or contains(text(), 'Đăng nhập')]"
            login_buttons = driver.find_elements(By.XPATH, login_button_xpath)
            if login_buttons:
                print("Phát hiện nút đăng nhập")
                return False
        except:
            pass

        # Lưu screenshot để debug (tùy chọn)
        try:
            driver.save_screenshot("login_check_debug.png")
        except:
            pass

        # Không thể xác định rõ ràng, kiểm tra URL
        current_url = driver.current_url
        if "login" in current_url or "sign-in" in current_url:
            print(f"URL hiện tại chứa 'login' hoặc 'sign-in': {current_url}")
            return False

        # Giả định là đã đăng nhập nếu không phát hiện các dấu hiệu đăng nhập
        return True

def process_account(driver, cookie_file_name, cookie_file_path):
    """
    Xử lý một tài khoản và trả về thông tin plan và expiry cùng với trạng thái cookie
    """
    plan = "Không xác định"
    expired = "Không rõ"  # Giá trị mặc định khi không tìm thấy
    cookie_valid = False  # Trạng thái cookie

    try:
        # Truy cập trang quản lý gói Spotify
        target_url = "https://www.spotify.com/vn-vi/account/manage-your-plan/"
        print(f"Đang truy cập {target_url}")
        driver.get(target_url)
        time.sleep(3)  # Đợi trang load

        # Kiểm tra đăng nhập
        if not check_login_status(driver):
            print(f"Cookie không còn hiệu lực cho file: {cookie_file_name}")
            return cookie_file_name, "Cookie hết hạn", "Cookie hết hạn", False

        # Cookie còn hiệu lực
        cookie_valid = True

        # Đợi trang load và các phần tử xuất hiện (tối đa 20 giây)
        wait = WebDriverWait(driver, 20)

        # Lấy text từ xpath thứ nhất (plan)
        try:
            xpath1 = '//*[@id="your-plan"]/section/div/div[1]/div/div/div[2]/span'
            element1 = wait.until(EC.presence_of_element_located((By.XPATH, xpath1)))
            plan = element1.text
            print(f"Plan: {plan}")
        except Exception as e:
            print(f"Không thể lấy thông tin plan: {e}")

        # Lấy text từ xpath thứ hai (expiry) - có thể không tồn tại
        try:
            xpath2 = '//*[@id="your-plan"]/section/div/div[2]/div/div[2]/div[2]/div/div[1]/b[2]'
            # Sử dụng timeout ngắn hơn để không chờ quá lâu nếu phần tử không tồn tại
            element2 = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xpath2)))
            expired = element2.text
            print(f"Expiry: {expired}")
        except TimeoutException:
            print("Không tìm thấy thông tin expiry (timeout)")
            expired = "Không rõ"
        except NoSuchElementException:
            print("Không tìm thấy thông tin expiry (element not found)")
            expired = "Không rõ"
        except Exception as e:
            print(f"Lỗi khi lấy thông tin expiry: {e}")
            expired = "Không rõ"

        # Thử tìm kiếm với xpath khác nếu không tìm thấy
        if expired == "Không rõ":
            try:
                # Thử một xpath thay thế (nếu có)
                alt_xpath = '//*[@id="your-plan"]/section/div/div[2]/div/div[2]/div/div/div[1]/b[2]'
                element2_alt = driver.find_element(By.XPATH, alt_xpath)
                expired = element2_alt.text
                print(f"Expiry (từ xpath thay thế): {expired}")
            except:
                # Vẫn giữ giá trị "Không rõ" nếu không tìm thấy
                pass

    except Exception as e:
        print(f"Lỗi khi xử lý tài khoản: {e}")
        cookie_valid = False  # Đánh dấu cookie không hợp lệ nếu có lỗi

    return cookie_file_name, plan, expired, cookie_valid

def append_to_result_file(result_file, result_line):
    """
    Ghi thêm một dòng kết quả vào file
    """
    try:
        with open(result_file, 'a', encoding='utf-8') as f:
            f.write(f"{result_line}\n")
        return True
    except Exception as e:
        print(f"Lỗi khi ghi vào file kết quả: {e}")
        return False

def main():
    # File proxy và cookies
    proxy_file = "proxy.txt"
    cookies_dir = "cookies"
    expired_cookies_dir = "expired_cookies"  # Thư mục lưu cookie hết hạn
    result_file = "spotify_accounts.txt"

    # Tạo thư mục lưu cookie hết hạn nếu chưa tồn tại
    if not os.path.exists(expired_cookies_dir):
        os.makedirs(expired_cookies_dir)
        print(f"Đã tạo thư mục {expired_cookies_dir} để lưu cookie hết hạn")

    # Tạo file kết quả mới (xóa nếu đã tồn tại)
    with open(result_file, 'w', encoding='utf-8') as f:
        pass  # Tạo file trống
    print(f"Đã tạo file kết quả {result_file}")

    # Đọc danh sách proxy
    proxies = load_proxies(proxy_file)

    # Lấy danh sách file cookie
    if not os.path.exists(cookies_dir):
        print(f"Thư mục {cookies_dir} không tồn tại")
        return

    cookie_files = [f for f in os.listdir(cookies_dir) if os.path.isfile(os.path.join(cookies_dir, f))]

    if not cookie_files:
        print(f"Không tìm thấy file cookie nào trong thư mục {cookies_dir}")
        return

    print(f"Tìm thấy {len(cookie_files)} file cookie")

    # Thống kê
    valid_cookies = 0
    invalid_cookies = 0

    # Xử lý từng file cookie
    for cookie_file in cookie_files:
        print(f"\n=== Đang xử lý file: {cookie_file} ===")

        # Đường dẫn đầy đủ đến file cookie
        cookie_file_path = os.path.join(cookies_dir, cookie_file)

        # Chọn proxy ngẫu nhiên nếu có
        current_proxy = random.choice(proxies) if proxies else None

        # Khởi tạo trình duyệt với proxy
        driver = setup_driver_with_proxy(current_proxy)

        try:
            # URL ban đầu (trang chủ Spotify)
            initial_url = "https://www.spotify.com"
            print(f"Đang truy cập {initial_url}")
            driver.get(initial_url)
            time.sleep(2)

            # Import cookie
            if import_cookies_from_file(driver, cookie_file_path):
                # Refresh trang để áp dụng cookies
                driver.refresh()
                time.sleep(3)

                # Xử lý tài khoản và lấy thông tin
                file_name, plan, expired, cookie_valid = process_account(driver, cookie_file, cookie_file_path)

                # Xử lý cookie dựa trên tính hiệu lực
                if cookie_valid:
                    valid_cookies += 1
                    print(f"Cookie {cookie_file} còn hiệu lực, giữ lại")
                else:
                    invalid_cookies += 1
                    # Di chuyển cookie hết hạn sang thư mục expired_cookies
                    expired_file_path = os.path.join(expired_cookies_dir, cookie_file)
                    shutil.move(cookie_file_path, expired_file_path)
                    print(f"Cookie {cookie_file} hết hạn, đã di chuyển đến {expired_cookies_dir}")

                # Ghi kết quả vào file ngay lập tức
                result_line = f"{file_name}|{plan}|{expired}"
                append_to_result_file(result_file, result_line)
                print(f"Đã ghi kết quả cho {file_name} vào file")

            else:
                invalid_cookies += 1
                # Di chuyển cookie lỗi sang thư mục expired_cookies
                expired_file_path = os.path.join(expired_cookies_dir, cookie_file)
                shutil.move(cookie_file_path, expired_file_path)
                print(f"Lỗi đọc cookie {cookie_file}, đã di chuyển đến {expired_cookies_dir}")

                # Ghi kết quả lỗi vào file
                result_line = f"{cookie_file}|Lỗi đọc cookie|Lỗi đọc cookie"
                append_to_result_file(result_file, result_line)
                print(f"Đã ghi kết quả lỗi cho {cookie_file} vào file")

        except Exception as e:
            print(f"Lỗi khi xử lý file {cookie_file}: {e}")
            invalid_cookies += 1

            # Di chuyển cookie lỗi sang thư mục expired_cookies
            try:
                expired_file_path = os.path.join(expired_cookies_dir, cookie_file)
                shutil.move(cookie_file_path, expired_file_path)
                print(f"Lỗi xử lý cookie {cookie_file}, đã di chuyển đến {expired_cookies_dir}")
            except Exception as move_error:
                print(f"Không thể di chuyển file cookie: {move_error}")

            # Ghi kết quả lỗi vào file
            result_line = f"{cookie_file}|Lỗi xử lý|Lỗi xử lý"
            append_to_result_file(result_file, result_line)
            print(f"Đã ghi kết quả lỗi cho {cookie_file} vào file")

        finally:
            # Đóng trình duyệt sau khi xử lý xong một file
            driver.quit()
            print(f"Đã đóng trình duyệt sau khi xử lý {cookie_file}")

            # Đợi một chút trước khi xử lý file tiếp theo
            time.sleep(2)

    print(f"\n=== Hoàn thành kiểm tra tất cả cookie ===")
    print(f"Tổng số cookie: {len(cookie_files)}")
    print(f"Cookie còn hiệu lực: {valid_cookies}")
    print(f"Cookie hết hạn/lỗi: {invalid_cookies}")
    print(f"Kết quả đã được lưu vào file {result_file}")

if __name__ == "__main__":
    main()