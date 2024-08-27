# Usage: python3 analyze.py [-i input_log] [-o output_path] [-n notes] [-p]
# Encoded in UTF-8

import argparse
import datetime
import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def analyze(file_path, fig_name, notes="", print_result=False):
    # 读取CSV文件
    data = pd.read_csv(file_path, header=0)
    
    stats = {}

    fig, axs = plt.subplots(4, 2, figsize=(12, 16))  # 4行2列的子图，图像大小可调整
    fig.tight_layout(pad=5.0)  # 调整子图之间的间距
    
    # Flatten the axs array for easier indexing
    axs = axs.flatten()

    # 对每一列进行统计
    for i, column in enumerate(data.columns):
        col_data = data[column]
        mean = col_data.mean()
        median = col_data.median()
        amount = len(col_data)
        stats[column] = {
            'mean': mean,
            'median': median,
            'amount': amount
        }
        if print_result:
            print(f"Latency: {column}")
            print(f"  Mean: {mean}")
            print(f"Median: {median}")
            print(f"Amount: {amount}")
            print("-" * 30)
    
        bin_width = col_data.max() // 20 # Never set less than 20!
        bins = np.arange(0, col_data.max()+bin_width, bin_width)
        axs[i].hist(col_data, bins=bins, edgecolor='black')
        axs[i].set_title(f'{column} Latency Distribution')
        axs[i].set_xlabel('Latency')
        axs[i].set_ylabel('Frequency')
        axs[i].text(0.7, 0.85,  f'Amount: {amount}', transform=axs[i].transAxes)
        axs[i].text(0.7, 0.9, f'Mean  : {mean:.2f}', transform=axs[i].transAxes)
        axs[i].text(0.7, 0.95,  f'Median: {median}', transform=axs[i].transAxes)    

        # axs[i].axvline(mean, color='red', linestyle='dashed', linewidth=1, label=f'Mean: {mean:.2f}')
        # axs[i].axvline(median, color='green', linestyle='dashed', linewidth=1, label=f'Median: {median:.2f}')
        # axs[i].legend()

    # Hide the 8th subplot (if it exists)
    if len(data.columns) < 8:
        axs[-1].axis('off')

    plt.text(0, 1, notes, transform=axs[-1].transAxes)

    plt.show()
    # 保存图像
    plt.savefig(fig_name)
    print(f"Output figure \"{fig_name}\".")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Process some input and output files.")

    parser.add_argument('-i', '--input', required=False, help='Input log file.')
    parser.add_argument('-o', '--output', required=False, help='Output picture file.')
    parser.add_argument('-n', '--notes', required=False, help='Additional description.')
    parser.add_argument('-p', action='store_true', help='Print the statistics.')

    args = parser.parse_args()

    default_input_log = 'memory_access.csv'
    default_output_path = '.'

    if args.input:
        file_path = args.input
    else:
        file_path = default_input_log

    if args.output:
        if not os.path.exists(args.output):
            analyze(file_path, args.output, args.notes, args.p)
        elif os.path.isdir(args.output):
            output_path = args.output
        else:
            print(f"File {args.output} already exsits.")
            exit()
    else:
        if not os.path.exists(default_output_path):
            os.makedirs(default_output_path)
        output_path = default_output_path
        
    current_time = datetime.datetime.now()
    timestamp = current_time.strftime("%Y_%m_%d_%H_%M_%S")

    analyze(file_path, f"{output_path}/{timestamp}.png", args.notes, args.p)
