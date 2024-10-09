# Usage: python3 analyze.py [-i input_cmd_log] [-o output_fig] [-n notes]
# Encoded in UTF-8

import argparse
import datetime
import os
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def draw_array_distribution(file_path, fig_name, notes=None):
    freq = {}
    data = pd.read_csv(file_path, header=None, skipinitialspace=True)
    for item in data[0]:
        if item not in freq:
            freq[item] = 1
        else:
            freq[item] += 1

    sorted_freq = dict(sorted(freq.items()))
    x = np.arange(len(sorted_freq))
    plt.bar(x, sorted_freq.values())
    custom_ticks = sorted_freq.keys()
    plt.xticks(x, custom_ticks)
    plt.xlabel('Interval/cycles')
    plt.ylabel('Frequency')
    amount = len(data[0])
    mean = data[0].mean()
    median = data[0].median()
    plt.text(0.7, 0.85,  f'Amount: {amount}', transform=plt.gca().transAxes)
    plt.text(0.7, 0.9,   f'Mean: {mean:.2f}', transform=plt.gca().transAxes)
    plt.text(0.7, 0.95,  f'Median: {median}', transform=plt.gca().transAxes)    
    if notes is not None:
        plt.title(notes, fontsize=16)
        plt.tight_layout(rect=[0, 0, 1, 0.95]) 
    plt.savefig(fig_name)

    print(f"Output figure \"{fig_name}\".")   
    return sorted_freq


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Process some input and output files.")

    parser.add_argument('-i', '--input', required=False, help='Input log file.', default='issue_log_ch0.log')
    parser.add_argument('-o', '--output', required=False, help='Output picture file.')
    parser.add_argument('-n', '--notes', required=False, help='Additional description.')

    args = parser.parse_args()

    default_input_log = 'issue_log_ch0.log'
    default_output_path = '.'

    if args.output:
        if not os.path.exists(args.output):
            draw_array_distribution(args.input, args.output, args.notes)
            exit()
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
    draw_array_distribution(args.input, f"{output_path}/{timestamp}.png", args.notes)
