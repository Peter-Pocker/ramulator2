# Usage: python3 dse.py [-c config_yaml] [-o output_log_folder] [--auto_clean]

import argparse
from concurrent.futures import ThreadPoolExecutor
import re
import shutil
import time
import pandas as pd
import yaml
import subprocess
import os
from latency_bd import draw_latency_breakdown
from interval import draw_cmd_interval_distribution

def update_yaml(data, updates):
    """
    递归更新 YAML 数据中的内容。
    
    :param data: 原始 YAML 数据
    :param updates: 用于更新的字典
    """
    for key, value in updates.items():
        if isinstance(value, dict) and key in data:
            update_yaml(data[key], value)
        else:
            data[key] = value


def modify_yaml(file_path, updates, new_yaml):
    """
    Modify YAML file with provided dict.

    :param file_path: YAML 文件的路径
    :param updates: 用于更新的字典
    """
    with open(file_path, 'r') as file:
        data = yaml.safe_load(file)

    update_yaml(data, updates)

    with open(new_yaml, 'w') as file:
        yaml.dump(data, file)


def analyze(access_log):
    data = pd.read_csv(access_log, header=0, skipinitialspace=True)
    stats = {}
    for column in data.columns:
        col_data = data[column]
        mean = col_data.mean()
        median = col_data.median()
        amount = len(col_data)
        stats[column] = {
            'mean': mean,
            'median': median,
            'amount': amount
        }
    return stats


def parse_cmd_cnt(file_path):
    """ 
    Parse the command count file into dict instance.
    """
    result = {}
    with open(file_path, 'r') as file:
        for line in file:
            key, value = line.strip().split(':')
            result[key.strip()] = int(value.strip())
    return result


def parse_memory_stats(file_path):
    """ 
    Find out the requests info.
    """
    result = {}
    
    pattern = re.compile(r'(total_num_other_requests|total_num_write_requests|total_num_read_requests|memory_system_cycles):\s*(\d+)')
    
    with open(file_path, 'r') as file:
        for line in file:
            match = pattern.search(line)
            if match:
                key = match.group(1)
                value = int(match.group(2)) 
                result[key] = value
    
    return result


def test_a_mapping(mapping):
    updates = {
        'Frontend': {
            'path': 'to_decide',
            'access_log': 'to_decide'
        },
        'MemorySystem': {
            'AddrMapper': {
                'mapping': 'to_decide'
            },
            'Controller': {
                'plugins': [
                    {
                        'ControllerPlugin': {
                            'impl': 'TraceRecorder', 
                            'path': 'to_decide'
                        }
                    },
                    {
                        'ControllerPlugin': {
                            'impl': 'CommandCounter', 
                            'path': 'to_decide',
                            'commands_to_count': CMD_TO_COUNT
                        }
                    },
                ]
            }
        }
    }

    cur_path = f"{DSE_ROOT_FOLDER}{mapping}/"
    if os.path.exists(cur_path):
        if VERBOSE:
            print(f'Deleting folder \"{cur_path}\".')
        shutil.rmtree(cur_path)
    os.mkdir(cur_path)

    updates['MemorySystem']['AddrMapper']['mapping'] = mapping

    for pattern, trace in TRACE_DICT.items():
        access_log = f"{cur_path}{pattern}.csv"
        cmd_issue_log_prefix = f"{cur_path}{pattern}_issue_log"
        cmd_cnt_log = f"{cur_path}{pattern}_cmd_cnt.log"
        config_yaml = f"{cur_path}{pattern}.yaml"
        stdout_log = f"{cur_path}debug.log"

        updates['Frontend']['path'] = trace
        updates['Frontend']['access_log'] = access_log
        # Command Tracer Plugin
        updates['MemorySystem']['Controller']['plugins'][0]['ControllerPlugin']['path'] = cmd_issue_log_prefix
        # Command Counter Plugin
        updates['MemorySystem']['Controller']['plugins'][1]['ControllerPlugin']['path'] = cmd_cnt_log
        modify_yaml(BASE_CONFIG, updates, config_yaml)
        # Run Ramulator.
        subprocess.run(f"{RAMULATOR_PATH} -f {config_yaml} > {stdout_log}", shell=True)
        # Analyze results.
        stats = analyze(access_log)
        cmd_cnt = parse_cmd_cnt(cmd_cnt_log)
        request = parse_memory_stats(stdout_log)
        # Utilization of DRAM bandwidth.
        bw_util = (request['total_num_read_requests'] + request['total_num_write_requests']) * 4 / request['memory_system_cycles']

        with open(TOTAL_LOG, 'a') as file:
            file.write(f"{pattern}, {trace}, {mapping}, "
                    + f"{request['memory_system_cycles']}, {bw_util}, {stats['process']['mean']}, {stats['process']['median']}, "
                    + f"{request['total_num_read_requests']}, {request['total_num_write_requests']}, "
                    + ', '.join(str(cmd_cnt[command]) for command in CMD_TO_COUNT) + '\n')


def concurrent_exec():
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=len(MAPPER_TABLE)) as executor:
        futures = [executor.submit(test_a_mapping, mapping) for mapping in MAPPER_TABLE]
    
        # Sync all threads.
        for future in futures:
            future.result()

    end_time = time.time()
    execution_time = end_time - start_time
    print(f"Execution time: {execution_time} seconds")


def print2xlsx(output_file):
    df = pd.read_csv(TOTAL_LOG)
    with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')

        workbook  = writer.book
        worksheet = writer.sheets['Sheet1']

        # 指定每一列的数据类型
        format_text = workbook.add_format({'num_format': '@'})  # text format
        format_int = workbook.add_format({'num_format': '0'})   # integer format
        format_num = workbook.add_format({'num_format': '0.00'})  # float format
        format_percent = workbook.add_format({'num_format': '0.00%'}) # percentage format

        # 设置列格式
        worksheet.set_column('A:C', None, format_text)    # pattern, trace, mapping
        worksheet.set_column('D:D', None, format_int)     # total_latency
        worksheet.set_column('E:E', None, format_percent) # bw_percentage
        worksheet.set_column('F:G', None, format_num)     # avg_latency, mid_latency
        worksheet.set_column('H:Q', None, format_int)     # # of read, # of write, commands


def draw_picture(auto_clean=False):
    # Because `matplotlib.pyplot` is multi-thread unsafe, pictures have to be made serially.
    print("Starting to draw figures...")

    for mapper in MAPPER_TABLE:
        for pattern, trace in TRACE_DICT.items():
            cur_path = f"{DSE_ROOT_FOLDER}{mapper}/"
            cmd_trace_file = f"{cur_path}{pattern}_issue_log_ch0.log"
            access_log = f"{cur_path}{pattern}.csv"
            plot_name1 = f"{cur_path}{pattern}_latency_breakdown.png"
            plot_name2 = f"{cur_path}{pattern}_cmd_interval.png"
            note = f"{mapper}\n{trace}"

            if os.path.exists(plot_name1):
                os.remove(plot_name1)
                if VERBOSE:
                    print(f"Deleting \"{plot_name1}\".")
            if VERBOSE:
                print(f"Drawing latency breakdown plot for \"{access_log}\".")
            draw_latency_breakdown(access_log, plot_name1, note)
            if auto_clean:
                if VERBOSE:
                    print(f"[AUTO CLEAN] Deleting \"{access_log}\".")
                os.remove(access_log)

            if os.path.exists(plot_name2):
                os.remove(plot_name2)
                if VERBOSE:
                    print(f"Deleting \"{plot_name2}\".")
            if VERBOSE:
                print(f"Drawing command interval distribution plot for \"{cmd_trace_file}\".")
            draw_cmd_interval_distribution(cmd_trace_file, plot_name2, note)
            if auto_clean:
                if VERBOSE:
                    print(f"[AUTO CLEAN] Deleting \"{cmd_trace_file}\".")
                os.remove(cmd_trace_file)

    print("All figures are done.")          
            

# Global Variables
RAMULATOR_PATH = "./build/ramulator2"
CMD_TO_COUNT = ['ACT', 'PRE', 'PREA', 'RD',  'WR',  'RDA',  'WRA', 'REFab']
TRACE_DICT = {
    'stream_1thread':'trace/1thread_cons_6.trace'
    ,'rand128B_1thread':'trace/1thread_mix_2.trace'
    ,'rand256B_1thread':'trace/1thread_mix_1.trace'
    # ,'random_1thread':'trace/1thread_rand_6.trace'
    # 'stream_1thread':'trace/1thread_stream_readonly_1M_28_addrbit.trace'
    # ,'rand128B_1thread':'trace/1thread_rand128B_readonly_1M_28_addrbit.trace'
    # ,'rand256B_1thread':'trace/1thread_rand256B_readonly_1M_28_addrbit.trace'
    # ,'rand512B_1thread':'trace/1thread_rand512B_readonly_1M_28_addrbit.trace'
    # ,'random_1thread':'trace/1thread_rand_readonly_1M_28_addrbit.trace'
    # ,'stream_2thread':'trace/2thread_stream_readonly_1M.trace'
    # ,'rand128B_2thread':'trace/2thread_rand128B_readonly_1M.trace'
}
MAPPER_TABLE = [
    '1RA-16R-2B-7C-2BG'
    ,'1RA-16R-7C-2B-2BG'
    # ,'1RA-16R-4C-2B-3C-2BG'
    # ,'1RA-16R-1BG-2B-7C-1BG'
    # ,'1RA-16R-2B-6C-2BG-1C'
    # ,'1RA-16R-1BG-2B-5C-1BG-2C'
    # ,'1RA-16R-1BG-2B-4C-1BG-3C'
    # ,'1RA-16R-2B-4C-2BG-3C'
    # ,'1RA-16R-1BG-2B-3C-1BG-4C'
    # ,'1RA-16R-2B-3C-2BG-4C'
    # ,'16R-1RA-2B-3C-2BG-4C'
    # ,'1RA-14R-1BG-2R-2B-2C-1BG-5C'
    # ,'1RA-14R-1BG-2R-4C-1BG-2B-3C'
    # ,'14R-1BG-2R-2B-4C-1RA-3C-1BG'
    # ,'14R-1BG-2R-2B-4C-1RA-1BG-3C'
    # ,'1RA-16R-2B-1C-2BG-6C'
    # ,'1RA-14R-1BG-2R-2B-1C-1BG-6C'
    # ,'1RA-14R-2BG-2R-1B-7C-1B'
    # ,'1RA-14R-1BG-2R-1B-4C-1BG-1B-3C'
    # ,'1RA-14R-2BG-2R-7C-2B'
    # ,'1RA-16R-2BG-2B-7C'
    # ,'1RA-16R-2BG-7C-2B'
    # ,'1RA-14R-1BG-2R-2B-7C-1BG'
    # ,'1RA-14R-1BG-2R-2B-6C-1BG-1C'
    # ,'1RA-14R-1BG-2R-2B-5C-1BG-2C'
    # ,'1RA-14R-1BG-2R-2B-4C-1BG-3C'
    # ,'1RA-14R-1BG-2R-2B-3C-1BG-4C'
    # ,'10R-1RA-2B-6R-2BG-7C'
    # '2BG-2B-1RA-16R-7C'
]

# Program Entry
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Process some input and output files.")
    parser.add_argument('-c', '--config', type=str, required=False, help='Base ramulator config yaml file.', default='ddr4.yaml')
    parser.add_argument('-o', '--output_dir', type=str, required=False, help='Output log folder.', default='./log/')
    parser.add_argument('--auto_clean', action='store_true', help='Whether to delete the log files.')
    parser.add_argument('--verbose', action='store_true', help='Print detail info.')
    args = parser.parse_args()

    global BASE_CONFIG
    global DSE_ROOT_FOLDER
    global TOTAL_LOG
    global VERBOSE

    BASE_CONFIG = args.config
    DSE_ROOT_FOLDER = f"{args.output_dir}/"
    TOTAL_LOG = f"{DSE_ROOT_FOLDER}result.csv"
    VERBOSE = args.verbose

    output_xlsx = f"{DSE_ROOT_FOLDER}result.xlsx"
    
    if os.path.exists(DSE_ROOT_FOLDER):
        print(f"Folder \"{DSE_ROOT_FOLDER}\" already exsits. Program exits.")
        exit()
    else:
        os.makedirs(DSE_ROOT_FOLDER)

    print(f"Program starts. All logs are in folder \"{DSE_ROOT_FOLDER}\".")
    with open(TOTAL_LOG, 'w') as file:
        file.write('pattern, trace, mapping, total_latency, bw_usage, avg_latency, mid_latency, read_req, write_req, ' + ', '.join(cmd for cmd in CMD_TO_COUNT) + '\n')
    concurrent_exec()
    print2xlsx(output_xlsx)
    print(f"Program ends. Excel results can be checked at \"{DSE_ROOT_FOLDER}result.xlsx\".")
    draw_picture(args.auto_clean)
