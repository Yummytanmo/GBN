import socket
import threading
import logging
import time

# Set up server logger
server_logger = logging.getLogger('SERVER')
server_logger.setLevel(logging.INFO)

# Configure logging format with a custom header "SERVER"
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - SERVER - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
server_logger.addHandler(handler)

class GBNServer:
    def __init__(self, host='localhost', port=12345, window_size=10, timeout=2):
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

    def send_packet(self, seq_num, data, client_address):
        """Construct and send a data packet."""
        packet = bytearray()
        packet.append(seq_num)  # 1 byte for sequence number
        packet.extend(data)  # Append the actual data
        packet.append(0x00)  # EOF indicator (end of frame)
        server_logger.info(f"Sending packet with Seq Num: {seq_num}")
        self.sock.sendto(packet, client_address)

    def send_fin(self, client_address):
        """Send a FIN message to indicate end of transmission."""
        fin_packet = bytearray()
        fin_packet.append(0xFF)  # Use 0xFF as the special FIN sequence number
        fin_packet.append(0x00)  # EOF
        server_logger.info("Sending FIN packet to indicate end of transmission")
        self.sock.sendto(fin_packet, client_address)

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


    def start(self):
        server_logger.info("Waiting for requests...")
        while True:
            try:
                data, client_address = self.sock.recvfrom(1024)
                message = data.decode()

                if message.startswith("-testgbn"):
                    server_logger.info("Starting GBN protocol test")
                    parts = message.split()
                    # server_logger.info(f"Parts: {parts}")
                    filename = parts[1] if len(parts) > 1 else "test_figure.png"
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
                    server_logger.info("GBN transmission complete")
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


if __name__ == '__main__':
    server = GBNServer()
    server.start()