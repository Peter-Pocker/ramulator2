#include <filesystem>
#include <iostream>
#include <fstream>

#include "frontend/frontend.h"
#include "base/exception.h"
#include "base/clocked.h"

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


    struct TraceLet {
      size_t traceid;
      bool is_write;
      AddrVec_t addr_vec;
    };

    struct LaunchSetting {
      Clk_t period = 1; // Frontend tries to launch a request every period.
      size_t retries = -1; // Maximum chances to retry after request failed to be enqueued by DRAM. -1 means infinity.
    };

    struct Status {
      TraceLet *curTraceLet;
      Clk_t cycles2launch; // Launch a new request or retry after such many cycles.
      size_t retries_left; // Remained retry chances.
      size_t m_num_req_pending; // The number of requests which are waiting for callback.
    };
    // The data size (in byte) of a single read/write DRAM operation.
    // UNIT_TRANSFER_SIZE must be a power of 2.
    const Addr_t UNIT_TRANSFER_SIZE = 512;

    Clk_t m_clk = 0;

    std::vector<Trace> m_trace;
    std::vector<std::vector<TraceLet> > m_tracelet;

    size_t m_trace_length = 0;
    size_t m_curr_trace_idx = 0;
    size_t m_tracelet_length = 0;
    size_t m_curr_tracelet_idx = 0; // Index in a trace's tracelets.

    LaunchSetting launch_setting;

    Status cur_status;

    Logger_t m_logger;

  public:
    void init() override {
      std::string trace_path_str = param<std::string>("path").desc("Path to the load store trace file.").required();
      m_clock_ratio = param<uint>("clock_ratio").required();
      launch_setting.period = param<uint>("period").required();
      launch_setting.retries = param<uint>("retries").required();

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
      if (cur_status.cycles2launch) {
        cur_status.cycles2launch = (cur_status.cycles2launch - 1) % launch_setting.period;
        ++m_clk;
        return;
      } else {
        cur_status.cycles2launch = launch_setting.period - 1;
      }
      bool isRetry = (cur_status.retries_left > 0);
      if (isRetry) {
        cur_status.retries_left--;
      } else { // Stop retrying and launch a new request.
        cur_status.curTraceLet = getNextTraceLet();
      }
      if (!cur_status.curTraceLet) { // ALl requests have been launched.
        ++m_clk;
        return;
      }
      const TraceLet& t = *(cur_status.curTraceLet);
      // Print request info.
      // TODO: Add clock info.
      std::cout << "[REQUEST] " << (t.is_write ? "WRITE" : " READ") << " addr: " << t.addr_vec[1] << std::endl;

      Request req(t.addr_vec[1], t.is_write ? Request::Type::Write : Request::Type::Read, 0, [this](Request &r) {
        done();
        // Print the time cost.
        std::cout << "[DONE] " << r.addr << ": " << r.depart - r.arrive << " cycles." <<  std::endl;
      });
      req.addr = t.addr_vec[1];

      bool success = m_memory_system->send(req);
      if (success) {
        if (!t.is_write) {
          cur_status.m_num_req_pending++;
        }
        cur_status.retries_left = 0;
      } else {
        std::cout << "[REQUEST FAILED] trace ID: " << t.traceid << ". tracelet ID: " << m_curr_tracelet_idx << std::endl;
        if (!isRetry) {
          if (!launch_setting.retries) { // Never retry.
            cur_status.retries_left = 0;
          } else if (launch_setting.retries > 0) { // Finite retries.
            cur_status.retries_left = launch_setting.retries;
          } else { // Retry until success.
            cur_status.retries_left++; // Keep retries number constant.
          }
        }
      }
      ++m_clk;
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

        Addr_t addr = std::stoll(tokens[1]);
        Addr_t size = std::stoll(tokens[2]);

        m_trace.push_back({is_write, addr, size});

        // Parse big memory request into small pieces.
        // Address alignment.
        Addr_t addr_musk = ~(UNIT_TRANSFER_SIZE-1);
        Addr_t init_addr = addr & addr_musk;
        Addr_t end_addr = ((addr+size)%addr_musk) == 0 ? (addr+size) : (((addr+size)&addr_musk)+UNIT_TRANSFER_SIZE);
        
        std::vector<TraceLet> tracelet;
        for (Addr_t cur_addr = init_addr; cur_addr < end_addr; cur_addr += UNIT_TRANSFER_SIZE) {
          AddrVec_t addrv;
          addrv.push_back(0); // Memory controller ID.
          addrv.push_back(cur_addr); // Memory address.
          tracelet.push_back({m_trace_length, is_write, addrv});
          ++m_tracelet_length;
        }
        m_tracelet.push_back(tracelet);

        ++m_trace_length;
      }
      trace_file.close();
    };

    bool is_finished() override {
      if (cur_status.m_num_req_pending == 0 && m_curr_tracelet_idx >= m_tracelet_length) {
        std::cout << "Now: " << m_clk << std::endl;
        return true;
      }
      else return false;
    };
    
    void done() {
      cur_status.m_num_req_pending--;
    }

    TraceLet* getNextTraceLet() {
      if (m_curr_tracelet_idx < m_tracelet[m_curr_trace_idx].size()-1) {
        ++m_curr_tracelet_idx;
      } else {
        ++m_curr_trace_idx;
        m_curr_tracelet_idx = 0;
      }
      if (m_curr_trace_idx == m_trace.size()) {
        return nullptr;
      } else {
        return &(m_tracelet[m_curr_trace_idx][m_curr_tracelet_idx]);
      }
    }
  
};

}        // namespace Ramulator