import threading
from server import GBNServer
from client import GBNClient

# 定义一个函数用于启动服务器
def run_server():
    server = GBNServer(host='localhost', port=12345)
    server.start()

# 定义一个函数用于启动客户端
def run_client():
    client = GBNClient(server_host='localhost', server_port=12345)
    client.start()

if __name__ == "__main__":
    # 创建服务端线程
    server_thread = threading.Thread(target=run_server)
    server_thread.start()

    # 确保服务器先启动
    threading.Event().wait(1)  # 延迟1秒，以确保服务器已启动

    # 创建客户端线程
    client_thread = threading.Thread(target=run_client)
    client_thread.start()

    # 等待两个线程结束
    server_thread.join()
    client_thread.join()