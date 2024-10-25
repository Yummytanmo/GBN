from datetime import datetime
import random
import socket
import threading
import logging
import time
import magic

# Set up server logger
server_logger = logging.getLogger('SERVER')
server_logger.setLevel(logging.INFO)

# Configure logging format with a custom header "SERVER"
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - SERVER - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
server_logger.addHandler(handler)


def get_extension(data):
     # 自动识别文件类型
    mime = magic.Magic(mime=True)
    file_type = mime.from_buffer(data[:2048])  # 检测文件前2048字节
    server_logger.info(f"Detected file type: {file_type}")

    # 根据文件MIME类型添加后缀
    extension = ""
    if "text/plain" in file_type:
        extension = ".txt"
    elif "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in file_type:
        extension = ".docx"
    elif "application/pdf" in file_type:
        extension = ".pdf"
    elif "image/jpeg" in file_type:
        extension = ".jpg"
    elif "image/png" in file_type:
        extension = ".png"
    else:
        extension = ".bin"  # 如果无法识别，使用`.bin`

    return extension

def get_filename(data):
    current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    extension = get_extension(data)
    filename = f"received_file_{current_time}{extension}"
    return filename

class GBNServer:
    def __init__(self, host='localhost', port=12345, window_size=10, timeout=2, packet_loss=0.2, ack_loss=0.2):
        self.server_address = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.server_address)
        self.window_size = window_size  # Sliding window size
        self.timeout = timeout  # Timeout for retransmission
        self.base = 0  # Base of the window
        self.next_seq_num = 0  # Next sequence number to be sent
        self.data_buffer = []  # Buffer for storing data to be sent
        self.lock = threading.Lock()  # Lock for thread safety
        self.acknowledged = threading.Event()  # Event to signal acknowledgement received
        self.timer = None
        self.packet_loss = packet_loss  # Loss rate for data packets
        self.ack_loss = ack_loss  # Loss rate for ACKs
        self.response = []

    def send_packet(self, seq_num, data, client_address):
        """Construct and send a data packet."""
        packet = bytearray()
        packet.append(seq_num)  # 1 byte for sequence number
        packet.extend(data)  # Append the actual data
        packet.append(0x00)  # EOF indicator (end of frame)
        server_logger.info(f"Sending packet with Seq Num: {seq_num}")
        self.sock.sendto(packet, client_address)

    def handle_gbn(self, client_address):
        """Main GBN protocol handler to send data."""
        while self.base < len(self.data_buffer):
            with self.lock:
                # Send all the packets in the window
                while self.next_seq_num < self.base + self.window_size and self.next_seq_num < len(self.data_buffer):
                    self.send_packet(self.next_seq_num, self.data_buffer[self.next_seq_num], client_address)
                    self.next_seq_num += 1

                # Start timer if it's not running
                if not self.timer:
                    self.timer = threading.Timer(self.timeout, self.timeout_handler, [client_address])
                    self.timer.start()

            # Wait for ACKs
            self.acknowledged.wait()

            # Handle ACK and slide window if received
            self.acknowledged.clear()

    def timeout_handler(self, client_address):
        """Handle packet retransmission on timeout."""
        with self.lock:
            server_logger.info(f"Timeout! Resending packets from Seq Num: {self.base}")
            self.timer = None  # Reset the timer
            self.next_seq_num = self.base  # Retransmit from base
            self.acknowledged.set()

    def receive_ack(self):
        """Receive ACK from client."""
        while True:
            ack_packet, client_address = self.sock.recvfrom(2048)
            ack_num = ack_packet[0]  # First byte is the ACK number
            if ack_num == 0xFF:  # Special FIN packet received
                server_logger.info(f"Received ACK for Seq Num: {-1}")
                continue
            server_logger.info(f"Received ACK for Seq Num: {ack_num}")

            with self.lock:
                if self.base <= ack_num < self.base + self.window_size:
                    self.base = ack_num + 1  # Slide the window

                    # # Stop the timer if all packets are acknowledged
                    # if self.base == self.next_seq_num:
                    if self.timer:
                        self.timer.cancel()
                        self.timer = None
                    self.acknowledged.set()

            if self.base == len(self.data_buffer):  # All packets sent and acknowledged
                break
    
    def get_data(self, file_path):
        with open(file_path, 'rb') as file:
            file_data = file.read()
        # 分片，最大数据部分为1024字节
        packets = []
        seq_number = 0
        for i in range(0, len(file_data), 1024):
            data_chunk = file_data[i:i + 1024]
            packet = data_chunk
            packets.append(packet)
            seq_number = (seq_number + 1) % 256  # Seq最大值255，循环
        return packets

    def receive_gbn(self):
        """Receive data using Go-Back-N protocol, simulate packet and ACK loss."""
        expected_seq_num = 0  # The next expected sequence number
        while True:
            # Receive packet
            try:
                data, server = self.sock.recvfrom(2048)
            except socket.timeout:
                server_logger.info("Timeout ending transmission.")
                break
            
            if random.random() < self.packet_loss:
                server_logger.info(f"Packet with Seq Num {data[0]} lost!")
                continue  # Simulate packet loss by not processing the packet

            # Extract the sequence number
            seq_num = data[0]
            if seq_num == expected_seq_num:
                # Correct sequence number
                server_logger.info(f"Received packet with Seq Num: {seq_num}")
                self.response.append(data[1:-1])
                expected_seq_num += 1
            else:
                server_logger.info(f"Out-of-order packet with Seq Num: {seq_num}, expected {expected_seq_num}")

            # Simulate ACK loss
            if random.random() < self.ack_loss:
                server_logger.info(f"ACK for Seq Num {seq_num} lost!")
                continue  # Simulate ACK loss by not sending it

            # Send ACK
            ack_packet = bytearray()

            ack_packet.append(expected_seq_num - 1 if expected_seq_num > 0 else 0xFF)  # ACK the received sequence number
            
            ack_packet.append(0x00)  # EOF
            server_logger.info(f"Sending ACK for Seq Num: {expected_seq_num - 1}")
            self.sock.sendto(ack_packet, server)

    def start(self):
        server_logger.info("Waiting for requests...")
        while True:
            try:
                data, client_address = self.sock.recvfrom(1024)
                message = data.decode()

                if message.startswith("-testgbn"):
                    server_logger.info("Starting protocol test")
                    parts = message.split()
                    # server_logger.info(f"Parts: {parts}")
                    filename = parts[1] if len(parts) > 1 else "test_txt.txt"
                    server_logger.info(f"Send {filename}")
                    # Simulate some data to send
                    self.data_buffer = self.get_data("./data/server/" + filename)
                    # Start a thread to handle sending data via GBN
                    send_thread = threading.Thread(target=self.handle_gbn, args=(client_address,))
                    send_thread.start()

                    # Start a thread to receive ACKs
                    ack_thread = threading.Thread(target=self.receive_ack)
                    ack_thread.start()

                    send_thread.join()
                    ack_thread.join()
                    server_logger.info("Transmission complete")
                elif message.startswith("-send"):
                    self.sock.settimeout(6.0)
                    receive_thread = threading.Thread(target=self.receive_gbn)
                    receive_thread.start()
                    receive_thread.join()
                    received_data = b''.join(i for i in self.response)
                    file_name = get_filename(received_data)
                    server_logger.info(f"Response from server: {file_name}")
                    output_file = "./data/server/receive/" + file_name
                    with open(output_file, 'wb') as file:
                        file.write(received_data)
                    self.sock.settimeout(None)
                elif message == "-time":
                    server_time = time.ctime().encode()
                    server_logger.info(f"Server time: {server_time.decode()}")
                    self.sock.sendto(server_time, client_address)
                elif message == "-quit":
                    server_logger.info("Good bye!")
                    self.sock.sendto("Good bye!".encode(), client_address)
                    break
                else:
                    self.sock.sendto(message.encode(), client_address)

            except KeyboardInterrupt:
                server_logger.info("Server is shutting down.")
                break

            self.base = 0  # Base of the window
            self.next_seq_num = 0  # Next sequence number to be sent
            self.data_buffer = []  # Buffer for storing data to be sent

        # Close the socket
        self.sock.close()

class StopAndWaitServer(GBNServer):
    def __init__(self, host='localhost', port=12345, timeout=2, packet_loss=0.2, ack_loss=0.2):
        super().__init__(host, port, 1, timeout, packet_loss, ack_loss)

if __name__ == '__main__':
    server = GBNServer()
    server.start()