import argparse
from concurrent.futures import ThreadPoolExecutor
import re
import shutil
import time
import pandas as pd
import yaml
import subprocess
import os

def update_yaml(data, updates):
    """
    递归更新 YAML 数据中的内容。
    
    :param data: 原始 YAML 数据
    :param updates: 用于更新的字典
    """
    for key, value in updates.items():
        if isinstance(value, dict) and key in data:
            # 如果值是字典，则递归更新
            update_yaml(data[key], value)
        # elif isinstance(value, list) and key in data:
        #     for item in value:
        #         for item_yaml in data[key]:
        #             if item
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


def analyze(file_path):
    """ 
    Analyze the test results. 
      
    """
    data = pd.read_csv(file_path, header=0, skipinitialspace=True)
    stats = {}
    for _, column in enumerate(data.columns):
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

    cmd_trace_prefix = 'issue_log'
    cmd_cnt_file = 'cmd_cnt.log'

    if os.path.exists(DSE_ROOT_FOLDER + mapping):
        print(f'Deleting exsitent folder {DSE_ROOT_FOLDER + mapping}')
        shutil.rmtree(DSE_ROOT_FOLDER + mapping)
    os.mkdir(DSE_ROOT_FOLDER + mapping)
    path_prefix = DSE_ROOT_FOLDER + mapping + '/'
    updates['MemorySystem']['AddrMapper']['mapping'] = mapping

    for pattern, trace in TRACE_DICT.items():
        updates['Frontend']['path'] = trace
        access_log = path_prefix + pattern + '.csv'
        updates['Frontend']['access_log'] = access_log
        updates['MemorySystem']['Controller']['plugins'][0]['ControllerPlugin']['path'] = path_prefix + pattern + '_' + cmd_trace_prefix
        updates['MemorySystem']['Controller']['plugins'][1]['ControllerPlugin']['path'] = path_prefix + pattern + '_' + cmd_cnt_file
        modify_yaml(BASE_CONFIG, updates, path_prefix + pattern + '.yaml')
        subprocess.run('./build/ramulator2 -f ' + path_prefix + pattern + '.yaml > ' + path_prefix + 'debug.log', shell=True)
        stats = analyze(access_log)
        cmd_cnt = parse_cmd_cnt(path_prefix + pattern + '_' + cmd_cnt_file)
        request = parse_memory_stats(path_prefix + 'debug.log')
        with open(TOTAL_LOG, 'a') as file:
            file.write(f"{pattern}, {trace}, {mapping}, {request['memory_system_cycles']}, {stats['process']['mean']}, {stats['process']['median']}, {request['total_num_read_requests']}, {request['total_num_write_requests']}, "
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
        format_text = workbook.add_format({'num_format': '@'})  # 文本格式
        format_int = workbook.add_format({'num_format': '0'})   # 整数格式
        format_num = workbook.add_format({'num_format': '0.00'})  # 数字格式

        # 设置列格式
        worksheet.set_column('A:C', None, format_text)  # pattern, trace, mapping
        worksheet.set_column('D:D', None, format_int)   # total_latency
        worksheet.set_column('E:F', None, format_num)   # avg_latency, mid_latency
        worksheet.set_column('G:P', None, format_int)


# Global Variables
BASE_CONFIG = 'ddr4.yaml'
DSE_ROOT_FOLDER = './log/'
TOTAL_LOG = DSE_ROOT_FOLDER + 'total.csv'
CMD_TO_COUNT = ['ACT', 'PRE', 'PREA', 'RD',  'WR',  'RDA',  'WRA', 'REFab']
TRACE_DICT = {
    'consecutive':'trace/1thread_cons_readonly_1M.trace'
    ,'rand128B':'trace/1thread_rand128B_readonly_1M.trace'
    ,'rand256B':'trace/1thread_rand256B_readonly_1M.trace'
    ,'rand512B':'trace/1thread_rand512B_readonly_1M.trace'
    ,'random':'trace/1thread_rand_readonly_1M.trace'
}
MAPPER_TABLE = [
    '1RA-14R-2BG-2R-1B-7C-1B'
    # ,'1RA-14R-1BG-2R-2B-7C-1BG'
    # ,'1RA-16R-2B-7C-2BG'
    # ,'1RA-14R-1BG-2R-2B-6C-1BG-1C'
    # ,'1RA-14R-1BG-2R-2B-5C-1BG-2C'
    # ,'1RA-14R-1BG-2R-2B-4C-1BG-3C'
    # ,'1RA-14R-1BG-2R-2B-3C-1BG-4C'
    # ,'1RA-14R-1BG-2R-2B-2C-1BG-5C'
    # ,'1RA-16R-2B-4C-2BG-3C'
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
    # ,'1RA-14R-2BG-1R-2B-7C-1R'
    ,'1RA-16R-2BG-2B-7C'
]

# Program Entry
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Process some input and output files.")
    parser.add_argument('-o', '--output', type=str, required=False, help='Output excel file.', default='result.xlsx')
    args = parser.parse_args()

    with open(TOTAL_LOG, 'w') as file:
        file.write('pattern, trace, mapping, total_latency, avg_latency, mid_latency, read_req, write_req, ' + ', '.join(cmd for cmd in CMD_TO_COUNT) + '\n')
    
    concurrent_exec()
    print2xlsx(args.output)
