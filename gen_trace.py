import random

def generate_memory_access_file(file_path, num_lines, thread_info):
    threads = list(thread_info.keys())
    weights = [thread_info[thread][4] for thread in threads]

    with open(file_path, 'w') as file:
        for _ in range(num_lines):
            thread = random.choices(threads, weights=weights)[0]
            start_addr, range_size, read_freq, access_size_weights = thread_info[thread][:4]
            write_freq = 1 - read_freq
            operation = random.choices(['R', 'W'], weights=[read_freq, write_freq])[0]
            address = random.randint(start_addr, start_addr + range_size)
            size = random.choices([64, 128, 256], weights=access_size_weights)[0]
            line = f"{operation} 0x{address:X} 0x{size:X}\n"  # 十六进制格式化输出
            file.write(line)

# 示例用法
file_path = 'memory_access.txt'
num_lines = 3000  # 生成的行数

# 定义不同线程的地址范围、读写频率、访问大小的频率和线程出现的频率权重
# 每个键表示线程名称，对应的值是一个包含五个元素的列表：
# 第一个元素是地址范围的最小值，第二个元素是地址范围的大小，
# 第三个元素是读操作的频率
# 第四个元素是访问大小的频率，表示每个大小值在生成时的权重，
# 第五个元素是线程出现的频率权重
thread_info = {
    'Thread1': (0x001000000, 0x200000, 0.8, [2, 3, 1], 1),
    'Thread2': (0x010000000, 0x200000, 0.5, [1, 1, 1], 1),
    'Thread3': (0x011000000, 0x200000, 0.9, [3, 2, 1], 1),
    'Thread4': (0x100000000, 0x200000, 0.6, [3, 2, 1], 1)
}

generate_memory_access_file(file_path, num_lines, thread_info)