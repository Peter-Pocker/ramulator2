# # Generate a trace file.
# python gen_trace.py -n 1048576 -f thread_info.yaml -o trace/1thread_rand_readonly_1M.trace -p random

# Simulation config.
config_file='ddr4.yaml'
stdout_file='debug.log'
cmd_cnt_file='cmd_cnt.log'
cmd_file='issue_log_ch0.log'
latency_file=$(grep 'access_log:' $config_file | sed -n 's/.*access_log: *\(.*\)/\1/p')
output_fig_dir='plot/'

trace_path=$(grep 'path:' $config_file | grep '.trace' | sed -n 's/.*path: *\(.*\)/\1/p')
mapping=$(grep 'mapping:' $config_file | sed -n 's/.*mapping: *\(.*\)/\1/p')

echo '---------- Begin Simulation ---------'
echo "Trace : $trace_path"
echo "Mapper: $mapping"
echo "stdout redirected into $stdout_file"
build/ramulator2 -f $config_file > $stdout_file
grep -E 'total_num_read_requests|total_num_write_requests|memory_system_cycles' $stdout_file | sed 's/^[ \t]*//'
cat $cmd_cnt_file
echo '---------- End Simulation -----------'

# Post-simulation process.
echo '------- Post-simulation Process -----'
if [ ! -d $output_fig_dir ]; then
    mkdir -p $output_fig_dir
fi
python interval.py -i $cmd_file -o $output_fig_dir -n "trace: $trace_path
mapper: $mapping"
python latency_bd.py -i $latency_file -o $output_fig_dir -n "trace: $trace_path
mapper: $mapping"
