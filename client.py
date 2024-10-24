import socket
import random
import threading
import logging


# Set up client logger
client_logger = logging.getLogger('CLIENT')
client_logger.setLevel(logging.INFO)

# Configure logging format with a custom header "SERVER"
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - CLIENT - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
client_logger.addHandler(handler)

class GBNClient:
    def __init__(self, server_host='localhost', server_port=12345, packet_loss=0.2, ack_loss=0.2):
        self.server_address = (server_host, server_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.packet_loss = packet_loss  # Loss rate for data packets
        self.ack_loss = ack_loss  # Loss rate for ACKs
        self.response = ""

    def receive_gbn(self):
        """Receive data using Go-Back-N protocol, simulate packet and ACK loss."""
        expected_seq_num = 0  # The next expected sequence number
        while True:
            # Receive packet
            data, server = self.sock.recvfrom(1024)
            if data[0] == 0xFF:
                client_logger.info("Received FIN packet, ending transmission.")
                break  # Exit the loop and end the GBN reception

            if random.random() < self.packet_loss:
                client_logger.info(f"Packet with Seq Num {data[0]} lost!")
                continue  # Simulate packet loss by not processing the packet
            
            # Extract the sequence number
            seq_num = data[0]
            if seq_num == expected_seq_num:
                # Correct sequence number
                client_logger.info(f"Received packet with Seq Num: {seq_num}, Data: {data[1:-1].decode()}")
                self.response += data[1:-1].decode()
                client_logger.info(f"Current response: {self.response}")
                expected_seq_num += 1
            else:
                client_logger.info(f"Out-of-order packet with Seq Num: {seq_num}, expected {expected_seq_num}")

            # Simulate ACK loss
            if random.random() < self.ack_loss:
                client_logger.info(f"ACK for Seq Num {seq_num} lost!")
                continue  # Simulate ACK loss by not sending it

            # Send ACK
            ack_packet = bytearray()
            ack_packet.append(seq_num)  # ACK the received sequence number
            ack_packet.append(0x00)  # EOF
            client_logger.info(f"Sending ACK for Seq Num: {seq_num}")
            self.sock.sendto(ack_packet, server)

    def send_command(self, command):
        """Send command to the server and receive the response."""
        self.sock.sendto(command.encode(), self.server_address)

        # If it's the GBN test command, run the GBN receiving mechanism
        if command.startswith("-testgbn"):
            receive_thread = threading.Thread(target=self.receive_gbn)
            receive_thread.start()
            receive_thread.join()
            client_logger.info(f"Response from server: {self.response}")
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
                self.packet_loss = packet_loss
                self.ack_loss = ack_loss
                client_logger.info(f"Starting GBN test with packet loss: {packet_loss}, ACK loss: {ack_loss}")
                self.send_command(command)
            else:
                self.send_command(command)


if __name__ == '__main__':
    client = GBNClient()
    client.start()