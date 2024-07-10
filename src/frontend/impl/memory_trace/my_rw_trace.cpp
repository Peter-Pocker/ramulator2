#include <filesystem>
#include <iostream>
#include <fstream>
#include <algorithm>
#include <random>
#include <ctime>

#include "frontend/frontend.h"
#include "base/exception.h"

namespace Ramulator {

namespace fs = std::filesystem;

class MyRWTrace : public IFrontEnd, public Implementation {
  RAMULATOR_REGISTER_IMPLEMENTATION(IFrontEnd, MyRWTrace, "MyRWTrace", "My Read/Write DRAM address vector trace.")

  private:
    struct Trace {
      bool is_write;
      Addr_t addr;
      Addr_t size;
    };

    struct LaunchSetting {
      Clk_t period; // Frontend tries to launch a request every period.
      int32_t max_retry; // Maximum chances to retry after request failed to be enqueued by DRAM. -1 means infinity.
      bool shuffle_tracelet; // Whether to shuffle the tracelets of a trace.
      bool shuffle_trace; // Whether to shuffle the traces.
      uint32_t seed; // Random seed.
    };

    struct Status {
      Trace *curTraceLet;
      Clk_t cycles2launch; // Launch a new request or retry after such many cycles.
      size_t retries_left; // Remained retry chances.
      size_t m_num_req_pending; // The number of requests which are waiting for callback.
    };

    // The data size (in byte) of a single read/write DRAM operation.
    // UNIT_TRANSFER_SIZE must be a power of 2.
    Addr_t UNIT_TRANSFER_SIZE;

    Clk_t m_clk = 0;

    std::vector<Trace> m_trace;
    std::vector<std::vector<Trace> > m_tracelet;

    std::ofstream access_log;

    size_t m_trace_length;
    size_t m_tracelet_length;
    size_t m_curr_trace_idx = 0;
    size_t m_curr_tracelet_idx = 0; // Index in a trace's tracelets.
    size_t num_trace_sent = 0;
    size_t num_read_sent = 0;
    size_t num_write_sent = 0;

    LaunchSetting launch_setting;

    Status cur_status;

    Logger_t m_logger;    

  public:
    void init() override {
      std::string trace_path_str = param<std::string>("path").desc("Path to the load store trace file.").required();
      std::string mem_access_log_path_str = param<std::string>("access_log").desc("Path to the output log file.").default_val("memory_access.log");
      access_log.open(mem_access_log_path_str);
      if (!access_log.is_open()) {
        throw ConfigurationError("Unable to open file: {}.", mem_access_log_path_str);
      }
      m_clock_ratio = param<uint>("clock_ratio").required();
      launch_setting.period = param<Clk_t>("period").default_val(1);
      launch_setting.max_retry = param<int32_t>("max_retry").default_val(-1);
      launch_setting.shuffle_tracelet = param<bool>("shuffle_tracelet").default_val(false);
      launch_setting.shuffle_trace = param<bool>("shuffle_trace").default_val(false);
      launch_setting.seed = param<uint32_t>("seed").default_val(time(nullptr));
      UNIT_TRANSFER_SIZE = param<uint32_t>("UNIT_TRANSFER_SIZE").default_val(64); // In bytes.

      m_logger = Logging::create_logger("MyRWTrace");

      m_logger->info("Loading trace file {} ...", trace_path_str);
      init_trace(trace_path_str);
      m_logger->info("Loaded {} lines.", m_trace.size());
      if (!m_trace_length) {
        throw ConfigurationError("Blank trace.");
      }

      cur_status.cycles2launch = 0;
      cur_status.retries_left = 1;
      cur_status.m_num_req_pending = 0;
      cur_status.curTraceLet = &(m_tracelet[0][0]);
    };


    void tick() override {
      ++m_clk;
      if (cur_status.cycles2launch) {
        cur_status.cycles2launch = (cur_status.cycles2launch - 1) % launch_setting.period;
        return;
      } else {
        cur_status.cycles2launch = launch_setting.period - 1;
      }
      bool isRetry = (cur_status.retries_left > 0);
      if (isRetry) {
        // std::cout << "Retrying" << std::endl;
      } else { // Stop retrying and launch a new request.
        cur_status.curTraceLet = get_next_tracelet();
      }
      if (!cur_status.curTraceLet) { // ALl requests have been launched.
        return;
      }
      const Trace& t = *(cur_status.curTraceLet);
      // Print request info.
      // TODO: Add clock info.
      // std::cout << "[REQUEST] " << (t.is_write ? "WRITE" : " READ") << " addr: " << t.addr << std::endl;

      bool success = m_memory_system->send({t.addr, t.is_write ? Request::Type::Write : Request::Type::Read, 0, [this](Request &r) {
        finish_read(r);
      }});

      if (success) {
        if (!t.is_write) {
          ++num_read_sent;
          cur_status.m_num_req_pending++;
        } else {
          ++num_write_sent;
        }
        cur_status.retries_left = 0;
      } else {
        // std::cout << "[REQUEST FAILED] trace ID: " << m_curr_trace_idx << ". tracelet ID: " << m_curr_tracelet_idx << std::endl;
        
        if (!launch_setting.max_retry) { // Never retry.
          cur_status.retries_left = 0;
        } else if (launch_setting.max_retry > 0) { // Finite retries.
          if (!isRetry) {
            cur_status.retries_left = launch_setting.max_retry;
          } else {
            cur_status.retries_left--;
          }
        } else { // Retry until success.
          cur_status.retries_left = 1; // Keep retries number constant.
        }
        
      }
    };

  private:
    void init_trace(const std::string& file_path_str) {
      fs::path trace_path(file_path_str);
      if (!fs::exists(trace_path)) {
        throw ConfigurationError("Trace {} does not exist!", file_path_str);
      }

      std::ifstream trace_file(trace_path);
      if (!trace_file.is_open()) {
        throw ConfigurationError("Trace {} cannot be opened!", file_path_str);
      }

      std::mt19937 rand_engine(launch_setting.seed);

      m_trace_length = 0;
      m_tracelet_length = 0;
      
      std::string line;      
      while (std::getline(trace_file, line)) {
        std::vector<std::string> tokens;
        tokenize(tokens, line, " ");

        // TODO: Add line number here for better error messages
        if (tokens.size() != 3) {
          throw ConfigurationError("Trace {} format invalid!", file_path_str);
        }

        bool is_write = false; 
        if (tokens[0] == "R") {
          is_write = false;
        } else if (tokens[0] == "W") {
          is_write = true;
        } else {
          throw ConfigurationError("Trace {} format invalid!", file_path_str);
        }

        Addr_t addr = std::stoll(tokens[1], nullptr, 0);
        Addr_t size = std::stoll(tokens[2], nullptr, 0);

        m_trace.push_back({is_write, addr, size});

        // Parse big memory request into small pieces.
        // Address alignment.
        Addr_t addr_musk = ~(UNIT_TRANSFER_SIZE-1);
        Addr_t init_addr = addr & addr_musk;
        Addr_t end_addr = ((addr+size)%addr_musk) == 0 ? (addr+size) : (((addr+size)&addr_musk)+UNIT_TRANSFER_SIZE);
        
        m_tracelet.push_back({});
        for (Addr_t cur_addr = init_addr; cur_addr < end_addr; cur_addr += UNIT_TRANSFER_SIZE) {
          m_tracelet[m_trace_length].push_back({is_write, cur_addr, UNIT_TRANSFER_SIZE});
          ++m_tracelet_length;
        }
        if (launch_setting.shuffle_tracelet) {
          std::shuffle(m_tracelet[m_trace_length].begin(), m_tracelet[m_trace_length].end(), rand_engine);
        }
        ++m_trace_length;
      }
      if (launch_setting.shuffle_trace) {
        std::shuffle(m_tracelet.begin(), m_tracelet.end(), rand_engine);
      }
      trace_file.close();
    };

    bool is_finished() override {
      if (cur_status.m_num_req_pending == 0 && m_curr_trace_idx >= m_trace_length) {
        std::cout << "Now: " << m_clk << std::endl;
        std::cout << "Seed: " << launch_setting.seed << std::endl;
        std::cout << "trace number: " << m_tracelet_length << std::endl;
        std::cout << "Read number: " << num_read_sent << std::endl;
        std::cout << "Write number: " << num_write_sent << std::endl;
        access_log.close();
        return true;
      }
      else return false;
    };
    
    void finish_read(Request &r) {
      cur_status.m_num_req_pending--;
      access_log << r.depart - r.arrive << std::endl;
    }

    Trace* get_next_tracelet() {
      if (m_curr_trace_idx >= m_trace_length) {
        return nullptr;
      }
      // Caution! Comparison between unsigned numbers!
      if (m_curr_tracelet_idx < m_tracelet[m_curr_trace_idx].size()-1) {
        ++m_curr_tracelet_idx;
      } else {
        ++m_curr_trace_idx;
        m_curr_tracelet_idx = 0;
      }
      if (m_curr_trace_idx == m_trace_length) {
        return nullptr;
      } else {
        return &(m_tracelet[m_curr_trace_idx][m_curr_tracelet_idx]);
      }
    }

    void gen_trace(uint32_t trace_num, std::string output_path="output.trace") {
      std::ofstream ofs(output_path);
      if (!ofs.is_open()) {
        throw std::runtime_error("Unable to open file.");
      }
      std::mt19937 rand_engine(launch_setting.seed);
      std::uniform_int_distribution<int> distribution(1, 8);

      Addr_t init_addr = 0x000123000;

      m_trace_length = 0;
      Addr_t addr = init_addr;
      for (uint32_t i = 0; i < trace_num; ++i) {
        Addr_t size = distribution(rand_engine) * 256;
        bool is_write = distribution(rand_engine) < 3;
        m_trace.push_back({is_write, addr, size});
        addr += size;
        ++m_trace_length;
      }
      std::shuffle(m_trace.begin(), m_trace.end(), rand_engine);

      uint32_t i = 0;
      Addr_t addr_musk = ~(UNIT_TRANSFER_SIZE-1);
      for (Trace &t : m_trace) {
        ofs << (t.is_write?"W":"R") << " " << t.addr << " " << t.size << std::endl;

        Addr_t first_addr = t.addr & addr_musk;
        Addr_t end_addr = ((t.addr+t.size)%addr_musk) == 0 ? (t.addr+t.size) : (((t.addr+t.size)&addr_musk)+UNIT_TRANSFER_SIZE);
        
        m_tracelet.push_back({});
        for (Addr_t cur_addr = first_addr; cur_addr < end_addr; cur_addr += UNIT_TRANSFER_SIZE) {
          m_tracelet[i].push_back({t.is_write, t.addr, UNIT_TRANSFER_SIZE});
          ++m_tracelet_length;
        }
        if (launch_setting.shuffle_tracelet) {
          std::shuffle(m_tracelet[i].begin(), m_tracelet[i].end(), rand_engine);
        }
        ++i;
      }

      ofs.close();
    }

};

}        // namespace Ramulator