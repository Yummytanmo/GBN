import socket
import random
import threading
import logging
from datetime import datetime
import magic

# Set up client logger
client_logger = logging.getLogger('CLIENT')
client_logger.setLevel(logging.INFO)

# Configure logging format with a custom header "SERVER"
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - CLIENT - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
client_logger.addHandler(handler)

def get_extension(data):
     # 自动识别文件类型
    mime = magic.Magic(mime=True)
    file_type = mime.from_buffer(data[:2048])  # 检测文件前2048字节
    client_logger.info(f"Detected file type: {file_type}")

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
class GBNClient:
    def __init__(self, server_host='localhost', server_port=12345, packet_loss=0.2, ack_loss=0.2):
        self.server_address = (server_host, server_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(10.0)
        self.packet_loss = packet_loss  # Loss rate for data packets
        self.ack_loss = ack_loss  # Loss rate for ACKs
        self.response = []

    def receive_gbn(self):
        """Receive data using Go-Back-N protocol, simulate packet and ACK loss."""
        expected_seq_num = 0  # The next expected sequence number
        while True:
            # Receive packet
            try:
                data, server = self.sock.recvfrom(2048)
            except socket.timeout:
                client_logger.info("Timeout ending transmission.")
                break
            
            if random.random() < self.packet_loss:
                client_logger.info(f"Packet with Seq Num {data[0]} lost!")
                continue  # Simulate packet loss by not processing the packet

            # Extract the sequence number
            seq_num = data[0]
            if seq_num == expected_seq_num:
                # Correct sequence number
                client_logger.info(f"Received packet with Seq Num: {seq_num}")
                self.response.append(data[1:-1])
                expected_seq_num += 1
            else:
                client_logger.info(f"Out-of-order packet with Seq Num: {seq_num}, expected {expected_seq_num}")

            # Simulate ACK loss
            if random.random() < self.ack_loss:
                client_logger.info(f"ACK for Seq Num {seq_num} lost!")
                continue  # Simulate ACK loss by not sending it

            # Send ACK
            ack_packet = bytearray()

            ack_packet.append(expected_seq_num - 1 if expected_seq_num > 0 else 0xFF)  # ACK the received sequence number
            
            ack_packet.append(0x00)  # EOF
            client_logger.info(f"Sending ACK for Seq Num: {expected_seq_num - 1}")
            self.sock.sendto(ack_packet, server)

    def send_command(self, command):
        """Send command to the server and receive the response."""
        self.sock.sendto(command.encode(), self.server_address)

        # If it's the GBN test command, run the GBN receiving mechanism
        if command.startswith("-testgbn"):
            receive_thread = threading.Thread(target=self.receive_gbn)
            receive_thread.start()
            receive_thread.join()
            received_data = b''.join(i for i in self.response)
            file_name = get_filename(received_data)
            client_logger.info(f"Response from server: {file_name}")
            output_file = "./data/client/" + file_name
            with open(output_file, 'wb') as file:
                file.write(received_data)
        else:
            # For other commands, simply receive and client_logger.info the response
            response, _ = self.sock.recvfrom(1024)
            client_logger.info(f"Response from server: {response.decode()}")

    def start(self):
        client_logger.info("Client started. Type commands to interact with the server.")
        while True:
            command = input("> ")
            if command == "-quit":
                self.send_command(command)
                break
            elif command == "-time":
                self.send_command(command)
            elif command.startswith("-testgbn"):
                # Parse optional packet loss and ack loss rates
                parts = command.split()
                packet_loss = float(parts[1]) if len(parts) > 1 else 0.2
                ack_loss = float(parts[2]) if len(parts) > 2 else 0.2
                filename = parts[3] if len(parts) > 3 else ""
                self.packet_loss = packet_loss
                self.ack_loss = ack_loss
                client_logger.info(f"Starting GBN test with packet loss: {packet_loss}, ACK loss: {ack_loss}")
                self.send_command("-testgbn " + filename)
            # elif command.startswith("-send"):

            else:
                self.send_command(command)
            
            self.response = []


if __name__ == '__main__':
    client = GBNClient()
    client.start()