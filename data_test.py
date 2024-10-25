from datetime import datetime
import magic

def get_data(file_path):
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

def get_extension(data):
     # 自动识别文件类型
    mime = magic.Magic(mime=True)
    file_type = mime.from_buffer(data[:2048])  # 检测文件前2048字节
    print(f"Detected file type: {file_type}")

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

def get_file_name(data):
    current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    extension = get_extension(data)
    file_name = f"received_file_{current_time}{extension}"
    return file_name

data_buffer = get_data("./data/server/test.jpg")
print(len(data_buffer))
data = b''.join(i for i in data_buffer)

output_file = "./data/client/" + get_file_name(data)
with open(output_file, 'wb') as file:
     file.write(data)

