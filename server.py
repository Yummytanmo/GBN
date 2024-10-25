from datetime import datetime
import random
import socket
import threading
import logging
import time
import magic
SOCK_TIMEOUT = 2.0
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
    def __init__(self, host='localhost', port=12345, window_size=10, timeout=0.3, packet_loss=0.2, ack_loss=0.2):
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
        self.sock_timeout = SOCK_TIMEOUT

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
                    self.sock.settimeout(self.sock_timeout)
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

            self.__init__()

        # Close the socket
        self.sock.close()

class StopAndWaitServer(GBNServer):
    def __init__(self, host='localhost', port=12345, timeout=2, packet_loss=0.2, ack_loss=0.2):
        super().__init__(host, port, 1, timeout, packet_loss, ack_loss)

class SRServer:
    def __init__(self, host='localhost', port=12345, window_size=10, timeout=0.3, packet_loss=0.2, ack_loss=0.2):
        self.server_address = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.server_address)
        self.window_size = window_size
        self.timeout = timeout
        self.unack = []
        self.base = 0
        self.rcv_base = 0
        self.next_seq_num = 0
        self.data_buffer = []
        self.lock = threading.Lock()
        self.acknowledged = threading.Event()
        self.timers = {}
        self.packet_loss = packet_loss
        self.ack_loss = ack_loss
        self.response = []
        self.acks_received = [False] * window_size
        self.received_data = [None] * window_size
        self.sock_timeout = SOCK_TIMEOUT

    def send_packet(self, seq_num, data, client_address):
        """Construct and send a data packet."""
        packet = bytearray()
        packet.append(seq_num)
        packet.extend(data)
        packet.append(0x00)  # EOF indicator
        server_logger.info(f"Sending packet with Seq Num: {seq_num}")
        self.sock.sendto(packet, client_address)
        

    def handle_sr(self, client_address):
        """Main SR protocol handler to send data."""
        while self.base < len(self.data_buffer):
            with self.lock:
                # Send packets in the window
                while self.next_seq_num < self.base + self.window_size and self.next_seq_num < len(self.data_buffer):
                    if self.next_seq_num in self.unack:
                        self.send_packet(self.next_seq_num, self.data_buffer[self.next_seq_num], client_address)
                        self.start_timer(self.next_seq_num, client_address)
                    self.next_seq_num += 1

            # Wait for ACKs
            self.acknowledged.wait()
            self.acknowledged.clear()

    def start_timer(self, seq_num, client_address):
        """Start a timer for the given sequence number."""
        if seq_num not in self.timers:
            timer = threading.Timer(self.timeout, self.timeout_handler, [seq_num, client_address])
            self.timers[seq_num] = timer
            timer.start()

    def stop_timer(self, seq_num):
        """Stop the timer for the given sequence number."""
        if seq_num in self.timers:
            self.timers[seq_num].cancel()
            del self.timers[seq_num]

    def timeout_handler(self, seq_num, client_address):
        """Handle packet retransmission on timeout."""
        with self.lock:
            if seq_num >= self.base:
                server_logger.info(f"Timeout! Resending packets from Seq Num: {seq_num}")
                self.send_packet(seq_num, self.data_buffer[seq_num], client_address)
                self.stop_timer(seq_num)
                self.start_timer(seq_num, client_address)  # Restart the timer for this packet

    def receive_ack(self):
        """Receive ACK from client."""
        while True:
            ack_packet, client_address = self.sock.recvfrom(2048)
            ack_num = ack_packet[0]
            with self.lock:
                if self.base <= ack_num < self.base + self.window_size:
                    if ack_num in self.unack:
                        self.unack.remove(ack_num)
                    server_logger.info(f"Received ACK for Seq Num: {ack_num}")
                    if len(self.unack) > 0:
                        self.base = min(self.unack)
                    else:
                        self.base = len(self.data_buffer)
                    server_logger.info(f"Move window to {self.base}")
                    
                    self.stop_timer(ack_num)
                    

                    # Signal to slide the window
                    self.acknowledged.set()

            if self.base == len(self.data_buffer):  # All packets sent and acknowledged
                break

    def get_data(self, file_path):
        with open(file_path, 'rb') as file:
            file_data = file.read()
        packets = []
        for i in range(0, len(file_data), 1024):
            data_chunk = file_data[i:i + 1024]
            packets.append(data_chunk)
        return packets

    def receive_sr(self):
        """Receive data using Selective Repeat protocol."""
        while True:
            try:
                data, server = self.sock.recvfrom(2048)
            except socket.timeout:
                server_logger.info("Timeout ending transmission.")
                break

            if random.random() < self.packet_loss:
                server_logger.info(f"Packet with Seq Num {data[0]} lost!")
                continue

            seq_num = data[0]
            if self.rcv_base <= seq_num < self.rcv_base + self.window_size:
                server_logger.info(f"Received packet with Seq Num: {seq_num}")
                if not self.acks_received[seq_num % self.window_size]:
                    self.received_data[seq_num % self.window_size] = data[1:-1]
                    self.acks_received[seq_num % self.window_size] = True
                    server_logger.info(f"Caching data with sequence number {seq_num}")
                if random.random() < self.ack_loss:
                    server_logger.info(f"ACK for Seq Num {seq_num} lost!")
                    continue

                ack_packet = bytearray()
                ack_packet.append(seq_num)
                ack_packet.append(0x00)  # EOF
                self.sock.sendto(ack_packet, server)
                server_logger.info(f"Sending ACK for Seq Num: {seq_num - 1}")
                # Check for continuous data to deliver
                while self.acks_received[self.rcv_base % self.window_size]:
                    # Deliver data to the upper layer
                    delivered_data = self.received_data[self.rcv_base % self.window_size]
                    if delivered_data is not None:
                        server_logger.info(f"Delivering data with sequence number {self.rcv_base} to upper layer")
                        self.response.append(delivered_data)
                    # Clear the cache
                    self.received_data[self.rcv_base % self.window_size] = None
                    self.acks_received[self.rcv_base % self.window_size] = False
                    self.rcv_base += 1  # Move the receiver window base
                    server_logger.info(f"Move the receiver window base to {self.rcv_base}")

            elif self.rcv_base - self.window_size <= seq_num < self.rcv_base:
                    # Sequence number is within [rcv_base-N, rcv_base-1]
                    server_logger.info(f"Received duplicate sequence number {seq_num}, must send ACK")
                    ack_packet = bytearray()
                    ack_packet.append(seq_num)  # Acknowledge the sequence number
                    ack_packet.append(0x00)  # EOF
                    if random.random() >= self.ack_loss:
                        self.sock.sendto(ack_packet, server)
                    server_logger.info(f"Sending ACK {seq_num} (duplicate)")
            else:
                    # Ignore packets in other cases
                    server_logger.info(f"Sequence number {seq_num} is out of window range, ignoring")
            

    def start(self):
        server_logger.info("Waiting for requests...")
        while True:
            try:
                data, client_address = self.sock.recvfrom(1024)
                message = data.decode()

                if message.startswith("-testsr"):
                    server_logger.info("Starting protocol test")
                    parts = message.split()
                    filename = parts[1] if len(parts) > 1 else "test_txt.txt"
                    server_logger.info(f"Send {filename}")
                    self.data_buffer = self.get_data("./data/server/" + filename)
                    self.unack = [i for i in range(len(self.data_buffer))]
                    send_thread = threading.Thread(target=self.handle_sr, args=(client_address,))
                    send_thread.start()

                    ack_thread = threading.Thread(target=self.receive_ack)
                    ack_thread.start()

                    send_thread.join()
                    ack_thread.join()
                    server_logger.info("Transmission complete")
                elif message.startswith("-send"):
                    self.sock.settimeout(self.sock_timeout)
                    receive_thread = threading.Thread(target=self.receive_sr)
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

            self.__init__()

        self.sock.close()


if __name__ == '__main__':
    server = SRServer()
    server.start()