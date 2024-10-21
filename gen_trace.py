# Usage: python3 gen_trace.py -n lines -f thread_yaml [-o output_file] [-p pattern(random/stream)]
# Encoded in UTF-8

import argparse
import random
import yaml

def generate_memory_access_file(file_path, num_lines, thread_info, pattern):
    print("Generating...")
    threads = list(thread_info.keys())
    weights = [thread_info[thread][5] for thread in threads]
    address_dict = {key: value[0] for key, value in thread_info.items()}

    with open(file_path, 'w') as file:
        if pattern == "random":
            i = 0
            while i < num_lines:
                thread = random.choices(threads, weights=weights)[0]
                start_addr, range_size, read_freq, access_size, access_size_weights = thread_info[thread][:5]
                write_freq = 1 - read_freq
                operation = random.choices(['R', 'W'], weights=[read_freq, write_freq])[0]
                # address = random.randint(start_addr, start_addr + range_size) & ~(0x03F) # Align to 64.
                address = random.randint(start_addr, start_addr + range_size - 1) & ~(0x03F) # Align to 64.
                size = random.choices(access_size, weights=access_size_weights)[0]
                if address+size > (start_addr+range_size) or (size//64 + i) > num_lines:
                    continue
                for _ in range(size // 64):
                    line = f"{operation} 0x{address:X} 0x40\n"  # 十六进制格式化输出
                    file.write(line)
                    address += 64
                    i += 1

        elif pattern == "stream":
            # 完全连续
            for _ in range(num_lines):
                thread = random.choices(threads, weights=weights)[0]
                start_addr, range_size, read_freq, access_size, access_size_weights = thread_info[thread][:5]
                write_freq = 1 - read_freq
                operation = random.choices(['R', 'W'], weights=[read_freq, write_freq])[0]
                address = address_dict[thread]
                size = 64
                address_dict[thread] = (address_dict[thread] + size - thread_info[thread][0]) % thread_info[thread][1] + thread_info[thread][0]
                line = f"{operation} 0x{address:X} 0x{size:X}\n"  # 十六进制格式化输出
                file.write(line)
        else:
            print("Unsupported pattern.")
            return

    print(f"Trace file    : \"{file_path}\"")
    print(f"Request number: {num_lines}")
    print(f"Trace pattern : {pattern}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Process some input and output files.")

    parser.add_argument('-n', '--number', type=int, required=True, help='Number of traces.')
    parser.add_argument('-f', '--file', required=True, help='YAML file that descripts thread info.')
    parser.add_argument('-o', '--output', required=True, help='Output trace file name.')
    parser.add_argument('-p', '--pattern', required=False, help='Memory access pattern.', default='random')

    args = parser.parse_args()
    
    if not args.pattern:
        pattern = "random"
    elif args.pattern != "random" and args.pattern != "consecutive":
        print("Unsupported memory access pattern.")
        exit()
    else:
        pattern = args.pattern

    if args.output:
        file_path = args.output
    else:
        file_path = pattern+'.trace'

    with open(args.file, 'r') as file:
        thread_info = yaml.safe_load(file)

    generate_memory_access_file(file_path, args.number, thread_info, pattern)
