# Usage: python3 analyze.py [log] [notes]
# Encoded in UTF-8

import datetime
import sys
import matplotlib.pyplot as plt
import numpy as np

# 读取文本文件，逐行读取数字
def read_numbers_from_file(file_path):
    with open(file_path, 'r') as file:
        numbers = [float(line.strip()) for line in file]
    return numbers

# 统计数字的总数、平均数和中位数
def analyze_numbers(numbers):
    total = len(numbers)
    average = np.mean(numbers)
    median = np.median(numbers)
    return total, average, median

# 绘制直方图
def plot_histogram(numbers, bin_width, fig_name='plot.png', title='Latency Distribution'):
    # 统计数字
    total, average, median = analyze_numbers(numbers)
    print(f"Total numbers: {total}")
    print(f"Average: {average}")
    print(f"Median: {median}")
    bins = np.arange(0, max(numbers) + bin_width, bin_width)
    plt.hist(numbers, bins=bins, edgecolor='black')
    plt.xlabel('Latency/cycles')
    plt.ylabel('Frequency')
    plt.title(title)
    # 添加总数、平均数、中位数的图注
    plt.text(0.7, 0.9, f'Total: {total}', transform=plt.gca().transAxes)
    plt.text(0.7, 0.85, f'Average: {average:.2f}', transform=plt.gca().transAxes)
    plt.text(0.7, 0.8, f'Median: {median}', transform=plt.gca().transAxes)        
    plt.show()
    # 保存图像
    plt.savefig(fig_name)
    print(f"Output figure \"{fig_name}\"")

# 主函数
def main():
    args = sys.argv
    if len(args) > 1:
        file_path = args[1]
    else:
        file_path = 'memory_access.log'

    plot_path = 'plot'
    # latency统计间隔
    bin_width = 50
    # 获取当前时间
    current_time = datetime.datetime.now()
    # 格式化时间戳字符串
    timestamp = current_time.strftime("%Y%m%d_%H%M%S")
    # 构建带时间戳的文件名
    plot_name = f"latency_distribution_{timestamp}.png"
    # 读取数字
    numbers = read_numbers_from_file(file_path)

    if len(args) > 2:
        notes = args[2]
        # 绘制直方图
        plot_histogram(numbers, bin_width, plot_path+'/'+plot_name, notes)
    else:
        plot_histogram(numbers, bin_width, plot_path+'/'+plot_name)
    

if __name__ == '__main__':
    main()