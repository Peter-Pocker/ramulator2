# Usage: python3 analyze.py [-i input_cmd_log] [-o output_fig] [-n notes]
# Encoded in UTF-8

import argparse
import datetime
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

def draw_cmd_interval_distribution(file_path, fig_name, notes=None):
    data = pd.read_csv(file_path, header=None, skipinitialspace=True)
    # Counting the intervals of all commands.
    freq = {}
    for item in data[0]:
        if item >= 400:
            if 400 not in freq:
                freq[400] = 1
            else:
                freq[400] += 1
        elif item not in freq:
            freq[item] = 1
        else:
            freq[item] += 1
    sorted_freq = dict(sorted(freq.items()))
    sorted_freq['>=400'] = sorted_freq.pop(400)

    # Counting the intervals of RD commands.
    RD_tick = data[data[2]=='RD'][1].copy()
    for index in range(len(RD_tick)-1, 1, -1):
        RD_tick.iloc[index] -= RD_tick.iloc[index-1]
    RD_interval_freq = {}
    for item in RD_tick:
        if item >= 400:
            if 400 not in RD_interval_freq:
                RD_interval_freq[400] = 1
            else:
                RD_interval_freq[400] += 1
        elif item not in RD_interval_freq:
            RD_interval_freq[item] = 1
        else:
            RD_interval_freq[item] += 1
    sorted_RD_interval_freq = dict(sorted(RD_interval_freq.items()))
    sorted_RD_interval_freq['>=400'] = sorted_RD_interval_freq.pop(400)

    # Drawing pictures.
    fig, axs = plt.subplots(2, 1, figsize=(8, 8))
    fig.tight_layout(pad=5.0)
    axs = axs.flatten()

    x1 = np.arange(len(sorted_freq))
    axs[0].bar(x1, sorted_freq.values())
    custom_ticks = sorted_freq.keys()
    axs[0].set_xticks(x1, custom_ticks)
    axs[0].set_xlabel('Interval/cycles')
    axs[0].set_ylabel('Frequency')
    axs[0].set_title('CMD interval')
    amount = len(data[0])
    mean = data[0].mean()
    median = data[0].median()
    axs[0].text(0.7, 0.85,  f'Amount: {amount}', transform=axs[0].transAxes)
    axs[0].text(0.7, 0.9,   f'Mean: {mean:.2f}', transform=axs[0].transAxes)
    axs[0].text(0.7, 0.95,  f'Median: {median}', transform=axs[0].transAxes)

    x2 = np.arange(len(sorted_RD_interval_freq))
    axs[1].bar(x2, sorted_RD_interval_freq.values())
    custom_ticks = sorted_RD_interval_freq.keys()
    axs[1].set_xticks(x2, custom_ticks)
    axs[1].set_xlabel('Interval/cycles')
    axs[1].set_ylabel('Frequency')
    axs[1].set_title('RD interval')
    amount = len(RD_tick)
    mean = RD_tick.mean()
    median = RD_tick.median()
    axs[1].text(0.7, 0.85,  f'Amount: {amount}', transform=axs[1].transAxes)
    axs[1].text(0.7, 0.9,   f'Mean: {mean:.2f}', transform=axs[1].transAxes)
    axs[1].text(0.7, 0.95,  f'Median: {median}', transform=axs[1].transAxes)
    fig.tight_layout()
    wspace = 0.5  # 调整子图之间的水平间距
    plt.subplots_adjust(wspace=wspace)

    fig_title = 'Commands Interval Distribution'
    if notes is not None:
        fig_title = fig_title+'\n'+notes
    fig.suptitle(fig_title, fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.95]) 
    plt.show(block=True)
    plt.savefig(fig_name)
    plt.close()

    print(f"Output picture \"{fig_name}\".")   
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
            draw_cmd_interval_distribution(args.input, args.output, args.notes)
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
    draw_cmd_interval_distribution(args.input, f"{output_path}/cmd_interval_{timestamp}.png", args.notes)
